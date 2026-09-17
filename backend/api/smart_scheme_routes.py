"""事件订阅（NetSDK 等）— 管理 CRUD 与启停，统一挂载 /api/v1。"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from src.database import get_db, Device, SmartScheme, SmartEvent
from api.auth import get_current_user, check_admin_permission
from api.logger import log_action
import uuid
import json

router = APIRouter(prefix="/smart-schemes", tags=["事件订阅管理"])

# Pydantic模型定义
class SmartSchemeBase(BaseModel):
    camera_id: str = Field(..., description="摄像头ID")
    camera_port: Optional[int] = Field(37777, description="摄像头监听端口")
    event_types: List[str] = Field(..., description="订阅的事件类型")
    alarm_interval: Optional[int] = Field(60, description="报警间隔时间(秒)")
    push_tags: Optional[str] = Field(None, description="推送标签")
    remarks: Optional[str] = Field(None, description="备注信息")

class SmartSchemeCreate(SmartSchemeBase):
    pass

class SmartSchemeUpdate(BaseModel):
    camera_id: Optional[str] = Field(None, description="摄像头ID")
    camera_port: Optional[int] = Field(None, description="摄像头监听端口")
    event_types: Optional[List[str]] = Field(None, description="订阅的事件类型")
    alarm_interval: Optional[int] = Field(None, description="报警间隔时间(秒)")
    push_tags: Optional[str] = Field(None, description="推送标签")
    remarks: Optional[str] = Field(None, description="备注信息")

class SmartSchemeResponse(SmartSchemeBase):
    id: str
    camera_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SmartEventBase(BaseModel):
    scheme_id: str = Field(..., description="订阅ID")
    event_type: str = Field(..., description="事件类型")
    title: str = Field(..., description="事件标题")
    description: Optional[str] = Field(None, description="事件描述")
    priority: str = Field(default="normal", description="优先级")
    event_data: Optional[Dict[str, Any]] = Field(None, description="事件数据")

class SmartEventCreate(SmartEventBase):
    pass

class ProcessingRecord(BaseModel):
    processed_at: Optional[datetime] = Field(None, description="处理时间")
    processing_result: Optional[str] = Field(None, description="处理结果")
    processing_comment: Optional[str] = Field(None, description="处理备注")
    processing_by: Optional[str] = Field(None, description="处理人")

class SmartEventUpdate(BaseModel):
    status: Optional[str] = Field(None, description="状态")
    processing_result: Optional[str] = Field(None, description="处理结果")
    processing_comment: Optional[str] = Field(None, description="处理备注")

class SmartEventResponse(SmartEventBase):
    id: str
    scheme_name: str
    camera_id: str
    camera_name: str
    status: str
    timestamp: datetime
    processing_records: ProcessingRecord

    class Config:
        from_attributes = True

# 事件类型映射
EVENT_TYPES = {
    "alarm": "报警事件",
    "smart": "智能事件", 
    "system_log": "设备日志"
}

def format_datetime(dt: datetime) -> str:
    """格式化日期时间"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# 查询事件订阅列表
@router.get("/manager", response_model=Dict[str, Any], tags=["事件订阅管理"])
def get_schemes(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    camera_id: Optional[str] = Query(None, description="摄像头ID"),
    event_type: Optional[str] = Query(None, description="事件类型"),
    status: Optional[str] = Query(None, description="状态"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    """获取事件订阅列表"""
    try:
        # 构建查询
        query = db.query(SmartScheme)
        
        # 应用过滤条件
        if camera_id:
            query = query.filter(SmartScheme.camera_id == camera_id)
        
        if event_type:
            # 使用PostgreSQL的数组操作符来检查数组中是否包含指定值
            query = query.filter(SmartScheme.event_types.any(event_type))
        
        if status:
            query = query.filter(SmartScheme.status == status)
        
        if search:
            # 通过摄像头名称搜索
            devices = db.query(Device).filter(Device.device_name.ilike(f"%{search}%")).all()
            device_ids = [device.device_id for device in devices]
            if device_ids:
                query = query.filter(SmartScheme.camera_id.in_(device_ids))
            else:
                # 如果没有匹配的设备，返回空结果
                return {
                    'items': [],
                    'total': 0,
                    'page': page,
                    'page_size': page_size
                }
        
        # 获取总数
        total = query.count()
        
        # 分页
        schemes = query.order_by(SmartScheme.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        
        # 转换为响应格式
        items = []
        for scheme in schemes:
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
            item = {
                'id': scheme.id,
                'camera_id': scheme.camera_id,
                'camera_name': device.device_name if device else "未知摄像机",
                'camera_ip': device.ip_address if device else "未知摄像机",
                'camera_port': scheme.camera_port,
                'event_types': scheme.event_types,
                'event_count': db.query(SmartEvent).filter(SmartEvent.scheme_id == scheme.id).count(), # 获取该订阅下的事件数量
                'alarm_interval': scheme.alarm_interval,
                'push_tags': scheme.push_tags,
                'remarks': scheme.remarks,
                'status': scheme.status,
                'created_at': scheme.created_at,
                'updated_at': scheme.updated_at,
                'started_at': scheme.started_at,
                'stopped_at': scheme.stopped_at,
                # 'last_heartbeat': scheme.last_heartbeat
            }
            items.append(item)
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#创建事件订阅
@router.post("/manager", response_model=SmartSchemeResponse, tags=["事件订阅管理"])
def create_scheme(
    scheme: SmartSchemeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """创建事件订阅"""
    try:
        # 验证必填字段
        if not scheme.camera_id:
            raise HTTPException(status_code=400, detail="缺少必填字段: camera_id")
        
        if not scheme.event_types:
            raise HTTPException(status_code=400, detail="缺少必填字段: event_types")
        
        # 验证摄像头是否存在
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
        if not device:
            raise HTTPException(status_code=400, detail="摄像头不存在")
        
        # 验证事件类型
        valid_event_types = ['alarm', 'smart', 'system_log']
        for event_type in scheme.event_types:
            if event_type not in valid_event_types:
                raise HTTPException(status_code=400, detail=f"无效的事件类型: {event_type}")
        
        # 验证报警间隔时间
        if scheme.alarm_interval is not None and scheme.alarm_interval < 0:
            raise HTTPException(status_code=400, detail="报警间隔时间不能为负数")
        
        # 创建订阅
        db_scheme = SmartScheme(
            camera_id=scheme.camera_id,
            camera_port=scheme.camera_port or 37777,
            event_types=scheme.event_types,
            alarm_interval=scheme.alarm_interval or 60,
            push_tags=scheme.push_tags or '',
            remarks=scheme.remarks or '',
            status='stopped'
        )
        
        db.add(db_scheme)
        db.commit()
        db.refresh(db_scheme)
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'create_smart_scheme', db_scheme.id, f"创建事件订阅 {device.device_name}")
        
        # 返回创建的订阅
        response_scheme = {
            'id': db_scheme.id,
            'camera_id': db_scheme.camera_id,
            'camera_name': device.device_name,
            'camera_port': db_scheme.camera_port,
            'event_types': db_scheme.event_types,
            'alarm_interval': db_scheme.alarm_interval,
            'push_tags': db_scheme.push_tags,
            'remarks': db_scheme.remarks,
            'status': db_scheme.status,
            'created_at': db_scheme.created_at,
            'updated_at': db_scheme.updated_at,
            'started_at': db_scheme.started_at,
            'stopped_at': db_scheme.stopped_at
        }
        
        return response_scheme
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 查询事件订阅详情
@router.get("/manager/{scheme_id}", response_model=SmartSchemeResponse, tags=["事件订阅管理"])
def get_scheme(
    scheme_id: str,
    db: Session = Depends(get_db)
):
    """获取事件订阅详情"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 获取摄像头信息
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
        
        # 构建响应
        response_scheme = {
            'id': scheme.id,
            'camera_id': scheme.camera_id,
            'camera_name': device.device_name if device else "未知摄像机",
            'camera_ip': device.ip_address if device else "未知摄像机",
            'camera_port': scheme.camera_port,
            'event_types': scheme.event_types,
            'alarm_interval': scheme.alarm_interval,
            'push_tags': scheme.push_tags,
            'remarks': scheme.remarks,
            'status': scheme.status,
            'created_at': scheme.created_at,
            'updated_at': scheme.updated_at,
            'started_at': scheme.started_at,
            'stopped_at': scheme.stopped_at
        }
        
        return response_scheme
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 更新事件订阅
@router.put("/manager/{scheme_id}", response_model=SmartSchemeResponse, tags=["事件订阅管理"])
def update_scheme(
    scheme_id: str,
    scheme_update: SmartSchemeUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """更新事件订阅"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 验证摄像头是否存在
        if scheme_update.camera_id:
            device = db.query(Device).filter(Device.device_id == scheme_update.camera_id).first()
            if not device:
                raise HTTPException(status_code=400, detail="摄像头不存在")
        
        # 验证事件类型
        if scheme_update.event_types:
            valid_event_types = ['alarm', 'smart', 'system_log']
            for event_type in scheme_update.event_types:
                if event_type not in valid_event_types:
                    raise HTTPException(status_code=400, detail=f"无效的事件类型: {event_type}")
        
        # 验证报警间隔时间
        if scheme_update.alarm_interval is not None and scheme_update.alarm_interval < 0:
            raise HTTPException(status_code=400, detail="报警间隔时间不能为负数")
        
        # 更新字段
        update_data = scheme_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(scheme, field, value)
        
        scheme.updated_at = datetime.now()
        
        db.commit()
        db.refresh(scheme)
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'update_smart_scheme', scheme_id, "更新事件订阅")
        
        # 获取摄像头信息
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
        
        # 返回更新的订阅
        response_scheme = {
            'id': scheme.id,
            'camera_id': scheme.camera_id,
            'camera_name': device.device_name if device else "未知摄像头",
            'camera_port': scheme.camera_port,
            'event_types': scheme.event_types,
            'alarm_interval': scheme.alarm_interval,
            'push_tags': scheme.push_tags,
            'remarks': scheme.remarks,
            'status': scheme.status,
            'created_at': scheme.created_at,
            'updated_at': scheme.updated_at,
            'started_at': scheme.started_at,
            'stopped_at': scheme.stopped_at
        }
        
        return response_scheme
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 删除事件订阅
@router.delete("/manager/{scheme_id}", tags=["事件订阅管理"])
def delete_scheme(
    scheme_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """删除事件订阅"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 获取摄像头信息用于日志
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
        camera_name = device.device_name if device else "未知摄像头"
        
        # 删除订阅（关联的事件也会被级联删除）
        db.delete(scheme)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'delete_smart_scheme', scheme_id, f"删除事件订阅 {camera_name}")
        
        return {"message": "删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 启动事件订阅
@router.post("/manager/{scheme_id}/start", tags=["事件订阅管理"])
def start_scheme(
    scheme_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """启动事件订阅"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 调用SmartSchemer启动订阅
        from src.smartSchemer import smart_schemer
        import asyncio
        
        # 在事件循环中运行异步函数
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        success = loop.run_until_complete(smart_schemer.start_scheme(scheme_id))
        
        if success:
            # 记录操作日志
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
            camera_name = device.device_name if device else "未知摄像头"
            log_action(db, current_user.user_id, 'start_smart_scheme', scheme_id, f"启动事件订阅 {camera_name}")
            
            return {"message": "启动成功", "status": "running"}
        else:
            raise HTTPException(status_code=500, detail="启动订阅失败")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 停止事件订阅
@router.post("/manager/{scheme_id}/stop", tags=["事件订阅管理"])
def stop_scheme(
    scheme_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """停止事件订阅"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 调用SmartSchemer停止订阅
        from src.smartSchemer import smart_schemer
        import asyncio
        
        # 在事件循环中运行异步函数
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        success = loop.run_until_complete(smart_schemer.stop_scheme(scheme_id))
        
        if success:
            # 记录操作日志
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
            camera_name = device.device_name if device else "未知摄像头"
            log_action(db, current_user.user_id, 'stop_smart_scheme', scheme_id, f"停止事件订阅 {camera_name}")
            
            return {"message": "停止成功", "status": "stopped"}
        else:
            raise HTTPException(status_code=500, detail="停止订阅失败")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 重启事件订阅
@router.post("/manager/{scheme_id}/restart", tags=["事件订阅管理"])
def restart_scheme(
    scheme_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """重启事件订阅"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 调用SmartSchemer重启订阅
        from src.smartSchemer import smart_schemer
        import asyncio
        
        # 在事件循环中运行异步函数
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 先停止再启动
        stop_success = loop.run_until_complete(smart_schemer.stop_scheme(scheme_id))
        if stop_success:
            start_success = loop.run_until_complete(smart_schemer.start_scheme(scheme_id))
            
            if start_success:
                # 记录操作日志
                device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
                camera_name = device.device_name if device else "未知摄像头"
                log_action(db, current_user.user_id, 'restart_smart_scheme', scheme_id, f"重启事件订阅 {camera_name}")
                
                return {"message": "重启成功", "status": "running"}
            else:
                raise HTTPException(status_code=500, detail="重启订阅失败")
        else:
            raise HTTPException(status_code=500, detail="停止订阅失败")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 获取所有订阅状态
@router.get("/status", tags=["事件订阅管理"])
def get_all_status(db: Session = Depends(get_db)):
    """获取所有订阅状态"""
    try:
        schemes = db.query(SmartScheme).all()
        status_list = []
        
        for scheme in schemes:
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
            status_info = {
                'scheme_id': scheme.id,
                'camera_id': scheme.camera_id,
                'camera_name': device.device_name if device else "未知摄像头",
                'status': scheme.status,
                'event_types': scheme.event_types
            }
            status_list.append(status_info)
        
        return {"status_list": status_list}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取单个订阅状态
@router.get("/{scheme_id}/status", tags=["事件订阅管理"])
def get_scheme_status(scheme_id: str, db: Session = Depends(get_db)):
    """获取单个订阅状态"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
        
        status_info = {
            'scheme_id': scheme_id,
            'camera_id': scheme.camera_id,
            'camera_name': device.device_name if device else "未知摄像头",
            'status': scheme.status,
            'event_types': scheme.event_types,
            'started_at': format_datetime(scheme.started_at) if scheme.started_at else None,
            'last_heartbeat': format_datetime(datetime.now()) if scheme.status == 'running' else None
        }
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 查询事件列表
@router.get("/events", response_model=Dict[str, Any], tags=["订阅事件管理"])
def get_events(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    scheme_id: Optional[str] = Query(None, description="订阅ID"),
    event_type: Optional[str] = Query(None, description="事件类型"),
    status: Optional[str] = Query(None, description="状态"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    """获取事件列表"""
    try:
        # 构建查询
        query = db.query(SmartEvent)
        
        # 应用过滤条件
        if scheme_id:
            query = query.filter(SmartEvent.scheme_id == scheme_id)
        
        if event_type:
            query = query.filter(SmartEvent.event_type == event_type)
        
        if status:
            query = query.filter(SmartEvent.status == status)
        
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(SmartEvent.timestamp >= start_dt)
        
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(SmartEvent.timestamp <= end_dt)
        
        if search:
            query = query.filter(
                (SmartEvent.title.ilike(f"%{search}%")) |
                (SmartEvent.description.ilike(f"%{search}%"))
            )
        
        # 按时间倒序排序
        query = query.order_by(SmartEvent.timestamp.desc())
        
        # 获取总数
        total = query.count()
        
        # 分页
        events = query.offset((page - 1) * page_size).limit(page_size).all()
        
        # 转换为响应格式
        items = []
        for event in events:
            # 获取订阅和摄像头信息
            scheme = db.query(SmartScheme).filter(SmartScheme.id == event.scheme_id).first()
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first() if scheme else None
            
            # 构建处理记录对象
            processing_record = None
            if event.processed_at or event.processing_result or event.processing_comment or event.processing_by:
                processing_record = {
                    'processed_at': event.processed_at,
                    'processing_result': event.processing_result,
                    'processing_comment': event.processing_comment,
                    'processing_by': event.processing_by
                }

            item = {
                'id': event.id,
                'scheme_id': event.scheme_id,
                'scheme_name': device.device_name if device else "未知摄像头",
                'camera_id': scheme.camera_id if scheme else None,
                'camera_name': device.device_name if device else "未知摄像头",
                'camera_ip': device.ip_address if device else "",
                'event_type': event.event_type,
                'title': event.title,
                'description': event.description,
                'priority': event.priority,
                'event_data': event.event_data,
                'status': event.status,
                'timestamp': event.timestamp,
                'processing_records': processing_record
            }
            items.append(item)
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 查询事件详情
@router.get("/events/{event_id}", response_model=SmartEventResponse, tags=["订阅事件管理"])
def get_event(event_id: str, db: Session = Depends(get_db)):
    """获取事件详情"""
    try:
        event = db.query(SmartEvent).filter(SmartEvent.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")
        
        # 获取订阅和摄像头信息
        scheme = db.query(SmartScheme).filter(SmartScheme.id == event.scheme_id).first()
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first() if scheme else None
        
        # 构建处理记录对象
        processing_record = None
        if event.processed_at or event.processing_result or event.processing_comment or event.processing_by:
            processing_record = {
                'processed_at': event.processed_at,
                'processing_result': event.processing_result,
                'processing_comment': event.processing_comment,
                'processing_by': event.processing_by
            }
        # 构建响应
        response_event = {
            'id': event.id,
            'scheme_id': event.scheme_id,
            'scheme_name': device.device_name if device else "未知摄像头",
            'camera_id': scheme.camera_id if scheme else None,
            'camera_name': device.device_name if device else "未知摄像头",
            'camera_ip': device.ip_address if device else "",
            'event_type': event.event_type,
            'title': event.title,
            'description': event.description,
            'priority': event.priority,
            'event_data': event.event_data,
            'status': event.status,
            'timestamp': event.timestamp,
            'processing_records': processing_record
        }
        
        return response_event
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 更新事件
@router.put("/events/{event_id}", response_model=SmartEventResponse, tags=["订阅事件管理"])
def update_event(
    event_id: str,
    event_update: SmartEventUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """更新事件"""
    try:
        event = db.query(SmartEvent).filter(SmartEvent.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")
        
        # 更新事件状态
        if event_update.status:
            event.status = event_update.status
            if event_update.status in ['processed', 'ignored']:
                event.processed_at = datetime.now()
                event.processing_by = current_user.username  # 记录处理人
        
        # 更新处理结果
        if event_update.processing_result:
            event.processing_result = event_update.processing_result
        
        # 更新处理备注
        if event_update.processing_comment:
            event.processing_comment = event_update.processing_comment
        
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'update_smart_event', event_id, f"更新事件状态为 {event_update.status}")
        
        # 获取订阅和摄像头信息
        scheme = db.query(SmartScheme).filter(SmartScheme.id == event.scheme_id).first()
        device = db.query(Device).filter(Device.device_id == scheme.camera_id).first() if scheme else None
        
        # 构建处理记录对象
        processing_record = None
        if event.processed_at or event.processing_result or event.processing_comment or event.processing_by:
            processing_record = {
                'processed_at': event.processed_at,
                'processing_result': event.processing_result,
                'processing_comment': event.processing_comment,
                'processing_by': event.processing_by
            }
        
        # 构建响应
        response_event = {
            'id': event.id,
            'scheme_id': event.scheme_id,
            'scheme_name': device.device_name if device else "未知摄像头",
            'camera_id': scheme.camera_id if scheme else None,
            'camera_name': device.device_name if device else "未知摄像头",
            'camera_ip': device.ip_address if device else "",
            'event_type': event.event_type,
            'title': event.title,
            'description': event.description,
            'priority': event.priority,
            'event_data': event.event_data,
            'status': event.status,
            'timestamp': event.timestamp,
            'processing_records': processing_record
        }
        
        return response_event
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 删除事件
@router.delete("/events/{event_id}", tags=["订阅事件管理"])
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """删除事件"""
    try:
        event = db.query(SmartEvent).filter(SmartEvent.id == event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")
        
        db.delete(event)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'delete_smart_event', event_id, "删除事件")
        
        return {"message": "删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 批量删除事件
@router.post("/events/batch-delete", tags=["订阅事件管理"])
def batch_delete_events(
    request_data: Dict[str, List[str]],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """批量删除事件"""
    try:
        event_ids = request_data.get('event_ids', [])
        if not event_ids:
            raise HTTPException(status_code=400, detail="缺少事件ID列表")
        
        # 批量删除事件
        deleted_count = db.query(SmartEvent).filter(SmartEvent.id.in_(event_ids)).delete(synchronize_session=False)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'batch_delete_events', None, f"批量删除 {deleted_count} 个事件")
        
        return {
            "message": f"成功删除 {deleted_count} 个事件",
            "deleted_count": deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 批量处理事件
@router.post("/events/batch-process", tags=["订阅事件管理"])
def batch_process_events(
    request_data: Dict[str, List[str]],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """批量处理事件"""
    try:
        event_ids = request_data.get('event_ids', [])
        if not event_ids:
            raise HTTPException(status_code=400, detail="缺少事件ID列表")
        
        # 批量更新事件状态为已处理
        updated_count = db.query(SmartEvent).filter(
            SmartEvent.id.in_(event_ids),
            SmartEvent.status == 'pending'
        ).update({
            SmartEvent.status: 'processed',
            SmartEvent.processed_at: datetime.now(),
            SmartEvent.processing_result: '批量处理',
            SmartEvent.processing_comment: f'由 {current_user.username} 批量处理',
            SmartEvent.processing_by: current_user.username
        }, synchronize_session=False)
        
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'batch_process_events', None, f"批量处理 {updated_count} 个事件")
        
        return {
            "message": f"成功处理 {updated_count} 个事件",
            "processed_count": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 批量忽略事件
@router.post("/events/batch-ignore", tags=["订阅事件管理"])
def batch_ignore_events(
    request_data: Dict[str, List[str]],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """批量忽略事件"""
    try:
        event_ids = request_data.get('event_ids', [])
        if not event_ids:
            raise HTTPException(status_code=400, detail="缺少事件ID列表")
        
        # 批量更新事件状态为已忽略
        updated_count = db.query(SmartEvent).filter(
            SmartEvent.id.in_(event_ids),
            SmartEvent.status == 'pending'
        ).update({
            SmartEvent.status: 'ignored',
            SmartEvent.processed_at: datetime.now(),
            SmartEvent.processing_result: '批量忽略',
            SmartEvent.processing_comment: f'由 {current_user.username} 批量忽略',
            SmartEvent.processing_by: current_user.username
        }, synchronize_session=False)
        
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'batch_ignore_events', None, f"批量忽略 {updated_count} 个事件")
        
        return {
            "message": f"成功忽略 {updated_count} 个事件",
            "ignored_count": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 统计信息
@router.get("/stats/summary", tags=["事件订阅管理"])
def get_stats_summary(db: Session = Depends(get_db)):
    """获取统计概览"""
    try:
        # 获取订阅统计
        total_schemes = db.query(SmartScheme).count()
        running_schemes = db.query(SmartScheme).filter(SmartScheme.status == 'running').count()
        
        # 获取事件统计
        today = datetime.now().date()
        today_events = db.query(SmartEvent).filter(
            func.date(SmartEvent.timestamp) == today
        ).count()
        total_events = db.query(SmartEvent).count()
        
        return {
            'schemes': {
                'total': total_schemes,
                'running': running_schemes,
                'stopped': total_schemes - running_schemes
            },
            'events': {
                'total': total_events,
                'today': today_events
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取事件统计概览
@router.get("/stats/overview", tags=["订阅事件管理"])
def get_events_stats_overview(db: Session = Depends(get_db)):
    """获取事件统计概览"""
    try:
        today = datetime.now().date()
        
        # 统计总事件数
        total_events_count = db.query(func.count(SmartEvent.id)).scalar()
        
        # 统计今日事件数
        today_events_count = db.query(func.count(SmartEvent.id)).filter(
            func.date(SmartEvent.timestamp) == today
        ).scalar()
        
        # 按类型统计总事件
        total_stats = db.query(
            SmartEvent.event_type,
            func.count(SmartEvent.id).label('count')
        ).group_by(SmartEvent.event_type).all()
        
        # 按类型统计今日事件
        today_stats = db.query(
            SmartEvent.event_type,
            func.count(SmartEvent.id).label('count')
        ).filter(func.date(SmartEvent.timestamp) == today).group_by(SmartEvent.event_type).all()
        
        # 转换为字典格式
        event_type_stats = {stat.event_type: stat.count for stat in total_stats}
        today_event_type_stats = {stat.event_type: stat.count for stat in today_stats}
        
        # 按event_type分类统计报警和智能事件数量
        alarm_events_total = event_type_stats.get('alarm', 0)
        smart_events_total = event_type_stats.get('smart', 0)
        alarm_events_today = today_event_type_stats.get('alarm', 0)
        smart_events_today = today_event_type_stats.get('smart', 0)
        
        return {
            'summary': {
                'total_events': total_events_count,
                'today_events': today_events_count
            },
            # 'by_type': {
            #     'total': event_type_stats,
            #     'today': today_event_type_stats
            # },
            'alarm_smart_events': {
                'total': {
                    'alarm': alarm_events_total,
                    'smart': smart_events_total
                },
                'today': {
                    'alarm': alarm_events_today,
                    'smart': smart_events_today
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取摄像头列表
@router.get("/cameras", tags=["事件订阅管理"])
def get_cameras(db: Session = Depends(get_db)):
    """获取摄像头列表"""
    try:
        devices = db.query(Device).filter(Device.device_type.in_(['camera', 'ipc'])).all()
        cameras = []
        for device in devices:
            cameras.append({
                'id': device.device_id,
                'name': device.device_name,
                'ip': device.ip_address,
                'port': device.port,
                'status': 'online' if device.status else 'offline'
            })
        return cameras
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取事件类型列表
@router.get("/event-types", tags=["事件订阅管理"])
def get_event_types():
    """获取事件类型列表"""
    try:
        event_types = [
            {'type': 'alarm', 'name': '报警事件'},
            {'type': 'smart', 'name': '智能事件'},
            {'type': 'system_log', 'name': '设备日志'}
        ]
        return event_types
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取订阅日志
@router.get("/{scheme_id}/logs", tags=["事件订阅管理"])
def get_scheme_logs(
    scheme_id: str,
    db: Session = Depends(get_db)
):
    """获取订阅日志"""
    try:
        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=404, detail="事件订阅不存在")
        
        # 模拟日志数据
        logs = [
            {
                'timestamp': format_datetime(datetime.now() - timedelta(minutes=5)),
                'level': 'INFO',
                'message': f'订阅 {scheme_id} 状态更新为 {scheme.status}'
            },
            {
                'timestamp': format_datetime(datetime.now() - timedelta(minutes=10)),
                'level': 'INFO',
                'message': f'订阅 {scheme_id} 接收到事件数据'
            }
        ]
        
        return {"logs": logs}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 获取SmartSchemer状态
@router.get("/system/status", tags=["事件订阅管理"])
def get_system_status():
    """获取SmartSchemer系统状态"""
    try:
        from src.smartSchemer import smart_schemer
        status = smart_schemer.get_status()
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 