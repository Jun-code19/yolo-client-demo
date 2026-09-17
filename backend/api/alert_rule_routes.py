"""复合告警规则 API（data-server）"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import check_admin_permission, get_current_user
from api.logger import log_action
from src.alert_rule_common import SUPPORTED_SOURCES, get_eval_interval_sec
from src.database import AlertRule, AlertRuleState, CompositeAlert, Device, User, get_db
from src.env_loader import get_detect_server_url

router = APIRouter(prefix="/alert-rules", tags=["复合告警规则"])


class RuleCondition(BaseModel):
    source: str = Field(..., description="事件源: detection_event / external_event / smart_event")
    label: Optional[str] = Field(None, description="单标签匹配（兼容旧数据）")
    labels: Optional[List[str]] = Field(None, description="多标签匹配（任一命中即可）")
    event_type: Optional[str] = Field(None, description="事件类型")
    scenario_type: Optional[str] = Field(None, description="检测事件场景类型")
    scenario_id: Optional[str] = Field(None, description="检测事件场景 ID")
    analysis_type: Optional[str] = Field(None, description="检测事件分析类型")
    match_mode: Optional[str] = Field(None, description="检测匹配: event / target / absence")
    target_classes: Optional[List[str]] = Field(None, description="目标类别，如 person/car")
    count_op: Optional[str] = Field(None, description="数量比较: gte/gt/eq/lt/lte")
    count_value: Optional[int] = Field(None, description="数量阈值")
    change_direction: Optional[str] = Field(None, description="人数变化: increase/decrease")
    scheme_id: Optional[str] = Field(None, description="事件订阅 scheme ID")
    duration_sec: Optional[int] = Field(0, ge=0, le=86400, description="本条条件持续满足秒数，0=即时")


class RuleDefinition(BaseModel):
    logic: str = Field(default="AND", description="AND / OR")
    same_device: bool = Field(default=True, description="多条件是否要求同一设备")
    window_sec: int = Field(default=300, ge=10, le=86400)
    duration_sec: int = Field(default=0, ge=0, le=86400, description="[兼容] 规则级持续秒数，优先使用 conditions[].duration_sec")
    cooldown_sec: int = Field(default=60, ge=0, le=86400)
    conditions: List[RuleCondition] = Field(default_factory=list)


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: bool = True
    device_id: Optional[str] = None
    definition: RuleDefinition
    priority: int = Field(default=100, ge=0, le=10000)
    push_tags: Optional[str] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    device_id: Optional[str] = None
    definition: Optional[RuleDefinition] = None
    priority: Optional[int] = Field(None, ge=0, le=10000)
    push_tags: Optional[str] = None


class AlertRuleResponse(BaseModel):
    rule_id: str
    name: str
    description: Optional[str]
    enabled: bool
    device_id: Optional[str]
    device_name: Optional[str] = None
    definition: Dict[str, Any]
    priority: int
    push_tags: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompositeAlertResponse(BaseModel):
    alert_id: str
    rule_id: str
    rule_name: Optional[str] = None
    device_id: Optional[str]
    device_name: Optional[str] = None
    involved_devices: List[Dict[str, Any]] = Field(default_factory=list)
    title: str
    summary: Optional[str]
    matched_events: List[Dict[str, Any]]
    definition_snapshot: Optional[Dict[str, Any]]
    status: str
    fired_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


def _collect_alert_device_ids(alert: CompositeAlert) -> List[str]:
    device_ids = set()
    if alert.device_id:
        device_ids.add(alert.device_id)
    for event in alert.matched_events or []:
        if isinstance(event, dict) and event.get("device_id"):
            device_ids.add(str(event["device_id"]))
    return sorted(device_ids)


def _serialize_composite_alert(
    row: CompositeAlert,
    rule_names: Dict[str, str],
    device_names: Dict[str, str],
) -> CompositeAlertResponse:
    involved_ids = _collect_alert_device_ids(row)
    involved_devices = [
        {
            "device_id": device_id,
            "device_name": device_names.get(device_id) or device_id,
        }
        for device_id in involved_ids
    ]
    primary_device_id = row.device_id or (involved_ids[0] if len(involved_ids) == 1 else None)
    return CompositeAlertResponse(
        alert_id=row.alert_id,
        rule_id=row.rule_id,
        rule_name=rule_names.get(row.rule_id),
        device_id=primary_device_id,
        device_name=device_names.get(primary_device_id) if primary_device_id else None,
        involved_devices=involved_devices,
        title=row.title,
        summary=row.summary,
        matched_events=row.matched_events or [],
        definition_snapshot=row.definition_snapshot,
        status=row.status,
        fired_at=row.fired_at,
        created_at=row.created_at,
    )


def _validate_definition(definition: RuleDefinition) -> None:
    if not definition.conditions:
        raise HTTPException(status_code=400, detail="规则至少需要一个条件")
    for cond in definition.conditions:
        if cond.source not in SUPPORTED_SOURCES:
            raise HTTPException(status_code=400, detail=f"不支持的事件源: {cond.source}")


def _serialize_rule(rule: AlertRule, db: Session) -> AlertRuleResponse:
    device_name = None
    if rule.device_id:
        device = db.query(Device).filter(Device.device_id == rule.device_id).first()
        device_name = device.device_name if device else None
    return AlertRuleResponse(
        rule_id=rule.rule_id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        device_id=rule.device_id,
        device_name=device_name,
        definition=rule.definition or {},
        priority=rule.priority or 100,
        push_tags=rule.push_tags,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/meta")
def get_alert_rule_meta():
    return {
        "eval_interval_sec": get_eval_interval_sec(),
        "supported_sources": sorted(SUPPORTED_SOURCES),
        "default_definition": RuleDefinition().model_dump(),
    }


@router.get("", response_model=List[AlertRuleResponse])
def list_alert_rules(
    enabled: Optional[bool] = Query(None),
    device_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(AlertRule).order_by(AlertRule.priority.asc(), AlertRule.created_at.desc())
    if enabled is not None:
        query = query.filter(AlertRule.enabled.is_(enabled))
    if device_id:
        query = query.filter(AlertRule.device_id == device_id)
    rules = query.all()
    return [_serialize_rule(rule, db) for rule in rules]


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    _validate_definition(payload.definition)
    if payload.device_id:
        device = db.query(Device).filter(Device.device_id == payload.device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

    rule = AlertRule(
        rule_id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        device_id=payload.device_id,
        definition=payload.definition.model_dump(),
        priority=payload.priority,
        push_tags=payload.push_tags,
    )
    db.add(rule)
    db.flush()
    db.add(AlertRuleState(rule_id=rule.rule_id, condition_state={}))
    db.commit()
    db.refresh(rule)
    log_action(db, current_user.user_id, "create_alert_rule", rule.rule_id, f"创建复合告警规则: {rule.name}")
    return _serialize_rule(rule, db)


@router.post("/evaluate")
def trigger_evaluate(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    detect_url = get_detect_server_url()
    try:
        resp = requests.post(f"{detect_url}/api/v2/alert-rules/evaluate", timeout=120)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"检测服务评估失败: {exc}") from exc

    stats = payload.get("stats") or {}
    log_action(db, current_user.user_id, "evaluate_alert_rules", "evaluate", "手动触发规则评估")
    return {"success": True, "stats": stats}


@router.get("/alerts/list", response_model=List[CompositeAlertResponse])
def list_composite_alerts(
    rule_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(CompositeAlert).order_by(CompositeAlert.fired_at.desc())
    if rule_id:
        query = query.filter(CompositeAlert.rule_id == rule_id)
    if device_id:
        query = query.filter(CompositeAlert.device_id == device_id)
    if status_filter:
        query = query.filter(CompositeAlert.status == status_filter)
    rows = query.offset(offset).limit(limit).all()

    rule_names = {
        rule.rule_id: rule.name
        for rule in db.query(AlertRule).filter(AlertRule.rule_id.in_({row.rule_id for row in rows})).all()
    }
    all_device_ids = set()
    for row in rows:
        all_device_ids.update(_collect_alert_device_ids(row))
    device_names = {
        device.device_id: device.device_name
        for device in db.query(Device).filter(Device.device_id.in_(all_device_ids)).all()
    } if all_device_ids else {}

    return [
        _serialize_composite_alert(row, rule_names, device_names)
        for row in rows
    ]


@router.patch("/alerts/{alert_id}/status")
def update_composite_alert_status(
    alert_id: str,
    status_value: str = Query(..., alias="status", pattern="^(new|acknowledged|ignored)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(CompositeAlert).filter(CompositeAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警记录不存在")
    alert.status = status_value
    db.commit()
    return {"success": True, "alert_id": alert_id, "status": status_value}


@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = db.query(AlertRule).filter(AlertRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _serialize_rule(rule, db)


@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    rule_id: str,
    payload: AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    rule = db.query(AlertRule).filter(AlertRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    data = payload.model_dump(exclude_unset=True)
    if "definition" in data and data["definition"] is not None:
        definition = RuleDefinition(**data["definition"])
        _validate_definition(definition)
        data["definition"] = definition.model_dump()
    if "device_id" in data and data["device_id"]:
        device = db.query(Device).filter(Device.device_id == data["device_id"]).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

    for key, value in data.items():
        setattr(rule, key, value)
    rule.updated_at = datetime.now()
    db.commit()
    db.refresh(rule)
    log_action(db, current_user.user_id, "update_alert_rule", rule.rule_id, f"更新复合告警规则: {rule.name}")
    return _serialize_rule(rule, db)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    rule = db.query(AlertRule).filter(AlertRule.rule_id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    name = rule.name
    db.delete(rule)
    db.commit()
    log_action(db, current_user.user_id, "delete_alert_rule", rule_id, f"删除复合告警规则: {name}")

