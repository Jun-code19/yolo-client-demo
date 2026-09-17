"""
检测运行时 FastAPI 应用：任务调度、/api/v2、WebSocket、storage。
生产入口为 serve_unified.py，勿单独 python serve_detect.py。
"""
import asyncio
import logging
import os

from src.env_loader import configure_ultralytics_env, load_env_file

configure_ultralytics_env()
load_env_file()

import numpy as np # 导入NumPy模块
from datetime import datetime, timedelta # 导入日期时间模块
from pathlib import Path # 导入路径模块

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware # 导入CORS中间件
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager # 导入异步上下文管理器
from sqlalchemy.orm import Session # 导入数据库会话

# 导入数据推送模块
from src.data_pusher import data_pusher
from src.alert_rule_engine import alert_rule_scheduler
# 导入数据库模块
from src.database import (
    SessionLocal, DetectionConfig, DetectionEvent, Device, DeviceGroup,
    DetectionModel, ExternalEvent, SmartEvent, Base, engine, get_db
)

from src.detection_runtime import extract_runtime_config
from src.inference_pipeline.pipeline_config import extract_inference_pipeline
from src.run_detection_task import DetectionTask
from src.group_detection_task import GroupDetectionTask
from src.yolo_task_utils import resolve_yolo_task, load_yolo_model_classes, load_detection_model, is_onnx_model_path
from src.inference_backend import cuda_available, use_ultralytics

# 导入认证模块
from api.auth import get_current_user, User
# 导入日志模块
from api.logger import log_action, log_detection_action
# 导入事件订阅管理器
from src.smartSchemer import smart_schemer
# 导入设备监控模块
from src.device_monitor import device_monitor

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 检测服务器类，管理所有检测任务
class DetectionServer:
    # 初始化检测服务器
    def __init__(self):
        self.tasks = {}  # 存储所有检测任务，格式: {config_id: DetectionTask}
        self.models_cache = {}  # 缓存已加载的模型，格式: {model_path: model}
        self.cleanup_task = None  # 全局清理任务
        self.max_concurrent_tasks = 50 # 最大并发任务数
        # 资源监控相关属性
        self.total_cpu_usage = 0
        self.total_memory_usage = 0
        self.active_task_count = 0

    @staticmethod
    def _log_device_id_for_config(config: DetectionConfig, task=None):
        config_mode = getattr(config, "config_mode", None) or "device"
        if config_mode == "group":
            if task and getattr(task, "last_device_id", None):
                return task.last_device_id
            return None
        return config.device_id
    
    # 启动特定配置的检测任务
    async def start_detection(self, config_id: str, db: Session, user_id: str = None):
        """启动特定配置的检测任务"""
        # 检查任务是否已在运行
        if config_id in self.tasks and self.tasks[config_id].thread and self.tasks[config_id].thread.is_alive():
            return {"status": "success", "message": "检测任务已在运行"}
        
        # 检查系统资源是否允许启动新任务
        if not self._should_start_new_task():
            return {"status": "error", "message": "系统资源不足，无法启动新任务"}
        
        try:
            # 获取检测配置
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
            if not config:
                logger.error(f"未找到检测配置: {config_id}")
                # 记录失败日志
                log_detection_action(config_id, "unknown", "start", "failed", "未找到检测配置", user_id)
                return {"status": "error", "message": "未找到检测配置"}
            
            # 获取模型信息
            model = db.query(DetectionModel).filter(DetectionModel.models_id == config.models_id).first()
            if not model:
                logger.error(f"未找到模型: {config.models_id}")
                log_detection_action(
                    config_id,
                    self._log_device_id_for_config(config),
                    "start",
                    "failed",
                    f"未找到模型: {config.models_id}",
                    user_id,
                )
                return {"status": "error", "message": "未找到模型"}
            
            # 检查频率
            config_mode = getattr(config, "config_mode", None) or "device"
            if config_mode == "group":
                if config.frequency.value != "realtime":
                    log_detection_action(
                        config_id,
                        None,
                        "start",
                        "failed",
                        f"分组检测仅支持实时模式 (group_id={config.group_id})",
                        user_id,
                    )
                    return {"status": "error", "message": "分组检测仅支持实时模式"}
                await self._create_and_start_task(config, model, db)
                log_detection_action(
                    config_id,
                    None,
                    "start",
                    "success",
                    f"启动分组检测任务成功 (group_id={config.group_id})",
                    user_id,
                )
                return {"status": "success", "message": "分组检测任务已启动"}
            elif config.frequency.value == "scheduled":
                log_detection_action(config_id, config.device_id, "start", "failed", "定时检测已移除，请改为实时检测或抽帧检测", user_id)
                return {"status": "error", "message": "定时检测已移除，请编辑配置并改为实时检测或抽帧检测"}
            elif config.frequency.value == "manual":
                await self._create_and_start_task(config, model, db)
                log_detection_action(config_id, config.device_id, "start", "success", "启动抽帧检测任务成功", user_id)
                return {"status": "success", "message": "抽帧检测任务已启动"}
            
            # 实时检测直接启动任务
            await self._create_and_start_task(config, model, db)
            # 记录成功日志
            log_detection_action(config_id, config.device_id, "start", "success", "启动实时检测任务成功", user_id)
            return {"status": "success", "message": "检测任务已启动"}
            
        except Exception as e:
            logger.error(f"启动检测任务失败: {str(e)}")
            log_device_id = None
            if "config" in locals() and config is not None:
                log_device_id = self._log_device_id_for_config(config)
            log_detection_action(config_id, log_device_id, "start", "failed", f"启动检测任务失败: {str(e)}", user_id)
            return {"status": "error", "message": f"启动检测任务失败: {str(e)}"}
    
    # 停止特定配置的检测任务
    async def stop_detection(self, config_id: str, db: Session, remove_scheduled_jobs=True, user_id: str = None):
        """停止特定配置的检测任务"""
        # 获取设备ID
        device_id = "unknown"
        config = None
        try:
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
            if config:
                task = self.tasks.get(config_id)
                device_id = self._log_device_id_for_config(config, task)
        except Exception:
            pass
        
        # 停止检测任务
        # if config_id not in self.tasks:
        #     logger.warning(f"检测任务不存在: {config_id}")
            # return {"status": "error", "message": "检测任务不存在"}
        
        try:
            # 停止任务
            if config_id in self.tasks:
                await self.tasks[config_id].stop()
            
            # 更新数据库中的任务状态
            if remove_scheduled_jobs:
                config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
                if config:
                    config.enabled = False
                    config.updated_at = datetime.now()
                    db.commit()
            
            # 移除任务
            if config_id in self.tasks:
                del self.tasks[config_id]
            
            # 记录日志
            log_detection_action(config_id, device_id, "stop", "success", "已停止检测任务", user_id)
            
            logger.info(f"检测任务已停止: {config_id}")
            return {"status": "success", "message": "检测任务已停止"}
            
        except Exception as e:
            logger.error(f"停止检测任务失败: {e}")
            # 记录失败日志
            log_detection_action(config_id, device_id, "stop", "failed", f"停止检测任务失败: {str(e)}", user_id)
            db.rollback()
            return {"status": "error", "message": f"停止检测任务失败: {str(e)}"}
    
    # 启动所有已启用的检测任务
    async def start_all_enabled(self, db: Session):
        """启动所有已启用的检测任务"""
        enabled_configs = db.query(DetectionConfig).filter(DetectionConfig.enabled.is_(True)).all()
        
        started_count = 0
        skipped_count = 0
        
        for config in enabled_configs:
            try:
                config_mode = getattr(config, "config_mode", None) or "device"
                if config.frequency.value == "scheduled":
                    skipped_count += 1
                    logger.warning(f"跳过已废弃的定时检测配置: {config.config_id}")
                elif config_mode == "group" or config.frequency.value in ("realtime", "manual"):
                    result = await self.start_detection(config.config_id, db)
                    if result.get("status") == "success":
                        started_count += 1
            except Exception as e:
                logger.error(f"启动任务 {config.config_id} 失败: {str(e)}")
        
        logger.info(f"已启动 {started_count} 个检测任务，跳过 {skipped_count} 个废弃定时配置")
    
    # 处理检测预览WebSocket连接
    async def handle_preview(self, websocket: WebSocket, config_id: str):
        """处理检测预览WebSocket连接"""
        await websocket.accept()
        
        if config_id not in self.tasks:
            await websocket.send_json({
                "status": "error", 
                "message": "请求的检测任务不存在或未启动"
            })
            await websocket.close()
            return

        task = self.tasks[config_id]
        
        try:
            # 添加WebSocket客户端到检测任务
            task.add_client(websocket)
            
            # 发送初始连接成功消息
            await websocket.send_json({
                "status": "success",
                "message": "已连接到检测服务",
                "config_id": config_id
            })
            
            # 保持连接，直到客户端断开
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    logger.info(f"WebSocket客户端断开连接: {id(websocket)}")
                    break
                except Exception as e:
                    logger.error(f"WebSocket接收消息错误: {e}")
                    break
        except Exception as e:
            logger.error(f"WebSocket连接处理异常: {e}")
        finally:
            # 确保客户端被移除
            if config_id in self.tasks and hasattr(self.tasks[config_id], "remove_client"):
                self.tasks[config_id].remove_client(websocket)
                logger.info(f"WebSocket客户端已从检测任务移除: {config_id}")

    # 创建并启动检测任务
    async def _create_and_start_task(self, config: DetectionConfig, model: DetectionModel, db: Session, reset_enabled=True):
        """创建并启动检测任务（内部方法）"""
        config_mode = getattr(config, "config_mode", None) or "device"
        if config_mode == "group":
            return await self._create_and_start_group_task(config, model, db, reset_enabled=reset_enabled)

        config_id = config.config_id
        device_id = config.device_id
        
        # 获取设备信息
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            logger.error(f"未找到设备: {device_id}")
            raise ValueError("未找到设备")
        
        # 检查模型文件是否存在
        model_path = model.file_path
        abs_model_path = os.path.abspath(model_path)
        
        if not os.path.exists(abs_model_path):
            # 尝试在models目录中查找
            base_name = os.path.basename(model_path)
            alternative_path = os.path.join("models", base_name)
            alt_abs_path = os.path.abspath(alternative_path)
            
            if os.path.exists(alt_abs_path):
                model_path = alternative_path
            else:
                raise FileNotFoundError(f"模型文件不存在: {os.path.basename(model_path)}")
        
        if model_path not in self.models_cache:
            try:
                logger.info("预加载模型到缓存: %s", model_path)
                cached, infer_dev, is_onnx = load_detection_model(
                    model_path, model.models_type, model.is_gpu
                )
                self.models_cache[model_path] = {
                    "model": cached,
                    "infer_device": infer_dev,
                    "is_onnx": is_onnx,
                }
            except Exception as e:
                logger.error(f"预加载模型到缓存失败: {e}")
        else:
            logger.info(f"使用缓存的模型: {model_path}")
        
        # 创建检测任务
        frequency_value = config.frequency.value if hasattr(config.frequency, "value") else config.frequency
        runtime_config = extract_runtime_config(config.schedule_config)
        inference_pipeline = extract_inference_pipeline(config.schedule_config)
        task = DetectionTask(
            device_id=config.device_id,
            device_name=device.device_name,
            device_ip=device.ip_address,
            config_id=config_id,
            model_path=model_path,  # 使用可能已更新的模型路径
            confidence=config.sensitivity,  
            models_type=model.models_type,
            is_gpu=model.is_gpu,
            target_class=config.target_classes,
            save_mode=config.save_mode,
            area_coordinates=config.area_coordinates,
            device_roi=device.area_coordinates,
            stream_type=getattr(config, 'stream_type', None) or 'main',
            frequency=frequency_value,
            runtime_config=runtime_config,
            inference_pipeline=inference_pipeline,
        )
        
        if model_path in self.models_cache:
            entry = self.models_cache[model_path]
            if isinstance(entry, dict):
                task.model = entry["model"]
                task.infer_device = entry["infer_device"]
                task.is_onnx_model = entry["is_onnx"]
            else:
                task.model = entry
            task.class_names = getattr(task.model, "names", {})
            if use_ultralytics() and not task.is_onnx_model:
                import torch

                device = "cuda" if cuda_available() and model.is_gpu else "cpu"
                task.device = torch.device(device)
            logger.info(
                "使用缓存模型设置任务: %s onnx=%s",
                config_id,
                getattr(task, "is_onnx_model", is_onnx_model_path(model_path)),
            )
        
        # 设置事件循环
        task.loop = asyncio.get_event_loop()
        
        # 启动任务
        task.start()
        
        # 保存任务
        self.tasks[config_id] = task
        
        # 更新数据库中的任务状态
        if reset_enabled:
            config.enabled = True
            config.updated_at = datetime.now()
            db.commit()
        
        return task

    async def _create_and_start_group_task(self, config: DetectionConfig, model: DetectionModel, db: Session, reset_enabled=True):
        """创建并启动分组检测任务"""
        config_id = config.config_id
        group_id = config.group_id
        if not group_id:
            raise ValueError("分组检测配置缺少 group_id")

        group = db.query(DeviceGroup).filter(DeviceGroup.group_id == group_id).first()
        if not group:
            raise ValueError("未找到设备分组")

        model_path = model.file_path
        abs_model_path = os.path.abspath(model_path)
        if not os.path.exists(abs_model_path):
            base_name = os.path.basename(model_path)
            alternative_path = os.path.join("models", base_name)
            alt_abs_path = os.path.abspath(alternative_path)
            if os.path.exists(alt_abs_path):
                model_path = alternative_path
            else:
                raise FileNotFoundError(f"模型文件不存在: {os.path.basename(model_path)}")

        if model_path not in self.models_cache:
            try:
                cached, infer_dev, is_onnx = load_detection_model(
                    model_path, model.models_type, model.is_gpu
                )
                self.models_cache[model_path] = {
                    "model": cached,
                    "infer_device": infer_dev,
                    "is_onnx": is_onnx,
                }
            except Exception as e:
                logger.error(f"预加载分组检测模型失败: {e}")

        runtime_config = extract_runtime_config(config.schedule_config)
        inference_pipeline = extract_inference_pipeline(config.schedule_config)
        task = GroupDetectionTask(
            config_id=config_id,
            group_id=group_id,
            group_name=group.group_name,
            model_path=model_path,
            confidence=config.sensitivity,
            models_type=model.models_type,
            is_gpu=model.is_gpu,
            target_class=config.target_classes,
            save_mode=config.save_mode,
            group_settings=config.group_settings,
            runtime_config=runtime_config,
            stream_type=getattr(config, "stream_type", None) or "main",
            inference_pipeline=inference_pipeline,
        )

        if model_path in self.models_cache:
            entry = self.models_cache[model_path]
            if isinstance(entry, dict):
                task.model = entry["model"]
                task.infer_device = entry["infer_device"]
                task.is_onnx_model = entry["is_onnx"]
            else:
                task.model = entry
            task.class_names = getattr(task.model, "names", {})
            if use_ultralytics() and not getattr(task, "is_onnx_model", False):
                import torch

                device = "cuda" if cuda_available() and model.is_gpu else "cpu"
                task.device = torch.device(device)

        task.loop = asyncio.get_event_loop()
        task.start()
        self.tasks[config_id] = task

        if reset_enabled:
            config.enabled = True
            config.updated_at = datetime.now()
            db.commit()

        return task
    
    def _check_system_resources(self):
        """检查系统资源使用情况"""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            self.total_cpu_usage = cpu_percent
            self.total_memory_usage = memory_percent
            self.active_task_count = len([t for t in self.tasks.values() if t.thread and t.thread.is_alive()])
            
            # 记录资源使用情况
            if self.active_task_count > 0:
                logger.info(f"系统资源状态 - CPU: {cpu_percent:.1f}%, 内存: {memory_percent:.1f}%, 活跃任务: {self.active_task_count}")
            
            return cpu_percent, memory_percent
            
        except ImportError:
            return 0, 0
        except Exception as e:
            logger.error(f"检查系统资源失败: {e}")
            return 0, 0
    
    def _should_start_new_task(self):
        """判断是否应该启动新任务"""
        cpu_percent, memory_percent = self._check_system_resources()
        
        # 资源限制条件
        if cpu_percent > 85:
            logger.warning(f"CPU使用率过高({cpu_percent:.1f}%)，暂停启动新任务")
            return False
            
        if memory_percent > 90:
            logger.warning(f"内存使用率过高({memory_percent:.1f}%)，暂停启动新任务")
            return False
            
        if self.active_task_count >= self.max_concurrent_tasks:
            logger.warning(f"已达到最大并发任务数({self.max_concurrent_tasks})，暂停启动新任务")
            return False
            
        return True
    
    async def start_global_cleanup_task(self):#启动全局清理任务
        """启动全局清理任务"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._global_cleanup_worker())
            
            # 计算下次清理时间并显示
            now = datetime.now()
            next_cleanup = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now >= next_cleanup:
                next_cleanup += timedelta(days=1)
    
    async def _global_cleanup_worker(self):#全局清理工作协程，每天凌晨2点执行一次
        """全局清理工作协程，每天凌晨2点执行一次"""
        while True:
            try:
                # 计算到下一个凌晨2点的等待时间
                now = datetime.now()
                
                # 设置今天凌晨2点的时间
                target_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
                
                # 如果当前时间已经过了今天的凌晨2点，则设置为明天凌晨2点
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                # 计算等待时间（秒）
                wait_seconds = (target_time - now).total_seconds()
                
                logger.info(f"全局清理任务已调度，将在 {target_time.strftime('%Y-%m-%d %H:%M:%S')} 执行下次清理")
                
                # 等待到目标时间
                await asyncio.sleep(wait_seconds)
                
                # 执行清理任务
                await self._cleanup_all_expired_events()
                logger.info(f"全局清理任务执行完成,当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"全局清理任务错误: {e}")
                # 出错后等待1小时再重试
                await asyncio.sleep(3600)
    
    async def _cleanup_all_expired_events(self):#清理所有配置的过期事件
        """清理所有配置的过期事件"""
        start_time = datetime.now()
        try:
            logger.info("开始执行全局清理任务...")
            
            # 1. 清理检测事件
            await self._cleanup_detection_events()
            
            # 2. 清理外部数据事件
            await self._cleanup_external_events()

            # 3. 清理智能事件
            await self._cleanup_smart_events()
            
            # 4. 清理空的日期目录
            try:
                await self._cleanup_empty_directories()
            except Exception as e:
                logger.warning(f"清理空目录失败: {e}")
            
            # 计算执行时间
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"全局清理任务执行完成 - 总执行时间: {execution_time:.2f}秒")           
            
        except Exception as e:
            logger.error(f"全局清理任务失败: {e}")
    
    async def _cleanup_detection_events(self):
        """清理检测事件"""
        db = SessionLocal()
        try:
            current_time = datetime.now()
            
            # 获取所有检测配置
            configs = db.query(DetectionConfig).all()
            
            total_deleted_events = 0
            total_deleted_files = 0
            processed_configs = 0
            failed_configs = 0
            
            logger.info(f"开始清理检测事件，共有 {len(configs)} 个配置需要处理")
            
            for config in configs:
                try:
                    # 获取最大存储天数，如果为0则设置为30天
                    max_storage_days = config.max_storage_days if config.max_storage_days > 0 else 30
                    
                    # 计算过期时间点
                    expire_time = current_time - timedelta(days=max_storage_days)
                    
                    # 查询要删除的事件
                    events_to_delete = db.query(DetectionEvent).filter(
                        DetectionEvent.config_id == config.config_id,
                        DetectionEvent.created_at < expire_time
                    ).all()
                    
                    if not events_to_delete:
                        continue  # 没有过期事件，跳过
                    
                    # 删除关联的文件
                    deleted_files_count = 0
                    for event in events_to_delete:
                        # 删除缩略图文件
                        if event.thumbnail_path and Path(event.thumbnail_path).exists():
                            try:
                                Path(event.thumbnail_path).unlink()
                                deleted_files_count += 1
                            except Exception as e:
                                logger.warning(f"删除缩略图文件失败: {event.thumbnail_path}, 错误: {e}")
                        
                        # 删除视频片段文件
                        if hasattr(event, 'snippet_path') and event.snippet_path and Path(event.snippet_path).exists():
                            try:
                                Path(event.snippet_path).unlink()
                                deleted_files_count += 1
                            except Exception as e:
                                logger.warning(f"删除视频文件失败: {event.snippet_path}, 错误: {e}")
                    
                    # 删除数据库记录
                    deleted_events_count = db.query(DetectionEvent).filter(
                        DetectionEvent.config_id == config.config_id,
                        DetectionEvent.created_at < expire_time
                    ).delete()
                    
                    if deleted_events_count > 0:
                        total_deleted_events += deleted_events_count
                        total_deleted_files += deleted_files_count
                        processed_configs += 1
                        logger.info(f"配置 {config.config_id} (设备: {config.device_id}) 清理了 {deleted_events_count} 条过期事件 (>{max_storage_days}天), {deleted_files_count} 个文件")
                        
                except Exception as e:
                    failed_configs += 1
                    logger.error(f"清理配置 {config.config_id} 的过期事件失败: {e}")
                    continue
            
            # 提交所有删除操作
            if total_deleted_events > 0:
                db.commit()
            
            # 输出清理统计
            log_action(db, 'admin', 'cleanup_detection_events', 'system', f"检测事件清理完成 - 处理配置 {processed_configs}/{len(configs)} 个, 失败 {failed_configs} 个")
            logger.info(f"检测事件清理完成 - 处理配置 {processed_configs}/{len(configs)} 个, 失败 {failed_configs} 个")
            logger.info(f"检测事件删除统计: {total_deleted_events} 条记录, {total_deleted_files} 个文件")
            
        except Exception as e:
            logger.error(f"清理检测事件失败: {e}")
            if 'db' in locals():
                db.rollback()
        finally:
            if 'db' in locals():
                db.close()
    
    async def _cleanup_empty_directories(self):#清理空的存储目录
        """清理空的存储目录"""
        storage_path = Path("storage/events")
        if not storage_path.exists():
            return
        
        deleted_dirs = 0
        try:
            # 遍历所有日期目录
            for date_dir in storage_path.iterdir():
                if date_dir.is_dir():
                    # 检查设备目录
                    for device_dir in date_dir.iterdir():
                        if device_dir.is_dir() and not any(device_dir.iterdir()):
                            # 删除空的设备目录
                            device_dir.rmdir()
                            deleted_dirs += 1
                    
                    # 如果日期目录也空了，删除它
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
                        deleted_dirs += 1
            
            if deleted_dirs > 0:
                logger.info(f"清理了 {deleted_dirs} 个空目录")
                
        except Exception as e:
            logger.warning(f"清理空目录时出错: {e}")
    
    async def _cleanup_external_events(self):#清理所有外部的数据事件
        """清理所有外部的数据事件"""
        try:
            db = SessionLocal()
            current_time = datetime.now()
            
            # 外部事件保留100天
            expire_time = current_time - timedelta(days=100)
            
            # 查询要删除的外部事件（用于删除关联的文件）
            events_to_delete = db.query(ExternalEvent).filter(
                ExternalEvent.created_at < expire_time
            ).all()
            
            if not events_to_delete:
                logger.info("没有找到过期的外部数据事件")
                return
            
            deleted_files_count = 0
            deleted_events_count = 0
            
            logger.info(f"开始清理外部数据事件，共有 {len(events_to_delete)} 条过期事件需要处理")
            log_action(db, 'admin', 'cleanup_external_events', 'system', f"开始清理外部数据事件，共有 {len(events_to_delete)} 条过期事件需要处理")
            # 删除关联的图片文件
            for event in events_to_delete:
                try:
                    image_paths = []
                    
                    # 从normalized_data中查找图片路径
                    if event.normalized_data and isinstance(event.normalized_data, dict):
                        # 检查processed_images字段
                        processed_images = event.normalized_data.get('processed_images', {})
                        if isinstance(processed_images, dict):
                            # 遍历processed_images中的所有字段（如pic_data、spic_data等）
                            for field_name, image_data in processed_images.items():
                                if isinstance(image_data, dict):
                                    # 检查original_path
                                    if 'original_path' in image_data and image_data['original_path']:
                                        image_paths.append(image_data['original_path'])
                                    
                                    # 检查thumbnail_path
                                    if 'thumbnail_path' in image_data and image_data['thumbnail_path']:
                                        image_paths.append(image_data['thumbnail_path'])                       
                    
                    # 删除所有找到的图片文件
                    for image_path in set(image_paths):  # 使用set去重
                        if image_path and isinstance(image_path, str):
                            # 处理Windows路径分隔符
                            image_path = image_path.replace('\\', '/')
                            
                            # 处理相对路径和绝对路径
                            if not Path(image_path).is_absolute():
                                # 如果是相对路径，直接使用，因为通常相对于项目根目录
                                full_path = Path(image_path)
                                if not full_path.exists():
                                    # 如果直接路径不存在，尝试在常见的存储目录中查找
                                    for base_dir in ['storage', 'uploads', 'images', 'data']:
                                        full_path = Path(base_dir) / image_path
                                        if full_path.exists():
                                            break
                            else:
                                full_path = Path(image_path)
                            
                            if full_path.exists():
                                try:
                                    full_path.unlink()
                                    deleted_files_count += 1
                                    logger.debug(f"已删除外部事件图片: {full_path}")
                                except Exception as e:
                                    logger.warning(f"删除外部事件图片失败: {full_path}, 错误: {e}")
                
                except Exception as e:
                    logger.warning(f"处理外部事件文件删除失败 (事件ID: {getattr(event, 'event_id', 'unknown')}): {e}")
                    continue
            
            # 删除数据库记录
            deleted_events_count = db.query(ExternalEvent).filter(
                ExternalEvent.created_at < expire_time
            ).delete()
            
            # 提交删除操作
            if deleted_events_count > 0:
                db.commit()
                logger.info(f"外部数据事件清理完成: 删除 {deleted_events_count} 条记录 (>100天), {deleted_files_count} 个图片文件")
            else:
                logger.info("没有需要清理的外部数据事件")
                
        except Exception as e:
            logger.error(f"清理外部数据事件失败: {e}")
            if 'db' in locals():
                db.rollback()
        finally:
            if 'db' in locals():
                db.close()
    
    async def _cleanup_smart_events(self):
        """清理智能事件"""
        try:
            db = SessionLocal()
            current_time = datetime.now()
            
            # 智能事件保留7天
            expire_time = current_time - timedelta(days=7)
            
            # 查询要删除的外部事件（用于删除关联的文件）
            events_to_delete = db.query(SmartEvent).filter(
                SmartEvent.created_at < expire_time
            ).all()
            
            if not events_to_delete:
                logger.info("没有找到过期的智能事件")
                return
            
            deleted_events_count = 0
            
            logger.info(f"开始清理智能事件，共有 {len(events_to_delete)} 条过期事件需要处理")
            log_action(db, 'admin', 'cleanup_smart_events', 'system', f"开始清理智能事件，共有 {len(events_to_delete)} 条过期事件需要处理")
           
            # 删除数据库记录
            deleted_events_count = db.query(SmartEvent).filter(
                SmartEvent.created_at < expire_time
            ).delete()
            
            # 提交删除操作
            if deleted_events_count > 0:
                db.commit()
                logger.info(f"智能事件清理完成: 删除 {deleted_events_count} 条记录 (>30天)")
            else:
                logger.info("没有需要清理的智能事件")
                
        except Exception as e:
            logger.error(f"清理智能事件失败: {e}")
            if 'db' in locals():
                db.rollback()
        finally:
            if 'db' in locals():
                db.close()
            
# 创建检测服务器实例
detection_server = DetectionServer()

# 应用程序生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理"""
    logger.info("检测服务器启动中...")
    
    # 创建数据库表（如果不存在）
    Base.metadata.create_all(bind=engine)

    # 2. 启动设备监控服务
    try:
        device_monitor.start()
    except Exception as e:
        logger.error(f"启动设备监控服务失败: {e}")

    # 3. 启动FFmpeg解码器线程池
    # try:
    #     logger.info("启动FFmpeg解码器线程池")
    # except Exception as e:
    #     logger.error(f"启动FFmpeg解码器线程池失败: {e}")

    # 3.启动数据推送服务
    try:
        data_pusher.startup_push_service()
    except Exception as e:
        logger.error(f"启动数据推送服务失败: {e}")

    # 4. 启动时初始化事件订阅管理器
    try:
        await smart_schemer.initialize()
    except Exception as e:
        logger.error(f"事件订阅管理器初始化失败: {e}")

    # 5. 启动检测服务
    try:
        db = SessionLocal()
        await detection_server.start_all_enabled(db)
        db.close()
    except Exception as e:
        logger.error(f"启动检测服务失败: {e}")

    # 6. 启动复合告警规则调度器（评估 + 推送）
    try:
        alert_rule_scheduler.start()
    except Exception as e:
        logger.error(f"启动复合告警规则调度器失败: {e}")

    # 7. 启动全局清理任务
    try:
        await detection_server.start_global_cleanup_task()
    except Exception as e:
        logger.error(f"启动全局清理任务失败: {e}")

    yield
    
    # 关闭服务（顺序与启动相反）
    logger.info("检测服务器关闭中...")
    
    # 1. 停止全局清理任务
    try:
        if detection_server.cleanup_task:
            detection_server.cleanup_task.cancel()
    except Exception as e:
        logger.error(f"停止全局清理任务失败: {e}")
    
    # 2. 停止复合告警规则调度器
    try:
        alert_rule_scheduler.stop()
    except Exception as e:
        logger.error(f"停止复合告警规则调度器失败: {e}")

    # 3. 先停设备监控（探活任务可能耗时很长，且 shutdown 不应阻塞在 wait=True）
    try:
        device_monitor.stop()
    except Exception as e:
        logger.error(f"停止设备监控服务失败: {e}")

    # 4. 停止检测任务（单任务最多约 15s）
    for config_id, task in list(detection_server.tasks.items()):
        try:
            await asyncio.wait_for(task.stop(), timeout=20.0)
        except asyncio.TimeoutError:
            logger.warning(f"停止检测任务 {config_id} 超时，继续关闭")
        except Exception as e:
            logger.error(f"停止检测任务 {config_id} 失败: {e}")
    
    # 5. 关闭事件订阅管理器
    try:
        await asyncio.wait_for(smart_schemer.shutdown(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("关闭事件订阅管理器超时，继续关闭")
    except Exception as e:
        logger.error(f"关闭事件订阅管理器失败: {e}")
    
    # 6. 停止数据推送服务
    try:
        data_pusher.shutdown_push_service()
    except Exception as e:
        logger.error(f"停止数据推送服务失败: {e}")

    logger.info("所有服务已停止")

# 创建FastAPI应用
app = FastAPI(
    title="检测服务器",
    description="用于管理对象检测任务的API",
    version="1.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动检测任务API
@app.post("/api/v2/detection/{config_id}/start", tags=["检测任务"])
async def start_detection_api(config_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """启动检测任务API"""
    log_action(db, current_user.user_id, 'start_detection', config_id, f"启动检测任务: {config_id}")
    return await detection_server.start_detection(config_id, db, current_user.user_id)

# 停止检测任务API
@app.post("/api/v2/detection/{config_id}/stop", tags=["检测任务"])
async def stop_detection_api(config_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """停止检测任务API"""
    log_action(db, current_user.user_id, 'stop_detection', config_id, f"停止检测任务: {config_id}")
    return await detection_server.stop_detection(config_id, db, remove_scheduled_jobs=True, user_id=current_user.user_id)

# 获取所有检测任务的状态API
@app.get("/api/v2/detection/status", tags=["检测任务"])
async def get_detection_status():
    """获取所有检测任务的状态"""
    tasks_status = {}
    for config_id, task in detection_server.tasks.items():
        tasks_status[config_id] = {
            "device_id": getattr(task, "device_id", None),
            "config_mode": getattr(task, "config_mode", "device"),
            "group_id": getattr(task, "group_id", None),
            "last_device_id": getattr(task, "last_device_id", None),
            "is_running": task.thread is not None and task.thread.is_alive(),
            "connected": getattr(task, "connected", False),
            "clients_count": len(getattr(task, "clients", [])),
        }
    
    return {
        "status": "success",
        "tasks": tasks_status,
        "total_tasks": len(tasks_status)
    }

# 手动清理过期事件API
@app.post("/api/v2/detection/cleanup-expired-events", tags=["清理事件"])
async def cleanup_expired_events_api(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """手动清理过期检测事件和外部事件"""
    try:
        log_action(db, current_user.user_id, 'cleanup_expired_events', 'system', "手动清理过期事件")
        
        # 执行完整的清理操作（包括检测事件和外部事件）
        await detection_server._cleanup_all_expired_events()
        
        return {
            "status": "success",
            "message": "过期事件清理完成（包括检测事件和外部事件）"
        }
    except Exception as e:
        logger.error(f"手动清理过期事件失败: {e}")
        return {
            "status": "error",
            "message": f"清理失败: {str(e)}"
        }

# 手动清理外部事件API
@app.post("/api/v2/detection/cleanup-external-events", tags=["清理事件"])
async def cleanup_external_events_api(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """手动清理外部数据事件"""
    try:
        log_action(db, current_user.user_id, 'cleanup_external_events', 'system', "手动清理外部数据事件")
        
        # 执行外部事件清理
        await detection_server._cleanup_external_events()
        
        return {
            "status": "success",
            "message": "外部数据事件清理完成"
        }
    except Exception as e:
        logger.error(f"手动清理外部事件失败: {e}")
        return {
            "status": "error",
            "message": f"清理失败: {str(e)}"
        }

# 获取清理任务状态API
@app.get("/api/v2/detection/cleanup-status", tags=["清理事件"])
async def get_cleanup_status_api(current_user: User = Depends(get_current_user)):
    """获取清理任务状态"""
    try:
        now = datetime.now()
        
        # 计算下次清理时间
        next_cleanup = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now >= next_cleanup:
            next_cleanup += timedelta(days=1)
        
        # 检查清理任务状态
        cleanup_task_running = (detection_server.cleanup_task is not None and 
                               not detection_server.cleanup_task.done())
        
        # 获取数据库中的事件统计
        db = SessionLocal()
        try:
            # 统计检测事件
            total_detection_events = db.query(DetectionEvent).count()
            expired_detection_events = 0
            
            # 统计各配置的过期事件
            configs = db.query(DetectionConfig).all()
            for config in configs:
                max_storage_days = config.max_storage_days if config.max_storage_days > 0 else 30
                expire_time = now - timedelta(days=max_storage_days)
                count = db.query(DetectionEvent).filter(
                    DetectionEvent.config_id == config.config_id,
                    DetectionEvent.created_at < expire_time
                ).count()
                expired_detection_events += count
            
            # 统计外部事件
            total_external_events = db.query(ExternalEvent).count()
            expire_time_external = now - timedelta(days=100)
            expired_external_events = db.query(ExternalEvent).filter(
                ExternalEvent.created_at < expire_time_external
            ).count()
            
        finally:
            db.close()
        
        return {
            "status": "success",
            "data": {
                "cleanup_task_running": cleanup_task_running,
                "next_cleanup_time": next_cleanup.strftime('%Y-%m-%d %H:%M:%S'),
                "current_time": now.strftime('%Y-%m-%d %H:%M:%S'),
                "time_until_next_cleanup": str(next_cleanup - now).split('.')[0],  # 去掉微秒
                "statistics": {
                    "detection_events": {
                        "total": total_detection_events,
                        "expired": expired_detection_events
                    },
                    "external_events": {
                        "total": total_external_events,
                        "expired": expired_external_events,
                        "retention_days": 100
                    }
                }
            }
        }
    except Exception as e:
        logger.error(f"获取清理任务状态失败: {e}")
        return {
            "status": "error",
            "message": f"获取状态失败: {str(e)}"
        }

# 获取系统资源状态API
@app.get("/api/v2/detection/system-status", tags=["清理事件"])
async def get_system_status_api(current_user: User = Depends(get_current_user)):
    """获取系统资源状态"""
    try:
        # 检查系统资源
        detection_server._check_system_resources()
        
        # 获取任务状态
        tasks_status = {}
        for config_id, task in detection_server.tasks.items():
            tasks_status[config_id] = {
                "device_id": getattr(task, "device_id", None),
                "config_mode": getattr(task, "config_mode", "device"),
                "is_running": task.thread is not None and task.thread.is_alive(),
                "connected": getattr(task, "connected", False),
                "clients_count": len(getattr(task, "clients", [])),
                "use_ffmpeg_decoder": hasattr(task, "ffmpeg_decoder") and task.ffmpeg_decoder is not None,
                "skip_frame_count": getattr(task, "skip_frame_count", 5),
            }
        
        return {
            "status": "success",
            "data": {
                "system_resources": {
                    "cpu_usage": detection_server.total_cpu_usage,
                    "memory_usage": detection_server.total_memory_usage,
                    "active_tasks": detection_server.active_task_count,
                    "max_concurrent_tasks": detection_server.max_concurrent_tasks
                },
                "tasks": tasks_status,
                "total_tasks": len(tasks_status),
                "gpu_available": cuda_available(),
                "gpu_device_count": (
                    __import__("torch").cuda.device_count() if cuda_available() else 0
                ),
            }
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {
            "status": "error",
            "message": f"获取系统状态失败: {str(e)}"
        }

# 加载模型API端点
@app.post("/api/v2/model/load", tags=["检测任务"])
async def load_model_api(model_data: dict):
    """加载模型 API：校验 .pt / .onnx 并返回类别"""
    model_path = model_data.get("model_path")
    if not model_path:
        raise HTTPException(status_code=400, detail="缺少 model_path")

    models_type = model_data.get("models_type")
    parameters = model_data.get("parameters") or {}
    try:
        classes = load_yolo_model_classes(
            model_path,
            models_type=models_type,
            parameters=parameters,
        )
        return {
            "status": "success",
            "message": "模型加载成功",
            "classes": classes,
        }
    except Exception as e:
        logger.error(f"加载模型失败: {e}")
        raise HTTPException(status_code=400, detail=f"加载模型失败: {e}")

# 检测预览WebSocket端点
@app.websocket("/ws/detection/preview/{config_id}")
async def detection_preview_websocket(websocket: WebSocket, config_id: str): # 检测预览WebSocket端点
    """检测预览WebSocket端点"""
    await websocket.accept()
    
    # 检查检测任务是否存在
    if config_id not in detection_server.tasks:
        # 先尝试启动任务
        logger.info(f"WebSocket请求的检测任务不存在，尝试启动: {config_id}")
        db = SessionLocal()
        result = await detection_server.start_detection(config_id, db)
        db.close()
        
        if result["status"] == "error" or config_id not in detection_server.tasks:
            # 启动失败，发送错误消息并关闭连接
            await websocket.send_json({
                "status": "error", 
                "message": result.get("message") or "请求的检测任务不存在或无法启动"
            })
            await websocket.close()
            return
    
    # 任务存在或已成功启动
    task = detection_server.tasks[config_id]

    try:
        # 发送初始连接成功消息
        await websocket.send_json({
            "status": "success",
            "message": "已连接到检测服务",
            "config_id": config_id,
            "device_id": getattr(task, "last_device_id", None) or task.device_id,
            "group_id": getattr(task, "group_id", None),
            "config_mode": getattr(task, "config_mode", "device"),
        })
        
        # 添加WebSocket客户端到检测任务
        task.add_client(websocket)
        logger.info(f"WebSocket客户端已添加到检测任务: {config_id}")
        
        # 保持连接，直到客户端断开
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"WebSocket客户端断开连接: {id(websocket)}")
                break
            except Exception as e:
                logger.error(f"WebSocket接收消息错误: {e}")
                break
    except Exception as e:
        logger.error(f"WebSocket连接处理异常: {e}")
    finally:
        # 确保客户端被移除
        if config_id in detection_server.tasks and hasattr(detection_server.tasks[config_id], "remove_client"):
            detection_server.tasks[config_id].remove_client(websocket)
            logger.info(f"WebSocket客户端已从检测任务移除: {config_id}")

from api.alert_rule_detect import router as alert_rule_detect_router
app.include_router(alert_rule_detect_router, prefix="/api/v2")

if os.path.isdir("storage"):
    app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# 添加数据推送相关的API接口
from api.data_push import router as data_push_router
app.include_router(data_push_router, prefix="/api/v2")

# 添加RTSP相关的API接口
from api.rtsp_server import router as rtsp_router
app.include_router(rtsp_router, prefix="/ws")

# 事件订阅、设备监控运行时 API 已挂载于 edge_bootstrap → /api/v1（serve_unified 单进程）