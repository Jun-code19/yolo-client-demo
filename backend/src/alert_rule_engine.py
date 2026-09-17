"""复合告警规则引擎：定时扫描事件表，命中后写入 composite_alert 并推送"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from src.alert_rule_common import (
    DEFAULT_COOLDOWN_SEC,
    DEFAULT_EVAL_INTERVAL_SEC,
    DEFAULT_WINDOW_SEC,
    COUNT_OPS,
    DETECTION_MATCH_MODES,
    SUPPORTED_SOURCES,
    get_eval_interval_sec,
)
from src.database import (
    SessionLocal,
    AlertRule,
    AlertRuleState,
    CompositeAlert,
    DetectionEvent,
    ExternalEvent,
    SmartEvent,
    SmartScheme,
    Device,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizedEvent:
    source: str
    source_id: str
    device_id: Optional[str]
    timestamp: datetime
    labels: List[str] = field(default_factory=list)
    event_type: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


def _parse_definition(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    definition = deepcopy(raw or {})
    definition.setdefault("logic", "AND")
    definition.setdefault("same_device", True)
    definition.setdefault("window_sec", DEFAULT_WINDOW_SEC)
    definition.setdefault("duration_sec", 0)
    definition.setdefault("cooldown_sec", DEFAULT_COOLDOWN_SEC)
    definition.setdefault("conditions", [])
    return definition


def _condition_key(index: int, condition: Dict[str, Any]) -> str:
    source = condition.get("source") or "unknown"
    raw_labels = condition.get("labels")
    if isinstance(raw_labels, list) and raw_labels:
        label = ",".join(sorted(str(x) for x in raw_labels if x))
    else:
        label = condition.get("label") or condition.get("event_type") or ""
    return f"{index}:{source}:{label}"


def _extract_labels_from_findings(findings: Any) -> List[str]:
    labels: List[str] = []
    if not findings:
        return labels
    if isinstance(findings, list):
        for item in findings:
            if isinstance(item, dict):
                for key in ("label", "type", "name", "category"):
                    val = item.get(key)
                    if val:
                        labels.append(str(val))
                        break
            elif item:
                labels.append(str(item))
    elif isinstance(findings, dict):
        for key in ("labels", "items", "findings"):
            nested = findings.get(key)
            if isinstance(nested, list):
                labels.extend(_extract_labels_from_findings(nested))
        for key in ("label", "type", "name"):
            val = findings.get(key)
            if val:
                labels.append(str(val))
    return labels


def _normalize_label(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _labels_match(event_labels: List[str], expected: Optional[str]) -> bool:
    if not expected:
        return True
    target = _normalize_label(expected)
    if not target:
        return True
    normalized = {_normalize_label(x) for x in event_labels if _normalize_label(x)}
    return target in normalized


def _labels_match_condition(event_labels: List[str], condition: Dict[str, Any]) -> bool:
    raw_labels = condition.get("labels")
    if isinstance(raw_labels, list) and raw_labels:
        targets = {_normalize_label(x) for x in raw_labels if _normalize_label(x)}
        if not targets:
            return True
        normalized = {_normalize_label(x) for x in event_labels if _normalize_label(x)}
        return bool(targets & normalized)
    return _labels_match(event_labels, condition.get("label"))


def _infer_scenario_type_from_meta(meta: Optional[Dict[str, Any]]) -> Optional[str]:
    if not meta:
        return None
    explicit = meta.get("scenario_type")
    if explicit:
        return str(explicit)
    analysis = meta.get("analysis_type") or meta.get("analysisType")
    counting = meta.get("counting_type") or meta.get("countingType")
    if analysis == "counting" or counting in ("occupancy", "flow"):
        return "counting"
    meta_event = str(meta.get("event_type") or "")
    if meta_event.startswith("occupancy_"):
        return "counting"
    if meta_event.startswith(("line_cross", "area_")):
        return "behavior"
    return None


def _meta_field_matches(meta: Optional[Dict[str, Any]], key: str, expected: Any) -> bool:
    if expected is None or expected == "":
        return True
    if not meta:
        meta = {}
    actual = meta.get(key)
    if key == "scenario_type" and (actual is None or actual == ""):
        actual = _infer_scenario_type_from_meta(meta)
    if key == "analysis_type" and (actual is None or actual == ""):
        actual = meta.get("analysisType")
    return str(actual) == str(expected)


def _meta_matches(meta: Optional[Dict[str, Any]], condition: Dict[str, Any]) -> bool:
    if not meta:
        meta = {}
    for key in ("scenario_type", "scenario_id", "analysis_type"):
        expected = condition.get(key)
        if expected is None or expected == "":
            continue
        if not _meta_field_matches(meta, key, expected):
            return False
    return True


def _detection_row_type_matches(expected_type: Optional[str], actual_type: Optional[str]) -> bool:
    if not expected_type:
        return True
    if not actual_type:
        return False
    expected = str(expected_type).strip().lower()
    actual = str(actual_type).strip().lower()
    if expected == actual:
        return True
    if expected == "detection":
        return actual in {
            "detection",
            "object_detection",
            "yolo_verify",
            "yolo_analyze",
            "yolo_then_verify",
            "yolo_then_analyze",
        }
    return False


def _detection_meta_event_matches(meta: Optional[Dict[str, Any]], condition: Dict[str, Any], event_labels: List[str]) -> bool:
    expected = condition.get("label")
    if not expected:
        return True
    meta = meta or {}
    meta_event = meta.get("event_type")
    candidates = []
    if meta_event:
        candidates.append(str(meta_event))
    candidates.extend(event_labels or [])
    return _labels_match_condition(candidates, condition)


def _normalize_class_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _class_name_matches(name: str, targets: Set[str]) -> bool:
    normalized = _normalize_class_name(name)
    if not normalized or not targets:
        return False
    if normalized in targets:
        return True
    aliases = {
        "person": {"person", "people", "human", "pedestrian", "人"},
        "car": {"car", "vehicle", "automobile", "truck", "bus", "车", "汽车"},
    }
    for target in targets:
        alias_set = aliases.get(target, {target})
        if normalized in alias_set:
            return True
        for alias in alias_set:
            if alias in normalized or normalized in alias:
                return True
    return False


def _extract_class_counts_from_event(event: NormalizedEvent) -> Dict[str, int]:
    meta = event.payload.get("meta_data") or {}
    raw_counts = meta.get("class_counts")
    if isinstance(raw_counts, dict) and raw_counts:
        return {str(k): int(v or 0) for k, v in raw_counts.items()}

    counts: Dict[str, int] = {}
    bbox = event.payload.get("bounding_box") or []
    if not isinstance(bbox, list):
        return counts
    for det in bbox:
        if not isinstance(det, dict):
            continue
        name = det.get("class_name") or det.get("class") or det.get("label")
        if name is None and det.get("class_id") is not None:
            name = str(det.get("class_id"))
        if not name:
            continue
        key = str(name).strip()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_for_target_classes(event: NormalizedEvent, target_classes: Optional[List[str]]) -> int:
    meta = event.payload.get("meta_data") or {}
    class_counts = _extract_class_counts_from_event(event)
    if not target_classes:
        if class_counts:
            return sum(class_counts.values())
        return int(meta.get("current_count") or 0)

    targets = {_normalize_class_name(item) for item in target_classes if _normalize_class_name(item)}
    if not targets:
        return int(meta.get("current_count") or 0)

    total = 0
    for name, count in class_counts.items():
        if _class_name_matches(name, targets):
            total += int(count or 0)
    return total


def _compare_count_value(actual: int, op: Optional[str], expected: Optional[Any]) -> bool:
    if expected is None or op is None:
        return True
    try:
        target = int(expected)
    except (TypeError, ValueError):
        return False
    operator = str(op).strip().lower()
    if operator in (">=", "gte"):
        return actual >= target
    if operator in ("<=", "lte"):
        return actual <= target
    if operator in (">", "gt"):
        return actual > target
    if operator in ("<", "lt"):
        return actual < target
    if operator in ("=", "==", "eq"):
        return actual == target
    return False


def _detection_match_mode(condition: Dict[str, Any]) -> str:
    mode = str(condition.get("match_mode") or "event").strip().lower()
    if mode not in DETECTION_MATCH_MODES:
        return "event"
    return mode


def _detection_presence_matches(condition: Dict[str, Any], event: NormalizedEvent) -> bool:
    probe = dict(condition)
    probe["match_mode"] = "target"
    if probe.get("count_op") in (None, "") and probe.get("count_value") in (None, ""):
        probe["count_op"] = "gte"
        probe["count_value"] = 1
    return _detection_target_matches(probe, event)


def _detection_target_matches(condition: Dict[str, Any], event: NormalizedEvent) -> bool:
    if not _detection_row_type_matches(condition.get("event_type"), event.event_type):
        return False
    meta = event.payload.get("meta_data") or {}
    if not _meta_matches(meta, condition):
        return False

    mode = _detection_match_mode(condition)
    if mode == "absence":
        return False

    if mode == "target":
        meta = event.payload.get("meta_data") or {}
        change_dir = condition.get("change_direction")
        if change_dir in ("increase", "decrease"):
            expected = f"occupancy_change_{change_dir}"
            return _normalize_label(meta.get("event_type")) == _normalize_label(expected)
        count = _count_for_target_classes(event, condition.get("target_classes"))
        if condition.get("count_op") in (None, "") and condition.get("count_value") in (None, ""):
            return count >= 1
        return _compare_count_value(count, condition.get("count_op"), condition.get("count_value"))

    return _detection_meta_event_matches(meta, condition, event.labels)


def _absence_condition_satisfied(
    condition: Dict[str, Any],
    scoped_events: List[NormalizedEvent],
    condition_state: Dict[str, Any],
    cond_key: str,
    now: datetime,
    duration_sec: float,
) -> Tuple[bool, Dict[str, Any]]:
    state = deepcopy(condition_state or {})
    entry = dict(state.get(cond_key) or {})
    duration_sec = float(duration_sec or 0)
    if duration_sec <= 0:
        entry["last_positive"] = None
        entry["absence_since"] = None
        state[cond_key] = entry
        return False, state

    positives = [
        event for event in scoped_events
        if _detection_presence_matches(condition, event)
    ]
    if positives:
        last_positive = max(event.timestamp for event in positives)
        entry["last_positive"] = last_positive.isoformat()
        entry["absence_since"] = None
        state[cond_key] = entry
        return False, state

    last_positive_raw = entry.get("last_positive")
    if last_positive_raw:
        last_positive = datetime.fromisoformat(last_positive_raw)
        elapsed = (now - last_positive).total_seconds()
        state[cond_key] = entry
        return elapsed >= duration_sec, state

    absence_since_raw = entry.get("absence_since")
    if not absence_since_raw:
        entry["absence_since"] = now.isoformat()
        state[cond_key] = entry
        return False, state

    absence_since = datetime.fromisoformat(absence_since_raw)
    state[cond_key] = entry
    return (now - absence_since).total_seconds() >= duration_sec, state


def _condition_duration_sec(condition: Dict[str, Any], definition: Dict[str, Any]) -> float:
    if "duration_sec" in condition and condition.get("duration_sec") is not None:
        try:
            return max(0.0, float(condition.get("duration_sec")))
        except (TypeError, ValueError):
            pass
    try:
        return max(0.0, float(definition.get("duration_sec") or 0))
    except (TypeError, ValueError):
        return 0.0


def _max_rule_duration_sec(definition: Dict[str, Any]) -> float:
    conditions = definition.get("conditions") or []
    if not conditions:
        try:
            return max(0.0, float(definition.get("duration_sec") or 0))
        except (TypeError, ValueError):
            return 0.0
    return max(_condition_duration_sec(cond, definition) for cond in conditions)


def _fetch_detection_events(
    db: Session,
    since: datetime,
    device_id: Optional[str],
) -> List[NormalizedEvent]:
    query = db.query(DetectionEvent).filter(DetectionEvent.timestamp >= since)
    if device_id:
        query = query.filter(DetectionEvent.device_id == device_id)
    rows = query.order_by(DetectionEvent.timestamp.asc()).all()
    events: List[NormalizedEvent] = []
    for row in rows:
        meta = row.meta_data if isinstance(row.meta_data, dict) else {}
        labels = []
        for key in ("scenario_type", "analysis_type", "event_type", "pushLabel"):
            val = meta.get(key)
            if val:
                labels.append(str(val))
        if row.event_type:
            labels.append(str(row.event_type))
        events.append(
            NormalizedEvent(
                source="detection_event",
                source_id=row.event_id,
                device_id=row.device_id,
                timestamp=row.timestamp,
                labels=labels,
                event_type=row.event_type,
                payload={
                    "config_id": row.config_id,
                    "confidence": row.confidence,
                    "meta_data": meta,
                    "location": row.location,
                    "bounding_box": row.bounding_box if isinstance(row.bounding_box, list) else [],
                },
            )
        )
    return events


def _fetch_external_events(
    db: Session,
    since: datetime,
    device_id: Optional[str],
) -> List[NormalizedEvent]:
    query = db.query(ExternalEvent).filter(ExternalEvent.timestamp >= since)
    if device_id:
        query = query.filter(ExternalEvent.device_id == device_id)
    rows = query.order_by(ExternalEvent.timestamp.asc()).all()
    events: List[NormalizedEvent] = []
    for row in rows:
        event_type = row.event_type.value if row.event_type else None
        labels = [event_type] if event_type else []
        if row.engine_name:
            labels.append(str(row.engine_name))
        events.append(
            NormalizedEvent(
                source="external_event",
                source_id=row.event_id,
                device_id=row.device_id,
                timestamp=row.timestamp,
                labels=labels,
                event_type=event_type,
                payload={
                    "config_id": row.config_id,
                    "device_sn": row.device_sn,
                    "device_name": row.device_name,
                    "normalized_data": row.normalized_data,
                    "original_data": row.original_data,
                },
            )
        )
    return events


def _fetch_smart_events(
    db: Session,
    since: datetime,
    device_id: Optional[str],
) -> List[NormalizedEvent]:
    query = (
        db.query(SmartEvent, SmartScheme.camera_id)
        .join(SmartScheme, SmartEvent.scheme_id == SmartScheme.id)
        .filter(SmartEvent.timestamp >= since)
    )
    if device_id:
        query = query.filter(SmartScheme.camera_id == device_id)
    rows = query.order_by(SmartEvent.timestamp.asc()).all()
    events: List[NormalizedEvent] = []
    for event, camera_id in rows:
        labels = [event.event_type] if event.event_type else []
        events.append(
            NormalizedEvent(
                source="smart_event",
                source_id=event.id,
                device_id=camera_id,
                timestamp=event.timestamp,
                labels=labels,
                event_type=event.event_type,
                payload={
                    "scheme_id": event.scheme_id,
                    "title": event.title,
                    "description": event.description,
                    "priority": event.priority,
                    "event_data": event.event_data,
                },
            )
        )
    return events


def _fetch_events_for_rule(
    db: Session,
    definition: Dict[str, Any],
    rule_device_id: Optional[str],
    since: datetime,
) -> List[NormalizedEvent]:
    sources_needed: Set[str] = set()
    for cond in definition.get("conditions") or []:
        source = cond.get("source")
        if source in SUPPORTED_SOURCES:
            sources_needed.add(source)

    events: List[NormalizedEvent] = []
    if "detection_event" in sources_needed:
        events.extend(_fetch_detection_events(db, since, rule_device_id))
    if "external_event" in sources_needed:
        events.extend(_fetch_external_events(db, since, rule_device_id))
    if "smart_event" in sources_needed:
        events.extend(_fetch_smart_events(db, since, rule_device_id))

    events.sort(key=lambda item: item.timestamp)
    return events


def _condition_matches(condition: Dict[str, Any], event: NormalizedEvent) -> bool:
    source = condition.get("source")
    if event.source != source:
        return False

    if source == "detection_event":
        mode = _detection_match_mode(condition)
        if mode == "absence":
            return False
        return _detection_target_matches(condition, event)

    if source == "external_event":
        expected_type = condition.get("event_type")
        if expected_type and event.event_type != expected_type:
            return False
        return _labels_match_condition(event.labels, condition)

    if source == "smart_event":
        expected_type = condition.get("event_type")
        if expected_type and event.event_type != expected_type:
            return False
        scheme_id = condition.get("scheme_id")
        if scheme_id and str(event.payload.get("scheme_id")) != str(scheme_id):
            return False
        return _labels_match_condition(event.labels, condition)

    return False


def _filter_matches(
    condition: Dict[str, Any],
    events: List[NormalizedEvent],
    window_start: datetime,
    logic: str = "AND",
    event_cursor: Optional[datetime] = None,
) -> List[NormalizedEvent]:
    if str(logic or "AND").upper() == "OR":
        cursor = event_cursor or datetime.min
        return [
            event
            for event in events
            if event.timestamp > cursor and _condition_matches(condition, event)
        ]
    return [
        event
        for event in events
        if event.timestamp >= window_start and _condition_matches(condition, event)
    ]


def _group_device_ids(events: List[NormalizedEvent], same_device: bool) -> List[Optional[str]]:
    if not same_device:
        return [None]
    device_ids = sorted({event.device_id for event in events if event.device_id})
    return device_ids or [None]


def _event_to_dict(event: NormalizedEvent) -> Dict[str, Any]:
    return {
        "source": event.source,
        "source_id": event.source_id,
        "device_id": event.device_id,
        "timestamp": event.timestamp.isoformat(),
        "labels": event.labels,
        "event_type": event.event_type,
        "payload": event.payload,
    }


def _duration_satisfied(
    matched: List[NormalizedEvent],
    duration_sec: float,
    condition_state: Dict[str, Any],
    cond_key: str,
    now: datetime,
) -> Tuple[bool, Dict[str, Any]]:
    state = deepcopy(condition_state or {})
    entry = dict(state.get(cond_key) or {})

    if duration_sec <= 0:
        entry["since"] = None
        state[cond_key] = entry
        return bool(matched), state

    if not matched:
        entry["since"] = None
        state[cond_key] = entry
        return False, state

    first_ts = min(event.timestamp for event in matched)
    last_ts = max(event.timestamp for event in matched)
    since_raw = entry.get("since")
    since_dt = datetime.fromisoformat(since_raw) if since_raw else first_ts
    if since_dt > first_ts:
        since_dt = first_ts
    entry["since"] = since_dt.isoformat()
    entry["last_match"] = last_ts.isoformat()
    state[cond_key] = entry

    span_sec = (last_ts - since_dt).total_seconds()
    if span_sec >= duration_sec:
        return True, state
    if (now - since_dt).total_seconds() >= duration_sec and len(matched) >= 1:
        return True, state
    return False, state


def _evaluate_for_device(
    definition: Dict[str, Any],
    events: List[NormalizedEvent],
    device_id: Optional[str],
    condition_state: Dict[str, Any],
    now: datetime,
    event_cursor: Optional[datetime] = None,
) -> Tuple[bool, List[NormalizedEvent], Dict[str, Any]]:
    conditions = definition.get("conditions") or []
    if not conditions:
        return False, [], condition_state

    logic = str(definition.get("logic") or "AND").upper()
    window_sec = float(definition.get("window_sec") or DEFAULT_WINDOW_SEC)
    window_start = now - timedelta(seconds=window_sec)

    scoped_events = events
    if device_id is not None:
        scoped_events = [event for event in events if event.device_id == device_id]

    per_condition_matches: List[List[NormalizedEvent]] = []
    per_condition_ok: List[bool] = []
    new_state = deepcopy(condition_state or {})

    for index, condition in enumerate(conditions):
        cond_key = _condition_key(index, condition)
        cond_duration_sec = _condition_duration_sec(condition, definition)
        if (
            condition.get("source") == "detection_event"
            and _detection_match_mode(condition) == "absence"
        ):
            ok, new_state = _absence_condition_satisfied(
                condition,
                scoped_events,
                new_state,
                cond_key,
                now,
                cond_duration_sec,
            )
            per_condition_ok.append(ok)
            per_condition_matches.append([])
            if not ok and logic == "AND":
                return False, [], new_state
            continue

        matched = _filter_matches(condition, scoped_events, window_start, logic, event_cursor)
        ok, new_state = _duration_satisfied(matched, cond_duration_sec, new_state, cond_key, now)
        per_condition_ok.append(ok)
        if not ok:
            per_condition_matches.append([])
            if logic == "AND":
                return False, [], new_state
            continue
        per_condition_matches.append(matched)

    if logic == "OR":
        any_hit = any(per_condition_ok)
        merged: List[NormalizedEvent] = []
        seen: Set[str] = set()
        for group in per_condition_matches:
            for event in group:
                if event.source_id in seen:
                    continue
                seen.add(event.source_id)
                merged.append(event)
        return any_hit, merged, new_state

    if not all(per_condition_ok):
        return False, [], new_state

    merged: List[NormalizedEvent] = []
    seen: Set[str] = set()
    for group in per_condition_matches:
        for event in group:
            if event.source_id in seen:
                continue
            seen.add(event.source_id)
            merged.append(event)
    return True, merged, new_state


def _ensure_rule_state(db: Session, rule_id: str) -> AlertRuleState:
    state = db.query(AlertRuleState).filter(AlertRuleState.rule_id == rule_id).first()
    if state:
        return state
    state = AlertRuleState(rule_id=rule_id, condition_state={})
    db.add(state)
    db.flush()
    return state


def _build_alert_title(rule: AlertRule, device_id: Optional[str], device_ids: Optional[List[str]] = None) -> str:
    if device_id:
        device_part = device_id
    elif device_ids and len(device_ids) > 1:
        device_part = f"{len(device_ids)}台设备"
    else:
        device_part = "全局"
    return f"{rule.name} @ {device_part}"


def _parse_push_tags(rule: AlertRule, device_id: Optional[str]) -> List[str]:
    tags: List[str] = []
    raw = (rule.push_tags or "").replace("，", ",")
    for part in raw.split(","):
        text = part.strip()
        if text and text not in tags:
            tags.append(text)
    for extra in ("composite_alert", f"rule_{rule.rule_id}"):
        if extra not in tags:
            tags.append(extra)
    if device_id and f"device_{device_id}" not in tags:
        tags.append(f"device_{device_id}")
    return tags


def _summarize_matched_events(matched: List[NormalizedEvent], limit: int = 8) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for event in matched[:limit]:
        items.append(
            {
                "source": event.source,
                "source_id": event.source_id,
                "device_id": event.device_id,
                "event_type": event.event_type,
                "labels": event.labels[:5],
                "timestamp": event.timestamp.isoformat(),
            }
        )
    if len(matched) > limit:
        items.append({"truncated": True, "total": len(matched)})
    return items


def _load_push_image(session: Session, matched: List[NormalizedEvent]):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    for event in matched:
        if event.source == "detection_event":
            row = (
                session.query(DetectionEvent)
                .filter(DetectionEvent.event_id == event.source_id)
                .first()
            )
            if not row:
                continue
            if row.thumbnail_data:
                arr = np.frombuffer(row.thumbnail_data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            if row.thumbnail_path and os.path.isfile(row.thumbnail_path):
                img = cv2.imread(row.thumbnail_path)
                if img is not None:
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return None


def _push_composite_alert(
    session: Session,
    rule: AlertRule,
    alert: CompositeAlert,
    device_id: Optional[str],
    matched: List[NormalizedEvent],
) -> bool:
    try:
        from src.data_pusher import data_pusher
    except ImportError:
        logger.debug("data_pusher 不可用，跳过复合告警推送")
        return False

    if not data_pusher.push_configs:
        return False

    tags = _parse_push_tags(rule, device_id)
    device = None
    if device_id:
        device = session.query(Device).filter(Device.device_id == device_id).first()

    camera_info = ""
    location = ""
    if device:
        camera_info = f"{device.device_name or device.device_id}:{device.ip_address or ''}"
        location = device.location or ""

    push_payload = {
        "event_type": "composite_alert",
        "alert_id": alert.alert_id,
        "rule_id": rule.rule_id,
        "rule_name": rule.name,
        "deviceId": device_id or "",
        "cameraInfo": camera_info,
        "location": location,
        "recordTime": alert.fired_at.isoformat() + "+08:00",
        "title": alert.title,
        "summary": alert.summary or "",
        "matched_count": len(matched),
        "matched_events": _summarize_matched_events(matched),
        "logic": (alert.definition_snapshot or {}).get("logic"),
        "event_description": f"复合告警: {rule.name}",
    }

    image = _load_push_image(session, matched)
    data_pusher.push_data(data=push_payload, image=image, tags=tags)
    logger.info(
        "复合告警已推送 rule=%s alert=%s device=%s tags=%s",
        rule.rule_id,
        alert.alert_id,
        device_id,
        tags,
    )
    return True


def evaluate_rules(db: Optional[Session] = None, push_enabled: bool = True) -> Dict[str, Any]:
    """评估所有启用规则，命中写入 composite_alert"""
    own_session = db is None
    session = db or SessionLocal()
    stats = {"evaluated": 0, "fired": 0, "pushed": 0, "skipped_cooldown": 0, "errors": 0}

    try:
        now = datetime.now()
        rules = (
            session.query(AlertRule)
            .filter(AlertRule.enabled.is_(True))
            .order_by(AlertRule.priority.asc(), AlertRule.created_at.asc())
            .all()
        )

        for rule in rules:
            stats["evaluated"] += 1
            try:
                definition = _parse_definition(rule.definition if isinstance(rule.definition, dict) else {})
                conditions = definition.get("conditions") or []
                if not conditions:
                    continue

                state = _ensure_rule_state(session, rule.rule_id)
                cooldown_sec = float(definition.get("cooldown_sec") or DEFAULT_COOLDOWN_SEC)
                if state.last_fired_at and (now - state.last_fired_at).total_seconds() < cooldown_sec:
                    stats["skipped_cooldown"] += 1
                    continue

                window_sec = float(definition.get("window_sec") or DEFAULT_WINDOW_SEC)
                max_duration_sec = _max_rule_duration_sec(definition)
                lookback_sec = max(window_sec, max_duration_sec, get_eval_interval_sec() * 2, 120)
                since = now - timedelta(seconds=lookback_sec)
                if state.watermark and state.watermark > since:
                    since = state.watermark - timedelta(seconds=lookback_sec)

                events = _fetch_events_for_rule(session, definition, rule.device_id, since)
                if not events:
                    state.watermark = now
                    state.updated_at = now
                    continue

                same_device = bool(definition.get("same_device", True))
                device_ids = _group_device_ids(events, same_device)

                event_cursor = state.watermark
                fired_any = False
                for device_id in device_ids:
                    hit, matched, new_condition_state = _evaluate_for_device(
                        definition,
                        events,
                        device_id,
                        state.condition_state or {},
                        now,
                        event_cursor=event_cursor,
                    )
                    state.condition_state = new_condition_state
                    if not hit or not matched:
                        continue

                    matched_device_ids = sorted({event.device_id for event in matched if event.device_id})
                    summary = f"规则 {rule.name} 命中，匹配 {len(matched)} 条事件"
                    if len(matched_device_ids) == 1:
                        device_id = matched_device_ids[0]
                    elif len(matched_device_ids) > 1:
                        device_id = None
                        summary += f"，涉及 {len(matched_device_ids)} 台设备"
                    else:
                        device_id = device_ids[0] if len(device_ids) == 1 else None

                    alert = CompositeAlert(
                        alert_id=str(uuid.uuid4()),
                        rule_id=rule.rule_id,
                        device_id=device_id,
                        title=_build_alert_title(rule, device_id, matched_device_ids),
                        summary=summary,
                        matched_events=[_event_to_dict(event) for event in matched],
                        definition_snapshot=definition,
                        status="new",
                        fired_at=now,
                    )
                    session.add(alert)
                    session.flush()
                    if push_enabled:
                        try:
                            if _push_composite_alert(session, rule, alert, device_id, matched):
                                stats["pushed"] += 1
                        except Exception as push_exc:
                            logger.error(
                                "复合告警推送失败 rule=%s alert=%s: %s",
                                rule.rule_id,
                                alert.alert_id,
                                push_exc,
                            )
                    state.last_fired_at = now
                    state.condition_state = {}
                    fired_any = True
                    stats["fired"] += 1
                    logger.info(
                        "复合告警命中 rule=%s device=%s matched=%s",
                        rule.rule_id,
                        device_id,
                        len(matched),
                    )
                    break

                state.watermark = max(event.timestamp for event in events)
                state.updated_at = now
                if fired_any:
                    continue

            except Exception as exc:
                stats["errors"] += 1
                logger.exception("评估规则失败 rule=%s: %s", rule.rule_id, exc)

        session.commit()
        return stats
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


class AlertRuleScheduler:
    """detect-server 后台定时评估"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.lock = threading.RLock()
        self._job_id = "alert_rule_evaluator"

    def start(self) -> None:
        interval = get_eval_interval_sec()
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
        if not self.scheduler.running:
            self.scheduler.start()
        self.scheduler.add_job(
            self._run_safe,
            trigger=IntervalTrigger(seconds=interval),
            id=self._job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("复合告警规则调度器已启动，间隔 %ss", interval)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("复合告警规则调度器已停止")

    def _run_safe(self) -> None:
        with self.lock:
            try:
                stats = evaluate_rules()
                logger.debug("规则评估完成: %s", stats)
            except Exception as exc:
                logger.error("规则评估任务异常: %s", exc)


alert_rule_scheduler = AlertRuleScheduler()
