"""检测框结构兼容：Ultralytics Results 与纯 NumPy ONNX 结果共用。"""
from __future__ import annotations

from typing import Any, Iterable, Iterator, List, Optional, Sequence, Union

import numpy as np


class _ArrayView:
    """模拟 tensor 的 .item() / .tolist() / .cpu().numpy()。"""

    def __init__(self, value: Union[float, int, Sequence[float]]):
        if isinstance(value, (list, tuple)):
            self._arr = np.asarray(value, dtype=np.float32)
        else:
            self._arr = np.asarray([value], dtype=np.float32)

    def item(self) -> float:
        return float(self._arr.reshape(-1)[0])

    def tolist(self) -> List[float]:
        return self._arr.reshape(-1).astype(float).tolist()

    def cpu(self) -> "_ArrayView":
        return self

    def numpy(self) -> np.ndarray:
        return self._arr.reshape(-1)


class SimpleBox:
    def __init__(self, xyxy: Sequence[float], conf: float, cls_id: int):
        self.xyxy = [_ArrayView(xyxy)]
        self.conf = _ArrayView(conf)
        self.cls = _ArrayView(cls_id)


class SimpleBoxes:
    def __init__(self, boxes: List[SimpleBox]):
        self._boxes = boxes

    def __iter__(self) -> Iterator[SimpleBox]:
        return iter(self._boxes)

    def __len__(self) -> int:
        return len(self._boxes)


class SimpleYoloResult:
    """替代 ultralytics.engine.results.Results 的最小结构。"""

    def __init__(
        self,
        orig_img: np.ndarray,
        names: dict,
        boxes: Optional[SimpleBoxes],
        speed: Optional[dict] = None,
    ):
        self.orig_img = orig_img
        self.names = names
        self.boxes = boxes
        self.speed = speed or {"preprocess": 0.0, "inference": 0.0, "postprocess": 0.0}
        self.masks = None


def box_xyxy_array(box: Any) -> np.ndarray:
    xy = box.xyxy[0]
    if hasattr(xy, "cpu"):
        return np.asarray(xy.cpu().numpy(), dtype=np.float32).reshape(4)
    if hasattr(xy, "tolist"):
        return np.asarray(xy.tolist(), dtype=np.float32).reshape(4)
    return np.asarray(xy, dtype=np.float32).reshape(4)


def box_confidence(box: Any) -> float:
    c = box.conf
    if hasattr(c, "cpu"):
        arr = c.cpu().numpy()
        return float(arr.reshape(-1)[0])
    if hasattr(c, "item"):
        return float(c.item())
    return float(c)


def box_class_id(box: Any) -> int:
    cls = box.cls
    if hasattr(cls, "cpu"):
        return int(cls.cpu().numpy().reshape(-1)[0])
    if hasattr(cls, "item"):
        return int(cls.item())
    return int(cls)
