from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import logging
import time

from src.database import get_db, DataPushConfig, PushMethod, DetectionConfig, DataPushLog
from api.auth import get_current_user, User
from api.logger import log_action
# 导入独立的数据推送模块
from src.data_pusher import data_pusher

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data_push", tags=["数据推送"])

# 推送服务运行时状态
push_configs = {}  # 存储所有活跃的推送配置
push_stats = {}    # 存储推送统计信息

# Pydantic模型
class PushDataBase(BaseModel):
    push_name: str
    push_method: str
    config_id: str
    tags: List[str]
    http_url: str
    http_method: str
    tcp_host: str
    tcp_port: int
    mqtt_broker: str
    mqtt_port: int
    mqtt_topic: str
    mqtt_username: str
    mqtt_password: str
    mqtt_use_tls: bool
    include_image: bool

class PushCreate(PushDataBase):
    pass

class PushUpdate(PushDataBase):
    push_name: Optional[str] = None
    push_method: Optional[str] = None
    config_id: Optional[str] = None
    tags: Optional[List[str]] = None
    http_url: Optional[str] = None
    http_method: Optional[str] = None
    tcp_host: Optional[str] = None
    tcp_port: Optional[int] = None
    mqtt_broker: Optional[str] = None
    mqtt_port: Optional[int] = None
    mqtt_topic: Optional[str] = None
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_use_tls: Optional[bool] = None
    include_image: Optional[bool] = None
    enabled: Optional[bool] = None

class PushResponse(BaseModel):
    push_id: str
    push_name: str
    config_id: str
    tags: List[str]
    push_method: str
    http_url: str
    http_method: str
    tcp_host: str
    tcp_port: int
    mqtt_broker: str
    mqtt_port: int
    mqtt_topic: str
    mqtt_username: str
    mqtt_password: str
    mqtt_use_tls: bool
    include_image: bool
    created_at: datetime
    last_push_time: datetime

@router.get("/stats")
async def get_push_stats():
    """获取所有数据推送的统计信息"""
    return {"status": "success", "data": data_pusher.get_push_stats()}


@router.get("/logs")
async def list_push_logs(
    push_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """查询推送执行记录"""
    try:
        query = db.query(DataPushLog)
        if push_id:
            query = query.filter(DataPushLog.push_id == push_id)
        if status in ("success", "failure"):
            query = query.filter(DataPushLog.status == status)

        total = query.count()
        rows = (
            query.order_by(DataPushLog.created_at.desc())
            .offset(skip)
            .limit(min(limit, 200))
            .all()
        )
        return {
            "status": "success",
            "data": [
                {
                    "log_id": row.log_id,
                    "push_id": row.push_id,
                    "push_name": row.push_name,
                    "push_method": row.push_method,
                    "status": row.status,
                    "target_summary": row.target_summary,
                    "message": row.message,
                    "tags": row.tags or [],
                    "config_id": row.config_id,
                    "duration_ms": row.duration_ms,
                    "payload_preview": row.payload_preview,
                    "is_test": row.is_test,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ],
            "total": total,
        }
    except Exception as e:
        logger.error(f"查询推送记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询推送记录失败: {str(e)}")

@router.get("/overview")
async def get_push_overview(db: Session = Depends(get_db)):
    """获取推送配置概览统计"""
    try:
        # 总配置数
        total_configs = db.query(DataPushConfig).count()
        
        # 启用的配置数
        enabled_configs = db.query(DataPushConfig).filter(DataPushConfig.enabled == True).count()
        
        # 各种推送方式的数量
        http_count = db.query(DataPushConfig).filter(DataPushConfig.push_method.in_([PushMethod.http, PushMethod.https])).count()
        tcp_count = db.query(DataPushConfig).filter(DataPushConfig.push_method == PushMethod.tcp).count()
        mqtt_count = db.query(DataPushConfig).filter(DataPushConfig.push_method == PushMethod.mqtt).count()
        
        # 最近推送统计（从内存统计中获取）
        push_stats = data_pusher.get_push_stats()
        total_success = sum(stat.get('success', 0) for stat in push_stats.values())
        total_failures = sum(stat.get('fail', 0) for stat in push_stats.values())
        
        return {
            "status": "success",
            "data": {
                "total_configs": total_configs,
                "enabled_configs": enabled_configs,
                "disabled_configs": total_configs - enabled_configs,
                "method_stats": {
                    "http": http_count,
                    "tcp": tcp_count,
                    "mqtt": mqtt_count
                },
                "push_stats": {
                    "total_success": total_success,
                    "total_failures": total_failures,
                    "success_rate": round((total_success / (total_success + total_failures)) * 100, 2) if (total_success + total_failures) > 0 else 0
                }
            }
        }
        
    except Exception as e:
        logger.error(f"获取推送概览统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取推送概览统计失败: {str(e)}")

@router.post("/reload/{push_id}")
async def reload_push_config(push_id: str, db: Session = Depends(get_db)):
    """重新加载指定的推送配置"""
    return data_pusher.reload_push_config(push_id, db)

@router.post("/create")
async def create_push_config(pushdata: PushCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): # 创建新的数据推送配置
    """创建新的数据推送配置"""
    try:
        # 验证推送方法
        try:
            method = PushMethod(pushdata.push_method.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的推送方法: {pushdata.push_method}")

        # 检查检测配置是否存在（如果指定了）
        if pushdata.config_id:
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == pushdata.config_id).first()
            if not config:
                raise HTTPException(status_code=404, detail=f"未找到检测配置: {pushdata.config_id}")
        else:
            pushdata.config_id = None

        # 根据推送方法验证必要的参数
        if method == PushMethod.http or method == PushMethod.https:
            if not pushdata.http_url:    
                raise HTTPException(status_code=400, detail="HTTP/HTTPS推送需要URL")
        elif method == PushMethod.tcp:
            if not pushdata.tcp_host or not pushdata.tcp_port:
                raise HTTPException(status_code=400, detail="TCP推送需要主机和端口")
        elif method == PushMethod.mqtt:
            if not pushdata.mqtt_broker or not pushdata.mqtt_topic:
                raise HTTPException(status_code=400, detail="MQTT推送需要代理和主题")

        # 创建新的推送配置
        push_config = DataPushConfig(
            push_name=pushdata.push_name,
            config_id=pushdata.config_id,  # 现在可以为空
            tags=pushdata.tags or [],  # 添加标签
            push_method=method,
            http_url=pushdata.http_url,
            http_method=pushdata.http_method,
            tcp_host=pushdata.tcp_host,
            tcp_port=pushdata.tcp_port,
            mqtt_broker=pushdata.mqtt_broker,
            mqtt_port=pushdata.mqtt_port,
            mqtt_topic=pushdata.mqtt_topic,
            mqtt_username=pushdata.mqtt_username,
            mqtt_password=pushdata.mqtt_password,
            mqtt_use_tls=pushdata.mqtt_use_tls,
            include_image=pushdata.include_image,
            http_headers={} if method in [PushMethod.http, PushMethod.https] else None
        )

        db.add(push_config)
        db.commit()
        db.refresh(push_config)

        # 记录创建操作
        log_action(db, current_user.user_id, 'create_data_push', push_config.push_id, f"创建数据推送配置: {push_config.push_name}")

        # 重新加载推送配置
        data_pusher.reload_push_config(push_config.push_id, db)

        return {
            "status": "success",
            "message": "推送配置已创建",
            "push_id": push_config.push_id
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"创建推送配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建推送配置失败: {str(e)}")

@router.get("/list")
async def list_push_configs(
    config_id: str = None, 
    tag: str = None,
    method: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
): # 获取推送配置列表，支持按配置ID、标签、推送方式筛选
    """获取推送配置列表，支持按配置ID、标签、推送方式筛选（分页）"""
    try:
        query = db.query(DataPushConfig)
        
        # 根据配置ID筛选
        if config_id:
            query = query.filter(DataPushConfig.config_id == config_id)
        
        # 根据标签筛选
        if tag:
            query = query.filter(DataPushConfig.tags.any(tag))
        
        # 根据推送方式筛选
        if method:
            try:
                push_method = PushMethod(method.lower())
                query = query.filter(DataPushConfig.push_method == push_method)
            except ValueError:
                # 忽略无效的推送方式
                pass
        
        # 获取总数
        total_count = query.count()
        
        # 分页查询
        configs = query.order_by(DataPushConfig.created_at.desc()).offset(skip).limit(limit).all()
        return {
            "status": "success",
            "data": [
                {
                    "push_id": config.push_id,
                    "push_name": config.push_name,
                    "config_id": config.config_id,
                    "tags": config.tags,  # 添加标签
                    "push_method": config.push_method.value,
                    "enabled": config.enabled,
                    "http_url": config.http_url,
                    "http_method": config.http_method,
                    "tcp_host": config.tcp_host,
                    "tcp_port": config.tcp_port,
                    "mqtt_broker": config.mqtt_broker,
                    "mqtt_port": config.mqtt_port,
                    "mqtt_topic": config.mqtt_topic,
                    "include_image": config.include_image,
                    "created_at": config.created_at.isoformat() if config.created_at else None,
                    "last_push_time": config.last_push_time.isoformat() if config.last_push_time else None
                }
                for config in configs
            ],
            "total": total_count
        }
    except Exception as e:
        logger.error(f"获取推送配置列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取推送配置列表失败: {str(e)}")

@router.put("/{push_id}")
async def update_push_config(push_id: str, pushdata: PushUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): # 更新推送配置
    """更新推送配置"""
    try:
        # 查找推送配置
        push_config = db.query(DataPushConfig).filter(DataPushConfig.push_id == push_id).first()
        if not push_config:
            raise HTTPException(status_code=404, detail=f"未找到推送配置: {push_id}")

        # 更新字段
        if pushdata.push_name is not None:
            push_config.push_name = pushdata.push_name
        if pushdata.config_id is not None:  # 允许将config_id设置为None
            # 如果有config_id，检查是否存在
            if pushdata.config_id and not db.query(DetectionConfig).filter(DetectionConfig.config_id == pushdata.config_id).first():
                raise HTTPException(status_code=404, detail=f"未找到检测配置: {pushdata.config_id}")
            push_config.config_id = pushdata.config_id
        if pushdata.tags is not None:
            push_config.tags = pushdata.tags
        if pushdata.enabled is not None:
            push_config.enabled = pushdata.enabled
        if pushdata.http_url is not None:
            push_config.http_url = pushdata.http_url
        if pushdata.http_method is not None:
            push_config.http_method = pushdata.http_method
        if pushdata.tcp_host is not None:
            push_config.tcp_host = pushdata.tcp_host
        if pushdata.tcp_port is not None:
            push_config.tcp_port = pushdata.tcp_port
        if pushdata.mqtt_broker is not None:
            push_config.mqtt_broker = pushdata.mqtt_broker
        if pushdata.mqtt_port is not None:
            push_config.mqtt_port = pushdata.mqtt_port
        if pushdata.mqtt_topic is not None:
            push_config.mqtt_topic = pushdata.mqtt_topic
        if pushdata.mqtt_username is not None:
            push_config.mqtt_username = pushdata.mqtt_username
        if pushdata.mqtt_password is not None:
            push_config.mqtt_password = pushdata.mqtt_password
        if pushdata.mqtt_use_tls is not None:
            push_config.mqtt_use_tls = pushdata.mqtt_use_tls
        if pushdata.include_image is not None:
            push_config.include_image = pushdata.include_image

        push_config.updated_at = datetime.now()
        db.commit()

        # 记录更新操作
        log_action(db, current_user.user_id, 'update_data_push', push_config.push_id, f"更新数据推送配置: {push_config.push_name}")

        # 重新加载推送配置
        data_pusher.reload_push_config(push_id, db)

        return {
            "status": "success",
            "message": "推送配置已更新"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"更新推送配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新推送配置失败: {str(e)}")

@router.delete("/{push_id}")
async def delete_push_config(push_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)): # 删除推送配置
    """删除推送配置"""
    try:
        # 查找推送配置
        push_config = db.query(DataPushConfig).filter(DataPushConfig.push_id == push_id).first()
        if not push_config:
            raise HTTPException(status_code=404, detail=f"未找到推送配置: {push_id}")

        db.delete(push_config)
        db.commit()

        # 记录删除操作
        log_action(db, current_user.user_id, 'delete_data_push', push_config.push_id, f"删除数据推送配置: {push_config.push_name}")

        # 从缓存中删除推送配置
        data_pusher.reload_push_config(push_id, db)

        return {
            "status": "success",
            "message": "推送配置已删除"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"删除推送配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除推送配置失败: {str(e)}")

@router.post("/test/{push_id}")
async def test_push_config(push_id: str, db: Session = Depends(get_db)): # 测试推送配置
    """测试推送配置"""
    try:
        # 查找推送配置
        push_config = db.query(DataPushConfig).filter(DataPushConfig.push_id == push_id).first()
        if not push_config:
            raise HTTPException(status_code=404, detail=f"未找到推送配置: {push_id}")

        # 创建测试数据
        test_data = {
            "timestamp": datetime.now().isoformat(),
            "test": True,
            "message": "这是一条测试消息",
            "push_id": push_id
        }

        # 根据推送方法进行测试
        success = False
        message = "推送测试失败"
        started = time.time()
        if push_config.push_method == PushMethod.http or push_config.push_method == PushMethod.https:
            success, message = data_pusher._push_http(push_config, test_data)
        elif push_config.push_method == PushMethod.tcp:
            success, message = data_pusher._push_tcp(push_config, test_data)
        elif push_config.push_method == PushMethod.mqtt:
            success, message = data_pusher._push_mqtt(push_config, test_data)

        duration_ms = int((time.time() - started) * 1000)
        data_pusher.record_push_log(
            push_config,
            success,
            message=message,
            duration_ms=duration_ms,
            payload_preview=data_pusher._payload_preview(test_data),
            is_test=True,
        )
        if success:
            with data_pusher.lock:
                if push_id not in data_pusher.push_stats:
                    data_pusher.push_stats[push_id] = {"success": 0, "fail": 0, "last_success": None}
                data_pusher.push_stats[push_id]["success"] += 1
                data_pusher.push_stats[push_id]["last_success"] = datetime.now()
        else:
            with data_pusher.lock:
                if push_id not in data_pusher.push_stats:
                    data_pusher.push_stats[push_id] = {"success": 0, "fail": 0, "last_success": None}
                data_pusher.push_stats[push_id]["fail"] += 1

        return {
            "status": "success" if success else "failure",
            "message": message if success else message,
        }

    except Exception as e:
        logger.error(f"测试推送配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"测试推送配置失败: {str(e)}")