"""设备监控配置：环境变量 > config/device_monitor.json > platform_settings > 默认值"""
import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_JSON_FILE_CACHE: Dict[str, Any] = {"path": None, "mtime": None, "data": {}}

DEFAULT_DEVICE_MONITOR_CONFIG: Dict[str, Any] = {
    "check_interval": 300,
    "offline_threshold": 3,
    "retry_count": 3,
    "retry_delay_seconds": 1.0,
    "per_device_delay_seconds": 0.2,
    "rtsp_timeout_seconds": 6.0,
    "tcp_timeout_seconds": 3.0,
    "http_timeout_seconds": 3.0,
    "enable_ping": False,
    "rtsp_stream_for_probe": "sub",
    "http_dahua_path": "/cgi-bin/api/tcpConnect/tcpTest",
    "http_dahua_port": 80,
    "default_methods_by_type": {
        "camera": ["rtsp", "tcp"],
        "nvr": ["rtsp", "tcp"],
        "edge_server": ["tcp", "http_dahua"],
        "storage_node": ["tcp"],
        "default": ["rtsp", "tcp", "http_dahua"],
    },
    "method_aliases": {
        "auto": "auto",
        "rtsp": "rtsp",
        "tcp": "tcp",
        "http": "http_dahua",
        "http_dahua": "http_dahua",
        "ping": "ping",
    },
}

_ENV_INT_KEYS = {
    "DEVICE_MONITOR_CHECK_INTERVAL": "check_interval",
    "DEVICE_MONITOR_OFFLINE_THRESHOLD": "offline_threshold",
    "DEVICE_MONITOR_RETRY_COUNT": "retry_count",
    "DEVICE_MONITOR_HTTP_DAHUA_PORT": "http_dahua_port",
}

_ENV_FLOAT_KEYS = {
    "DEVICE_MONITOR_RETRY_DELAY": "retry_delay_seconds",
    "DEVICE_MONITOR_PER_DEVICE_DELAY": "per_device_delay_seconds",
    "DEVICE_MONITOR_RTSP_TIMEOUT": "rtsp_timeout_seconds",
    "DEVICE_MONITOR_TCP_TIMEOUT": "tcp_timeout_seconds",
    "DEVICE_MONITOR_HTTP_TIMEOUT": "http_timeout_seconds",
}

_ENV_BOOL_KEYS = {
    "DEVICE_MONITOR_ENABLE_PING": "enable_ping",
}

_ENV_STR_KEYS = {
    "DEVICE_MONITOR_RTSP_STREAM": "rtsp_stream_for_probe",
    "DEVICE_MONITOR_HTTP_DAHUA_PATH": "http_dahua_path",
    "DEVICE_MONITOR_DEFAULT_METHODS": "default_methods_global",
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key in ("push_interval", "enable_push", "push_tags", "enable_notifications"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env(config: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(config)
    for env_key, cfg_key in _ENV_INT_KEYS.items():
        raw = os.getenv(env_key)
        if raw is not None and raw != "":
            result[cfg_key] = int(raw)
    for env_key, cfg_key in _ENV_FLOAT_KEYS.items():
        raw = os.getenv(env_key)
        if raw is not None and raw != "":
            result[cfg_key] = float(raw)
    for env_key, cfg_key in _ENV_BOOL_KEYS.items():
        raw = os.getenv(env_key)
        if raw is not None and raw != "":
            result[cfg_key] = raw.strip().lower() in {"1", "true", "yes", "on"}
    for env_key, cfg_key in _ENV_STR_KEYS.items():
        raw = os.getenv(env_key)
        if raw is not None and raw.strip():
            if cfg_key == "default_methods_global":
                result["default_methods_by_type"]["default"] = [
                    item.strip() for item in raw.split(",") if item.strip()
                ]
            else:
                result[cfg_key] = raw.strip()
    return result


def _load_json_file() -> Dict[str, Any]:
    candidates = [
        Path(os.getenv("DEVICE_MONITOR_CONFIG", "config/device_monitor.json")),
        Path("config/device_monitor.json"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
            cache = _JSON_FILE_CACHE
            if cache["path"] == str(path) and cache["mtime"] == mtime:
                return deepcopy(cache["data"])

            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue

            cache["path"] = str(path)
            cache["mtime"] = mtime
            cache["data"] = data
            logger.info("已加载设备监控配置: %s", path)
            return deepcopy(data)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取设备监控配置失败 %s: %s", path, exc)
    return {}


def _load_platform_setting(db_session) -> Dict[str, Any]:
    if db_session is None:
        return {}
    try:
        from src.database import PlatformSetting

        row = db_session.query(PlatformSetting).filter(
            PlatformSetting.setting_key == "device_monitor"
        ).first()
        if row and isinstance(row.setting_value, dict):
            return row.setting_value
    except Exception as exc:
        logger.debug("读取 platform_settings.device_monitor 失败: %s", exc)
    return {}


def load_device_monitor_config(db_session=None) -> Dict[str, Any]:
    config = deepcopy(DEFAULT_DEVICE_MONITOR_CONFIG)
    config = _deep_merge(config, _load_json_file())
    config = _apply_env(config)
    config = _deep_merge(config, _load_platform_setting(db_session))
    return config


def resolve_check_methods(device: Any, config: Dict[str, Any]) -> List[str]:
    """根据设备 monitor_method / device_type 解析探活方法链"""
    aliases = config.get("method_aliases") or {}
    raw_method = getattr(device, "monitor_method", None) or "auto"
    raw_method = str(raw_method).strip().lower()
    normalized = aliases.get(raw_method, raw_method)

    if normalized != "auto":
        return [normalized]

    device_type = (getattr(device, "device_type", None) or "camera").strip().lower()
    by_type = config.get("default_methods_by_type") or {}
    methods = by_type.get(device_type) or by_type.get("default") or ["rtsp", "tcp"]
    return list(methods)
