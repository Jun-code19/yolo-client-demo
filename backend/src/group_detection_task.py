"""分组检测任务：轮询组内设备单帧取图 + 普通 YOLO 检测（无追踪/智能方案）"""
import asyncio
import base64
import colorsys
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.cjk_font import ascii_fallback_text, load_cjk_font
from src.database import (
    SessionLocal,
    DetectionConfig,
    DetectionEvent,
    Device,
    DeviceGroup,
    EventStatus,
    SaveMode,
)
from src.detection_runtime import is_within_active_period
from src.frame_acquisition import DEFAULT_GROUP_SETTINGS, frame_acquisition
from src.device_roi import (
    coerce_area_coordinates,
    get_device_roi_pixels,
    filter_detections_by_roi,
    draw_device_roi,
)
from src.yolo_task_utils import (
    is_segmentation_type,
    process_yolo_results,
    draw_segmentation_detections,
    build_detection_meta,
    load_detection_model,
    predict_detection_frame,
    class_names_for_model_path,
)

logger = logging.getLogger(__name__)


class GroupDetectionTask:
    """按设备分组定时取帧并执行普通检测"""

    def __init__(
        self,
        config_id: str,
        group_id: str,
        group_name: str,
        model_path: str,
        confidence: float,
        models_type: str,
        is_gpu: bool,
        target_class: List[str],
        save_mode: SaveMode,
        group_settings: Optional[dict] = None,
        runtime_config: Optional[dict] = None,
        stream_type: str = "main",
        inference_pipeline: Optional[dict] = None,
    ):
        self.config_id = config_id
        self.config_mode = "group"
        self.group_id = group_id
        self.group_name = group_name
        self.device_id = group_id  # 兼容日志/状态接口
        self.device_name = group_name
        self.device_ip = ""
        self.model_path = model_path
        self.confidence = confidence
        self.models_type = models_type
        self.is_gpu = is_gpu
        self.target_class = target_class or []
        self.save_mode = save_mode
        self.group_settings = {**DEFAULT_GROUP_SETTINGS, **(group_settings or {})}
        self.runtime_config = runtime_config or {}
        self.stream_type = stream_type or "main"
        self.frequency = "realtime"

        self.stop_event = threading.Event()
        self.thread = None
        self.loop = None
        self.model = None
        self.infer_device = "cpu"
        self.is_onnx_model = False
        self.device = None
        self.class_names = None
        self.connected = False
        self.clients = set()
        self.last_device_id = None
        self.message_queue = asyncio.Queue()
        self.broadcast_task = None
        self.class_colors = {}
        self._count_font = None
        self._last_event_at: dict = {}
        self._event_cooldown = float(self.group_settings.get("event_cooldown_sec") or 3)
        del inference_pipeline

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    async def stop(self):
        self.stop_event.set()
        if self.broadcast_task:
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except asyncio.CancelledError:
                pass
        try:
            if self.loop and not self.message_queue.empty():
                await self.message_queue.put(None)
        except Exception:
            pass
        if self.thread:
            self.thread.join(timeout=5)
    def load_model(self) -> bool:
        try:
            abs_model_path = os.path.abspath(self.model_path)
            if not os.path.exists(abs_model_path):
                base_name = os.path.basename(abs_model_path)
                alt_path = os.path.abspath(os.path.join("models", base_name))
                if os.path.exists(alt_path):
                    abs_model_path = alt_path
                    self.model_path = os.path.join("models", base_name)
                else:
                    logger.error("无法找到模型文件: %s", self.model_path)
                    return False

            self.model, self.infer_device, self.is_onnx_model = load_detection_model(
                abs_model_path,
                self.models_type,
                self.is_gpu,
                class_names=class_names_for_model_path(abs_model_path),
            )
            self.class_names = getattr(self.model, "names", {})
            return True
        except Exception as exc:
            logger.error("分组检测加载模型失败: %s", exc)
            return False

    def _run_loop(self):
        if not self.load_model():
            return

        device_interval = float(self.group_settings.get("device_interval_sec") or 1.0)
        device_interval = max(0.2, device_interval)
        try:
            round_interval = max(0.0, float(self.group_settings.get("group_round_interval_sec") or 0))
        except (TypeError, ValueError):
            round_interval = 0.0

        while not self.stop_event.is_set():
            try:
                if not is_within_active_period(datetime.now(), self.runtime_config):
                    time.sleep(1)
                    continue

                devices = self._load_group_devices()
                if not devices:
                    self.connected = False
                    time.sleep(2)
                    continue

                for device in devices:
                    if self.stop_event.is_set():
                        break
                    if not is_within_active_period(datetime.now(), self.runtime_config):
                        break

                    self._process_device(device)
                    time.sleep(device_interval)

                if round_interval > 0 and not self.stop_event.is_set():
                    time.sleep(round_interval)
            except Exception as exc:
                logger.error("分组检测循环异常 config=%s: %s", self.config_id, exc)
                time.sleep(1)

        self.connected = False

    def _load_group_devices(self) -> List[Device]:
        db = SessionLocal()
        try:
            devices = (
                db.query(Device)
                .filter(Device.group_id == self.group_id, Device.status.is_(True))
                .order_by(Device.device_name)
                .all()
            )
            for device in devices:
                db.expunge(device)
            return devices
        finally:
            db.close()

    def _get_device_area_coordinates(self, device_id: str):
        db = SessionLocal()
        try:
            row = (
                db.query(Device.area_coordinates)
                .filter(Device.device_id == device_id)
                .first()
            )
            return coerce_area_coordinates(row[0] if row else None)
        finally:
            db.close()

    def _process_device(self, device: Device) -> None:
        self.last_device_id = device.device_id
        self.device_name = device.device_name
        self.device_ip = device.ip_address or ""

        stream_type = getattr(device, "stream_type", None) or self.stream_type
        frame = frame_acquisition.get_frame(
            device, self.group_settings, stream_type=stream_type
        )
        if frame is None:
            logger.debug("分组检测跳过设备(取帧失败): %s", device.device_id)
            return
        self.connected = True
        preview_frame = frame.copy()
        detections = []
        speed = 0.0
        roi_pixels = None
        try:
            results = predict_detection_frame(
                self.model,
                frame,
                infer_device=self.infer_device,
                is_onnx=self.is_onnx_model,
                confidence=self.confidence,
            )
            speed = results[0].speed
            detections = self._process_detection_results(results)

            area_coordinates = self._get_device_area_coordinates(device.device_id)
            roi_pixels = get_device_roi_pixels(area_coordinates, frame.shape)
            if roi_pixels:
                before_count = len(detections)
                detections = filter_detections_by_roi(detections, roi_pixels)
                draw_device_roi(preview_frame, roi_pixels)
                logger.info(
                    "分组检测区域过滤 device=%s: %d -> %d",
                    device.device_id,
                    before_count,
                    len(detections),
                )

            if self.models_type == "pose" and detections:
                preview_frame = self._display_pose_results(preview_frame, results[0])
            elif is_segmentation_type(self.models_type) and detections:
                preview_frame = draw_segmentation_detections(
                    preview_frame,
                    detections,
                    self._get_class_color,
                )
            else:
                preview_frame = self._draw_detections_list(preview_frame, detections)
            preview_frame = self._draw_total_count_label(preview_frame, len(detections))
            if detections:
                push_label = (area_coordinates or {}).get("pushLabel") or ""
                self._process_detection_events(frame, detections, device, speed, roi_pixels)
        except Exception as exc:
            logger.error(
                "分组检测设备推理失败 config=%s device=%s: %s",
                self.config_id,
                device.device_id,
                exc,
            )
        finally:
            if self.clients:
                self.broadcast_img_result(preview_frame, detections, device.device_id)

    def _process_detection_results(self, results):
        return process_yolo_results(
            results,
            self.target_class,
            include_segmentation=is_segmentation_type(self.models_type),
        )

    def _process_detection_events(self, frame, detections, device: Device, speed, roi_pixels=None):
        if not detections:
            return
        now = time.time()
        last_at = self._last_event_at.get(device.device_id, 0.0)
        if now - last_at < self._event_cooldown:
            return
        try:
            self.save_detection_event(frame, detections, device.device_id, roi_pixels)
            self._last_event_at[device.device_id] = now
        except Exception as exc:
            logger.error("分组检测保存事件失败: %s", exc)

    def save_detection_event(self, frame, detections, device_id: str, roi_pixels=None):
        try:
            db = SessionLocal()
            event_id = str(uuid.uuid4())
            current_time = datetime.now()

            config = (
                db.query(DetectionConfig)
                .filter(DetectionConfig.config_id == self.config_id)
                .first()
            )
            if not config:
                db.close()
                return

            event = DetectionEvent(
                event_id=event_id,
                config_id=self.config_id,
                device_id=device_id,
                timestamp=current_time,
                event_type=self.models_type,
                confidence=max(d["confidence"] for d in detections) if detections else 0.0,
                bounding_box=detections,
                status=EventStatus.new,
                created_at=current_time,
            )
            event.meta_data = build_detection_meta(self.models_type, detections, self.target_class)
            event.meta_data["group_id"] = self.group_id
            event.meta_data["group_name"] = self.group_name

            if self.save_mode in (SaveMode.screenshot, SaveMode.both):
                save_dir = Path(
                    f"storage/events/{current_time.strftime('%Y-%m-%d')}/{device_id}"
                )
                save_dir.mkdir(parents=True, exist_ok=True, mode=0o777)
                thumbnail_path = save_dir / f"{event_id}.jpg"
                quality = 70
                save_image = self._render_saved_event_image(frame, detections, roi_pixels)
                cv2.imwrite(
                    str(thumbnail_path), save_image, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                )
                event.thumbnail_path = str(thumbnail_path)

            db.add(event)
            db.commit()
            logger.info("分组检测已保存事件: %s device=%s", event_id, device_id)
            self._push_group_detection_data(frame, detections, device_id)
        except Exception as exc:
            logger.error("分组检测保存事件失败: %s", exc)
            if "db" in locals() and db:
                db.rollback()
        finally:
            if "db" in locals() and db:
                db.close()

    def _push_group_detection_data(self, frame, detections, device_id: str):
        from src.data_pusher import data_pusher

        if not data_pusher.push_configs:
            return
        push_data = {
            "cameraInfo": f"{self.group_name}:{device_id}",
            "deviceId": device_id,
            "groupId": self.group_id,
            "enteredCount": 0,
            "exitedCount": 0,
            "stayingCount": len(detections),
            "passedCount": 0,
            "recordTime": datetime.now().isoformat() + "+08:00",
            "event_description": "分组目标检测",
            "target_class": self.target_class,
        }
        data_pusher.push_data(
            data=push_data,
            image=frame,
            tags=[f"group_{self.group_id}", f"device_{device_id}"],
            config_id=self.config_id,
        )

    def _render_saved_event_image(self, frame, detections, roi_pixels=None):
        """生成带目标框/mask 与总数标注的入库截图"""
        img = frame.copy()
        if roi_pixels:
            draw_device_roi(img, roi_pixels)
        if is_segmentation_type(self.models_type) and detections:
            img = draw_segmentation_detections(img, detections, self._get_class_color)
        else:
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
                class_id = det.get("class_id", 0)
                color = self._get_class_color(class_id)
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                class_name = det.get("class_name") or str(class_id)
                conf = det.get("confidence", 0.0)
                label = f"{class_name}: {conf:.2f}"
                cv2.putText(
                    img,
                    label,
                    (x1, max(y1 - 8, 16)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                )
        return self._draw_total_count_label(img, len(detections))

    def _get_count_font(self, size=28):
        if self._count_font is not None:
            return self._count_font
        self._count_font = load_cjk_font(size)
        return self._count_font

    def _draw_total_count_label(self, img, count: int):
        label = f"目标总数: {count}"
        font = self._get_count_font()
        if font is None:
            cv2.putText(
                img,
                ascii_fallback_text(label),
                (12, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            return img
        frame_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)
        draw.text((12, 12), label, font=font, fill=(0, 255, 0))
        return cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)

    def _draw_detections_list(self, img, detections):
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cls = det.get("class_id", 0)
            conf = det.get("confidence", 0.0)
            color = self._get_class_color(cls)
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            class_name = det.get("class_name") or (
                self.class_names[cls] if self.class_names else f"Class {cls}"
            )
            label = f"{class_name}: {conf:.2f}"
            cv2.putText(
                img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )
        return img

    def _display_detection_results(self, img, results, show_boxes=True):
        if not show_boxes or not hasattr(results, "boxes") or results.boxes is None:
            return img
        for box in results.boxes:
            from src.yolo_box_compat import box_class_id, box_confidence, box_xyxy_array

            xy = box_xyxy_array(box)
            x1, y1, x2, y2 = xy
            conf = box_confidence(box)
            cls = box_class_id(box)
            if str(cls) not in self.target_class:
                continue
            color = self._get_class_color(cls)
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            class_name = self.class_names[cls] if self.class_names else f"Class {cls}"
            label = f"{class_name}: {conf:.2f}"
            cv2.putText(
                img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )
        return img

    def _display_pose_results(self, img, results):
        if not hasattr(results, "keypoints") or results.keypoints is None:
            return img
        for person_keypoints in results.keypoints:
            for kpt in person_keypoints.data[0]:
                x, y, conf = kpt
                if conf > 0.5:
                    cv2.circle(img, (int(x), int(y)), 5, (0, 255, 0), -1)
        return img

    def _get_class_color(self, class_id):
        if class_id not in self.class_colors:
            if self.class_names:
                colors = self._generate_colors(len(self.class_names))
                self.class_colors = {i: color for i, color in enumerate(colors)}
            else:
                self.class_colors[class_id] = tuple(np.random.randint(0, 255, 3).tolist())
        return self.class_colors[class_id]

    @staticmethod
    def _generate_colors(num_classes):
        hsv_tuples = [(x / num_classes, 1.0, 1.0) for x in range(num_classes)]
        colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        return [
            (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)) for x in colors
        ]

    def broadcast_img_result(self, frame, detections, device_id: str):
        if not self.clients:
            return
        try:
            _, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            message = {
                "device_id": device_id,
                "config_id": self.config_id,
                "group_id": self.group_id,
                "timestamp": time.time(),
                "image": base64.b64encode(buffer.tobytes()).decode("utf-8"),
                "detections": detections,
            }
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(
                    lambda: self.message_queue.put_nowait(message)
                )
        except Exception as exc:
            logger.error("分组检测广播预览帧失败: %s", exc)

    async def broadcast_worker(self):
        try:
            while not self.stop_event.is_set():
                try:
                    message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                    if message is None:
                        break
                    for client in list(self.clients):
                        try:
                            await client.send_json(message)
                        except Exception as exc:
                            logger.error("分组预览推送失败: %s", exc)
                            self.clients.discard(client)
                    self.message_queue.task_done()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    def add_client(self, websocket):
        self.clients.add(websocket)
        if not self.broadcast_task or self.broadcast_task.done():
            try:
                if self.loop and self.loop.is_running():
                    self.broadcast_task = asyncio.run_coroutine_threadsafe(
                        self.broadcast_worker(), self.loop
                    )
                else:
                    self.loop = asyncio.get_event_loop()
                    self.broadcast_task = asyncio.create_task(self.broadcast_worker())
            except Exception as exc:
                logger.error("启动分组预览广播失败: %s", exc)

    def remove_client(self, websocket):
        self.clients.discard(websocket)
        if not self.clients and self.broadcast_task:
            self.broadcast_task.cancel()
            self.broadcast_task = None
