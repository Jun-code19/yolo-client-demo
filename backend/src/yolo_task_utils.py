"""YOLO 任务类型解析、分割 mask 处理与绘制"""
from __future__ import annotations

import ast
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

import cv2
import numpy as np

from src.inference_backend import cuda_available, get_inference_backend, use_ultralytics

logger = logging.getLogger(__name__)


def resolve_yolo_task(models_type: Optional[str]) -> str:
    task = (models_type or "").lower()
    if task == "pose":
        return "pose"
    if task == "segmentation":
        return "segment"
    return "detect"


def is_segmentation_type(models_type: Optional[str]) -> bool:
    return (models_type or "").lower() == "segmentation"


def is_face_type(models_type: Optional[str]) -> bool:
    return (models_type or "").lower() == "face"


def is_rknn_model_path(model_path: str) -> bool:
    return os.path.splitext(model_path or "")[1].lower() == ".rknn"


def event_description_for_type(models_type: Optional[str], count: int) -> str:
    task = (models_type or "").lower()
    if task == "face":
        return f"检测到{count}张人脸"
    if task == "segmentation":
        return f"检测到{count}个分割目标"
    if task == "pose":
        return f"检测到{count}个姿态目标"
    return f"检测到{count}个目标"


def simplify_polygon(points: Sequence[Sequence[float]], max_points: int = 48) -> List[List[float]]:
    if not points or len(points) < 3:
        return [list(p) for p in points] if points else []

    contour = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    peri = cv2.arcLength(contour, True)
    epsilon = max(peri * 0.002, 1.0)
    approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    simplified = approx.tolist()
    if len(simplified) > max_points:
        step = max(1, len(simplified) // max_points)
        simplified = simplified[::step][:max_points]
    return simplified


def process_yolo_results(
    results,
    target_class: Sequence[str],
    include_segmentation: bool = False,
) -> List[Dict[str, Any]]:
    detections: List[Dict[str, Any]] = []
    target_set = {str(cls_id) for cls_id in (target_class or [])}

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue

        masks = getattr(result, "masks", None)
        mask_xy_list = masks.xy if masks is not None and hasattr(masks, "xy") else None

        for idx, box in enumerate(boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            confidence = float(box.conf.item())
            class_id = int(box.cls.item())
            if target_set and str(class_id) not in target_set:
                continue

            names_map = result.names or {}
            class_name = names_map.get(class_id, str(class_id)) if isinstance(names_map, dict) else str(class_id)
            detection: Dict[str, Any] = {
                "bbox": [x1, y1, x2, y2],
                "confidence": confidence,
                "class_id": class_id,
                "class_name": class_name,
            }

            if include_segmentation and mask_xy_list is not None and idx < len(mask_xy_list):
                polygon = mask_xy_list[idx]
                if polygon is not None and len(polygon) >= 3:
                    detection["has_mask"] = True
                    detection["mask_polygon"] = simplify_polygon(polygon.tolist())

            detections.append(detection)

    return detections


def draw_segmentation_detections(
    img,
    detections: List[Dict[str, Any]],
    get_class_color: Callable[[int], Sequence[int]],
    alpha: float = 0.42,
    draw_boxes: bool = True,
):
    if img is None or not detections:
        return img

    overlay = img.copy()
    has_mask = False
    for det in detections:
        polygon = det.get("mask_polygon")
        if not polygon or len(polygon) < 3:
            continue
        has_mask = True
        cls = int(det.get("class_id", 0))
        color = tuple(int(c) for c in get_class_color(cls))
        pts = np.array(polygon, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], color)

    if has_mask:
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    if not draw_boxes:
        return img

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cls = int(det.get("class_id", 0))
        conf = float(det.get("confidence", 0.0))
        color = tuple(int(c) for c in get_class_color(cls))
        cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        class_name = det.get("class_name") or f"Class {cls}"
        label = f"{class_name}: {conf:.2f}"
        cv2.putText(
            img,
            label,
            (int(x1), max(int(y1) - 8, 0)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )
    return img


def build_detection_meta(models_type: Optional[str], detections: List[Dict[str, Any]], target_class) -> Dict[str, Any]:
    class_counts: Dict[str, int] = {}
    for det in detections or []:
        if not isinstance(det, dict):
            continue
        name = det.get("class_name") or det.get("class") or det.get("label")
        if name is None and det.get("class_id") is not None:
            name = str(det.get("class_id"))
        if name is None:
            continue
        key = str(name).strip()
        if not key:
            continue
        class_counts[key] = class_counts.get(key, 0) + 1

    meta = {
        "current_count": len(detections or []),
        "class_counts": class_counts,
        "target_class": target_class,
        "event_description": event_description_for_type(models_type, len(detections or [])),
    }
    if is_segmentation_type(models_type):
        meta["has_segmentation"] = any(d.get("has_mask") for d in detections)
    if is_face_type(models_type):
        meta["face_detection"] = True
    return meta


def normalize_yolo_class_names(names: Any) -> Dict[int, str]:
    if not names:
        return {}
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    if isinstance(names, list):
        return {i: str(n) for i, n in enumerate(names)}
    return {}


def _parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return value


def normalize_model_parameters(parameters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """兼容前端键值对：字符串 JSON、整段 parameters 误填等。"""
    if not parameters:
        return {}
    out: Dict[str, Any] = {}
    for key, value in parameters.items():
        name = str(key).strip()
        if not name:
            continue
        out[name] = _parse_jsonish(value)

    classes = out.get("classes")
    if isinstance(classes, dict) and set(classes.keys()) == {"classes"}:
        inner = classes.get("classes")
        if isinstance(inner, dict):
            out["classes"] = inner

    if not out.get("classes"):
        for value in out.values():
            if isinstance(value, dict) and value.get("classes") is not None:
                out["classes"] = value["classes"]
                break

    return out


def classes_from_parameters(parameters: Optional[Dict[str, Any]]) -> Dict[int, str]:
    parameters = normalize_model_parameters(parameters)
    if not parameters:
        return {}
    raw = parameters.get("classes")
    if raw is None or raw == "":
        return {}
    raw = _parse_jsonish(raw)
    if isinstance(raw, dict):
        if set(raw.keys()) == {"classes"}:
            raw = raw.get("classes") or {}
        if not isinstance(raw, dict):
            return {}
        return {int(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        return {i: str(n) for i, n in enumerate(raw)}
    return {}


def is_onnx_model_path(model_path: str) -> bool:
    return os.path.splitext(model_path or "")[1].lower() == ".onnx"


def class_names_from_onnx_metadata(model_path: str) -> Dict[int, str]:
    try:
        import ast
        import onnxruntime as ort

        session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        meta = session.get_modelmeta().custom_metadata_map or {}
        raw_names = meta.get("names")
        if not raw_names:
            return {}
        if isinstance(raw_names, str):
            raw_names = ast.literal_eval(raw_names)
        return normalize_yolo_class_names(raw_names)
    except Exception as exc:
        logger.debug("读取 ONNX metadata 类别失败: %s", exc)
        return {}


def _resolve_model_path(model_path: str) -> str:
    abs_path = os.path.abspath(model_path)
    if not os.path.exists(abs_path):
        base_name = os.path.basename(abs_path)
        alt_path = os.path.abspath(os.path.join("models", base_name))
        if os.path.exists(alt_path):
            return alt_path
        raise FileNotFoundError(f"模型文件不存在: {model_path}")
    return abs_path


def _prefer_onnx_for_edge(abs_path: str) -> str:
    """边缘部署：按 EDGE_INFERENCE 选择 .rknn / .onnx，替代 .pt。"""
    if use_ultralytics():
        return abs_path
    backend = get_inference_backend()
    ext = os.path.splitext(abs_path)[1].lower()
    base, _ = os.path.splitext(abs_path)
    rknn_alt = base + ".rknn"
    onnx_alt = base + ".onnx"

    if ext == ".rknn":
        return abs_path
    if ext == ".onnx":
        if backend == "rknn" and os.path.exists(rknn_alt):
            logger.info("RKNN 模式：使用 %s 替代 %s", rknn_alt, abs_path)
            return rknn_alt
        return abs_path
    if ext == ".pt":
        if backend == "rknn" and os.path.exists(rknn_alt):
            logger.info("RKNN 模式：使用 %s 替代 %s", rknn_alt, abs_path)
            return rknn_alt
        if os.path.exists(onnx_alt):
            logger.info("边缘推理：使用 %s 替代 %s", onnx_alt, abs_path)
            return onnx_alt
        if backend == "rknn":
            raise RuntimeError(
                f"当前 EDGE_INFERENCE=rknn，无法加载 .pt。请将 {os.path.basename(abs_path)} "
                f"转为同名 .rknn 并放入 models/。参见 deploy/RKNN-EXPORT.md"
            )
        raise RuntimeError(
            f"当前 EDGE_INFERENCE={backend}，无法加载 .pt 模型。"
            f"请将 {os.path.basename(abs_path)} 导出为同名 .onnx 并放入 models/。"
            "示例: yolo export model=xxx.pt format=onnx opset=12"
        )
    return abs_path


def _require_rknn_weight_when_enabled(abs_path: str) -> None:
    if get_inference_backend() != "rknn":
        return
    if is_rknn_model_path(abs_path):
        return
    raise RuntimeError(
        f"EDGE_INFERENCE=rknn 需要 .rknn 权重，当前为 {os.path.basename(abs_path)}。"
        "请上传 RKNN 模型或设置 EDGE_INFERENCE=onnx。"
        "转换步骤见 deploy/RKNN-EXPORT.md"
    )


def _require_ultralytics_for_task(models_type: Optional[str]) -> None:
    task = (models_type or "").lower()
    if not use_ultralytics() and task in ("pose", "segmentation", "keypoint"):
        raise RuntimeError(
            f"EDGE_INFERENCE={get_inference_backend()} 暂不支持模型类型「{task}」，"
            "请使用 object_detection 的 ONNX，或在本机设置 EDGE_INFERENCE=ultralytics。"
        )


def load_detection_model(
    model_path: str,
    models_type: Optional[str],
    is_gpu: bool,
    class_names: Optional[Dict[int, str]] = None,
):
    from src.env_loader import configure_ultralytics_env
    from src.onnx_yolo_adapter import OnnxYoloAdapter, is_onnx_model_path as _is_onnx

    configure_ultralytics_env()

    abs_path = _resolve_model_path(model_path)
    _require_ultralytics_for_task(models_type)
    abs_path = _prefer_onnx_for_edge(abs_path)
    _require_rknn_weight_when_enabled(abs_path)

    if get_inference_backend() == "rknn" and is_rknn_model_path(abs_path):
        from src.rknn_yolo import RknnYoloAdapter

        names = class_names or {0: "object"}
        imgsz = int(os.getenv("RKNN_IMGSZ", "640") or 640)
        model = RknnYoloAdapter(abs_path, names, imgsz=imgsz)
        return model, "npu", True

    use_cuda = cuda_available() and is_gpu

    if _is_onnx(abs_path):
        names = class_names or class_names_from_onnx_metadata(abs_path)
        if not names:
            names = {0: "face"} if is_face_type(models_type) else {0: "object"}
        model = OnnxYoloAdapter(abs_path, names, use_cuda=use_cuda and use_ultralytics())
        infer_device = "0" if use_cuda else "cpu"
        return model, infer_device, True

    if not use_ultralytics():
        raise RuntimeError(
            "边缘 ONNX 模式仅支持 .onnx / .rknn 权重。"
            f"当前文件: {abs_path}"
        )

    import torch
    from ultralytics import YOLO

    os.environ.setdefault("YOLO_VERBOSE", "0")
    task_type = resolve_yolo_task(models_type)
    model = YOLO(abs_path, task=task_type)
    infer_device = torch.device("cuda" if use_cuda else "cpu")
    model.to(infer_device)
    if use_cuda and hasattr(model, "model") and hasattr(model.model, "half"):
        try:
            model.model.half()
        except Exception:
            pass
    return model, infer_device, False


def predict_detection_frame(
    model,
    frame: np.ndarray,
    *,
    infer_device,
    is_onnx: bool,
    confidence: float = 0.5,
    iou: float = 0.45,
    max_det: int = 300,
):
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        raise ValueError("无效的检测帧")
    frame = np.ascontiguousarray(frame)
    kwargs = {
        "conf": confidence,
        "iou": iou,
        "max_det": max_det,
        "verbose": False,
        "half": False,
        "device": infer_device,
    }
    return model(frame, **kwargs)


def load_yolo_model_classes(
    file_path: str,
    models_type: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[int, str]:
    from src.env_loader import configure_ultralytics_env

    configure_ultralytics_env()
    parameters = normalize_model_parameters(parameters)

    abs_path = _resolve_model_path(file_path)
    _require_ultralytics_for_task(models_type)
    ext = os.path.splitext(abs_path)[1].lower()

    if ext == ".onnx":
        classes = class_names_from_onnx_metadata(abs_path)
        if not classes:
            classes = classes_from_parameters(parameters)
        if not classes:
            raise RuntimeError(
                "ONNX 模型未解析到类别。"
                '请在「参数」JSON 中填写 {"classes": {"0": "face"}} 后重试。'
            )
        return classes

    if ext == ".rknn":
        classes = classes_from_parameters(parameters)
        if not classes:
            raise RuntimeError('RKNN 模型请在「参数」JSON 中填写 {"classes": {"0": "person"}}')
        return classes

    if not use_ultralytics():
        onnx_alt = os.path.splitext(abs_path)[0] + ".onnx"
        if os.path.exists(onnx_alt):
            return load_yolo_model_classes(onnx_alt, models_type, parameters)
        raise RuntimeError(
            f"EDGE_INFERENCE={get_inference_backend()} 下请上传 .onnx 或提供同名 .onnx 文件。"
        )

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "当前环境未安装 ultralytics。边缘设备请使用 ONNX 模型并设置 EDGE_INFERENCE=onnx。"
        ) from exc

    task = resolve_yolo_task(models_type)
    load_errors: List[str] = []
    candidates = [(task, abs_path), ("auto", abs_path)]
    model = None
    for task_name, path in candidates:
        try:
            model = YOLO(path) if task_name == "auto" else YOLO(path, task=task_name)
            break
        except Exception as exc:
            load_errors.append(f"{task_name}: {exc}")

    if model is None:
        detail = "；".join(load_errors[-2:]) if load_errors else "未知错误"
        raise RuntimeError(f"无法加载模型: {detail}")

    classes = normalize_yolo_class_names(getattr(model, "names", None))
    if not classes:
        classes = classes_from_parameters(parameters)
    if not classes:
        raise RuntimeError("模型加载成功但未解析到类别。")
    return classes
