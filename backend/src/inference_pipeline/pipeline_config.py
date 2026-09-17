"""边缘盒仅 YOLO 检测，不解析 VLM 二阶段配置。"""
from __future__ import annotations

from typing import Any, Dict, Optional

MODE_YOLO_ONLY = "yolo_only"


def normalize_inference_pipeline(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    del config
    return {"mode": MODE_YOLO_ONLY}


def extract_inference_pipeline(schedule_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    del schedule_config
    return {"mode": MODE_YOLO_ONLY}
