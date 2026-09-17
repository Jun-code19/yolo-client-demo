"""
目标追踪模块 - 用于追踪目标，并进行智能分析
"""
import cv2
import numpy as np
from collections import deque
from typing import Tuple
import colorsys
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from src.smart_scenarios import ScenarioProcessor, is_multi_scenario_config

class ObjectTracker:
    def __init__(self, max_age=30, min_hits=3, iou_threshold=0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.trackers = {}
        self.frame_count = 0
        self.colors = {}
        self.class_colors = {}
        self.next_id = 0
        self.active_tracks = set()  # 添加活跃轨迹集合
        self.trajectory_buffer = {}  # 添加轨迹缓冲区
        self.interpolation_threshold = 50  # 插值阈值
        
        # 智能分析相关
        self.area_coordinates = None
        self.area_points = None
        self.area_polygons = []  # 多区域人数统计
        self.area_counts = {}  # 各区域独立人数 {area_id: {name, count}}
        self.current_count = 0  # 总人数（各区域之和，用于报警）
        self.today_in_count = 0  # 今日进入总数
        self.today_out_count = 0  # 今日离开总数
        self.triggered_events = {}  # 已触发的事件，避免重复触发
        self.line_crossed_tracks = {}  # 记录已过线的轨迹
        self.date = datetime.now().strftime("%Y-%m-%d")  # 记录当前日期
        self._occupancy_history = {}  # 各区域原始人数历史 {area_id: deque}
        self._display_total = 0
        self._decrease_hold = 0
        self.scenario_processor = ScenarioProcessor()
        self.multi_scenario_mode = False

        # 尝试加载中文字体，如果失败则使用默认字体
        try:
            # Windows系统中文字体路径
            self.font_path = "C:/Windows/Fonts/simhei.ttf"  # 黑体
            self.font = ImageFont.truetype(self.font_path, 30)
            self.font_small = ImageFont.truetype(self.font_path, 16)
        except:
            try:
                # 尝试其他常见中文字体
                self.font_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"  # 微软雅黑
                self.font = ImageFont.truetype(self.font_path, 30)
                self.font_small = ImageFont.truetype(self.font_path, 16)
            except:
                # 如果都找不到，使用默认字体
                self.font = ImageFont.load_default()
                self.font_small = ImageFont.load_default()

    def _generate_colors(self, num_classes):
        hsv_tuples = [(x / num_classes, 1., 1.) for x in range(num_classes)]
        colors = list(map(lambda x: colorsys.hsv_to_rgb(*x), hsv_tuples))
        colors = list(map(lambda x: (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)), colors))
        return colors

    def _assign_color(self, class_id):
        if class_id not in self.class_colors:
            if not self.class_colors:
                colors = self._generate_colors(100)  # 假设最多100个类别
                self.class_colors = {i: color for i, color in enumerate(colors)}
            else:
                self.class_colors[class_id] = tuple(np.random.randint(0, 255, 3).tolist())
        return self.class_colors[class_id]
    
    def set_area_coordinates(self, area_coordinates, frame_shape):
        """设置区域坐标"""
        self.area_coordinates = area_coordinates
        self.frame_shape = frame_shape
        self.area_points = None
        self.area_polygons = []
        self.area_counts = {}
        self._occupancy_history = {}
        self._display_total = 0
        self._decrease_hold = 0
        self.multi_scenario_mode = is_multi_scenario_config(area_coordinates)

        if not area_coordinates:
            self.scenario_processor = ScenarioProcessor()
            return

        if self.multi_scenario_mode:
            self.scenario_processor.configure(area_coordinates, frame_shape, self)
            return

        h, w = frame_shape[:2]

        if area_coordinates.get('countingType') == 'occupancy':
            occupancy_areas = area_coordinates.get('occupancyAreas') or []
            if occupancy_areas:
                for i, area in enumerate(occupancy_areas):
                    area_points = area.get('points') or []
                    if len(area_points) >= 3:
                        pixel_points = [(int(p['x'] * w), int(p['y'] * h)) for p in area_points]
                        self.area_polygons.append({
                            'id': area.get('id', f'area-{i}'),
                            'name': area.get('name', f'区域{i + 1}'),
                            'points': pixel_points
                        })
            elif area_coordinates.get('points'):
                pixel_points = [(int(p['x'] * w), int(p['y'] * h)) for p in area_coordinates['points']]
                self.area_polygons = [{
                    'id': 'area-0',
                    'name': '区域1',
                    'points': pixel_points
                }]

            if self.area_polygons:
                self.area_points = self.area_polygons[0]['points']
            return

        if area_coordinates.get('points'):
            self.area_points = [(int(p['x'] * w), int(p['y'] * h)) for p in area_coordinates['points']]
    
    def _point_in_polygon(self, point, polygon):
        """判断点是否在多边形内（Ray casting算法）"""
        if not polygon or len(polygon) < 3:
            return False
            
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _line_intersection(self, line1, line2):
        """计算两条线段的交点"""
        (x1, y1), (x2, y2) = line1
        (x3, y3), (x4, y4) = line2
        
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None  # 平行线
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
        
        if 0 <= t <= 1 and 0 <= u <= 1:
            ix = x1 + t * (x2 - x1)
            iy = y1 + t * (y2 - y1)
            return (ix, iy)
        
        return None
    
    def _crossed_line(self, track_id, current_point, previous_point):
        """检测是否穿越了拌线"""
        if not self.area_points or len(self.area_points) < 2:
            return False, None
        
        # 构建拌线段
        for i in range(len(self.area_points) - 1):
            line_segment = (self.area_points[i], self.area_points[i + 1])
            trajectory_segment = (previous_point, current_point)
            
            intersection = self._line_intersection(line_segment, trajectory_segment)
            if intersection:
                return True, intersection
        
        return False, None
    
    def _analyze_behavior(self, track_id, current_center, prev_center):
        """分析行为逻辑"""
        analysis_type = self.area_coordinates.get('analysisType')
        
        if analysis_type == 'behavior':
            self._analyze_behavior_detection(track_id, current_center, prev_center)
        elif analysis_type == 'counting':
            self._analyze_counting(track_id, current_center, prev_center)
    
    def _analyze_behavior_detection(self, track_id, current_center, prev_center):
        """通用行为分析"""
        behavior_type = self.area_coordinates.get('behaviorType')
        behavior_subtype = self.area_coordinates.get('behaviorSubtype', 'simple')
        behavior_direction = self.area_coordinates.get('behaviorDirection', 'in')
        
        if behavior_type == 'area':
            # 区域检测
            current_in_area = self._point_in_polygon(current_center, self.area_points)
            prev_in_area = self._point_in_polygon(prev_center, self.area_points)
            
            if behavior_subtype == 'simple':
                # 普通检测：只要进入区域就触发
                if current_in_area and not prev_in_area:
                    self._trigger_behavior_event(track_id, 'area_enter', current_center)
                elif not current_in_area and prev_in_area:
                    self._trigger_behavior_event(track_id, 'area_exit', current_center)
            elif behavior_subtype == 'directional':
                # 方向检测：只检测指定方向
                if behavior_direction == 'in' and current_in_area and not prev_in_area:
                    self._trigger_behavior_event(track_id, 'area_enter', current_center)
                elif behavior_direction == 'out' and not current_in_area and prev_in_area:
                    self._trigger_behavior_event(track_id, 'area_exit', current_center)
        
        elif behavior_type == 'line':
            # 拌线检测
            crossed, intersection = self._crossed_line(track_id, current_center, prev_center)
            
            if crossed:
                if behavior_subtype == 'simple':
                    # 普通检测：穿越拌线就触发
                    self._trigger_behavior_event(track_id, 'line_cross', intersection or current_center)
                elif behavior_subtype == 'directional':
                    # 方向检测：需要判断穿越方向
                    direction = self._get_crossing_direction(prev_center, current_center)
                    if (behavior_direction == 'in' and direction == 'in') or \
                       (behavior_direction == 'out' and direction == 'out'):
                        self._trigger_behavior_event(track_id, f'line_cross_{direction}', intersection or current_center)
    
    def _analyze_counting(self, track_id, current_center, prev_center):
        """人数统计分析"""
        counting_type = self.area_coordinates.get('countingType')
        
        if counting_type == 'occupancy':
            # 区域内人数统计 - 每帧重新统计区域内的实际人数
            if self.date != datetime.now().strftime("%Y-%m-%d"):
                self.today_in_count = 0
                self.today_out_count = 0
                self.date = datetime.now().strftime("%Y-%m-%d")
            # 不需要依赖进出事件，直接统计当前帧中所有在区域内的目标
            # pass  # 实际统计在update方法中进行
        
        elif counting_type == 'flow':
            
            # 如果日期发生变化，重置今日计数
            if self.date != datetime.now().strftime("%Y-%m-%d"):
                self.today_in_count = 0
                self.today_out_count = 0
                self.date = datetime.now().strftime("%Y-%m-%d")

            # 人流统计
            crossed, intersection = self._crossed_line(track_id, current_center, prev_center)
            
            if crossed and track_id not in self.line_crossed_tracks:
                direction = self._get_crossing_direction(prev_center, current_center)
                flow_direction = self.area_coordinates.get('flowDirection', 'bidirectional')
                
                # 根据流向设置判断是否计数
                should_count = False
                if flow_direction == 'bidirectional':
                    should_count = True
                elif flow_direction == 'in' and direction == 'in':
                    should_count = True
                elif flow_direction == 'out' and direction == 'out':
                    should_count = True
                
                if should_count:
                    if direction == 'in':
                        self.today_in_count += 1
                    else:
                        self.today_out_count += 1
                    
                    self.line_crossed_tracks[track_id] = direction
                    self._trigger_counting_event(track_id, f'line_cross_{direction}', intersection or current_center)
    
    def _get_crossing_direction(self, prev_point, current_point):
        """判断穿越方向（简化版本，可根据实际需求优化）"""
        # 这里使用简单的Y坐标判断，实际应用中可能需要更复杂的算法
        flowPeriod = self.area_coordinates.get('flowPeriod', 'detect_in')
        if current_point[1] > prev_point[1]:
            if flowPeriod == 'detect_in':
                return 'in'  # 向下为进入
            else:
                return 'out'
        else:
            if flowPeriod == 'detect_in':
                return 'out'  # 向上为离开
            else:
                return 'in'
    
    def _trigger_behavior_event(self, track_id, event_type, position):
        """触发行为事件"""
        event_key = f"{track_id}_{event_type}"
        if event_key not in self.triggered_events:
            self.triggered_events[event_key] = {
                'track_id': track_id,
                'event_type': event_type,
                'position': position,
                'current_count': 1,
                'timestamp': self.frame_count
            }
            # 这里可以添加回调函数来处理事件
            # print(f"行为事件触发: {event_type}, 轨迹ID: {track_id}, 位置: {position}")
    
    def _trigger_counting_event(self, track_id, event_type, position):
        """触发计数事件"""
        event_key = f"{track_id}_{event_type}"
        if event_key not in self.triggered_events:
            self.triggered_events[event_key] = {
                'track_id': track_id,
                'event_type': event_type,
                'position': position,
                'current_count': self.current_count,
                'today_in_count': self.today_in_count,
                'today_out_count': self.today_out_count,
                'timestamp': self.frame_count
            }
            # 这里可以添加回调函数来处理事件
            # print(f"计数事件: {event_type}, 当前人数: {self.current_count}, 今日进入: {self.today_in_count}, 今日离开: {self.today_out_count}")

    def _calculate_iou(self, bbox1, bbox2):
        x1, y1, x2, y2 = bbox1
        x3, y3, x4, y4 = bbox2
        
        xi1, yi1 = max(x1, x3), max(y1, y3)
        xi2, yi2 = min(x2, x4), min(y2, y4)
        
        intersection_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        bbox1_area = (x2 - x1) * (y2 - y1)
        bbox2_area = (x4 - x3) * (y4 - y3)
        
        union_area = bbox1_area + bbox2_area - intersection_area
        
        iou = intersection_area / union_area if union_area > 0 else 0
        return iou

    def _center_distance(self, bbox1, bbox2):
        c1 = self._get_center(bbox1)
        c2 = self._get_center(bbox2)
        return float(np.hypot(c1[0] - c2[0], c1[1] - c2[1]))

    def _bbox_size(self, bbox):
        x1, y1, x2, y2 = bbox
        return max(x2 - x1, y2 - y1, 1.0)

    def _get_reassociate_threshold(self, tracker, detection):
        """跳帧检测时 IoU 容易失效，用中心距离兜底关联"""
        base_size = max(
            self._bbox_size(tracker['box']),
            self._bbox_size(detection['bbox']),
        )
        age_factor = 1 + tracker.get('age', 0) * 0.6
        return max(base_size * 2.0 * age_factor, 100.0)

    def _match_detections_to_tracks(self, detections):
        """两阶段匹配：IoU 优先，中心距离兜底，减少移动时 ID 切换"""
        matched_detections = set()
        matched_trackers = set()
        matches = []

        iou_candidates = []
        for det_idx, det in enumerate(detections):
            for track_id, tracker in self.trackers.items():
                iou = self._calculate_iou(tracker['box'], det['bbox'])
                if iou >= self.iou_threshold:
                    iou_candidates.append((iou, track_id, det_idx))

        for _, track_id, det_idx in sorted(iou_candidates, reverse=True):
            if track_id in matched_trackers or det_idx in matched_detections:
                continue
            matches.append((track_id, det_idx))
            matched_trackers.add(track_id)
            matched_detections.add(det_idx)

        dist_candidates = []
        for det_idx, det in enumerate(detections):
            if det_idx in matched_detections:
                continue
            for track_id, tracker in self.trackers.items():
                if track_id in matched_trackers:
                    continue
                if tracker.get('class') != det.get('class_id'):
                    continue
                dist = self._center_distance(tracker['box'], det['bbox'])
                threshold = self._get_reassociate_threshold(tracker, det)
                if dist <= threshold:
                    dist_candidates.append((dist, track_id, det_idx))

        for _, track_id, det_idx in sorted(dist_candidates):
            if track_id in matched_trackers or det_idx in matched_detections:
                continue
            matches.append((track_id, det_idx))
            matched_trackers.add(track_id)
            matched_detections.add(det_idx)

        return matches, matched_detections, matched_trackers

    def _get_center(self, bbox):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def _get_foot_point(self, bbox):
        """底边中点，适用于监控俯拍/区域人数统计"""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, y2)

    def _get_occupancy_settings(self):
        """读取区域人数统计相关配置"""
        coords = self.area_coordinates or {}
        smooth_window = max(1, int(coords.get('smoothWindow', 3)))
        return {
            'count_min_hits': int(coords.get('countMinHits', self.min_hits)),
            'count_point_mode': coords.get('countPointMode', 'foot'),
            'smooth_window': smooth_window,
            'decrease_hold_frames': max(0, int(coords.get('decreaseHoldFrames', 2))),
            'count_bias': float(coords.get('countBias', 0)),
            'count_scale': float(coords.get('countScale', 1.0)),
        }

    def _track_counts_for_occupancy(self, track):
        """判断轨迹是否应参与区域人数统计（仅本帧有真实检测的目标）"""
        if track.get('age', 0) > 0:
            return False
        settings = self._get_occupancy_settings()
        hits = track.get('hits', 0)
        if hits >= settings['count_min_hits']:
            track['confirmed'] = True
        return track.get('confirmed', False)

    def _track_in_area(self, track, polygon):
        """判断轨迹是否在区域内（默认脚点，可配置）"""
        settings = self._get_occupancy_settings()
        bbox = track['box']
        mode = settings['count_point_mode']

        if mode == 'center':
            return self._point_in_polygon(track['center'], polygon)

        if mode == 'bottom_edge':
            x1, y1, x2, y2 = bbox
            points = [((x1 + x2) / 2, y2), (x1, y2), (x2, y2)]
            return any(self._point_in_polygon(point, polygon) for point in points)

        return self._point_in_polygon(self._get_foot_point(bbox), polygon)

    def _predict_tracker_position(self, track_id, steps=1):
        """漏检帧用最近速度外推位置，延续轨迹"""
        tracker = self.trackers[track_id]
        trajectory = tracker.get('trajectory', [])
        if len(trajectory) < 2:
            return

        vx = trajectory[-1][0] - trajectory[-2][0]
        vy = trajectory[-1][1] - trajectory[-2][1]
        x1, y1, x2, y2 = tracker['box']
        box_w = x2 - x1
        box_h = y2 - y1

        for _ in range(max(1, int(steps))):
            new_center = (tracker['center'][0] + vx, tracker['center'][1] + vy)
            tracker['center'] = new_center
            trajectory.append(new_center)
            tracker['box'] = [
                new_center[0] - box_w / 2,
                new_center[1] - box_h / 2,
                new_center[0] + box_w / 2,
                new_center[1] + box_h / 2,
            ]

    def _smooth_count(self, area_id, raw_count, window_size):
        """滑动窗口中位数平滑"""
        if area_id not in self._occupancy_history:
            self._occupancy_history[area_id] = deque(maxlen=max(window_size, 1))

        history = self._occupancy_history[area_id]
        history.append(raw_count)
        return int(round(float(np.median(history))))

    def _apply_count_calibration(self, count):
        """应用现场校正系数"""
        settings = self._get_occupancy_settings()
        calibrated = round(settings['count_scale'] * count + settings['count_bias'])
        max_capacity = (self.area_coordinates or {}).get('maxCapacity')
        if max_capacity:
            calibrated = min(calibrated, int(max_capacity))
        return max(0, calibrated)

    def _apply_decrease_hysteresis(self, smoothed_total):
        """人数下降时延迟更新，避免单帧漏检导致数字骤降"""
        settings = self._get_occupancy_settings()
        hold_frames = settings['decrease_hold_frames']

        if smoothed_total >= self._display_total:
            self._display_total = smoothed_total
            self._decrease_hold = hold_frames
            return self._display_total

        if hold_frames <= 0:
            self._display_total = smoothed_total
            return self._display_total

        if self._decrease_hold > 0:
            self._decrease_hold -= 1
            return self._display_total

        self._display_total = smoothed_total
        return self._display_total

    def update(self, detections, frame_gap=1):
        self.frame_count += max(1, int(frame_gap))
        detections = detections or []
        frame_gap = max(1, int(frame_gap))
        current_active_tracks = set()
        matched_detections = set()
        matched_trackers = set()

        if not self.trackers:
            for det in detections:
                track_id = self._init_new_tracker(det)
                current_active_tracks.add(track_id)
            self.active_tracks = current_active_tracks
            self._update_area_occupancy_count()
            if self.multi_scenario_mode and self.scenario_processor.is_active:
                scenario_events = self.scenario_processor.process()
                if scenario_events:
                    self.triggered_events.update(scenario_events)
            return

        matches, matched_detections, matched_trackers = self._match_detections_to_tracks(detections)

        for track_id, det_idx in matches:
            self._update_tracker(track_id, detections[det_idx])
            current_active_tracks.add(track_id)

        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                track_id = self._init_new_tracker(det)
                current_active_tracks.add(track_id)

        for track_id, tracker in self.trackers.items():
            if track_id in matched_trackers:
                continue

            tracker['age'] = tracker.get('age', 0) + frame_gap
            if tracker['age'] <= self.max_age:
                self._predict_tracker_position(track_id, steps=frame_gap)
                current_active_tracks.add(track_id)

        self.trackers = {k: v for k, v in self.trackers.items() if k in current_active_tracks}
        self.active_tracks = current_active_tracks
        self._update_area_occupancy_count()

        if self.multi_scenario_mode and self.scenario_processor.is_active:
            scenario_events = self.scenario_processor.process()
            if scenario_events:
                self.triggered_events.update(scenario_events)

    def _init_new_tracker(self, detection):
        """初始化新的跟踪器并返回track_id"""
        track_id = self.next_id
        center = self._get_center(detection['bbox'])
        self.trackers[track_id] = {
            'box': detection['bbox'],
            'center': center,
            'hits': 1,
            'age': 0,
            'class': detection['class_id'],
            'trajectory': [center],
            'confidence': detection.get('confidence', 1.0),
            'confirmed': False,
            'last_update': self.frame_count
        }
        self.next_id += 1
        return track_id

    def _update_tracker(self, track_id, detection):
        """更新现有跟踪器，包含轨迹平滑和插值"""
        current_center = self._get_center(detection['bbox'])
        prev_center = self.trackers[track_id]['center']
        
        # 计算与上一个点的距离
        distance = np.sqrt((current_center[0] - prev_center[0])**2 + 
                         (current_center[1] - prev_center[1])**2)
        
        # 如果距离过大且有足够的历史轨迹点，进行插值
        if distance > self.interpolation_threshold and len(self.trackers[track_id]['trajectory']) > 0:
            interpolated_points = self._interpolate_points(prev_center, current_center)
            self.trackers[track_id]['trajectory'].extend(interpolated_points)

        # 智能分析逻辑（单场景模式）
        if not self.multi_scenario_mode and self.area_coordinates and self.area_points:
            self._analyze_behavior(track_id, current_center, prev_center)

        # 更新轨迹
        self.trackers[track_id]['trajectory'].append(current_center)
        
        # 使用卡尔曼滤波平滑轨迹
        if len(self.trackers[track_id]['trajectory']) >= 3:
            self._smooth_trajectory(track_id)
        
        self.trackers[track_id].update({
            'box': detection['bbox'],
            'center': current_center,
            'hits': self.trackers[track_id]['hits'] + 1,
            'age': 0,
            'class': detection['class_id'],
            'confidence': detection.get('confidence', 1.0),
            'last_update': self.frame_count
        })
        if self.trackers[track_id]['hits'] >= self.min_hits:
            self.trackers[track_id]['confirmed'] = True
        if self.area_coordinates and self.area_coordinates.get('countingType') == 'occupancy':
            if self.trackers[track_id]['hits'] >= self._get_occupancy_settings()['count_min_hits']:
                self.trackers[track_id]['confirmed'] = True

    def _interpolate_points(self, start_point, end_point):
        """在两点之间进行线性插值"""
        num_points = int(np.sqrt(
            (end_point[0] - start_point[0])**2 + 
            (end_point[1] - start_point[1])**2
        ) / 10)  # 每10像素插入一个点
        
        if num_points < 2:
            return []
            
        x = np.linspace(start_point[0], end_point[0], num_points)
        y = np.linspace(start_point[1], end_point[1], num_points)
        
        return list(zip(x, y))[1:-1]  # 不包括起点和终点

    def _smooth_trajectory(self, track_id):
        """使用简单的移动平均平滑轨迹"""
        trajectory = np.array(self.trackers[track_id]['trajectory'])
        window_size = 3
        
        if len(trajectory) >= window_size:
            smoothed = []
            for i in range(len(trajectory)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(trajectory), i + window_size // 2 + 1)
                window = trajectory[start_idx:end_idx]
                smoothed.append(np.mean(window, axis=0))
            
            self.trackers[track_id]['trajectory'] = smoothed

    def draw_tracks(self, frame, max_trajectory_length=30, show_boxes=True):
        """绘制平滑的跟踪轨迹和智能分析信息"""
        # 绘制轨迹
        for track_id, track in self.trackers.items():
            if track_id in self.active_tracks and track['hits'] >= self.min_hits:
                color = self._assign_color(track['class'])
                
                # 只在show_boxes为True时绘制边界框和ID
                if show_boxes:
                    x1, y1, x2, y2 = map(int, track['box'])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    conf_text = f"ID:{track_id} {track['confidence']:.2f}"
                    cv2.putText(frame, conf_text, (x1, y1 - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                # 绘制轨迹（人流统计时显示更明显的轨迹）
                show_trajectory = self._should_draw_trajectory()
                
                if show_trajectory:
                    trajectory = track['trajectory'][-max_trajectory_length:]
                    if len(trajectory) > 1:
                        points = np.array(trajectory, dtype=np.float32)
                        points = np.round(points).astype(np.int32)
                        
                        for i in range(len(points) - 1):
                            pt1 = tuple(points[i])
                            pt2 = tuple(points[i + 1])
                            cv2.line(frame, pt1, pt2, color, 2, cv2.LINE_AA)
                
                # 绘制当前位置点
                cv2.circle(frame, (int(track['center'][0]), int(track['center'][1])), 
                          4, color, -1, cv2.LINE_AA)
        
        # 绘制智能分析信息
        self._draw_analysis_info(frame)
        
        return frame
    
    def _draw_chinese_text(self, frame, text, position, font_size=24, color=(255, 255, 255)):
        """使用PIL绘制中文文字到OpenCV图像上"""
        height, width, _ = frame.shape
    
        # 根据画面高度动态调整字体大小
        font_size = int(height / 25)  # 例如，设置字体大小为画面高度的1/20

        # 将OpenCV图像转换为PIL图像
        frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(frame_pil)
        # 选择字体大小
        if font_size <= 24:
            current_font = self.font_small
        else:
            current_font = self.font
        # 绘制文字（PIL的颜色是RGB格式）
        pil_color = (color[2], color[1], color[0])  # BGR转RGB

        try:
            draw.text(position, text, font=current_font, fill=pil_color)
        except Exception as e:
            print(f"绘制文字失败: {e}")

        # 将PIL图像转换回OpenCV图像
        frame_cv = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
        frame[:] = frame_cv[:]

    def _should_draw_trajectory(self) -> bool:
        if self.multi_scenario_mode and self.scenario_processor.is_active:
            overlays = self.scenario_processor.get_display_overlays()
            has_flow = any(item.get("kind") == "flow" for item in overlays)
            has_occupancy = any(item.get("kind") == "occupancy" for item in overlays)
            if has_flow:
                return True
            if has_occupancy:
                return False
            return True

        if not self.area_coordinates:
            return True
        analysis_type = self.area_coordinates.get('analysisType')
        counting_type = self.area_coordinates.get('countingType')
        if analysis_type == 'counting' and counting_type == 'occupancy':
            return False
        return True

    @staticmethod
    def _polygon_centroid(points) -> Tuple[int, int]:
        if not points:
            return 10, 10
        xs = [int(p[0]) for p in points]
        ys = [int(p[1]) for p in points]
        return int(sum(xs) / len(xs)), int(sum(ys) / len(ys))

    @staticmethod
    def _line_label_position(points) -> Tuple[int, int]:
        if not points:
            return 10, 10
        if len(points) == 1:
            return int(points[0][0]), max(10, int(points[0][1]) - 30)
        mid_index = len(points) // 2
        if mid_index >= len(points):
            mid_index = len(points) - 1
        x, y = points[mid_index]
        return int(x), max(10, int(y) - 36)

    def _draw_analysis_info(self, frame):
        """绘制智能分析信息"""
        if self.multi_scenario_mode and self.scenario_processor.is_active:
            self._draw_multi_scenario_analysis_info(frame)
            return

        if not self.area_coordinates:
            return
        
        analysis_type = self.area_coordinates.get('analysisType')
        
        if analysis_type == 'counting':
            counting_type = self.area_coordinates.get('countingType')
            
            if counting_type == 'occupancy':
                # 区域人数统计 - 显示各区域人数及总人数
                y = 10
                if self.area_counts and len(self.area_counts) > 1:
                    self._draw_chinese_text(frame, f"总人数: {self.current_count}", (10, y), 30, (0, 255, 0))
                    y += int(frame.shape[0] / 22)
                    for info in self.area_counts.values():
                        self._draw_chinese_text(frame, f"{info['name']}: {info['count']}", (10, y), 24, (0, 255, 0))
                        y += int(frame.shape[0] / 28)
                else:
                    area_name = next(iter(self.area_counts.values()), {}).get('name', '当前人数')
                    label = area_name if self.area_counts else '当前人数'
                    info_text = f"{label}: {self.current_count}"
                    self._draw_chinese_text(frame, info_text, (10, y), 30, (0, 255, 0))
                
                # 显示今日统计
                # today_text = f"今日进入: {self.today_in_count} | 今日离开: {self.today_out_count}"
                # self._draw_chinese_text(frame, today_text, (10, 40), 18, (255, 255, 255))
                
            elif counting_type == 'flow':
                # 人流统计 - 显示进出统计
                flow_direction = self.area_coordinates.get('flowDirection', 'bidirectional')
                
                if flow_direction == 'bidirectional':
                    info_text = f"今日进入: {self.today_in_count} | 今日离开: {self.today_out_count}"
                elif flow_direction == 'in':
                    info_text = f"今日进入: {self.today_in_count}"
                elif flow_direction == 'out':
                    info_text = f"今日离开: {self.today_out_count}"
                else:
                    info_text = f"总通过: {self.today_in_count + self.today_out_count}"
                
                self._draw_chinese_text(frame, info_text, (10, 10), 30, (0, 255, 255))
                
        elif analysis_type == 'behavior':
            # 行为分析 - 显示检测模式
            behavior_type = self.area_coordinates.get('behaviorType')
            behavior_subtype = self.area_coordinates.get('behaviorSubtype', 'simple')
            behavior_direction = self.area_coordinates.get('behaviorDirection', '')
            
            type_text = '区域检测' if behavior_type == 'area' else '拌线检测'
            mode_text = '方向检测' if behavior_subtype == 'directional' else '普通检测'
            
            info_text = f"{type_text} - {mode_text}"
            if behavior_subtype == 'directional':
                direction_text = '进入' if behavior_direction == 'in' else '离开'
                info_text += f" ({direction_text})"
            
            self._draw_chinese_text(frame, info_text, (10, 10), 30, (255, 165, 0))

    def _draw_multi_scenario_analysis_info(self, frame):
        overlays = self.scenario_processor.get_display_overlays()
        if not overlays:
            return

        line_height = max(24, int(frame.shape[0] / 28))
        corner_y = 10

        for item in overlays:
            if item.get("kind") == "occupancy":
                points = item.get("points") or []
                if len(points) < 3:
                    continue
                cx, cy = self._polygon_centroid(points)
                label = f"{item.get('area_name', '区域')}: {item.get('count', 0)}人"
                text_x = max(8, cx - min(80, cx // 3))
                text_y = max(24, cy - 8)
                self._draw_chinese_text(frame, label, (text_x, text_y), 26, (0, 255, 0))
            elif item.get("kind") == "flow":
                flow_direction = item.get("flow_direction", "bidirectional")
                today_in = item.get("today_in_count", 0)
                today_out = item.get("today_out_count", 0)
                scenario_name = item.get("scenario_name") or "人流"
                if flow_direction == "in":
                    info_text = f"{scenario_name} 进入:{today_in}"
                elif flow_direction == "out":
                    info_text = f"{scenario_name} 离开:{today_out}"
                else:
                    info_text = f"{scenario_name} 进入:{today_in} 离开:{today_out}"

                points = item.get("points") or []
                if len(points) >= 2:
                    pos = self._line_label_position(points)
                else:
                    pos = (10, corner_y)
                    corner_y += line_height
                self._draw_chinese_text(frame, info_text, pos, 26, (0, 255, 255))
    
    def get_counting_stats(self):
        """获取计数统计信息"""
        return {
            'current_count': self.current_count,
            'area_counts': self.area_counts,
            'today_in_count': self.today_in_count,
            'today_out_count': self.today_out_count,
            'total_today': self.today_in_count + self.today_out_count
        }

    def _count_unique_tracks_in_area(self, area_polygon):
        """区域内人数：去重高度重叠的轨迹，避免同一人被重复计数"""
        candidates = []
        for track_id in self.active_tracks:
            track = self.trackers.get(track_id)
            if not track or not self._track_counts_for_occupancy(track):
                continue
            if self._track_in_area(track, area_polygon):
                candidates.append(track)

        unique_tracks = []
        for track in candidates:
            if any(self._calculate_iou(track['box'], kept['box']) > 0.45 for kept in unique_tracks):
                continue
            unique_tracks.append(track)
        return len(unique_tracks)

    def _update_area_occupancy_count(self):
        """更新区域内人数统计（各区域独立计数，总人数为各区域之和）"""
        if self.multi_scenario_mode:
            return
        if not self.area_coordinates or self.area_coordinates.get('countingType') != 'occupancy':
            return

        polygons = self.area_polygons or []
        if not polygons and self.area_points and len(self.area_points) >= 3:
            polygons = [{'id': 'area-0', 'name': '区域1', 'points': self.area_points}]

        settings = self._get_occupancy_settings()
        smoothed_area_counts = {}

        for area in polygons:
            raw_count = self._count_unique_tracks_in_area(area['points'])
            smoothed_count = self._smooth_count(area['id'], raw_count, settings['smooth_window'])
            smoothed_area_counts[area['id']] = {
                'name': area['name'],
                'smoothed_count': smoothed_count,
                'raw_count': raw_count,
            }

        smoothed_total = sum(item['smoothed_count'] for item in smoothed_area_counts.values())
        hysteresis_total = self._apply_decrease_hysteresis(smoothed_total)
        current_total_count = self._apply_count_calibration(hysteresis_total)

        new_area_counts = {}
        area_items = list(smoothed_area_counts.items())
        if not area_items:
            return

        if len(area_items) == 1:
            area_id, info = area_items[0]
            new_area_counts[area_id] = {
                'name': info['name'],
                'count': current_total_count,
                'raw_count': info['raw_count'],
            }
        elif smoothed_total > 0:
            allocated = 0
            for index, (area_id, info) in enumerate(area_items):
                if index == len(area_items) - 1:
                    area_display = max(0, current_total_count - allocated)
                else:
                    area_display = max(0, round(current_total_count * info['smoothed_count'] / smoothed_total))
                    allocated += area_display
                new_area_counts[area_id] = {
                    'name': info['name'],
                    'count': area_display,
                    'raw_count': info['raw_count'],
                }
        else:
            for area_id, info in area_items:
                new_area_counts[area_id] = {
                    'name': info['name'],
                    'count': 0,
                    'raw_count': info['raw_count'],
                }

        counts_changed = current_total_count != self.current_count
        if not counts_changed:
            for area_id, info in new_area_counts.items():
                old_count = (self.area_counts or {}).get(area_id, {}).get('count')
                if old_count != info['count']:
                    counts_changed = True
                    break

        if counts_changed:
            old_count = self.current_count
            self.current_count = current_total_count
            self.area_counts = new_area_counts

            change_type = 'increase' if current_total_count > old_count else 'decrease'
            change_amount = abs(current_total_count - old_count)

            event_key = f"occupancy_{self.frame_count}_{change_type}_{change_amount}"
            if event_key not in self.triggered_events:
                self.triggered_events[event_key] = {
                    'track_id': 0,
                    'event_type': f'occupancy_change_{change_type}',
                    'position': None,
                    'current_count': self.current_count,
                    'area_counts': self.area_counts,
                    'today_in_count': 0,
                    'today_out_count': 0,
                    'timestamp': self.frame_count
                }

            change_amount = current_total_count - old_count
            if change_amount > 0:
                self.today_in_count += change_amount
            else:
                self.today_out_count += abs(change_amount)

