import ffmpeg
import numpy as np
import threading
import time
import logging
import psutil
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from typing import Optional, Tuple, Dict, Any
import subprocess
import os
import select

logger = logging.getLogger(__name__)

class FFmpegDecoderDocker:
    """针对Docker环境优化的FFmpeg视频解码器 V4 - 缓冲区优化版本"""
    
    def __init__(self, rtsp_url: str, max_workers: int = 4, buffer_size: int = 5):
        self.rtsp_url = rtsp_url
        self.max_workers = max_workers
        self.buffer_size = buffer_size
        
        # 状态变量
        self.is_running = False
        self.process = None
        self.read_thread = None
        
        # 帧缓冲 - 增加缓冲区大小
        self.frame_buffer = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        
        # 统计信息
        self.frame_count = 0
        self.last_frame_time = 0
        self.decode_times = []
        self.cpu_usage_history = []
        
        # 连接参数
        self.connection_retries = 3
        self.retry_delay = 2
        self.width = None
        self.height = None
        self.frame_size = None
        
        # 解码线程池
        self.decoder_pool = ThreadPoolExecutor(max_workers=max_workers)
        
        # 调试信息
        self.debug_mode = True
        self.last_error = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10
        
        # Docker环境特殊设置
        self.docker_mode = True
        self.read_timeout = 5.0  # 增加超时时间到5秒
        self.buffer_chunk_size = 16384  # 增加分块读取大小
        self.frame_skip_threshold = 0.8  # 帧数据完整性阈值

    def _create_ffmpeg_process(self) -> Optional[Any]:
        """创建FFmpeg进程（优化版本）"""
        try:
            logger.info(f"创建FFmpeg进程，URL: {self.rtsp_url}")
            
            # 使用优化的FFmpeg参数
            process = (
                ffmpeg
                .input(
                    self.rtsp_url,
                    rtsp_transport='tcp'      # 使用TCP传输
                )
                .output(
                    'pipe:',
                    format='rawvideo',
                    pix_fmt='bgr24',           # OpenCV兼容的像素格式
                    acodec='none',             # 不处理音频
                    vsync='cfr'                # 恒定帧率
                )
                .run_async(pipe_stdout=True, pipe_stderr=True, quiet=False)
            )
            
            logger.info("FFmpeg进程创建成功")
            return process
            
        except Exception as e:
            logger.error(f"创建FFmpeg进程失败: {e}")
            return None

    def _create_ffmpeg_process_subprocess(self) -> Optional[Any]:
        """使用subprocess创建FFmpeg进程（备用方案）"""
        try:
            logger.info("使用subprocess创建FFmpeg进程...")
            
            # 构建优化的FFmpeg命令
            cmd = [
                'ffmpeg',
                '-i', self.rtsp_url,
                '-rtsp_transport', 'tcp',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-an',  # 不处理音频
                '-vsync', 'cfr',  # 恒定帧率
                '-'
            ]
            
            logger.info(f"FFmpeg命令: {' '.join(cmd)}")
            
            # 创建进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            logger.info("subprocess FFmpeg进程创建成功")
            return process
            
        except Exception as e:
            logger.error(f"使用subprocess创建FFmpeg进程失败: {e}")
            return None

    def _decode_frame_worker(self, frame_data: bytes, width: int, height: int) -> Optional[np.ndarray]:
        """解码帧的工作函数"""
        try:
            start_time = time.time()
            
            # 将字节数据转换为numpy数组
            frame = np.frombuffer(frame_data, dtype=np.uint8)
            frame = frame.reshape((height, width, 3))
            
            decode_time = time.time() - start_time
            self.decode_times.append(decode_time)

            return frame
        except Exception as e:
            logger.error(f"解码帧失败: {e}")
            return None

    def _read_frame_data_docker_v4(self, process: Any, width: int, height: int) -> Optional[np.ndarray]:
        """V4版本的帧数据读取（优化版本）"""
        try:
            frame_size = width * height * 3
            logger.debug(f"尝试读取帧数据，期望大小: {frame_size} 字节")
            
            # 检查进程状态
            if hasattr(process, 'poll') and process.poll() is not None:
                logger.warning("FFmpeg进程已退出")
                return None
            
            # 使用优化的读取策略
            frame_data = b''
            start_time = time.time()
            last_read_time = start_time
            consecutive_empty_reads = 0
            max_consecutive_empty = 10
            
            while len(frame_data) < frame_size:
                current_time = time.time()
                
                # 检查总超时
                if current_time - start_time > self.read_timeout:
                    logger.warning(f"读取帧数据超时，已读取 {len(frame_data)}/{frame_size} 字节")
                    # 如果读取了大部分数据，尝试使用不完整的数据
                    if len(frame_data) >= frame_size * self.frame_skip_threshold:
                        logger.info(f"使用不完整的帧数据: {len(frame_data)}/{frame_size}")
                        break
                    return None
                
                # 检查是否有数据可读
                if hasattr(process.stdout, 'fileno'):
                    try:
                        # 使用select检查是否有数据可读
                        ready, _, _ = select.select([process.stdout], [], [], 0.05)
                        if not ready:
                            # 检查进程是否还在运行
                            if hasattr(process, 'poll') and process.poll() is not None:
                                logger.warning("FFmpeg进程在等待数据时退出")
                                return None
                            
                            consecutive_empty_reads += 1
                            if consecutive_empty_reads > max_consecutive_empty:
                                logger.warning("连续多次无数据可读，可能流已结束")
                                break
                            continue
                        else:
                            consecutive_empty_reads = 0
                            
                    except (OSError, ValueError) as e:
                        logger.debug(f"select检查失败: {e}")
                        pass
                
                # 分块读取数据
                chunk_size = min(self.buffer_chunk_size, frame_size - len(frame_data))
                chunk = process.stdout.read(chunk_size)
                
                if chunk:
                    frame_data += chunk
                    last_read_time = current_time
                    logger.debug(f"读取数据块: {len(chunk)} 字节，总计: {len(frame_data)}/{frame_size}")
                else:
                    # 没有更多数据，检查是否长时间没有新数据
                    if current_time - last_read_time > 0.5:  # 0.5秒没有新数据
                        logger.warning("长时间没有新数据，可能流已结束")
                        break
                    time.sleep(0.01)
                    continue
            
            # 处理帧数据大小不匹配的情况
            if len(frame_data) != frame_size:
                logger.warning(f"帧数据大小不匹配: 期望{frame_size}, 实际{len(frame_data)}")
                if len(frame_data) > 0:
                    logger.info(f"尝试使用实际数据大小进行解码")
                    # 尝试调整分辨率以适应实际数据
                    actual_pixels = len(frame_data) // 3
                    # 计算最接近的宽高比
                    aspect_ratio = width / height
                    new_height = int(np.sqrt(actual_pixels / aspect_ratio))
                    new_width = int(new_height * aspect_ratio)
                    if new_width * new_height * 3 == len(frame_data):
                        logger.info(f"调整分辨率到: {new_width}x{new_height}")
                        width, height = new_width, new_height
                        frame_size = len(frame_data)
                    else:
                        # 如果无法调整，尝试填充或截断
                        if len(frame_data) < frame_size:
                            # 填充不足的部分
                            padding = frame_size - len(frame_data)
                            frame_data += b'\x00' * padding
                            logger.info(f"填充 {padding} 字节到帧数据")
                        else:
                            # 截断多余的部分
                            frame_data = frame_data[:frame_size]
                            logger.info(f"截断帧数据到 {frame_size} 字节")
                else:
                    return None
            
            # 解码帧
            frame = self._decode_frame_worker(frame_data, width, height)
            if frame is not None:
                logger.debug(f"成功解码帧: {frame.shape}")
            return frame
            
        except Exception as e:
            logger.error(f"读取帧数据失败: {e}")
            self.last_error = str(e)
            return None

    def _get_stream_info(self, process: Any = None) -> Tuple[Optional[int], Optional[int]]:
        """获取流信息（宽度和高度）"""
        try:
            logger.info("获取流信息...")
            # 使用ffprobe获取流信息
            probe = ffmpeg.probe(self.rtsp_url)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')  
            width = int(video_info['width'])
            height = int(video_info['height'])
            logger.info(f"获取到流信息: {width}x{height}")
            return width, height
        except Exception as e:
            logger.error(f"获取流信息失败: {e}")
            # 使用默认分辨率
            logger.info("使用默认分辨率: 1920x1080")
            return 1920, 1080

    def start(self) -> bool:
        """启动解码器"""
        if self.is_running:
            return True
            
        logger.info("启动FFmpeg解码器...")
        
        for attempt in range(self.connection_retries):
            try:               
                logger.info(f"尝试启动解码器 (第{attempt + 1}次)")
                
                # 先获取流信息
                width, height = self._get_stream_info(None)
                if not width or not height:
                    logger.error("无法获取流信息")
                    continue
                
                self.width = width
                self.height = height
                self.frame_size = width * height * 3
                logger.info(f"设置帧大小: {self.frame_size} 字节")
                
                # 尝试使用ffmpeg-python创建进程
                self.process = self._create_ffmpeg_process()
                
                # 如果ffmpeg-python失败，尝试使用subprocess
                if not self.process:
                    logger.info("ffmpeg-python创建进程失败，尝试使用subprocess...")
                    self.process = self._create_ffmpeg_process_subprocess()
                
                if not self.process:
                    logger.error("创建FFmpeg进程失败")
                    continue
                
                # 等待一下让进程稳定
                time.sleep(2)
                
                # 检查进程是否还在运行
                if hasattr(self.process, 'poll') and self.process.poll() is not None:
                    logger.error("FFmpeg进程启动后立即退出")
                    # 尝试获取错误信息
                    if hasattr(self.process, 'stderr'):
                        try:
                            stderr_output = self.process.stderr.read()
                            if stderr_output:
                                logger.error(f"FFmpeg错误输出: {stderr_output.decode('utf-8', errors='ignore')}")
                        except:
                            pass
                    continue
                
                # 启动读取线程
                self.is_running = True
                self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
                self.read_thread.start()
                
                # 启动自动重连线程
                self.reconnect_thread = threading.Thread(target=self._auto_reconnect_loop, daemon=True)
                self.reconnect_thread.start()
                
                logger.info("FFmpeg解码器启动成功")
                return True
                
            except Exception as e:
                logger.error(f"启动解码器失败 (第{attempt + 1}次): {e}")
                if self.process:
                    try:
                        self.process.terminate()
                    except:
                        pass
                    self.process = None
                
                if attempt < self.connection_retries - 1:
                    logger.info(f"等待 {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
        
        logger.error("FFmpeg解码器启动失败，已达到最大重试次数")
        return False

    def _auto_reconnect_loop(self):
        """自动重连循环"""
        while self.is_running:
            try:
                # 每5秒检查一次，但每0.5秒检查一次停止信号
                for _ in range(10):  # 10 * 0.5 = 5秒
                    if not self.is_running:
                        logger.debug("自动重连循环收到停止信号，退出")
                        return
                    time.sleep(0.5)
                
                # 检查读取线程是否还在运行
                if self.is_running and self.read_thread and not self.read_thread.is_alive():
                    logger.warning("读取线程已停止，尝试重新启动解码器")
                    if self.is_running:  # 再次检查，避免在停止过程中重启
                        self._restart_decoder()
                    
            except Exception as e:
                logger.error(f"自动重连循环出错: {e}")
                if not self.is_running:
                    break
                time.sleep(1)
        
        logger.debug("自动重连循环已退出")

    def _restart_decoder(self):
        """重启解码器"""
        try:
            # 检查是否已经停止
            if not self.is_running:
                logger.debug("解码器已停止，跳过重启")
                return
            
            logger.info("重启FFmpeg解码器...")
            
            # 停止当前进程
            if self.process:
                try:
                    self.process.terminate()
                except:
                    pass
                self.process = None
            
            # 重置状态
            self.is_running = False
            time.sleep(1)
            
            # 检查是否应该继续重启
            if not self.is_running:
                logger.debug("解码器已停止，取消重启")
                return
            
            # 重新启动
            if self.start():
                logger.info("FFmpeg解码器重启成功")
            else:
                logger.error("FFmpeg解码器重启失败")
                
        except Exception as e:
            logger.error(f"重启解码器失败: {e}")

    def _read_loop(self):
        """读取循环（V4版本）"""
        consecutive_empty_reads = 0
        max_empty_reads = 50
        last_success_time = time.time()
        frame_interval = 1.0 / 25  # 25fps的目标间隔
        restart_count = 0
        max_restarts = 3
                
        logger.info("开始读取循环...")
        
        while self.is_running and self.process:
            try:
                loop_start = time.time()
                
                # 检查是否已停止
                if not self.is_running:
                    logger.debug("读取循环收到停止信号，退出")
                    break
                
                # 使用V4版本的读取方法
                frame = self._read_frame_data_docker_v4(self.process, self.width, self.height)

                if frame is not None:
                    with self.lock:
                        # 确保缓冲区有空间
                        if len(self.frame_buffer) >= self.buffer_size:
                            self.frame_buffer.popleft()  # 移除最旧的帧
                        self.frame_buffer.append(frame)
                        self.frame_count += 1
                        self.last_frame_time = time.time()
                        self.consecutive_failures = 0
                    
                    consecutive_empty_reads = 0
                    last_success_time = time.time()
                    restart_count = 0
                    
                    if self.frame_count % 10 == 0:  # 每10帧记录一次
                        logger.info(f"已成功读取 {self.frame_count} 帧，缓冲区: {len(self.frame_buffer)}")
                        
                else:
                    consecutive_empty_reads += 1
                    self.consecutive_failures += 1
                    
                    # 检查进程是否还在运行
                    if self.process and hasattr(self.process, 'poll') and self.process.poll() is not None:
                        logger.warning("FFmpeg进程已退出，尝试重新连接")
                        break
                    
                    # 检查是否长时间没有成功读取帧
                    if time.time() - last_success_time > 10:
                        if restart_count < max_restarts and self.is_running:
                            logger.warning(f"长时间未读取到帧，尝试重启解码器 (第{restart_count + 1}次)")
                            restart_count += 1
                            if self.is_running:
                                self._quick_restart()
                            last_success_time = time.time()
                            continue
                        else:
                            logger.error("达到最大重启次数，停止解码器")
                            break
                    
                    # 如果连续失败次数过多，尝试重启
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        if restart_count < max_restarts and self.is_running:
                            logger.warning(f"连续失败{self.consecutive_failures}次，尝试重启解码器 (第{restart_count + 1}次)")
                            restart_count += 1
                            if self.is_running:
                                self._quick_restart()
                            continue
                        else:
                            logger.error("达到最大重启次数，停止解码器")
                            break
                
                # 控制循环频率
                loop_time = time.time() - loop_start
                if loop_time < frame_interval:
                    time.sleep(frame_interval - loop_time)
                    
            except Exception as e:
                logger.error(f"读取循环出错: {e}")
                self.consecutive_failures += 1
                if not self.is_running:
                    break
                time.sleep(0.05)
        
        logger.debug("读取循环已退出")
        self.is_running = False

    def _quick_restart(self):
        """快速重启解码器"""
        try:
            if not self.is_running:
                logger.debug("解码器已停止，跳过快速重启")
                return False
            
            logger.info("快速重启FFmpeg解码器...")
            
            if self.process:
                try:
                    self.process.terminate()
                except:
                    pass
                self.process = None
            
            time.sleep(0.5)
            
            if not self.is_running:
                logger.debug("解码器已停止，取消快速重启")
                return False
            
            if self.is_running:
                # 尝试使用subprocess创建进程
                self.process = self._create_ffmpeg_process_subprocess()
                if not self.process:
                    logger.error("快速重启失败：无法创建FFmpeg进程")
                    return False
                
                self.consecutive_failures = 0
                logger.info("快速重启成功")
                return True
            else:
                logger.debug("解码器已停止，取消快速重启")
                return False
            
        except Exception as e:
            logger.error(f"快速重启失败: {e}")
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """读取一帧（兼容OpenCV的read方法）"""
        if not self.is_running:
            return False, None
        
        max_attempts = 5
        success = False
        frame = None
        
        for attempt in range(max_attempts):
            with self.lock:
                if self.frame_buffer:
                    frame = self.frame_buffer.popleft()
                    success = True
                    break
            
            if attempt < max_attempts - 1:
                if attempt < 2:
                    time.sleep(0.005)
                elif attempt < 4:
                    time.sleep(0.02)
                else:
                    time.sleep(0.05)
        
        return success, frame

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        with self.lock:
            avg_decode_time = np.mean(self.decode_times) if self.decode_times else 0
            
            return {
                'frame_count': self.frame_count,
                'buffer_size': len(self.frame_buffer),
                'avg_decode_time_ms': avg_decode_time * 1000,
                'is_running': self.is_running,
                'thread_pool_size': self.max_workers,
                'consecutive_failures': self.consecutive_failures,
                'last_error': self.last_error,
                'docker_mode': self.docker_mode,
                'width': self.width,
                'height': self.height,
                'frame_size': self.frame_size
            }

    def stop(self):
        """停止解码器"""
        logger.info("正在停止FFmpeg解码器...")
        
        self.is_running = False
        
        if self.process:
            try:
                logger.debug("终止FFmpeg进程...")
                if hasattr(self.process, 'terminate'):
                    self.process.terminate()
                    if hasattr(self.process, 'wait'):
                        try:
                            self.process.wait(timeout=3)  # 减少等待时间
                        except:
                            pass
                else:
                    self.process.kill()
            except Exception as e:
                logger.warning(f"终止FFmpeg进程失败: {e}")
                try:
                    if hasattr(self.process, 'kill'):
                        self.process.kill()
                except:
                    pass
            finally:
                self.process = None
        
        if self.read_thread and self.read_thread.is_alive():
            logger.debug("等待读取线程结束...")
            try:
                self.read_thread.join(timeout=3)  # 减少等待时间
                if self.read_thread.is_alive():
                    logger.warning("读取线程未能在3秒内结束")
            except Exception as e:
                logger.warning(f"等待读取线程结束失败: {e}")
        
        if hasattr(self, 'reconnect_thread') and self.reconnect_thread and self.reconnect_thread.is_alive():
            logger.debug("等待自动重连线程结束...")
            try:
                self.reconnect_thread.join(timeout=3)  # 减少等待时间
                if self.reconnect_thread.is_alive():
                    logger.warning("自动重连线程未能在3秒内结束")
            except Exception as e:
                logger.warning(f"等待自动重连线程结束失败: {e}")
        
        with self.lock:
            self.frame_buffer.clear()
        
        if self.decoder_pool:
            self.decoder_pool.shutdown(wait=True)
        
        logger.info("FFmpeg解码器已停止")
