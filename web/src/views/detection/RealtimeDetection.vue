<template>
  <div class="detection-container">
    <div class="page-header">
      <h2>实时检测</h2>
      <div class="header-controls">
        <el-select
          v-model="selectedConfig"
          placeholder="选择检测配置"
          class="config-select"
          filterable
        >
          <el-option
            v-for="config in configs"
            :key="config.config_id"
            :label="getConfigOptionLabel(config)"
            :value="config.config_id"
          />
        </el-select>
        <el-button-group>
          <el-button
            type="primary"
            :disabled="!selectedConfig"
            @click="toggleConnection"
          >
            {{ isConnected ? '断开连接' : '连接' }}
          </el-button>
          <el-button
            type="info"
            :disabled="!selectedConfig"
            @click="showConfigInfo"
          >
            配置信息
          </el-button>
        </el-button-group>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="16">
        <el-card class="video-card">
          <template #header>
            <div class="video-header">
              <div class="video-status">
                <el-tag :type="isConnected ? 'success' : 'info'" effect="dark">
                  {{ isConnected ? '已连接' : '未连接' }}
                </el-tag>
                <span class="video-info" v-if="isConnected">
                  检测到: {{ detectedCount }} 个目标
                </span>
              </div>
              <div class="video-controls">
                <el-button-group>
                  <el-button 
                    type="primary" 
                    icon="FullScreen"
                    @click="toggleFullscreen"
                  >
                    全屏
                  </el-button>
                  <el-button 
                    type="primary"
                    icon="Camera"
                    @click="takeSnapshot"
                    :disabled="!isConnected"
                  >
                    截图
                  </el-button>
                </el-button-group>
              </div>
            </div>
          </template>
          <div class="video-container" ref="videoContainer">
            <div v-if="!isConnected" class="placeholder">
              <el-icon :size="64"><VideoCamera /></el-icon>
              <p>选择检测配置并连接</p>
            </div>
            <div v-else-if="connectionError" class="error-container">
              <el-icon :size="64"><CircleClose /></el-icon>
              <p>{{ connectionError }}</p>
              <el-button type="primary" @click="retryConnection">重试连接</el-button>
            </div>
            <div v-else class="video-wrapper">
              <img 
                v-if="currentFrame" 
                :src="currentFrame" 
                class="video-frame" 
                ref="videoFrame"
              />
              <div v-else class="no-data-placeholder">
                <el-icon :size="32"><VideoPlay /></el-icon>
                <p>等待视频数据...</p>
              </div>
              <div class="loading-overlay" v-if="isConnecting">
                <el-icon class="rotating" :size="32"><Loading /></el-icon>
                <p>正在连接...</p>
              </div>
              <div class="connection-info" v-if="isConnected && !isConnecting">
                <span>{{ lastDetectionTime }} - {{ detectedCount }} 个目标</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="detection-info">
          <template #header>
            <div class="card-header">
              <span>检测日志</span>
              <div class="header-actions">
                <el-button-group>
                  <el-button 
                    type="primary" 
                    link 
                    icon="Delete"
                    @click="clearLogs"
                  >
                    清空日志
                  </el-button>
                </el-button-group>
              </div>
            </div>
          </template>
          
          <div class="info-content">
            <div class="detection-stats">
              <div class="stat-group">
                <div class="stat-item">
                  <label>检测配置</label>
                  <span>{{ selectedConfigName }}</span>
                </div>
                <div class="stat-item">
                  <label>目标数量</label>
                  <span class="highlight">{{ detectedCount }}</span>
                </div>
              </div>
              <div class="stat-group">
                <div class="stat-item">
                  <label>连接时长</label>
                  <span>{{ connectionTime }}</span>
                </div>
                <div class="stat-item">
                  <label>检测时间</label>
                  <span>{{ lastDetectionTime }}</span>
                </div>
              </div>
            </div>

            <div class="detection-list">
              <div class="list-header">
                <h4>检测记录</h4>
              </div>
              
              <div class="records-container" ref="recordsContainer">
                <el-scrollbar ref="scrollbar" :always="true">
                  <el-timeline>
                    <el-timeline-item
                      v-for="(log, index) in logs"
                      :key="index"
                      :timestamp="log.time"
                      :type="log.type"
                    >
                      <div class="record-content">
                        <div class="record-header">
                          <el-tag 
                            :type="getLogTagType(log.type)"
                            size="small"
                            effect="plain"
                          >
                            {{ getLogTypeText(log.type) }}
                          </el-tag>
                          <span v-if="log.objectCount" class="object-count">
                            检测到 {{ log.objectCount }} 个目标
                          </span>
                        </div>
                        <p class="record-message">{{ log.message }}</p>
                        <div v-if="log.details && log.details.length > 0" class="record-details">
                          <el-collapse>
                            <el-collapse-item>
                              <template #title>
                                <el-icon><InfoFilled /></el-icon>
                                检测详情
                              </template>
                              <div class="details-content">
                                <div v-for="(det, i) in log.details" :key="i" class="detection-item">
                                  <span class="class-name">{{ det.class_name }}</span>
                                  <span class="confidence">置信度: {{ (det.confidence * 100).toFixed(1) }}%</span>
                                </div>
                              </div>
                            </el-collapse-item>
                          </el-collapse>
                        </div>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
                </el-scrollbar>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 配置信息对话框 -->
    <el-dialog
      v-model="configInfoDialogVisible"
      title="检测配置信息"
      width="500px"
    >
      <div v-if="selectedConfigDetails">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="配置ID">{{ selectedConfigDetails.config_id }}</el-descriptions-item>
          <el-descriptions-item label="设备/分组">{{ getConfigDeviceLabel(selectedConfigDetails) }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ getModelTypeName(selectedConfigDetails.models_type) }} - {{ selectedConfigDetails.models_name }}</el-descriptions-item>
          <el-descriptions-item label="检测方式">
            {{ getFrequencyLabel(selectedConfigDetails.frequency) }}
            <span v-if="getFrameIntervalText(selectedConfigDetails)">
              · {{ getFrameIntervalText(selectedConfigDetails) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="灵敏度">{{ (selectedConfigDetails.sensitivity * 100).toFixed(0) }}%</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedConfigDetails.enabled ? 'success' : 'info'">
              {{ selectedConfigDetails.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { VideoCamera, CircleClose, Loading, InfoFilled, Camera, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { detectionConfigApi } from '@/api/detection';
import { startDetection, stopDetection, getDetectionStatus } from '@/api/detection_server';

// 响应式数据
const selectedConfig = ref('')
const configs = ref([])
const isConnected = ref(false)
const isConnecting = ref(false)
const connectionError = ref(null)
const detectedCount = ref(0)
const currentFrame = ref(null)
const logs = ref([])
const connectionStartTime = ref(null)
const connectionTime = ref('00:00:00')
const lastDetectionTime = ref('-')
const configInfoDialogVisible = ref(false)
const selectedConfigDetails = ref(null)

// DOM引用
const videoContainer = ref(null)
const videoFrame = ref(null)
const scrollbar = ref(null)

// WebSocket连接
let ws = null
let timeUpdateInterval = null

// 计算属性
const selectedConfigName = computed(() => {
  const config = configs.value.find(c => c.config_id === selectedConfig.value)
  return config ? `${config.device_name} - ${config.model_name}` : '未选择'
})

// 检测方式标签
const getFrequencyLabel = (frequency) => {
  const map = {
    realtime: '实时检测',
    manual: '抽帧检测',
    scheduled: '定时检测'
  }
  return map[frequency] || frequency || '未知'
}

const getFrameIntervalText = (config) => {
  if (!config || config.frequency !== 'manual') return ''
  const interval = config.schedule_config?.runtime?.frame_interval
  return interval ? `${interval}秒/帧` : ''
}

const getConfigDeviceLabel = (config) => {
  if (!config.device_id || config.config_mode === 'group') {
    const groupName = config.group_name || config.group_id || '未命名分组'
    return `分组-${groupName}`
  }
  return `${config.device_id}-${config.device_name || config.device_id}`
}

const getConfigOptionLabel = (config) => {
  const base = `${getConfigDeviceLabel(config)} - ${config.model_name}`
  const mode = config.config_mode === 'group'
    ? '分组轮询'
    : getFrequencyLabel(config.frequency)
  const interval = config.frequency === 'manual' && config.schedule_config?.runtime?.frame_interval
    ? ` ${config.schedule_config.runtime.frame_interval}秒/帧`
    : ''
  return `${base} (${mode}${interval})`
}

// 加载检测配置（实时 + 抽帧）
const loadConfigurations = async () => {
  try {
    const response = await detectionConfigApi.getConfigs({ skip: 0, limit: 500 })
    configs.value = response.data.data.map(config => ({
      config_id: config.config_id,
      config_mode: config.config_mode || 'device',
      device_id: config.device_id,
      group_id: config.group_id,
      group_name: config.group_name,
      device_name: config.device_name || config.group_name || config.device_id,
      model_name: config.models_name || '默认模型',
      models_type: config.models_type,
      models_name: config.models_name,
      frequency: config.frequency,
      schedule_config: config.schedule_config,
      sensitivity: config.sensitivity,
      enabled: config.enabled
    }))
  } catch (error) {
    ElMessage.error('加载检测配置失败')
  }
}

// 切换WebSocket连接
const toggleConnection = async () => {
  if (isConnected.value) {
    disconnectWebSocket()
  } else {
    connectWebSocket()
  }
}

// 断开WebSocket连接
const disconnectWebSocket = () => {
  if (ws) {
    ws.close(); // 关闭WebSocket连接
    ws = null; // 清空WebSocket实例
    handleDisconnection('手动断开连接'); // 处理断开连接的逻辑
  }
}

// 连接WebSocket逻辑
const connectWebSocket = () => {
  if (!selectedConfig.value) {
    ElMessage.warning('请先选择检测配置')
    return
  }
  
  isConnecting.value = true
  connectionError.value = null
  
  // 创建WebSocket连接
  const wsUrl = `ws://${window.location.host}/ws/detection/preview/${selectedConfig.value}`
  ws = new WebSocket(wsUrl)
  
  // 添加超时处理
  const connectionTimeout = setTimeout(() => {
    if (ws && ws.readyState !== WebSocket.OPEN) {
      ws.close()
      handleDisconnection('连接超时，请检查服务器状态')
    }
  }, 10000) // 10秒超时
  
  ws.onopen = async () => {
    try {

      clearTimeout(connectionTimeout)
      addLog('info', '已连接到WebSocket服务器，等待视频数据...')
      // 启动检测任务
      await startDetectionTask()
      
      // 添加无数据超时检测
      startDataTimeoutMonitor()
    } catch (error) {
      clearTimeout(connectionTimeout)
      handleDisconnection(`启动检测任务失败: ${error.message}`)
    }
  }
  
  ws.onclose = (event) => {
    clearTimeout(connectionTimeout)
    handleDisconnection(event.wasClean ? '连接已关闭' : '连接异常关闭')
  }
  
  ws.onerror = (error) => {
    clearTimeout(connectionTimeout)
    // console.error('WebSocket错误:', error)
    handleDisconnection('WebSocket连接出错')
  }
  
  ws.onmessage = (event) => {
    try {
      // 添加调试日志
      // console.log('收到WebSocket消息，数据长度:', event.data.length);
      
      const data = JSON.parse(event.data);
      // console.log('解析WebSocket消息:', data.hasOwnProperty('image') ? '包含图像数据' : '不包含图像数据');
      
      // 重置无数据超时计时器
      resetDataTimeout()
      
      // 处理不同类型的消息
      if (data.status === 'error') {
        // 处理错误消息
        addLog('danger', data.message || '服务器返回错误')
        return
      } else if (data.status === 'success' && data.message) {
        // 处理成功消息
        addLog('success', data.message)
        if (!isConnected.value) {
          isConnected.value = true
          isConnecting.value = false
          connectionStartTime.value = new Date()
          timeUpdateInterval = setInterval(updateConnectionTime, 1000)
        }
        return
      }
      
      // 如果是检测数据（图像和检测结果）
      if (data.image) {
        // 如果这是第一帧数据，标记为已连接
        if (!isConnected.value) {
          isConnected.value = true
          isConnecting.value = false
          connectionStartTime.value = new Date()
          timeUpdateInterval = setInterval(updateConnectionTime, 1000)
          addLog('success', '已接收到视频数据流')
        }
        
        // 更新最后检测时间
        lastDetectionTime.value = new Date().toLocaleTimeString()
        
        // 将base64图像数据显示在页面上
        currentFrame.value = `data:image/jpeg;base64,${data.image}`
        
        // 更新检测到的目标数量
        if (data.detections) {
          const newCount = data.detections.length
          
          // 只有当数量变化时才记录
          if (newCount !== detectedCount.value) {
            detectedCount.value = newCount
            
            if (newCount > 0) {
              addLog('success', `检测到 ${newCount} 个目标`, data.detections, newCount)
            } else if (detectedCount.value > 0) {
              // 从有到无的变化也记录
              addLog('info', '未检测到目标')
            }
          }
          
          // 更新数量
          detectedCount.value = newCount
        }
      }
    } catch (error) {
      // console.error('处理WebSocket消息失败:', error);
    }
  }
}

// 启动检测任务
const startDetectionTask = async () => {
  try {
    // 检查任务状态
    const statusResponse = await getDetectionStatus();
    const tasks = statusResponse.tasks || {}
    
    // 如果任务已在运行，直接返回
    if (tasks[selectedConfig.value] && tasks[selectedConfig.value].is_running) {
      addLog('info', '检测任务已在运行')
      return
    }
    
    // 启动任务
    const response = await startDetection(selectedConfig.value)
    
    if (response.status === 'success') {
      addLog('success', '检测任务已启动')
    } else {
      throw new Error(response.message || '启动任务失败')
    }
  } catch (error) {
    // console.error('启动检测任务失败:', error)
    throw error
  }
}

// 无数据超时监控
let dataTimeoutId = null
const DATA_TIMEOUT = 60000 // 15秒无数据视为连接问题

const startDataTimeoutMonitor = () => {
  resetDataTimeout()
}

const resetDataTimeout = () => {
  if (dataTimeoutId) {
    clearTimeout(dataTimeoutId)
  }
  
  dataTimeoutId = setTimeout(() => {
    if (isConnected.value) {
      addLog('warning', '长时间未收到检测数据，可能存在连接问题')
      // 不断开连接，但显示警告
      ElMessage.warning('长时间未收到检测数据，可能是后端服务出现问题')
    }
  }, DATA_TIMEOUT)
}

// 处理断开连接 - 添加自动重连机制
let reconnectCount = 0
const MAX_RECONNECT = 3
let reconnectTimeoutId = null

const handleDisconnection = (errorMessage) => {
  isConnected.value = false
  isConnecting.value = false
  
  if (dataTimeoutId) {
    clearTimeout(dataTimeoutId)
    dataTimeoutId = null
  }
  
  if (timeUpdateInterval) {
    clearInterval(timeUpdateInterval)
    timeUpdateInterval = null
  }
  
  connectionStartTime.value = null
  
  // 如果是手动断开，不显示错误
  if (errorMessage === '手动断开连接') {
    connectionError.value = null
    addLog('info', '已断开连接')
    reconnectCount = 0
    return
  }
  
  // 显示错误信息
  connectionError.value = errorMessage
  if (errorMessage) {
    addLog('danger', errorMessage)
  } else {
    addLog('info', '连接已断开')
  }
}

// 更新连接时间
const updateConnectionTime = () => {
  if (!connectionStartTime.value) return
  
  const now = new Date()
  const diff = now - connectionStartTime.value
  const hours = Math.floor(diff / 3600000)
  const minutes = Math.floor((diff % 3600000) / 60000)
  const seconds = Math.floor((diff % 60000) / 1000)
  
  connectionTime.value = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
}

// 添加日志
const addLog = (type, message, details = null, objectCount = null) => {
  logs.value.unshift({
    time: new Date().toLocaleTimeString(),
    type,
    message,
    details,
    objectCount
  })
  
  // 保持日志数量在合理范围内
  if (logs.value.length > 100) {
    logs.value = logs.value.slice(0, 100)
  }
}

// 获取日志标签类型
const getLogTagType = (type) => {
  const typeMap = {
    success: 'success',
    warning: 'warning',
    danger: 'danger',
    info: 'info'
  }
  return typeMap[type]
}

// 获取日志类型文本
const getLogTypeText = (type) => {
  const textMap = {
    success: '成功',
    warning: '警告',
    danger: '错误',
    info: '信息'
  }
  return textMap[type]
}

// 获取模型类型名称
const getModelTypeName = (type) => {
  const typeMap = {
    'object_detection': '目标检测',
    'smart_behavior': '智能行为',
    'smart_person': '人员场景',
    'smart_counting': '智能人数统计',
    'segmentation': '图像分割',
    'keypoint': '关键点检测',
    'pose': '姿态估计',
    'face': '人脸识别',
    'other': '其他类型'
  }
  return typeMap[type] || type
}

// 全屏控制
const toggleFullscreen = async () => {
  try {
    if (!document.fullscreenElement) {
      await videoContainer.value.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  } catch (error) {
    ElMessage.error('切换全屏失败')
  }
}

// 截图功能
const takeSnapshot = () => {
  if (!isConnected.value || !currentFrame.value) {
    ElMessage.warning('无可用的视频帧')
    return
  }
  
  try {
    const link = document.createElement('a')
    link.download = `detection_snapshot_${new Date().toISOString().replace(/[:.]/g, '-')}.jpg`
    link.href = currentFrame.value
    link.click()
    
    addLog('success', '截图已保存')
  } catch (error) {
    ElMessage.error('截图失败')
  }
}

// 清空日志
const clearLogs = () => {
  ElMessageBox.confirm(
    '确定要清空日志吗？',
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    logs.value = []
    ElMessage.success('日志已清空')
  }).catch(() => {})
}

// 重试连接
const retryConnection = () => {
  connectionError.value = null
  reconnectCount = 0
  if (reconnectTimeoutId) {
    clearTimeout(reconnectTimeoutId)
    reconnectTimeoutId = null
  }
  connectWebSocket()
}

// 显示配置信息
const showConfigInfo = async () => {
  if (!selectedConfig.value) {
    ElMessage.warning('请先选择检测配置')
    return
  }
  
  try {
    // 替换为实际的API端点
    const response = await detectionConfigApi.getConfig(selectedConfig.value);
    selectedConfigDetails.value = response.data
    configInfoDialogVisible.value = true
  } catch (error) {
    ElMessage.error('获取配置信息失败')
  }
}

// 生命周期钩子
onMounted(() => {
  loadConfigurations()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  
  if (timeUpdateInterval) {
    clearInterval(timeUpdateInterval)
  }
  
  if (dataTimeoutId) {
    clearTimeout(dataTimeoutId)
  }
  
  if (reconnectTimeoutId) {
    clearTimeout(reconnectTimeoutId)
  }
  
  // 如果有活跃的连接，尝试停止检测任务
  if (selectedConfig.value && isConnected.value) {
    disconnectWebSocket()
  }
})

// 停止检测任务
const stopDetectionTask = async () => {
  try {
    await stopDetection(selectedConfig.value)
    // console.log('检测任务已停止')
  } catch (error) {
    // console.error('停止检测任务失败:', error)
    throw error
  }
}

// 监听配置变化
watch(selectedConfig, () => {
  if (isConnected.value) {
    disconnectWebSocket()
  }
})
</script>

<style scoped>
.detection-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}


.header-controls {
  display: flex;
  gap: 16px;
  align-items: center;
}

.config-select {
  width: 240px;
}

.video-card {
  margin-bottom: 20px;
}

.video-container {
  width: 100%;
  height: 600px;
  background-color: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.placeholder {
  text-align: center;
  color: #606266;
}

.error-container {
  text-align: center;
  color: #f56c6c;
}

.video-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
}

.video-frame {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: white;
}

.rotating {
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.detection-info {
  height: 700px;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detection-stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
  margin-bottom: 16px;
}

.stat-group {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background-color: #ffffff;
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.stat-item label {
  color: #64748b;
  font-size: 13px;
}

.stat-item span {
  color: #1e293b;
  font-size: 16px;
  font-weight: 500;
}

.stat-item span.highlight {
  color: #409EFF;
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.detection-list {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 0 8px;
}

.list-header h4 {
  margin: 0;
}

.records-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: 400px; /* 设置最大高度 */
}

.record-content {
  padding: 8px;
  background-color: #f8fafc;
  border-radius: 6px;
}

.record-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.object-count {
  font-size: 13px;
  color: #409EFF;
  font-weight: 500;
}

.record-message {
  margin: 0;
  color: #2c3e50;
  font-size: 14px;
  line-height: 1.4;
}

.record-details {
  margin-top: 8px;
}

.details-content {
  padding: 8px;
  background-color: #ffffff;
  border-radius: 4px;
}

.detection-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}

.detection-item:last-child {
  border-bottom: none;
}

.class-name {
  font-weight: 500;
  color: #409EFF;
}

.confidence {
  color: #909399;
  font-size: 13px;
}

.video-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.video-info {
  font-size: 14px;
  color: #409EFF;
}

.detection-info {
  font-size: 14px;
  color: #409EFF;
}

.info-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 响应式布局 */
@media (max-width: 1400px) {
  .stat-group {
    grid-template-columns: 1fr;
  }
}
</style> 
 