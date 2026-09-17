"""设备级检测区域（ROI）工具：供普通目标检测引用"""
import json
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def coerce_area_coordinates(raw: Any) -> Optional[dict]:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw if isinstance(raw, dict) else None


def is_device_roi_enabled(area_coordinates: Optional[dict]) -> bool:
    """判断设备区域是否已启用且坐标有效

    - enabled=true：启用
    - enabled=false：显式关闭（即使有点也忽略）
    - 旧数据仅有 points 未写 enabled：有点则视为启用
    """
    area_coordinates = coerce_area_coordinates(area_coordinates)
    if not area_coordinates:
        return False
    points = area_coordinates.get("points") or []
    if len(points) < 3:
        return False
    if area_coordinates.get("enabled") is False:
        return False
    return True


def normalize_points_to_pixels(
    points: List[Any], frame_shape: Tuple[int, ...]
) -> List[Tuple[int, int]]:
    h, w = frame_shape[:2]
    pixels: List[Tuple[int, int]] = []
    for p in points:
        if isinstance(p, dict):
            pixels.append((int(float(p["x"]) * w), int(float(p["y"]) * h)))
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = float(p[0]), float(p[1])
            if 0 <= x <= 1 and 0 <= y <= 1:
                pixels.append((int(x * w), int(y * h)))
            else:
                pixels.append((int(x), int(y)))
    return pixels


def get_device_roi_pixels(
    area_coordinates: Optional[dict], frame_shape: Tuple[int, ...]
) -> Optional[List[Tuple[int, int]]]:
    area_coordinates = coerce_area_coordinates(area_coordinates)
    if not is_device_roi_enabled(area_coordinates):
        return None
    pixels = normalize_points_to_pixels(area_coordinates.get("points") or [], frame_shape)
    return pixels if len(pixels) >= 3 else None


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[int, int]]) -> bool:
    if not polygon or len(polygon) < 3:
        return False
    contour = np.array(polygon, dtype=np.int32)
    result = cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False)
    return result >= 0


def bbox_probe_point(bbox: List[float]) -> Tuple[float, float]:
    """检测框判区点：底边中点（与现场判区习惯一致）"""
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, y2


def filter_detections_by_roi(
    detections: List[Dict[str, Any]], roi_pixels: Optional[List[Tuple[int, int]]]
) -> List[Dict[str, Any]]:
    if not roi_pixels or len(roi_pixels) < 3:
        return detections
    filtered = []
    for det in detections:
        probe = bbox_probe_point(det["bbox"])
        if point_in_polygon(probe, roi_pixels):
            filtered.append(det)
    return filtered


def draw_device_roi(
    frame,
    roi_pixels: Optional[List[Tuple[int, int]]],
    line_color: Tuple[int, int, int] = (0, 255, 0),
    fill_alpha: float = 0.12,
):
    if not roi_pixels or len(roi_pixels) < 3:
        return frame
    roi_array = np.array(roi_pixels, np.int32)
    cv2.polylines(frame, [roi_array], True, line_color, 2, cv2.LINE_AA)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [roi_array], line_color)
    cv2.addWeighted(overlay, fill_alpha, frame, 1 - fill_alpha, 0, frame)
    return frame
