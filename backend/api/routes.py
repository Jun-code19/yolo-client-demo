from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from src.database import get_db, Device, DeviceGroup, User, SysLog, DetectionModel, DetectionConfig, DetectionEvent, DetectionPerformance, SaveMode, EventStatus, DetectionFrequency, DetectionLog, CrowdAnalysisJob,CrowdAnalysisResult, DataPushConfig, DataPushLog, EdgeServer,ExternalEvent,ListenerConfig,SmartEvent, SmartScheme, AlertRule, CompositeAlert, DetectionRule
from src.rtsp_url import build_rtsp_url, RTSP_URL_PRESETS
from pydantic import BaseModel, Field, validator
from fastapi.security import OAuth2PasswordRequestForm
from api.auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user, check_admin_permission, get_password_hash, verify_password
from api.logger import log_action
from src.env_loader import load_env_file, get_detect_server_url
from src.edge_noop import delete_gallery_for_events

load_env_file()
from passlib.context import CryptContext
from fastapi.responses import FileResponse, Response, StreamingResponse
import requests

import os
import base64
import uuid
import json
import io
import re
import pandas as pd
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, text, desc, and_, or_

router = APIRouter()

# Pydantic模型定义
class Point(BaseModel):
    x: float
    y: float

class Coordinates(BaseModel):
    enabled: Optional[bool] = None
    points: Optional[List[Point]] = None  # 归一化多边形顶点

class DeviceCreate(BaseModel):
    device_id: str
    device_name: str
    device_type: str
    ip_address: str
    port: int
    username: str
    password: str
    channel: Optional[int] = 1
    stream_type: Optional[str] = "main"
    rtsp_url_mode: Optional[str] = "dahua"
    rtsp_url: Optional[str] = None
    monitor_method: Optional[str] = "auto"
    location: Optional[str] = None
    area: Optional[str] = None
    group_id: Optional[str] = None

class DeviceResponse(BaseModel):
    device_id: str
    device_name: str
    device_type: str
    ip_address: str
    port: int
    username: str
    password: str
    channel: Optional[int] = 1
    stream_type: Optional[str] = "main"
    rtsp_url_mode: Optional[str] = "dahua"
    rtsp_url: Optional[str] = None
    monitor_method: Optional[str] = "auto"
    location: Optional[str] = None
    area: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    status: bool
    last_heartbeat: Optional[datetime]
    area_coordinates:Optional[Coordinates] = None

    class Config:
        from_attributes = True

class DeviceUpdate(BaseModel):
    device_name: str = None
    device_type: str = None
    ip_address: str = None
    port: int = None
    username: str = None
    password: Optional[str] = None
    channel: Optional[int] = None
    stream_type: Optional[str] = None
    rtsp_url_mode: Optional[str] = None
    rtsp_url: Optional[str] = None
    monitor_method: Optional[str] = None
    location: Optional[str] = None
    area: Optional[str] = None
    group_id: Optional[str] = None
    area_coordinates:Optional[Coordinates] = None

# 设备管理API
@router.post("/devices/", response_model=DeviceResponse, tags=["设备管理"])
def create_device(device: DeviceCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 处理IP地址，将IPv4Address转换为字符串
    device_data = device.dict()
    # if isinstance(device_data['ip_address'], (str, bytes, bytearray)):
    #     device_data['ip_address'] = str(device_data['ip_address'])
    
    db_device = Device(**device_data)
    try:
        db.add(db_device)
        db.commit()
        db.refresh(db_device)
        log_action(db, current_user.user_id, 'create_device', db_device.device_id, f"创建设备 {db_device.device_name}")
        return db_device
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/devices/", tags=["设备管理"])
def get_devices(
    skip: int = 0, 
    limit: int = 100, 
    device_type: Optional[str] = None,
    status: Optional[bool] = None,
    device_name: Optional[str] = None,
    ip_address: Optional[str] = None,
    location: Optional[str] = None,
    area: Optional[str] = None,
    group_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    获取设备列表，支持筛选参数
    
    参数:
    - skip: 跳过记录数（分页）
    - limit: 限制记录数（分页）
    - device_type: 设备类型筛选（camera, nvr, edge_server, storage_node）
    - status: 设备状态筛选（True=在线, False=离线）
    - device_name: 设备名称筛选（模糊搜索）
    - ip_address: IP地址筛选（模糊搜索）
    - location: 位置筛选（模糊搜索）
    - area: 区域筛选（模糊搜索）
    """
    query = db.query(Device)
    
    # 应用筛选条件
    if device_type:
        query = query.filter(Device.device_type == device_type)
    
    if status is not None:
        query = query.filter(Device.status == status)
    
    if device_name:
        query = query.filter(Device.device_name.ilike(f"%{device_name}%"))
    
    if ip_address:
        query = query.filter(Device.ip_address.ilike(f"%{ip_address}%"))
    
    if location:
        query = query.filter(Device.location.ilike(f"%{location}%"))
    
    if area:
        query = query.filter(Device.area.ilike(f"%{area}%"))

    if group_id:
        if group_id == "__ungrouped__":
            query = query.filter(Device.group_id.is_(None))
        else:
            query = query.filter(Device.group_id == group_id)
    
    # 获取总数（应用筛选条件后的）
    total_count = query.count()
    
    # 应用分页
    result = (
        query.options(joinedload(Device.device_group))
        .order_by(Device.ip_address.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    def enrich_device(device: Device):
        data = {c.name: getattr(device, c.name) for c in device.__table__.columns}
        data["group_name"] = device.device_group.group_name if device.device_group else None
        return data
    
    # 返回包含总数的响应
    return {
        "data": [enrich_device(d) for d in result],
        "total": total_count,
        "filters": {
            "device_type": device_type,
            "status": status,
            "device_name": device_name,
            "ip_address": ip_address,
            "location": location,
            "area": area
        }
    }

@router.get("/devices/{device_id}", response_model=DeviceResponse, tags=["设备管理"])
def get_device(device_id: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.get("/alldevices/status", tags=["设备管理"])
async def update_device_status(db: Session = Depends(get_db)):
    from src.device_monitor import check_device_online
    from src.device_monitor_config import load_device_monitor_config

    config = load_device_monitor_config(db)
    offline_threshold = int(config.get("offline_threshold", 3))
    devices = db.query(Device).all()

    for device in devices:
        try:
            is_online = await check_device_online(device, db)
            if is_online:
                device.offline_count = 0
                device.status = True
                device.last_heartbeat = datetime.now()
                device.last_online_time = datetime.now()
            else:
                device.offline_count = (device.offline_count or 0) + 1
                if device.offline_count >= offline_threshold:
                    device.status = False
        except Exception:
            device.offline_count = (device.offline_count or 0) + 1
            if device.offline_count >= offline_threshold:
                device.status = False

    db.commit()
    return {"message": "Status updated successfully"}

@router.get("/devices/{device_id}/rtsp-url", tags=["设备管理"])
def get_device_rtsp_url(device_id: str, db: Session = Depends(get_db)):
    """获取设备实际使用的 RTSP 拉流地址（不返回密码明文日志）"""
    db_device = db.query(Device).filter(Device.device_id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        "device_id": device_id,
        "rtsp_url_mode": db_device.rtsp_url_mode or "dahua",
        "rtsp_url": build_rtsp_url(db_device),
    }

@router.put("/devices/{device_id}", response_model=DeviceResponse, tags=["设备管理"])
def update_device(device_id: str, device: DeviceUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_device = db.query(Device).filter(Device.device_id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # 更新设备信息
    update_data = device.dict(exclude_unset=True)
    # 如果密码为空，不更新密码
    if 'password' in update_data and not update_data['password']:
        del update_data['password']
    
    try:
        for key, value in update_data.items():
            setattr(db_device, key, value)
        db.commit()
        db.refresh(db_device)
        log_action(db, current_user.user_id, 'update_device', device_id, f"更新设备 {db_device.device_name}")
        return db_device
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

def _delete_detection_config_with_relations(db: Session, config: DetectionConfig) -> None:
    """删除检测配置及其关联数据（不提交事务）"""
    config_id = config.config_id

    detection_rules = db.query(DetectionRule).filter(DetectionRule.config_id == config_id).all()
    for rule in detection_rules:
        db.delete(rule)

    data_push_configs = db.query(DataPushConfig).filter(DataPushConfig.config_id == config_id).all()
    for push_config in data_push_configs:
        db.delete(push_config)

    detection_logs = db.query(DetectionLog).filter(DetectionLog.config_id == config_id).all()
    for log in detection_logs:
        db.delete(log)

    performance_records = db.query(DetectionPerformance).filter(DetectionPerformance.config_id == config_id).all()
    for perf in performance_records:
        db.delete(perf)

    events = db.query(DetectionEvent).filter(DetectionEvent.config_id == config_id).all()
    if events:
        delete_gallery_for_events([event.event_id for event in events], db=db)
    for event in events:
        try:
            if event.thumbnail_path and os.path.exists(event.thumbnail_path):
                os.remove(event.thumbnail_path)
            if event.snippet_path and os.path.exists(event.snippet_path):
                os.remove(event.snippet_path)
        except OSError as e:
            print(f"删除事件文件失败: {e}")
        db.delete(event)

    db.delete(config)


def _delete_device_with_relations(db: Session, device: Device) -> None:
    """删除设备及其关联数据（不提交事务）"""
    device_id = device.device_id
    device_ip = device.ip_address

    configs = db.query(DetectionConfig).filter(DetectionConfig.device_id == device_id).all()
    for config in configs:
        _delete_detection_config_with_relations(db, config)

    device_rules = db.query(DetectionRule).filter(DetectionRule.device_id == device_id).all()
    for rule in device_rules:
        db.delete(rule)

    device_events = db.query(DetectionEvent).filter(DetectionEvent.device_id == device_id).all()
    if device_events:
        delete_gallery_for_events([event.event_id for event in device_events], db=db)
    for event in device_events:
        try:
            if event.thumbnail_path and os.path.exists(event.thumbnail_path):
                os.remove(event.thumbnail_path)
            if event.snippet_path and os.path.exists(event.snippet_path):
                os.remove(event.snippet_path)
        except OSError as e:
            print(f"删除事件文件失败: {e}")
        db.delete(event)

    device_performance_records = db.query(DetectionPerformance).filter(DetectionPerformance.device_id == device_id).all()
    for perf in device_performance_records:
        db.delete(perf)

    device_logs = db.query(DetectionLog).filter(DetectionLog.device_id == device_id).all()
    for log in device_logs:
        db.delete(log)

    try:
        device_image_path = f"storage/devices/{device_ip}.jpg"
        if os.path.exists(device_image_path):
            os.remove(device_image_path)
            print(f"删除设备图片: {device_image_path}")
    except OSError as e:
        print(f"删除设备图片失败: {e}")

    db.delete(device)

@router.delete("/devices/{device_id}", tags=["设备管理"])
def delete_device(device_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device_name = device.device_name

    try:
        _delete_device_with_relations(db, device)
        db.commit()

        log_action(db, current_user.user_id, 'delete_device', device_id,
                  f"删除设备 {device_name} 及其相关数据和图片文件")
        return {"message": "Device and related data deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/devices/batch-delete", tags=["设备管理"])
def batch_delete_devices(
    request_data: Dict[str, List[str]],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量删除设备及其关联数据"""
    device_ids = request_data.get('device_ids', [])
    if not device_ids:
        raise HTTPException(status_code=400, detail="请提供要删除的设备ID列表")

    deleted_ids = []
    errors = []

    try:
        for device_id in device_ids:
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                errors.append(f"{device_id}: 设备不存在")
                continue
            try:
                _delete_device_with_relations(db, device)
                deleted_ids.append(device_id)
            except Exception as e:
                errors.append(f"{device_id}: {str(e)}")

        db.commit()

        log_action(
            db,
            current_user.user_id,
            'batch_delete_devices',
            '批量删除',
            f"批量删除设备: 成功{len(deleted_ids)}个, 失败{len(errors)}个"
        )

        return {
            "message": f"批量删除完成，成功删除 {len(deleted_ids)} 个设备",
            "deleted_count": len(deleted_ids),
            "total_requested": len(device_ids),
            "deleted_ids": deleted_ids,
            "errors": errors
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# 用户管理API相关数据模型
class UserCreate(BaseModel):
    user_id: str
    username: str
    password: str
    role: str = Field(..., description="用户角色，可选值: admin, operator, auditor")
    allowed_devices: List[str] = []
    
    @validator('role')
    def validate_role(cls, v):
        valid_roles = ['admin', 'operator', 'auditor']
        if v not in valid_roles:
            raise ValueError(f'角色必须是以下值之一: {", ".join(valid_roles)}')
        return v

class UserUpdate(BaseModel):
    username: str
    allowed_devices: Optional[List[str]] = []

class PasswordUpdate(BaseModel):
    user_id: str
    old_password: str
    new_password: str

# 用户管理API
@router.get("/users/", response_model=dict, tags=["用户管理"])
def get_users(
    skip: int = 0, 
    limit: int = 100, 
    role: Optional[str] = None,
    username: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """获取用户列表，支持筛选参数"""
    query = db.query(User)
    
    # 应用筛选条件
    if role:
        query = query.filter(User.role == role)
    
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    
    # 获取总数（应用筛选条件后的）
    total_count = query.count()
    
    # 应用分页
    result = query.order_by(User.created_at.desc() if hasattr(User, 'created_at') else User.user_id).offset(skip).limit(limit).all()
    
    # 转换结果，不返回密码哈希
    users_data = []
    for user in result:
        user_dict = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "allowed_devices": user.allowed_devices or []
        }
        users_data.append(user_dict)
    
    # 返回包含总数的响应
    return {
        "data": users_data,
        "total": total_count,
        "filters": {
            "role": role,
            "username": username
        }
    }

@router.post("/users/", response_model=dict, tags=["用户管理"])
def create_user(user: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(check_admin_permission)):
    # 检查用户ID是否已存在
    existing_user = db.query(User).filter(User.user_id == user.user_id).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户ID已存在")
    
    # 检查用户名是否已存在
    existing_username = db.query(User).filter(User.username == user.username).first()
    if existing_username:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 验证角色值
    valid_roles = ['admin', 'operator', 'auditor']
    if user.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"无效的角色值。允许的角色: {', '.join(valid_roles)}")
    
    # 哈希处理密码
    hashed_password = get_password_hash(user.password)
    db_user = User(
        user_id=user.user_id,
        username=user.username,
        password_hash=hashed_password,
        role=user.role,
        allowed_devices=user.allowed_devices
    )
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        # 记录操作日志
        log_action(db, current_user.user_id, 'create_user', db_user.user_id, f"创建用户 {db_user.username}")
        return {"message": "用户创建成功", "user_id": db_user.user_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/users/profile", response_model=dict, tags=["用户管理"])
def update_user_profile(user_data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """更新当前用户的个人信息"""
    try:
        # 更新用户信息
        current_user.username = user_data.username
        current_user.allowed_devices = user_data.allowed_devices
        
        db.commit()
        db.refresh(current_user)
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'update_profile', current_user.user_id, f"更新用户个人信息 for {current_user.username}")
        
        return {
            "message": "用户信息更新成功",
            "user_id": current_user.user_id,
            "username": current_user.username,
            "role": current_user.role,
            "allowed_devices": current_user.allowed_devices
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/users/password", response_model=dict, tags=["用户管理"])
def update_user_password(password_data: PasswordUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """更新用户密码"""
    # 验证是当前用户或管理员在操作
    if current_user.user_id != password_data.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权修改其他用户的密码")
    
    # 获取需要修改密码的用户
    target_user = current_user
    if current_user.user_id != password_data.user_id:
        target_user = db.query(User).filter(User.user_id == password_data.user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="用户不存在")
    
    # 验证旧密码（管理员重置密码可跳过此步骤）
    if current_user.role != "admin" and not verify_password(password_data.old_password, target_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    
    # 更新密码
    try:
        target_user.password_hash = get_password_hash(password_data.new_password)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'change_password', target_user.user_id, f"更新用户 {target_user.username} 的密码")
        
        return {"message": "密码更新成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/users/{user_id}", tags=["用户管理"])
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(check_admin_permission)):
    """删除用户"""
    # 不能删除自己
    if current_user.user_id == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己的账户")
    
    # 查找用户
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    username = user.username
    
    try:
        # 删除用户
        db.delete(user)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'delete_user', user_id, f"删除用户 {username}")
        
        return {"message": "用户删除成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# 系统日志API
@router.get("/syslogs/", tags=["系统管理"])
def get_syslogs(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    action_type: Optional[str] = None,
    db: Session = Depends(get_db)):
    query = db.query(SysLog).order_by(SysLog.log_time.desc())
    total_count = query.count()
    if user_id:
        query = query.filter(SysLog.user_id == user_id)
    if start_date:
        query = query.filter(SysLog.log_time >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(SysLog.log_time <= datetime.strptime(end_date, '%Y-%m-%d'))
    if action_type:
        query = query.filter(SysLog.action_type == action_type)
    result = query.offset(skip).limit(limit).all()
    # 返回包含总数的响应
    return {
        "data": result,
        "total": total_count
    }

# 认证API
class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/token", response_model=Token, tags=["用户登录"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
       
    # 首先尝试使用标准认证
    user = authenticate_user(db, form_data.username, form_data.password)
    
    # 如果标准认证失败，尝试使用回退策略
    if not user:       
        user = db.query(User).filter(User.username == form_data.username).first()
        
        # 如果找到用户但认证失败，尝试直接比较密码
        if user and user.password_hash == form_data.password:
            print("使用明文密码比较成功")
        else:
            print("回退认证也失败")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # 此时认证已成功
    print(f"用户 {form_data.username} 认证成功")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # 记录登录日志
    log_action(db, user.user_id, 'login', user.user_id, f"User {user.username} logged in")
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=dict, tags=["用户登录"])
async def read_users_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "role": current_user.role,
        "allowed_devices": current_user.allowed_devices
    }

@router.get("/token/validate", tags=["用户登录"])
async def validate_token(current_user: User = Depends(get_current_user)):
    """验证token是否有效"""
    return {"status": "success", "message": "Token is valid"}

@router.get("/system/init-check", tags=["用户登录"])
def check_system_initialization(db: Session = Depends(get_db)):
    """检查系统是否已初始化（是否存在用户）"""
    users_count = db.query(User).count()
    return {"initialized": users_count > 0}

@router.post("/system/init", tags=["用户登录"])
def initialize_system(admin_data: UserCreate, db: Session = Depends(get_db)):
    """初始化系统，创建管理员账户（仅当系统中没有用户时可用）"""
    users_count = db.query(User).count()
    if users_count > 0:
        raise HTTPException(status_code=400, detail="系统已初始化，无法重复创建管理员账户")
    
    # 设置为管理员角色
    admin_data.role = "admin"
    
    # 初始化加密上下文
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # 生成哈希（示例输出：$2b$12$Pv20XbsKbZQrZpP58FABDupyf8DE9/NGHjB3IJ7fxtgfyIw.ygu92）
    hashed_password = pwd_context.hash(admin_data.password)
    # 创建管理员用户
    db_user = User(
        user_id=admin_data.user_id,
        username=admin_data.username,
        password_hash=hashed_password,
        role=admin_data.role,
        allowed_devices=admin_data.allowed_devices
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        # 记录操作日志
        log_action(db, db_user.user_id, 'create_admin', db_user.user_id, f"Created admin user {db_user.username}")
        return {"message": "系统初始化成功，管理员账户已创建"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

# 模型相关的Pydantic模型
class ModelBase(BaseModel):
    models_name: str
    models_type: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

class ModelUpdate(BaseModel):
    """更新模型信息的模型"""
    models_name: Optional[str] = None
    models_type: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    is_gpu: Optional[bool] = None

class ModelResponse(ModelBase):
    models_id: str
    file_path: str
    file_size: int
    format: str
    upload_time: datetime
    last_used: Optional[datetime] = None
    is_active: bool
    is_gpu: bool
    models_classes: Optional[Dict[int, str]] = None

    class Config:
        from_attributes = True


def _build_model_download_filename(models_name: str, file_suffix: str) -> str:
    """将模型名称转为安全的下载文件名，并保留原始扩展名"""
    safe_name = re.sub(r'[\\/:*?"<>|\s]+', '_', (models_name or 'model').strip()).strip('._')
    safe_name = safe_name or 'model'
    suffix = file_suffix if file_suffix.startswith('.') else f'.{file_suffix}'
    if safe_name.lower().endswith(suffix.lower()):
        return safe_name
    return f'{safe_name}{suffix}'

# 模型管理API
@router.get("/models/upload-policy", tags=["检测模型"])
def get_model_upload_policy():
    """前端上传约束：扩展名与模型类型（随 EDGE_INFERENCE 变化）"""
    from src.edge_model_policy import allowed_model_extensions, allowed_model_types
    from src.inference_backend import get_inference_backend

    backend = get_inference_backend()
    exts = sorted(allowed_model_extensions())
    allowed = allowed_model_types()
    type_order = ("object_detection", "face", "segmentation", "keypoint", "pose", "other")
    types = [t for t in type_order if t in allowed]
    types.extend(sorted(allowed - set(types)))
    if backend == "rknn":
        hint = (
            "NPU 模式：请上传 .rknn；模型类型仅「目标检测」「人脸检测」。"
            "参数 classes 必填，见 RKNN-EXPORT.md。"
        )
    elif backend == "onnx":
        hint = "边缘盒 ONNX；模型类型仅「目标检测」「人脸检测」。无内置类别时在参数中填写 classes。"
    else:
        hint = "开发模式支持 .pt 等；边缘部署请使用 ONNX 并设置 EDGE_INFERENCE=onnx。"
    return {
        "inference_backend": backend,
        "extensions": exts,
        "model_types": types,
        "hint": hint,
    }


@router.get("/models/", response_model=List[ModelResponse], tags=["检测模型"])
def get_models(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取所有检测模型列表"""
    models = db.query(DetectionModel).order_by(DetectionModel.upload_time.desc()).offset(skip).limit(limit).all()
    return models

@router.get("/models/{models_id}", response_model=ModelResponse, tags=["检测模型"])
def get_model(models_id: str, db: Session = Depends(get_db)):
    """获取特定模型详情"""
    model = db.query(DetectionModel).filter(DetectionModel.models_id == models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model

@router.get("/models/{models_id}/download", tags=["检测模型"])
def download_model(
    models_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载模型文件，文件名使用模型名称"""
    model = db.query(DetectionModel).filter(DetectionModel.models_id == models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    file_path = Path(model.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Model file not found on server")

    download_filename = _build_model_download_filename(model.models_name, file_path.suffix)
    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        filename=download_filename,
    )

def _detect_server_is_local() -> bool:
    """单进程 unified / dev-unified：检测与管理同端口，不可 HTTP 自调（会阻塞超时）。"""
    from urllib.parse import urlparse

    if os.getenv("EDGE_UNIFIED", "").strip().lower() in ("1", "true", "yes"):
        return True
    parsed = urlparse(get_detect_server_url().rstrip("/"))
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        return False
    port = parsed.port
    if port is None:
        return True
    edge_port = int(os.getenv("EDGE_PORT", "8080") or 8080)
    return port in (edge_port, 8000, 8080)


def _load_uploaded_model_classes(
    file_path: str,
    models_type: str,
    models_params: dict,
) -> dict:
    from src.yolo_task_utils import load_yolo_model_classes

    if _detect_server_is_local():
        try:
            classes = load_yolo_model_classes(
                file_path,
                models_type=models_type,
                parameters=models_params,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"加载模型失败: {exc}") from exc
        if not classes:
            raise HTTPException(status_code=400, detail="模型加载成功，但未解析到类别信息")
        return classes

    detect_server_url = get_detect_server_url().rstrip("/")
    try:
        response = requests.post(
            f"{detect_server_url}/api/v2/model/load",
            json={
                "model_path": file_path,
                "models_type": models_type,
                "parameters": models_params,
            },
            timeout=600,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="模型加载失败: 检测服务未启动，请确认 serve_unified 在运行",
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise HTTPException(
            status_code=504,
            detail="模型加载失败: 检测服务响应超时，请稍后重试或检查 ONNX 文件",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {exc}") from exc

    if response.status_code != 200:
        detail = (response.text or "").strip()
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or detail
            if isinstance(detail, list):
                detail = "; ".join(str(x) for x in detail)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"模型加载失败: {detail}")

    classes = response.json().get("classes") or {}
    if not classes:
        raise HTTPException(status_code=500, detail="模型加载成功，但未返回类别信息")
    return classes


@router.post("/models/", response_model=ModelResponse, tags=["检测模型"])
async def upload_model(
    models_file: UploadFile = File(...),
    models_name: str = Form(...),
    models_type: str = Form(...),
    description: Optional[str] = Form(None),
    parameters: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """上传新模型文件"""
    # 检查权限（只有管理员可以上传模型）
    check_admin_permission(current_user)
    
    # 检查文件大小 (2GB限制)
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    if models_file.size and models_file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, 
            detail=f"文件太大。最大允许大小为 2GB，当前文件大小为 {models_file.size / (1024*1024*1024):.2f}GB"
        )
    
    # 检查文件格式与任务类型（边缘盒仅 .onnx / .rknn + 检测类）
    file_ext = os.path.splitext(models_file.filename)[1].lower()
    from src.edge_model_policy import validate_model_upload

    try:
        validate_model_upload(file_ext, models_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    # 创建模型ID
    models_id = str(uuid.uuid4())
    
    # 确保模型目录存在
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # 流式保存文件，避免大文件内存问题
    file_path = models_dir / f"{models_id}{file_ext}"
    try:
        with open(file_path, "wb") as buffer:
            # 使用较小的块大小进行流式保存，避免内存溢出
            chunk_size = 8192  # 8KB chunks
            while chunk := models_file.file.read(chunk_size):
                buffer.write(chunk)
    except Exception as e:
        # 如果保存失败，清理已创建的文件
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
    
    # 获取文件大小
    file_size = os.path.getsize(file_path)
    
    # 解析参数JSON
    models_params = {}
    if parameters:
        try:
            models_params = json.loads(parameters)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid parameters JSON")

    from src.yolo_task_utils import normalize_model_parameters

    models_params = normalize_model_parameters(models_params)
    
    try:
        classes = _load_uploaded_model_classes(
            str(file_path),
            models_type,
            models_params,
        )
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    # 创建数据库记录
    db_model = DetectionModel(
        models_id=models_id,
        models_name=models_name,
        models_type=models_type,
        file_path=str(file_path),
        file_size=file_size,
        format=file_ext[1:],  # 去掉点号
        description=description,
        parameters=models_params,
        upload_time=datetime.now(),
        is_active=True,
        models_classes=classes  # 将类别信息存储到数据库
    )
    
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    
    # 记录操作日志
    log_action(db, current_user.user_id, 'upload_model', models_id, f"Uploaded model {models_name}")
    
    return db_model

@router.delete("/models/{models_id}", tags=["检测模型"])
def delete_model(models_id: str, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """删除模型"""
    # 检查权限
    check_admin_permission(current_user)
    
    # 查找模型
    model = db.query(DetectionModel).filter(DetectionModel.models_id == models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    model_name = model.models_name
    model_file_path = model.file_path
    
    try:
        # 检查是否有检测配置使用此模型
        configs_using_model = db.query(DetectionConfig).filter(DetectionConfig.models_id == models_id).all()
        if configs_using_model:
            for config in configs_using_model:
                _delete_detection_config_with_relations(db, config)
        
        # 删除模型文件
        try:
            if os.path.exists(model_file_path):
                os.remove(model_file_path)
                print(f"删除模型文件: {model_file_path}")
        except OSError as e:
            # 如果文件不存在，继续删除数据库记录
            print(f"删除模型文件失败: {e}")
        
        # 删除数据库记录
        db.delete(model)
        db.commit()
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'delete_model', models_id, 
                  f"删除模型 {model_name} 及其相关配置和文件")
        
        return {"message": "Model and related configurations deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/models/{models_id}", response_model=ModelResponse, tags=["检测模型"])
def update_model(
    models_id: str, 
    model_update: ModelUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """更新模型基础信息"""
    # 检查权限（只有管理员可以修改模型）
    check_admin_permission(current_user)
    
    # 查找模型
    model = db.query(DetectionModel).filter(DetectionModel.models_id == models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 更新字段
    update_data = model_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    if "parameters" in update_data:
        from src.yolo_task_utils import (
            normalize_model_parameters,
            class_names_from_detection_model,
        )

        model.parameters = normalize_model_parameters(model.parameters or {})
        classes = class_names_from_detection_model(None, model.parameters)
        if classes:
            model.models_classes = classes
    
    try:
        db.commit()
        db.refresh(model)
        
        # 记录操作日志
        log_action(db, current_user.user_id, 'update_model', models_id, f"Updated model {model.models_name}")
        
        return model
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新模型失败: {str(e)}")

@router.put("/models/{models_id}/toggle", tags=["检测模型"])
def toggle_models_active(models_id: str, active: bool, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """切换模型激活状态"""
    # 检查权限
    check_admin_permission(current_user)
    
    # 查找模型
    model = db.query(DetectionModel).filter(DetectionModel.models_id == models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 更新状态
    model.is_active = active
    db.commit()
    db.refresh(model)
    
    # 记录操作日志
    action = "activate_model" if active else "deactivate_model"
    log_action(db, current_user.user_id, action, models_id, f"{'Activated' if active else 'Deactivated'} model {model.models_name}")
    
    return {"message": f"Model {'activated' if active else 'deactivated'} successfully"}

class Point(BaseModel):
    x: float
    y: float

class occupancyArea(BaseModel):
    points: Optional[List[Point]] = None # 使用 Point 模型来表示坐标点
    name: Optional[str] = None # 区域名称
    id: Optional[str] = None # 区域ID

class SmartScenario(BaseModel):
    """v2 多场景配置项"""
    class Config:
        extra = 'allow'

    id: Optional[str] = None
    catalogType: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = True
    points: Optional[List[Point]] = None
    occupancyAreas: Optional[List[occupancyArea]] = None
    params: Optional[Dict[str, Any]] = None
    behaviorType: Optional[str] = None
    behaviorSubtype: Optional[str] = None
    behaviorDirection: Optional[str] = None
    countingType: Optional[str] = None
    countingInterval: Optional[int] = None
    flowDirection: Optional[str] = None
    flowPeriod: Optional[str] = None
    maxCapacity: Optional[int] = None
    enableAlert: Optional[bool] = None
    alertThreshold: Optional[int] = None
    smoothWindow: Optional[int] = None
    decreaseHoldFrames: Optional[int] = None
    countBias: Optional[int] = None
    countScale: Optional[float] = None
    countPointMode: Optional[str] = None
    countMinHits: Optional[int] = None
    pushLabel: Optional[str] = None

class AreaCoordinates(BaseModel):
    class Config:
        extra = 'allow'

    version: Optional[int] = None
    scenarios: Optional[List[SmartScenario]] = None
    alertThreshold: Optional[int] = None # 报警阈值
    analysisType: Optional[str] = None # 分析类型 counting/behavior
    countingInterval: Optional[int] = None # 计数间隔
    countingType: Optional[str] = None # 计数类型 occupancy/flow
    behaviorDirection: Optional[str] = None  # 方向 in/out
    enableAlert: Optional[bool] = None # 是否启用报警
    flowDirection: Optional[str] = None # 人流方向 in/out/bidirectional
    flowPeriod: Optional[str] = None # 人流周期 10s/30s/60s/realtime
    maxCapacity: Optional[int] = None # 最大容量 100
    points: Optional[List[Point]] = None  # 使用 Point 模型来表示坐标点
    occupancyAreas: Optional[List[occupancyArea]] = None # 使用 List[List[Point]] 模型来表示区域
    pushLabel: Optional[str] = None # 推送标签
    alarm_interval: Optional[int] = None # 报警推送间隔(秒)
    behaviorSubtype: Optional[str] = None  # 可选值：directional（方向检测）、simple（普通检测）
    behaviorType: Optional[str] = None # 检测类型 area/line
    smoothWindow: Optional[int] = None # 平滑窗口
    decreaseHoldFrames: Optional[int] = None # 减少hold帧数
    countBias: Optional[int] = None # 计数偏移量
    countScale: Optional[float] = None # 计数缩放比例
    countPointMode: Optional[str] = None # 计数点模式
    countMinHits: Optional[int] = None # 计数最小命中数
# 添加检测配置的Pydantic模型
class DetectionConfigBase(BaseModel):
    config_mode: Optional[str] = "device"
    device_id: Optional[str] = None
    group_id: Optional[str] = None
    group_settings: Optional[Dict[str, Any]] = None
    models_id: str
    enabled: bool = False
    sensitivity: float = 0.5
    target_classes: Optional[List[str]] = []
    frequency: Optional[str] = "realtime"
    stream_type: Optional[str] = "main"
    save_mode: Optional[str] = "none"
    save_duration: int = 10
    max_storage_days: int = 30
    area_coordinates: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None  # 运行时段配置

class DetectionConfigCreate(DetectionConfigBase):
    pass

class DetectionConfigUpdate(BaseModel):
    models_id: Optional[str] = None
    enabled: Optional[bool] = None
    sensitivity: Optional[float] = None
    target_classes: Optional[List[str]] = None
    frequency: Optional[str] = None
    stream_type: Optional[str] = None
    save_mode: Optional[str] = None
    save_duration: Optional[int] = None
    max_storage_days: Optional[int] = None
    area_coordinates: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None  # 运行时段配置
    group_settings: Optional[Dict[str, Any]] = None

class DetectionConfigResponse(DetectionConfigBase):
    config_id: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True

class DetectionConfigInfoResponse(DetectionConfigBase):
    config_id: str
    device_name: Optional[str] = None
    group_name: Optional[str] = None
    models_name: str
    models_type: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


def _normalize_group_settings(settings: Optional[dict]) -> dict:
    defaults = {
        "frame_source_primary": "snapshot",
        "frame_source_fallback": "rtsp",
        "device_interval_sec": 1.0,
        "group_round_interval_sec": 0.0,
    }
    merged = {**defaults, **(settings or {})}
    for key in ("frame_source_primary", "frame_source_fallback"):
        if merged[key] not in ("snapshot", "rtsp"):
            merged[key] = defaults[key]
    try:
        merged["device_interval_sec"] = max(0.2, float(merged.get("device_interval_sec") or 1.0))
    except (TypeError, ValueError):
        merged["device_interval_sec"] = 1.0
    try:
        merged["group_round_interval_sec"] = max(0.0, float(merged.get("group_round_interval_sec") or 0))
    except (TypeError, ValueError):
        merged["group_round_interval_sec"] = 0.0
    return merged


def _serialize_detection_config(config: DetectionConfig, include_device_fields: bool = False) -> dict:
    config_mode = getattr(config, "config_mode", None) or "device"
    area_coordinates = config.area_coordinates or {}
    payload = {
        "config_id": config.config_id,
        "config_mode": config_mode,
        "device_id": config.device_id,
        "group_id": getattr(config, "group_id", None),
        "group_settings": getattr(config, "group_settings", None) or _normalize_group_settings(None),
        "models_id": config.models_id,
        "enabled": config.enabled,
        "sensitivity": config.sensitivity,
        "target_classes": config.target_classes if config.target_classes else [],
        "frequency": config.frequency.value if hasattr(config.frequency, "value") else config.frequency,
        "stream_type": getattr(config, "stream_type", None) or "main",
        "save_mode": config.save_mode.value if hasattr(config.save_mode, "value") else config.save_mode,
        "save_duration": config.save_duration,
        "max_storage_days": config.max_storage_days,
        "area_coordinates": area_coordinates,
        "schedule_config": config.schedule_config,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
        "created_by": config.created_by,
    }
    if include_device_fields:
        device = config.device
        group = getattr(config, "device_group", None)
        payload.update({
            "device_name": device.device_name if device else (group.group_name if group else ""),
            "group_name": group.group_name if group else None,
            "models_name": config.model.models_name if config.model else "",
            "models_type": config.model.models_type if config.model else "",
        })
        if device:
            payload.update({
                "device_type": device.device_type,
                "ip_address": device.ip_address,
                "port": device.port,
                "username": device.username,
                "password": device.password,
            })
    return payload

class BoundingBoxItem(BaseModel):
    bbox: List[float]
    class_id: int
    class_name: str
    confidence: float
# 添加检测事件的Pydantic模型
class DetectionEventBase(BaseModel):
    device_id: str
    config_id: str
    event_type: str
    confidence: float
    bounding_box: List[BoundingBoxItem]  # 修改为列表
    meta_data: Optional[dict] = None
    location: Optional[str] = None

class DetectionEventCreate(DetectionEventBase):
    pass

class DetectionEventUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    viewed_by: Optional[str] = None

class DetectionEventResponse(DetectionEventBase):
    event_id: str
    timestamp: datetime
    snippet_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: str
    viewed_at: Optional[datetime] = None
    viewed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    save_mode: str = None

    class Config:
        from_attributes = True

# 获取检测配置列表
@router.get("/detection/configs", tags=["检测配置"])
async def get_detection_configs(
    device_id: Optional[str] = None,
    device_name: Optional[str] = None,
    models_id: Optional[str] = None,
    enabled: Optional[bool] = None,
    frequency: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)):
    """
    获取检测配置列表，可按设备、模型、启用状态和检测频率筛选
    """
    query = (
        db.query(DetectionConfig)
        .options(
            joinedload(DetectionConfig.device),
            joinedload(DetectionConfig.device_group),
            joinedload(DetectionConfig.model),
        )
    )
    
    if device_id:
        query = query.filter(DetectionConfig.device_id == device_id)
    if device_name:
        query = query.join(Device, isouter=True).filter(Device.device_name.ilike(f"%{device_name}%"))
    if models_id:
        query = query.filter(DetectionConfig.models_id == models_id)
    if enabled is not None:
        query = query.filter(DetectionConfig.enabled == enabled)
    if frequency is not None:
        query = query.filter(DetectionConfig.frequency == frequency)
    
    total_count = query.count()

    query = query.order_by(desc(DetectionConfig.created_at))
  
    configs = query.offset(skip).limit(limit).all()
    
    result = [_serialize_detection_config(config, include_device_fields=True) for config in configs]
    
    return {
        "data": result,
        "total": total_count
    }

@router.get("/detection/configs/stats", tags=["检测配置"])
async def get_detection_configs_stats(db: Session = Depends(get_db)):
    """获取检测配置统计概览"""
    try:
        total_configs = db.query(DetectionConfig).count()
        enabled_configs = db.query(DetectionConfig).filter(DetectionConfig.enabled == True).count()
        disabled_configs = total_configs - enabled_configs
        manual_configs = db.query(DetectionConfig).filter(
            DetectionConfig.frequency == DetectionFrequency.manual
        ).count()
        realtime_configs = db.query(DetectionConfig).filter(
            DetectionConfig.frequency == DetectionFrequency.realtime
        ).count()
        group_configs = db.query(DetectionConfig).filter(
            DetectionConfig.config_mode == "group"
        ).count()

        return {
            "status": "success",
            "data": {
                "total_configs": total_configs,
                "enabled_configs": enabled_configs,
                "disabled_configs": disabled_configs,
                "manual_configs": manual_configs,
                "realtime_configs": realtime_configs,
                "group_configs": group_configs,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取检测配置统计失败: {str(e)}")

# 获取单个检测配置
@router.get("/detection/configs/{config_id}", response_model=DetectionConfigInfoResponse, tags=["检测配置"])
async def get_detection_config(
    config_id: str,
    db: Session = Depends(get_db)):
    """
    获取单个检测配置详情
    """
    config = (
        db.query(DetectionConfig)
        .options(
            joinedload(DetectionConfig.device),
            joinedload(DetectionConfig.device_group),
            joinedload(DetectionConfig.model),
        )
        .filter(DetectionConfig.config_id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="检测配置不存在")
    
    return _serialize_detection_config(config, include_device_fields=True)

# 创建检测配置
@router.post("/detection/configs", response_model=DetectionConfigResponse, tags=["检测配置"])
async def create_detection_config(
    config: DetectionConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    创建新的检测配置
    """
    config_mode = (config.config_mode or "device").strip()
    if config_mode not in ("device", "group"):
        raise HTTPException(status_code=400, detail="无效的配置类型")

    # 检查模型是否存在
    model = db.query(DetectionModel).filter(DetectionModel.models_id == config.models_id).first()
    if not model:
        raise HTTPException(status_code=400, detail="检测模型不存在")
    
    # 处理枚举类型
    try:
        frequency_enum = DetectionFrequency(config.frequency) if isinstance(config.frequency, str) else config.frequency
        save_mode_enum = SaveMode(config.save_mode) if isinstance(config.save_mode, str) else config.save_mode
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的频率或保存模式值")
    
    if config.frequency == "scheduled":
        raise HTTPException(status_code=400, detail="定时检测已移除，请使用实时检测或抽帧检测")

    stream_type = (config.stream_type or "main").strip()
    if stream_type not in ("main", "sub"):
        raise HTTPException(status_code=400, detail="无效的码流类型，有效值: main, sub")

    device_id = config.device_id
    group_id = config.group_id
    group_settings = None

    if config_mode == "group":
        if not group_id:
            raise HTTPException(status_code=400, detail="分组检测必须选择设备分组")
        group = db.query(DeviceGroup).filter(DeviceGroup.group_id == group_id).first()
        if not group:
            raise HTTPException(status_code=400, detail="设备分组不存在")
        device_id = None
        frequency_enum = DetectionFrequency.realtime
        group_settings = _normalize_group_settings(config.group_settings)
        if config.area_coordinates:
            raise HTTPException(status_code=400, detail="分组检测不支持智能方案/区域配置")
    else:
        if not device_id:
            raise HTTPException(status_code=400, detail="单设备检测必须选择设备")
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            raise HTTPException(status_code=400, detail="设备不存在")
        group_id = None
    
    # 创建配置记录
    db_config = DetectionConfig(
        config_id=str(uuid.uuid4()),
        config_mode=config_mode,
        device_id=device_id,
        group_id=group_id,
        group_settings=group_settings,
        models_id=config.models_id,
        enabled=config.enabled,
        sensitivity=config.sensitivity,
        target_classes=config.target_classes,
        frequency=frequency_enum,
        stream_type=stream_type,
        save_mode=save_mode_enum,
        save_duration=config.save_duration,
        max_storage_days=config.max_storage_days,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # 添加运行时段等配置
    if config.schedule_config:
        db_config.schedule_config = config.schedule_config
    if config_mode == "device" and config.area_coordinates:
        db_config.area_coordinates = config.area_coordinates
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    log_action(db, current_user.user_id, 'create_detection_config', db_config.config_id, f"Created detection config {db_config.config_id}")
    return _serialize_detection_config(db_config)

# 更新检测配置
@router.put("/detection/configs/{config_id}", response_model=DetectionConfigResponse, tags=["检测配置"])
async def update_detection_config(
    config_id: str,
    config_update: DetectionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    更新检测配置
    """
    # 查找配置
    db_config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
    if not db_config:
        raise HTTPException(status_code=404, detail="检测配置不存在")

    config_mode = getattr(db_config, "config_mode", None) or "device"
    
    # 更新模型ID（如果提供）
    if config_update.models_id is not None:
        model = db.query(DetectionModel).filter(DetectionModel.models_id == config_update.models_id).first()
        if not model:
            raise HTTPException(status_code=400, detail="检测模型不存在")
        db_config.models_id = config_update.models_id
    
    # 更新其他字段
    if config_update.enabled is not None:
        db_config.enabled = config_update.enabled
    
    if config_update.sensitivity is not None:
        db_config.sensitivity = config_update.sensitivity
    
    if config_update.target_classes is not None:
        db_config.target_classes = config_update.target_classes

    if config_update.stream_type is not None:
        stream_type = config_update.stream_type.strip()
        if stream_type not in ("main", "sub"):
            raise HTTPException(status_code=400, detail="无效的码流类型，有效值: main, sub")
        db_config.stream_type = stream_type
    
    if config_update.frequency is not None:
        try:
            if config_update.frequency == "scheduled":
                raise HTTPException(status_code=400, detail="定时检测已移除，请使用实时检测或抽帧检测")
            if config_mode == "group" and config_update.frequency != "realtime":
                raise HTTPException(status_code=400, detail="分组检测仅支持实时检测")
            db_config.frequency = DetectionFrequency(config_update.frequency) if isinstance(config_update.frequency, str) else config_update.frequency
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的频率值")
    
    if config_update.group_settings is not None and config_mode == "group":
        db_config.group_settings = _normalize_group_settings(config_update.group_settings)
    
    # 更新运行时段等配置
    if config_update.schedule_config is not None:
        db_config.schedule_config = config_update.schedule_config
    
    if config_update.save_mode is not None:
        try:
            db_config.save_mode = SaveMode(config_update.save_mode) if isinstance(config_update.save_mode, str) else config_update.save_mode
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的保存模式值")
    
    if config_update.save_duration is not None:
        db_config.save_duration = config_update.save_duration
    
    if config_update.max_storage_days is not None:
        db_config.max_storage_days = config_update.max_storage_days

    if config_update.area_coordinates is not None:
        if config_mode == "group":
            raise HTTPException(status_code=400, detail="分组检测不支持智能方案/区域配置")
        db_config.area_coordinates = config_update.area_coordinates
    
    # 更新时间戳
    db_config.updated_at = datetime.now()
    
    # 提交更改
    db.commit()
    db.refresh(db_config)
    
    log_action(db, current_user.user_id, 'update_detection_config', db_config.config_id, f"Updated detection config {db_config.config_id}")
    return _serialize_detection_config(db_config)

@router.put("/detection/configs/{config_id}/toggle", tags=["检测配置"])
def toggle_detection_active(config_id: str, enabled: bool, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """切换检测配置启用状态"""
    # 检查权限
    check_admin_permission(current_user)
    
    # 查找模型
    config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="检测配置不存在")
    
    # 更新状态
    config.enabled = enabled
    db.commit()
    db.refresh(config)
    log_action(db, current_user.user_id, 'toggle_detection_active', config_id, f"Toggled detection config {config_id} {'enabled' if enabled else 'disabled'}")
    return {"message": f"检测配置 {'启用' if enabled else '禁用'} 成功"}

# 删除检测配置
@router.delete("/detection/configs/{config_id}", tags=["检测配置"])
async def delete_detection_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    删除检测配置
    """
    db_config = db.query(DetectionConfig).filter(DetectionConfig.config_id == config_id).first()
    if not db_config:
        raise HTTPException(status_code=404, detail="检测配置不存在")
    
    try:
        _delete_detection_config_with_relations(db, db_config)
        db.commit()
        log_action(db, current_user.user_id, 'delete_detection_config', config_id, f"Deleted detection config {config_id}")
        return {"message": "检测配置已成功删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除检测配置失败: {str(e)}")

# 获取设备的所有检测事件
@router.get("/detection/events", tags=["检测事件"])
async def get_detection_events(
    device_id: Optional[str] = None,
    config_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)):
    """
    获取检测事件列表，支持多种筛选条件
    """
    query = db.query(DetectionEvent).join(DetectionConfig)
    # 应用筛选条件
    if device_id:
        query = query.filter(DetectionEvent.device_id == device_id)
    if config_id:
        query = query.filter(DetectionEvent.config_id == config_id)
    if event_type:
        query = query.filter(DetectionEvent.event_type == event_type)
    if start_date:
        query = query.filter(DetectionEvent.created_at >= start_date)
    if end_date:
        query = query.filter(DetectionEvent.created_at <= end_date)
    if status:
        try:
            status_enum = getattr(EventStatus, status)
            query = query.filter(DetectionEvent.status == status_enum)
        except AttributeError:
            raise HTTPException(status_code=400, detail="无效的状态值")
    if min_confidence:
        query = query.filter(DetectionEvent.confidence >= min_confidence)
    
    # 获取总数
    total_count = query.count()
    
    # 按时间倒序排列
    query = query.order_by(desc(DetectionEvent.created_at))
    
    events = query.offset(skip).limit(limit).all()
    
    # 转换结果
    result = []
    for event in events:
        # 确保bounding_box是字典
        bounding_box = event.bounding_box
        if isinstance(bounding_box, str):
            try:
                bounding_box = json.loads(bounding_box)
            except (json.JSONDecodeError, TypeError):
                bounding_box = []
        
        # 确保meta_data是字典
        meta_data = event.meta_data
        if isinstance(meta_data, str):
            try:
                meta_data = json.loads(meta_data)
            except (json.JSONDecodeError, TypeError):
                meta_data = {}
        elif meta_data is None:
            meta_data = {}
        
        event_dict = {
            "event_id": event.event_id,
            "device_id": event.device_id,
            "config_id": event.config_id,
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "confidence": event.confidence,
            "bounding_box": bounding_box,
            "meta_data": meta_data,
            "location": event.location,
            "snippet_path": event.snippet_path,
            "thumbnail_path": event.thumbnail_path,
            "status": event.status.value if hasattr(event.status, "value") else event.status,
            "viewed_at": event.viewed_at,
            "viewed_by": event.viewed_by,
            "notes": event.notes,
            "created_at": event.created_at,
            "save_mode": event.config.save_mode.value if hasattr(event.config.save_mode, "value") else event.config.save_mode
        }
        result.append(event_dict)
    
    # 返回包含总数的响应
    return {
        "data": result,
        "total": total_count
    }

# 获取单个检测事件详情
@router.get("/detection/events/{event_id}", response_model=DetectionEventResponse, tags=["检测事件"])
async def get_detection_event(
    event_id: str,
    db: Session = Depends(get_db)):
    """
    通过事件ID获取检测事件详情
    """
    event = db.query(DetectionEvent).filter(DetectionEvent.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="检测事件不存在")
    
    # 确保bounding_box是字典
    bounding_box = event.bounding_box
    if isinstance(bounding_box, str):
        try:
            bounding_box = json.loads(bounding_box)
        except (json.JSONDecodeError, TypeError):
            bounding_box = []
    
    # 确保meta_data是字典
    meta_data = event.meta_data
    if isinstance(meta_data, str):
        try:
            meta_data = json.loads(meta_data)
        except (json.JSONDecodeError, TypeError):
            meta_data = {}
    elif meta_data is None:
        meta_data = {}
    
    # 转换结果
    event_dict = {
        "event_id": event.event_id,
        "device_id": event.device_id,
        "config_id": event.config_id,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "confidence": event.confidence,
        "bounding_box": bounding_box,
        "meta_data": meta_data,
        "location": event.location,
        "snippet_path": event.snippet_path,
        "thumbnail_path": event.thumbnail_path,
        "status": event.status.value if hasattr(event.status, "value") else event.status,
        "viewed_at": event.viewed_at,
        "viewed_by": event.viewed_by,
        "notes": event.notes,
        "created_at": event.created_at
    }
    
    return event_dict

@router.get("/detection/events/{event_id}/thumbnail", tags=["检测事件"])
async def get_thumbnail(event_id: str, db: Session = Depends(get_db)):
    """获取缩略图数据"""
    event = db.query(DetectionEvent).filter(DetectionEvent.event_id == event_id).first() 

    if not event or not event.thumbnail_data:
        raise HTTPException(status_code=404, detail="未找到图像数据")
    
    # 添加缓存控制头
    headers = {
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400",
        "Content-Disposition": f"inline; filename={event_id}.jpg"
    }
    
    # 验证二进制数据有效性
    if not isinstance(event.thumbnail_data, bytes):
        raise HTTPException(status_code=500, detail="数据格式错误")
    
    return Response(
        content=event.thumbnail_data,
        media_type="image/jpeg",
        headers=headers
    )

# 创建检测事件
@router.post("/detection/events", response_model=DetectionEventResponse, tags=["检测事件"])
async def create_detection_event(
    event: DetectionEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    创建新的检测事件
    """
    # 检查设备是否存在
    device = db.query(Device).filter(Device.device_id == event.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    
    # 检查配置是否存在
    config = db.query(DetectionConfig).filter(DetectionConfig.config_id == event.config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="检测配置不存在")
    
     # 确保bounding_box是列表
    bounding_box = event.bounding_box
    if not isinstance(bounding_box, list):
        raise HTTPException(status_code=400, detail="bounding_box必须是一个有效的列表对象")
    
    # 确保每个元素都是字典
    for item in bounding_box:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="bounding_box中的每个元素必须是字典对象")
    
    # 确保meta_data是字典
    meta_data = event.meta_data if event.meta_data is not None else {}
    if not isinstance(meta_data, dict):
        raise HTTPException(status_code=400, detail="meta_data必须是一个有效的JSON对象")
    
    try:
        event_id = str(uuid.uuid4())
        current_time = datetime.now()
        db_event = DetectionEvent(
            event_id=event_id,
            device_id=event.device_id,
            config_id=event.config_id,
            timestamp=current_time,
            event_type=event.event_type,
            confidence=event.confidence,
            bounding_box=bounding_box,
            meta_data=meta_data,
            status=EventStatus.new,
            location=event.location,
            created_at=current_time
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
        
        log_action(db, current_user.user_id, 'create_detection_event', db_event.event_id, f"Created detection event {db_event.event_id}")
        
        # 处理返回数据中的bounding_box
        bounding_box_result = db_event.bounding_box
        if isinstance(bounding_box_result, str):
            try:
                bounding_box_result = json.loads(bounding_box_result)
            except (json.JSONDecodeError, TypeError):
                bounding_box_result = []
                
        # 处理返回数据中的meta_data
        meta_data_result = db_event.meta_data
        if isinstance(meta_data_result, str):
            try:
                meta_data_result = json.loads(meta_data_result)
            except (json.JSONDecodeError, TypeError):
                meta_data_result = {}
        elif meta_data_result is None:
            meta_data_result = {}
        
        # 转换返回数据
        event_dict = {
            "event_id": db_event.event_id,
            "device_id": db_event.device_id,
            "config_id": db_event.config_id,
            "timestamp": db_event.timestamp,
            "event_type": db_event.event_type,
            "confidence": db_event.confidence,
            "bounding_box": bounding_box_result,
            "meta_data": meta_data_result,
            "location": db_event.location,
            "snippet_path": db_event.snippet_path,
            "thumbnail_path": db_event.thumbnail_path,
            "status": db_event.status.value if hasattr(db_event.status, "value") else db_event.status,
            "viewed_at": db_event.viewed_at,
            "viewed_by": db_event.viewed_by,
            "notes": db_event.notes,
            "created_at": db_event.created_at
        }
        
        return event_dict
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建检测事件失败: {str(e)}")

# 批量更新检测事件状态（须在 /{event_id} 之前注册，避免 batch-update 被当作 event_id）
@router.put("/detection/events/batch-update", tags=["检测事件"])
async def batch_update_detection_events(
    request_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新检测事件状态"""
    try:
        event_ids = request_data.get("event_ids") or []
        status_value = request_data.get("status")
        if not event_ids:
            raise HTTPException(status_code=400, detail="请提供要更新的事件ID列表")
        if not status_value:
            raise HTTPException(status_code=400, detail="请提供目标状态")
        try:
            new_status = getattr(EventStatus, status_value)
        except AttributeError:
            raise HTTPException(status_code=400, detail="无效的状态值")

        events = db.query(DetectionEvent).filter(DetectionEvent.event_id.in_(event_ids)).all()
        if not events:
            raise HTTPException(status_code=404, detail="未找到要更新的事件")

        now = datetime.now()
        updated_count = 0
        for event in events:
            event.status = new_status
            event.viewed_by = current_user.username
            event.viewed_at = now
            updated_count += 1

        db.commit()
        log_action(
            db,
            current_user.user_id,
            "batch_update_detection_events",
            "批量更新",
            f"批量更新检测事件状态为 {status_value}，共 {updated_count} 个",
        )
        return {
            "status": "success",
            "message": f"批量更新完成，成功更新 {updated_count} 个事件",
            "updated_count": updated_count,
            "total_requested": len(event_ids),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量更新检测事件失败: {str(e)}")

# 批量删除检测事件
@router.post("/detection/events/batch-delete", tags=["检测事件"])
async def batch_delete_detection_events(
    request_data: Dict[str, List[str]],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    批量删除检测事件及其关联的图片文件
    """
    try:
        event_ids = request_data.get('event_ids', [])
        if not event_ids:
            raise HTTPException(status_code=400, detail="请提供要删除的事件ID列表")
        
        # 查询要删除的事件
        events = db.query(DetectionEvent).filter(DetectionEvent.event_id.in_(event_ids)).all()
        
        if not events:
            raise HTTPException(status_code=404, detail="未找到要删除的事件")

        delete_gallery_for_events([event.event_id for event in events])
        
        deleted_count = 0
        all_files_deleted = []
        all_files_failed = []
        errors = []
        
        for event in events:
            try:
                # 删除关联的图片文件
                event_files_deleted = []
                event_files_failed = []
                
                # 删除缩略图
                if event.thumbnail_path:
                    try:
                        if os.path.exists(event.thumbnail_path):
                            os.remove(event.thumbnail_path)
                            event_files_deleted.append(event.thumbnail_path)
                    except OSError as e:
                        event_files_failed.append(f"缩略图: {str(e)}")
                
                # 删除视频片段
                if event.snippet_path:
                    try:
                        if os.path.exists(event.snippet_path):
                            os.remove(event.snippet_path)
                            event_files_deleted.append(event.snippet_path)
                    except OSError as e:
                        event_files_failed.append(f"视频片段: {str(e)}")
                
                # 删除事件记录
                db.delete(event)
                deleted_count += 1
                
                all_files_deleted.extend(event_files_deleted)
                all_files_failed.extend(event_files_failed)
                
            except Exception as e:
                errors.append(f"删除事件 {event.event_id} 失败: {str(e)}")
        
        db.commit()
        
        # 构建日志消息
        log_message = f"批量删除检测事件: 成功{deleted_count}个, 失败{len(errors)}个"
        if all_files_deleted:
            log_message += f", 已删除文件: {len(all_files_deleted)}个"
        if all_files_failed:
            log_message += f", 文件删除失败: {len(all_files_failed)}个"
        
        log_action(db, current_user.user_id, 'batch_delete_detection_events', '批量删除', log_message)
        
        result = {
            "message": f"批量删除完成，成功删除 {deleted_count} 个事件",
            "deleted_count": deleted_count,
            "total_requested": len(event_ids),
            "files_deleted": all_files_deleted,
            "files_failed": all_files_failed
        }
        
        if errors:
            result["errors"] = errors
            result["message"] += f"，{len(errors)} 个事件删除失败"
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除检测事件失败: {str(e)}")

# 更新检测事件状态
@router.put("/detection/events/{event_id}", response_model=DetectionEventResponse, tags=["检测事件"])
async def update_detection_event(
    event_id: str,
    event_update: DetectionEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    更新检测事件状态、备注等信息
    """
    db_event = db.query(DetectionEvent).filter(DetectionEvent.event_id == event_id).first()
    if not db_event:
        raise HTTPException(status_code=404, detail="检测事件不存在")
    
    # 更新字段
    if event_update.status is not None:
        try:
            db_event.status = getattr(EventStatus, event_update.status)
        except AttributeError:
            raise HTTPException(status_code=400, detail="无效的状态值")
    
    if event_update.notes is not None:
        db_event.notes = event_update.notes
    
    # if event_update.viewed_by is not None:
    #     # 检查用户是否存在
    #     user = db.query(User).filter(User.user_id == event_update.viewed_by).first()
    #     if not user:
    #         raise HTTPException(status_code=404, detail="用户不存在")
    db_event.viewed_by = current_user.username
    db_event.viewed_at = datetime.now()
    
    try:
        db.commit()
        db.refresh(db_event)
        
        log_action(db, current_user.user_id, 'update_detection_event', db_event.event_id, f"更新检测事件状态，状态为{db_event.status.value}")
        # 确保bounding_box是字典
        bounding_box = db_event.bounding_box
        if isinstance(bounding_box, str):
            try:
                bounding_box = json.loads(bounding_box)
            except (json.JSONDecodeError, TypeError):
                bounding_box = []
        
        # 确保meta_data是字典
        meta_data = db_event.meta_data
        if isinstance(meta_data, str):
            try:
                meta_data = json.loads(meta_data)
            except (json.JSONDecodeError, TypeError):
                meta_data = {}
        elif meta_data is None:
            meta_data = {}
        
        # 转换返回数据
        event_dict = {
            "event_id": db_event.event_id,
            "device_id": db_event.device_id,
            "config_id": db_event.config_id,
            "timestamp": db_event.timestamp,
            "event_type": db_event.event_type,
            "confidence": db_event.confidence,
            "bounding_box": bounding_box,
            "meta_data": meta_data,
            "location": db_event.location,
            "snippet_path": db_event.snippet_path,
            "thumbnail_path": db_event.thumbnail_path,
            "status": db_event.status.value if hasattr(db_event.status, "value") else db_event.status,
            "viewed_at": db_event.viewed_at,
            "viewed_by": db_event.viewed_by,
            "notes": db_event.notes,
            "created_at": db_event.created_at
        }
        
        return event_dict
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新检测事件失败: {str(e)}")

# 删除检测事件
@router.delete("/detection/events/{event_id}", tags=["检测事件"])
async def delete_detection_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    """
    删除检测事件及其关联的图片文件
    """
    db_event = db.query(DetectionEvent).filter(DetectionEvent.event_id == event_id).first()
    if not db_event:
        raise HTTPException(status_code=404, detail="检测事件不存在")
    
    try:
        # 删除关联的图片文件
        files_deleted = []
        files_failed = []
        
        # 删除缩略图
        if db_event.thumbnail_path:
            try:
                if os.path.exists(db_event.thumbnail_path):
                    os.remove(db_event.thumbnail_path)
                    files_deleted.append(db_event.thumbnail_path)
            except OSError as e:
                files_failed.append(f"缩略图: {str(e)}")
        
        # 删除视频片段
        if db_event.snippet_path:
            try:
                if os.path.exists(db_event.snippet_path):
                    os.remove(db_event.snippet_path)
                    files_deleted.append(db_event.snippet_path)
            except OSError as e:
                files_failed.append(f"视频片段: {str(e)}")
        
        # 删除人员图库关联记录
        delete_gallery_for_events([event_id])

        # 删除数据库记录
        db.delete(db_event)
        db.commit()
        
        # 构建日志消息
        log_message = f"删除检测事件 {event_id}"
        if files_deleted:
            log_message += f", 已删除文件: {', '.join(files_deleted)}"
        if files_failed:
            log_message += f", 文件删除失败: {', '.join(files_failed)}"
        
        log_action(db, current_user.user_id, 'delete_detection_event', event_id, log_message)
        
        return {
            "message": "检测事件已成功删除",
            "files_deleted": files_deleted,
            "files_failed": files_failed
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除检测事件失败: {str(e)}")

# 获取检测事件统计概览
@router.get("/detection/stats", tags=["检测事件"])
async def get_detection_events_overview(db: Session = Depends(get_db)):
    """
    获取检测事件统计概览数据
    """
    try:
        # 获取当前日期（用于今日数据统计）
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 并行获取各种统计数据
        from sqlalchemy import func, and_
        
        # 1. 今日总事件数
        today_events = db.query(DetectionEvent).filter(
            DetectionEvent.created_at >= today
        ).count()
        
        # 2. 各状态事件数
        new_events = db.query(DetectionEvent).filter(
            and_(
                DetectionEvent.status == EventStatus.new,
                DetectionEvent.created_at >= today
            )
        ).count()
        
        viewed_events = db.query(DetectionEvent).filter(
            and_(
                DetectionEvent.status == EventStatus.viewed,
                DetectionEvent.created_at >= today
            )
        ).count()
        
        flagged_events = db.query(DetectionEvent).filter(
            and_(
                DetectionEvent.status == EventStatus.flagged,
                DetectionEvent.created_at >= today
            )
        ).count()
        
        archived_events = db.query(DetectionEvent).filter(
            and_(
                DetectionEvent.status == EventStatus.archived,
                DetectionEvent.created_at >= today
            )
        ).count()
        
        # 3. 高置信度事件数（置信度大于0.8）
        high_confidence_events = db.query(DetectionEvent).filter(
            and_(
                DetectionEvent.confidence >= 0.8,
                DetectionEvent.created_at >= today
            )
        ).count()
        
        # 计算已处理事件数（非新事件）
        processed_events = viewed_events + flagged_events + archived_events
        
        return {
            "status": "success",
            "data": {
                "total_today": today_events,
                "processed_today": processed_events,
                "flagged_today": flagged_events,
                "high_confidence": high_confidence_events,
                "status_breakdown": {
                    "new": new_events,
                    "viewed": viewed_events,
                    "flagged": flagged_events,
                    "archived": archived_events
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取检测事件统计失败: {str(e)}")

@router.get("/files/{file_path:path}", tags=["检测事件"])
async def get_file(file_path: str):
    # 构建完整的文件路径
    full_path = os.path.join(file_path)

    # 检查文件是否存在
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    # 返回文件
    return FileResponse(full_path)

# 添加清除系统日志的API
@router.delete("/system/logs/clear", tags=["系统管理"])
def clear_system_logs(
    days: int = Query(30, description="清除多少天前的日志"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """清除系统日志"""
    try:
        # 计算截止时间
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 删除指定日期之前的日志
        deleted = db.query(SysLog).filter(SysLog.log_time < cutoff_date).delete()
        db.commit()
        
        # 记录清除操作
        log_action(db, current_user.user_id, 'clear_system_logs', 'system', f"清除{days}天前的系统日志，共{deleted}条")
        
        return {"message": f"Successfully cleared {deleted} logs older than {days} days"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 添加导出系统日志的API
@router.get("/system/logs/export", tags=["系统管理"])
def export_system_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    action_type: Optional[str] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出系统日志"""
    try:
        query = db.query(SysLog)
        
        if start_date:  
            query = query.filter(SysLog.log_time >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(SysLog.log_time <= datetime.strptime(end_date, '%Y-%m-%d'))
        if action_type:
            query = query.filter(SysLog.action_type == action_type)
        if user_id:
            query = query.filter(SysLog.user_id == user_id)

        logs = query.order_by(SysLog.log_time.desc()).all()
        
        # 记录导出操作
        log_action(db, current_user.user_id, 'export_system_logs', 'system', f"导出系统日志，共{len(logs)}条")
        
        return {
            "data": [
                {
                    "log_id": log.log_id,
                    "user_id": log.user_id,
                    "action_type": log.action_type,
                    "target_id": log.target_id,
                    "detail": log.detail,
                    "log_time": log.log_time.isoformat()
                }
                for log in logs
            ],
            "total": len(logs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加检测日志API
@router.get("/detection/logs/", tags=["系统管理"])
def get_detection_logs(
    skip: int = 0,
    limit: int = 100,
    config_id: Optional[str] = None,
    device_id: Optional[str] = None,
    operation: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取检测日志"""
    query = db.query(DetectionLog).order_by(DetectionLog.created_at.desc())
    
    # 应用筛选条件
    if config_id:
        query = query.filter(DetectionLog.config_id == config_id)
    if device_id:
        query = query.filter(DetectionLog.device_id == device_id)
    if operation:
        query = query.filter(DetectionLog.operation == operation)
    if status:
        query = query.filter(DetectionLog.status == status)
    if start_date:
        query = query.filter(DetectionLog.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        # 添加一天，以便包含结束日期当天的记录
        end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(DetectionLog.created_at < end)
    
    # 计算总记录数
    total_count = query.count()
    
    # 获取分页结果
    logs = query.order_by(DetectionLog.created_at.desc()).offset(skip).limit(limit).all()
    
    # 构建响应
    result = []
    for log in logs:
        # 获取设备和配置的名称
        device_name = None
        config_name = None
        try:
            device = db.query(Device).filter(Device.device_id == log.device_id).first()
            if device:
                device_name = device.device_name
            
            config = db.query(DetectionConfig).filter(DetectionConfig.config_id == log.config_id).first()
            if config:
                config_name = f"检测配置 {config.config_id[:6]}..." 
        except Exception:
            pass
        
        # 获取用户名
        username = None
        if log.created_by:
            try:
                user = db.query(User).filter(User.user_id == log.created_by).first()
                if user:
                    username = user.username
            except Exception:
                pass
        
        # 构建日志记录
        log_data = {
            "log_id": log.log_id,
            "config_id": log.config_id,
            "config_name": config_name,
            "device_id": log.device_id,
            "device_name": device_name,
            "operation": log.operation,
            "status": log.status,
            "message": log.message,
            "created_by": log.created_by,
            "username": username,
            "created_at": log.created_at.isoformat()
        }
        result.append(log_data)
    
    return {
        "data": result,
        "total": total_count
    }

# 设备数据导出模板
@router.get("/devices/export/template", tags=["设备管理"])
def export_device_template(current_user: User = Depends(get_current_user)):
    """导出设备数据模板"""
    # 创建数据框架
    df = pd.DataFrame(columns=[
        "device_id", "device_name", "device_type",
        "ip_address", "port", "username", "password",
        "channel", "stream_type", "rtsp_url_mode", "rtsp_url",
        "location", "area"
    ])

    # 添加示例数据行
    example_row = {
        "device_id": "camera1",
        "device_name": "前门摄像头",
        "device_type": "camera",
        "ip_address": "192.168.1.100",
        "port": 554,
        "username": "admin",
        "password": "admin123",
        "channel": 1,
        "stream_type": "main",
        "rtsp_url_mode": "dahua",
        "rtsp_url": "",
        "location": "前门",
        "area": "安全区"
    }
    hikvision_preset = next(p for p in RTSP_URL_PRESETS if p["value"] == "hikvision")
    hikvision_example_row = {
        "device_id": "hik_nvr_ch1",
        "device_name": "海康NVR-1通道",
        "device_type": "nvr",
        "ip_address": "192.168.1.101",
        "port": 554,
        "username": "admin",
        "password": "admin123",
        "channel": 1,
        "stream_type": "main",
        "rtsp_url_mode": hikvision_preset["mode"],
        "rtsp_url": hikvision_preset["url"],
        "location": "大厅",
        "area": "安全区"
    }
    df = pd.concat([df, pd.DataFrame([example_row, hikvision_example_row])], ignore_index=True)
    
    # 创建内存缓冲区并保存Excel文件
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='设备模板', index=False)
        
        # 获取工作簿和工作表对象
        workbook = writer.book
        worksheet = writer.sheets['设备模板']
        
        # 设置列宽
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, column_len)
            
        # 添加列说明
        # 创建说明工作表
        info_worksheet = workbook.add_worksheet('填写说明')
        
        # 设置标题格式
        title_format = workbook.add_format({
            'bold': True, 
            'font_size': 14, 
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # 设置正文格式
        content_format = workbook.add_format({
            'font_size': 11,
            'text_wrap': True,
            'valign': 'top'
        })
        
        # 写入标题
        info_worksheet.write(0, 0, '设备导入模板填写说明', title_format)
        info_worksheet.set_row(0, 30)
        
        # 合并标题单元格
        info_worksheet.merge_range('A1:B1', '设备导入模板填写说明', title_format)
        
        # 写入说明内容
        instructions = [
            ['字段', '说明'],
            ['device_id', '设备ID，必填，唯一标识符'],
            ['device_name', '设备名称，必填'],
            ['device_type', '设备类型，必填，可选值：camera(摄像头)/nvr(硬盘录像机)/edge_server(边缘服务器)/storage_node(存储节点)'],
            ['ip_address', 'IP地址，必填，格式：xxx.xxx.xxx.xxx'],
            ['port', '端口号，必填，整数，默认554'],
            ['username', '用户名，必填'],
            ['password', '密码，必填'],
            ['channel', '通道号，选填，适用于NVR设备，整数，默认1'],
            ['stream_type', '码流类型，选填，可选值：main(主码流)/sub(辅码流)，默认main'],
            ['rtsp_url_mode', '拉流方式存储值，选填：dahua(大华)/custom(海康/宇视/通用)，默认 dahua'],
            ['rtsp_url', 'RTSP 模板或完整地址；custom 时必填。海康: .../Streaming/Channels/{hik_channel}；宇视: .../video{channel}/{subtype}'],
            ['location', '位置，选填'],
            ['area', '区域，选填']
        ]
        
        # 写入说明内容
        for row_num, row_data in enumerate(instructions):
            info_worksheet.write(row_num + 1, 0, row_data[0], content_format)
            info_worksheet.write(row_num + 1, 1, row_data[1], content_format)
            
        # 设置列宽
        info_worksheet.set_column('A:A', 15)
        info_worksheet.set_column('B:B', 60)
    
    # 设置文件指针位置到开始
    output.seek(0)
    
    # 记录日志
    log_action(next(get_db()), current_user.user_id, 'export_device_template', 'system', f"用户 {current_user.username} 导出设备模板")
    
    # 返回Excel文件
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=device_template.xlsx"}
    )

# 设备数据导出
@router.get("/devices/export/data", tags=["设备管理"])
def export_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """导出所有设备数据"""
    # 从数据库获取所有设备
    devices = db.query(Device).all()
    
    # 将设备数据转换为字典列表
    devices_data = []
    for device in devices:
        device_dict = {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "device_type": device.device_type,
            "ip_address": device.ip_address,
            "port": device.port,
            "username": device.username,
            "password": device.password,
            "channel": device.channel,
            "stream_type": device.stream_type,
            "rtsp_url_mode": device.rtsp_url_mode or "dahua",
            "rtsp_url": device.rtsp_url or "",
            "location": device.location,
            "area": device.area,
            "status": "在线" if device.status else "离线",
            "last_heartbeat": device.last_heartbeat.strftime("%Y-%m-%d %H:%M:%S") if device.last_heartbeat else ""
        }
        devices_data.append(device_dict)
    
    # 创建数据框架
    df = pd.DataFrame(devices_data)
    
    # 创建内存缓冲区并保存Excel文件
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='设备数据', index=False)
        
        # 获取工作簿和工作表对象
        workbook = writer.book
        worksheet = writer.sheets['设备数据']
        
        # 设置列宽
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, column_len)
    
    # 设置文件指针位置到开始
    output.seek(0)
    
    # 记录日志
    log_action(db, current_user.user_id, 'export_devices', 'system', f"用户 {current_user.username} 导出设备数据")
    
    # 设置当前日期作为文件名一部分
    current_date = datetime.now().strftime("%Y%m%d")
    
    # 返回Excel文件
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=devices_{current_date}.xlsx"}
    )

# 设备数据导入
@router.post("/devices/import", tags=["设备管理"])
async def import_devices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导入设备数据"""
    # 检查文件扩展名
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ['.xlsx', '.xls', '.csv']:
        raise HTTPException(status_code=400, detail="仅支持Excel(.xlsx/.xls)或CSV(.csv)文件格式")
    
    # 读取文件内容
    contents = await file.read()
    
    try:
        # 解析Excel文件
        df = pd.read_excel(io.BytesIO(contents)) if file_extension in ['.xlsx', '.xls'] else pd.read_csv(io.BytesIO(contents))
        
        # 检查必要的列是否存在
        required_columns = ['device_id', 'device_name', 'device_type', 'ip_address', 'port', 'username', 'password']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"导入文件缺少必要的列: {', '.join(missing_columns)}")
        
        # 处理导入的设备数据
        success_count = 0
        error_count = 0
        update_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # 检查必填字段是否有值
                for col in required_columns:
                    if pd.isna(row[col]) or str(row[col]).strip() == '':
                        raise ValueError(f"第{index+2}行: {col}字段不能为空")
                
                # 检查设备类型是否有效
                valid_device_types = ['camera', 'nvr', 'edge_server', 'storage_node']
                if row['device_type'] not in valid_device_types:
                    raise ValueError(f"第{index+2}行: 无效的设备类型 '{row['device_type']}'. 有效类型: {', '.join(valid_device_types)}")
                
                valid_stream_types = ['main', 'sub']
                stream_type = str(row['stream_type']).strip() if 'stream_type' in row and not pd.isna(row['stream_type']) else 'main'
                if stream_type not in valid_stream_types:
                    raise ValueError(f"第{index+2}行: 无效的码流类型 '{stream_type}'，有效值: main, sub")

                rtsp_url_mode = str(row['rtsp_url_mode']).strip().lower() if 'rtsp_url_mode' in row and not pd.isna(row['rtsp_url_mode']) else 'dahua'
                if rtsp_url_mode not in ['dahua', 'custom']:
                    raise ValueError(f"第{index+2}行: 无效的拉流方式 '{rtsp_url_mode}'，有效值: dahua, custom")

                rtsp_url = str(row['rtsp_url']).strip() if 'rtsp_url' in row and not pd.isna(row['rtsp_url']) else ''
                if rtsp_url_mode == 'custom' and not rtsp_url:
                    raise ValueError(f"第{index+2}行: 自定义拉流方式需填写 rtsp_url")
                if rtsp_url_mode == 'dahua':
                    rtsp_url = None

                # 准备设备数据
                device_data = {
                    "device_id": str(row['device_id']),
                    "device_name": str(row['device_name']),
                    "device_type": str(row['device_type']),
                    "ip_address": str(row['ip_address']),
                    "port": int(row['port']),
                    "username": str(row['username']),
                    "password": str(row['password']),
                    "channel": int(row['channel']) if 'channel' in row and not pd.isna(row['channel']) else 1,
                    "stream_type": stream_type,
                    "rtsp_url_mode": rtsp_url_mode,
                    "rtsp_url": rtsp_url,
                    "location": str(row['location']) if 'location' in row and not pd.isna(row['location']) else None,
                    "area": str(row['area']) if 'area' in row and not pd.isna(row['area']) else None
                }
                
                # 检查设备ID是否已存在
                existing_device = db.query(Device).filter(Device.device_id == device_data['device_id']).first()
                
                if existing_device:
                    # 更新已存在的设备
                    for key, value in device_data.items():
                        setattr(existing_device, key, value)
                    update_count += 1
                else:
                    # 创建新设备
                    new_device = Device(**device_data)
                    db.add(new_device)
                    success_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(str(e))
                continue
        
        # 提交事务
        db.commit()
        
        # 记录日志
        log_action(
            db, 
            current_user.user_id, 
            'import_devices', 
            'system', 
            f"用户 {current_user.username} 导入设备数据: 成功新增{success_count}个, 更新{update_count}个, 失败{error_count}个"
        )
        
        # 构建响应
        response = {
            "message": f"设备导入完成: 成功新增{success_count}个, 更新{update_count}个, 失败{error_count}个",
            "success_count": success_count,
            "update_count": update_count,
            "error_count": error_count
        }
        
        # 如果有错误，添加错误详情
        if errors:
            response["errors"] = errors[:10]  # 只返回前10个错误
            if len(errors) > 10:
                response["errors"].append(f"... 还有{len(errors) - 10}个错误未显示")
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理导入文件时出错: {str(e)}")

@router.get("/detection/logs/export", tags=["系统管理"])
def export_detection_logs(
    skip: int = 0,
    limit: int = 1000,
    config_id: Optional[str] = None,
    device_id: Optional[str] = None,
    operation: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出检测日志"""
    try:
        query = db.query(DetectionLog).order_by(DetectionLog.created_at.desc())
        
        # 应用筛选条件
        if config_id:
            query = query.filter(DetectionLog.config_id == config_id)
        if device_id:
            query = query.filter(DetectionLog.device_id == device_id)
        if operation:
            query = query.filter(DetectionLog.operation == operation)
        if status:
            query = query.filter(DetectionLog.status == status)
        if start_date:
            query = query.filter(DetectionLog.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            # 添加一天，以便包含结束日期当天的记录
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(DetectionLog.created_at < end)
        
        # 获取数据
        logs = query.limit(limit).offset(skip).all()
        
        # 转换为Excel
        df = pd.DataFrame()
        result = []
        
        for log in logs:
            # 获取设备和配置的名称
            device_name = None
            config_name = None
            try:
                device = db.query(Device).filter(Device.device_id == log.device_id).first()
                if device:
                    device_name = device.device_name
                
                config = db.query(DetectionConfig).filter(DetectionConfig.config_id == log.config_id).first()
                if config:
                    config_name = f"检测配置 {config.config_id[:6]}..." 
            except Exception:
                pass
            
            # 获取用户名
            username = None
            if log.created_by:
                try:
                    user = db.query(User).filter(User.user_id == log.created_by).first()
                    if user:
                        username = user.username
                except Exception:
                    pass
            
            # 构建日志记录
            log_data = {
                "日志ID": log.log_id,
                "设备ID": log.device_id,
                "设备名称": device_name,
                "配置ID": log.config_id,
                "配置名称": config_name,
                "操作类型": log.operation,
                "状态": "成功" if log.status == "success" else "失败",
                "消息": log.message,
                "执行用户ID": log.created_by,
                "执行用户": username,
                "操作时间": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else ""
            }
            result.append(log_data)
        
        df = pd.DataFrame(result)
        
        # 创建内存缓冲区并保存Excel文件
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='检测日志', index=False)
            
            # 获取工作簿和工作表对象
            workbook = writer.book
            worksheet = writer.sheets['检测日志']
            
            # 设置列宽
            for i, col in enumerate(df.columns):
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, column_len)
        
        # 设置文件指针位置到开始
        output.seek(0)
        
        # 记录日志
        log_action(db, current_user.user_id, 'export_detection_logs', 'system', f"用户 {current_user.username} 导出检测日志")
        
        # 设置当前日期作为文件名一部分
        current_date = datetime.now().strftime("%Y%m%d")
        
        # 返回Excel文件
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=detection_logs_{current_date}.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出日志失败: {str(e)}")

@router.delete("/detection/logs/clear", tags=["系统管理"])
def clear_detection_logs(
    days: int = Query(30, description="清除多少天前的日志"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """清除检测日志"""
    try:
        # 计算截止时间
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 删除指定日期之前的日志
        deleted = db.query(DetectionLog).filter(DetectionLog.created_at < cutoff_date).delete()
        db.commit()
        
        # 记录清除操作
        log_action(db, current_user.user_id, 'clear_detection_logs', 'system', f"清除{days}天前的检测日志，共{deleted}条")
        
        return {"message": f"成功清除 {deleted} 条{days}天前的检测日志"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data_push/list", tags=["数据推送"])
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


@router.get("/data_push/logs", tags=["数据推送"])
async def list_push_logs_v1(
    push_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """查询推送执行记录（持久化）"""
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
        raise HTTPException(status_code=500, detail=f"查询推送记录失败: {str(e)}")


# 系统状态监控API
@router.get("/system/status", tags=["系统管理"])
def get_system_status(db: Session = Depends(get_db)):
    """获取边缘盒系统状态（主机信息、CPU/内存/NPU/存储等）"""
    try:
        from src.system_status import collect_system_status

        return collect_system_status(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")

# 首页仪表盘API
@router.get("/dashboard/comprehensive-overview", tags=["首页仪表盘"] )
def get_comprehensive_dashboard_overview(db: Session = Depends(get_db)):
    """获取完整的首页数据概览，包含所有模块的统计数据"""
    try:
        # 获取当前日期（用于今日数据统计）
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        
        # 1. 设备管理统计
        total_devices = db.query(Device).count()
        online_devices = db.query(Device).filter(Device.status == True).count()
        offline_devices = total_devices - online_devices
        
        # 按设备类型统计
        device_types = db.query(
            Device.device_type, 
            func.count(Device.device_id).label('count')
        ).group_by(Device.device_type).all()
        device_type_distribution = {device_type: count for device_type, count in device_types}
        
        # 2. 模型管理统计
        total_models = db.query(DetectionModel).count()
        active_models = db.query(DetectionModel).filter(DetectionModel.is_active == True).count()
        
        # 按模型类型统计
        model_types = db.query(
            DetectionModel.models_type, 
            func.count(DetectionModel.models_id).label('count')
        ).group_by(DetectionModel.models_type).all()
        model_type_distribution = {model_type: count for model_type, count in model_types}
        
        # 3. 数据推送统计
        total_push_configs = db.query(DataPushConfig).count()
        active_push_configs = db.query(DataPushConfig).filter(DataPushConfig.enabled == True).count()
        
        # 按推送方式统计
        push_methods = db.query(
            DataPushConfig.push_method, 
            func.count(DataPushConfig.push_id).label('count')
        ).group_by(DataPushConfig.push_method).all()
        push_method_distribution = {method.value: count for method, count in push_methods}
        
        # 边缘盒：无事件监听（TCP/MQTT/HTTP 接入）
        total_listeners = 0
        active_listeners = 0
        listener_type_distribution = {}

        # 边缘盒产品：不统计纳管节点 / 人群 / VLM 巡检（字段保留为 0 以兼容前端）
        total_edge_servers = 0
        online_edge_servers = 0
        total_crowd_jobs = 0
        active_crowd_jobs = 0
        total_crowd_results = 0
        crowd_job_distribution = []

        # 7. 检测任务统计
        total_detection_configs = db.query(DetectionConfig).count()
        active_detection_configs = db.query(DetectionConfig).filter(DetectionConfig.enabled == True).count()

        pipeline_mode_distribution = {"yolo_only": total_detection_configs}

        # 8. 检测事件统计（总数而非今日）
        total_detection_events = db.query(DetectionEvent).count()
        today_detection_events = db.query(DetectionEvent).filter(DetectionEvent.created_at >= today).count()

        # 按状态统计检测事件
        event_status_stats = db.query(
            DetectionEvent.status, 
            func.count(DetectionEvent.event_id).label('count')
        ).group_by(DetectionEvent.status).all()
        event_status_distribution = {status.value: count for status, count in event_status_stats}
        
        # 按事件类型统计检测事件
        event_type_stats = db.query(
            DetectionEvent.event_type, 
            func.count(DetectionEvent.event_id).label('count')
        ).group_by(DetectionEvent.event_type).all()
        event_type_distribution = {event_type: count for event_type, count in event_type_stats}
        
        # 9. 规则引擎统计（复合告警）
        total_alert_rules = db.query(AlertRule).count()
        enabled_alert_rules = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).count()
        total_composite_alerts = db.query(CompositeAlert).count()
        today_composite_alerts = db.query(CompositeAlert).filter(CompositeAlert.fired_at >= today).count()

        alert_status_stats = db.query(
            CompositeAlert.status,
            func.count(CompositeAlert.alert_id).label('count')
        ).group_by(CompositeAlert.status).all()
        alert_status_distribution = {status: count for status, count in alert_status_stats}

        rule_alert_stats = db.query(
            AlertRule.name,
            func.count(CompositeAlert.alert_id).label('count')
        ).join(
            CompositeAlert, CompositeAlert.rule_id == AlertRule.rule_id
        ).group_by(AlertRule.name).order_by(func.count(CompositeAlert.alert_id).desc()).limit(20).all()
        alert_rule_distribution = {name: count for name, count in rule_alert_stats}
        
        # 订阅事件统计
        total_scheme_events = db.query(SmartEvent).count()
        today_scheme_events = db.query(SmartEvent).filter(SmartEvent.created_at >= today).count()

        scheme_event_stats = db.query(
            SmartScheme.id,
            Device.device_name,
            SmartScheme.remarks,
            func.count(SmartEvent.id).label("event_count"),
        ).join(SmartEvent, SmartEvent.scheme_id == SmartScheme.id).join(
            Device, Device.device_id == SmartScheme.camera_id
        ).group_by(
            SmartScheme.id, Device.device_name, SmartScheme.remarks
        ).order_by(func.count(SmartEvent.id).desc()).limit(20).all()

        scheme_event_distribution = []
        for scheme_id, device_name, remarks, event_count in scheme_event_stats:
            label = (remarks or device_name or scheme_id or "未命名订阅").strip()
            if len(label) > 20:
                label = f"{label[:20]}…"
            scheme_event_distribution.append({
                "scheme_id": scheme_id,
                "scheme_name": label,
                "device_name": device_name,
                "count": int(event_count or 0),
            })

        # 10. 用户统计
        total_users = db.query(User).count()
        # admin_users = db.query(User).filter(User.role == "admin").count()
        # operator_users = db.query(User).filter(User.role == "operator").count()
        # auditor_users = db.query(User).filter(User.role == "auditor").count()
        
        # 11. 系统日志统计
        total_system_logs = db.query(SysLog).count()
        # today_system_logs = db.query(SysLog).filter(SysLog.log_time >= today).count()
        
        # 12. 检测日志统计
        total_detection_logs = db.query(DetectionLog).count()
        # today_detection_logs = db.query(DetectionLog).filter(DetectionLog.created_at >= today).count()
        
        # 13. 近7天的数据趋势
        # 获取最近5天的每天的数据条数
        composite_alert_history = db.query(
            func.date(CompositeAlert.fired_at).label('date'),
            func.count(CompositeAlert.alert_id).label('count')
        ).filter(
            CompositeAlert.fired_at >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(CompositeAlert.fired_at)
        ).all()

        detection_event_history = db.query(
            func.date(DetectionEvent.created_at).label('date'), 
            func.count(DetectionEvent.event_id).label('count')
        ).filter(
            DetectionEvent.created_at >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(DetectionEvent.created_at)
        ).all()

        smart_event_history = db.query(
            func.date(SmartEvent.timestamp).label('date'), 
            func.count(SmartEvent.id).label('count')
        ).filter(
            SmartEvent.timestamp >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(SmartEvent.timestamp)
        ).all()

        # 创建一个字典来存储所有数据，以日期为键
        result_dict = {}
        # 生成过去5天的所有日期，并初始化为0
        today = datetime.now().date()
        for i in range(7, -1, -1): # 包括今天和过去5天，共6天
            date = today - timedelta(days=i)
            result_dict[date] = {
                "date": date.strftime("%Y-%m-%d"),
                "alert_rules": 0,
                "detection_events": 0,
                "scheme_events": 0
            }

        # 处理规则引擎告警趋势
        for date, count in composite_alert_history:
            if date in result_dict:
                result_dict[date]["alert_rules"] = count

        # 处理检测事件数据
        for date, count in detection_event_history:
            if date in result_dict:
                result_dict[date]["detection_events"] = count

        # 处理智能事件数据
        for date, count in smart_event_history:
            if date in result_dict:
                result_dict[date]["scheme_events"] = count

        # 转换为列表并按日期排序
        daily_trends = sorted(result_dict.values(), key=lambda x: x["date"])       
        
        # 14. 最近活动（合并检测事件和外部事件）
        recent_detection_events = db.query(DetectionEvent).order_by(
            DetectionEvent.created_at.desc()
        ).limit(20).all()
        
        # recent_external_events = db.query(ExternalEvent).order_by(
        #     ExternalEvent.timestamp.desc()
        # ).limit(10).all()
        
        def getModelTypeName(type):
            typeMap = {
                'object_detection': '目标检测',
                'smart_behavior': '智能行为',
                'smart_person': '人员场景',
                'smart_counting': '智能人数统计',
                'segmentation': '图像分割',
                'keypoint': '关键点检测',
                'pose': '姿态估计',
                'face': '人脸识别',
                'other': '其他类型'
            }
            return typeMap.get(type) or type
        
        def formatDetectionActivityContent(event, device_name):
            meta = event.meta_data or {}
            if event.event_type == 'object_detection':
                count = meta.get('current_count', 0)
            elif event.event_type == 'smart_behavior':
                count = 1
            elif event.event_type == 'smart_person':
                count = meta.get('current_count', 1)
            elif event.event_type == 'smart_counting':
                count = meta.get('current_count', 0)
            else:
                count = meta.get('current_count', 0)
            return f"[本地检测][{getModelTypeName(event.event_type)}][{device_name}]检测到:{count}个目标"
        
        def formatTimeAgo(timestamp):
            time_diff = datetime.now() - timestamp
            if time_diff.days > 0:
                return f"{time_diff.days} 天前"
            elif time_diff.seconds >= 3600:
                return f"{time_diff.seconds // 3600} 小时前"
            elif time_diff.seconds >= 60:
                return f"{time_diff.seconds // 60} 分钟前"
            else:
                return f"{time_diff.seconds} 秒前"
        
        recent_activities = []
        
        # 添加检测事件
        for event in recent_detection_events:
            device = db.query(Device).filter(Device.device_id == event.device_id).first()
            device_name = device.device_name if device else "未知设备"
            
            event_type = "primary"
            if event.status == EventStatus.new:
                event_type = "danger"
            elif event.status == EventStatus.viewed or event.status == EventStatus.flagged:
                event_type = "warning"
            elif event.status == EventStatus.archived:
                event_type = "success"

            recent_activities.append({
                "content": formatDetectionActivityContent(event, device_name),
                "timestamp": formatTimeAgo(event.created_at),
                "type": event_type,
                "event_id": event.event_id,
                "source": "detection"
            })
        
        # 添加外部事件
        # for event in recent_external_events:
        #     # 从normalized_data.targets获取
        #     if event.normalized_data and event.normalized_data.get('targets'):
        #         count = len(event.normalized_data['targets'])
        #     # 从 algorithm_data 获取 - 修正字段访问
        #     elif event.algorithm_data and event.algorithm_data.get('detections'):
        #         count = len(event.algorithm_data['detections'])
        #     # 从原始数据获取
        #     elif event.original_data and event.original_data.get('detections'):
        #         count = len(event.original_data['detections'])
        #     # 修正 nn_output 处理 - 它本身是结果数组
        #     elif event.original_data and event.original_data.get('nn_output'):
        #         # nn_output 本身是检测结果数组
        #         count = len(event.original_data['nn_output'])
        #     else:
        #         count = 0

        #     recent_activities.append({
        #         "content": f"[外部事件][{event.engine_name or '未知引擎'}][{event.location or '未知位置'}]检测到:{count}个目标",    
        #         "timestamp": formatTimeAgo(event.timestamp),
        #         "type": "info",
        #         "event_id": event.event_id,
        #         "source": "external"
        #     })
        
        # 按时间排序
        # recent_activities.sort(key=lambda x: x["timestamp"], reverse=True)
        # recent_activities = recent_activities[:20]  # 只取前20个
        
        # 15. 系统性能统计（近 7 天）
        perf_since = datetime.now() - timedelta(days=7)
        avg_detection_time = db.query(
            func.avg(
                DetectionPerformance.detection_time
                + DetectionPerformance.preprocessing_time
                + DetectionPerformance.postprocessing_time
            )
        ).filter(
            DetectionPerformance.timestamp >= perf_since,
            DetectionPerformance.detection_time.isnot(None),
        ).scalar()
        # 库内与 API 均为 ms
        avg_detection_time = round(float(avg_detection_time or 0), 2)

        perf_sample_count = db.query(func.count(DetectionPerformance.performance_id)).filter(
            DetectionPerformance.timestamp >= perf_since
        ).scalar() or 0

        avg_confidence_raw = db.query(func.avg(DetectionEvent.confidence)).filter(
            DetectionEvent.created_at >= perf_since,
            DetectionEvent.confidence.isnot(None),
        ).scalar()
        avg_confidence = round(float(avg_confidence_raw or 0) * 100, 1)

        confidence_sample_count = db.query(func.count(DetectionEvent.event_id)).filter(
            DetectionEvent.created_at >= perf_since,
            DetectionEvent.confidence.isnot(None),
        ).scalar() or 0
        
        # 整合返回数据
        response = {
            "summary": {
                "total_devices": total_devices,
                "online_devices": online_devices,
                "offline_devices": offline_devices,
                "total_models": total_models,
                "active_models": active_models,
                "total_push_configs": total_push_configs,
                "active_push_configs": active_push_configs,
                "total_listeners": total_listeners,
                "active_listeners": active_listeners,
                "total_edge_servers": total_edge_servers,
                "online_edge_servers": online_edge_servers,
                "total_crowd_jobs": total_crowd_jobs,
                "active_crowd_jobs": active_crowd_jobs,
                "total_detection_configs": total_detection_configs,
                "active_detection_configs": active_detection_configs,
                "total_users": total_users,
                "total_system_logs": total_system_logs,
                "total_detection_logs": total_detection_logs
            },
            "events": {
                "detection_events": {
                    "total": total_detection_events,
                    "today": today_detection_events,
                    "status_distribution": event_status_distribution,
                    "type_distribution": event_type_distribution
                },
                "alert_rules": {
                    "total": total_composite_alerts,
                    "today": today_composite_alerts,
                    "rule_total": total_alert_rules,
                    "rule_enabled": enabled_alert_rules,
                    "status_distribution": alert_status_distribution,
                    "rule_distribution": alert_rule_distribution,
                },
                "scheme_events":{
                    "total":total_scheme_events,
                    "today": today_scheme_events,
                    "scheme_distribution": scheme_event_distribution,
                }
            },
            "distributions": {
                "device_types": device_type_distribution,
                "model_types": model_type_distribution,
                "push_methods": push_method_distribution,
                "listener_types": listener_type_distribution
            },
            "crowd_analysis": {
                "total_results": total_crowd_results,
                "job_distribution": crowd_job_distribution
            },
            "inference_pipeline": {
                "mode_distribution": pipeline_mode_distribution,
            },
            "performance": {
                "avg_confidence": avg_confidence,
                "avg_confidence_sample_count": int(confidence_sample_count),
                "avg_detection_time": avg_detection_time,
                "avg_detection_time_sample_count": int(perf_sample_count),
            },
            "trends": {
                "daily": daily_trends
            },
            "recent_activities": recent_activities
        }
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取完整仪表盘数据失败: {str(e)}")
    
class EdgeServerBase(BaseModel):
    """边缘服务器基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="服务器名称")
    ip_address: str = Field(..., description="IP地址或主机名")
    port: int = Field(default=80, ge=1, le=65535, description="端口号")
    description: Optional[str] = Field(None, description="服务器描述")
    platform_type: str = Field(default="maisi", description="平台类型: maisi/nodered/custom")
    admin_url: Optional[str] = Field(None, description="管理/编辑器地址")
    dashboard_url: Optional[str] = Field(None, description="Dashboard 地址")
    health_check_url: Optional[str] = Field(None, description="自定义健康检查地址")
    is_active: bool = Field(default=True, description="是否启用")

class EdgeServerCreate(EdgeServerBase):
    """创建边缘服务器模型"""
    pass

class EdgeServerUpdate(BaseModel):
    """更新边缘服务器模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="服务器名称")
    ip_address: Optional[str] = Field(None, description="IP地址或主机名")
    port: Optional[int] = Field(None, ge=1, le=65535, description="端口号")
    description: Optional[str] = Field(None, description="服务器描述")
    platform_type: Optional[str] = Field(None, description="平台类型: maisi/nodered/custom")
    admin_url: Optional[str] = Field(None, description="管理/编辑器地址")
    dashboard_url: Optional[str] = Field(None, description="Dashboard 地址")
    health_check_url: Optional[str] = Field(None, description="自定义健康检查地址")
    is_active: Optional[bool] = Field(None, description="是否启用")
    status: Optional[str] = Field(None, description="状态")
    system_info: Optional[Dict[str, Any]] = Field(None, description="系统信息")
    version_info: Optional[Dict[str, Any]] = Field(None, description="版本信息")
    device_info: Optional[Dict[str, Any]] = Field(None, description="设备信息")

class EdgeServerResponse(EdgeServerBase):
    """边缘服务器响应模型"""
    id: int
    status: str
    last_checked: Optional[datetime]
    system_info: Optional[Dict[str, Any]]
    version_info: Optional[Dict[str, Any]]
    device_info: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EdgeServerListResponse(BaseModel):
    """边缘服务器列表响应模型"""
    total: int
    items: List[EdgeServerResponse]

class EdgeServerStatusUpdate(BaseModel):
    """边缘服务器状态更新模型"""
    status: str = Field(..., description="状态")
    system_info: Optional[Dict[str, Any]] = Field(None, description="系统信息")
    version_info: Optional[Dict[str, Any]] = Field(None, description="版本信息")
    device_info: Optional[Dict[str, Any]] = Field(None, description="设备信息") 


@router.post("/edge-servers", response_model=EdgeServerResponse, tags=["边缘服务"], summary="创建边缘服务器")
async def create_edge_server(
    server_data: EdgeServerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """创建新的边缘服务器"""
    try:
        # 检查IP是否已存在
        existing_server = db.query(EdgeServer).filter(
            and_(
                EdgeServer.ip_address == server_data.ip_address,
                EdgeServer.port == server_data.port
            )
        ).first()
        
        if existing_server:
            raise ValueError(f"服务器 {server_data.ip_address}:{server_data.port} 已存在")
        
        db_server = EdgeServer(
            name=server_data.name,
            ip_address=server_data.ip_address,
            port=server_data.port,
            description=server_data.description,
            platform_type=server_data.platform_type or "maisi",
            admin_url=server_data.admin_url,
            dashboard_url=server_data.dashboard_url,
            health_check_url=server_data.health_check_url,
            is_active=server_data.is_active,
            status="unknown"
        )
        
        db.add(db_server)
        db.commit()
        db.refresh(db_server)
        
        log_action(db, current_user.user_id, "create_edge_server", db_server.name, f"创建边缘服务器成功: {db_server.name} ({db_server.ip_address}:{db_server.port})")
        return db_server
            
    except Exception as e:
        db.rollback()
        raise

@router.get("/edge-servers", response_model=EdgeServerListResponse, tags=["边缘服务"], summary="获取边缘服务器列表")
async def get_edge_servers(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的记录数"),
    status: Optional[str] = Query(None, description="状态筛选"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    db: Session = Depends(get_db)
):
    """获取边缘服务器列表"""
    try:
        servers = db.query(EdgeServer)
        if status:
            servers = servers.filter(EdgeServer.status == status)
        if is_active:
            servers = servers.filter(EdgeServer.is_active == is_active)

        total = servers.count()
        servers = servers.order_by(EdgeServer.created_at.desc()).offset(skip).limit(limit).all()
        
        return EdgeServerListResponse(total=total, items=servers)

    except Exception as e:
        # logger.error(f"获取边缘服务器列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取边缘服务器列表失败")

@router.get("/edge-servers/{server_id}", response_model=EdgeServerResponse, tags=["边缘服务"], summary="获取边缘服务器详情")
async def get_edge_server(
    server_id: int,
    db: Session = Depends(get_db)
):
    """根据ID获取边缘服务器详情"""
    server = db.query(EdgeServer).filter(EdgeServer.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="边缘服务器不存在")
    return server

@router.put("/edge-servers/{server_id}", response_model=EdgeServerResponse, tags=["边缘服务"], summary="更新边缘服务器")
async def update_edge_server(
    server_id: int,
    server_data: EdgeServerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """更新边缘服务器信息"""
    try:
            db_server = db.query(EdgeServer).filter(EdgeServer.id == server_id).first()
            if not db_server:
                return None
            
            # 如果更新IP和端口，检查是否与其他服务器冲突
            if server_data.ip_address or server_data.port:
                new_ip = server_data.ip_address or db_server.ip_address
                new_port = server_data.port or db_server.port
                
                existing_server = db.query(EdgeServer).filter(
                    and_(
                        EdgeServer.ip_address == new_ip,
                        EdgeServer.port == new_port,
                        EdgeServer.id != server_id
                    )
                ).first()
                
                if existing_server:
                    raise ValueError(f"服务器 {new_ip}:{new_port} 已存在")
            
            # 更新字段
            update_data = server_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_server, field, value)
            
            db_server.updated_at = datetime.now()
            db.commit()
            db.refresh(db_server)
            
            log_action(db, current_user.user_id, "update_edge_server", db_server.name, f"更新边缘服务器成功: {db_server.name} ({db_server.ip_address}:{db_server.port})")
            return db_server
            
    except Exception as e:
        db.rollback()
        raise

@router.patch("/edge-servers/{server_id}/status", response_model=EdgeServerResponse, tags=["边缘服务"], summary="更新边缘服务器状态")
async def update_edge_server_status(
    server_id: int,
    status_data: EdgeServerStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """更新边缘服务器状态和系统信息"""
    try:
        db_server = db.query(EdgeServer).filter(EdgeServer.id == server_id).first()
        if not db_server:
            return None
        
        db_server.status = status_data.status
        db_server.last_checked = datetime.now()
        
        if status_data.system_info:
            db_server.system_info = status_data.system_info
        if status_data.version_info:
            db_server.version_info = status_data.version_info
        if status_data.device_info:
            db_server.device_info = status_data.device_info
        
        db_server.updated_at = datetime.now()
        db.commit()
        db.refresh(db_server)
        
        log_action(db, current_user.user_id, "update_edge_server_status", db_server.name, f"更新边缘服务器状态成功: {db_server.name} -> {status_data.status}")
        return db_server
            
    except Exception as e:
        db.rollback()
        raise

@router.delete("/edge-servers/{server_id}", tags=["边缘服务"], summary="删除边缘服务器")
async def delete_edge_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission)
):
    """删除边缘服务器"""
    try:
        db_server = db.query(EdgeServer).filter(EdgeServer.id == server_id).first()
        if not db_server:
            return False
        
        db.delete(db_server)
        db.commit()
        
        log_action(db, current_user.user_id, "delete_edge_server", db_server.name, f"删除边缘服务器成功: {db_server.name} ({db_server.ip_address}:{db_server.port})")
        return True
            
    except Exception as e:
        db.rollback()
        raise

@router.get("/edge-servers/online/list", response_model=List[EdgeServerResponse], tags=["边缘服务"], summary="获取在线边缘服务器")
async def get_online_edge_servers(db: Session = Depends(get_db)):
    """获取所有在线的边缘服务器"""
    try:
        return db.query(EdgeServer).filter(
            and_(
                EdgeServer.status == "online",
                EdgeServer.is_active == True
            )
        ).all()
    except Exception as e:
        # logger.error(f"获取在线边缘服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取在线边缘服务器失败")

@router.get("/edge-servers/status/{status}", response_model=List[EdgeServerResponse], tags=["边缘服务"], summary="根据状态获取边缘服务器")
async def get_edge_servers_by_status(
    status: str,
    db: Session = Depends(get_db)
):
    """根据状态获取边缘服务器列表"""
    try:
        return db.query(EdgeServer).filter(EdgeServer.status == status).all() 
    except Exception as e:
        # logger.error(f"根据状态获取边缘服务器失败: {str(e)}")
        raise HTTPException(status_code=500, detail="根据状态获取边缘服务器失败") 

# 设备抓图API
class DeviceSnapshotRequest(BaseModel):
    device_id: str
    ip_address: str
    device_type: str
    channel: int = 1
    username: str
    password: str

@router.post("/devices/snapshot", tags=["设备管理"], summary="获取设备抓图")
async def get_device_snapshot(
    request: DeviceSnapshotRequest
):
    """
    获取设备抓图
    支持Digest认证和Basic认证
    """
    try:
        
        # 构建设备抓图URL
        if request.device_type.lower() == 'nvr':
            snapshot_url = f"http://{request.ip_address}/cgi-bin/snapshot.cgi?channel={request.channel}&type=0"
        else:
            snapshot_url = f"http://{request.ip_address}/cgi-bin/snapshot.cgi?channel=1&type=0"
        
        # 第一次请求，获取认证信息
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        first_response = requests.get(snapshot_url, headers=headers, timeout=10)

        if first_response.status_code == 200:
            # 如果直接成功，返回图片数据
            return Response(
                content=first_response.content,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"}
            )
        
        elif first_response.status_code == 401:
            # 需要认证
            auth_header = first_response.headers.get('www-authenticate', '')
            
            if 'Digest' in auth_header:
                # Digest认证
                auth_response = await _generate_digest_auth(
                    auth_header, request.username, request.password, 
                    'GET', snapshot_url
                )
                
                # 发送带认证的请求
                auth_headers = {
                    'Authorization': auth_response,
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                auth_response_obj = requests.get(snapshot_url, headers=auth_headers, timeout=10)
                
                if auth_response_obj.status_code == 200:
                    return Response(
                        content=auth_response_obj.content,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"}
                    )
                else:
                    raise HTTPException(
                        status_code=auth_response_obj.status_code,
                        detail=f"Digest认证失败: {auth_response_obj.status_code}"
                    )
            
            elif 'Basic' in auth_header:
                # Basic认证
                credentials = f"{request.username}:{request.password}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                
                basic_headers = {
                    'Authorization': f'Basic {encoded_credentials}',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                basic_response = requests.get(snapshot_url, headers=basic_headers, timeout=10)
                
                if basic_response.status_code == 200:
                    return Response(
                        content=basic_response.content,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"}
                    )
                else:
                    raise HTTPException(
                        status_code=basic_response.status_code,
                        detail=f"Basic认证失败: {basic_response.status_code}"
                    )
            
            else:
                # 尝试Basic认证（某些设备不返回www-authenticate头）
                credentials = f"{request.username}:{request.password}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                
                basic_headers = {
                    'Authorization': f'Basic {encoded_credentials}',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                basic_response = requests.get(snapshot_url, headers=basic_headers, timeout=10)
                
                if basic_response.status_code == 200:
                    return Response(
                        content=basic_response.content,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"}
                    )
                else:
                    raise HTTPException(
                        status_code=basic_response.status_code,
                        detail=f"Basic认证失败: {basic_response.status_code}"
                    )
        
        else:
            # 其他状态码
            raise HTTPException(
                status_code=first_response.status_code,
                detail=f"设备抓图失败: {first_response.status_code}"
            )
            
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=408, detail="请求超时，设备可能离线或网络不通")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="连接失败，设备可能离线或网络不通")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设备抓图失败: {str(e)}")

async def _generate_digest_auth(auth_header: str, username: str, password: str, method: str, uri: str) -> str:
    """
    生成Digest认证响应
    """
    import hashlib
    import re
    
    # 解析认证头
    auth_info = {}
    pattern = r'(\w+)="([^"]*)"'
    matches = re.findall(pattern, auth_header)
    
    for key, value in matches:
        auth_info[key] = value
    
    realm = auth_info.get('realm', '')
    nonce = auth_info.get('nonce', '')
    qop = auth_info.get('qop', '')
    algorithm = auth_info.get('algorithm', 'MD5')
    
    # 生成随机值
    import secrets
    cnonce = secrets.token_hex(8)
    nc = '00000001'
    
    # 计算HA1 = MD5(username:realm:password)
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    
    # 计算HA2 = MD5(method:uri)
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    
    # 计算response
    if qop:
        response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
    else:
        response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    
    # 构建Authorization头
    auth_response = f'Digest username="{username}", realm="{realm}", nonce="{nonce}", uri="{uri}", algorithm={algorithm}, response="{response}"'
    
    if qop:
        auth_response += f', qop={qop}, nc={nc}, cnonce="{cnonce}"'
    
    return auth_response