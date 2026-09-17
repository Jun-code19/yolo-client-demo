from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import asyncio
import logging
import psutil  # 导入psutil库

from src.database import (
    get_db, Device, DetectionEvent, DetectionConfig, EdgeServer, ExternalEvent,
    CrowdAnalysisJob, CrowdAnalysisResult, SmartScheme, SmartEvent,
    DetectionPerformance, CompositeAlert,
    AlertRule, EventStatus, DetectionModel, DataPushConfig, DataPushLog,
    ListenerConfig, ListenerStatus, HeatmapArea, HeatmapBinding,
)
from api.edge_dashboard_utils import resolve_dashboard_screen_name
from api.logger import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["数据大屏"])

# 定义事件类型映射
event_type_map = {
    "object_detection": "目标检测",
    "smart_behavior": "智能行为",
    "smart_person": "人员场景",
    "smart_counting": "智能人数统计",
    "segmentation": "图像分割",
    "keypoint": "关键点检测",
    "pose": "姿态估计",
    "face": "人脸识别",
    "other": "其他类型",
    "alarm": "订阅报警",
    "smart": "订阅智能",
    "number_stat": "订阅人数统计",
    "system_log": "设备日志",
    "yolo_analyze": "YOLO 分析",
    "yolo_then_verify": "YOLO 复核",
    "yolo_then_analyze": "YOLO 分析链",
}

#数据大屏API-旧
@router.get("/overview-data")
def get_dashboard_data(db: Session = Depends(get_db)):
    """获取数据大屏数据"""
    try:
        device_count = db.query(Device).count()
        detection_event_count = db.query(DetectionEvent).count()
        detection_config_count = db.query(DetectionConfig).count()
        crowd_analysis_job_count = db.query(CrowdAnalysisJob).count()
        edge_server_count = db.query(EdgeServer).count()
        external_event_count = db.query(ExternalEvent).count()
        return {
            "data": {
                "device_count": device_count,
                "detection_event_count": detection_event_count,
                "detection_config_count": detection_config_count,
                "crowd_analysis_job_count": crowd_analysis_job_count, 
                "edge_server_count": edge_server_count,
                "external_event_count": external_event_count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏数据失败")
    
@router.get("/crowd-analysis-data")
def get_dashboard_crowd_analysis_data(db: Session = Depends(get_db)):
    """获取数据大屏人群分析数据"""
    try:
        # 方法1：获取每个任务的最新分析结果
        # 使用子查询获取每个job_id的最新timestamp
        from sqlalchemy import func
        
        subquery = db.query(
            CrowdAnalysisResult.job_id,
            func.max(CrowdAnalysisResult.timestamp).label('latest_timestamp')
        ).group_by(CrowdAnalysisResult.job_id).subquery()
        
        # 主查询：关联获取最新结果
        latest_results = db.query(
            CrowdAnalysisJob.job_name,
            CrowdAnalysisResult.total_person_count,
            CrowdAnalysisResult.timestamp
        ).join(
            CrowdAnalysisResult, 
            CrowdAnalysisJob.job_id == CrowdAnalysisResult.job_id
        ).join(
            subquery,
            (CrowdAnalysisResult.job_id == subquery.c.job_id) & 
            (CrowdAnalysisResult.timestamp == subquery.c.latest_timestamp)
        ).all()
        
        result = []
        for job_name, people_count, timestamp in latest_results:
            result.append({
                "job_name": job_name,
                "people_count": people_count or 0,
                "last_update": timestamp.isoformat() if timestamp else None
            })
        return {
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏人群分析数据失败")
    
@router.get("/alert-history-data")
def get_dashboard_alert_history_data(db: Session = Depends(get_db)):
    """获取数据大屏告警历史数据"""
    try:
        events = db.query(ExternalEvent).order_by(ExternalEvent.timestamp.desc()).limit(10).all()
        return {
            "data": events
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏告警历史数据失败")
    
@router.get("/historical-stats-data")
def get_dashboard_historical_stats_data(db: Session = Depends(get_db)):
    """获取数据大屏历史数据事件数据"""
    try:
        from sqlalchemy import func
        
        # 获取最近5天的每天的数据条数
        events = db.query(
            func.date(ExternalEvent.timestamp).label('date'), 
            func.count(ExternalEvent.event_id).label('count')
        ).filter(
            ExternalEvent.timestamp >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(ExternalEvent.timestamp)
        ).all()
        # 升序
        events = sorted(events, key=lambda x: x.date)
        # 转换为字典格式
        result = []
        for date, count in events:
            result.append({
                "date": date.isoformat() if date else None,
                "count": count
            })
        
        return {
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏历史数据事件数据失败")
    
@router.get("/detection-event-data")
def get_dashboard_detection_event_data(db: Session = Depends(get_db)):
    """获取数据大屏检测事件数据"""
    try:
        from sqlalchemy import func
        
        # 获取检测总数
        detection_count = db.query(ExternalEvent).count()
        
        # 根据引擎名称统计检测数量
        engine_count_query = db.query(
            ExternalEvent.engine_name,
            func.count(ExternalEvent.event_id).label('count')
        ).filter(
            ExternalEvent.engine_name.isnot(None)
        ).group_by(
            ExternalEvent.engine_name
        ).all()
        
        # 转换为列表格式
        engine_count = []
        for engine_name, count in engine_count_query:
            engine_count.append({
                "engine_name": engine_name or "未知引擎",
                "detection_count": count
            })
        
        # engine_count只保留前5个
        engine_count = engine_count[:5]
        
        engine_count.append({
            "engine_name": "异常事件",
            "detection_count": detection_count
        })

        return {
            "data": engine_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏检测事件数据失败")
    
@router.get("/detection-type-data")
def get_dashboard_detection_type_data(db: Session = Depends(get_db)):
    """获取数据大屏检测类型数据"""
    try:
        from sqlalchemy import func, and_
        
        # 计算时间范围
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        day_before_yesterday_start = today_start - timedelta(days=2)
        
        # 优化的查询：分别统计总数、昨天、前天的数据
        # 总数统计
        total_count_query = db.query(
            ExternalEvent.engine_name,
            func.count(ExternalEvent.event_id).label('total_count')
        ).filter(
            ExternalEvent.engine_name.isnot(None)
        ).group_by(ExternalEvent.engine_name)
        
        # 昨天数据统计
        yesterday_count_query = db.query(
            ExternalEvent.engine_name,
            func.count(ExternalEvent.event_id).label('yesterday_count')
        ).filter(
            and_(
                ExternalEvent.engine_name.isnot(None),
                ExternalEvent.timestamp >= yesterday_start,
                ExternalEvent.timestamp < today_start
            )
        ).group_by(ExternalEvent.engine_name)
        
        # 前天数据统计
        day_before_yesterday_count_query = db.query(
            ExternalEvent.engine_name,
            func.count(ExternalEvent.event_id).label('day_before_yesterday_count')
        ).filter(
            and_(
                ExternalEvent.engine_name.isnot(None),
                ExternalEvent.timestamp >= day_before_yesterday_start,
                ExternalEvent.timestamp < yesterday_start
            )
        ).group_by(ExternalEvent.engine_name)
        
        # 执行查询
        total_counts = {row.engine_name: row.total_count for row in total_count_query.all()}
        yesterday_counts = {row.engine_name: row.yesterday_count for row in yesterday_count_query.all()}
        day_before_yesterday_counts = {row.engine_name: row.day_before_yesterday_count for row in day_before_yesterday_count_query.all()}
        
        # 合并数据并计算同比率
        detection_type_count = []
        for engine_name in total_counts.keys():
            total = total_counts.get(engine_name, 0)
            yesterday = yesterday_counts.get(engine_name, 0)
            day_before_yesterday = day_before_yesterday_counts.get(engine_name, 0)
            
            # 计算同比率（昨天相比前天的变化率）
            if day_before_yesterday > 0:
                rate = round((yesterday - day_before_yesterday) / day_before_yesterday * 100, 2)
            else:
                rate = 0 if yesterday == 0 else 100  # 如果前天没有数据，昨天有数据则为100%增长
            
            detection_type_count.append({
                "engine_name": engine_name,
                "count": total,
                "count_yesterday": yesterday,
                "count_day_before_yesterday": day_before_yesterday,
                "count_yesterday_rate": rate
            })
        
        # 按总数排序，取前6个（为本地引擎留一个位置）
        detection_type_count.sort(key=lambda x: x["count"], reverse=True)
        detection_type_count = detection_type_count[:6]
        
        # 添加本地检测引擎数据（从DetectionEvent表查询）
        try:
            local_total = db.query(DetectionEvent).count()
            local_yesterday = db.query(DetectionEvent).filter(
                and_(
                    DetectionEvent.timestamp >= yesterday_start,
                    DetectionEvent.timestamp < today_start
                )
            ).count()
            local_day_before_yesterday = db.query(DetectionEvent).filter(
                and_(
                    DetectionEvent.timestamp >= day_before_yesterday_start,
                    DetectionEvent.timestamp < yesterday_start
                )
            ).count()
            
            # 计算本地引擎同比率
            if local_day_before_yesterday > 0:
                local_rate = round((local_yesterday - local_day_before_yesterday) / local_day_before_yesterday * 100, 2)
            else:
                local_rate = 0 if local_yesterday == 0 else 100
            
            detection_type_count.append({
                "engine_name": "本地引擎",
                "count": local_total,
                "count_yesterday": local_yesterday,
                "count_day_before_yesterday": local_day_before_yesterday,
                "count_yesterday_rate": local_rate
            })
        except Exception as local_error:
            # 如果本地引擎数据查询失败，添加默认数据
            detection_type_count.append({
                "engine_name": "本地引擎",
                "count": 0,
                "count_yesterday": 0,
                "count_day_before_yesterday": 0,
                "count_yesterday_rate": 0
            })
        
        return {
            "data": detection_type_count,
            "meta": {
                "query_time": now.isoformat(),
                "time_ranges": {
                    "today_start": today_start.isoformat(),
                    "yesterday_start": yesterday_start.isoformat(),
                    "day_before_yesterday_start": day_before_yesterday_start.isoformat()
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏检测类型数据失败")

#数据大屏API-新
@router.get("/overview-smart-data")
def get_dashboard_overview_data(db: Session = Depends(get_db)):
    """获取数据大屏数据"""
    try:
        device_count = db.query(Device).count()
        detection_config_count = db.query(DetectionConfig).count()
        crowd_analysis_job_count = db.query(CrowdAnalysisJob).count()

        smart_scheme_count = db.query(SmartScheme).count()
        smart_event_count = db.query(SmartEvent).count()
        # smart_type_count = db.query(SmartEvent.event_type, func.count(SmartEvent.id)).group_by(SmartEvent.event_type).all()

        detection_event_count = db.query(DetectionEvent).count()
        # detection_type_count = db.query(DetectionEvent.event_type, func.count(DetectionEvent.event_id)).group_by(DetectionEvent.event_type).all()
        detection_events = db.query(DetectionEvent, Device.device_name).join(Device, DetectionEvent.device_id == Device.device_id).order_by(DetectionEvent.created_at.desc()).limit(25).all()
        detection_lasted_events = db.query(DetectionEvent, Device.device_name).join(Device, DetectionEvent.device_id == Device.device_id
            ).filter(and_(DetectionEvent.thumbnail_path.isnot(None), DetectionEvent.thumbnail_path != "")
            ).order_by(DetectionEvent.created_at.desc()
            ).limit(12).all()

        external_event_count = db.query(ExternalEvent).count()
        # 根据引擎名称统计检测数量
        # external_type_count = db.query(
        #     ExternalEvent.engine_name,
        #     func.count(ExternalEvent.event_id).label('count')
        # ).filter(
        #     ExternalEvent.engine_name.isnot(None)
        # ).group_by(
        #     ExternalEvent.engine_name
        # ).all()
       
        # 转换为列表格式
        # event_count = []
        # for engine_name, count in external_type_count:
        #     event_count.append({
        #         "event_type": engine_name or "未知引擎",
        #         "event_count": count
        #     })
        # for event_type, count in smart_type_count:
        #     event_count.append({
        #         "event_type": event_type_map.get(event_type, "未知类型"),
        #         "event_count": count
        #     })
        # for event_type, count in detection_type_count:
        #     event_count.append({
        #         "event_type": event_type_map.get(event_type, "未知类型"),
        #         "event_count": count
        #     })

        detection_events_data = []
        for event, device_name in detection_events:
            event_dict = event.__dict__
            event_dict.pop('_s-instance_state', None) # 移除SQLAlchemy内部状态
            event_dict['device_name'] = device_name
             # 如果 event_type 已经是中文，则不再转换；否则，进行转换
            if event_dict['event_type'] not in event_type_map:
                # 假设已经是中文，直接使用
                pass  
            else:
                event_dict['event_type'] = event_type_map.get(event_dict['event_type'], "未知类型")
            detection_events_data.append(event_dict)

        detection_lasted_events_data = []
        for event, device_name in detection_lasted_events:
            event_dict = event.__dict__
            event_dict.pop('_s-instance_state', None)
            event_dict['device_name'] = device_name
            # 如果 event_type 已经是中文，则不再转换；否则，进行转换
            if event_dict['event_type'] not in event_type_map:
                # 假设已经是中文，直接使用
                pass  
            else:
                event_dict['event_type'] = event_type_map.get(event_dict['event_type'], "未知类型")
            detection_lasted_events_data.append(event_dict)

        return {
            "data": {
                "device_count": device_count,                
                "detection_config_count": detection_config_count,
                "crowd_analysis_job_count": crowd_analysis_job_count, 
                "smart_scheme_count": smart_scheme_count,
                "smart_event_count": smart_event_count,
                "detection_event_count": detection_event_count,
                "external_event_count":external_event_count,
                # "event_type_count":event_count,              
                "detection_events": detection_events_data,
                "detection_lasted_events": detection_lasted_events_data     
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏数据失败")
    
@router.get("/historical-smart-data")
def get_dashboard_historical_data(db: Session = Depends(get_db)):
    """获取数据大屏历史数据事件数据"""
    try:       
        # 获取最近5天的每天的数据条数
        external_event_history = db.query(
            func.date(ExternalEvent.timestamp).label('date'), 
            func.count(ExternalEvent.event_id).label('count')
        ).filter(
            ExternalEvent.timestamp >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(ExternalEvent.timestamp)
        ).all()

        detection_event_history = db.query(
            func.date(DetectionEvent.created_at).label('date'), 
            func.count(DetectionEvent.event_id).label('count')
        ).filter(
            DetectionEvent.created_at >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(DetectionEvent.created_at)
        ).all()

        smart_event_history = db.query(
            func.date(SmartEvent.timestamp).label('date'), 
            func.count(SmartEvent.id).label('count')
        ).filter(
            SmartEvent.timestamp >= datetime.now() - timedelta(days=5)
        ).group_by(
            func.date(SmartEvent.timestamp)
        ).all()

        # 创建一个字典来存储所有数据，以日期为键
        result_dict = {}
        # 生成过去5天的所有日期，并初始化为0
        today = datetime.now().date()
        for i in range(5, -1, -1): # 包括今天和过去5天，共6天
            date = today - timedelta(days=i)
            result_dict[date] = {
                "date": date.isoformat(),
                "external_event_count": 0,
                "detection_event_count": 0,
                "smart_event_count": 0
            }

        # 处理外部事件数据
        for date, count in external_event_history:
            if date in result_dict: # 确保日期存在于初始化后的字典中
                result_dict[date]["external_event_count"] = count

        # 处理检测事件数据
        for date, count in detection_event_history:
            if date in result_dict:
                result_dict[date]["detection_event_count"] = count

        # 处理智能事件数据
        for date, count in smart_event_history:
            if date in result_dict:
                result_dict[date]["smart_event_count"] = count

        # 转换为列表并按日期排序
        result = sorted(result_dict.values(), key=lambda x: x["date"])
        
        return {
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏历史数据事件数据失败")

@router.get("/type-smart-data")
def get_dashboard_type_data(db: Session = Depends(get_db)):
    """获取数据大屏检测类型数据"""
    try:       
        # 计算时间范围（确保时区一致性，这里使用服务器本地时间）
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)  # 昨天结束时刻是今天开始前一微秒
        day_before_yesterday_start = today_start - timedelta(days=2)
        day_before_yesterday_end = yesterday_start - timedelta(microseconds=1)  # 前天结束时刻是昨天开始前一微秒

        # 定义一个函数来执行针对特定事件模型和分类字段的统计查询
        def get_event_stats(event_model, category_field, timestamp_field,id_field):
            """获取指定事件模型在三个时间段的统计信息（今天、昨天、前天）"""
            
            total_stats = db.query(
                category_field.label('category'),
                func.count(id_field).label('total_count')
            ).filter(
                category_field.isnot(None),
            ).group_by(category_field).all()

            # 今天数据统计
            today_stats = db.query(
                category_field.label('category'),
                func.count(id_field).label('today_count')
            ).filter(
                and_(
                    category_field.isnot(None),
                    timestamp_field >= today_start,
                    timestamp_field <= now  # 到今天当前时刻为止
                )
            ).group_by(category_field).all()
            
            # 昨天数据统计
            yesterday_stats = db.query(
                category_field.label('category'),
                func.count(id_field).label('yesterday_count')
            ).filter(
                and_(
                    category_field.isnot(None),
                    timestamp_field >= yesterday_start,
                    timestamp_field <= yesterday_end
                )
            ).group_by(category_field).all()
            
            # 前天数据统计
            day_before_yesterday_stats = db.query(
                category_field.label('category'),
                func.count(id_field).label('day_before_yesterday_count')
            ).filter(
                and_(
                    category_field.isnot(None),
                    timestamp_field >= day_before_yesterday_start,
                    timestamp_field <= day_before_yesterday_end
                )
            ).group_by(category_field).all()
            
            # 将查询结果转换为字典以便后续合并，键为 category
            total_dict = {category: count for category, count in total_stats}
            today_dict = {category: count for category, count in today_stats}
            yesterday_dict = {category: count for category, count in yesterday_stats}
            day_before_yesterday_dict = {category: count for category, count in day_before_yesterday_stats}
            
            return {
                'total_dict': total_dict,
                'today_dict': today_dict,
                'yesterday_dict': yesterday_dict,
                'day_before_yesterday_dict': day_before_yesterday_dict
            }

        # 获取三种事件类型的统计信息
        # ExternalEvent 按 engine_name 分类
        external_stats = get_event_stats(ExternalEvent, ExternalEvent.engine_name, ExternalEvent.timestamp,ExternalEvent.event_id)
        # DetectionEvent 按 event_type 分类
        detection_stats = get_event_stats(DetectionEvent, DetectionEvent.event_type, DetectionEvent.created_at,DetectionEvent.event_id)
        # SmartEvent 按 event_type 分类
        smart_stats = get_event_stats(SmartEvent, SmartEvent.event_type, SmartEvent.timestamp,SmartEvent.id)

        # 获取所有可能的分类名（合并三种事件类型中的分类名）
        all_categories = set()
        all_categories.update(external_stats['total_dict'].keys())
        all_categories.update(external_stats['today_dict'].keys())
        all_categories.update(external_stats['yesterday_dict'].keys())
        all_categories.update(external_stats['day_before_yesterday_dict'].keys())
        all_categories.update(detection_stats['total_dict'].keys())
        all_categories.update(detection_stats['today_dict'].keys())
        all_categories.update(detection_stats['yesterday_dict'].keys())
        all_categories.update(detection_stats['day_before_yesterday_dict'].keys())
        all_categories.update(smart_stats['total_dict'].keys())
        all_categories.update(smart_stats['today_dict'].keys())
        all_categories.update(smart_stats['yesterday_dict'].keys())
        all_categories.update(smart_stats['day_before_yesterday_dict'].keys())

        # 合并数据并计算增长率（昨天相比前天的变化率）
        final_result = []
        for category in all_categories:
            # 初始化各事件类型在三个时间段的计数
            external_total = external_stats['total_dict'].get(category, 0)
            external_today = external_stats['today_dict'].get(category, 0)
            external_yesterday = external_stats['yesterday_dict'].get(category, 0)
            external_day_before = external_stats['day_before_yesterday_dict'].get(category, 0)
            
            detection_total = detection_stats['total_dict'].get(category, 0)
            detection_today = detection_stats['today_dict'].get(category, 0)
            detection_yesterday = detection_stats['yesterday_dict'].get(category, 0)
            detection_day_before = detection_stats['day_before_yesterday_dict'].get(category, 0)
            
            smart_total = smart_stats['total_dict'].get(category, 0)
            smart_today = smart_stats['today_dict'].get(category, 0)
            smart_yesterday = smart_stats['yesterday_dict'].get(category, 0)
            smart_day_before = smart_stats['day_before_yesterday_dict'].get(category, 0)
            
            # 计算总计数
            event_total = external_total + detection_total + smart_total
            today_total = external_today + detection_today + smart_today
            yesterday_total = external_yesterday + detection_yesterday + smart_yesterday
            day_before_yesterday_total = external_day_before + detection_day_before + smart_day_before
            
            # 计算同比增长率（昨天相比前天的变化率）
            growth_rate = 0.0
            if day_before_yesterday_total > 0:
                growth_rate = round(((yesterday_total - day_before_yesterday_total) / day_before_yesterday_total) * 100, 2)
            elif yesterday_total > 0:
                # 如果前天为0而昨天有数据，则增长率为100%
                growth_rate = 100.0
            # 如果前天和昨天都为0，则增长率为0%（保持不变）
            
            final_result.append({
                "category": event_type_map.get(category, category),
                "event_total":event_total,
                "today_total": today_total,
                "yesterday_total": yesterday_total,
                "day_before_yesterday_total": day_before_yesterday_total,
                "growth_rate": growth_rate,  # 昨天相对于前天的增长率
            })

        # 可以根据需要按 event_total 或其他字段排序
        final_result.sort(key=lambda x: x['event_total'], reverse=True)

        return {
            "data": final_result,
            "meta": {
                "query_time": now.isoformat(),
                "time_ranges": {
                    "today_start": today_start.isoformat(),
                    "today_end": now.isoformat(),
                    "yesterday_start": yesterday_start.isoformat(),
                    "yesterday_end": yesterday_end.isoformat(),
                    "day_before_yesterday_start": day_before_yesterday_start.isoformat(),
                    "day_before_yesterday_end": day_before_yesterday_end.isoformat()
                },
                "growth_rate_note": "growth_rate is calculated as ((yesterday - day_before_yesterday) / day_before_yesterday) * 100%"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="获取数据大屏检测类型数据失败")

@router.get("/system-status")
def get_system_status():
    """获取系统资源状态"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=False)  # 物理核心数
        cpu_logical_count = psutil.cpu_count(logical=True) # 逻辑核心数

        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024 ** 3), 2)
        memory_used_gb = round(memory.used / (1024 ** 3), 2)
        memory_percent = memory.percent

        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024 ** 3), 2)
        disk_used_gb = round(disk.used / (1024 ** 3), 2)
        disk_percent = disk.percent

        # 尝试获取GPU信息，如果psutil或相关库不支持，则返回默认值
        gpu_percent = 0
        gpu_total_gb = 0
        gpu_used_gb = 0
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # 假设只有一块GPU或者只取第一块
                gpu_percent = round(gpu.load * 100, 2)
                gpu_total_gb = round(gpu.memoryTotal / 1024, 2)
                gpu_used_gb = round(gpu.memoryUsed / 1024, 2)
        except Exception:
            pass # 忽略GPU获取失败的情况

        status = "normal"
        if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90 or gpu_percent > 90:
            status = "danger"
        elif cpu_percent > 70 or memory_percent > 80 or disk_percent > 80 or gpu_percent > 70:
            status = "warning"

        return {
            "data": {
                "status": status, # 默认正常，可根据阈值判断
                "cpu": {
                    "percent": cpu_percent,
                    "total": cpu_count,
                    "used": round(cpu_percent / 100 * cpu_count, 2)  # 根据百分比估算已用核数
                },
                "memory": {
                    "percent": memory_percent,
                    "total": memory_total_gb,
                    "used": memory_used_gb
                },
                "disk": {
                    "percent": disk_percent,
                    "total": disk_total_gb,
                    "used": disk_used_gb
                },
                "gpu": {
                    "percent": gpu_percent,
                    "total": gpu_total_gb,
                    "used": gpu_used_gb
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统资源数据失败: {str(e)}")


def _map_event_type(event_type: Optional[str]) -> str:
    if not event_type:
        return "未知类型"
    return event_type_map.get(event_type, event_type)


def _event_status_value(status) -> str:
    if status is None:
        return "new"
    return status.value if hasattr(status, "value") else str(status)


def _count_detections(bbox) -> int:
    if isinstance(bbox, list):
        return len(bbox)
    if isinstance(bbox, dict):
        if isinstance(bbox.get("detections"), list):
            return len(bbox["detections"])
        return len(bbox)
    return 0


def _serialize_detection_event(event: DetectionEvent, device_name: str) -> Dict[str, Any]:
    meta = event.meta_data if isinstance(event.meta_data, dict) else {}
    return {
        "event_id": event.event_id,
        "device_name": device_name or "未知设备",
        "event_type": _map_event_type(event.event_type),
        "description": meta.get("event_description") or meta.get("pushLabel") or "",
        "detection_count": _count_detections(event.bounding_box),
        "confidence": round(float(event.confidence or 0) * 100, 1),
        "timestamp": (event.created_at or event.timestamp).isoformat() if (event.created_at or event.timestamp) else None,
        "status": _event_status_value(event.status),
        "thumbnail_path": event.thumbnail_path,
    }


@router.get("/board-data")
def get_dashboard_board_data(db: Session = Depends(get_db)):
    """展板统一数据：聚合多表有效指标供大屏展示"""
    try:
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        trend_since = now - timedelta(days=6)

        device_total = db.query(Device).count()
        device_online = db.query(Device).filter(Device.status.is_(True)).count()
        detection_config_total = db.query(DetectionConfig).count()
        detection_config_enabled = db.query(DetectionConfig).filter(DetectionConfig.enabled.is_(True)).count()
        detection_event_total = db.query(DetectionEvent).count()
        detection_event_today = db.query(DetectionEvent).filter(DetectionEvent.created_at >= today_start).count()
        detection_event_new = db.query(DetectionEvent).filter(DetectionEvent.status == EventStatus.new).count()
        smart_scheme_total = db.query(SmartScheme).count()
        smart_event_total = db.query(SmartEvent).count()
        smart_event_today = db.query(SmartEvent).filter(SmartEvent.timestamp >= today_start).count()
        crowd_job_total = db.query(CrowdAnalysisJob).count()
        crowd_job_active = db.query(CrowdAnalysisJob).filter(CrowdAnalysisJob.is_active.is_(True)).count()
        external_event_total = db.query(ExternalEvent).count()
        external_event_today = db.query(ExternalEvent).filter(ExternalEvent.timestamp >= today_start).count()
        vlm_job_total = 0
        vlm_job_active = 0
        vlm_alert_today = 0
        composite_alert_total = db.query(CompositeAlert).count()
        composite_alert_today = db.query(CompositeAlert).filter(CompositeAlert.fired_at >= today_start).count()
        alert_rule_enabled = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).count()
        edge_server_total = db.query(EdgeServer).count()
        edge_server_online = db.query(EdgeServer).filter(EdgeServer.status == "online").count()

        perf_since = now - timedelta(days=7)
        avg_detection_time_ms = db.query(
            func.avg(
                DetectionPerformance.detection_time
                + DetectionPerformance.preprocessing_time
                + DetectionPerformance.postprocessing_time
            )
        ).filter(
            DetectionPerformance.timestamp >= perf_since,
            DetectionPerformance.detection_time.isnot(None),
        ).scalar()
        avg_confidence_raw = db.query(func.avg(DetectionEvent.confidence)).filter(
            DetectionEvent.created_at >= perf_since,
            DetectionEvent.confidence.isnot(None),
        ).scalar()

        # 近 7 天检测性能趋势（按日平均 ms）
        perf_rows = db.query(
            func.date(DetectionPerformance.timestamp).label("day"),
            func.avg(
                DetectionPerformance.detection_time
                + DetectionPerformance.preprocessing_time
                + DetectionPerformance.postprocessing_time
            ).label("avg_ms"),
            func.count(DetectionPerformance.performance_id).label("sample_count"),
        ).filter(
            DetectionPerformance.timestamp >= trend_since,
        ).group_by(func.date(DetectionPerformance.timestamp)).all()
        perf_by_day = {row.day: row for row in perf_rows}
        performance_trend = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            row = perf_by_day.get(day)
            performance_trend.append({
                "date": day.isoformat(),
                "avg_ms": round(float(row.avg_ms or 0), 1) if row else 0,
                "sample_count": int(row.sample_count or 0) if row else 0,
            })

        # 近 7 天三类事件趋势（检测 / 规则告警 / 订阅）
        alert_rule_rows = db.query(
            func.date(CompositeAlert.fired_at).label("day"),
            func.count(CompositeAlert.alert_id).label("cnt"),
        ).filter(CompositeAlert.fired_at >= trend_since).group_by(func.date(CompositeAlert.fired_at)).all()
        detection_rows = db.query(
            func.date(DetectionEvent.created_at).label("day"),
            func.count(DetectionEvent.event_id).label("cnt"),
        ).filter(DetectionEvent.created_at >= trend_since).group_by(func.date(DetectionEvent.created_at)).all()
        smart_rows = db.query(
            func.date(SmartEvent.timestamp).label("day"),
            func.count(SmartEvent.id).label("cnt"),
        ).filter(SmartEvent.timestamp >= trend_since).group_by(func.date(SmartEvent.timestamp)).all()
        alert_rule_by_day = {row.day: row.cnt for row in alert_rule_rows}
        detection_by_day = {row.day: row.cnt for row in detection_rows}
        smart_by_day = {row.day: row.cnt for row in smart_rows}
        historical_trend = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            historical_trend.append({
                "date": day.isoformat(),
                "detection_event_count": int(detection_by_day.get(day, 0)),
                "alert_rule_count": int(alert_rule_by_day.get(day, 0)),
                "smart_event_count": int(smart_by_day.get(day, 0)),
            })

        # 检测类型 Top：优先今日，无数据则回退累计
        type_rows = db.query(
            DetectionEvent.event_type,
            func.count(DetectionEvent.event_id).label("today_count"),
        ).filter(
            DetectionEvent.created_at >= today_start,
            DetectionEvent.event_type.isnot(None),
        ).group_by(DetectionEvent.event_type).order_by(func.count(DetectionEvent.event_id).desc()).limit(8).all()
        stats_scope = "today"
        if not type_rows:
            stats_scope = "total"
            type_rows = db.query(
                DetectionEvent.event_type,
                func.count(DetectionEvent.event_id).label("today_count"),
            ).filter(
                DetectionEvent.event_type.isnot(None),
            ).group_by(DetectionEvent.event_type).order_by(func.count(DetectionEvent.event_id).desc()).limit(8).all()
        total_type_rows = db.query(
            DetectionEvent.event_type,
            func.count(DetectionEvent.event_id).label("total_count"),
        ).filter(DetectionEvent.event_type.isnot(None)).group_by(DetectionEvent.event_type).all()
        total_type_map = {row.event_type: row.total_count for row in total_type_rows}
        detection_type_stats = []
        for row in type_rows:
            category = _map_event_type(row.event_type)
            count_value = int(row.today_count or 0)
            total_count = int(total_type_map.get(row.event_type, 0))
            if stats_scope == "today":
                display_count = count_value
                ratio_base = max(detection_event_today, 1)
            else:
                display_count = total_count
                ratio_base = max(detection_event_total, 1)
            detection_type_stats.append({
                "category": category,
                "today_count": count_value if stats_scope == "today" else 0,
                "total_count": total_count,
                "display_count": display_count,
                "ratio": round(display_count / ratio_base * 100, 1),
            })

        # 昨日对比增长率（检测事件总量按类型）
        yesterday_start = today_start - timedelta(days=1)
        yesterday_type_rows = db.query(
            DetectionEvent.event_type,
            func.count(DetectionEvent.event_id).label("cnt"),
        ).filter(
            DetectionEvent.created_at >= yesterday_start,
            DetectionEvent.created_at < today_start,
        ).group_by(DetectionEvent.event_type).all()
        day_before_start = today_start - timedelta(days=2)
        day_before_type_rows = db.query(
            DetectionEvent.event_type,
            func.count(DetectionEvent.event_id).label("cnt"),
        ).filter(
            DetectionEvent.created_at >= day_before_start,
            DetectionEvent.created_at < yesterday_start,
        ).group_by(DetectionEvent.event_type).all()
        yesterday_map = {row.event_type: row.cnt for row in yesterday_type_rows}
        day_before_map = {row.event_type: row.cnt for row in day_before_type_rows}
        behavior_stats = []
        for row in type_rows[:8]:
            et = row.event_type
            yesterday_count = int(yesterday_map.get(et, 0))
            day_before_count = int(day_before_map.get(et, 0))
            if day_before_count > 0:
                growth_rate = round((yesterday_count - day_before_count) / day_before_count * 100, 1)
            elif yesterday_count > 0:
                growth_rate = 100.0
            else:
                growth_rate = 0.0
            total_count = int(total_type_map.get(et, 0))
            today_count = int(row.today_count or 0) if stats_scope == "today" else 0
            behavior_stats.append({
                "category": _map_event_type(et),
                "today_count": today_count,
                "total_count": total_count,
                "display_count": today_count if stats_scope == "today" else total_count,
                "growth_rate": growth_rate,
            })

        # 设备告警排行：优先今日，无数据则回退累计
        device_rank_rows = db.query(
            Device.device_name,
            func.count(DetectionEvent.event_id).label("today_count"),
        ).join(DetectionEvent, DetectionEvent.device_id == Device.device_id).filter(
            DetectionEvent.created_at >= today_start,
        ).group_by(Device.device_name).order_by(func.count(DetectionEvent.event_id).desc()).limit(6).all()
        device_rank_scope = "today"
        if not device_rank_rows:
            device_rank_scope = "total"
            device_rank_rows = db.query(
                Device.device_name,
                func.count(DetectionEvent.event_id).label("today_count"),
            ).join(DetectionEvent, DetectionEvent.device_id == Device.device_id).group_by(
                Device.device_name
            ).order_by(func.count(DetectionEvent.event_id).desc()).limit(6).all()
        device_ranking = [
            {"device_name": name or "未知设备", "today_count": int(cnt or 0)}
            for name, cnt in device_rank_rows
        ]

        # 最近检测事件
        recent_rows = db.query(DetectionEvent, Device.device_name).join(
            Device, DetectionEvent.device_id == Device.device_id
        ).order_by(DetectionEvent.created_at.desc()).limit(30).all()
        recent_events = [_serialize_detection_event(event, device_name) for event, device_name in recent_rows]

        # 最新抓拍
        snapshot_rows = db.query(DetectionEvent, Device.device_name).join(
            Device, DetectionEvent.device_id == Device.device_id
        ).filter(
            DetectionEvent.thumbnail_path.isnot(None),
            DetectionEvent.thumbnail_path != "",
        ).order_by(DetectionEvent.created_at.desc()).limit(12).all()
        latest_snapshots = [_serialize_detection_event(event, device_name) for event, device_name in snapshot_rows]

        # 人群分析最新人数
        subquery = db.query(
            CrowdAnalysisResult.job_id,
            func.max(CrowdAnalysisResult.timestamp).label("latest_timestamp"),
        ).group_by(CrowdAnalysisResult.job_id).subquery()
        crowd_rows = db.query(
            CrowdAnalysisJob.job_name,
            CrowdAnalysisResult.total_person_count,
            CrowdAnalysisResult.timestamp,
            CrowdAnalysisJob.is_active,
        ).join(
            CrowdAnalysisResult, CrowdAnalysisJob.job_id == CrowdAnalysisResult.job_id
        ).join(
            subquery,
            (CrowdAnalysisResult.job_id == subquery.c.job_id)
            & (CrowdAnalysisResult.timestamp == subquery.c.latest_timestamp),
        ).order_by(CrowdAnalysisResult.total_person_count.desc()).limit(8).all()
        crowd_distribution = [
            {
                "job_name": job_name or "未命名任务",
                "people_count": int(people_count or 0),
                "last_update": ts.isoformat() if ts else None,
                "is_active": bool(is_active),
            }
            for job_name, people_count, ts, is_active in crowd_rows
        ]

        # 事件状态分布
        status_labels = {
            EventStatus.new: "未处理",
            EventStatus.viewed: "已查看",
            EventStatus.flagged: "已标记",
            EventStatus.archived: "已归档",
        }
        status_rows = db.query(
            DetectionEvent.status,
            func.count(DetectionEvent.event_id).label("cnt"),
        ).group_by(DetectionEvent.status).all()
        event_status_distribution = [
            {
                "status": _event_status_value(status),
                "label": status_labels.get(status, str(status)),
                "count": int(cnt or 0),
            }
            for status, cnt in status_rows
        ]

        # 近 7 天检测事件按小时分布（0-23）
        hour_rows = db.query(
            func.extract("hour", DetectionEvent.created_at).label("hour"),
            func.count(DetectionEvent.event_id).label("cnt"),
        ).filter(
            DetectionEvent.created_at >= trend_since,
        ).group_by(func.extract("hour", DetectionEvent.created_at)).all()
        hour_map = {int(row.hour): int(row.cnt or 0) for row in hour_rows if row.hour is not None}
        hourly_distribution = [
            {"hour": h, "label": f"{h:02d}:00", "count": hour_map.get(h, 0)}
            for h in range(24)
        ]

        # 规则告警命中 Top（按规则名）
        alert_rule_stat_rows = db.query(
            AlertRule.name,
            func.count(CompositeAlert.alert_id).label("cnt"),
        ).join(
            CompositeAlert, CompositeAlert.rule_id == AlertRule.rule_id
        ).group_by(AlertRule.name).order_by(func.count(CompositeAlert.alert_id).desc()).limit(6).all()
        alert_rule_stats = [
            {"name": name or "未命名规则", "value": int(cnt or 0)}
            for name, cnt in alert_rule_stat_rows
        ]

        # 复合告警最近记录
        composite_rows = db.query(
            CompositeAlert, Device.device_name
        ).outerjoin(
            Device, CompositeAlert.device_id == Device.device_id
        ).order_by(CompositeAlert.fired_at.desc()).limit(10).all()
        recent_composite_alerts = [
            {
                "id": alert.alert_id,
                "source": "composite",
                "title": alert.title,
                "summary": (alert.summary or "")[:120],
                "device_name": device_name or "多设备",
                "status": alert.status or "new",
                "timestamp": alert.fired_at.isoformat() if alert.fired_at else None,
            }
            for alert, device_name in composite_rows
        ]

        recent_vlm_alerts = []

        # 离线设备
        offline_device_rows = db.query(
            Device.device_name, Device.ip_address, Device.last_online_time
        ).filter(Device.status.is_(False)).order_by(Device.last_online_time.desc()).limit(8).all()
        offline_devices = [
            {
                "name": name or "未命名",
                "ip": ip or "",
                "last_online": last.isoformat() if last else None,
            }
            for name, ip, last in offline_device_rows
        ]

        # 推送与模型
        push_config_enabled = db.query(DataPushConfig).filter(DataPushConfig.enabled.is_(True)).count()
        push_success_today = db.query(DataPushLog).filter(
            DataPushLog.status == "success",
            DataPushLog.created_at >= today_start,
        ).count()
        push_failure_today = db.query(DataPushLog).filter(
            DataPushLog.status == "failure",
            DataPushLog.created_at >= today_start,
        ).count()
        listener_running = 0
        active_models = db.query(DetectionModel).filter(DetectionModel.is_active.is_(True)).count()
        total_models = db.query(DetectionModel).count()
        vlm_alert_total = 0

        smart_scheme_running = db.query(SmartScheme).filter(SmartScheme.status == "running").count()
        listener_error = 0
        listener_running_count = 0

        # 订阅事件最近记录
        smart_event_rows = db.query(SmartEvent).order_by(SmartEvent.timestamp.desc()).limit(10).all()
        recent_smart_events = [
            {
                "id": ev.id,
                "source": "smart",
                "title": ev.title or ev.event_type or "订阅事件",
                "summary": (ev.description or "")[:120],
                "event_type": ev.event_type,
                "priority": ev.priority or "normal",
                "status": ev.status or "pending",
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
            }
            for ev in smart_event_rows
        ]

        # 最近推送记录（优先失败）
        push_log_rows = db.query(DataPushLog).order_by(
            DataPushLog.created_at.desc()
        ).limit(20).all()
        push_failures = [
            {
                "push_name": log.push_name or "未命名",
                "status": log.status,
                "message": (log.message or "")[:80],
                "target": log.target_summary or "",
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            }
            for log in push_log_rows if log.status == "failure"
        ][:8]
        recent_push_logs = [
            {
                "push_name": log.push_name or "未命名",
                "status": log.status,
                "method": log.push_method or "",
                "duration_ms": log.duration_ms,
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            }
            for log in push_log_rows[:8]
        ]

        # 热力图区域当前人数
        heatmap_rows = db.query(
            HeatmapArea.name,
            HeatmapBinding.current_count,
            HeatmapBinding.last_update_time,
            HeatmapBinding.data_source_name,
        ).join(
            HeatmapBinding, HeatmapBinding.area_id == HeatmapArea.id
        ).filter(
            HeatmapArea.is_active.is_(True),
            HeatmapBinding.is_active.is_(True),
        ).order_by(HeatmapBinding.current_count.desc()).limit(8).all()
        heatmap_area_stats = [
            {
                "area_name": name or "未命名区域",
                "people_count": int(cnt or 0),
                "source": source or "",
                "last_update": ts.isoformat() if ts else None,
            }
            for name, cnt, ts, source in heatmap_rows
        ]

        # 外部事件最近记录（展板已改用规则告警，保留空列表兼容旧前端）
        recent_external_events = []

        listener_status_summary = []

        return {
            "data": {
                "overview": {
                    "device_total": device_total,
                    "device_online": device_online,
                    "device_offline": max(device_total - device_online, 0),
                    "detection_config_total": detection_config_total,
                    "detection_config_enabled": detection_config_enabled,
                    "detection_event_total": detection_event_total,
                    "detection_event_today": detection_event_today,
                    "detection_event_new": detection_event_new,
                    "smart_scheme_total": smart_scheme_total,
                    "smart_event_total": smart_event_total,
                    "smart_event_today": smart_event_today,
                    "crowd_job_total": crowd_job_total,
                    "crowd_job_active": crowd_job_active,
                    "external_event_total": external_event_total,
                    "external_event_today": external_event_today,
                    "vlm_job_total": vlm_job_total,
                    "vlm_job_active": vlm_job_active,
                    "vlm_alert_today": vlm_alert_today,
                    "composite_alert_total": composite_alert_total,
                    "composite_alert_today": composite_alert_today,
                    "alert_rule_enabled": alert_rule_enabled,
                    "edge_server_total": edge_server_total,
                    "edge_server_online": edge_server_online,
                    "avg_detection_time_ms": round(float(avg_detection_time_ms or 0), 1),
                    "avg_confidence": round(float(avg_confidence_raw or 0) * 100, 1),
                    "push_config_enabled": int(push_config_enabled),
                    "push_success_today": int(push_success_today),
                    "push_failure_today": int(push_failure_today),
                    "listener_running": int(listener_running),
                    "active_models": int(active_models),
                    "total_models": int(total_models),
                    "vlm_alert_total": int(vlm_alert_total),
                    "smart_scheme_running": int(smart_scheme_running),
                    "listener_error": int(listener_error),
                    "listener_running_count": int(listener_running_count),
                },
                "detection_type_stats": detection_type_stats,
                "behavior_stats": behavior_stats,
                "stats_scope": stats_scope,
                "device_ranking": device_ranking,
                "device_rank_scope": device_rank_scope,
                "performance_trend": performance_trend,
                "historical_trend": historical_trend,
                "recent_events": recent_events,
                "latest_snapshots": latest_snapshots,
                "crowd_distribution": crowd_distribution,
                "event_status_distribution": event_status_distribution,
                "hourly_distribution": hourly_distribution,
                "external_engine_stats": alert_rule_stats,
                "alert_rule_stats": alert_rule_stats,
                "recent_composite_alerts": recent_composite_alerts,
                "recent_vlm_alerts": recent_vlm_alerts,
                "offline_devices": offline_devices,
                "recent_smart_events": recent_smart_events,
                "recent_external_events": recent_external_events,
                "recent_push_logs": recent_push_logs,
                "push_failures": push_failures,
                "heatmap_area_stats": heatmap_area_stats,
                "listener_status_summary": listener_status_summary,
                "screen_name": resolve_dashboard_screen_name(db),
                "query_time": now.isoformat(),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取展板数据失败: {str(e)}")
