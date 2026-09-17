"""
边缘推理后端：
  ultralytics — 本机 Windows/Linux 调试 .pt
  onnx        — CPU（Windows 开发 / 功能验证）
  rknn        — RK3588 NPU（仅裸机 + rknn-toolkit-lite2）
"""
import os

BACKEND_ULTRALYTICS = "ultralytics"
BACKEND_ONNX = "onnx"
BACKEND_RKNN = "rknn"


def get_inference_backend() -> str:
    raw = (os.getenv("EDGE_INFERENCE") or BACKEND_ULTRALYTICS).strip().lower()
    if raw in (BACKEND_ONNX, BACKEND_RKNN, BACKEND_ULTRALYTICS):
        return raw
    return BACKEND_ULTRALYTICS


def use_ultralytics() -> bool:
    return get_inference_backend() == BACKEND_ULTRALYTICS


def cuda_available() -> bool:
    if not use_ultralytics():
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False
