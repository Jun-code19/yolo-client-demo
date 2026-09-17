"""
事件订阅管理模块 - 管理监听摄像头主动上报的不同类型数据事件订阅配置
基于NetSDK开发包实现真实的设备连接和事件订阅
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import uuid
import os

from src.data_pusher import data_pusher

# NetSDK相关导入
try:
    from NetSDK.NetSDK import NetClient
    from NetSDK.SDK_Struct import *
    from NetSDK.SDK_Enum import *
    from NetSDK.SDK_Callback import fDisConnect, fHaveReConnect, fMessCallBackEx1, fVideoStatSumCallBack, fAnalyzerDataCallBack, CB_FUNCTYPE
    # from ctypes import cast, POINTER, c_char, c_long, c_llong, c_dword, c_ldword
    NETSDK_AVAILABLE = True

    # 事件类型 -> (标题后缀, 描述动作短语, 描述前缀)
    # 新增类型时只需要在这里补一行映射即可
    SMART_TYPE_TEXT_MAP = {
        EM_EVENT_IVS_TYPE.CROSSREGIONDETECTION: ("区域入侵", "触发区域入侵", ""),
        EM_EVENT_IVS_TYPE.CROSSLINEDETECTION: ("绊线入侵", "触发绊线入侵", ""),
        EM_EVENT_IVS_TYPE.HEAT_IMAGING_TEMPER: ("温度规则", "触发温度规则", ""),
        EM_EVENT_IVS_TYPE.FIREDETECTION: ("火情报警", "触发火情报警", ""),
        EM_EVENT_IVS_TYPE.SMOKEDETECTION: ("烟雾报警", "触发烟雾报警", ""),
    }

    ALARM_TYPE_TEXT_MAP = {
        SDK_ALARM_TYPE.EVENT_CROSSREGION_DETECTION: ("区域入侵", "触发区域入侵", ""),
        SDK_ALARM_TYPE.EVENT_CROSSLINE_DETECTION: ("绊线入侵", "触发绊线入侵", ""),
        SDK_ALARM_TYPE.ALARM_FIREWARNING_INFO: ("火情报警", "触发火情报警", ""),
        # 兜底：保持原逻辑（非上述类型默认为火情报警）
    }
except ImportError:
    NETSDK_AVAILABLE = False
    SMART_TYPE_TEXT_MAP = {}
    ALARM_TYPE_TEXT_MAP = {}
    logging.warning("NetSDK包未安装，请检查NetSDK包是否正确安装")

from sqlalchemy.orm import Session
from src.database import (
    SessionLocal, Device, SmartScheme, SmartEvent, 
    EventStatus, get_db
)

logger = logging.getLogger(__name__)


@dataclass
class DeviceConnection:
    """设备连接信息"""
    device_id: str  # 存储设备ID而不是Device对象
    device_name: str  # 存储设备名称
    ip_address: str  # 存储设备IP
    port: int  # 存储设备端口
    username: str  # 存储用户名
    password: str  # 存储密码
    login_id: int = 0 # 登录ID
    attach_id: int = 0 # 视频统计摘要ID
    smart_id: int = 0 #智能报警订阅ID
    is_connected: bool = False # 是否连接
    re_connected: bool = False # 是否重新连接成功
    schemes: List[str] = None  # 该设备上的订阅ID列表
    alarm_interval: int = 0  # 报警间隔时间
    last_heartbeat: Optional[datetime] = None # 上次心跳时间
    last_alarm_time: Optional[datetime] = None  # 上次报警时间，用于控制报警间隔
    push_tags: List[str] = None  # 推送标签
    event_types: List[str] = None  # 事件类型

    def __post_init__(self):
        if self.schemes is None:
            self.schemes = []


class SmartSchemer:
    """事件订阅管理器"""
    
    def __init__(self):
        self.device_connections: Dict[str, DeviceConnection] = {}  # device_id -> DeviceConnection
        self.scheme_connections: Dict[str, str] = {}  # scheme_id -> device_id
        self.running = False
        self._lock = threading.Lock()
        
        if NETSDK_AVAILABLE:
            # NetSDK用到的相关变量和回调
            self.m_DisConnectCallBack = fDisConnect(self.DisConnectCallBack)
            self.m_ReConnectCallBack = fHaveReConnect(self.ReConnectCallBack)
            self.m_MessCallBackEx1 = fMessCallBackEx1(self.MessCallBackEx1)
            self.m_VideoStatSumCallBack = fVideoStatSumCallBack(self.VideoStatSumCallBack)
            self.m_AnalyzerDataCallBack = fAnalyzerDataCallBack(self.AnalyzerDataCallBack)
            # 获取NetSDK对象并初始化
            self.sdk = NetClient()
            self.sdk.InitEx(self.m_DisConnectCallBack)
            self.sdk.SetAutoReconnect(self.m_ReConnectCallBack)
            # 设置报警回调函数
            self.sdk.SetDVRMessCallBackEx1(self.m_MessCallBackEx1, 0)
        else:
            self.sdk = None

    @staticmethod
    def _build_title_description(prefix: str, type_value, text_map: Dict, default_text: tuple, device_conn: "DeviceConnection"):
        label, action_text, desc_prefix = text_map.get(type_value, default_text)
        title = f"{prefix}({label})"
        description = f"{desc_prefix}{device_conn.device_name}_{device_conn.ip_address}_{action_text}"
        return title, description
    
    async def initialize(self):
        """初始化管理器"""
        try:
            # 从数据库加载所有启用的订阅配置
            await self._load_schemes()
            
            # 启动监控线程
            self.running = True
            asyncio.create_task(self._monitor_loop())
            
        except Exception as e:
            raise
    
    async def _load_schemes(self):
        """从数据库加载订阅配置"""
        try:
            db = SessionLocal()
            try:
                # 获取所有运行中的订阅
                schemes = db.query(SmartScheme).filter(SmartScheme.status == 'running').all()
                
                for scheme in schemes:
                    await self._start_scheme_internal(scheme, db)
                    
                logger.info(f"加载了 {len(schemes)} 个运行中的订阅")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"加载订阅配置失败: {e}")
    
    async def _start_scheme_internal(self, scheme: SmartScheme, db: Session):
        """内部启动订阅"""
        if not NETSDK_AVAILABLE:
            logger.warning(f"NetSDK未安装，跳过订阅启动: {scheme.id}")
            return False
        try:
            device = db.query(Device).filter(Device.device_id == scheme.camera_id).first()
            if not device:
                logger.error(f"设备不存在: {scheme.camera_id}")
                return False
            
            # 检查设备连接
            if scheme.camera_id not in self.device_connections:
                # 创建新的设备连接
                device_conn = DeviceConnection(
                    device_id=device.device_id,
                    device_name=device.device_name,
                    ip_address=device.ip_address,
                    port=scheme.camera_port,
                    username=device.username,
                    password=device.password,
                    alarm_interval=scheme.alarm_interval,
                    push_tags=scheme.push_tags.split(','),
                    event_types=scheme.event_types
                )
                self.device_connections[scheme.camera_id] = device_conn
                
                # 登录设备
                if not await self._login_device(device_conn):
                    logger.error(f"设备登录失败: {device.device_name}")
                    return False

            device_conn = self.device_connections[scheme.camera_id]
            
            # 检查订阅是否已经存在，避免重复添加
            if scheme.id not in device_conn.schemes:
                # 根据事件类型启动相应的订阅
                for event_type in scheme.event_types:
                    if event_type == 'alarm':
                        await self._start_alarm_listen(device_conn, scheme)
                    elif event_type == 'smart':
                        await self._start_smart_listen(device_conn, scheme)
                    elif event_type == 'number_stat':
                        await self._start_number_stat_listen(device_conn, scheme)
                
                # 记录订阅关系 
                device_conn.schemes.append(scheme.id)
                self.scheme_connections[scheme.id] = scheme.camera_id
            else:
                logger.info(f"订阅 {scheme.id} 已存在，跳过重复启动")
          
            # 更新数据库状态
            scheme.started_at = datetime.now()
            scheme.updated_at = datetime.now()
            db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"启动订阅失败: {scheme.id}, 错误: {e}")
            return False
    
    async def _login_device(self, device_conn: DeviceConnection) -> bool:
        """登录设备"""
        try:
            stuInParam = NET_IN_LOGIN_WITH_HIGHLEVEL_SECURITY()
            stuInParam.dwSize = sizeof(NET_IN_LOGIN_WITH_HIGHLEVEL_SECURITY)
            stuInParam.szIP = device_conn.ip_address.encode()
            stuInParam.nPort = device_conn.port
            stuInParam.szUserName = device_conn.username.encode()
            stuInParam.szPassword = device_conn.password.encode()
            stuInParam.emSpecCap = EM_LOGIN_SPAC_CAP_TYPE.TCP
            stuInParam.pCapParam = None

            stuOutParam = NET_OUT_LOGIN_WITH_HIGHLEVEL_SECURITY()
            stuOutParam.dwSize = sizeof(NET_OUT_LOGIN_WITH_HIGHLEVEL_SECURITY)
            
            loginID, device_info, error_msg = self.sdk.LoginWithHighLevelSecurity(stuInParam, stuOutParam)
            
            if loginID != 0:
                device_conn.login_id = loginID
                device_conn.is_connected = True
                device_conn.last_heartbeat = datetime.now()
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"设备登录异常: {device_conn.device.device_name}, 错误: {e}")
            return False
    
    async def _start_alarm_listen(self, device_conn: DeviceConnection, scheme: SmartScheme):
        """启动报警事件订阅"""      
        try:
            result = self.sdk.StartListenEx(device_conn.login_id)
            if result:
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"启动报警事件订阅异常: {scheme.id}, 错误: {e}")
            return False
    
    async def _start_smart_listen(self, device_conn: DeviceConnection, scheme: SmartScheme):
        """启动智能事件订阅"""       
        try:
            nChannel = 0 # 默认通道
            dwAlarmType = EM_EVENT_IVS_TYPE.ALL
            bNeedPicFile = 0 # 是否订阅图片
            cbAnalyzerData = self.m_AnalyzerDataCallBack
            smartID = self.sdk.RealLoadPictureEx(device_conn.login_id, nChannel, dwAlarmType, bNeedPicFile, cbAnalyzerData)
            if smartID != 0 :
                device_conn.smart_id = smartID
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"启动智能事件订阅异常: {scheme.id}, 错误: {e}")
            return False

    async def _start_number_stat_listen(self, device_conn: DeviceConnection, scheme: SmartScheme):
        """启动智能事件订阅"""       
        try:
            # 启动视频统计摘要订阅
            inParam = NET_IN_ATTACH_VIDEOSTAT_SUM()
            inParam.dwSize = sizeof(NET_IN_ATTACH_VIDEOSTAT_SUM)
            inParam.nChannel = 0  # 默认通道
            inParam.cbVideoStatSum = self.m_VideoStatSumCallBack
            outParam = NET_OUT_ATTACH_VIDEOSTAT_SUM()
            outParam.dwSize = sizeof(NET_OUT_ATTACH_VIDEOSTAT_SUM)
            
            attachID = self.sdk.AttachVideoStatSummary(device_conn.login_id, inParam, outParam, 5000)
            if attachID != 0:
                device_conn.attach_id = attachID
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"启动智能事件订阅异常: {scheme.id}, 错误: {e}")
            return False
    
    async def start_scheme(self, scheme_id: str) -> bool:
        """启动订阅"""
        try:
            db = SessionLocal()
            try:
                scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
                if not scheme:
                    return False
                
                if scheme.status == 'running':
                    return True
                
                success = await self._start_scheme_internal(scheme, db)
                if success:
                    scheme.status = 'running'
                    db.commit()
                else:
                    scheme.status = 'error'
                    db.commit()
                
                return success
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"启动订阅异常: {scheme_id}, 错误: {e}")
            return False
    
    async def stop_scheme(self, scheme_id: str) -> bool:
        """停止订阅"""
        try:
            db = SessionLocal()
            try:
                scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
                if not scheme:
                    logger.error(f"订阅不存在: {scheme_id}")
                    return False
                
                # 从连接管理中移除
                device_id = self.scheme_connections.pop(scheme_id, None)
                if device_id and device_id in self.device_connections:
                    device_conn = self.device_connections[device_id]
                    if scheme_id in device_conn.schemes:
                        device_conn.schemes.remove(scheme_id)
                    
                    # 如果设备没有其他订阅，则登出设备
                    if not device_conn.schemes:
                        await self._logout_device(device_conn)
                        del self.device_connections[device_id]
                
                # 更新数据库状态
                scheme.status = 'stopped'
                scheme.stopped_at = datetime.now()
                scheme.updated_at = datetime.now()
                db.commit()
                
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"停止订阅异常: {scheme_id}, 错误: {e}")
            return False
    
    async def _logout_device(self, device_conn: DeviceConnection):
        """登出设备"""       
        try:
            if device_conn.login_id > 0:
                # 停止智能事件
                if device_conn.smart_id > 0:
                    self.sdk.StopLoadPic(device_conn.smart_id)
                # 停止人数统计订阅
                if device_conn.attach_id > 0:
                    self.sdk.DetachVideoStatSummary(device_conn.attach_id)
                self.sdk.StopListen(device_conn.login_id)
                # 登出
                result = self.sdk.Logout(device_conn.login_id)
                if result:
                    pass
                else:
                    pass
                
                device_conn.is_connected = False
                device_conn.login_id = 0
                device_conn.attach_id = 0
                device_conn.smart_id = 0
                
        except Exception as e:
            logger.error(f"设备登出异常: {device_conn.device_name}, 错误: {e}")
    
    async def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                await self._check_connections()
                await self._update_heartbeats()
                await asyncio.sleep(30)  # 每30秒检查一次
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(60)  # 异常时等待更长时间
    
    async def _check_connections(self):
        """检查连接状态"""
        for device_id, device_conn in list(self.device_connections.items()):
            if not device_conn.is_connected:
                # 尝试重新连接
                await self._reconnect_device(device_conn)
    
    async def _reconnect_device(self, device_conn: DeviceConnection):
        """重新连接设备"""
        try:         
            # 重新登录
            # if await self._login_device(device_conn):
            if device_conn.re_connected:
                # logger.info(f"重新启动该设备上的所有订阅: {device_conn.schemes}")
                
                # 重新启动该设备上的所有订阅的事件监听
                db = SessionLocal()
                try:
                    for scheme_id in device_conn.schemes:
                        scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
                        if scheme and scheme.status == 'running':
                            # 只重新启动事件监听，不重新创建订阅关系
                            result = await self._restart_event_listeners(device_conn, scheme)
                            if result:
                                device_conn.is_connected = True

                finally:
                    db.close()
                
                # logger.info(f"设备重新连接成功: {device_conn.device_name}")
            else:
                logger.error(f"设备重新连接失败: {device_conn.device_name}")
                
        except Exception as e:
            logger.error(f"重新连接设备异常: {device_conn.device_name}, 错误: {e}")
    
    async def _restart_event_listeners(self, device_conn: DeviceConnection, scheme: SmartScheme):
        """重新启动事件监听（不重新创建订阅关系）"""
        try:
            # logger.info(f"重新启动事件监听: 设备={device_conn.device_name}, 订阅={scheme.id}")
            
            # 确保订阅关系映射正确
            if scheme.id not in self.scheme_connections:
                self.scheme_connections[scheme.id] = device_conn.device_id
            
            # 根据事件类型重新启动相应的订阅
            for event_type in scheme.event_types:
                if event_type == 'alarm':
                    await self._start_alarm_listen(device_conn, scheme)
                elif event_type == 'smart':
                    await self._start_smart_listen(device_conn, scheme)
                elif event_type == 'number_stat':
                    await self._start_number_stat_listen(device_conn, scheme)
            
            # logger.info(f"事件监听重新启动成功: 订阅={scheme.id}")
            return True
            
        except Exception as e:
            logger.error(f"重新启动事件监听失败: {scheme.id}, 错误: {e}")
            return False
    
    async def _update_heartbeats(self):
        """更新心跳时间"""

        # 推送设备连接状态
        # cameraStatuses = []

        for device_conn in self.device_connections.values():

            if device_conn.is_connected:
                device_conn.last_heartbeat = datetime.now()
            #     cameraStatuses.append({
            #         'deviceId': device_conn.device_id,
            #         'online': True,
            #     })
            # else:
            #     cameraStatuses.append({
            #         'deviceId': device_conn.device_id,
            #         'online': False,
            #     })    

        # 增加推送设备连接状态
        # try:
        #     if data_pusher.push_configs:               
        #         data_pusher.push_data(
        #             data={'cameraStatuses': cameraStatuses},
        #             tags=["device_online_status"]
        #         )
        # except Exception as push_error:
        #     logger.error(f"数据推送失败: {push_error}")
    
    def _create_smart_event(self, scheme_id: str, event_type: str, title: str, 
                           description: str = None, priority: str = 'normal', 
                           event_data: Dict = None):
        """创建智能统计事件"""
        try:
            db = SessionLocal()
            try:
                event = SmartEvent(
                    scheme_id=scheme_id,
                    event_type=event_type,
                    title=title,
                    description=description,
                    priority=priority,
                    event_data=event_data,
                    status='pending',
                    timestamp=datetime.now()
                )
                
                db.add(event)
                db.commit()
                db.refresh(event)
                
                return event
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"创建智能事件失败: {e}")
            return None
    
    def AnalyzerDataCallBack(self, lAnalyzerHandle, dwAlarmType, pAlarmInfo, pBuffer, dwBufSize, dwUser, nSequence, reserved):
        try:
            try:
                smart_type = EM_EVENT_IVS_TYPE(dwAlarmType) # 报警类型
                print(f"智能类型: {hex(smart_type)}")
            except Exception as e:
                logger.error(f"解析智能事件类型异常: {e}")
                return

            if smart_type == EM_EVENT_IVS_TYPE.CROSSREGIONDETECTION:  # 警戒区事件                
                info = cast(pAlarmInfo, POINTER(DEV_EVENT_CROSSREGION_INFO)).contents
                if info.bEventAction == 0 or info.bEventAction == 1 or info.bEventAction == 2:
                    pass
                else:
                    return
            elif smart_type == EM_EVENT_IVS_TYPE.CROSSLINEDETECTION:  # 警戒线事件
                info = cast(pAlarmInfo, POINTER(DEV_EVENT_CROSSLINE_INFO)).contents
                if info.bEventAction == 0 or info.bEventAction == 1 or info.bEventAction == 2:
                    pass
                else:
                    return
            elif smart_type == EM_EVENT_IVS_TYPE.HEAT_IMAGING_TEMPER: # 热成像测温点温度异常报警事件
                info = cast(pAlarmInfo, POINTER(DEV_EVENT_HEAT_IMAGING_TEMPER_INFO)).contents
                if info.nAction == 0 or info.nAction == 1 or info.nAction == 2:
                    pass
                else:
                    return
            elif smart_type == EM_EVENT_IVS_TYPE.FIREDETECTION: # 火情报警事件
                info = cast(pAlarmInfo, POINTER(NET_A_DEV_EVENT_FIRE_INFO)).contents
                if info.nAction == 0 or info.nAction == 1 or info.nAction == 2:
                    pass
                else:
                    return
            elif smart_type == EM_EVENT_IVS_TYPE.SMOKEDETECTION: # 烟雾报警事件
                info = cast(pAlarmInfo, POINTER(NET_A_DEV_EVENT_SMOKE_INFO)).contents
                if info.nAction == 0 or info.nAction == 1 or info.nAction == 2:
                    pass
                else:
                    return
            else:
                return
            
            # 查找对应的订阅
            for device_conn in self.device_connections.values():
                if device_conn.smart_id == lAnalyzerHandle:
                    for scheme_id in device_conn.schemes:
                        event_data={}
                        if smart_type == EM_EVENT_IVS_TYPE.CROSSREGIONDETECTION:  # 警戒区事件
                            info = cast(pAlarmInfo, POINTER(DEV_EVENT_CROSSREGION_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'direction': '0:进入' if info.bDirection == 0 else '1:离开' if info.bDirection == 1 else '2:出现' if info.bDirection == 2 else '3:消失',
                                    'actionType': '0:出现' if info.bActionType == 0 else '1:消失' if info.bActionType == 1 else '2:在区域内' if info.bActionType == 2 else '3:穿越区域',
                                    # 'occurrenceCount': f'累计触发{info.nOccurrenceCount}次',
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_触发区域入侵',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'crossregion_alarm'
                                }
                        if smart_type == EM_EVENT_IVS_TYPE.CROSSLINEDETECTION:  # 警戒线事件
                            info = cast(pAlarmInfo, POINTER(DEV_EVENT_CROSSLINE_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'direction': '0:进入' if info.bDirection == 0 else '1:离开' if info.bDirection == 1 else '2:出现' if info.bDirection == 2 else '3:消失',
                                    # 'occurrenceCount': f'累计触发{info.nOccurrenceCount}次',
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_触发绊线入侵',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'crossline_alarm'
                                }
                        if smart_type == EM_EVENT_IVS_TYPE.HEAT_IMAGING_TEMPER:  # 测温规则报警事件
                            info = cast(pAlarmInfo, POINTER(NET_A_DEV_EVENT_FIREWARNING_INFO)).contents
                            if info.nAction == 0 or info.nAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_出现温度规则事件',
                                    'nAction': info.nAction,
                                    'event_type': 'temp_alarm_start'
                                } 
                        if smart_type == EM_EVENT_IVS_TYPE.FIREDETECTION:  # 火情报警事件
                            info = cast(pAlarmInfo, POINTER(NET_A_DEV_EVENT_FIRE_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_出现火情事件',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'fire_alarm_start'
                                } 
                        if smart_type == EM_EVENT_IVS_TYPE.SMOKEDETECTION:  # 烟雾报警事件
                            info = cast(pAlarmInfo, POINTER(NET_A_DEV_EVENT_SMOKE_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_出现烟雾报警事件',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'smoke_alarm_start'
                                }                               
                        # 推送事件
                        
                        try:
                            if data_pusher.push_configs:
                                data_pusher.push_data(
                                    data=event_data,
                                    tags=device_conn.push_tags
                            )
                        except Exception as push_error:
                            logger.error(f"数据推送失败: {push_error}")
                        
                        # 创建报警事件
                        smart_title, smart_description = self._build_title_description(
                            prefix="智能",
                            type_value=smart_type,
                            text_map=SMART_TYPE_TEXT_MAP,
                            # 保持原先 else 分支行为：默认按“温度规则”展示
                            default_text=("智能事件", "触发智能事件", ""),
                            device_conn=device_conn,
                        )
                        self._create_smart_event(
                            scheme_id=scheme_id,
                            event_type='smart',
                            title=smart_title,
                            description=smart_description,
                            priority='high',
                            event_data=event_data
                        )
                    break
        except Exception as e:
                logger.error(f"处理智能事件回调异常: {e}")

    # NetSDK回调函数
    def VideoStatSumCallBack(self, lAttachHandle, pBuf, dwBufLen, dwUser):
        """视频统计摘要回调函数"""
        try:            
            # 查找对应的订阅
            for device_conn in self.device_connections.values():
                if device_conn.attach_id == lAttachHandle:  # 根据attach_id查找对应的订阅
                    for scheme_id in device_conn.schemes:
                        # 正确转换结构体指针
                        info = cast(pBuf, POINTER(NET_VIDEOSTAT_SUMMARY)).contents
                        
                        # 检查报警间隔时间
                        if info.szRuleName != b'NumberStat' and device_conn.alarm_interval > 0:
                            # 检查间隔时间
                            if device_conn.last_alarm_time is None:
                                # 第一次报警，允许通过，并记录当前时间
                                device_conn.last_alarm_time = datetime.now()
                            else:
                                time_diff = datetime.now() - device_conn.last_alarm_time
                                if time_diff.total_seconds() < device_conn.alarm_interval:
                                    return
                                else:
                                    device_conn.last_alarm_time = datetime.now()                                                                                    
                       
                        event_data={
                                'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                'deviceId': device_conn.device_id,
                                'enteredCount': info.stuEnteredSubtotal.nToday,
                                'exitedCount': info.stuExitedSubtotal.nToday,
                                'stayingCount': info.nInsidePeopleNum,
                                'passedCount': info.stuPassedSubtotal.nToday,
                                'recordTime': datetime.now().isoformat() + '+08:00', #System.DateTimeOffset格式，明确指定北京时间时区
                                'event_description': f'事件类型={info.szRuleName}, 区域内人数={info.nInsidePeopleNum}, 今日进入={info.stuEnteredSubtotal.nToday}, 今日离开={info.stuExitedSubtotal.nToday}, 今日通过={info.stuPassedSubtotal.nToday}'
                            }

                        # 调用现有的数据推送功能
                        try:
                            if data_pusher.push_configs:
                                data_pusher.push_data(
                                    data=event_data,
                                    tags=device_conn.push_tags
                                )
                        except Exception as push_error:
                            logger.error(f"数据推送失败: {push_error}")
                        
                        # 创建智能事件
                        self._create_smart_event(
                            scheme_id=scheme_id,
                            event_type='number_stat',
                            title=f'客流(区域人数)' if info.szRuleName == b'ManNumDetection' else f'客流(人流统计)' if info.szRuleName == b'NumberStat' else "未知",
                            description=f'区域内人数={info.nInsidePeopleNum}, 今日进入={info.stuEnteredSubtotal.nToday}, 今日离开={info.stuExitedSubtotal.nToday}',
                            priority='normal',
                            event_data=event_data
                        )
                    break
                    
        except Exception as e:
            logger.error(f"处理视频统计摘要回调异常: {e}")

    def MessCallBackEx1(self, lCommand, lLoginID, pBuf, dwBufLen, pchDVRIP, nDVRPort, bAlarmAckFlag, nEventID, dwUser):
        """消息回调函数"""
        try:       
            # 报警类型转换
            try:
                alarm_type = SDK_ALARM_TYPE(lCommand) # 报警类型
                #需要转换成16进制打印alarm_type
                alarm_type_hex = hex(alarm_type)
                print(f"报警类型: {alarm_type_hex}")
            except (ValueError, TypeError):
                return          
            
            if alarm_type == SDK_ALARM_TYPE.EVENT_CROSSREGION_DETECTION:  # 警戒区事件                
                info = cast(pBuf, POINTER(DEV_EVENT_CROSSREGION_INFO)).contents
                if info.bEventAction == 0 or info.bEventAction == 1 or info.bEventAction == 2:
                    pass
                else:
                    return
               
            elif alarm_type == SDK_ALARM_TYPE.EVENT_CROSSLINE_DETECTION:  # 警戒线事件
                info = cast(pBuf, POINTER(DEV_EVENT_CROSSLINE_INFO)).contents
                if info.bEventAction == 0 or info.bEventAction == 1 or info.bEventAction == 2:
                    pass
                else:
                    return
              
            elif alarm_type == SDK_ALARM_TYPE.ALARM_FIREWARNING_INFO:  # 火情报警事件
                info = cast(pBuf, POINTER(NET_A_DEV_EVENT_FIREWARNING_INFO)).contents
                if info.nAction == 0 or info.nAction == 1 or info.nAction == 2:
                    pass
                else:
                    return
            else:
                return
            
            # 查找对应的订阅
            for device_conn in self.device_connections.values():
                if device_conn.login_id == lLoginID:
                    for scheme_id in device_conn.schemes:
                        event_data={}
                        if alarm_type == SDK_ALARM_TYPE.EVENT_CROSSREGION_DETECTION:  # 警戒区事件
                            info = cast(pBuf, POINTER(DEV_EVENT_CROSSREGION_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'direction': '0:进入' if info.bDirection == 0 else '1:离开' if info.bDirection == 1 else '2:出现' if info.bDirection == 2 else '3:消失',
                                    'actionType': '0:出现' if info.bActionType == 0 else '1:消失' if info.bActionType == 1 else '2:在区域内' if info.bActionType == 2 else '3:穿越区域',
                                    # 'occurrenceCount': f'累计触发{info.nOccurrenceCount}次',
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_触发区域入侵',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'crossregion_alarm'
                                }
                        if alarm_type == SDK_ALARM_TYPE.EVENT_CROSSLINE_DETECTION:  # 警戒线事件
                            info = cast(pBuf, POINTER(DEV_EVENT_CROSSLINE_INFO)).contents
                            if info.bEventAction == 0 or info.bEventAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'direction': '0:进入' if info.bDirection == 0 else '1:离开' if info.bDirection == 1 else '2:出现' if info.bDirection == 2 else '3:消失',
                                    # 'occurrenceCount': f'累计触发{info.nOccurrenceCount}次',
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_触发绊线入侵',
                                    'bEventAction': info.bEventAction,
                                    'event_type': 'crossline_alarm'
                                }

                        if alarm_type == SDK_ALARM_TYPE.ALARM_FIREWARNING_INFO:  # 火情报警事件
                            info = cast(pBuf, POINTER(NET_A_DEV_EVENT_FIREWARNING_INFO)).contents
                            if info.nAction == 0 or info.nAction == 1:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_出现火情事件',
                                    'nAction': info.nAction,
                                    'event_type': 'fire_alarm_start'
                                }
                            elif info.nAction == 2:
                                event_data={
                                    'cameraInfo': device_conn.device_name + "_" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'{device_conn.device_name}_{device_conn.ip_address}_火情消除',
                                    'nAction': info.nAction,
                                    'event_type': 'fire_alarm_end'
                                }
                        # 推送事件
                        
                        try:
                            if data_pusher.push_configs:
                                data_pusher.push_data(
                                    data=event_data,
                                    tags=device_conn.push_tags
                            )
                        except Exception as push_error:
                            logger.error(f"数据推送失败: {push_error}")
                        
                        # 创建报警事件
                        alarm_title, alarm_description = self._build_title_description(
                            prefix="报警",
                            type_value=alarm_type,
                            text_map=ALARM_TYPE_TEXT_MAP,
                            # 保持原先 else 分支行为：默认按“火情报警”展示
                            default_text=("报警事件", "触发报警事件", ""),
                            device_conn=device_conn,
                        )
                        self._create_smart_event(
                            scheme_id=scheme_id,
                            event_type='alarm',
                            title=alarm_title,
                            description=alarm_description,
                            priority='high',
                            event_data=event_data
                        )
                    break
                    
        except Exception as e:
            logger.error(f"处理报警回调异常: {e}")
    
    def DisConnectCallBack(self, lLoginID, pchDVRIP, nDVRPort, dwUser):
        """断开连接回调函数"""
        try:  
            # 查找对应的设备
            for device_conn in self.device_connections.values():
                if device_conn.login_id == lLoginID:
                    device_conn.is_connected = False
                    device_conn.re_connected = False
                    if device_conn.event_types is not None and 'system_log' in device_conn.event_types:
                
                        # 为所有相关订阅创建系统日志事件
                        for scheme_id in device_conn.schemes:
                            self._create_smart_event(
                                scheme_id=scheme_id,
                                event_type='system_log',
                                title='设备断开连接',
                                description=f'设备 {device_conn.device_name} + {device_conn.ip_address} 连接断开',
                                priority='high',
                                event_data={
                                    'cameraInfo': device_conn.device_name + ":" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'设备 {device_conn.device_name} + {device_conn.ip_address} 连接断开'
                                }
                            )
                        break
                    
        except Exception as e:
            logger.error(f"处理断开连接回调异常: {e}")
    
    def ReConnectCallBack(self, lLoginID, pchDVRIP, nDVRPort, dwUser):
        """重新连接回调函数"""
        try:  
            print(f"重新连接回调函数: {lLoginID}")
            # 查找对应的设备
            for device_conn in self.device_connections.values():
                if device_conn.login_id == lLoginID:
                    device_conn.re_connected = True
                    # device_conn.is_connected = True
                    # device_conn.last_heartbeat = datetime.now()
                    
                    # 重新启动该设备上的所有订阅
                    # db = SessionLocal()
                    # try:
                    #     for scheme_id in device_conn.schemes:
                    #         scheme = db.query(SmartScheme).filter(SmartScheme.id == scheme_id).first()
                    #         if scheme and scheme.status == 'running':
                    #             await self._restart_event_listeners(device_conn, scheme)
                    # finally:
                    #     db.close()

                    if device_conn.event_types is not None and 'system_log' in device_conn.event_types:
                        # 为所有相关订阅创建系统日志事件
                        for scheme_id in device_conn.schemes:
                            self._create_smart_event(
                                scheme_id=scheme_id,
                                event_type='system_log',
                                title='设备重新连接',
                                description=f'设备 {device_conn.device_name} + {device_conn.ip_address} 重新连接成功',
                                priority='normal',
                                event_data={
                                    'cameraInfo': device_conn.device_name + ":" + device_conn.ip_address,
                                    'deviceId': device_conn.device_id,
                                    'recordTime': datetime.now().isoformat() + '+08:00',
                                    'event_description': f'设备 {device_conn.device_name} + {device_conn.ip_address} 重新连接成功'
                                }
                            )
                        break
                    
        except Exception as e:
            logger.error(f"处理重新连接回调异常: {e}")

    async def shutdown(self):
        """关闭管理器"""
        try:
            self.running = False

            for device_conn in list(self.device_connections.values()):
                try:
                    await asyncio.wait_for(self._logout_device(device_conn), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("设备 %s 登出超时，跳过", device_conn.device_name)

            if NETSDK_AVAILABLE and self.sdk:
                await asyncio.to_thread(self.sdk.Cleanup)

            self.device_connections.clear()
            self.scheme_connections.clear()
            logger.info("事件订阅管理器已关闭")
        except Exception as e:
            logger.error(f"关闭事件订阅管理器失败: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        status = {
            'running': self.running,
            'device_connections': len(self.device_connections),
            'scheme_connections': len(self.scheme_connections),
            'devices': []
        }
        
        for device_id, device_conn in self.device_connections.items():
            status['devices'].append({
                'device_id': device_id,
                'device_name': device_conn.device_name,
                'is_connected': device_conn.is_connected,
                'login_id': device_conn.login_id,
                'scheme_count': len(device_conn.schemes),
                'last_heartbeat': device_conn.last_heartbeat.isoformat() if device_conn.last_heartbeat else None
            })
        
        return status
      
# 全局实例
smart_schemer = SmartSchemer()
