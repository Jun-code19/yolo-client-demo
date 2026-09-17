"""
数据推送模块 - 支持HTTP/HTTPS、TCP和MQTT多种推送方式
此模块设计为独立服务，可由系统中任何组件调用
"""

import json
import logging
import queue
import socket
import ssl
import threading
import time
import uuid
import base64
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import cv2
import requests
import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session
import numpy as np

from src.database import SessionLocal, DataPushConfig, PushMethod, DataPushLog

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataPusher:
    """数据推送器，负责将数据推送到外部系统"""
    
    def __init__(self):
        self.push_queue = queue.Queue()
        self.running = False
        self.push_thread = None
        self.push_configs = {}  # 存储推送配置信息 {push_id: config}
        self.push_tasks = {}    # 存储正在处理的推送任务
        self.push_stats = {}    # 存储推送统计信息 {push_id: {success: 0, fail: 0, last_success: None}}
        self.lock = threading.Lock()
    
    def start(self):
        """启动推送线程"""
        if not self.running:
            self.running = True
            self.push_thread = threading.Thread(target=self._process_queue)
            self.push_thread.daemon = True
            self.push_thread.start()
    
    def stop(self):
        """停止推送线程"""
        self.running = False
        if self.push_thread:
            self.push_thread.join(timeout=5)
    
    def load_push_configs(self, db=None):
        """从数据库加载所有启用的推送配置"""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
            
        try:
            configs = db.query(DataPushConfig).filter(DataPushConfig.enabled == True).all()
            with self.lock:
                self.push_configs = {config.push_id: config for config in configs}
                # 初始化统计信息
                for push_id in self.push_configs:
                    if push_id not in self.push_stats:
                        self.push_stats[push_id] = {"success": 0, "fail": 0, "last_success": None}
            logger.info(f"已加载 {len(self.push_configs)} 个推送配置")
        except Exception as e:
            logger.error(f"加载推送配置失败: {e}")
        finally:
            if close_db:
                db.close()
    
    def reload_push_config(self, push_id, db=None):
        """重新加载单个推送配置"""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
            
        try:
            config = db.query(DataPushConfig).filter(DataPushConfig.push_id == push_id).first()
            if config:
                with self.lock:
                    self.push_configs[push_id] = config
                    if push_id not in self.push_stats:
                        self.push_stats[push_id] = {"success": 0, "fail": 0, "last_success": None}
                logger.info(f"已重新加载推送配置: {push_id}")
            else:
                # 如果配置不存在，则从缓存中移除
                with self.lock:
                    if push_id in self.push_configs:
                        del self.push_configs[push_id]
                    if push_id in self.push_stats:
                        del self.push_stats[push_id]
                logger.info(f"推送配置已删除: {push_id}")
        except Exception as e:
            logger.error(f"重新加载推送配置失败: {e}")
        finally:
            if close_db:
                db.close()
    
    def get_push_stats(self):
        """获取推送统计信息（JSON 可序列化）"""
        with self.lock:
            result = {}
            for push_id, stat in self.push_stats.items():
                last_success = stat.get("last_success")
                result[push_id] = {
                    "success": stat.get("success", 0),
                    "fail": stat.get("fail", 0),
                    "last_success": last_success.isoformat() if last_success else None,
                }
            return result

    @staticmethod
    def _target_summary(config) -> str:
        method = config.push_method.value if hasattr(config.push_method, "value") else str(config.push_method)
        if method in ("http", "https"):
            return config.http_url or ""
        if method == "tcp":
            return f"{config.tcp_host}:{config.tcp_port}"
        if method == "mqtt":
            return f"{config.mqtt_broker}:{config.mqtt_port}/{config.mqtt_topic}"
        return method

    @staticmethod
    def _payload_preview(data: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"value": str(data)[:200]}
        preview = {}
        for idx, (key, value) in enumerate(data.items()):
            if idx >= limit:
                preview["_truncated"] = True
                break
            if isinstance(value, (str, int, float, bool)) or value is None:
                text = "" if value is None else str(value)
                preview[str(key)] = text[:120]
            elif isinstance(value, (list, dict)):
                preview[str(key)] = f"<{type(value).__name__} len={len(value)}>"
            else:
                preview[str(key)] = type(value).__name__
        return preview

    def record_push_log(
        self,
        config,
        success: bool,
        message: str = "",
        duration_ms: int = 0,
        tags: Optional[List[str]] = None,
        payload_preview: Optional[Dict[str, Any]] = None,
        is_test: bool = False,
    ) -> None:
        """写入推送执行记录"""
        db = SessionLocal()
        try:
            method = config.push_method.value if hasattr(config.push_method, "value") else str(config.push_method)
            row = DataPushLog(
                log_id=str(uuid.uuid4()),
                push_id=config.push_id,
                push_name=config.push_name,
                push_method=method,
                status="success" if success else "failure",
                target_summary=self._target_summary(config),
                message=(message or "")[:2000],
                tags=list(tags or config.tags or []),
                config_id=config.config_id,
                duration_ms=duration_ms or None,
                payload_preview=payload_preview,
                is_test=is_test,
                created_at=datetime.now(),
            )
            db.add(row)
            db.commit()
        except Exception as exc:
            logger.error(f"写入推送记录失败: {exc}")
            db.rollback()
        finally:
            db.close()
    
    def push_data(self, data: Dict[str, Any], image=None, tags: List[str] = None, config_id: str = None):
        """将数据放入推送队列
        
        Args:
            data: 要推送的数据
            image: 可选的图像数据
            tags: 标签列表，用于筛选适用的推送配置
            config_id: 可选的配置ID，用于兼容现有代码
        """

        # 确保数据可以被JSON序列化
        serializable_data = self._ensure_json_serializable(data)
        
        # 处理图像数据
        serializable_image = None
        if image is not None:
            if isinstance(image, np.ndarray):
                # 如果是OpenCV图像，进行编码
                _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 70])
                serializable_image = base64.b64encode(buffer).decode('utf-8')
            elif isinstance(image, bytes):
                # 如果是二进制数据，进行Base64编码
                serializable_image = base64.b64encode(image).decode('utf-8')
            elif isinstance(image, str) and image.startswith('data:image'):
                # 如果已经是base64编码的数据URI，直接使用
                serializable_image = image
        
        # 确保标签列表可序列化
        serializable_tags = None
        if tags:
            serializable_tags = [str(tag) for tag in tags]
        
        with self.lock:
            # 根据标签和配置ID筛选推送配置
            push_configs = []
            
            if config_id:
                # 兼容现有代码，根据配置ID筛选
                push_configs.extend([
                    config for config in self.push_configs.values() 
                    if config.config_id == config_id and config.enabled
                ])
            
            if serializable_tags:
                # 根据标签筛选
                for config in self.push_configs.values():
                    if config.enabled and config.tags:
                        # 如果配置的标签与传入的标签有交集
                        if set(serializable_tags).intersection(set(config.tags)):
                            # 避免重复添加
                            if config not in push_configs:
                                push_configs.append(config)
        
        for config in push_configs:
            # 检查是否需要间隔推送
            can_push = True
            if config.push_interval > 0 and config.last_push_time:
                now = datetime.now()
                time_diff = (now - config.last_push_time).total_seconds()
                if time_diff < config.push_interval:
                    can_push = False
            
            if can_push:
                # 为每个推送配置创建一个任务并放入队列
                push_task = {
                    "push_id": config.push_id,
                    "push_method": config.push_method.value,
                    "data": serializable_data,
                    "timestamp": datetime.now().isoformat(),
                    "retry_count": 0,
                    "max_retries": config.retry_count
                }
                
                # 如果包含图像且配置要求包含图像
                if serializable_image is not None and config.include_image:
                    push_task["image"] = serializable_image
                
                self.push_queue.put(push_task)
                logger.debug(f"数据已加入推送队列: {config.push_id}")
    
    def _process_queue(self):
        """处理推送队列的线程函数"""
        while self.running:
            try:
                if self.push_queue.empty():
                    time.sleep(0.1)
                    continue
                
                task = self.push_queue.get(timeout=1)
                push_id = task["push_id"]
                
                with self.lock:
                    # 获取推送配置
                    config = self.push_configs.get(push_id)
                    if not config:
                        logger.warning(f"未找到推送配置: {push_id}")
                        self.push_queue.task_done()
                        continue
                
                # 根据推送方式调用相应的推送函数
                success = False
                error_message = ""
                started = time.time()
                try:
                    if config.push_method == PushMethod.http or config.push_method == PushMethod.https:
                        success, error_message = self._push_http(config, task["data"], task.get("image"))
                    elif config.push_method == PushMethod.tcp:
                        success, error_message = self._push_tcp(config, task["data"], task.get("image"))
                    elif config.push_method == PushMethod.mqtt:
                        success, error_message = self._push_mqtt(config, task["data"], task.get("image"))

                    duration_ms = int((time.time() - started) * 1000)
                    preview = self._payload_preview(task.get("data") or {})
                    self.record_push_log(
                        config,
                        success,
                        message=error_message or ("推送成功" if success else "推送失败"),
                        duration_ms=duration_ms,
                        payload_preview=preview,
                    )

                    # 更新统计信息
                    with self.lock:
                        if success:
                            self.push_stats[push_id]["success"] += 1
                            self.push_stats[push_id]["last_success"] = datetime.now()
                            # 更新最后推送时间
                            db = SessionLocal()
                            try:
                                db_config = db.query(DataPushConfig).filter(DataPushConfig.push_id == push_id).first()
                                if db_config:
                                    db_config.last_push_time = datetime.now()
                                    db.commit()
                            except Exception as e:
                                logger.error(f"更新推送时间失败: {e}")
                                db.rollback()
                            finally:
                                db.close()
                        else:
                            self.push_stats[push_id]["fail"] += 1
                            logger.info(f"推送失败:{push_id}, 数据:{task['data']}")

                except Exception as e:
                    logger.error(f"推送数据时出错: {e}")
                    duration_ms = int((time.time() - started) * 1000)
                    self.record_push_log(
                        config,
                        False,
                        message=str(e),
                        duration_ms=duration_ms,
                        payload_preview=self._payload_preview(task.get("data") or {}),
                    )
                    with self.lock:
                        self.push_stats[push_id]["fail"] += 1
                
                finally:
                    self.push_queue.task_done()
            
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"推送处理线程异常: {e}")
                time.sleep(1)  # 避免CPU占用过高
    
    def _push_http(self, config, data, image=None):
        """通过HTTP/HTTPS推送数据，返回 (success, message)"""
        try:
            url = config.http_url
            if not url:
                return False, "HTTP URL 未配置"

            post_data = data.copy()
            if image is not None:
                post_data["image"] = image

            headers = {}
            if config.http_headers:
                headers = dict(config.http_headers)
            headers["Content-Type"] = "application/json"

            response = requests.request(
                method=config.http_method,
                url=url,
                json=post_data,
                headers=headers,
                timeout=3,
            )

            if 200 <= response.status_code < 300:
                return True, f"HTTP {response.status_code}"
            return False, f"HTTP {response.status_code}: {(response.text or '')[:300]}"

        except requests.exceptions.RequestException as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def _push_tcp(self, config, data, image=None):
        """通过TCP推送数据，返回 (success, message)"""
        try:
            host = config.tcp_host
            port = config.tcp_port

            if not host or not port:
                return False, "TCP 主机或端口未配置"

            send_data = data.copy()
            if image is not None:
                send_data["image"] = image

            json_data = json.dumps(send_data) + "\n"

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(10)
                sock.connect((host, port))
                sock.sendall(json_data.encode("utf-8"))
            return True, "TCP 发送成功"

        except socket.error as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def _push_mqtt(self, config, data, image=None):
        """通过MQTT推送数据，返回 (success, message)"""
        try:
            broker = config.mqtt_broker
            port = config.mqtt_port
            topic = config.mqtt_topic
            client_id = config.mqtt_client_id or f"detector-{uuid.uuid4()}"

            if not broker or not topic:
                return False, "MQTT 代理或主题未配置"

            send_data = data.copy()
            if image is not None:
                send_data["image"] = image

            json_data = json.dumps(send_data)
            client = mqtt.Client(client_id=client_id)

            if config.mqtt_username and config.mqtt_password:
                client.username_pw_set(config.mqtt_username, config.mqtt_password)

            if config.mqtt_use_tls:
                client.tls_set(
                    ca_certs=None,
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                    ciphers=None,
                )

            client.connect(broker, port=port, keepalive=60)
            result = client.publish(topic, json_data, qos=1)
            client.disconnect()

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True, "MQTT 发布成功"
            return False, f"MQTT 错误码: {result.rc}"

        except Exception as e:
            return False, str(e)

    def _ensure_json_serializable(self, data):
        """确保数据可以被JSON序列化"""
        if data is None:
            return None
        
        if isinstance(data, (str, int, float, bool)):
            return data
        
        if isinstance(data, bytes):
            # 将二进制数据转换为base64字符串
            return base64.b64encode(data).decode('utf-8')
        
        if isinstance(data, datetime):
            # 将datetime转换为ISO格式字符串
            return data.isoformat()
        
        if isinstance(data, list):
            # 递归处理列表的每个元素
            return [self._ensure_json_serializable(item) for item in data]
        
        if isinstance(data, dict):
            # 递归处理字典的每个值
            result = {}
            for key, value in data.items():
                # 确保键是字符串
                string_key = str(key)
                result[string_key] = self._ensure_json_serializable(value)
            return result
        
        if isinstance(data, np.ndarray):
            # 处理numpy数组
            return data.tolist()
        
        # 其他类型转换为字符串
        return str(data)

    def startup_push_service(self): # 启动时加载推送配置
        """启动时加载推送配置"""
        db = SessionLocal()
        try:
            self.load_push_configs(db)
            self.start()
        finally:
            db.close()

    def shutdown_push_service(self): # 停止时关闭推送服务
        """关闭推送服务"""
        self.stop()

# 创建全局推送器实例
data_pusher = DataPusher()