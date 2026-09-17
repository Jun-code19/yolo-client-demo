"""检测运行时段与图片检测间隔配置"""
from datetime import datetime
from typing import Any, Dict, List, Optional


def _get_attr(source: Any, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _time_str_to_minutes(value: str) -> int:
    if not value or ":" not in value:
        return 0
    hour, minute = value.split(":", 1)
    total = int(hour) * 60 + int(minute)
    return min(total, 24 * 60)


def _is_minute_in_range(current_minute: int, start: str, end: str) -> bool:
    start_minute = _time_str_to_minutes(start)
    end_minute = _time_str_to_minutes(end)
    if start_minute == end_minute:
        return True
    if start_minute < end_minute:
        return start_minute <= current_minute < end_minute
    return current_minute >= start_minute or current_minute < end_minute


def _weekday_key(now: datetime) -> str:
    """将 datetime.weekday() 映射为前端周计划键：0=周日 ... 6=周六"""
    return str((now.weekday() + 1) % 7)


def extract_runtime_config(schedule_config: Any) -> Dict[str, Any]:
    """从 schedule_config 中提取 realtime/manual 的运行配置"""
    if not schedule_config or not isinstance(schedule_config, dict):
        return {}
    runtime = schedule_config.get("runtime")
    if not isinstance(runtime, dict):
        return {}
    return runtime


def is_within_active_period(now: datetime, runtime: Optional[Dict[str, Any]]) -> bool:
    """判断当前时间是否处于配置的生效时段内"""
    runtime = runtime or {}
    mode = runtime.get("time_period_mode") or "all"
    if mode == "all":
        return True

    current_minute = now.hour * 60 + now.minute

    if mode == "weekly":
        weekly = runtime.get("weekly_schedule") or {}
        day_key = _weekday_key(now)
        ranges: List[Dict[str, str]] = weekly.get(day_key) or weekly.get(str(day_key)) or []
        if not ranges:
            return False
        return any(
            _is_minute_in_range(current_minute, item.get("start", "00:00"), item.get("end", "24:00"))
            for item in ranges
            if item.get("start") and item.get("end")
        )

    if mode == "day_night":
        scope = runtime.get("day_night_scope") or "both"
        day_start = runtime.get("day_start") or "08:00"
        day_end = runtime.get("day_end") or "20:00"
        night_start = runtime.get("night_start") or "20:00"
        night_end = runtime.get("night_end") or "08:00"
        in_day = _is_minute_in_range(current_minute, day_start, day_end)
        in_night = _is_minute_in_range(current_minute, night_start, night_end)
        if scope == "day":
            return in_day
        if scope == "night":
            return in_night
        return in_day or in_night

    if mode == "custom":
        ranges = runtime.get("custom_ranges") or []
        if not ranges:
            return True
        return any(
            _is_minute_in_range(current_minute, item.get("start", "00:00"), item.get("end", "23:59"))
            for item in ranges
            if item.get("start") and item.get("end")
        )

    return True


def get_frame_interval(runtime: Optional[Dict[str, Any]], default: float = 5.0) -> float:
    runtime = runtime or {}
    try:
        interval = float(runtime.get("frame_interval", default))
    except (TypeError, ValueError):
        interval = default
    return max(1.0, interval)
