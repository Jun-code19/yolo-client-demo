"""边缘检测盒 — 上传模型格式与任务类型约束。"""
from __future__ import annotations

import os
from typing import Iterable, Set

from src.inference_backend import get_inference_backend, use_ultralytics

# 开发机 ultralytics 仍允许 .pt；边缘 onnx/rknn 仅下列扩展名
_DEV_EXTENSIONS = {".pt", ".onnx", ".pth", ".weights", ".rknn"}
_EDGE_EXTENSIONS = {".onnx", ".rknn"}

# 边缘 ONNX/RKNN 仅支持检测类任务（无 pose/seg 后处理）
_EDGE_MODEL_TYPES = {"object_detection", "face"}


def allowed_model_extensions() -> Set[str]:
    if use_ultralytics():
        return set(_DEV_EXTENSIONS)
    return set(_EDGE_EXTENSIONS)


def allowed_model_types() -> Set[str]:
    if use_ultralytics():
        return {
            "object_detection",
            "segmentation",
            "keypoint",
            "pose",
            "face",
            "other",
        }
    return set(_EDGE_MODEL_TYPES)


def validate_model_upload(file_ext: str, models_type: str) -> None:
    ext = (file_ext or "").lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    allowed_ext = allowed_model_extensions()
    if ext not in allowed_ext:
        backend = get_inference_backend()
        if use_ultralytics():
            detail = f"不支持的模型格式 {ext}，允许: {', '.join(sorted(allowed_ext))}"
        else:
            detail = (
                f"边缘推理（EDGE_INFERENCE={backend}）仅支持 "
                f"{', '.join(sorted(_EDGE_EXTENSIONS))}，当前为 {ext}"
            )
        raise ValueError(detail)

    task = (models_type or "").strip().lower()
    allowed_types = allowed_model_types()
    if task not in allowed_types:
        if use_ultralytics():
            raise ValueError(f"不支持的模型类型: {models_type}")
        raise ValueError(
            f"边缘盒 ONNX/RKNN 仅支持模型类型: "
            f"{', '.join(sorted(_EDGE_MODEL_TYPES))}，当前为 {models_type}。"
            "分割/姿态等请在本机 ultralytics 环境使用。"
        )
