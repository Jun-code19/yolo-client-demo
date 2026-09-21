"""边缘盒系统状态采集（/api/v1/system/status）。"""
from __future__ import annotations

import os
import platform
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def _read_text(path: str, max_len: int = 256) -> Optional[str]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore").strip()
        return text[:max_len] if text else None
    except OSError:
        return None


def _format_uptime(seconds: float) -> str:
    total = max(int(seconds), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours or days:
        parts.append(f"{hours}小时")
    parts.append(f"{minutes}分钟")
    return "".join(parts)


def _disk_usage(path: str) -> Dict[str, Any]:
    import psutil

    try:
        usage = psutil.disk_usage(path)
    except OSError:
        return {"path": path, "percent": 0, "total": 0, "used": 0, "free": 0}
    return {
        "path": path,
        "percent": round(usage.percent, 1),
        "total": round(usage.total / (1024 ** 3), 2),
        "used": round(usage.used / (1024 ** 3), 2),
        "free": round(usage.free / (1024 ** 3), 2),
    }


_RKNPU_VERSION = "/sys/kernel/debug/rknpu/version"
_RKNPU_LOAD = "/sys/kernel/debug/rknpu/load"
_RKNPU_VERSION_RUN = "/run/edge-ai-box/rknpu-version"
_RKNPU_LOAD_RUN = "/run/edge-ai-box/rknpu-load"


def _read_npu_debug(primary: str, fallback: str) -> Optional[str]:
    text = _read_text(primary)
    if text:
        return text
    return _read_text(fallback)


def _parse_rknpu_load(load_raw: str) -> tuple[Optional[float], List[Dict[str, Any]]]:
    """解析 `NPU load: Core0: 59%, Core1: 4%, ...`"""
    cores: List[Dict[str, Any]] = []
    for match in re.finditer(r"Core(\d+):\s*(\d+(?:\.\d+)?)\s*%", load_raw, re.I):
        idx = int(match.group(1))
        pct = float(match.group(2))
        cores.append({"core": idx, "percent": round(pct, 1)})
    if not cores:
        return None, cores
    peak = max(c["percent"] for c in cores)
    return round(peak, 1), cores


def _npu_info(inference_backend: str) -> Dict[str, Any]:
    driver = _read_npu_debug(_RKNPU_VERSION, _RKNPU_VERSION_RUN)
    load_raw = _read_npu_debug(_RKNPU_LOAD, _RKNPU_LOAD_RUN)
    load_percent: Optional[float] = None
    load_cores: List[Dict[str, Any]] = []
    load_readable: Optional[str] = None
    load_error: Optional[str] = None

    if load_raw:
        load_percent, load_cores = _parse_rknpu_load(load_raw)
        if load_cores:
            load_readable = " · ".join(
                f"Core{c['core']} {c['percent']}%" for c in load_cores
            )
    elif inference_backend == "rknn" and not load_raw:
        run_load = Path(_RKNPU_LOAD_RUN)
        if not run_load.is_file():
            load_error = "NPU 负载未同步（请启用 edge-rknpu-debugfs-refresh.timer）"
        elif not _read_text(_RKNPU_LOAD_RUN):
            load_error = "NPU 负载快照为空"

    has_drm = Path("/dev/dri/renderD129").exists() or Path("/dev/dri/renderD128").exists()
    available = inference_backend == "rknn" or bool(driver) or has_drm
    status_text = "就绪"
    if inference_backend != "rknn":
        status_text = "未启用（EDGE_INFERENCE≠rknn）"
    elif not available:
        status_text = "驱动或设备不可用"
    elif load_error:
        status_text = load_error

    return {
        "available": available,
        "backend": inference_backend,
        "driver_version": driver,
        "load_percent": load_percent,
        "load_cores": load_cores,
        "load_readable": load_readable,
        "load_error": load_error,
        "status_text": status_text,
    }


def collect_system_status(db: Optional[Session] = None) -> Dict[str, Any]:
    import psutil

    from src.inference_backend import get_inference_backend

    now = datetime.now()
    boot_ts = psutil.boot_time()
    uptime_sec = now.timestamp() - boot_ts

    cpu_percent = psutil.cpu_percent(interval=0.4)
    cpu_count = psutil.cpu_count(logical=True) or 0

    memory = psutil.virtual_memory()
    inference = get_inference_backend() or os.getenv("EDGE_INFERENCE", "onnx")

    disk_root = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    disk = _disk_usage(disk_root)

    backend_dir = Path(__file__).resolve().parents[1]
    data_disk = _disk_usage(str(backend_dir))

    npu = _npu_info(inference)

    gpu_percent = 0.0
    gpu_total = 0.0
    gpu_used = 0.0
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            gpu_percent = round(gpu.load * 100, 1)
            gpu_total = round(gpu.memoryTotal / 1024, 2)
            gpu_used = round(gpu.memoryUsed / 1024, 2)
    except Exception:
        pass

    status = "normal"
    if cpu_percent > 90 or memory.percent > 90 or disk["percent"] > 90:
        status = "danger"
    elif cpu_percent > 70 or memory.percent > 80 or disk["percent"] > 80:
        status = "warning"
    if npu.get("load_percent") is not None and npu["load_percent"] > 90:
        status = "danger" if status != "danger" else status

    active_detection = 0
    if db is not None:
        try:
            from src.database import DetectionConfig

            active_detection = (
                db.query(DetectionConfig).filter(DetectionConfig.enabled.is_(True)).count()
            )
        except Exception:
            active_detection = 0

    return {
        "status": status,
        "system": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "app_name": "edge-ai-box",
            "app_version": os.getenv("EDGE_APP_VERSION", "1.0.0"),
            "edge_inference": inference,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "boot_time": datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": int(uptime_sec),
            "uptime_text": _format_uptime(uptime_sec),
        },
        "cpu": {
            "percent": round(cpu_percent, 1),
            "total": cpu_count,
            "used": round(cpu_count * (cpu_percent / 100.0), 2),
        },
        "memory": {
            "percent": round(memory.percent, 1),
            "total": round(memory.total / (1024 ** 3), 2),
            "used": round(memory.used / (1024 ** 3), 2),
        },
        "disk": disk,
        "data_storage": data_disk,
        "npu": npu,
        "gpu": {
            "percent": gpu_percent,
            "total": gpu_total,
            "used": gpu_used,
        },
        "detection": {
            "enabled_configs": active_detection,
        },
    }
