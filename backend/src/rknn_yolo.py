"""RK3588 NPU 推理 — YOLOv8 检测类 .rknn（与 onnx_yolo_adapter 同接口）。"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Union

import numpy as np

from src.onnx_yolo_adapter import (
    _letterbox,
    _postprocess_yolo_output,
    _scale_boxes,
)
from src.yolo_box_compat import SimpleBox, SimpleBoxes, SimpleYoloResult

logger = logging.getLogger(__name__)

# 进程内所有 .rknn 共用 NPU 驱动；多任务/多模型并发 inference 会互相踩内存，必须全局串行。
_RKNN_NPU_LOCK = threading.Lock()


def _import_rknnlite():
    try:
        from rknnlite.api import RKNNLite

        return RKNNLite
    except ImportError as exc:
        raise RuntimeError(
            "未安装 rknn-toolkit-lite2。请在 RK3588 上安装 Rockchip 提供的 "
            "rknn_toolkit_lite2-*-linux_aarch64.whl，并确保 librknnrt.so 可被加载 "
            "（常见路径 /usr/lib，或设置 LD_LIBRARY_PATH）。"
        ) from exc


def _core_mask_from_env(RKNNLite):
    raw = (os.getenv("RKNN_CORE_MASK") or "auto").strip().lower()
    table = {
        "0": "NPU_CORE_0",
        "1": "NPU_CORE_1",
        "2": "NPU_CORE_2",
        "0_1": "NPU_CORE_0_1",
        "0_1_2": "NPU_CORE_0_1_2",
        "all": "NPU_CORE_0_1_2",
        "auto": "NPU_CORE_AUTO",
    }
    attr = table.get(raw, "NPU_CORE_AUTO")
    if hasattr(RKNNLite, attr):
        return getattr(RKNNLite, attr)
    if hasattr(RKNNLite, "NPU_CORE_0_1_2"):
        return RKNNLite.NPU_CORE_0_1_2
    return getattr(RKNNLite, "NPU_CORE_0", 1)


def _env_uint8_input() -> bool:
    v = (os.getenv("RKNN_INPUT_UINT8") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


class RknnYoloAdapter:
    """YOLOv8 单输出 .rknn，后处理与 ONNX 路径一致（84×8400 或 4+nc 布局）。"""

    backend = "rknn"
    names: Dict[int, str]

    def __init__(
        self,
        model_path: str,
        class_names: Optional[Dict[int, str]] = None,
        imgsz: int = 640,
    ):
        RKNNLite = _import_rknnlite()
        self.model_path = model_path
        self.imgsz = int(imgsz or 640)
        self.names = class_names or {0: "object"}
        self.nc = max(len(self.names), 1)
        self._use_uint8 = _env_uint8_input()

        self._rknn = RKNNLite()
        ret = self._rknn.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError(f"load_rknn 失败: {model_path}, ret={ret}")

        core_mask = _core_mask_from_env(RKNNLite)
        ret = self._rknn.init_runtime(core_mask=core_mask)
        if ret != 0:
            self._rknn.release()
            raise RuntimeError(
                f"init_runtime(NPU) 失败 ret={ret}。"
                "请确认 /dev/rknpu* 存在、当前用户有权限，且 librknnrt 版本与 .rknn 匹配。"
            )

        logger.info(
            "RKNN/NPU 适配器已加载: path=%s imgsz=%s nc=%s uint8_input=%s core_mask=%s",
            model_path,
            self.imgsz,
            self.nc,
            self._use_uint8,
            core_mask,
        )

    def release(self) -> None:
        if getattr(self, "_rknn", None) is not None:
            try:
                self._rknn.release()
            except Exception:
                pass
            self._rknn = None

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass

    def _prepare_input(self, im0: np.ndarray, letterboxed: np.ndarray):
        if self._use_uint8:
            im_rgb = letterboxed[..., ::-1]
            return np.ascontiguousarray(im_rgb, dtype=np.uint8)[None]
        im_rgb = letterboxed[..., ::-1].transpose(2, 0, 1)
        im_batch = np.ascontiguousarray(im_rgb, dtype=np.float32) / 255.0
        return im_batch[None]

    def _normalize_output(self, raw: np.ndarray) -> np.ndarray:
        if raw.dtype == np.float32:
            return raw
        return raw.astype(np.float32)

    def __call__(
        self,
        source: Union[np.ndarray, List[np.ndarray]],
        conf: float = 0.25,
        iou: float = 0.45,
        max_det: int = 300,
        verbose: bool = False,
        device=None,
        half: bool = False,
        **kwargs,
    ) -> List[SimpleYoloResult]:
        del verbose, device, half, kwargs

        frames = [source] if isinstance(source, np.ndarray) else list(source)
        results: List[SimpleYoloResult] = []

        for im0 in frames:
            if im0 is None or not isinstance(im0, np.ndarray) or im0.size == 0:
                continue

            t0 = time.perf_counter()
            im, _, _ = _letterbox(im0, (self.imgsz, self.imgsz))
            inp = self._prepare_input(im0, im)
            t1 = time.perf_counter()

            with _RKNN_NPU_LOCK:
                outputs = self._rknn.inference(inputs=[inp])
                if not outputs:
                    raise RuntimeError("RKNN inference 未返回输出")
                raw = np.asarray(self._normalize_output(outputs[0]), dtype=np.float32).copy()
                t2 = time.perf_counter()
                det = _postprocess_yolo_output(raw, conf, iou, max_det, max(self.nc, 1))
                if len(det):
                    det[:, :4] = _scale_boxes(det[:, :4], im.shape, im0.shape)

            t3 = time.perf_counter()
            boxes = [
                SimpleBox(det[i, :4].tolist(), float(det[i, 4]), int(det[i, 5]))
                for i in range(len(det))
            ]
            speed = {
                "preprocess": (t1 - t0) * 1000,
                "inference": (t2 - t1) * 1000,
                "postprocess": (t3 - t2) * 1000,
            }
            results.append(
                SimpleYoloResult(
                    orig_img=im0,
                    names=self.names,
                    boxes=SimpleBoxes(boxes) if boxes else None,
                    speed=speed,
                )
            )

        return results

    def predict(self, frame, conf: float = 0.25, **kwargs) -> List[Any]:
        return self(frame, conf=conf, **kwargs)
