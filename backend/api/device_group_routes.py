"""设备分组 API"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from api.auth import get_current_user
from api.logger import log_action
from src.database import (
    CrowdAnalysisJob,
    DetectionConfig,
    Device,
    DeviceGroup,
    User,
    get_db,
)

router = APIRouter(prefix="/device-groups", tags=["设备分组"])


class DeviceGroupCreate(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    sort_order: int = 0


class DeviceGroupUpdate(BaseModel):
    group_name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    sort_order: Optional[int] = None


class AssignDevicesBody(BaseModel):
    device_ids: List[str] = Field(default_factory=list)


def _serialize_device(device: Device) -> Dict[str, Any]:
    return {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "ip_address": device.ip_address,
        "port": device.port,
        "username": device.username,
        "password": device.password,
        "channel": device.channel,
        "stream_type": device.stream_type,
        "rtsp_url_mode": device.rtsp_url_mode,
        "rtsp_url": device.rtsp_url,
        "location": device.location,
        "area": device.area,
        "group_id": device.group_id,
        "group_name": device.device_group.group_name if device.device_group else None,
        "status": device.status,
        "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
        "area_coordinates": device.area_coordinates,
    }


def _serialize_group(group: Optional[DeviceGroup], devices: List[Device]) -> Dict[str, Any]:
    if group is None:
        return {
            "group_id": None,
            "group_name": "未分组",
            "description": None,
            "sort_order": 999999,
            "device_count": len(devices),
            "devices": [_serialize_device(d) for d in devices],
        }
    return {
        "group_id": group.group_id,
        "group_name": group.group_name,
        "description": group.description,
        "sort_order": group.sort_order or 0,
        "device_count": len(devices),
        "devices": [_serialize_device(d) for d in devices],
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "updated_at": group.updated_at.isoformat() if group.updated_at else None,
    }


@router.get("")
async def list_device_groups(db: Session = Depends(get_db)):
    groups = db.query(DeviceGroup).order_by(DeviceGroup.sort_order.asc(), DeviceGroup.group_name.asc()).all()
    return {
        "status": "success",
        "data": [
            {
                "group_id": g.group_id,
                "group_name": g.group_name,
                "description": g.description,
                "sort_order": g.sort_order or 0,
                "device_count": len(g.devices or []),
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            }
            for g in groups
        ],
    }


@router.get("/overview")
async def get_groups_overview(
    device_type: Optional[str] = Query(None),
    status: Optional[bool] = Query(None),
    device_name: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """分组视图：按组聚合全部设备（含未分组）"""
    query = db.query(Device).options(joinedload(Device.device_group))
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if status is not None:
        query = query.filter(Device.status == status)
    if device_name:
        query = query.filter(Device.device_name.ilike(f"%{device_name}%"))
    if location:
        query = query.filter(Device.location.ilike(f"%{location}%"))

    devices = query.order_by(Device.device_name.asc()).all()
    groups = db.query(DeviceGroup).order_by(DeviceGroup.sort_order.asc(), DeviceGroup.group_name.asc()).all()

    grouped: Dict[Optional[str], List[Device]] = {g.group_id: [] for g in groups}
    ungrouped: List[Device] = []

    for device in devices:
        if device.group_id and device.group_id in grouped:
            grouped[device.group_id].append(device)
        else:
            ungrouped.append(device)

    result = [_serialize_group(g, grouped.get(g.group_id, [])) for g in groups]
    if ungrouped:
        result.append(_serialize_group(None, ungrouped))

    return {"status": "success", "data": result, "total_devices": len(devices)}


@router.post("")
async def create_device_group(
    body: DeviceGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exists = db.query(DeviceGroup).filter(DeviceGroup.group_name == body.group_name.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="分组名称已存在")

    group = DeviceGroup(
        group_id=str(uuid.uuid4()),
        group_name=body.group_name.strip(),
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    log_action(db, current_user.user_id, "create_device_group", group.group_id, f"创建设备组 {group.group_name}")
    return {"status": "success", "data": _serialize_group(group, [])}


@router.put("/{group_id}")
async def update_device_group(
    group_id: str,
    body: DeviceGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(DeviceGroup).filter(DeviceGroup.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    if body.group_name is not None:
        name = body.group_name.strip()
        conflict = (
            db.query(DeviceGroup)
            .filter(DeviceGroup.group_name == name, DeviceGroup.group_id != group_id)
            .first()
        )
        if conflict:
            raise HTTPException(status_code=400, detail="分组名称已存在")
        group.group_name = name

    if body.description is not None:
        group.description = body.description
    if body.sort_order is not None:
        group.sort_order = body.sort_order
    group.updated_at = datetime.now()

    db.commit()
    db.refresh(group)
    log_action(db, current_user.user_id, "update_device_group", group_id, f"更新设备组 {group.group_name}")
    devices = db.query(Device).filter(Device.group_id == group_id).all()
    return {"status": "success", "data": _serialize_group(group, devices)}


@router.delete("/{group_id}")
async def delete_device_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(DeviceGroup).filter(DeviceGroup.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")

    name = group.group_name
    # 解除所有外键引用，否则 PostgreSQL 会阻止删除分组
    db.query(Device).filter(Device.group_id == group_id).update(
        {Device.group_id: None}, synchronize_session=False
    )
    db.query(DetectionConfig).filter(DetectionConfig.group_id == group_id).update(
        {DetectionConfig.group_id: None, DetectionConfig.enabled: False},
        synchronize_session=False,
    )
    db.query(CrowdAnalysisJob).filter(CrowdAnalysisJob.group_id == group_id).update(
        {CrowdAnalysisJob.group_id: None, CrowdAnalysisJob.is_active: False},
        synchronize_session=False,
    )
    db.delete(group)
    db.commit()
    log_action(db, current_user.user_id, "delete_device_group", group_id, f"删除设备组 {name}")
    return {
        "status": "success",
        "message": "分组已删除，组内设备已移至未分组；引用该分组的检测/分析任务已解除关联并停用",
    }


@router.post("/{group_id}/assign")
async def assign_devices_to_group(
    group_id: str,
    body: AssignDevicesBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if group_id != "__ungrouped__":
        group = db.query(DeviceGroup).filter(DeviceGroup.group_id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        target_group_id = group_id
        group_name = group.group_name
    else:
        target_group_id = None
        group_name = "未分组"

    updated = 0
    for device_id in body.device_ids:
        device = db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            continue
        device.group_id = target_group_id
        updated += 1

    db.commit()
    log_action(
        db,
        current_user.user_id,
        "assign_device_group",
        group_id,
        f"将 {updated} 个设备分配到 {group_name}",
    )
    return {"status": "success", "updated_count": updated}
