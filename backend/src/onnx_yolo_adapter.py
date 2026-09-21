"""ONNX YOLO 推理（纯 NumPy + OpenCV，不依赖 torch / ultralytics）。"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

from src.yolo_box_compat import SimpleBox, SimpleBoxes, SimpleYoloResult

logger = logging.getLogger(__name__)


def is_onnx_model_path(model_path: str) -> bool:
    return str(model_path or "").lower().endswith(".onnx")


def _resolve_image_input(session) -> str:
    inputs = session.get_inputs()
    preferred = ("images", "input", "input.1", "data", "x")
    for name in preferred:
        for inp in inputs:
            inp_type = (inp.type or "").lower()
            if inp.name == name and "float" in inp_type:
                return inp.name
    for inp in inputs:
        inp_type = (inp.type or "").lower()
        if "float" not in inp_type:
            continue
        shape = inp.shape or []
        if len(shape) == 4:
            return inp.name
    details = [(inp.name, inp.type, inp.shape) for inp in inputs]
    raise RuntimeError(f"ONNX 模型缺少可用的浮点图像输入，当前输入: {details}")


def _resolve_imgsz(session, input_name: str, default: int = 640) -> int:
    for inp in session.get_inputs():
        if inp.name != input_name:
            continue
        shape = inp.shape or []
        if len(shape) == 4:
            for dim in shape[2:4]:
                if isinstance(dim, int) and dim > 0:
                    return int(dim)
    return default


def _letterbox(
    im: np.ndarray,
    new_shape: tuple = (640, 640),
    color: tuple = (114, 114, 114),
):
    shape = im.shape[:2]
    if shape[0] <= 0 or shape[1] <= 0:
        raise ValueError("invalid image shape")
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw = new_shape[1] - new_unpad[0]
    dh = new_shape[0] - new_unpad[1]
    dw /= 2
    dh /= 2
    if shape[::-1] != new_unpad:
        im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im = cv2.copyMakeBorder(im, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return im, r, (left, top)


def _scale_boxes(boxes_xyxy: np.ndarray, img1_shape, img0_shape) -> np.ndarray:
    gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
    pad_x = (img1_shape[1] - img0_shape[1] * gain) / 2
    pad_y = (img1_shape[0] - img0_shape[0] * gain) / 2
    boxes = boxes_xyxy.copy()
    boxes[:, [0, 2]] -= pad_x
    boxes[:, [1, 3]] -= pad_y
    boxes[:, :4] /= max(gain, 1e-6)
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, img0_shape[1])
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, img0_shape[0])
    return boxes


def _xywh2xyxy(x: np.ndarray) -> np.ndarray:
    y = np.empty_like(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_thres: float, max_det: int) -> List[int]:
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1).clip(0) * (y2 - y1).clip(0)
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size > 0 and len(keep) < max_det:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = (xx2 - xx1).clip(0)
        h = (yy2 - yy1).clip(0)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[1:][iou <= iou_thres]
    return keep


def _maybe_sigmoid_scores(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    smin = float(np.min(scores))
    smax = float(np.max(scores))
    if smin >= 0.0 and smax <= 1.0:
        return scores.astype(np.float32, copy=False)
    return (1.0 / (1.0 + np.exp(-np.clip(scores, -50, 50)))).astype(np.float32)


def _normalize_yolo_pred_layout(pred: np.ndarray, nc_hint: int) -> tuple[np.ndarray, int]:
    """Ultralytics 检测头常见 (4+nc, N) 或 (N, 4+nc)，统一为 (N, 4+nc)。"""
    if pred.ndim == 3:
        pred = pred[0]
    if pred.ndim != 2:
        return pred, max(int(nc_hint or 0), 1)

    h, w = pred.shape
    nc_hint = max(int(nc_hint or 0), 1)

    # 通道在前：(8, 8400) / (84, 8400)
    if h < w and 6 <= h <= 4 + 512:
        return pred.T, max(nc_hint, h - 4)
    # 锚点在前：(8400, 8)
    if w < h and 6 <= w <= 4 + 512:
        return pred, max(nc_hint, w - 4)
    if w <= h and 6 <= w <= 4 + 512:
        return pred, max(nc_hint, w - 4)

    if h in (4 + nc_hint, 84, 4 + 80) and h < w:
        return pred.T, nc_hint
    return pred, nc_hint


def _postprocess_yolo_output(
    pred: np.ndarray,
    conf_thres: float,
    iou_thres: float,
    max_det: int,
    nc: int,
) -> np.ndarray:
    """pred: (N, 4+nc) 或 (4+nc, N)。"""
    pred, nc = _normalize_yolo_pred_layout(pred, nc)
    if pred.ndim != 2 or pred.shape[1] < 6:
        return np.zeros((0, 6), dtype=np.float32)
    boxes = pred[:, :4]
    cls_scores = _maybe_sigmoid_scores(pred[:, 4:])
    if cls_scores.size == 0:
        return np.zeros((0, 6), dtype=np.float32)
    class_ids = np.argmax(cls_scores, axis=1)
    scores = cls_scores[np.arange(len(cls_scores)), class_ids]
    mask = scores >= conf_thres
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]
    if len(boxes) == 0:
        return np.zeros((0, 6), dtype=np.float32)
    finite = np.isfinite(boxes).all(axis=1) & np.isfinite(scores)
    boxes = boxes[finite]
    scores = scores[finite]
    class_ids = class_ids[finite]
    if len(boxes) == 0:
        return np.zeros((0, 6), dtype=np.float32)
    boxes_xyxy = _xywh2xyxy(boxes.astype(np.float32))
    keep = _nms_xyxy(boxes_xyxy, scores.astype(np.float32), iou_thres, max_det)
    if not keep:
        return np.zeros((0, 6), dtype=np.float32)
    out = np.zeros((len(keep), 6), dtype=np.float32)
    for row, idx in enumerate(keep):
        out[row, :4] = boxes_xyxy[idx]
        out[row, 4] = scores[idx]
        out[row, 5] = class_ids[idx]
    return out


class OnnxYoloAdapter:
    names: Dict[int, str]

    def __init__(
        self,
        model_path: str,
        class_names: Optional[Dict[int, str]] = None,
        use_cuda: bool = False,
        imgsz: Optional[int] = None,
    ):
        import onnxruntime as ort

        providers = ["CPUExecutionProvider"]
        if use_cuda and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")

        self.model_path = model_path
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = _resolve_image_input(self.session)
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.imgsz = imgsz or _resolve_imgsz(self.session, self.input_name)
        self.names = class_names or {0: "object"}
        self.nc = len(self.names)
        self._infer_lock = threading.Lock()
        logger.info(
            "ONNX 适配器已加载: input=%s outputs=%s imgsz=%s nc=%s",
            self.input_name,
            self.output_names,
            self.imgsz,
            self.nc,
        )

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
            im_rgb = im[..., ::-1].transpose(2, 0, 1)
            im_batch = np.ascontiguousarray(im_rgb, dtype=np.float32) / 255.0
            im_batch = im_batch[None]
            t1 = time.perf_counter()

            with self._infer_lock:
                outputs = self.session.run(self.output_names, {self.input_name: im_batch})
                t2 = time.perf_counter()
                raw = outputs[0].astype(np.float32).copy()
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
