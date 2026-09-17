"""
检测任务模块 - 用于执行检测任务，包括目标检测、姿态检测、智能分析等
"""
import asyncio
import cv2
import numpy as np
import time
import threading
import logging
from collections import deque
from typing import List, Optional, Dict, Any
import os
import uuid
import colorsys
import base64 # 导入base64编码
from pathlib import Path # 导入路径模块
from threading import Lock # 导入锁
from datetime import datetime, timedelta # 导入日期时间模块

# 导入数据库模块
from src.database import (
    SessionLocal, DetectionConfig, DetectionEvent, Device, 
    DetectionPerformance, SaveMode, EventStatus
)
# 导入目标追踪模块
from src.tracker import ObjectTracker
# 导入数据推送模块
from src.data_pusher import data_pusher
from src.frame_acquisition import open_rtsp_capture, probe_rtsp_host
from src.rtsp_url import build_rtsp_url
from src.detection_runtime import is_within_active_period, get_frame_interval
from src.smart_scenarios import is_multi_scenario_config, normalize_smart_config, SCENARIO_TYPE_LABELS, _resolve_counting_type
from src.device_roi import (
    coerce_area_coordinates,
    get_device_roi_pixels,
    filter_detections_by_roi,
    draw_device_roi,
)
from src.yolo_box_compat import box_class_id, box_confidence, box_xyxy_array
from src.yolo_task_utils import (
    is_segmentation_type,
    process_yolo_results,
    draw_segmentation_detections,
    build_detection_meta,
    load_detection_model,
    predict_detection_frame,
)

logger = logging.getLogger(__name__)

try:
    from src.ffmpeg_decoder_docker import FFmpegDecoderDocker

    FFMPEG_DECODER_AVAILABLE = True
except ImportError:
    FFMPEG_DECODER_AVAILABLE = False
    logger.warning("FFmpeg 管道解码不可用，将使用 OpenCV")

USE_FFMPEG_DECODER = False  # RTSP 默认 OpenCV；必要时改为 True

class DetectionTask:
    """优化后的检测任务类"""
    
    def __init__(self, device_id: str, device_name: str, device_ip: str, config_id: str, model_path: str, 
                 confidence: float, models_type: str, is_gpu: bool, target_class: List[str],                  save_mode: SaveMode, area_coordinates:Optional[dict]=None,
                 device_roi: Optional[dict] = None,
                 stream_type: str = 'main', frequency: str = 'realtime', runtime_config: Optional[dict] = None,
                 inference_pipeline: Optional[dict] = None):
        del inference_pipeline
        self.device_id = device_id
        self.device_name = device_name
        self.device_ip = device_ip
        self.config_id = config_id
        self.model_path = model_path       
        self.confidence = confidence
        self.models_type = models_type
        self.is_gpu = is_gpu
        self.target_class = target_class
        self.save_mode = save_mode
        self.area_coordinates = area_coordinates  # 检测配置中的智能方案区域
        self.device_roi = device_roi  # 设备管理中的检测区域（enabled + points）
        self.class_colors = {}  # 用于存储每个类别的固定颜色
        self.class_names = None  # 用于存储类别名称
        self.stream_type = stream_type or 'main'
        self.frequency = frequency or 'realtime'
        self.runtime_config = runtime_config or {}
        self.frame_interval = get_frame_interval(self.runtime_config)
        self.last_detection_time = 0.0
        self.stop_event = threading.Event()
        self.model = None
        self.infer_device = "cpu"
        self.is_onnx_model = False
        self.device = None
        self.cap = None
        self.ffmpeg_decoder = None  # 添加GPU解码器
        self.thread = None
        self.frame_thread = None
        self.lock = Lock()  # 初始化锁
        self.frame_buffer = deque(maxlen=1)  # 存储最近的帧
        self.last_detection_time = time.time()
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.clients = set()  # WebSocket客户端集合，用于实时预览
        self._detection_loop = None  # 检测线程专属事件循环
        self._preview_loop = None  # FastAPI/Uvicorn 预览广播循环
        self.loop = None  # 兼容旧引用，始终指向 _detection_loop
        self.message_queue = None  # 预览广播队列（绑定 _preview_loop）
        self.broadcast_task = None  # 添加广播任务引用

        # 初始化目标追踪参数
        self.max_trajectory_length = 30
        self.max_age = 10
        self.min_hits = 3
        self.iou_threshold = 0.3

        # 初始化 ObjectTracker
        self.object_tracker = ObjectTracker(max_age=self.max_age, min_hits=self.min_hits, iou_threshold=self.iou_threshold)
        self.last_yolo_event_time = 0.0
        
        # 设置智能分析区域坐标
        if self.area_coordinates:
            # 这里需要等到有实际帧时才能设置，因为需要frame_shape
            self.area_coordinates_set = False
        else:
            self.area_coordinates_set = True
            
        # 性能优化参数
        self.use_ffmpeg_decoder = USE_FFMPEG_DECODER and FFMPEG_DECODER_AVAILABLE
        self.skip_frame_count = 1  # 跳帧数，可根据CPU负载动态调整
        self.last_performance_check = time.time()
        self.performance_check_interval = 3600  # 每3600秒检查一次性能
    
    def _get_fresh_device_roi(self) -> Optional[dict]:
        db = SessionLocal()
        try:
            row = (
                db.query(Device.area_coordinates)
                .filter(Device.device_id == self.device_id)
                .first()
            )
            return coerce_area_coordinates(row[0] if row else None)
        finally:
            db.close()

    def load_model(self): # 加载YOLO模型
        """加载YOLO模型"""
        try:
            abs_model_path = os.path.abspath(self.model_path)
            logger.info(f"加载模型 - 路径: {abs_model_path}")

            if not os.path.exists(abs_model_path):
                base_name = os.path.basename(abs_model_path)
                alt_path = os.path.join("models", base_name)
                alt_abs_path = os.path.abspath(alt_path)
                if os.path.exists(alt_abs_path):
                    abs_model_path = alt_abs_path
                    self.model_path = alt_path
                else:
                    logger.error("无法找到模型文件")
                    return False

            self.model, self.infer_device, self.is_onnx_model = load_detection_model(
                abs_model_path,
                self.models_type,
                self.is_gpu,
            )
            self.class_names = getattr(self.model, "names", {})
            if getattr(self.model, "backend", None) == "rknn":
                logger.info("已使用 RKNN/NPU 推理适配器加载模型")
            elif self.is_onnx_model:
                logger.info("已使用 ONNX 专用推理适配器加载模型")
            else:
                logger.info("已加载 PyTorch/YOLO 模型，device=%s", self.infer_device)
            return True
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            return False
    
    def connect_to_camera(self): # 连接到RTSP摄像机
        """连接到RTSP摄像机"""
        if self.stop_event.is_set():
            return False
        try:
            if self.connected or self.cap or self.ffmpeg_decoder:
                self.release_camera_connection("重新连接前释放")

            db = SessionLocal()
            device = db.query(Device).filter(Device.device_id == self.device_id).first()
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == self.config_id).first()
            db.close()

            if self.stop_event.is_set():
                return False
            
            if not device:
                logger.error(f"设备信息不存在: {self.device_id}")
                return False

            if config and getattr(config, 'stream_type', None):
                self.stream_type = config.stream_type or 'main'

            rtsp_url = build_rtsp_url(device, stream_type=self.stream_type)

            if self.stop_event.is_set():
                return False

            reachable, host_port = probe_rtsp_host(rtsp_url, timeout=2.0)
            if not reachable:
                if not self.stop_event.is_set():
                    logger.error(
                        "摄像机 %s RTSP 端口不可达 (%s)，请检查 IP、网段、路由或防火墙",
                        self.device_id,
                        host_port,
                    )
                return False

            if self.stop_event.is_set():
                return False

            if self.use_ffmpeg_decoder:
                try:
                    self.ffmpeg_decoder = FFmpegDecoderDocker(rtsp_url)
                    if self.ffmpeg_decoder.start():
                        self.connected = True
                        self.reconnect_attempts = 0
                        return True
                   
                except Exception as e:
                    logger.warning(f"FFmpeg 解码初始化失败，回退到 OpenCV: {e}")
            
            # 回退到OpenCV解码（仅在拉流线程内调用，避免跨线程 release）
            logger.info(f"使用OpenCV解码器连接: {self.device_id}")
            if self.stop_event.is_set():
                return False
            cap = open_rtsp_capture(rtsp_url)
            if self.stop_event.is_set():
                try:
                    cap.release()
                except Exception:
                    pass
                return False

            self.cap = cap
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 25)

            if self.cap.isOpened():
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                self.connected = True
                self.reconnect_attempts = 0
                return True

            self.release_camera_connection("连接失败")
            if not self.stop_event.is_set():
                logger.error(f"无法连接到摄像机: {self.device_id}")
            return False
                
        except Exception as e:
            if not self.stop_event.is_set():
                logger.error(f"连接摄像机时出错: {e}")
            return False

    def _is_streaming_allowed(self) -> bool:
        """当前是否处于允许拉流/检测的生效时段"""
        return is_within_active_period(datetime.now(), self.runtime_config)

    def release_camera_connection(self, reason: str = "") -> None:
        """释放摄像机连接（必须在拉流线程内调用，避免 FFmpeg 跨线程崩溃）"""
        with self.lock:
            self.frame_buffer.clear()

        if self.cap:
            try:
                self.cap.release()
            except Exception as e:
                logger.warning(f"释放 OpenCV 连接失败: {self.device_id}, {e}")
            self.cap = None

        if self.ffmpeg_decoder:
            try:
                self.ffmpeg_decoder.stop()
            except Exception as e:
                logger.warning(f"释放解码器失败: {self.device_id}, {e}")
            self.ffmpeg_decoder = None

        if self.connected or reason in ("任务停止", "拉流线程退出"):
            suffix = f" ({reason})" if reason else ""
            logger.info(f"已断开摄像机拉流: {self.device_id}{suffix}")

        self.connected = False
        self.reconnect_attempts = 0

    def _wait_or_stop(self, timeout: float) -> bool:
        """可中断等待，返回 True 表示应停止。"""
        return self.stop_event.wait(timeout=timeout)

    def read_frame(self): # 从摄像机读取帧的线程函数
        """从摄像机读取帧的线程函数"""
        error_count = 0
        last_reconnect_time = time.time()
        schedule_paused = False

        try:
            while not self.stop_event.is_set():
                try:
                    if not self._is_streaming_allowed():
                        if self.connected or self.cap or self.ffmpeg_decoder:
                            self.release_camera_connection("生效时段外暂停拉流")
                        if not schedule_paused:
                            schedule_paused = True
                            logger.info(f"生效时段外，暂停拉流: {self.device_id}")
                        if self._wait_or_stop(1.0):
                            break
                        continue

                    if schedule_paused:
                        schedule_paused = False
                        error_count = 0
                        last_reconnect_time = time.time()
                        self.reconnect_attempts = 0
                        logger.info(f"进入生效时段，恢复拉流: {self.device_id}")

                    # 改进重连逻辑，添加退避策略
                    if not self.connected or error_count > 30:
                        if self.stop_event.is_set():
                            break
                        current_time = time.time()
                        # 添加最小间隔时间，防止频繁重试
                        if current_time - last_reconnect_time > self.reconnect_attempts * 2:
                            if self.reconnect_attempts < self.max_reconnect_attempts:
                                logger.info(f"尝试重新连接摄像机: {self.device_id} (尝试 {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
                                last_reconnect_time = current_time
                                self.reconnect_attempts += 1
                                if self.connect_to_camera():
                                    error_count = 0
                                else:
                                    if self._wait_or_stop(min(2 * self.reconnect_attempts, 10)):
                                        break
                                    continue
                            else:
                                logger.error(f"重连摄像机 {self.device_id} 失败，停止检测任务")
                                break
                        else:
                            if self._wait_or_stop(0.5):
                                break
                            continue
                    
                    if self.stop_event.is_set():
                        break

                    # 根据解码器类型读取帧
                    if self.ffmpeg_decoder:
                        if self.stop_event.is_set():
                            break
                        try:
                            ret, frame = self.ffmpeg_decoder.read()
                        except Exception:
                            ret, frame = False, None
                    else:
                        if not self.cap or self.stop_event.is_set():
                            break
                        ret, frame = self.cap.read()
                    
                    if self.stop_event.is_set():
                        break

                    if not ret:
                        error_count += 1
                        logger.warning(f"从摄像机 {self.device_id} 获取帧失败 ({error_count}/30)")
                        
                        if self._wait_or_stop(0.01):
                            break
                        continue
                    
                    # 重置错误计数
                    if error_count > 0:
                        error_count = 0

                    # 使用锁来确保线程安全
                    with self.lock:
                        self.frame_buffer.append(frame)
                
                except Exception as e:
                    logger.error(f"读取帧时出错: {e}")
                    error_count += 1
                    if self._wait_or_stop(0.1):
                        break
        finally:
            reason = "任务停止" if self.stop_event.is_set() else "拉流线程退出"
            self.release_camera_connection(reason)

    def run_detection(self): # 执行检测的主循环
        """执行检测的主循环"""
        # 为检测线程创建和设置事件循环
        try:
            self._detection_loop = asyncio.new_event_loop()
            self.loop = self._detection_loop
            asyncio.set_event_loop(self._detection_loop)
        except Exception as e:
            logger.error(f"为检测线程创建事件循环失败: {e}")
        
        try:
            # 如果模型已经加载，跳过加载步骤
            if not hasattr(self, 'model') or self.model is None:
                if not self.load_model():
                    return
            
            # 启动读取帧的线程（与检测主线程分离，避免 stop 时 join 错对象）
            self.frame_thread = threading.Thread(
                target=self.read_frame,
                name=f"frame-{self.config_id}",
            )
            self.frame_thread.daemon = True
            self.frame_thread.start()

            frame_count = 0

            if self.area_coordinates and self.area_coordinates.get('alarm_interval'):
                cooldown_period = self.area_coordinates.get('alarm_interval')
            elif self.area_coordinates and is_multi_scenario_config(self.area_coordinates):
                cooldown_period = normalize_smart_config(self.area_coordinates).get('global', {}).get('alarm_interval', 15)
            else:
                cooldown_period = 15  # 检测事件的冷却时间（秒）

            # 动态调整参数
            skip_frame_count = self.skip_frame_count
            last_performance_check = time.time()
            
            while not self.stop_event.is_set():
                try:
                    if not is_within_active_period(datetime.now(), self.runtime_config):
                        if self._wait_or_stop(0.5):
                            break
                        continue

                    # 性能监控和动态调整
                    current_time = time.time()
                    if current_time - last_performance_check > self.performance_check_interval:
                        if not self.stop_event.is_set():
                            self._adjust_performance_parameters()
                        last_performance_check = current_time
                        skip_frame_count = self.skip_frame_count
                                  
                    # 使用锁来安全地访问帧缓存
                    with self.lock:
                        if self.frame_buffer:
                            frame_rgb = self.frame_buffer[-1]  # 获取最新的帧
                        else:
                            if self._wait_or_stop(0.01):
                                break
                            continue  # 如果没有帧，跳过

                    if self.stop_event.is_set():
                        break

                    # 优化：每skip_frame_count帧执行一次检测，减少计算负担
                    frame_count += 1
                    if self.frequency == 'manual':
                        now_ts = time.time()
                        should_detect = now_ts - self.last_detection_time >= self.frame_interval
                    else:
                        should_detect = frame_count % skip_frame_count == 0
                    if should_detect:
                         # 执行检测
                        detect_frame = frame_rgb.copy()
                        if self.stop_event.is_set():
                            break
                        # img_result = frame_rgb.copy() 保留如果保存不带检测结果的帧，可以用于调试 _process_detection_events                 
                        # 使用 try-except 捕获模型推理过程中的错误
                        try:
                            results = predict_detection_frame(
                                self.model,
                                detect_frame,
                                infer_device=self.infer_device,
                                is_onnx=self.is_onnx_model,
                                confidence=self.confidence,
                            )
                            if self.stop_event.is_set():
                                break
                            # 获取速度
                            speed = results[0].speed
                            # 处理检测结果
                            detections = self.process_detection_results(results)
                            device_roi = self._get_fresh_device_roi()
                            roi_pixels = get_device_roi_pixels(device_roi, detect_frame.shape)
                            output_detections = detections
                            
                            # 首次设置区域坐标
                            if self.area_coordinates and not self.area_coordinates_set:
                                self.object_tracker.set_area_coordinates(self.area_coordinates, detect_frame.shape)
                                self.area_coordinates_set = True
                            
                            # 绘制智能方案区域框
                            self.draw_roi(detect_frame)

                            if self._has_smart_analysis():
                                if self.models_type == 'pose' and detections:
                                    detect_frame = self.display_pose_results(detect_frame, results[0])
                                self.object_tracker.update(detections, frame_gap=skip_frame_count)
                                detect_frame = self.object_tracker.draw_tracks(
                                    detect_frame,
                                    max_trajectory_length=self.max_trajectory_length,
                                    show_boxes=True,
                                )
                                self._process_smart_analysis_events(detect_frame, detections, speed, cooldown_period)
                            else:
                                basic_detections = detections
                                if roi_pixels:
                                    draw_device_roi(detect_frame, roi_pixels)
                                    basic_detections = filter_detections_by_roi(detections, roi_pixels)
                                output_detections = basic_detections
                                if basic_detections:
                                    if self.models_type == 'pose':
                                        detect_frame = self.display_pose_results(detect_frame, results[0])
                                    elif is_segmentation_type(self.models_type):
                                        detect_frame = draw_segmentation_detections(
                                            detect_frame,
                                            basic_detections,
                                            self.get_class_color,
                                        )
                                    else:
                                        detect_frame = self.display_detections_list(detect_frame, basic_detections)
                                    self._process_detection_events(
                                        detect_frame, basic_detections, speed, cooldown_period
                                    )

                            if self.frequency == 'manual':
                                self.last_detection_time = time.time()

                            if not self.clients:
                                continue  # 没有客户端连接，跳过下面步骤
                            else:
                                self.broadcast_img_result(detect_frame, output_detections)
                            
                        except Exception as e:
                            logger.error(f"模型推理过程中出错: {e}")
                            # 不终止整个检测循环，仅记录错误
                    
                    # 动态休眠，根据客户端连接情况调整
                    if self.clients:
                        if self._wait_or_stop(0.01):
                            break
                    else:
                        if self._wait_or_stop(0.05):
                            break
                    
                except Exception as e:
                    logger.error(f"检测过程中出错: {e}")
                    if self._wait_or_stop(0.1):
                        break

        except Exception as e:
            logger.error(f"检测任务异常: {e}")
        finally:
            if self.frame_thread and self.frame_thread.is_alive() and self.frame_thread is not threading.current_thread():
                self.frame_thread.join(timeout=1)
            self._shutdown_detection_loop()

    def _shutdown_detection_loop(self) -> None:
        """在检测线程内安全关闭专属事件循环（绝不触碰预览主循环）"""
        loop = self._detection_loop
        if not loop or loop.is_closed():
            return
        try:
            if loop.is_running():
                return
            loop.run_until_complete(loop.shutdown_asyncgens())
        except RuntimeError as exc:
            logger.debug("检测事件循环关闭跳过: %s", exc)
        except Exception as exc:
            logger.warning("关闭检测事件循环失败: %s", exc)
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            except Exception as exc:
                logger.debug("检测事件循环 close 失败: %s", exc)
            self._detection_loop = None
            if self.loop is loop:
                self.loop = None
            logger.info(f"事件循环已关闭: {self.config_id}")
    
    def _adjust_performance_parameters(self):
        """动态调整性能参数"""
        try:
            import psutil
            
            # 非阻塞采样，避免 stop 时在 cpu_percent(interval=1) 卡住
            cpu_percent = psutil.cpu_percent(interval=None)
            if cpu_percent == 0:
                cpu_percent = psutil.cpu_percent(interval=0.05)
            memory_percent = psutil.virtual_memory().percent
            
            # 根据CPU使用率调整跳帧数
            if cpu_percent > 80:
                # 高CPU负载，增加跳帧数
                new_skip_frames = min(self.skip_frame_count + 2, 10)
                if new_skip_frames != self.skip_frame_count:
                    logger.info(f"CPU负载高({cpu_percent:.1f}%)，调整跳帧数: {self.skip_frame_count} -> {new_skip_frames}")
                    self.skip_frame_count = new_skip_frames
            elif cpu_percent < 50 and self.skip_frame_count > 3:
                # 低CPU负载，减少跳帧数
                new_skip_frames = max(self.skip_frame_count - 1, 4)
                if new_skip_frames != self.skip_frame_count:
                    logger.info(f"CPU负载低({cpu_percent:.1f}%)，调整跳帧数: {self.skip_frame_count} -> {new_skip_frames}")
                    self.skip_frame_count = new_skip_frames
                    
        except ImportError:
            # psutil不可用，使用默认参数
            pass
        except Exception as e:
            logger.warning(f"性能参数调整失败: {e}")

    def process_detection_results(self, results):
        """处理检测结果"""
        return process_yolo_results(
            results,
            self.target_class,
            include_segmentation=is_segmentation_type(self.models_type),
        )
    # 显示检测结果
    def display_detection_results(self, img, results,show_boxes=True): # 显示检测结果
        if not hasattr(results, 'boxes') or results.boxes is None:
            return img
        
        if not show_boxes:
            return img

        boxes = results.boxes
        for box in boxes:
            xy = box_xyxy_array(box)
            x1, y1, x2, y2 = xy
            conf = box_confidence(box)
            cls = box_class_id(box)
            
            if str(cls) not in self.target_class:
                continue

            color = self.get_class_color(cls)
            
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            class_name = self.class_names[cls] if self.class_names else f"Class {cls}"
            label = f"{class_name}: {conf:.2f}"
            cv2.putText(img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        return img

    def display_detections_list(self, img, detections, show_boxes=True):
        """按过滤后的检测列表绘制目标框"""
        if not show_boxes or not detections:
            return img
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cls = det.get("class_id", 0)
            conf = det.get("confidence", 0.0)
            color = self.get_class_color(cls)
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            class_name = det.get("class_name") or (
                self.class_names[cls] if self.class_names else f"Class {cls}"
            )
            label = f"{class_name}: {conf:.2f}"
            cv2.putText(
                img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )
        return img

    def display_pose_results(self, img, results): # 显示姿态结果
        if not hasattr(results, 'keypoints') or results.keypoints is None:
            print("No keypoints found in pose results")
            return img

        keypoints = results.keypoints
        boxes = results.boxes

        # 定义不同身体部位的颜色
        colors = {
            'head': (255, 0, 0),    # 蓝色
            'body': (0, 255, 0),    # 绿色
            'arms': (255, 165, 0),  # 橙色
            'legs': (255, 0, 255)   # 紫色
        }

        for person_keypoints, box in zip(keypoints, boxes):
            kpts = person_keypoints.data[0]
            for kpt in kpts:
                x, y, conf = kpt
                if conf > 0.5:
                    cv2.circle(img, (int(x), int(y)), 5, (0, 255, 0), -1)

            connections = [
                ((0, 1), 'head'), ((0, 2), 'head'), ((1, 3), 'head'), ((2, 4), 'head'),
                ((0, 5), 'body'), ((0, 6), 'body'),
                ((5, 6), 'body'), ((5, 11), 'body'), ((6, 12), 'body'), ((11, 12), 'body'),
                ((5, 7), 'arms'), ((7, 9), 'arms'), ((6, 8), 'arms'), ((8, 10), 'arms'),
                ((11, 13), 'legs'), ((13, 15), 'legs'), ((12, 14), 'legs'), ((14, 16), 'legs')
            ]
            for (connection, body_part) in connections:
                pt1, pt2 = kpts[connection[0]], kpts[connection[1]]
                if pt1[2] > 0.5 and pt2[2] > 0.5:
                    cv2.line(img, (int(pt1[0]), int(pt1[1])), (int(pt2[0]), int(pt2[1])), colors[body_part], 2)

            x1, y1, x2, y2 = box.xyxy[0]
            conf = box.conf[0]
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            label = f"Person: {conf:.2f}"
            cv2.putText(img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return img

    def get_class_color(self, class_id): # 获取类别颜色
        if class_id not in self.class_colors:
            if not self.class_colors:
                colors = self.generate_colors(len(self.class_names))
                self.class_colors = {i: color for i, color in enumerate(colors)}
            else:
                self.class_colors[class_id] = tuple(np.random.randint(0, 255, 3).tolist())
        return self.class_colors[class_id]

    def generate_colors(self, num_classes): # 生成颜色
        hsv_tuples = [(x / num_classes, 1., 1.) for x in range(num_classes)]
        colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        colors = list(map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)), colors))
        return colors

    # 启动/停止检测任务线程
    def start(self): # 启动检测任务线程
        """启动检测任务线程"""
        if self.thread and self.thread.is_alive():
            logger.info(f"检测任务已在运行: {self.config_id}")
            return
        
        self.stop_event.clear()
        self.frame_thread = None
        self.clients.clear()
        self.broadcast_task = None
        self.message_queue = None
        self._preview_loop = None
        self.thread = threading.Thread(
            target=self.run_detection,
            name=f"detect-{self.config_id}",
        )
        self.thread.daemon = True
        self.thread.start()
    
    async def stop(self): # 停止检测任务
        """停止检测任务"""
        logger.info(f"正在停止检测任务: {self.config_id}")
        self.stop_event.set()
        self.clients.clear()
        # 不在此线程 release 摄像机（OpenCV/FFmpeg 跨线程 release 会导致进程崩溃）

        # 停止预览广播（运行在 FastAPI 主循环，不可在检测线程里 await）
        await self._stop_broadcast_worker()

        # 在线程池中 join，拉流线程 finally 中会 release 摄像机
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._join_worker_threads)

    def _join_worker_threads(self) -> None:
        """等待拉流/检测线程结束（同步，供 asyncio.to_thread 调用）"""
        if self.frame_thread and self.frame_thread.is_alive():
            self.frame_thread.join(timeout=4)
            if self.frame_thread.is_alive():
                logger.warning(f"拉流线程未能及时停止: {self.config_id}")

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=8)
            if self.thread.is_alive():
                logger.warning(f"检测线程未能及时停止: {self.config_id}")

    async def _stop_broadcast_worker(self) -> None:
        """取消预览广播协程并清空队列"""
        task = self.broadcast_task
        self.broadcast_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"广播任务已取消: {self.config_id}")
            except Exception as exc:
                logger.debug("取消广播任务: %s", exc)

        if self.message_queue is not None:
            try:
                while not self.message_queue.empty():
                    self.message_queue.get_nowait()
                    self.message_queue.task_done()
            except Exception:
                pass
            try:
                await self.message_queue.put(None)
            except Exception as exc:
                logger.debug("发送广播停止信号失败: %s", exc)
        self.message_queue = None
        self._preview_loop = None
    
    # 保存检测事件到数据库并存储图像/视频
    def _process_detection_events(self, img_result, detections, speed, cooldown_period):
        """生成普通检测事件（不参与规则）"""
        if not detections:
            return
        now = time.time()
        if now - self.last_yolo_event_time < float(cooldown_period or 0):
            return
        try:
            self.save_detection_event(img_result, detections)
            self.push_detection_data_legacy(detections, img_result, speed)
            self.last_yolo_event_time = now
            self.last_detection_time = now
        except Exception as exc:
            logger.error("保存检测事件失败: %s", exc)
            
    def save_detection_event(self, frame, detections): # 保存检测事件到数据库并存储图像/视频
        """保存检测事件到数据库并存储图像/视频"""
        try:
            # 保存事件到数据库
            db = SessionLocal()
            event_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            # 获取检测配置信息
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == self.config_id).first()
            
            if not config:
                logger.error(f"未找到检测配置: {self.config_id}")
                db.close()
                return        

            # 创建检测事件记录
            event = DetectionEvent(
                event_id=event_id,
                config_id=self.config_id,
                device_id=self.device_id,
                timestamp=current_time,
                event_type=self.models_type,
                confidence=max([d["confidence"] for d in detections]) if detections else 0.0,
                bounding_box=detections,
                status=EventStatus.new,
                created_at=current_time
            )

            event.meta_data = build_detection_meta(self.models_type, detections, self.target_class)
            
            if self.save_mode in [SaveMode.screenshot, SaveMode.both]:
                # 根据保存模式保存图像/视频
                save_dir = Path(f"storage/events/{current_time.strftime('%Y-%m-%d')}/{self.device_id}")
                save_dir.mkdir(parents=True, exist_ok=True, mode=0o777)   
                # 保存带检测框的截图（原图）
                thumbnail_path = save_dir / f"{event_id}.jpg"
                if self.stream_type == 'sub':
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                else:
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                event.thumbnail_path = str(thumbnail_path)
            
            # 提交事件
            db.add(event)
            db.commit()
            logger.info(f"已保存检测事件: {event_id}")

        except Exception as e:
            logger.error(f"保存检测事件失败: {e}")
            if 'db' in locals() and db:
                db.rollback()
        finally:
            if 'db' in locals() and db:
                db.close()  
    
    def push_detection_data_legacy(self, detections, frame_rgb, speed): # 推送检测数据
        """推送检测数据"""
        if not data_pusher.push_configs:
            return
        
        if self.area_coordinates and self.area_coordinates.get('pushLabel'):
            push_label = self.area_coordinates.get('pushLabel')
        
            push_data = {
                "cameraInfo": self.device_name + ":" + self.device_ip,
                "deviceId": self.device_id,
                "enteredCount":0,
                "exitedCount":0,
                "stayingCount": len(detections),
                "passedCount":0,
                "recordTime": datetime.now().isoformat() + '+08:00',
                "event_description": "目标检测",
                "target_class": self.target_class
            }
            # 增加标签，使推送更灵活
            data_pusher.push_data(
                data=push_data, 
                image=frame_rgb, 
                tags=[push_label, f"device_{self.device_id}"],
                config_id=self.config_id  # 为了兼容性保留
            )
            
            # 记录性能统计信息
            db = SessionLocal()
            try:
                perf = DetectionPerformance(
                    device_id=self.device_id,
                    config_id=self.config_id,
                    detection_time=speed['inference'],
                    preprocessing_time=speed['preprocess'],
                    postprocessing_time=speed['postprocess'],
                    frame_width=frame_rgb.shape[1],
                    frame_height=frame_rgb.shape[0],
                    objects_detected=len(detections)
                )
                db.add(perf)
                db.commit()
            except Exception as e:
                logger.error(f"保存性能数据失败: {e}")
                db.rollback()
            finally:
                db.close()

    def _has_smart_analysis(self) -> bool:
        if not self.area_coordinates:
            return False
        if is_multi_scenario_config(self.area_coordinates):
            normalized = normalize_smart_config(self.area_coordinates)
            return bool(normalized.get("scenarios"))
        return bool(self.area_coordinates.get("analysisType"))

    def _process_smart_analysis_events(self, img_result, detections, speed, cooldown_period):
        """生成智能分析事件（不参与规则）"""
        try:
            for _event_key, event_info in list(self.object_tracker.triggered_events.items()):
                scenario_type = event_info.get("scenario_type")
                analysis = event_info.get("analysisType") or event_info.get("analysis_type")
                counting = event_info.get("counting_type") or event_info.get("countingType")
                evt = event_info.get("event_type") or ""

                if scenario_type in ("leave_post", "crowd_gather", "loitering"):
                    self._create_scenario_alert_event(event_info, img_result, detections)
                    self._push_scenario_alert_event(event_info, img_result, detections, speed)
                elif evt in (
                    "occupancy_alert",
                    "occupancy_change_increase",
                    "occupancy_change_decrease",
                    "occupancy_report",
                ) or counting in ("occupancy", "flow") or evt.startswith("occupancy_"):
                    # 定期上报：有推送标签才推送，不入库（事件列表仅保留增减/超限）
                    if evt == "occupancy_report" or event_info.get("_periodic_only"):
                        push_label = event_info.get("pushLabel")
                        if not push_label and self.area_coordinates:
                            push_label = self.area_coordinates.get("pushLabel")
                        if push_label:
                            self.push_counting_event_legacy(event_info, img_result, detections, speed)
                    else:
                        self._create_counting_event(event_info, img_result, detections)
                        self.push_counting_event_legacy(event_info, img_result, detections, speed)
                        if evt == "occupancy_alert":
                            self._check_alert(event_info.get("current_count", 0))
                elif analysis == "behavior" or scenario_type == "behavior" or evt.startswith(
                    ("line_cross", "area_")
                ):
                    self._create_behavior_event(event_info, img_result, detections)
                    self.push_behavior_event_legacy(event_info, img_result, detections, speed)
                else:
                    self._create_behavior_event(event_info, img_result, detections)
                    self.push_behavior_event_legacy(event_info, img_result, detections, speed)
            self.object_tracker.triggered_events.clear()
        except Exception as exc:
            logger.error("保存智能分析事件失败: %s", exc)

    def _create_scenario_alert_event(self, event_info, frame, detections):
        """创建离岗/聚众等场景告警事件"""
        try:
            db = SessionLocal()
            event_id = str(uuid.uuid4())
            current_time = datetime.now()

            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == self.config_id).first()
            if not config:
                logger.error(f"未找到检测配置: {self.config_id}")
                db.close()
                return

            event = DetectionEvent(
                event_id=event_id,
                config_id=self.config_id,
                device_id=self.device_id,
                timestamp=current_time,
                event_type='smart_person',
                confidence=max([d["confidence"] for d in detections]) if detections else 0.0,
                bounding_box=detections,
                status=EventStatus.new,
                created_at=current_time
            )

            event.meta_data = {
                "scenario_id": event_info.get('scenario_id'),
                "scenario_name": event_info.get('scenario_name'),
                "scenario_type": event_info.get('scenario_type'),
                "event_type": event_info.get('event_type'),
                "event_description": self._get_event_description(event_info.get('event_type')),
                "current_count": event_info.get('current_count'),
                "min_persons": event_info.get('min_persons'),
                "duration_sec": event_info.get('duration_sec'),
                "target_class": self.target_class,
            }

            save_dir = Path(f"storage/events/{current_time.strftime('%Y-%m-%d')}/{self.device_id}")
            save_dir.mkdir(parents=True, exist_ok=True, mode=0o777)

            if self.save_mode in [SaveMode.screenshot, SaveMode.both]:
                thumbnail_path = save_dir / f"{event_id}.jpg"
                quality = 100 if self.stream_type == 'sub' else 70
                cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                event.thumbnail_path = str(thumbnail_path)

            db.add(event)
            db.commit()
            logger.info(f"已保存场景告警事件: {event_id} ({event_info.get('scenario_name')})")
        except Exception as e:
            logger.error(f"保存场景告警事件失败: {e}")
            if 'db' in locals() and db:
                db.rollback()
        finally:
            if 'db' in locals() and db:
                db.close()

    def _push_scenario_alert_event(self, event_info, frame, detections, speed):
        if not data_pusher.push_configs:
            return

        push_label = event_info.get('pushLabel')
        if not push_label and self.area_coordinates:
            push_label = self.area_coordinates.get('pushLabel')
        if not push_label:
            return

        push_data = {
            "cameraInfo": self.device_name + ":" + self.device_ip,
            "deviceId": self.device_id,
            "scenarioId": event_info.get('scenario_id'),
            "scenarioName": event_info.get('scenario_name'),
            "scenarioType": event_info.get('scenario_type'),
            "eventType": event_info.get('event_type'),
            "currentCount": event_info.get('current_count', 0),
            "minPersons": event_info.get('min_persons'),
            "durationSec": event_info.get('duration_sec'),
            "recordTime": datetime.now().isoformat() + '+08:00',
        }
        data_pusher.push_data(
            data=push_data,
            image=frame,
            tags=[push_label, f"device_{self.device_id}", f"scenario_{event_info.get('scenario_id')}"],
            config_id=self.config_id
        )
    
    def _create_behavior_event(self, event_info, frame, detections): # 创建行为事件记录
        """创建行为事件记录"""
        try:
            # 保存事件到数据库
            db = SessionLocal()
            event_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            # 获取检测配置信息
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == self.config_id).first()
            
            if not config:
                logger.error(f"未找到检测配置: {self.config_id}")
                db.close()
                return           

            # 创建检测事件记录
            event = DetectionEvent(
                event_id=event_id,
                config_id=self.config_id,
                device_id=self.device_id,
                timestamp=current_time,
                event_type='smart_behavior',# 智能行为事件
                confidence=max([d["confidence"] for d in detections]) if detections else 0.0,
                bounding_box=detections,
                status=EventStatus.new,
                created_at=current_time
            )

            # 保存事件元数据
            event.meta_data = {
                "analysis_type": event_info.get('analysisType') or self.area_coordinates.get('analysisType'),
                "behavior_type": event_info.get('behavior_type') or self.area_coordinates.get('behaviorType'),
                "behavior_subtype": event_info.get('behavior_subtype') or self.area_coordinates.get('behaviorSubtype'),
                "scenario_id": event_info.get('scenario_id'),
                "scenario_name": event_info.get('scenario_name'),
                "event_type": event_info['event_type'],
                "event_description": self._get_event_description(event_info['event_type']),
                "target_class": self.target_class           
            }
            
            # 根据保存模式保存图像/视频
            save_dir = Path(f"storage/events/{current_time.strftime('%Y-%m-%d')}/{self.device_id}")
            save_dir.mkdir(parents=True, exist_ok=True, mode=0o777)
            
            if self.save_mode in [SaveMode.screenshot, SaveMode.both]:   
                # 保存带检测框的截图（原图）
                thumbnail_path = save_dir / f"{event_id}.jpg"
                if self.stream_type == 'sub':
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                else:
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                event.thumbnail_path = str(thumbnail_path)
          
            # 提交事件
            db.add(event)
            db.commit()
            logger.info(f"已保存智能行为事件: {event_id}")
            
        except Exception as e:
            logger.error(f"保存智能行为事件失败: {e}")
            if 'db' in locals() and db:
                db.rollback()
        finally:
            if 'db' in locals() and db:
                db.close()
        
    def _create_counting_event(self, event_info, frame, detections): # 创建人数统计事件记录
        """创建人数统计事件记录"""
        try:
            # 保存事件到数据库
            db = SessionLocal()
            event_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            # 获取检测配置信息
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == self.config_id).first()
            
            if not config:
                logger.error(f"未找到检测配置: {self.config_id}")
                db.close()
                return
            
            # 创建检测事件记录
            event = DetectionEvent(
                event_id=event_id,
                config_id=self.config_id,
                device_id=self.device_id,
                timestamp=current_time,
                event_type='smart_counting',# 智能人数统计事件
                confidence=max([d["confidence"] for d in detections]) if detections else 0.0,
                bounding_box=detections,
                status=EventStatus.new,
                created_at=current_time
            )

            # 保存事件元数据
            event.meta_data = {
                "analysis_type": event_info.get('analysisType') or self.area_coordinates.get('analysisType'),
                "counting_type": event_info.get('counting_type') or self.area_coordinates.get('countingType'),
                "counting_subtype": 'area_counting' if (event_info.get('counting_type') or self.area_coordinates.get('countingType')) == 'occupancy' else 'flow_counting',
                "scenario_id": event_info.get('scenario_id'),
                "scenario_name": event_info.get('scenario_name'),
                "scenario_type": event_info.get('scenario_type') or 'counting',
                "event_type": event_info['event_type'],
                "event_description": self._get_event_description(event_info['event_type']),
                "target_class": self.target_class,
                "current_count": event_info.get('current_count'),
                "previous_count": event_info.get('previous_count'),
                "change_amount": event_info.get('change_amount'),
                "area_counts": event_info.get('area_counts'),
                "today_in_count": event_info.get('today_in_count'),
                "today_out_count": event_info.get('today_out_count')
            }
            
            # 根据保存模式保存图像/视频
            save_dir = Path(f"storage/events/{current_time.strftime('%Y-%m-%d')}/{self.device_id}")
            save_dir.mkdir(parents=True, exist_ok=True, mode=0o777)
            
            if self.save_mode in [SaveMode.screenshot, SaveMode.both]:   
                # 保存带检测框的截图（原图）
                thumbnail_path = save_dir / f"{event_id}.jpg"
                if self.stream_type == 'sub':
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                else:
                    cv2.imwrite(str(thumbnail_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                event.thumbnail_path = str(thumbnail_path)
          
            # 提交事件
            db.add(event)
            db.commit()
            logger.info(f"已保存智能人数统计事件: {event_id}")
            
        except Exception as e:
            logger.error(f"保存智能人数统计事件失败: {e}")
            if 'db' in locals() and db:
                db.rollback()
        finally:
            if 'db' in locals() and db:
                db.close()

    def push_behavior_event_legacy(self, event_info, frame, detections, speed): # 推送行为事件
        """推送行为事件"""
        if not data_pusher.push_configs:
            return
        
        push_label = event_info.get('pushLabel')
        if not push_label and self.area_coordinates:
            push_label = self.area_coordinates.get('pushLabel')
        if not push_label:
            return

        push_data = {
            "cameraInfo": self.device_name + ":" + self.device_ip,
            "deviceId": self.device_id,
            "enteredCount": 0,
            "exitedCount": 0,
            "stayingCount": event_info.get('current_count', 0),
            "passedCount": 0,
            "recordTime": datetime.now().isoformat() + '+08:00',
        }
        data_pusher.push_data(
            data=push_data,
            image=frame,
            tags=[push_label, f"device_{self.device_id}"],
            config_id=self.config_id
        )

    def push_counting_event_legacy(self, event_info, frame, detections, speed): # 推送人数统计事件
        """推送人数统计事件"""
        if not data_pusher.push_configs:
            return

        push_label = event_info.get('pushLabel')
        if not push_label and self.area_coordinates:
            push_label = self.area_coordinates.get('pushLabel')
        if not push_label:
            return

        record_time = datetime.now().isoformat() + '+08:00'

        area_counts = event_info.get('area_counts')

        if not area_counts or len(area_counts) <= 1:
            push_data = {
                "cameraInfo": self.device_name + ":" + self.device_ip,
                "deviceId": self.device_id,
                "enteredCount": event_info.get('today_in_count', 0),
                "exitedCount": event_info.get('today_out_count', 0),
                "stayingCount": event_info.get('current_count', 0),
                "areaCounts": event_info.get('area_counts', {}),
                "passedCount": 0,
                "recordTime": record_time,
            }
            data_pusher.push_data(
                data=push_data,
                image=frame,
                tags=[push_label, f"device_{self.device_id}"],
                config_id=self.config_id
            )
            return

        push_data_list = []

        for area_key, area_info in area_counts.items():
            push_data = {
                "cameraInfo": self.device_name + ":" + self.device_ip,
                "deviceId": area_info.get("name"),          # ✅ 使用区域 name
                "enteredCount": event_info.get('today_in_count', 0),
                "exitedCount": event_info.get('today_out_count', 0),
                "stayingCount": area_info.get("count", 0),  # ✅ 使用区域 count
                "passedCount": 0,
                "recordTime": record_time,
            }
            push_data_list.append(push_data)

        # 逐条推送
        for push_data in push_data_list:
            data_pusher.push_data(
                data=push_data,
                image=frame,
                tags=[push_label, f"device_{self.device_id}"],
                config_id=self.config_id
            )

    def _check_alert(self, current_count):
        """检查人数是否超过预警阈值"""

        if self.area_coordinates.get('enableAlert') == False or self.area_coordinates.get('alertThreshold') == None:
            return
        
        if not data_pusher.push_configs:
            return

        if current_count >= self.area_coordinates.get('alertThreshold'):
            # 生成预警消息
            warning_msg = f"人群密度预警：{self.device_id} 区域人数达到 {current_count}人，超过预警阈值({self.area_coordinates.get('alertThreshold')}人)"
            
            # 发送预警（可以通过数据推送模块发送到外部系统）
            if self.area_coordinates.get('pushLabel'):
                push_label = self.area_coordinates.get('pushLabel')
                data_pusher.push_data(
                    data={
                        "analysis_type": 'counting',
                        "counting_type": 'occupancy',
                        "config_id": self.config_id,
                        "device_id": self.device_id,
                        "alert_threshold": self.area_coordinates.get('alertThreshold'),
                        "current_count": current_count,
                        "message": warning_msg,
                        "timestamp": datetime.now().isoformat()
                    },
                    tags=[push_label, f"device_{self.device_id}"],
                )
            
            logger.warning(f"人群密度预警: {warning_msg}")

    def _get_event_description(self, event_type): # 获取事件描述
        """获取事件描述"""
        descriptions = {
            'area_enter': '进入检测区域',
            'area_exit': '离开检测区域',
            'line_cross': '穿越检测线',
            'line_cross_in': '穿越检测线（进入方向）',
            'line_cross_out': '穿越检测线（离开方向）',
            'enter_area': '进入统计区域',
            'exit_area': '离开统计区域',
            'occupancy_change_increase': '区域内人数增加',
            'occupancy_change_decrease': '区域内人数减少',
            'occupancy_report': '区域人数定期上报',
            'leave_post_alert': '离岗告警',
            'crowd_gather_alert': '聚众告警',
            'loitering_alert': '徘徊告警',
            'occupancy_alert': '区域人数超限告警',
            'occupancy_stats': '区域人数统计',
        }
        return descriptions.get(event_type, '未知事件')

    # 向所有WebSocket客户端广播检测结果
    def broadcast_img_result(self, pose_frame, detections): # 向所有WebSocket客户端广播检测结果
        """向所有WebSocket客户端广播检测结果"""
        if not self.clients:
            return  # 没有客户端连接，跳过
        
        try:            
            
            # 将帧转换为JPEG，增加质量参数
            if self.stream_type == 'sub':
                _, buffer = cv2.imencode('.jpg', pose_frame, [cv2.IMWRITE_JPEG_QUALITY, 100])  # 提高JPEG质量
            else:
                _, buffer = cv2.imencode('.jpg', pose_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])  # 提高JPEG质量
            jpg_bytes = buffer.tobytes()
            base64_image = base64.b64encode(jpg_bytes).decode('utf-8')
            
            # 创建消息
            message = {
                "device_id": self.device_id,
                "config_id": self.config_id,
                "timestamp": time.time(),
                "image": base64_image,
                "detections": detections
            }
            
            # 将消息放入队列（线程安全，仅通过预览主循环）
            preview_loop = self._preview_loop
            if preview_loop and preview_loop.is_running() and self.message_queue is not None:
                preview_loop.call_soon_threadsafe(
                    lambda msg=message: self.message_queue.put_nowait(msg)
                )
       
        except Exception as e:
            logger.error(f"广播检测结果失败: {e}")

    def normalize_points(self, points, frame_shape): #归一化坐标转换
        """归一化坐标转换"""
        h,w = frame_shape[:2]
        return [(int(p['x']*w), int(p['y']*h)) for p in points]

    def draw_roi(self, frame, line_color=(0,255,0), fill_color=(0,0,0,0), thickness=2, line_type=cv2.LINE_AA): # 绘制线段/区域 ROI（支持line/area类型）
        """
        绘制线段/区域 ROI（支持line/area类型）
        """
        if not self.area_coordinates:
            return

        if is_multi_scenario_config(self.area_coordinates):
            self._draw_multi_scenario_roi(frame, thickness, line_type)
            return

        roi_type = None
        roi_points = None
        # 获取区域配置
        if self.area_coordinates.get('analysisType'):
            roi_type = self.area_coordinates['behaviorType'] if self.area_coordinates['analysisType'] == 'behavior' else self.area_coordinates['countingType']
            roi_points = self.area_coordinates['points']
        else:
            return

        if roi_type not in ['line', 'area', 'occupancy', 'flow']:
            raise ValueError("Invalid ROI type. Must be 'line' or 'area' or 'occupancy' or 'flow'")

        if roi_type == 'occupancy' and self.area_coordinates.get('occupancyAreas'):
            for area in self.area_coordinates['occupancyAreas']:
                area_points = area.get('points') or []
                if len(area_points) < 3:
                    continue
                line = self.normalize_points(area_points, frame.shape)
                roi_array = np.array(line, np.int32)
                cv2.polylines(frame, [roi_array], True, line_color, thickness, line_type)
                if fill_color[3] != 0:
                    cv2.fillPoly(frame, [roi_array], fill_color[:3])
            return
        
        line = self.normalize_points(roi_points, frame.shape)

        # 转换为整数坐标
        roi_array = np.array(line, np.int32)
        
        if roi_type == 'line' or roi_type == 'flow':
            # 线段绘制（至少需要2个点）
            if len(roi_array) < 2:
                return
            # 绘制线段轮廓
            cv2.polylines(frame, [roi_array], False, line_color, thickness, line_type)
            # 绘制中间点标记（可选）
            for pt in roi_array:
                cv2.circle(frame, tuple(pt), 3, line_color, -1)
                
        elif roi_type == 'area' or roi_type == 'occupancy':
            # 区域绘制
            if len(roi_array) < 3:
                # 最小包围矩形
                x_coords = [p[0] for p in roi_array]
                y_coords = [p[1] for p in roi_array]
                x1, x2 = int(min(x_coords)), int(max(x_coords))
                y1, y2 = int(min(y_coords)), int(max(y_coords))
                cv2.rectangle(frame, (x1, y1), (x2, y2), line_color, thickness)
            else:
                # 多边形绘制
                cv2.polylines(frame, [roi_array], True, line_color, thickness, line_type)
                # 区域填充（支持透明度）
                if fill_color[3]!= 0:
                    cv2.fillPoly(frame, [roi_array], fill_color[:3])  # 填充颜色（BGR）
                    # 绘制半透明覆盖层
                    overlay = frame.copy()
                    cv2.fillPoly(overlay, [roi_array], fill_color)
                    frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)

    def _draw_multi_scenario_roi(self, frame, thickness=2, line_type=cv2.LINE_AA):
        normalized = normalize_smart_config(self.area_coordinates)
        palette = [
            (0, 255, 0), (255, 170, 0), (0, 170, 255), (255, 68, 170), (170, 68, 255)
        ]
        for index, scenario in enumerate(normalized.get('scenarios') or []):
            if scenario.get('enabled') is False:
                continue
            color = palette[index % len(palette)]
            scenario_type = scenario.get('type')
            if scenario_type == 'counting' and _resolve_counting_type(scenario) == 'occupancy':
                for area in scenario.get('occupancyAreas') or []:
                    area_points = area.get('points') or []
                    if len(area_points) < 3:
                        continue
                    line = self.normalize_points(area_points, frame.shape)
                    roi_array = np.array(line, np.int32)
                    cv2.polylines(frame, [roi_array], True, color, thickness, line_type)
                continue

            points = scenario.get('points') or []
            if len(points) < 2:
                continue
            line = self.normalize_points(points, frame.shape)
            roi_array = np.array(line, np.int32)
            is_line = (
                (scenario_type == 'behavior' and scenario.get('behaviorType') == 'line')
                or (scenario_type == 'counting' and _resolve_counting_type(scenario) == 'flow')
            )
            if is_line:
                cv2.polylines(frame, [roi_array], False, color, thickness, line_type)
                for pt in roi_array:
                    cv2.circle(frame, tuple(pt), 3, color, -1)
            elif len(roi_array) >= 3:
                cv2.polylines(frame, [roi_array], True, color, thickness, line_type)
            else:
                cv2.polylines(frame, [roi_array], False, color, thickness, line_type)

    async def broadcast_worker(self): # 处理消息广播的工作协程
        """处理消息广播的工作协程"""
        logger.info(f"广播工作协程已启动: {self.config_id}")
        try:
            while not self.stop_event.is_set():
                try:
                    # 设置超时，避免永久阻塞
                    message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                    
                    if message is None:  # 停止信号
                        break
                    
                    # 调试日志
                    logger.debug(f"准备向 {len(self.clients)} 个客户端广播消息")
                    
                    # 获取当前活跃的客户端列表
                    clients = list(self.clients)
                    for client in clients:
                        try:
                            await client.send_json(message)
                            # 可选：添加成功发送日志
                            # logger.debug(f"成功向客户端 {id(client)} 发送消息")
                        except Exception as e:
                            logger.error(f"向客户端 {id(client)} 发送消息失败: {e}")
                            # 移除断开连接的客户端
                            if client in self.clients:
                                self.clients.remove(client)
                                logger.info(f"客户端已断开连接，检测任务 {self.config_id}, 当前客户端数: {len(self.clients)}")
                    
                    self.message_queue.task_done()
                except asyncio.TimeoutError:
                    # 超时但不影响循环继续
                    continue
                except Exception as e:
                    logger.error(f"广播工作协程错误: {e}")
                    # await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info(f"广播任务被取消: {self.config_id}")
        finally:
            logger.info(f"广播工作协程已停止: {self.config_id}")
    
    def add_client(self, websocket): # 添加WebSocket客户端到广播列表
        """添加WebSocket客户端到广播列表"""
        self.clients.add(websocket)
        logger.info(f"客户端已连接到检测任务 {self.config_id}, 当前客户端数: {len(self.clients)}")

        try:
            preview_loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error(f"预览连接不在异步上下文中，无法启动广播: {self.config_id}")
            return

        self._preview_loop = preview_loop
        if self.message_queue is None:
            self.message_queue = asyncio.Queue()

        if not self.broadcast_task or self.broadcast_task.done():
            try:
                self.broadcast_task = preview_loop.create_task(self.broadcast_worker())
                logger.info(f"为检测任务 {self.config_id} 创建了新的广播任务")
            except Exception as e:
                logger.error(f"创建广播任务失败: {e}")
    
    def remove_client(self, websocket): # 从广播列表中移除WebSocket客户端
        """从广播列表中移除WebSocket客户端"""
        if websocket in self.clients:
            self.clients.remove(websocket)
            logger.info(f"客户端已断开连接，检测任务 {self.config_id}, 当前客户端数: {len(self.clients)}")

            # 无客户端时标记广播任务结束（实际 cancel 由 stop 或任务自然退出）
            if not self.clients and self.broadcast_task and not self.broadcast_task.done():
                self.broadcast_task.cancel()
                self.broadcast_task = None