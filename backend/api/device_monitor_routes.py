"""检测服务：设备监控运行时状态"""
import shutil

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from src.database import User
from src.device_monitor import device_monitor
from src.device_monitor_config import load_device_monitor_config

router = APIRouter(tags=["设备监控"])


@router.get("/settings/device-monitor/runtime")
def get_device_monitor_runtime(current_user: User = Depends(get_current_user)):
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    opencv = False
    try:
        import cv2  # noqa: F401

        opencv = True
    except ImportError:
        pass

    if ffprobe:
        rtsp_probe_mode = "ffprobe"
    elif opencv:
        rtsp_probe_mode = "opencv"
    else:
        rtsp_probe_mode = "none"

    return {
        "success": True,
        "data": {
            "monitor_running": device_monitor.running,
            "scheduler_jobs": len(device_monitor.scheduler.get_jobs()) if device_monitor.running else 0,
            "ffmpeg_available": bool(ffmpeg),
            "ffprobe_available": bool(ffprobe),
            "opencv_available": opencv,
            "rtsp_probe_mode": rtsp_probe_mode,
            "rtsp_probe_hint": {
                "ffprobe": "推荐：RTSP 探测稳定、超时可控",
                "opencv": "回退：无 ffprobe 时用 OpenCV 拉流，部分环境较慢或不准",
                "none": "不可用：请安装 ffmpeg 或 opencv-python",
            }.get(rtsp_probe_mode, ""),
            "config": load_device_monitor_config(),
        },
    }


@router.post("/settings/device-monitor/reload")
def reload_device_monitor_scheduler(current_user: User = Depends(get_current_user)):
    device_monitor.reload_scheduler()
    return {"success": True, "message": "设备监控调度已刷新"}
