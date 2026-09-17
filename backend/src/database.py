from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Integer, Float, Enum, ForeignKey, ARRAY, Text, SmallInteger, Index
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime
import uuid
from sqlalchemy import LargeBinary
import os

Base = declarative_base()

class AlarmStatus(enum.Enum):
    pending = "pending"
    processed = "processed"
    ignored = "ignored"

class AnalysisTarget(enum.Enum):
    person = "person"
    vehicle = "vehicle"
    fire = "fire"
    helmet = "helmet"

class SaveMode(enum.Enum):
    none="none"
    screenshot = "screenshot"
    video = "video"
    both = "both"

class EventStatus(enum.Enum):
    new = "new"
    viewed = "viewed"
    flagged = "flagged"
    archived = "archived"

class PushMethod(enum.Enum):
    http = "http"
    https = "https"
    tcp = "tcp"
    mqtt = "mqtt"

class DetectionFrequency(enum.Enum):
    realtime = "realtime"
    scheduled = "scheduled"
    manual = "manual"

class DeviceGroup(Base):
    """设备分组"""
    __tablename__ = "device_group"

    group_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    devices = relationship("Device", back_populates="device_group")

class Device(Base):
    __tablename__ = "device"
    
    device_id = Column(String(64), primary_key=True)
    device_name = Column(String(255), nullable=False)
    device_type = Column(String(50))
    ip_address = Column(String(15), nullable=False)
    port = Column(SmallInteger, nullable=False)
    username = Column(String(64), nullable=False)
    password = Column(String(256), nullable=False)
    channel = Column(Integer, default=1)  # 通道号，默认为1
    stream_type = Column(String(10), default="main")  # 码流类型，main或sub
    rtsp_url_mode = Column(String(20), default="dahua")  # dahua=大华默认, custom=自定义URL/模板
    rtsp_url = Column(Text, nullable=True)  # 自定义 RTSP 完整地址或模板
    monitor_method = Column(String(32), default="auto", comment="探活方式: auto/rtsp/tcp/http_dahua/ping")
    offline_count = Column(Integer, default=0) # 记录设备连续离线的次数
    last_online_time = Column(DateTime, default=datetime.now) # 记录设备最后一次在线的时间
    status = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime)
    location = Column(String(255))
    area = Column(String(255))
    group_id = Column(String(64), ForeignKey('device_group.group_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    area_coordinates = Column(JSONB)  # 新增字段，用于存储区域坐标
    
    device_group = relationship("DeviceGroup", back_populates="devices")
    detection_configs = relationship("DetectionConfig", back_populates="device", cascade="all, delete-orphan")
    detection_events = relationship("DetectionEvent", back_populates="device", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(String(64), primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(64), nullable=False)
    role = Column(String(20))
    allowed_devices = Column(ARRAY(Text))
    created_at = Column(DateTime, default=datetime.now)

class SysLog(Base):
    __tablename__ = "syslog"
    
    log_id = Column(Integer, primary_key=True)
    user_id = Column(String(64), ForeignKey('users.user_id'))
    action_type = Column(String(50), nullable=False)
    target_id = Column(String(64))
    detail = Column(Text)
    log_time = Column(DateTime, default=datetime.now)

class DetectionModel(Base):
    __tablename__ = "detection_model"
    
    models_id = Column(String(64), primary_key=True)
    models_name = Column(String(255), nullable=False)
    models_type = Column(String(50), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    format = Column(String(20), nullable=False)
    description = Column(Text)
    parameters = Column(JSONB)
    upload_time = Column(DateTime, default=datetime.now)
    last_used = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_gpu = Column(Boolean, default=False)
    models_classes = Column(JSONB, nullable=True)  # 新增字段，用于存储类别信息

    detection_configs = relationship("DetectionConfig", back_populates="model", cascade="all, delete-orphan")

class DetectionConfig(Base):
    __tablename__ = "detection_config"

    config_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_mode = Column(String(20), default="device")  # device | group
    device_id = Column(String(64), ForeignKey('device.device_id'), nullable=True)
    group_id = Column(String(64), ForeignKey('device_group.group_id'), nullable=True)
    group_settings = Column(JSONB)  # 分组检测：取帧策略、轮询间隔等
    models_id = Column(String(64), ForeignKey('detection_model.models_id'), nullable=False)
    enabled = Column(Boolean, default=False)
    sensitivity = Column(Float, default=0.5)
    target_classes = Column(ARRAY(Text))
    frequency = Column(Enum(DetectionFrequency), default=DetectionFrequency.realtime)
    save_mode = Column(Enum(SaveMode), default=SaveMode.screenshot)
    save_duration = Column(Integer, default=10)
    max_storage_days = Column(Integer, default=30)
    area_coordinates = Column(JSONB)  # 新增字段，用于存储区域坐标
    schedule_config = Column(JSONB)  # 运行时段等配置（schedule_config.runtime）
    stream_type = Column(String(10), default="main")  # 码流类型，main或sub（按检测配置独立设置）
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(String(64), ForeignKey('users.user_id'))
    
    device = relationship("Device", back_populates="detection_configs")
    device_group = relationship("DeviceGroup", backref="detection_configs")
    model = relationship("DetectionModel", back_populates="detection_configs")
    # schedules = relationship("DetectionSchedule", back_populates="config", cascade="all, delete-orphan")
    events = relationship("DetectionEvent", back_populates="config", cascade="all, delete-orphan")
    rules = relationship("DetectionRule", back_populates="config", cascade="all, delete-orphan", foreign_keys="DetectionRule.config_id")

class DetectionEvent(Base):
    __tablename__ = "detection_event"
    
    event_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey('device.device_id'), nullable=False)
    config_id = Column(String(64), ForeignKey('detection_config.config_id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    event_type = Column(String(50))
    confidence = Column(Float)
    bounding_box = Column(JSONB)
    # 新增以下两个二进制字段
    thumbnail_data = Column(LargeBinary)  # 存储JPEG图像数据
    is_compressed = Column(Boolean, default=False)  # 添加压缩标记
    # video_data = Column(LargeBinary)     # 存储MP4视频数据（可选）
    # 删除原来的路径字段（如果存在）
    snippet_path = Column(Text)
    thumbnail_path = Column(Text)
    meta_data = Column(JSONB)
    status = Column(Enum(EventStatus), default=EventStatus.new)
    viewed_at = Column(DateTime)
    viewed_by = Column(String(64), ForeignKey('users.user_id'))
    notes = Column(Text)
    location = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    
    device = relationship("Device", back_populates="detection_events")
    config = relationship("DetectionConfig", back_populates="events")
    viewer = relationship("User", foreign_keys=[viewed_by])
    person_gallery_items = relationship("PersonGalleryItem", back_populates="event", cascade="all, delete-orphan")


class PersonGalleryItem(Base):
    """人员搜索图库（POC：检测事件人体抠图 + 特征向量）"""
    __tablename__ = "person_gallery"

    gallery_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(64), ForeignKey("detection_event.event_id"), nullable=True)
    device_id = Column(String(64), ForeignKey("device.device_id"), nullable=False)
    bbox_index = Column(Integer, default=0)
    confidence = Column(Float)
    crop_path = Column(Text, nullable=False)
    bbox = Column(JSONB)
    embedding = Column(JSONB)
    created_at = Column(DateTime, default=datetime.now, index=True)

    event = relationship("DetectionEvent", back_populates="person_gallery_items")
    device = relationship("Device")

class DetectionPerformance(Base):
    __tablename__ = "detection_performance"
    
    performance_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey('device.device_id'))
    config_id = Column(String(64), ForeignKey('detection_config.config_id'))
    timestamp = Column(DateTime, default=datetime.now)
    detection_time = Column(Float)
    preprocessing_time = Column(Float)
    postprocessing_time = Column(Float)
    frame_width = Column(Integer)
    frame_height = Column(Integer)
    objects_detected = Column(Integer)
    device = relationship("Device")
    config = relationship("DetectionConfig")

class DataPushConfig(Base):
    __tablename__ = "data_push_config"
    
    push_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    push_name = Column(String(255), nullable=False)
    push_method = Column(Enum(PushMethod), nullable=False)
    # 修改config_id为可选，允许推送器独立于检测配置
    config_id = Column(String(64), ForeignKey('detection_config.config_id'), nullable=True)
    # 添加标签字段，用于灵活关联不同模块
    tags = Column(ARRAY(Text), default=[])
    enabled = Column(Boolean, default=True)
    
    # HTTP/HTTPS设置
    http_url = Column(Text)
    http_headers = Column(JSONB)
    http_method = Column(String(10), default="POST")
    
    # TCP设置
    tcp_host = Column(String(255))
    tcp_port = Column(Integer)
    
    # MQTT设置
    mqtt_broker = Column(String(255))
    mqtt_port = Column(Integer, default=1883)
    mqtt_topic = Column(String(255))
    mqtt_client_id = Column(String(255))
    mqtt_username = Column(String(255))
    mqtt_password = Column(String(255))
    mqtt_use_tls = Column(Boolean, default=False)
    
    # 通用设置
    push_interval = Column(Integer, default=0)  # 0表示实时推送，>0表示间隔秒数
    last_push_time = Column(DateTime)
    retry_count = Column(Integer, default=3)
    retry_interval = Column(Integer, default=10)  # 重试间隔(秒)
    include_image = Column(Boolean, default=False)  # 是否包含图像数据
    data_format = Column(String(50), default="json")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关系可以保留，但现在是可选的
    config = relationship("DetectionConfig", foreign_keys=[config_id])


class DataPushLog(Base):
    """数据推送执行记录（持久化，便于查询成功/失败）"""
    __tablename__ = "data_push_log"

    log_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    push_id = Column(String(64), ForeignKey("data_push_config.push_id"), nullable=False, index=True)
    push_name = Column(String(255))
    push_method = Column(String(32))
    status = Column(String(20), nullable=False, index=True)  # success | failure
    target_summary = Column(String(500))
    message = Column(Text)
    tags = Column(ARRAY(Text), default=[])
    config_id = Column(String(64))
    duration_ms = Column(Integer)
    payload_preview = Column(JSONB)
    is_test = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now, index=True)

    push_config = relationship("DataPushConfig", foreign_keys=[push_id])


class DetectionRule(Base):
    """检测规则：Fact 匹配条件 + 冷却 + 动作"""
    __tablename__ = "detection_rule"

    rule_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id = Column(String(64), ForeignKey('detection_config.config_id'), nullable=True)
    device_id = Column(String(64), ForeignKey('device.device_id'), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=100)
    is_builtin = Column(Boolean, default=False)
    builtin_key = Column(String(128))
    cooldown_sec = Column(Integer, default=15)
    cooldown_scope = Column(String(32), default="scenario")
    conditions = Column(JSONB, nullable=False, default=dict)
    actions = Column(JSONB, nullable=False, default=list)
    schedule = Column(JSONB)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    config = relationship("DetectionConfig", back_populates="rules", foreign_keys=[config_id])
    device = relationship("Device", foreign_keys=[device_id])

class CrowdAnalysisJob(Base):
    __tablename__ = "crowd_analysis_job"
    
    job_id = Column(String(64), primary_key=True)
    job_name = Column(String(128), nullable=False)
    device_mode = Column(String(20), default="manual")  # manual | group
    group_id = Column(String(64), ForeignKey('device_group.group_id'), nullable=True)
    group_settings = Column(JSONB)  # 取帧策略、设备间隔等
    schedule_config = Column(JSONB)  # 生效时段 schedule_config.runtime
    device_ids = Column(ARRAY(String)) # 设备ID列表（手动模式）或分组快照
    models_id = Column(String(64), ForeignKey('detection_model.models_id'), nullable=True) # 检测模型ID
    interval = Column(Integer, nullable=True) # 执行间隔(秒)
    cron_expression = Column(String(64), nullable=True) # Cron表达式
    tags = Column(ARRAY(String)) # 标签列表
    location_info = Column(JSONB, nullable=True) # 位置信息
    description = Column(String(512), nullable=True) # 描述
    is_active = Column(Boolean, default=True) # 是否启用
    detect_classes = Column(ARRAY(String), nullable=True) # 检测类别
    confidence_threshold = Column(Float, default=0.5) # 置信度阈值，默认0.5
    created_at = Column(DateTime, default=datetime.now)
    last_run = Column(DateTime, nullable=True) # 最后执行时间
    last_result = Column(JSONB, nullable=True) # 最后结果
    last_error = Column(String(512), nullable=True) # 最后错误信息
    warning_threshold = Column(Integer, default=0)  # 人数预警阈值，0表示不预警
    warning_message = Column(String(256))  # 预警消息模板
    warning_receivers = Column(ARRAY(String))  # 预警接收者
    
    model = relationship("DetectionModel", foreign_keys=[models_id])
    device_group = relationship("DeviceGroup", foreign_keys=[group_id])

class CrowdAnalysisResult(Base):
    __tablename__ = "crowd_analysis_result"
    
    result_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(64), ForeignKey('crowd_analysis_job.job_id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    total_person_count = Column(Integer, default=0)
    camera_counts = Column(JSONB)  # 存储各摄像头的人数数据
    location_info = Column(JSONB, nullable=True)
    
    job = relationship("CrowdAnalysisJob", back_populates="results")

# 添加反向关系
CrowdAnalysisJob.results = relationship("CrowdAnalysisResult", back_populates="job")


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:admin123@127.0.0.1:5432/edge_box",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 添加DetectionLog表
class DetectionLog(Base):
    __tablename__ = "detection_log"
    
    log_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_id = Column(String(64), ForeignKey('detection_config.config_id'), nullable=False)
    device_id = Column(String(64), ForeignKey('device.device_id'), nullable=True)
    operation = Column(String(50), nullable=False)  # start, stop, auto_start, auto_stop
    status = Column(String(50))  # success, failed
    message = Column(Text)
    created_by = Column(String(64), ForeignKey('users.user_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    
    # 关联
    config = relationship("DetectionConfig")
    device = relationship("Device")
    user = relationship("User", foreign_keys=[created_by]) 

class EdgeServer(Base):
    """边缘服务器模型"""
    __tablename__ = "edge_servers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="服务器名称")
    ip_address = Column(String(45), nullable=False, unique=True, comment="IP地址")
    port = Column(Integer, default=80, nullable=False, comment="端口号")
    description = Column(Text, comment="服务器描述")
    platform_type = Column(String(20), default="maisi", nullable=False, comment="平台类型: maisi/nodered/custom")
    admin_url = Column(String(512), comment="管理/编辑器地址")
    dashboard_url = Column(String(512), comment="Dashboard 地址")
    health_check_url = Column(String(512), comment="自定义健康检查地址")
    
    # 状态信息
    status = Column(String(20), default="unknown", comment="状态: online/offline/checking/unknown")
    last_checked = Column(DateTime(timezone=True), comment="最后检查时间")
    
    # 系统信息 (JSON格式存储)
    system_info = Column(JSONB, comment="系统信息")
    version_info = Column(JSONB, comment="版本信息")
    device_info = Column(JSONB, comment="设备信息")
    
    # 创建和更新时间
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 是否启用
    is_active = Column(Boolean, default=True, comment="是否启用")
    
    def __repr__(self):
        return f"<EdgeServer(id={self.id}, name='{self.name}', ip='{self.ip_address}')>" 

class ListenerType(enum.Enum):
    tcp = "tcp"
    mqtt = "mqtt"
    sdk = "sdk"
    http = "http"
    websocket = "websocket"

class ExternalEventType(enum.Enum):
    detection = "detection"
    alarm = "alarm"
    status = "status"
    command = "command"
    heartbeat = "heartbeat"
    other = "other"

class ListenerConfig(Base):
    __tablename__ = "listener_configs"
    
    config_id = Column(String, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    listener_type = Column(Enum(ListenerType), nullable=False)
    connection_config = Column(JSONB, nullable=False)  # 连接配置
    data_mapping = Column(JSONB)  # 数据映射规则
    filter_rules = Column(JSONB)  # 过滤规则
    
    # 新增：边缘设备和算法字段映射
    edge_device_mappings = Column(JSONB)  # 关联的边缘设备列表
    algorithm_field_mappings = Column(JSONB)  # 算法字段映射配置 {device_id: [engine_ids]}
    algorithm_specific_fields = Column(JSONB)  # 算法特定字段配置 {device_id: {engine_id: {field_configs}}}
    
    # 新增：设备和引擎名称映射（用于数据标准化时获取名称）
    device_name_mappings = Column(JSONB)  # 设备SN到名称的映射 {device_sn: device_name}
    engine_name_mappings = Column(JSONB)  # 引擎ID到名称的映射 {engine_id: engine_name}
    
    storage_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=False)
    push_config = Column(JSONB)  # 推送配置
    enabled = Column(Boolean, default=False)
    created_by = Column(String, ForeignKey('users.user_id'))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    creator = relationship("User")

class ExternalEvent(Base):
    __tablename__ = "external_events"
    
    event_id = Column(String, primary_key=True)
    config_id = Column(String, ForeignKey('listener_configs.config_id'), nullable=False)
    source_type = Column(Enum(ListenerType), nullable=False)
    event_type = Column(Enum(ExternalEventType), nullable=False)
    
    # 设备相关信息
    device_id = Column(String(64))  # 可选关联设备（保持向后兼容）
    device_sn = Column(String(100))  # 新增：设备SN码
    device_name = Column(String(200))  # 新增：设备名称
    channel_id = Column(String(50))  # 新增：视频通道ID
    engine_id = Column(String(50))   # 新增：算法引擎ID
    engine_name = Column(String(200))  # 新增：算法引擎名称
    
    location = Column(String(200))
    confidence = Column(Float)
    original_data = Column(JSONB, nullable=False)  # 原始数据
    normalized_data = Column(JSONB)  # 标准化数据
    algorithm_data = Column(JSONB)   # 新增：算法特定数据
    event_metadata = Column(JSONB)  # 元数据
    status = Column(Enum(EventStatus), default=EventStatus.new)
    processed = Column(Boolean, default=False)
    viewed_at = Column(DateTime)  # 新增：查看时间
    viewed_by = Column(String(64), ForeignKey('users.user_id'))  # 新增：查看者
    notes = Column(Text)  # 新增：备注
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    config = relationship("ListenerConfig")
    # viewer = relationship("User", foreign_keys=[viewed_by])  # 新增：查看者关系
    # device = relationship("Device")

class ListenerStatus(Base):
    __tablename__ = "listener_status"
    
    config_id = Column(String, ForeignKey('listener_configs.config_id'), primary_key=True)
    status = Column(String(20), default='stopped')  # running, stopped, error
    last_event_time = Column(DateTime)
    events_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    started_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    config = relationship("ListenerConfig")

# 添加索引
Index('idx_external_events_timestamp', ExternalEvent.timestamp)
Index('idx_external_events_type', ExternalEvent.event_type)
Index('idx_external_events_config', ExternalEvent.config_id)
Index('idx_listener_configs_type', ListenerConfig.listener_type)

# 事件订阅相关表模型
class SmartScheme(Base):
    """事件订阅表"""
    __tablename__ = "smart_schemes"
    
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String(64), ForeignKey('device.device_id'), nullable=False, comment="摄像头ID")
    camera_port = Column(Integer, default=37777, comment="摄像头监听端口")
    event_types = Column(ARRAY(String), nullable=False, comment="订阅的事件类型")
    alarm_interval = Column(Integer, default=60, comment="报警间隔时间(秒)")
    push_tags = Column(String(500), comment="推送标签")
    remarks = Column(Text, comment="备注信息")
    status = Column(String(20), default='stopped', comment="状态: running/stopped/error")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    started_at = Column(DateTime, comment="启动时间")
    stopped_at = Column(DateTime, comment="停止时间")
    
    # 关系
    camera = relationship("Device", foreign_keys=[camera_id])
    events = relationship("SmartEvent", back_populates="scheme", cascade="all, delete-orphan")

class SmartEvent(Base):
    """智能事件表"""
    __tablename__ = "smart_events"
    
    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    scheme_id = Column(String(64), ForeignKey('smart_schemes.id'), nullable=False, comment="订阅ID")
    event_type = Column(String(50), nullable=False, comment="事件类型")
    title = Column(String(255), nullable=False, comment="事件标题")
    description = Column(Text, comment="事件描述")
    priority = Column(String(20), default='normal', comment="优先级: low/normal/high/critical")
    event_data = Column(JSONB, comment="事件数据")
    status = Column(String(20), default='pending', comment="状态: pending/processed/ignored")
    timestamp = Column(DateTime, nullable=False, comment="事件发生时间")
    processed_at = Column(DateTime, comment="处理时间")
    processing_result = Column(String(50), comment="处理结果")
    processing_comment = Column(Text, comment="处理备注")
    processing_by = Column(String(100), comment="处理人")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    
    # 关系
    scheme = relationship("SmartScheme", back_populates="events")

# 热力图相关表模型
class HeatmapMap(Base):
    """热力图地图表"""
    __tablename__ = "heatmap_maps"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="地图名称")
    file_path = Column(String(500), nullable=False, comment="地图文件路径")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_size = Column(Integer, nullable=False, comment="文件大小(字节)")
    mime_type = Column(String(100), nullable=False, comment="文件MIME类型")
    width = Column(Integer, comment="图片宽度")
    height = Column(Integer, comment="图片高度")
    scale_factor = Column(Float, default=1.0, comment="比例尺(像素/米)")
    description = Column(Text, comment="地图描述")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    created_by = Column(String(100), comment="创建人")
    
    # 关系
    areas = relationship("HeatmapArea", back_populates="map", cascade="all, delete-orphan")
    dashboard_configs = relationship("HeatmapDashboardConfig", back_populates="map", cascade="all, delete-orphan")

class HeatmapArea(Base):
    """热力图区域表"""
    __tablename__ = "heatmap_areas"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    map_id = Column(Integer, ForeignKey('heatmap_maps.id'), nullable=False, comment="关联地图ID")
    name = Column(String(255), nullable=False, comment="区域名称")
    shape_type = Column(String(20), default='polygon', comment="形状类型: polygon区域 / point项目点")
    points = Column(JSONB, nullable=False, comment="区域多边形坐标点")
    color = Column(String(50), default='rgba(74, 144, 226, 0.5)', comment="区域颜色")
    area_size = Column(Float, default=0, comment="区域面积(平方米)")
    max_capacity = Column(Integer, comment="最大容量")
    description = Column(Text, comment="区域描述")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 关系
    map = relationship("HeatmapMap", back_populates="areas")
    bindings = relationship("HeatmapBinding", back_populates="area", cascade="all, delete-orphan")
    history = relationship("HeatmapHistory", back_populates="area", cascade="all, delete-orphan")

class HeatmapBinding(Base):
    """热力图数据绑定表"""
    __tablename__ = "heatmap_bindings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey('heatmap_areas.id'), nullable=False, comment="关联区域ID")
    data_source_type = Column(String(50), nullable=False, comment="数据源类型(crowd_analysis,manual,api)")
    data_source_id = Column(String(100), comment="数据源ID(如人群分析任务ID)")
    data_source_name = Column(String(255), comment="数据源名称")
    refresh_interval = Column(Integer, default=30, comment="刷新间隔(秒)")
    last_update_time = Column(DateTime, comment="最后更新时间")
    current_count = Column(Integer, default=0, comment="当前人数")
    config = Column(JSONB, comment="绑定配置信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 关系
    area = relationship("HeatmapArea", back_populates="bindings")

class HeatmapDashboardConfig(Base):
    """热力图展板配置表"""
    __tablename__ = "heatmap_dashboard_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    map_id = Column(Integer, ForeignKey('heatmap_maps.id'), nullable=False, comment="关联地图ID")
    display_mode = Column(Enum('preview', 'mini', 'full', name='display_mode_enum'), default='preview', comment="显示模式")
    screen_name = Column(String(128), comment="大屏标题名称")
    max_areas = Column(Integer, default=6, comment="最大显示区域数")
    refresh_interval = Column(Integer, default=30, comment="刷新间隔(秒)")
    config = Column(JSONB, comment="其他配置信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 关系
    map = relationship("HeatmapMap", back_populates="dashboard_configs")

class AlertRule(Base):
    """复合告警规则（定时扫表评估）"""
    __tablename__ = "alert_rule"

    rule_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)
    device_id = Column(String(64), ForeignKey("device.device_id"), nullable=True)
    definition = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, default=100)
    push_tags = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    device = relationship("Device")
    state = relationship("AlertRuleState", back_populates="rule", uselist=False, cascade="all, delete-orphan")
    alerts = relationship("CompositeAlert", back_populates="rule", cascade="all, delete-orphan")


class AlertRuleState(Base):
    """规则评估状态（watermark / 持续条件 / 冷却）"""
    __tablename__ = "alert_rule_state"

    rule_id = Column(String(64), ForeignKey("alert_rule.rule_id"), primary_key=True)
    watermark = Column(DateTime, nullable=True)
    condition_state = Column(JSONB, default=dict)
    last_fired_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    rule = relationship("AlertRule", back_populates="state")


class CompositeAlert(Base):
    """规则命中记录（复合告警）"""
    __tablename__ = "composite_alert"

    alert_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(String(64), ForeignKey("alert_rule.rule_id"), nullable=False)
    device_id = Column(String(64), ForeignKey("device.device_id"), nullable=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text)
    matched_events = Column(JSONB, nullable=False, default=list)
    definition_snapshot = Column(JSONB)
    status = Column(String(20), default="new")
    fired_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)

    rule = relationship("AlertRule", back_populates="alerts")
    device = relationship("Device")


Index("idx_alert_rule_enabled", AlertRule.enabled)
Index("idx_alert_rule_device_id", AlertRule.device_id)
Index("idx_composite_alert_rule_id", CompositeAlert.rule_id)
Index("idx_composite_alert_fired_at", CompositeAlert.fired_at.desc())
Index("idx_composite_alert_device_id", CompositeAlert.device_id)
Index("idx_composite_alert_status", CompositeAlert.status)


class PlatformSetting(Base):
    """平台级键值配置（如大屏外部接口）"""
    __tablename__ = "platform_settings"

    setting_key = Column(String(128), primary_key=True, comment="配置键")
    setting_value = Column(JSONB, nullable=False, default=dict, comment="配置值(JSON)")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

class HeatmapHistory(Base):
    """热力图历史数据表 (可选，用于存储历史统计)"""
    __tablename__ = "heatmap_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey('heatmap_areas.id'), nullable=False, comment="关联区域ID")
    people_count = Column(Integer, nullable=False, comment="人数")
    density = Column(Float, comment="人口密度")
    record_time = Column(DateTime, default=datetime.now, comment="记录时间")
    data_source = Column(String(100), comment="数据来源")
    
    # 关系
    area = relationship("HeatmapArea", back_populates="history")

# 添加热力图相关索引
Index('idx_heatmap_areas_map_id', HeatmapArea.map_id)
Index('idx_heatmap_bindings_area_id', HeatmapBinding.area_id)
Index('idx_heatmap_bindings_data_source', HeatmapBinding.data_source_type, HeatmapBinding.data_source_id)
Index('idx_heatmap_dashboard_config_map_id', HeatmapDashboardConfig.map_id)
Index('idx_heatmap_history_area_time', HeatmapHistory.area_id, HeatmapHistory.record_time)
Index('idx_heatmap_history_record_time', HeatmapHistory.record_time)

# 事件订阅相关索引
Index('idx_smart_schemes_camera_id', SmartScheme.camera_id)
Index('idx_smart_schemes_status', SmartScheme.status)
Index('idx_smart_events_scheme_id', SmartEvent.scheme_id)
Index('idx_smart_events_event_type', SmartEvent.event_type)
Index('idx_smart_events_status', SmartEvent.status)
Index('idx_smart_events_timestamp', SmartEvent.timestamp)

# 数据库依赖注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 