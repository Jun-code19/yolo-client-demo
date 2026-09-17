"""多场景智能分析：同一路流并发评估多个 ROI 场景"""
from __future__ import annotations

import time
import uuid
from collections import deque
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

SCENARIO_TYPE_LABELS = {
    "leave_post": "离岗检测",
    "crowd_gather": "聚众检测",
    "loitering": "徘徊检测",
    "behavior": "行为分析",
    "counting": "人数统计",
}


def normalize_smart_config(area_coordinates: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """统一智能配置结构，兼容旧版单场景 area_coordinates"""
    if not area_coordinates:
        return {"version": 2, "scenarios": [], "global": _default_global()}

    if area_coordinates.get("version") == 2 or area_coordinates.get("scenarios") is not None:
        scenarios = area_coordinates.get("scenarios") or []
        return {
            "version": 2,
            "scenarios": scenarios,
            "global": {
                "alarm_interval": area_coordinates.get("alarm_interval", 15),
                "pushLabel": area_coordinates.get("pushLabel", "") or "",
            },
        }

    analysis_type = area_coordinates.get("analysisType")
    if not analysis_type or analysis_type == "none":
        return {"version": 2, "scenarios": [], "global": _extract_global(area_coordinates)}

    legacy = deepcopy(area_coordinates)
    legacy.setdefault("id", "legacy-1")
    legacy.setdefault("name", SCENARIO_TYPE_LABELS.get(analysis_type, "智能场景"))
    legacy.setdefault("enabled", True)
    legacy["type"] = "behavior" if analysis_type == "behavior" else "counting"
    return {"version": 2, "scenarios": [legacy], "global": _extract_global(area_coordinates)}


def is_multi_scenario_config(area_coordinates: Optional[Dict[str, Any]]) -> bool:
    if not area_coordinates:
        return False
    if area_coordinates.get("scenarios") is not None:
        return True
    return area_coordinates.get("version") == 2


def _default_global() -> Dict[str, Any]:
    return {"alarm_interval": 15, "pushLabel": ""}


def _extract_global(area_coordinates: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "alarm_interval": area_coordinates.get("alarm_interval", 15),
        "pushLabel": area_coordinates.get("pushLabel", "") or "",
    }


def _points_to_pixels(points: List[Dict[str, Any]], frame_shape: Tuple[int, int, int]) -> List[Tuple[int, int]]:
    h, w = frame_shape[:2]
    result = []
    for point in points or []:
        result.append((int(float(point["x"]) * w), int(float(point["y"]) * h)))
    return result


def _resolve_counting_type(raw: Dict[str, Any]) -> str:
    counting_type = raw.get("countingType")
    if counting_type:
        return counting_type
    catalog = raw.get("catalogType")
    if catalog == "flow_count":
        return "flow"
    if catalog == "occupancy":
        return "occupancy"
    return "occupancy"


def _crossing_direction(prev_point, current_point, flow_period: str = "detect_in") -> str:
    if current_point[1] > prev_point[1]:
        return "in" if flow_period == "detect_in" else "out"
    return "out" if flow_period == "detect_in" else "in"


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


class ScenarioProcessor:
    """在同一路检测流上并发评估多个场景"""

    def __init__(self):
        self.tracker = None
        self.frame_shape = None
        self.normalized: Dict[str, Any] = {"version": 2, "scenarios": [], "global": _default_global()}
        self.parsed_scenarios: List[Dict[str, Any]] = []
        self.states: Dict[str, Dict[str, Any]] = {}

    def configure(self, area_coordinates: Optional[Dict[str, Any]], frame_shape, tracker) -> None:
        self.tracker = tracker
        self.frame_shape = frame_shape
        self.normalized = normalize_smart_config(area_coordinates)
        self.parsed_scenarios = []
        self.states = {}

        for raw in self.normalized.get("scenarios") or []:
            if raw.get("enabled") is False:
                continue
            parsed = self._parse_scenario(raw)
            if not parsed:
                continue
            self.parsed_scenarios.append(parsed)
            self.states[parsed["id"]] = self._init_state(parsed)

    @property
    def is_active(self) -> bool:
        return bool(self.parsed_scenarios)

    def _parse_scenario(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        scenario_type = raw.get("type") or raw.get("analysisType")
        if scenario_type == "behavior":
            scenario_type = "behavior"
        elif scenario_type == "counting":
            scenario_type = "counting"
        elif scenario_type not in SCENARIO_TYPE_LABELS:
            return None

        params = raw.get("params") or {}
        points = raw.get("points") or []
        occupancy_areas = raw.get("occupancyAreas") or []

        parsed = {
            "id": raw.get("id") or str(uuid.uuid4()),
            "name": raw.get("name") or SCENARIO_TYPE_LABELS.get(scenario_type, scenario_type),
            "type": scenario_type,
            "points": _points_to_pixels(points, self.frame_shape) if points else [],
            "params": params,
            "pushLabel": raw.get("pushLabel") or "",
            "raw": raw,
        }

        if scenario_type == "counting" and _resolve_counting_type(raw) == "occupancy":
            areas = occupancy_areas or ([{"points": points}] if len(points) >= 3 else [])
            parsed["polygons"] = []
            for index, area in enumerate(areas):
                area_points = area.get("points") or []
                pixel_points = _points_to_pixels(area_points, self.frame_shape)
                if len(pixel_points) >= 3:
                    parsed["polygons"].append({
                        "id": area.get("id") or f"area-{index}",
                        "name": area.get("name") or f"区域{index + 1}",
                        "points": pixel_points,
                    })
            if not parsed["polygons"]:
                return None
        elif scenario_type in ("leave_post", "crowd_gather", "loitering", "behavior") and raw.get("behaviorType") != "line":
            if len(parsed["points"]) >= 3:
                parsed["polygons"] = [{"id": "main", "name": parsed["name"], "points": parsed["points"]}]
            else:
                return None
        elif scenario_type == "behavior" and raw.get("behaviorType") == "line":
            if len(parsed["points"]) < 2:
                return None
        elif scenario_type == "counting" and _resolve_counting_type(raw) == "flow":
            if len(parsed["points"]) < 2:
                return None

        return parsed

    def _init_state(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "condition_since": None,
            "last_trigger_at": 0.0,
            "line_crossed_tracks": {},
            "track_area_state": {},
            "today_in_count": 0,
            "today_out_count": 0,
            "current_count": 0,
            "display_total": 0,
            "decrease_hold": 0,
            "occupancy_history": {},
            "last_stats_emit": 0.0,
        }

    def process(self) -> Dict[str, Dict[str, Any]]:
        if not self.tracker or not self.parsed_scenarios:
            return {}

        events: Dict[str, Dict[str, Any]] = {}
        for parsed in self.parsed_scenarios:
            scenario_type = parsed["type"]
            if scenario_type == "leave_post":
                events.update(self._process_leave_post(parsed))
            elif scenario_type == "crowd_gather":
                events.update(self._process_crowd_gather(parsed))
            elif scenario_type == "loitering":
                events.update(self._process_loitering(parsed))
            elif scenario_type == "behavior":
                events.update(self._process_behavior(parsed))
            elif scenario_type == "counting":
                events.update(self._process_counting(parsed))
        return events

    def _scenario_push_label(self, parsed: Dict[str, Any]) -> str:
        return parsed.get("pushLabel") or self.normalized.get("global", {}).get("pushLabel") or ""

    def _cooldown_sec(self, parsed: Dict[str, Any]) -> float:
        params = parsed.get("params") or {}
        raw = parsed.get("raw") or {}
        value = params.get("alarmInterval")
        if value is None:
            value = raw.get("alarm_interval")
        if value is None:
            value = self.normalized.get("global", {}).get("alarm_interval", 15)
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return 15.0

    def _can_trigger(self, parsed: Dict[str, Any], state: Dict[str, Any]) -> bool:
        cooldown = self._cooldown_sec(parsed)
        if cooldown <= 0:
            return True
        return (time.time() - state.get("last_trigger_at", 0.0)) >= cooldown

    def _mark_triggered(self, state: Dict[str, Any]) -> None:
        state["last_trigger_at"] = time.time()
        state["condition_since"] = None

    def _primary_polygon(self, parsed: Dict[str, Any]) -> Optional[List[Tuple[int, int]]]:
        polygons = parsed.get("polygons") or []
        if polygons:
            return polygons[0]["points"]
        points = parsed.get("points") or []
        return points if len(points) >= 3 else None

    def _occupancy_settings(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "count_min_hits": int(raw.get("countMinHits", 3)),
            "count_point_mode": raw.get("countPointMode", "foot"),
            "smooth_window": max(1, int(raw.get("smoothWindow", 3))),
            "decrease_hold_frames": max(0, int(raw.get("decreaseHoldFrames", 2))),
            "count_bias": float(raw.get("countBias", 0)),
            "count_scale": float(raw.get("countScale", 1.0)),
            "max_capacity": raw.get("maxCapacity"),
            "counting_interval": max(1, int(raw.get("countingInterval", 5))),
        }

    def _track_counts_for_scenario(self, track: Dict[str, Any], settings: Dict[str, Any]) -> bool:
        if track.get("age", 0) > 0:
            return False
        hits = track.get("hits", 0)
        if hits >= settings["count_min_hits"]:
            track["confirmed"] = True
        return track.get("confirmed", False)

    def _track_in_polygon(self, track: Dict[str, Any], polygon: List[Tuple[int, int]], settings: Dict[str, Any]) -> bool:
        bbox = track["box"]
        mode = settings["count_point_mode"]
        if mode == "center":
            return self.tracker._point_in_polygon(track["center"], polygon)
        if mode == "bottom_edge":
            x1, y1, x2, y2 = bbox
            probe_points = [((x1 + x2) / 2, y2), (x1, y2), (x2, y2)]
            return any(self.tracker._point_in_polygon(point, polygon) for point in probe_points)
        foot_point = self.tracker._get_foot_point(bbox)
        return self.tracker._point_in_polygon(foot_point, polygon)

    def _count_persons(self, polygon: List[Tuple[int, int]], settings: Optional[Dict[str, Any]] = None) -> int:
        settings = settings or {"count_min_hits": 1, "count_point_mode": "foot"}
        candidates = []
        for track_id in self.tracker.active_tracks:
            track = self.tracker.trackers.get(track_id)
            if not track or not self._track_counts_for_scenario(track, settings):
                continue
            if self._track_in_polygon(track, polygon, settings):
                candidates.append(track)

        unique_tracks = []
        for track in candidates:
            if any(self.tracker._calculate_iou(track["box"], kept["box"]) > 0.45 for kept in unique_tracks):
                continue
            unique_tracks.append(track)
        return len(unique_tracks)

    def _smooth_scenario_count(self, state: Dict[str, Any], area_id: str, raw_count: int, window_size: int) -> int:
        history_map = state.setdefault("occupancy_history", {})
        if area_id not in history_map:
            history_map[area_id] = deque(maxlen=max(window_size, 1))
        history_map[area_id].append(raw_count)
        return int(round(_median(list(history_map[area_id]))))

    def _apply_scenario_calibration(self, count: int, settings: Dict[str, Any]) -> int:
        calibrated = round(settings["count_scale"] * count + settings["count_bias"])
        max_capacity = settings.get("max_capacity")
        if max_capacity:
            calibrated = min(calibrated, int(max_capacity))
        return max(0, calibrated)

    def _apply_scenario_decrease_hysteresis(self, state: Dict[str, Any], smoothed_total: int, hold_frames: int) -> int:
        if smoothed_total <= 0:
            state["decrease_hold"] = 0
            state["display_total"] = 0
            return 0

        display_total = state.get("display_total", 0)
        if smoothed_total >= display_total:
            state["decrease_hold"] = 0
            state["display_total"] = smoothed_total
            return smoothed_total
        if hold_frames <= 0:
            state["display_total"] = smoothed_total
            return smoothed_total
        decrease_hold = state.get("decrease_hold", 0)
        if decrease_hold < hold_frames:
            state["decrease_hold"] = decrease_hold + 1
            return display_total
        state["display_total"] = smoothed_total
        state["decrease_hold"] = 0
        return smoothed_total

    def _find_line_cross(
        self,
        parsed: Dict[str, Any],
        track_id: int,
        track: Dict[str, Any],
        state: Dict[str, Any],
        raw: Dict[str, Any],
        *,
        behavior_subtype: str = "simple",
        behavior_direction: str = "in",
    ) -> Optional[Dict[str, Any]]:
        line_points = parsed.get("points") or []
        if len(line_points) < 2 or track_id in state["line_crossed_tracks"]:
            return None

        trajectory = track.get("trajectory") or []
        if len(trajectory) < 2:
            return None

        self.tracker.area_points = line_points
        max_segments = min(8, len(trajectory) - 1)
        start_index = max(0, len(trajectory) - max_segments - 1)

        flow_period = raw.get("flowPeriod", "detect_in")
        for index in range(start_index, len(trajectory) - 1):
            prev_center = trajectory[index]
            current_center = trajectory[index + 1]
            crossed, intersection = self.tracker._crossed_line(track_id, current_center, prev_center)
            if not crossed:
                continue

            direction = _crossing_direction(prev_center, current_center, flow_period)
            if behavior_subtype == "directional":
                if not (
                    (behavior_direction == "in" and direction == "in")
                    or (behavior_direction == "out" and direction == "out")
                ):
                    continue
                event_type = f"line_cross_{direction}"
            else:
                event_type = "line_cross"

            state["line_crossed_tracks"][track_id] = direction
            return {
                "event_type": event_type,
                "direction": direction,
                "position": intersection or current_center,
            }
        return None

    def _emit_event(
        self,
        parsed: Dict[str, Any],
        event_type: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        state = self.states[parsed["id"]]
        if not self._can_trigger(parsed, state):
            return {}

        self._mark_triggered(state)
        payload = {
            "scenario_id": parsed["id"],
            "scenario_name": parsed["name"],
            "scenario_type": parsed["type"],
            "event_type": event_type,
            "pushLabel": self._scenario_push_label(parsed),
            "timestamp": self.tracker.frame_count,
        }
        if extra:
            payload.update(extra)
        return {f"{parsed['id']}:{event_type}": payload}

    def _process_duration_scenario(
        self,
        parsed: Dict[str, Any],
        count: int,
        active_when,
        event_type: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        state = self.states[parsed["id"]]
        params = parsed.get("params") or {}
        duration_sec = float(params.get("durationSec", params.get("duration_sec", 30)))

        if active_when(count):
            if state["condition_since"] is None:
                state["condition_since"] = time.time()
            elif (time.time() - state["condition_since"]) >= duration_sec:
                data = {"current_count": count, "duration_sec": duration_sec}
                if extra:
                    data.update(extra)
                return self._emit_event(parsed, event_type, data)
        else:
            state["condition_since"] = None
        return {}

    def _process_leave_post(self, parsed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        polygon = self._primary_polygon(parsed)
        if not polygon:
            return {}
        params = parsed.get("params") or {}
        min_persons = int(params.get("minPersons", params.get("min_persons", 1)))
        count = self._count_persons(polygon)
        return self._process_duration_scenario(
            parsed,
            count,
            lambda value: value < min_persons,
            "leave_post_alert",
            {"min_persons": min_persons, "threshold_persons": min_persons},
        )

    def _process_crowd_gather(self, parsed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        polygon = self._primary_polygon(parsed)
        if not polygon:
            return {}
        params = parsed.get("params") or {}
        min_persons = int(params.get("minPersons", params.get("min_persons", 5)))
        count = self._count_persons(polygon)
        return self._process_duration_scenario(
            parsed,
            count,
            lambda value: value >= min_persons,
            "crowd_gather_alert",
            {"min_persons": min_persons, "threshold_persons": min_persons},
        )

    def _process_loitering(self, parsed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """徘徊：规则层，基于 ROI 内人数事实 + 持续时长"""
        polygon = self._primary_polygon(parsed)
        if not polygon:
            return {}
        params = parsed.get("params") or {}
        min_persons = int(params.get("minPersons", params.get("min_persons", 1)))
        count = self._count_persons(polygon)
        return self._process_duration_scenario(
            parsed,
            count,
            lambda value: value >= min_persons,
            "loitering_alert",
            {"min_persons": min_persons, "threshold_persons": min_persons},
        )

    def _process_behavior(self, parsed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        raw = parsed.get("raw") or {}
        behavior_type = raw.get("behaviorType", "area")
        behavior_subtype = raw.get("behaviorSubtype", "simple")
        behavior_direction = raw.get("behaviorDirection", "in")
        state = self.states[parsed["id"]]
        events: Dict[str, Dict[str, Any]] = {}

        if behavior_type == "line" and len(parsed.get("points") or []) >= 2:
            self.tracker.area_points = parsed["points"]

        for track_id in self.tracker.active_tracks:
            track = self.tracker.trackers.get(track_id)
            if not track or len(track.get("trajectory", [])) < 2:
                continue
            prev_center = track["trajectory"][-2]
            current_center = track["center"]

            if behavior_type == "area":
                polygon = self._primary_polygon(parsed)
                if not polygon:
                    continue
                current_in = self.tracker._point_in_polygon(current_center, polygon)
                prev_in = self.tracker._point_in_polygon(prev_center, polygon)
                event_type = None
                if behavior_subtype == "simple":
                    if current_in and not prev_in:
                        event_type = "area_enter"
                    elif not current_in and prev_in:
                        event_type = "area_exit"
                elif behavior_subtype == "directional":
                    if behavior_direction == "in" and current_in and not prev_in:
                        event_type = "area_enter"
                    elif behavior_direction == "out" and not current_in and prev_in:
                        event_type = "area_exit"
                if event_type:
                    key = f"{parsed['id']}:{track_id}:{event_type}"
                    if key not in events:
                        events[key] = {
                            "scenario_id": parsed["id"],
                            "scenario_name": parsed["name"],
                            "scenario_type": "behavior",
                            "analysisType": "behavior",
                            "event_type": event_type,
                            "track_id": track_id,
                            "position": current_center,
                            "pushLabel": self._scenario_push_label(parsed),
                            "behavior_type": behavior_type,
                            "behavior_subtype": behavior_subtype,
                            "behavior_direction": behavior_direction,
                            "timestamp": self.tracker.frame_count,
                        }
            else:
                cross_info = self._find_line_cross(
                    parsed,
                    track_id,
                    track,
                    state,
                    raw,
                    behavior_subtype=behavior_subtype,
                    behavior_direction=behavior_direction,
                )
                if not cross_info:
                    continue
                event_type = cross_info["event_type"]
                key = f"{parsed['id']}:{track_id}:{event_type}"
                events[key] = {
                    "scenario_id": parsed["id"],
                    "scenario_name": parsed["name"],
                    "scenario_type": "behavior",
                    "analysisType": "behavior",
                    "event_type": event_type,
                    "track_id": track_id,
                    "position": cross_info["position"],
                    "pushLabel": self._scenario_push_label(parsed),
                    "behavior_type": behavior_type,
                    "behavior_subtype": behavior_subtype,
                    "behavior_direction": behavior_direction,
                    "timestamp": self.tracker.frame_count,
                }

        return events

    def _process_counting(self, parsed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        raw = parsed.get("raw") or {}
        counting_type = _resolve_counting_type(raw)
        state = self.states[parsed["id"]]
        events: Dict[str, Dict[str, Any]] = {}

        if counting_type == "occupancy":
            settings = self._occupancy_settings(raw)
            polygons = parsed.get("polygons") or []
            if not polygons:
                return events

            smoothed_area_counts: Dict[str, Dict[str, Any]] = {}
            for area in polygons:
                raw_count = self._count_persons(area["points"], settings)
                smoothed_count = self._smooth_scenario_count(state, area["id"], raw_count, settings["smooth_window"])
                smoothed_area_counts[area["id"]] = {
                    "name": area["name"],
                    "smoothed_count": smoothed_count,
                    "raw_count": raw_count,
                }

            smoothed_total = sum(item["smoothed_count"] for item in smoothed_area_counts.values())
            hysteresis_total = self._apply_scenario_decrease_hysteresis(
                state,
                smoothed_total,
                settings["decrease_hold_frames"],
            )
            current_total = self._apply_scenario_calibration(hysteresis_total, settings)

            area_counts: Dict[str, Dict[str, Any]] = {}
            area_items = list(smoothed_area_counts.items())
            if len(area_items) == 1:
                area_id, info = area_items[0]
                area_counts[area_id] = {
                    "name": info["name"],
                    "count": current_total,
                    "raw_count": info["raw_count"],
                }
            elif current_total > 0 and smoothed_total > 0:
                allocated = 0
                for index, (area_id, info) in enumerate(area_items):
                    if index == len(area_items) - 1:
                        area_display = max(0, current_total - allocated)
                    else:
                        area_display = max(0, round(current_total * info["smoothed_count"] / smoothed_total))
                        allocated += area_display
                    area_counts[area_id] = {
                        "name": info["name"],
                        "count": area_display,
                        "raw_count": info["raw_count"],
                    }
            else:
                for area_id, info in area_items:
                    area_counts[area_id] = {
                        "name": info["name"],
                        "count": 0,
                        "raw_count": info["raw_count"],
                    }

            old_count = state.get("current_count", 0)
            state["current_count"] = current_total
            state["area_counts"] = area_counts

            enable_alert = raw.get("enableAlert", False)
            alert_threshold = raw.get("alertThreshold")
            if enable_alert and alert_threshold is not None and current_total >= int(alert_threshold):
                events.update(
                    self._emit_event(
                        parsed,
                        "occupancy_alert",
                        {
                            "current_count": current_total,
                            "alert_threshold": alert_threshold,
                            "area_counts": area_counts,
                            "analysisType": "counting",
                            "counting_type": "occupancy",
                        },
                    )
                )
                return events

            now = time.time()
            count_changed = current_total != old_count
            interval_ok = (now - state.get("last_stats_emit", 0.0)) >= settings["counting_interval"]

            if count_changed:
                change_type = "increase" if current_total > old_count else "decrease"
                change_amount = abs(current_total - old_count)
                if current_total > old_count:
                    state["today_in_count"] = state.get("today_in_count", 0) + change_amount
                else:
                    state["today_out_count"] = state.get("today_out_count", 0) + change_amount

                event_type = f"occupancy_change_{change_type}"
                state["last_stats_emit"] = now
                key = f"{parsed['id']}:{event_type}:{old_count}->{current_total}:{now}"
                events[key] = {
                    "scenario_id": parsed["id"],
                    "scenario_name": parsed["name"],
                    "scenario_type": "counting",
                    "analysisType": "counting",
                    "counting_type": "occupancy",
                    "event_type": event_type,
                    "previous_count": old_count,
                    "change_amount": change_amount,
                    "current_count": current_total,
                    "area_counts": area_counts,
                    "today_in_count": state.get("today_in_count", 0),
                    "today_out_count": state.get("today_out_count", 0),
                    "pushLabel": self._scenario_push_label(parsed),
                    "timestamp": self.tracker.frame_count,
                }
            elif interval_ok:
                push_label = self._scenario_push_label(parsed)
                state["last_stats_emit"] = now
                if not push_label:
                    return events
                key = f"{parsed['id']}:occupancy_report:{current_total}:{int(now)}"
                events[key] = {
                    "scenario_id": parsed["id"],
                    "scenario_name": parsed["name"],
                    "scenario_type": "counting",
                    "analysisType": "counting",
                    "counting_type": "occupancy",
                    "event_type": "occupancy_report",
                    "previous_count": current_total,
                    "change_amount": 0,
                    "current_count": current_total,
                    "area_counts": area_counts,
                    "today_in_count": state.get("today_in_count", 0),
                    "today_out_count": state.get("today_out_count", 0),
                    "pushLabel": push_label,
                    "timestamp": self.tracker.frame_count,
                    "_periodic_only": True,
                }
            return events

        if len(parsed.get("points") or []) >= 2:
            self.tracker.area_points = parsed["points"]

        flow_direction = raw.get("flowDirection", "bidirectional")
        for track_id in self.tracker.active_tracks:
            track = self.tracker.trackers.get(track_id)
            if not track:
                continue
            cross_info = self._find_line_cross(
                parsed,
                track_id,
                track,
                state,
                raw,
                behavior_subtype="simple",
                behavior_direction="in",
            )
            if not cross_info:
                continue

            direction = cross_info["direction"]
            should_count = (
                flow_direction == "bidirectional"
                or (flow_direction == "in" and direction == "in")
                or (flow_direction == "out" and direction == "out")
            )
            if not should_count:
                continue

            if direction == "in":
                state["today_in_count"] += 1
            else:
                state["today_out_count"] += 1

            event_type = f"line_cross_{direction}"
            key = f"{parsed['id']}:{track_id}:{event_type}"
            events[key] = {
                "scenario_id": parsed["id"],
                "scenario_name": parsed["name"],
                "scenario_type": "counting",
                "analysisType": "counting",
                "counting_type": "flow",
                "event_type": event_type,
                "track_id": track_id,
                "position": cross_info["position"],
                "current_count": state.get("current_count", 0),
                "today_in_count": state["today_in_count"],
                "today_out_count": state["today_out_count"],
                "pushLabel": self._scenario_push_label(parsed),
                "timestamp": self.tracker.frame_count,
            }
        return events

    def get_display_overlays(self) -> List[Dict[str, Any]]:
        """供画面叠加显示：区域人数、人流进出等"""
        overlays: List[Dict[str, Any]] = []
        for parsed in self.parsed_scenarios:
            state = self.states.get(parsed["id"], {})
            raw = parsed.get("raw") or {}
            if parsed.get("type") != "counting":
                continue

            counting_type = _resolve_counting_type(raw)
            if counting_type == "occupancy":
                area_counts = state.get("area_counts") or {}
                for area in parsed.get("polygons") or []:
                    count_info = area_counts.get(area["id"], {})
                    overlays.append({
                        "kind": "occupancy",
                        "scenario_name": parsed.get("name"),
                        "area_name": area.get("name") or count_info.get("name") or "区域",
                        "count": count_info.get("count", 0),
                        "points": area.get("points") or [],
                    })
            elif counting_type == "flow":
                flow_direction = raw.get("flowDirection", "bidirectional")
                overlays.append({
                    "kind": "flow",
                    "scenario_name": parsed.get("name"),
                    "today_in_count": state.get("today_in_count", 0),
                    "today_out_count": state.get("today_out_count", 0),
                    "flow_direction": flow_direction,
                    "points": parsed.get("points") or [],
                })
        return overlays

    def get_overlay_scenarios(self) -> List[Dict[str, Any]]:
        return self.parsed_scenarios
