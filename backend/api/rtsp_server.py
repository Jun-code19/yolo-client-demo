"""
RTSP流处理模块 - 用于处理RTSP流，包括启动、停止、捕获帧等
"""
from fastapi import APIRouter, WebSocket,WebSocketDisconnect # 导入FastAPI相关模块
from typing import Dict, Tuple # 导入字典类型和元组类型
import cv2 # 导入OpenCV模块
from src.frame_acquisition import open_rtsp_capture, probe_rtsp_host
import base64 # 导入base64编码
import time # 导入时间模块
import threading # 导入线程模块
import asyncio # 导入异步I/O模块
from concurrent.futures import ThreadPoolExecutor # 导入线程池
import logging # 导入日志模块
import numpy as np # 导入NumPy模块
from collections import deque # 导入双端队列
from src.inference_backend import cuda_available
from src.yolo_task_utils import load_detection_model, predict_detection_frame, process_yolo_results
from pathlib import Path # 导入路径模块
import os # 导入操作系统模块
import re # 导入正则表达式模块
from urllib.parse import urlparse # 导入URL解析模块

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建API路由
router = APIRouter(prefix="/rtsp", tags=["RTSP流处理"])

# 全局变量
models_cache = {} # 模型缓存
frame_queues = {} # 帧队列
max_queue_size = 1  # 减小队列大小以降低延迟
executor = ThreadPoolExecutor(max_workers=2)  # 减少线程数以避免资源竞争
previous_boxes = {} # 前一帧的检测框
box_smooth_factor = 0.2  # 减小平滑因子以降低延迟
max_latency = 1000  # 增加最大延迟阈值(ms)，避免跳过太多帧
max_size = 320  # 减小处理尺寸以提高性能

# 添加 WebSocket 连接管理
active_connections: Dict[str, WebSocket] = {}
rtsp_sessions: Dict[str, dict] = {}

class RTSPManager:
    """管理RTSP流的类"""
    
    def __init__(self):
        self.active_streams = {}
        self.stop_events = {}
        self.frame_buffers = {}
        self.frame_ready_events = {}
        self.thread_executors = ThreadPoolExecutor(max_workers=4)  # 专用于RTSP的线程池
        self.stream_status = {}  # 用于线程和异步任务间通信
        self.stream_urls = {}  # 存储连接ID对应的流URL
    
    async def start_stream(self, connection_id: str, stream_url: str) -> bool:
        """启动RTSP流处理"""
        if connection_id in self.active_streams:
            return False
        
        # 设置停止事件和帧缓冲
        stop_event = threading.Event()
        self.stop_events[connection_id] = stop_event
        self.frame_buffers[connection_id] = deque(maxlen=5)  # 存储最多5帧
        self.stream_status[connection_id] = {"status": "connecting", "info": None, "error": None}
        self.stream_urls[connection_id] = stream_url  # 存储流URL
        
        # 在单独的线程中运行RTSP捕获
        self.thread_executors.submit(
            self._capture_rtsp_frames,
            connection_id,
            stream_url,
            stop_event
        )
        
        # 创建异步任务处理流
        task = asyncio.create_task(
            self._process_frames_async(connection_id)
        )
        self.active_streams[connection_id] = task
        
        return True
    
    async def stop_stream(self, connection_id: str) -> bool:
        """停止RTSP流处理"""
        if connection_id not in self.active_streams:
            return False
        
        # 设置停止事件
        if connection_id in self.stop_events:
            self.stop_events[connection_id].set()
        
        # 等待任务结束
        task = self.active_streams[connection_id]
        if not task.done():
            await asyncio.wait([task], timeout=5)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 清理资源
        self.active_streams.pop(connection_id, None)
        self.stop_events.pop(connection_id, None)
        if connection_id in self.frame_buffers:
            self.frame_buffers.pop(connection_id)
        if connection_id in self.stream_status:
            self.stream_status.pop(connection_id)
        if connection_id in self.stream_urls:
            self.stream_urls.pop(connection_id)
        
        return True
    
    def _capture_rtsp_frames(self, connection_id: str, stream_url: str, stop_event):
        """在单独的线程中从RTSP流捕获帧"""
        frame_count = 0
        frame_buffer = self.frame_buffers.get(connection_id)
        skip_frame_count = 0
        
        try:
            # 尝试从RTSP连接视频源
            try:
                reachable, host_port = probe_rtsp_host(stream_url)
                if not reachable:
                    logger.error("RTSP 预览端口不可达: %s", host_port)
                    if connection_id in self.stream_status:
                        self.stream_status[connection_id] = {
                            "status": "error",
                            "error": f"无法连接摄像机 ({host_port})，请检查 IP 是否与本机同网段或路由是否可达",
                        }
                    return False

                cap = open_rtsp_capture(stream_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 设置缓冲区大小为1，减少延迟

                if not cap.isOpened():
                    logger.error("RTSP 预览打开失败: %s", host_port or stream_url[:64])
                    if connection_id in self.stream_status:
                        self.stream_status[connection_id] = {
                            "status": "error",
                            "error": f"无法打开 RTSP 流 ({host_port or 'unknown'})，请检查账号密码与通道号",
                        }
                    return False
                
                fps = cap.get(cv2.CAP_PROP_FPS)
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        
                if connection_id in self.stream_status:
                    self.stream_status[connection_id] = {
                        "status": "connected",
                        "info": {
                            "width": width,
                            "height": height,
                            "fps": float(fps) if fps else 30.0
                        },
                        "error": None
                    }
                
                target_fps = min(30, fps if fps else 30)
                frame_interval = 1.0 / target_fps
                
                last_frame_time = time.time()
                
                # 循环处理视频帧
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    if stop_event.is_set():
                        break
                    
                    current_time = time.time()
                    elapsed = current_time - last_frame_time
                    
                    # 控制帧率，避免缓冲区溢出
                    if elapsed < frame_interval * 0.5:  # 如果时间间隔过短，跳过该帧
                        skip_frame_count += 1
                        if skip_frame_count % 30 == 0:
                            logger.debug(f"跳过帧以控制帧率，已跳过: {skip_frame_count}")
                        continue
                    
                    # 将PyAV帧转换为OpenCV格式
                    # img = frame.to_ndarray(format='bgr24')
                    img = frame
                    # 添加帧信息
                    frame_data = {
                        "frame": img,
                        "frame_id": frame_count,
                        "timestamp": current_time,
                        "width": img.shape[1],
                        "height": img.shape[0]
                    }
                    
                    # 将帧放入共享缓冲区
                    if frame_buffer is not None:
                        if len(frame_buffer) >= frame_buffer.maxlen:
                            frame_buffer.popleft()  # 移除最老的帧，避免延迟累积
                        frame_buffer.append(frame_data)
                    
                    frame_count += 1
                    last_frame_time = current_time
                    
                    # 避免CPU占用过高
                    time.sleep(0.001)
                
                # logger.info(f"RTSP捕获完成，共捕获 {frame_count} 帧，跳过 {skip_frame_count} 帧")
                
            except Exception as e:
                logger.error(f"无法打开RTSP流: {e}")
                # 设置错误状态
                if connection_id in self.stream_status:
                    self.stream_status[connection_id] = {
                        "status": "error", 
                        "error": f"无法连接到RTSP流: {str(e)}"
                    }
                return
                
        except Exception as e:
            # 设置错误状态
            if connection_id in self.stream_status:
                self.stream_status[connection_id] = {
                    "status": "error", 
                    "error": f"视频流处理错误: {str(e)}"
                }
        finally:
            # 关闭容器
            try:
                if 'cap' in locals():
                    cap.release()
            except Exception as e:
                logger.error(f"关闭RTSP容器时发生错误: {e}")
    
    async def _process_frames_async(self, connection_id: str):
        """异步处理并发送捕获的帧"""
        frame_buffer = self.frame_buffers.get(connection_id)
        stop_event = self.stop_events.get(connection_id)
        last_send_time = time.time()
        send_interval = 1.0 / 30.0  # 控制发送帧率，最高30fps
        processed_frames = 0
        
        # 通知参数
        stream_notified = False
        retry_count = 0
        max_retry = 50  # 最多等待5秒
        
        try:
            # 等待RTSP连接成功或失败
            while retry_count < max_retry:
                if connection_id in self.stream_status:
                    status = self.stream_status[connection_id]
                    
                    # 检查是否有错误
                    if status.get("status") == "error":
                        websocket = active_connections.get(connection_id)
                        if websocket:
                            await websocket.send_json({
                                "type": "error",
                                "message": status.get("error", "未知错误")
                            })
                        return
                    
                    # 检查是否已连接
                    if status.get("status") == "connected" and status.get("info"):
                        websocket = active_connections.get(connection_id)
                        if websocket:
                            # 发送流信息
                            await websocket.send_json({
                                "type": "stream_info",
                                "width": status["info"].get("width"),
                                "height": status["info"].get("height"),
                                "fps": status["info"].get("fps")
                            })
                            
                            # 发送预览开始通知
                            await websocket.send_json({
                                "type": "preview_start",
                                "width": status["info"].get("width"),
                                "height": status["info"].get("height")
                            })
                            stream_notified = True
                        break
                
                retry_count += 1
                await asyncio.sleep(0.1)
            
            # 主循环处理帧
            while not stop_event.is_set():
                # 检查是否有新帧
                if frame_buffer and len(frame_buffer) > 0:
                    # 获取最新的帧
                    frame_data = frame_buffer[-1]  # 总是处理最新的帧
                    img = frame_data["frame"]
                    frame_id = frame_data["frame_id"]
                    
                    current_time = time.time()
                    elapsed = current_time - last_send_time
                    
                    # 控制发送频率
                    if elapsed >= send_interval:
                        # 处理图像质量
                        try:
                            # 原始分辨率
                            orig_h, orig_w = img.shape[:2]
                            
                            # 调整尺寸（可选，保持高质量）
                            max_dim = 1920  # 增加到1920以提高质量
                            resized = False
                            processed_img = img
                            
                            if max(orig_h, orig_w) > max_dim:
                                scale = max_dim / max(orig_h, orig_w)
                                new_width = int(orig_w * scale)
                                new_height = int(orig_h * scale)
                                processed_img = cv2.resize(img, (new_width, new_height), 
                                                         interpolation=cv2.INTER_AREA)
                                resized = True
                                
                            # 使用更高的JPEG质量
                            _, buffer = cv2.imencode('.jpg', processed_img, 
                                                   [cv2.IMWRITE_JPEG_QUALITY, 90])
                            jpeg_data = base64.b64encode(buffer).decode('utf-8')
                            
                            # 获取当前帧的宽高
                            current_width = processed_img.shape[1]
                            current_height = processed_img.shape[0]
                                                       
                            # 发送数据到WebSocket
                            websocket = active_connections.get(connection_id)
                            if websocket:
                                # 发送帧数据
                                await websocket.send_json({
                                    "type": "stream_data",
                                    "format": "jpeg",
                                    "data": jpeg_data,
                                    "frame_id": frame_id,
                                    "width": current_width,
                                    "height": current_height,
                                    "original_width": orig_w,
                                    "original_height": orig_h,
                                    "resized": resized
                                })
                                
                                processed_frames += 1
                                last_send_time = current_time
                            else:
                                logger.info(f"WebSocket连接已关闭，停止流处理: {connection_id}")
                                break
                                
                        except Exception as e:
                            logger.error(f"处理帧时发生错误: {e}")
                    
                # 检查WebSocket连接是否仍然活跃
                if connection_id not in active_connections:
                    logger.info(f"WebSocket连接已关闭，停止帧处理: {connection_id}")
                    break
                    
                # 短暂休眠，让出控制权
                await asyncio.sleep(0.01)
                
            logger.info(f"帧处理任务完成，共处理 {processed_frames} 帧")
            
        except asyncio.CancelledError:
            logger.info(f"帧处理任务被取消: {connection_id}")
        except Exception as e:
            logger.error(f"帧处理任务错误: {e}")
            # 通知客户端发生错误
            websocket = active_connections.get(connection_id)
            if websocket:
                await websocket.send_json({
                    "type": "error",
                    "message": f"帧处理错误: {str(e)}"
                })
        finally:
            logger.info(f"帧处理任务已结束: {connection_id}")
# 创建RTSP管理器实例
rtsp_manager = RTSPManager()

class FrameProcessor:
    def __init__(self):
        self.processing_times = deque(maxlen=50)  # 存储最近50次处理时间
        self.last_predictions = {}  # 存储每个目标的上一次预测结果
    
    def get_avg_processing_time(self):
        if not self.processing_times:
            return 0
        return sum(self.processing_times) / len(self.processing_times)
    
    def smooth_boxes(self, current_boxes, frame_id):
        """平滑检测框的位置"""
        if frame_id not in previous_boxes:
            previous_boxes[frame_id] = current_boxes
            return current_boxes
        
        smoothed_boxes = []
        prev_boxes = previous_boxes[frame_id]
        
        # 对每个当前检测框
        for curr_box in current_boxes:
            # 在上一帧中找到最匹配的框
            best_match = None
            min_dist = float('inf')
            
            for prev_box in prev_boxes:
                if prev_box["class"] == curr_box["class"]:
                    # 计算框中心点距离
                    curr_center = (curr_box["bbox"][0] + curr_box["bbox"][2]/2,
                                 curr_box["bbox"][1] + curr_box["bbox"][3]/2)
                    prev_center = (prev_box["bbox"][0] + prev_box["bbox"][2]/2,
                                 prev_box["bbox"][1] + prev_box["bbox"][3]/2)
                    
                    dist = ((curr_center[0] - prev_center[0])**2 +
                           (curr_center[1] - prev_center[1])**2)**0.5
                    
                    if dist < min_dist:
                        min_dist = dist
                        best_match = prev_box
            
            # 如果找到匹配的框，进行平滑处理
            if best_match and min_dist < 100:  # 设置最大匹配距离阈值
                smooth_box = {
                    "class": curr_box["class"],
                    "confidence": curr_box["confidence"],
                    "bbox": [
                        best_match["bbox"][0] * box_smooth_factor + curr_box["bbox"][0] * (1 - box_smooth_factor),
                        best_match["bbox"][1] * box_smooth_factor + curr_box["bbox"][1] * (1 - box_smooth_factor),
                        best_match["bbox"][2] * box_smooth_factor + curr_box["bbox"][2] * (1 - box_smooth_factor),
                        best_match["bbox"][3] * box_smooth_factor + curr_box["bbox"][3] * (1 - box_smooth_factor)
                    ]
                }
                smoothed_boxes.append(smooth_box)
            else:
                smoothed_boxes.append(curr_box)
        
        previous_boxes[frame_id] = smoothed_boxes
        return smoothed_boxes
# 创建帧处理器实例
frame_processor = FrameProcessor()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        connection_id = str(id(websocket))
        self.active_connections[connection_id] = websocket
        return connection_id

    async def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            del self.active_connections[connection_id]
            try:
                await websocket.close()
            except Exception:
                pass

        # 取消并清理相关任务
        if connection_id in self.connection_tasks:
            task = self.connection_tasks[connection_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.connection_tasks[connection_id]

    async def send_json(self, connection_id: str, message: dict):
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                await self.disconnect(connection_id)
# 创建连接管理器实例
manager = ConnectionManager()
# 获取或加载YOLO模型
def get_model(models_name):
    """获取或加载检测模型（ONNX 优先，兼容 ultralytics 开发环境）。"""
    if models_name not in models_cache:
        candidates = [
            Path(f"models/{models_name}.onnx"),
            Path(f"models/{models_name}.pt"),
        ]
        models_path = next((p for p in candidates if p.exists()), None)
        if models_path is None:
            logger.error("Model file not found: %s (.onnx / .pt)", models_name)
            return None
        try:
            model, infer_device, is_onnx = load_detection_model(
                str(models_path),
                models_type="object_detection",
                is_gpu=cuda_available(),
            )
            models_cache[models_name] = {
                "type": "onnx" if is_onnx else "pytorch",
                "model": model,
                "infer_device": infer_device,
                "is_onnx": is_onnx,
            }
            logger.info("RTSP preview model loaded: %s onnx=%s", models_path, is_onnx)
        except Exception as e:
            logger.error(f"Error loading model {models_name}: {e}")
            return None
    return models_cache.get(models_name)
# 处理单帧图像
def process_frame(frame, models_info, frame_id, timestamp, total_frames=None, start_time=None):
    """处理单帧图像。成功返回 (result_dict, None)，失败返回 (None, error_message)。"""
    start_process_time = time.time()
    
    try:
        # 预处理图像
        if frame is None or frame.ndim < 2:
            return None, "Invalid frame array"
        orig_h, orig_w = frame.shape[:2]
        if orig_h <= 0 or orig_w <= 0:
            return None, f"Invalid frame size: {orig_w}x{orig_h}"
        scale = min(max_size / orig_h, max_size / orig_w)
        
        if scale < 1:
            new_h, new_w = int(orig_h * scale), int(orig_w * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)  # 使用INTER_AREA以提高性能
        
        infer_device = models_info.get("infer_device", "cpu")
        is_onnx = models_info.get("is_onnx", models_info.get("type") == "onnx")
        results = predict_detection_frame(
            models_info["model"],
            frame,
            infer_device=infer_device,
            is_onnx=is_onnx,
            confidence=0.25,
        )
        parsed = process_yolo_results(results, [], include_segmentation=False)
        detections = []
        for item in parsed:
            x1, y1, x2, y2 = item["bbox"]
            if scale < 1:
                x1, x2 = x1 / scale, x2 / scale
                y1, y2 = y1 / scale, y2 / scale
            w = x2 - x1
            h = y2 - y1
            detections.append({
                "class": item.get("class_name", "object"),
                "confidence": round(float(item.get("confidence", 0)), 3),
                "bbox": [float(x1), float(y1), float(w), float(h)],
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
            })
        
        # 应用框平滑
        smoothed_detections = frame_processor.smooth_boxes(detections, frame_id)
        
        processing_time = time.time() - start_process_time
        frame_processor.processing_times.append(processing_time)

        # 计算进度和剩余时间
        progress = None
        remaining_time = None
        if total_frames and start_time:
            progress = (frame_id + 1) / total_frames * 100
            elapsed_time = time.time() - start_time
            avg_time_per_frame = elapsed_time / (frame_id + 1)
            remaining_frames = total_frames - (frame_id + 1)
            remaining_time = remaining_frames * avg_time_per_frame
        
        return {
            "type": "detection_result",
            "objects": smoothed_detections,
            "frame_id": frame_id,
            "timestamp": timestamp,
            "processing_time": processing_time,
            "avg_processing_time": frame_processor.get_avg_processing_time(),
            "progress": progress,
            "remaining_time": remaining_time,
            "total_frames": total_frames,
            "image_width": orig_w,
            "image_height": orig_h
        }, None
    
    except Exception as e:
        logger.exception("Error processing frame")
        return None, str(e)
# 异步处理帧队列
async def process_frame_queue(connection_id: str):
    """异步处理帧队列"""
    queue = frame_queues.get(connection_id)
    if not queue:
        return
        
    last_processed_time = 0
    skip_count = 0
    
    try:
        while connection_id in frame_queues and connection_id in manager.active_connections:
            try:
                if queue.empty():
                    await asyncio.sleep(0.01)
                    continue
                
                current_time = time.time()
                
                # 智能帧选择
                if queue.qsize() > 1:
                    while queue.qsize() > 1:
                        queue.get_nowait()
                        skip_count += 1
                    
                    if skip_count >= 10:
                        logger.info(f"Skipped {skip_count} frames for client {connection_id} to reduce latency")
                        skip_count = 0
                
                frame_data = queue.get_nowait()
                
                # 检查延迟
                latency = (current_time - frame_data["timestamp"]/1000) * 1000
                if latency > max_latency:
                    logger.debug(f"Dropping frame {frame_data['frame_id']} for client {connection_id} due to high latency: {latency:.0f}ms")
                    continue
                
                # 控制处理频率
                if current_time - last_processed_time < 0.033:
                    continue
                
                result, proc_err = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    process_frame,
                    frame_data["frame"],
                    frame_data["model"],
                    frame_data["frame_id"],
                    frame_data["timestamp"],
                    frame_data.get("total_frames"),
                    frame_data.get("start_time")
                )
                
                if proc_err:
                    logger.error(f"process_frame failed for {connection_id}: {proc_err}")
                if result:
                    await manager.send_json(connection_id, result)
                    last_processed_time = current_time
            
            except Exception as e:
                logger.error(f"Error in frame queue processing for client {connection_id}: {e}")
                await asyncio.sleep(0.1)
    
    except asyncio.CancelledError:
        logger.info(f"Frame queue processing cancelled for client {connection_id}")
    except Exception as e:
        logger.error(f"Unexpected error in frame queue processing for client {connection_id}: {e}")
    finally:
        logger.info(f"Frame queue processing ended for client {connection_id}")
# 非极大值抑制(NMS)
def non_max_suppression(boxes, scores, iou_threshold=0.45):
    """
    执行非极大值抑制(NMS)，去除重叠的检测框
    
    参数:
        boxes: 边界框列表 [[x, y, w, h], ...]
        scores: 对应的置信度分数
        iou_threshold: IoU阈值，高于此值的框会被抑制
        
    返回:
        保留的检测框的索引列表
    """
    try:
        # 检查输入有效性
        if len(boxes) == 0 or len(scores) != len(boxes):
            return []
        
        # 转换成numpy数组
        boxes = np.array(boxes)
        scores = np.array(scores)
        
        # 计算每个框的面积和右下角坐标
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        w = boxes[:, 2]
        h = boxes[:, 3]
        x2 = x1 + w
        y2 = y1 + h
        area = w * h
        
        # 按照分数从高到低排序
        idxs = np.argsort(scores)[::-1]
        
        # 保留的框的索引
        keep = []
        
        while len(idxs) > 0:
            # 取分数最高的框
            i = idxs[0]
            keep.append(i)
            
            # 计算其他框与当前框的IoU
            xx1 = np.maximum(x1[i], x1[idxs[1:]])
            yy1 = np.maximum(y1[i], y1[idxs[1:]])
            xx2 = np.minimum(x2[i], x2[idxs[1:]])
            yy2 = np.minimum(y2[i], y2[idxs[1:]])
            
            # 计算重叠区域的宽和高
            w_inter = np.maximum(0, xx2 - xx1)
            h_inter = np.maximum(0, yy2 - yy1)
            
            # 计算重叠区域的面积
            intersection = w_inter * h_inter
            
            # 计算IoU
            union = area[i] + area[idxs[1:]] - intersection
            iou = intersection / (union + 1e-8)  # 避免除以0
            
            # 保留IoU小于阈值的框
            idxs = idxs[1:][iou < iou_threshold]
        
        return keep
    except Exception as e:
        logger.error(f"Error in NMS: {e}")
        return list(range(len(boxes)))  # 出错时返回所有框
# 检测预览WebSocket端点
@router.websocket("/preview")
async def websocket_endpoint(websocket: WebSocket):
    connection_id = await manager.connect(websocket)
    rtsp_sessions[connection_id] = {"status": "connected"}
    models_info = None
    
    try:
        # 等待客户端的连接请求
        while True:
            message = await websocket.receive_json()
            # 增加处理连接请求的逻辑
            if message["type"] == "connect":
                # 发送连接确认
                await websocket.send_json({
                    "type": "connect_confirm"
                })
                continue
            # 增加处理RTSP预览请求的逻辑
            elif message["type"] == "preview_request":
                # 获取RTSP URL
                stream_url = message.get("stream_url")
                device_id = message.get("device_id")
                
                if not stream_url:
                    await websocket.send_json({
                        "type": "error",
                        "message": "缺少流URL"
                    })
                    continue
                
                # 将WebSocket连接添加到活动连接字典
                active_connections[connection_id] = websocket
                
                # 启动RTSP流处理
                await websocket.send_json({
                    "type": "preview_connecting",
                    "message": "正在连接RTSP流，请稍候..."
                })
                
                result = await rtsp_manager.start_stream(connection_id, stream_url)
                
                if not result:
                    await websocket.send_json({
                        "type": "error",
                        "message": "启动流处理失败，可能该流已在处理中"
                    })
                continue
            # 增加处理模型配置请求的逻辑
            elif message["type"] == "config":
                # 处理模型配置
                models_name = message.get("models_name")
                if not models_name:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No model specified in configuration"
                    })
                    continue

                try:
                    models_info = get_model(message.get("models_id"))
                    
                    if not models_info:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Failed to load model: {models_name}"
                        })
                        continue
                                        
                    # 发送配置确认
                    await websocket.send_json({
                        "type": "config_confirm",
                        "model": models_name
                    })
                
                except Exception as e:
                    error_msg = f"Error configuring model {models_name}: {str(e)}"
                    await websocket.send_json({
                        "type": "error",
                        "message": error_msg
                    })
                continue
            # 增加处理图片检测请求的逻辑
            elif message["type"] == "image":
                # 处理单张图片检测请求
                if not models_info:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Model not configured. Please configure model first."
                    })
                    continue
                
                start_time = time.time()
                try:
                    # 获取图片信息
                    image_id = message.get("image_id", 0)
                    image_name = message.get("image_name", f"image_{image_id}")
                    timestamp = message.get("timestamp", time.time())
                    width = message.get("width", 0)
                    height = message.get("height", 0)
                    original_width = message.get("original_width", width)
                    original_height = message.get("original_height", height)
                    scale = message.get("scale", 1.0)               
                    
                    # 解码图像
                    decode_start_time = time.time()
                    try:
                        img_data = base64.b64decode(message.get("frame"))
                        nparr = np.frombuffer(img_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if frame is None:
                            raise ValueError("Failed to decode image")
                        
                        decode_time = time.time() - decode_start_time
                    except Exception as e:
                        error_msg = f"Error decoding image: {str(e)}"
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })
                        continue
                    
                    # 处理图片
                    try:
                        # 性能优化：如果图像尺寸过大，可以缩小后处理
                        max_dim = 1280  # 最大尺寸
                        orig_h, orig_w = frame.shape[:2]
                        target_frame = frame
                        target_scale = 1.0
                        
                        # 如果原始图像过大，先缩小进行检测，再缩放结果
                        if max(orig_h, orig_w) > max_dim:
                            resize_scale = max_dim / max(orig_h, orig_w)
                            new_h, new_w = int(orig_h * resize_scale), int(orig_w * resize_scale)
                            target_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                            target_scale = resize_scale
                        
                        # 检测开始时间
                        detect_start_time = time.time()
                        
                        # 使用process_frame函数处理图片
                        result, proc_err = process_frame(
                            frame=target_frame,
                            models_info=models_info,
                            frame_id=image_id,
                            timestamp=timestamp
                        )
                        
                        # 检测时间
                        detect_time = time.time() - detect_start_time
                        
                        if proc_err or not result:
                            raise ValueError(proc_err or "Failed to process image")
                        
                        # 处理缩放以匹配原始尺寸
                        if target_scale < 1.0:
                            for obj in result["objects"]:
                                if "bbox" in obj:
                                    x, y, w, h = obj["bbox"]
                                    obj["bbox"] = [
                                        x / target_scale,
                                        y / target_scale,
                                        w / target_scale,
                                        h / target_scale
                                    ]
                                if all(k in obj for k in ["x1", "y1", "x2", "y2"]):
                                    obj["x1"] /= target_scale
                                    obj["y1"] /= target_scale
                                    obj["x2"] /= target_scale
                                    obj["y2"] /= target_scale
                        
                        # 应用非极大值抑制(NMS)处理重叠检测框
                        nms_start_time = time.time()
                        nms_applied = False
                        try:
                            if len(result["objects"]) > 1:
                                
                                # 提取边界框和分数
                                boxes = []
                                scores = []
                                for obj in result["objects"]:
                                    if "bbox" in obj:
                                        boxes.append(obj["bbox"])
                                        scores.append(obj["confidence"])
                                
                                # 应用NMS
                                if boxes and scores:
                                    keep_indices = non_max_suppression(boxes, scores, iou_threshold=0.45)
                                    
                                    # 仅保留NMS后的检测结果
                                    filtered_objects = [result["objects"][i] for i in keep_indices]
                                    result["objects"] = filtered_objects
                                    nms_applied = True
                        except Exception as e:
                            logger.error(f"Error applying NMS: {e}")
                            # 继续使用原始检测结果
                        
                        nms_time = time.time() - nms_start_time
                        
                        # 如果图片进行了缩放，需要调整检测框坐标
                        if scale != 1.0 and original_width > 0 and original_height > 0:
                            scale_factor = 1.0 / scale
                            for obj in result["objects"]:
                                # 调整检测框坐标和尺寸
                                if "bbox" in obj:
                                    x, y, w, h = obj["bbox"]
                                    obj["bbox"] = [
                                        x * scale_factor,
                                        y * scale_factor,
                                        w * scale_factor,
                                        h * scale_factor
                                    ]
                                # 更新x1, y1, x2, y2坐标(如果存在)
                                if all(k in obj for k in ["x1", "y1", "x2", "y2"]):
                                    obj["x1"] *= scale_factor
                                    obj["y1"] *= scale_factor
                                    obj["x2"] *= scale_factor
                                    obj["y2"] *= scale_factor
                        
                        # 添加图片ID和名称到结果
                        result["image_id"] = image_id
                        result["image_name"] = image_name
                        result["original_width"] = original_width
                        result["original_height"] = original_height
                        
                        # 添加性能信息
                        total_time = time.time() - start_time
                        result["performance"] = {
                            "decode_time": round(decode_time * 1000, 2),  # ms
                            "detection_time": round(detect_time * 1000, 2),  # ms
                            "nms_time": round(nms_time * 1000, 2),  # ms
                            "total_time": round(total_time * 1000, 2),  # ms
                            "nms_applied": nms_applied
                        }
                                             
                        # 发送检测结果
                        await websocket.send_json(result)
                        
                    except Exception as e:
                        error_msg = f"Error processing image: {str(e)}"
                        await websocket.send_json({
                            "type": "error",
                            "message": error_msg
                        })
                except Exception as e:
                    error_msg = f"Error handling image detection request: {str(e)}"
                    await websocket.send_json({
                        "type": "error",
                        "message": error_msg
                    })
                continue
            # 增加处理视频信息请求的逻辑
            elif message["type"] == "video_info":
                # 处理视频信息
                if not models_info:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Model not configured. Please configure model first."
                    })
                    continue
                                        
                frame_queues[connection_id] = asyncio.Queue(maxsize=max_queue_size)
                
                # 启动帧处理任务
                task = asyncio.create_task(process_frame_queue(connection_id))
                manager.connection_tasks[connection_id] = task               
            # 增加处理视频帧请求的逻辑
            elif message["type"] == "video":
                # 处理视频帧
                if not models_info:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Model not configured. Please configure model first."
                    })
                    continue
                                        
                try:
                    frame_data = message.get("frame")
                    frame_id = message.get("frame_id", 0)
                    current_time = time.time()
                    
                    # 检查帧延迟
                    frame_timestamp = message.get("timestamp", current_time)
                    latency = (current_time - frame_timestamp) * 1000
                    
                    if latency > max_latency:
                        continue
                    
                    if not frame_data:
                        continue
                                        
                    # 解码图像
                    img_data = base64.b64decode(frame_data)
                    nparr = np.frombuffer(img_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is None:
                        raise ValueError("Failed to decode image")
                    
                    # 将帧数据放入队列
                    results = await frame_queues[connection_id].put({
                        "frame": frame,
                        "model": models_info,
                        "frame_id": frame_id,
                        "timestamp": frame_timestamp,
                        "total_frames": message.get("total_frames"),
                        "start_time": message.get("start_time")
                    })
                    if results:
                        # 添加延迟信息到结果中
                        results["latency"] = latency
                        await websocket.send_json(results)
                    
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to process frame: {str(e)}"
                    })
            else:
                # 处理其他现有命令...
                pass

    except WebSocketDisconnect:
        logger.info(f"Client {connection_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {connection_id}: {str(e)}")
    finally:
        # 确保断开连接时停止所有流处理
        if connection_id in active_connections:
            await rtsp_manager.stop_stream(connection_id)
        await manager.disconnect(connection_id)