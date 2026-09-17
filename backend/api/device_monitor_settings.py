"""设备监控平台配置 API（存 platform_settings，检测服务读取）"""
from copy import deepcopy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import check_admin_permission, get_current_user
from api.logger import log_action
from src.device_monitor_config import DEFAULT_DEVICE_MONITOR_CONFIG, load_device_monitor_config
from src.database import PlatformSetting, User, get_db

SETTING_KEY = "device_monitor"

router = APIRouter(tags=["设备监控配置"])


class DeviceTypeMethods(BaseModel):
    camera: List[str] = Field(default_factory=lambda: ["rtsp", "tcp"])
    nvr: List[str] = Field(default_factory=lambda: ["rtsp", "tcp"])
    edge_server: List[str] = Field(default_factory=lambda: ["tcp", "http_dahua"])
    storage_node: List[str] = Field(default_factory=lambda: ["tcp"])
    default: List[str] = Field(default_factory=lambda: ["rtsp", "tcp", "http_dahua"])


class DeviceMonitorSettingsModel(BaseModel):
    check_interval: int = Field(default=300, ge=30, le=86400)
    offline_threshold: int = Field(default=3, ge=1, le=20)
    retry_count: int = Field(default=3, ge=1, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.0, le=30.0)
    per_device_delay_seconds: float = Field(default=0.2, ge=0.0, le=5.0)
    rtsp_timeout_seconds: float = Field(default=6.0, ge=2.0, le=60.0)
    tcp_timeout_seconds: float = Field(default=3.0, ge=1.0, le=30.0)
    http_timeout_seconds: float = Field(default=3.0, ge=1.0, le=30.0)
    enable_ping: bool = False
    rtsp_stream_for_probe: str = Field(default="sub", pattern="^(main|sub)$")
    http_dahua_path: str = "/cgi-bin/api/tcpConnect/tcpTest"
    http_dahua_port: int = Field(default=80, ge=1, le=65535)
    default_methods_by_type: DeviceTypeMethods = Field(default_factory=DeviceTypeMethods)


def _defaults_dict() -> Dict[str, Any]:
    base = deepcopy(DEFAULT_DEVICE_MONITOR_CONFIG)
    return {
        "check_interval": base["check_interval"],
        "offline_threshold": base["offline_threshold"],
        "retry_count": base["retry_count"],
        "retry_delay_seconds": base["retry_delay_seconds"],
        "per_device_delay_seconds": base["per_device_delay_seconds"],
        "rtsp_timeout_seconds": base["rtsp_timeout_seconds"],
        "tcp_timeout_seconds": base["tcp_timeout_seconds"],
        "http_timeout_seconds": base["http_timeout_seconds"],
        "enable_ping": base["enable_ping"],
        "rtsp_stream_for_probe": base["rtsp_stream_for_probe"],
        "http_dahua_path": base["http_dahua_path"],
        "http_dahua_port": base["http_dahua_port"],
        "default_methods_by_type": deepcopy(base["default_methods_by_type"]),
    }


def _merge_stored(stored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = _defaults_dict()
    if not stored:
        return merged
    for key, value in stored.items():
        if key in ("push_interval", "enable_push", "push_tags", "enable_notifications"):
            continue
        if key == "default_methods_by_type" and isinstance(value, dict):
            merged[key].update(value)
        elif key in merged:
            merged[key] = value
    return merged


def _load_settings(db: Session) -> Dict[str, Any]:
    row = db.query(PlatformSetting).filter(PlatformSetting.setting_key == SETTING_KEY).first()
    if row and isinstance(row.setting_value, dict):
        return _merge_stored(row.setting_value)
    return load_device_monitor_config(db)


def _save_settings(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = db.query(PlatformSetting).filter(PlatformSetting.setting_key == SETTING_KEY).first()
    if row:
        row.setting_value = payload
    else:
        row = PlatformSetting(setting_key=SETTING_KEY, setting_value=payload)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row.setting_value


@router.get("/settings/device-monitor")
def get_device_monitor_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"success": True, "data": _load_settings(db)}


@router.put("/settings/device-monitor")
def save_device_monitor_settings(
    body: DeviceMonitorSettingsModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    payload = body.model_dump()
    saved = _save_settings(db, payload)
    log_action(
        db,
        current_user.user_id,
        "update_system_config",
        SETTING_KEY,
        "更新设备监控配置",
    )
    return {"success": True, "data": saved}
