<template>
  <div class="detection-container">
    <div class="page-header">
      <div class="header-actions">
        <el-select
          v-model="selectedModel"
          placeholder="选择验证模型"
          class="model-select"
          :disabled="isDetecting"
          :loading="loadingModels"
        >
        <el-option
            v-for="model in models"
            :key="model.models_id"
            :label="`${model.models_name} (${getModelTypeName(model.models_type)})`"
            :value="model.models_id"
          >
            <div class="model-option">
              <span>{{ model.models_name }}</span>
              <el-tag size="small" effect="plain">{{ getModelTypeName(model.models_type) }}</el-tag>
            </div>
          </el-option>
          <template #empty>
            <div class="empty-model-list">
              <p v-if="loadingModels">加载模型中...</p>
              <p v-else>暂无可用模型，请先上传并激活模型</p>
            </div>
          </template>
        </el-select>
        <el-upload
          class="upload-video"
          action="#"
          :auto-upload="false"
          :show-file-list="false"
          accept=".mp4,.avi,.mkv,.mov,.wmv"
          :on-change="handleVideoChange"
          :before-upload="() => false"
        >
          <el-button type="primary">选择视频</el-button>
        </el-upload>
        <el-button 
          type="success" 
          :disabled="!videoFile || (!selectedModel && !isDetecting)" 
          @click="toggleDetection"
        >
          {{ isDetecting ? '停止验证' : '开始验证' }}
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="16">
        <el-card class="video-card">
          <div class="video-container">
            <video 
              ref="videoRef" 
              class="video-player" 
              controls
              :class="{ 'hidden': !videoFile }"
            ></video>
            <div v-if="!videoFile" class="placeholder">
              <el-icon :size="64"><VideoPlay /></el-icon>
              <p>选择视频文件开始验证</p>
            </div>
            <canvas v-show="videoFile" ref="canvasRef" class="detection-canvas"></canvas>
          </div>
          
          <div v-if="videoFile" class="video-controls">
            <div class="progress-info">
              <span>验证进度：{{ progress }}%</span>
              <span>剩余时间：{{ remainingTime }}</span>
            </div>
            <el-progress 
              :percentage="progress" 
              :status="isDetecting ? 'success' : ''"
            />
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="detection-info">
          <template #header>
            <div class="card-header">
              <span>验证信息</span>
              <el-button-group>
                <el-button type="primary" link>导出结果</el-button>
                <el-button type="primary" link>导出视频</el-button>
              </el-button-group>
            </div>
          </template>
          
          <div class="detection-content">
            <div class="video-info" v-if="videoFile">
              <div class="info-item">
                <label>文件名：</label>
                <span class="info-value">{{ videoFile.name }}</span>
              </div>
              <div class="info-item">
                <label>时长：</label>
                <span>{{ duration }}</span>
              </div>
              <div class="info-item">
                <label>大小：</label>
                <span>{{ fileSize }}</span>
              </div>
            </div>

            <div class="detection-stats">
              <div class="stat-item">
                <label>验证状态：</label>
                <el-tag :type="isDetecting ? 'success' : 'info'">
                  {{ isDetecting ? '验证中' : '未开始' }}
                </el-tag>
              </div>
              <div class="stat-item">
                <label>目标数量：</label>
                <span>{{ detectedCount }}</span>
              </div>
              <div v-if="modelDetails" class="stat-item">
                <label>当前模型：</label>
                <el-tooltip :content="modelDetails.description || '无描述'" placement="top">
                  <el-tag type="primary">{{ modelDetails.models_name }}</el-tag>
                </el-tooltip>
              </div>
              <div v-if="modelDetails" class="stat-item">
                <label>模型类型：</label>
                <span>{{ getModelTypeName(modelDetails.models_type) }}</span>
              </div>
              <div v-if="modelDetails" class="stat-item">
                <label>模型格式：</label>
                <span>{{ modelDetails.format.toUpperCase() }}</span>
              </div>
            </div>
            
            <div v-if="modelDetails && modelDetails.parameters" class="model-parameters">
              <h4>模型参数</h4>
              <el-collapse>
                <el-collapse-item title="详细参数" name="1">
                  <div class="parameter-list">
                    <div v-if="Object.keys(modelDetails.parameters).length === 0" class="no-parameters">
                      无自定义参数
                    </div>
                    <div v-else v-for="(value, key) in modelDetails.parameters" :key="key" class="parameter-item">
                      <label>{{ key }}：</label>
                      <span>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</span>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <div class="detection-list">
              <h4>验证结果</h4>
              <el-empty v-if="!detectionResults.length" description="暂无验证结果" />
              <el-timeline v-else>
                <el-timeline-item
                  v-for="(result, index) in detectionResults"
                  :key="index"
                  :timestamp="result.time"
                  :type="result.type"
                >
                  {{ result.message }}
                </el-timeline-item>
              </el-timeline>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import deviceApi from '@/api/device'

const route = useRoute()

// WebSocket 连接
let ws = null
let wsReconnectTimer = null
const maxReconnectAttempts = 3
let reconnectAttempts = 0
let isReconnecting = false
let isWsConnected = false
let animationFrameId = null

// 响应式变量
const videoFile = ref(null)
const videoUrl = ref('')
const videoWidth = ref(0)  // 添加视频宽度变量
const videoHeight = ref(0)  // 添加视频高度变量
const isDetecting = ref(false)
const progress = ref(0)
const remainingTime = ref('00:00')
const detectedCount = ref(0)
const detectionResults = ref([])
const selectedModel = ref('')
const videoRef = ref(null)
const canvasRef = ref(null)
const lastSentTime = ref(0)
const frameBuffer = new Map()
const maxBufferSize = 8
const targetFPS = 5
const frameInterval = 1000 / targetFPS
const frameDelay = 1000
const frameId = ref(0)
const minTimestampDiff = 50
const maxDetectionDelay = 1000

// 添加自适应帧率控制
let adaptiveFPS = targetFPS
let avgDetectionDelay = 0
const delayHistory = []
const maxDelayHistorySize = 10

// 模型列表相关
const models = ref([])
const loadingModels = ref(false)
const modelDetails = ref(null)

// 从后端加载模型列表
const loadModels = async () => {
  try {
    loadingModels.value = true
    addDetectionRecord('info', '正在加载检测模型列表...')
    
    const response = await deviceApi.getModels();
    models.value = response.data.filter(
      model => model.is_active && model.models_type !== 'vlm' && model.format !== 'api'
    );
    
    if (models.value.length === 0) {
      addDetectionRecord('warning', '未找到可用的检测模型，请先上传和激活模型')
    } else {
      addDetectionRecord('success', `成功加载 ${models.value.length} 个检测模型`)
    }
  } catch (error) {
    addDetectionRecord('error', '加载模型列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingModels.value = false
  }
}

// 获取模型类型名称
const getModelTypeName = (type) => {
  const typeMap = {
    'object_detection': '目标检测',
    'smart_behavior': '智能行为',
    'smart_counting': '智能人数统计',
    'segmentation': '分割模型',
    'keypoint': '关键点检测',
    'pose': '姿态估计',
    'face': '人脸识别',
    'other': '其他模型'
  }
  return typeMap[type] || type
}

// 监听选择模型变化时，获取模型详情
watch(selectedModel, async (modelId) => {
  if (!modelId) {
    modelDetails.value = null
    return
  }
  
  try {
    const { data } = await deviceApi.getModel(modelId)
    modelDetails.value = data
    addDetectionRecord('info', `已选择模型: ${data.models_name}`)
  } catch (error) {
    // console.error('获取模型详情失败:', error)
    addDetectionRecord('error', '获取模型详情失败: ' + (error.response?.data?.detail || error.message))
  }
})

// 添加检测记录
const addDetectionRecord = (type, message) => {
  const now = new Date()
  const time = now.toLocaleTimeString()
  
  // 将自定义类型映射到 Element Plus 支持的类型
  let timelineType = 'primary' // 默认类型
  switch (type) {
    case 'error':
      timelineType = 'danger'
      break
    case 'success':
      timelineType = 'success'
      break
    case 'info':
      timelineType = 'info'
      break
    case 'warning':
      timelineType = 'warning'
      break
  }

  detectionResults.value.unshift({
    time,
    type: timelineType, // 使用映射后的类型
    message
  })

  // 限制记录数量，保留最新的50条
  if (detectionResults.value.length > 50) {
    detectionResults.value = detectionResults.value.slice(0, 50)
  }
}

// 计算属性
const duration = ref('00:00')

// 添加对视频播放进度的监听
const updateVideoProgress = () => {
  const video = videoRef.value
  if (!video || video.duration === 0 || video.duration === Infinity || isNaN(video.duration)) {
    progress.value = 0
    remainingTime.value = '00:00'
    return
  }
  
  // 计算播放进度百分比
  const currentProgress = (video.currentTime / video.duration) * 100
  progress.value = Math.round(currentProgress)
  
  // 计算剩余时间
  const remainingSecs = video.duration - video.currentTime
  if (remainingSecs < 0 || isNaN(remainingSecs)) {
    remainingTime.value = '00:00'
    return
  }
  
  const minutes = Math.floor(remainingSecs / 60)
  const seconds = Math.floor(remainingSecs % 60)
  remainingTime.value = `${minutes}分${seconds}秒`
}

// 初始化视频进度
const initVideoProgress = () => {
  progress.value = 0
  remainingTime.value = '00:00'
  
  // 确保在视频加载完成后更新一次进度
  const video = videoRef.value
  if (video) {
    video.addEventListener('loadedmetadata', updateVideoProgress, { once: true })
  }
}

// 监听视频加载完成
watch(videoUrl, async (newUrl) => {
  if (newUrl) {
    initVideoProgress() // 初始化视频进度
    try {
      // 等待组件更新完成
      await nextTick()
      
      // 确保视频元素存在
      const videoElement = videoRef.value
      if (!videoElement) {
        // console.error('Video element not found')
        throw new Error('无法找到视频元素')
      }
      
      // 等待视频元数据加载完成
      await new Promise((resolve, reject) => {
        const handleLoad = () => {
          // console.log('Video metadata loaded')
          // 获取视频尺寸
          videoWidth.value = videoElement.videoWidth
          videoHeight.value = videoElement.videoHeight
          // console.log('Video dimensions:', videoWidth.value, 'x', videoHeight.value)
          videoElement.removeEventListener('loadedmetadata', handleLoad)
          videoElement.removeEventListener('error', handleError)
          resolve()
        }
        
        const handleError = (error) => {
          // console.error('Video loading error:', error)
          videoElement.removeEventListener('loadedmetadata', handleLoad)
          videoElement.removeEventListener('error', handleError)
          reject(new Error('获取视频信息失败：' + (videoElement.error?.message || '未知错误')))
        }
        
        if (videoElement.readyState >= 1) {
          // 如果视频元数据已经加载完成，直接获取尺寸
          videoWidth.value = videoElement.videoWidth
          videoHeight.value = videoElement.videoHeight
          // console.log('Video dimensions:', videoWidth.value, 'x', videoHeight.value)
          resolve()
        } else {
          videoElement.addEventListener('loadedmetadata', handleLoad)
          videoElement.addEventListener('error', handleError)
        }
      })
      
      // 更新视频时长
      const minutes = Math.floor(videoElement.duration / 60)
      const seconds = Math.floor(videoElement.duration % 60)
      duration.value = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
      
      // 更新视频容器尺寸
      await nextTick()
      handleVideoResize()
      
    } catch (error) {
      // console.error('获取视频时长失败:', error)
      duration.value = '--:--'
      addDetectionRecord('error', '获取视频信息失败：' + error.message)
    }
  } else {
    duration.value = '00:00'
    progress.value = 0
    remainingTime.value = '00:00'
  }
})

const fileSize = computed(() => {
  if (!videoFile.value) return '0 MB'
  const size = (videoFile.value.size / (1024 * 1024)).toFixed(2)
  const dimensions = videoWidth.value && videoHeight.value ? ` (${videoWidth.value}x${videoHeight.value})` : ''
  return size + ' MB' + dimensions
})

// 修改WebSocket初始化函数
const initWebSocket = () => {
  return new Promise((resolve, reject) => {
    // 如果已经有活跃的连接，先关闭它
    if (ws) {
      if (ws.readyState === WebSocket.OPEN) {
        isWsConnected = true
        resolve()
        return
      }
      // 如果连接正在关闭，等待它完全关闭
      if (ws.readyState === WebSocket.CLOSING) {
        ws.addEventListener('close', () => {
          ws = null
          isWsConnected = false
          createNewConnection()
        })
        return
      }
      ws.close()
      ws = null
      isWsConnected = false
    }

    createNewConnection()

    function createNewConnection() {
      try {
        ws = new WebSocket(`ws://${window.location.host}/ws/rtsp/preview`)
        
        ws.onopen = () => {
          // console.log('WebSocket connection established, sending handshake...')
          // 发送连接请求
          ws.send(JSON.stringify({
            type: 'connect',
            client_type: 'detection_client'
          }))
        }

        ws.onmessage = handleWsMessage

        // 设置连接超时
        const connectionTimeout = setTimeout(() => {
          if (!isWsConnected) {
            // console.error('WebSocket connection timeout')
            ws.close()
            reject(new Error('WebSocket连接超时'))
          }
        }, 5000)

        ws.onerror = (error) => {
          // console.error('WebSocket error:', error)
          isWsConnected = false
          clearTimeout(connectionTimeout)
          reject(error)
        }

        ws.onclose = () => {
          // console.log('WebSocket closed')
          isWsConnected = false
          clearTimeout(connectionTimeout)
          if (isDetecting.value && !isReconnecting) {
            handleReconnect()
          }
        }
      } catch (error) {
        // console.error('Failed to create WebSocket:', error)
        reject(error)
      }
    }
  })
}

// 修改WebSocket消息处理函数
const handleWsMessage = (event) => {
  try {
    const data = JSON.parse(event.data)
    // console.log('Received WebSocket message:', data.type)
    
    switch (data.type) {
      case 'detection_result':
        handleDetectionResult(data)
        break
      case 'connect_confirm':
        // console.log('Connection confirmed by server')
        isWsConnected = true
        reconnectAttempts = 0
        break
      case 'config_confirm':
        // console.log('Model configuration confirmed by server')
        break
      case 'progress':
        // 不再更新进度条和剩余时间，因为它们现在由视频播放事件更新
        // console.log('Server progress update:', data)
        break
      case 'error':
        // console.error('Server error:', data.message)
        addDetectionRecord('error', `服务器错误: ${data.message}`)
        break
      default:
        // console.log('Unhandled message type:', data.type)
    }
  } catch (error) {
    // console.error('Error handling WebSocket message:', error)
  }
}

// 添加帧跟踪统计
const frameStats = {
  sent: 0,
  received: 0,
  dropped: 0,
  outOfSync: 0
}

// 修改帧匹配辅助函数
const findBestMatchingFrame = (targetTimestamp, timestamps) => {
  // 首先尝试精确匹配
  if (frameBuffer.has(targetTimestamp)) {
    return targetTimestamp
  }

  // 在容忍范围内查找最接近的时间戳
  let bestMatch = null
  let minDiff = Infinity

  // 按时间戳排序
  const sortedTimestamps = timestamps.sort((a, b) => Math.abs(a - targetTimestamp) - Math.abs(b - targetTimestamp))
  
  for (const timestamp of sortedTimestamps) {
    const diff = Math.abs(timestamp - targetTimestamp)
    // 只匹配在最大检测延迟范围内的帧
    if (diff < maxDetectionDelay && diff < minDiff) {
      minDiff = diff
      bestMatch = timestamp
      // 如果找到足够接近的帧，立即返回
      if (diff < minTimestampDiff) {
        break
      }
    }
  }

  return bestMatch
}

// 修改发送帧函数
const sendVideoFrame = async () => {
  if (!isDetecting.value) return

  const now = Date.now()
  if (now - lastSentTime.value < frameInterval) return

  try {
    const video = videoRef.value
    if (!video || video.readyState !== 4 || video.paused || video.ended) return

    // 清理过期帧
    const currentTime = Date.now()
    for (const [timestamp, frameInfo] of frameBuffer.entries()) {
      if (currentTime - timestamp > frameDelay) {
        frameBuffer.delete(timestamp)
        frameStats.dropped++
      }
    }

    // 如果缓冲区已满，删除最旧的帧
    if (frameBuffer.size >= maxBufferSize) {
      const oldestTimestamp = Math.min(...frameBuffer.keys())
      frameBuffer.delete(oldestTimestamp)
      frameStats.dropped++
    }

    // 使用固定的目标尺寸
    const targetWidth = 512
    const targetHeight = 512

    // 复用离屏canvas
    if (!window._offscreenCanvas) {
      window._offscreenCanvas = document.createElement('canvas')
      window._offscreenCanvas.width = targetWidth
      window._offscreenCanvas.height = targetHeight
      window._offscreenCtx = window._offscreenCanvas.getContext('2d', {
        alpha: false,
        willReadFrequently: true
      })
      window._offscreenCtx.imageSmoothingEnabled = true
      window._offscreenCtx.imageSmoothingQuality = 'high'
    }

    const ctx = window._offscreenCtx

    // 计算裁剪参数以保持宽高比
    const scale = Math.min(targetWidth / video.videoWidth, targetHeight / video.videoHeight)
    const scaledWidth = video.videoWidth * scale
    const scaledHeight = video.videoHeight * scale
    const offsetX = (targetWidth - scaledWidth) / 2
    const offsetY = (targetHeight - scaledHeight) / 2

    // 清除画布并绘制视频帧
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, targetWidth, targetHeight)
    ctx.drawImage(
      video,
      offsetX,
      offsetY,
      scaledWidth,
      scaledHeight
    )

    // 更新帧信息
    frameBuffer.set(now, {
      videoTime: video.currentTime,
      canvasWidth: video.videoWidth,
      canvasHeight: video.videoHeight,
      scale: scale,
      offset: { x: offsetX, y: offsetY },
      displayWidth: video.getBoundingClientRect().width,
      displayHeight: video.getBoundingClientRect().height,
      timestamp: now
    })

    // 转换为较低质量的JPEG
    const blob = await new Promise(resolve => {
      window._offscreenCanvas.toBlob(resolve, 'image/jpeg', 0.65)
    })

    if (!blob || blob.size < 512) return

    // 转换为base64
    const base64Image = await new Promise((resolve) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result.split(',')[1])
      reader.readAsDataURL(blob)
    })

    if (!base64Image || base64Image.length < 500) return

    // 发送帧数据
    ws.send(JSON.stringify({
      type: 'video',
      frame_id: frameId.value++,
      frame: base64Image,
      width: targetWidth,
      height: targetHeight,
      timestamp: now
    }))

    lastSentTime.value = now

    // 更新发送统计
    frameStats.sent++
    
    // 每100帧输出一次统计信息
    // if (frameStats.sent % 100 === 0) {
    //   console.log('Frame stats:', {
    //     sent: frameStats.sent,
    //     received: frameStats.received,
    //     dropped: frameStats.dropped,
    //     outOfSync: frameStats.outOfSync,
    //     bufferSize: frameBuffer.size
    //   })
    // }

  } catch (error) {
    // console.error('Error sending frame:', error)
  }
}

// 修改检测结果处理函数
const handleDetectionResult = (data) => {
  try {
    if (!data || !data.objects || !Array.isArray(data.objects) || !data.timestamp) {
      // console.warn('Invalid detection result data:', data)
      return
    }

    frameStats.received++

    // 计算检测延迟并更新自适应帧率
    const detectionDelay = Date.now() - data.timestamp
    
    // 更新延迟历史
    delayHistory.push(detectionDelay)
    if (delayHistory.length > maxDelayHistorySize) {
      delayHistory.shift()
    }
    
    // 计算平均延迟
    avgDetectionDelay = delayHistory.reduce((a, b) => a + b, 0) / delayHistory.length
    
    // 自适应调整帧率
    if (avgDetectionDelay > 800) {
      adaptiveFPS = Math.max(2, adaptiveFPS - 0.5)
    } else if (avgDetectionDelay < 400 && adaptiveFPS < targetFPS) {
      adaptiveFPS = Math.min(targetFPS, adaptiveFPS + 0.5)
    }
    
    // 如果延迟太大，跳过这一帧
    if (detectionDelay > maxDetectionDelay) {
      // console.warn(`Detection delay too large: ${detectionDelay}ms, skipping frame`)
      frameStats.outOfSync++
      return
    }

    // 获取所有可用的时间戳
    const timestamps = Array.from(frameBuffer.keys())
    if (timestamps.length === 0) {
      // console.warn('Frame buffer empty, waiting for frames...')
      return
    }

    // 查找最佳匹配帧
    const matchedTimestamp = findBestMatchingFrame(data.timestamp, timestamps)
    if (!matchedTimestamp) {
      frameStats.outOfSync++
      return
    }

    const frameInfo = frameBuffer.get(matchedTimestamp)

    // 更新检测计数
    detectedCount.value = data.objects.length

    // 获取画布和视频元素
    const canvas = canvasRef.value
    const video = videoRef.value
    if (!canvas || !video) {
      // console.warn('Canvas or video element not found')
      return
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      // console.warn('Could not get canvas context')
      return
    }

    // 使用帧信息中保存的显示尺寸
    canvas.width = frameInfo.displayWidth
    canvas.height = frameInfo.displayHeight

    // 计算视频在显示容器中的实际尺寸和位置（考虑object-fit: contain）
    const videoDisplayAspect = frameInfo.displayWidth / frameInfo.displayHeight
    const videoAspect = frameInfo.canvasWidth / frameInfo.canvasHeight
    
    let videoDisplayWidth, videoDisplayHeight, videoDisplayOffsetX, videoDisplayOffsetY
    
    if (videoAspect > videoDisplayAspect) {
      // 视频更宽，以宽度为准
      videoDisplayWidth = frameInfo.displayWidth
      videoDisplayHeight = frameInfo.displayWidth / videoAspect
      videoDisplayOffsetX = 0
      videoDisplayOffsetY = (frameInfo.displayHeight - videoDisplayHeight) / 2
    } else {
      // 视频更高，以高度为准
      videoDisplayWidth = frameInfo.displayHeight * videoAspect
      videoDisplayHeight = frameInfo.displayHeight
      videoDisplayOffsetX = (frameInfo.displayWidth - videoDisplayWidth) / 2
      videoDisplayOffsetY = 0
    }

    // 清除上一帧的检测框
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 绘制新的检测框
    data.objects.forEach(obj => {
      const [x, y, w, h] = obj.bbox
      
      // 第一步：从512x512坐标系转换回原始视频坐标系
      // 考虑发送时的缩放和偏移
      const originalX = (x - frameInfo.offset.x) / frameInfo.scale
      const originalY = (y - frameInfo.offset.y) / frameInfo.scale
      const originalW = w / frameInfo.scale
      const originalH = h / frameInfo.scale
      
      // 第二步：从原始视频坐标系转换到显示坐标系
      const displayScale = {
        x: videoDisplayWidth / frameInfo.canvasWidth,
        y: videoDisplayHeight / frameInfo.canvasHeight
      }
      
      const boxX = originalX * displayScale.x + videoDisplayOffsetX
      const boxY = originalY * displayScale.y + videoDisplayOffsetY
      const boxW = originalW * displayScale.x
      const boxH = originalH * displayScale.y

      // 设置绘制样式
      ctx.lineWidth = Math.max(2, Math.min(canvas.width, canvas.height) / 200)
      ctx.strokeStyle = '#00ff00'
      ctx.fillStyle = '#00ff00'
      
      // 绘制边界框
      ctx.beginPath()
      ctx.strokeRect(boxX, boxY, boxW, boxH)

      // 准备标签文本
      const label = `${obj.class} ${Math.round(obj.confidence * 100)}%`
      const fontSize = Math.max(12, Math.min(canvas.width / 50, 16))
      ctx.font = `${fontSize}px Arial`
      
      // 测量文本宽度
      const textMetrics = ctx.measureText(label)
      const padding = 4

      // 绘制标签背景
      ctx.globalAlpha = 0.7
      ctx.fillRect(
        boxX,
        boxY - fontSize - padding * 2,
        textMetrics.width + padding * 2,
        fontSize + padding * 2
      )

      // 绘制标签文本
      ctx.globalAlpha = 1.0
      ctx.fillStyle = '#ffffff'
      ctx.fillText(label, boxX + padding, boxY - padding)
    })

    // 清理已处理的帧
    frameBuffer.delete(matchedTimestamp)

    // 添加检测记录（限制更新频率）
    if (data.objects.length > 0 && (!lastRecordTime || Date.now() - lastRecordTime > 1000)) {
      const uniqueClasses = [...new Set(data.objects.map(obj => obj.class))]
      const message = `检测到 ${data.objects.length} 个目标: ${uniqueClasses.join(', ')}`
      addDetectionRecord('success', message)
      lastRecordTime = Date.now()
    }

  } catch (error) {
    // console.error('Error handling detection result:', error)
  }
}

// 添加记录时间控制
let lastRecordTime = 0

// 修改帧捕获启动函数
const startFrameCapture = () => {
  let lastFrameTime = 0
  const captureFrame = (timestamp) => {
    if (!isDetecting.value) return
    
    const interval = 1000 / adaptiveFPS  // 使用自适应帧率
    const elapsed = timestamp - lastFrameTime
    
    if (elapsed >= interval) {
      sendVideoFrame()
      lastFrameTime = timestamp
      
      // 输出性能统计
      // if (frameStats.sent % 50 === 0) {
      //   console.log('Performance stats:', {
      //     fps: adaptiveFPS.toFixed(1),
      //     avgDelay: avgDetectionDelay.toFixed(0),
      //     bufferSize: frameBuffer.size,
      //     dropped: frameStats.dropped,
      //     outOfSync: frameStats.outOfSync
      //   })
      // }
    }
    
    animationFrameId = requestAnimationFrame(captureFrame)
  }
  
  animationFrameId = requestAnimationFrame(captureFrame)
}

// 处理视频文件选择
const handleVideoChange = async (file) => {
  // 检查文件类型
  const allowedTypes = ['video/mp4', 'video/webm', 'video/ogg', 'video/x-matroska', 'video/avi', 'video/quicktime']
  const fileType = file.raw.type.toLowerCase()
  
  // 检查文件扩展名
  const fileName = file.raw.name.toLowerCase()
  const allowedExtensions = ['.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov', '.wmv']
  const hasAllowedExtension = allowedExtensions.some(ext => fileName.endsWith(ext))
  
  if (!allowedTypes.includes(fileType) && !hasAllowedExtension) {
    ElMessage.error('请上传支持的视频格式：MP4、WebM、OGG、MKV、AVI、MOV或WMV')
    return false
  }
  
  // 检查文件大小（限制为2GB）
  if (file.raw.size > 2 * 1024 * 1024 * 1024) {
    ElMessage.error('视频文件大小不能超过2GB')
    return false
  }
  
  try {
    // 清理之前的视频资源
    if (videoUrl.value) {
      URL.revokeObjectURL(videoUrl.value)
      videoUrl.value = ''
    }
    
    // 重置状态
    videoFile.value = null
    progress.value = 0
    remainingTime.value = '00:00'
    detectedCount.value = 0
    detectionResults.value = []
    
    // 等待组件更新完成
    await nextTick()
    
    // 确保视频元素存在
    const videoElement = videoRef.value
    if (!videoElement) {
      // console.error('Video element not found in DOM')
      throw new Error('无法找到视频元素，请刷新页面重试')
    }
    
    // 重置视频元素
    videoElement.pause()
    videoElement.removeAttribute('src')
    videoElement.load()
    
    // 等待DOM更新
    await nextTick()
    
    // 创建视频URL并设置文件
    const url = URL.createObjectURL(file.raw)
    videoFile.value = file.raw
    
    // 设置事件监听器并加载视频
    await new Promise((resolve, reject) => {
      let timeoutId = setTimeout(() => {
        cleanup()
        reject(new Error('视频加载超时，请检查文件是否损坏'))
      }, 30000)
      
      const cleanup = () => {
        videoElement.removeEventListener('loadedmetadata', handleLoad)
        videoElement.removeEventListener('error', handleError)
        videoElement.removeEventListener('loadeddata', handleDataLoad)
        clearTimeout(timeoutId)
      }
      
      const handleLoad = () => {
        // console.log('Video metadata loaded, readyState:', videoElement.readyState)
        videoElement.addEventListener('loadeddata', handleDataLoad)
        // 添加进度更新
        updateVideoProgress()
      }
      
      const handleDataLoad = () => {
        // console.log('Video data loaded, readyState:', videoElement.readyState)
        if (videoElement.readyState >= 2) {
          updateVideoProgress() // 再次更新进度
          cleanup()
          resolve()
        }
      }
      
      const handleError = (error) => {
        // console.error('Video loading error:', error)
        cleanup()
        reject(new Error('视频加载失败：' + (videoElement.error?.message || '未知错误')))
      }
      
      // 设置事件监听器
      videoElement.addEventListener('loadedmetadata', handleLoad)
      videoElement.addEventListener('error', handleError)
      
      // 设置视频源
      videoElement.src = url
      videoUrl.value = url
    })
    
    // 确保视频尺寸已设置
    if (videoElement.videoWidth === 0 || videoElement.videoHeight === 0) {
      throw new Error('无法获取视频尺寸，请检查文件是否正确')
    }
    
    // 视频加载成功
    // console.log('Video loaded successfully:', {
    //   width: videoElement.videoWidth,
    //   height: videoElement.videoHeight,
    //   duration: videoElement.duration
    // })
    
    // 更新视频容器尺寸
    await nextTick()
    handleVideoResize()
    
    addDetectionRecord('success', '视频加载完成')
    ElMessage.success('视频加载成功')
    
  } catch (error) {
    // console.error('视频加载错误:', error)
    ElMessage.error(error.message || '视频加载失败')
    
    // 清理资源
    if (videoUrl.value) {
      URL.revokeObjectURL(videoUrl.value)
      videoUrl.value = ''
    }
    if (videoRef.value) {
      videoRef.value.removeAttribute('src')
      videoRef.value.load()
    }
    videoFile.value = null
    
    addDetectionRecord('error', `视频加载失败: ${error.message || '未知错误'}`)
    
    // 重置进度
    progress.value = 0
    remainingTime.value = '00:00'
  }
  
  return false
}

// 切换检测状态
const toggleDetection = async () => {
  if (isDetecting.value) {
    stopDetection()
  } else {
    startDetection()
  }
}

// 开始检测
const startDetection = async () => {
  try {
    if (!selectedModel.value) {
      throw new Error('请先选择检测模型')
    }

    // 确保 WebSocket 连接
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      await initWebSocket()
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error('无法建立WebSocket连接')
    }

    // 发送模型配置并等待确认
    try {
      await sendModelConfig()
    } catch (error) {
      // console.error('Model configuration failed:', error)
      throw new Error(`模型配置失败: ${error.message}`)
    }

    isDetecting.value = true
    detectedCount.value = 0
    detectionResults.value = []
    frameId.value = 0

    const video = videoRef.value
    
    // 确保视频已加载完成
    if (!video) {
      throw new Error('视频元素未找到')
    }

    if (video.readyState < 2) { // HAVE_CURRENT_DATA
      await new Promise((resolve) => {
        video.addEventListener('loadeddata', resolve, { once: true })
      })
    }

    // 获取视频总帧数
    const totalFrames = Math.ceil(video.duration * targetFPS)
    
    // 发送视频信息
    try {
      ws.send(JSON.stringify({
        type: 'video_info',
        total_frames: totalFrames,
        video_width: video.videoWidth,
        video_height: video.videoHeight,
        fps: targetFPS
      }))
    } catch (error) {
      throw new Error('发送视频信息失败：' + error.message)
    }

    // 重置视频到开始位置并开始播放
    video.currentTime = 0
    await new Promise((resolve) => {
      video.addEventListener('seeked', resolve, { once: true })
      video.play()
    })

    startFrameCapture()
    addDetectionRecord('success', '开始检测')
  } catch (error) {
    // console.error('Failed to start detection:', error)
    addDetectionRecord('error', `启动检测失败: ${error.message}`)
    isDetecting.value = false
    // 如果是WebSocket错误，尝试重新连接
    if (error.message.includes('WebSocket')) {
      handleReconnect()
    }
  }
}

// 监听视频尺寸变化
const handleVideoResize = () => {
  if (videoRef.value && canvasRef.value) {
    const videoRect = videoRef.value.getBoundingClientRect()
    canvasRef.value.width = videoRect.width
    canvasRef.value.height = videoRect.height
  }
}

// 添加重连处理函数
const handleReconnect = async () => {
  if (isReconnecting || reconnectAttempts >= maxReconnectAttempts) {
    return
  }

  isReconnecting = true
  reconnectAttempts++

  try {
    // console.log(`尝试重新连接 (${reconnectAttempts}/${maxReconnectAttempts})...`)
    addDetectionRecord('info', `尝试重新连接 (${reconnectAttempts}/${maxReconnectAttempts})...`)
    
    await initWebSocket()
    
    isReconnecting = false
    reconnectAttempts = 0
    addDetectionRecord('success', '重新连接成功')
    
    // 如果正在检测，重新开始检测
    if (isDetecting.value) {
      startDetection()
    }
  } catch (error) {
    // console.error('Reconnection failed:', error)
    isReconnecting = false
    
    if (reconnectAttempts < maxReconnectAttempts) {
      // 使用指数退避策略
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 5000)
      wsReconnectTimer = setTimeout(handleReconnect, delay)
    } else {
      addDetectionRecord('error', '重新连接失败，请刷新页面重试')
      stopDetection()
    }
  }
}

// 修改停止检测函数
const stopDetection = async () => {
  isDetecting.value = false
  
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }

  if (videoRef.value) {
    videoRef.value.pause()
  }

  // 确保WebSocket正确关闭
  if (ws) {
    try {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }))
        await new Promise(resolve => {
          ws.onclose = resolve
          ws.close()
        })
      }
      ws = null
      isWsConnected = false
    } catch (error) {
      // console.error('Error closing WebSocket:', error)
    }
  }

  // 重置统计信息
  Object.assign(frameStats, {
    sent: 0,
    received: 0,
    dropped: 0,
    outOfSync: 0
  })
  
  frameBuffer.clear()
  
  addDetectionRecord('info', '检测已停止')
}

// 发送模型配置到WebSocket服务器
const sendModelConfig = () => {
  return new Promise((resolve, reject) => {
    if (!selectedModel.value || !modelDetails.value) {
      reject(new Error('未选择模型或模型详情未加载'))
      return
    }

    try {
      const modelConfig = {
        type: 'config',
        models_id: modelDetails.value.models_id,
        models_name: modelDetails.value.models_name,
        models_type: modelDetails.value.models_type,
        models_path: modelDetails.value.file_path,
        format: modelDetails.value.format,
        parameters: modelDetails.value.parameters || {}
      }

      // 注册一次性消息处理器，等待配置确认
      const configConfirmHandler = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'config_confirm') {
            // 移除此处理器
            ws.removeEventListener('message', configConfirmHandler)
            
            if (data.model === modelDetails.value.models_name) {
              addDetectionRecord('success', `模型 ${modelDetails.value.models_name} 配置成功`)
              resolve()
            } else {
              reject(new Error(data.message || '模型配置失败'))
            }
          }
        } catch (error) {
          // console.error('处理模型配置响应失败:', error)
        }
      }

      // 添加一次性消息监听器
      ws.addEventListener('message', configConfirmHandler)

      // 发送模型配置
      // console.log('Sending model config:', modelConfig)
      ws.send(JSON.stringify(modelConfig))

      // 设置超时，防止无限等待
      setTimeout(() => {
        // 如果仍然是侦听器，则移除并拒绝
        ws.removeEventListener('message', configConfirmHandler)
        reject(new Error('模型配置响应超时'))
      }, 10000)
      
    } catch (error) {
      reject(new Error('发送模型配置失败: ' + error.message))
    }
  })
}

// 监听组件加载
onMounted(async () => {
  await loadModels()

  if (route.query.modelId) {
    selectedModel.value = String(route.query.modelId)
  }
  
  // 添加视频播放进度更新事件
  const video = videoRef.value
  if (video) {
    video.addEventListener('timeupdate', updateVideoProgress)
  }
  
  // 恢复原有的初始化代码
  initWebSocket()
  window.addEventListener('resize', handleVideoResize)
})

onBeforeUnmount(() => {
  if (isDetecting.value) {
    stopDetection()
  }
  
  // 移除视频播放进度更新事件
  const video = videoRef.value
  if (video) {
    video.removeEventListener('timeupdate', updateVideoProgress)
  }
  
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  
  if (ws) {
    try {
      ws.close()
      ws = null
      isWsConnected = false
    } catch (error) {
      // console.error('Error closing WebSocket on unmount:', error)
    }
  }
  
  if (videoUrl.value) {
    URL.revokeObjectURL(videoUrl.value)
  }
  
  window.removeEventListener('resize', handleVideoResize)
})
</script>

<style scoped>
.detection-container {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.video-card {
  margin-bottom: 20px;
}

.video-container {
  width: 100%;
  height: 500px;
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

.placeholder .el-icon {
  margin-bottom: 16px;
}

.video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.video-player.hidden {
  display: none;
}

.detection-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.video-controls {
  margin-top: 20px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #606266;
  font-size: 14px;
}

.detection-info {
  height: auto;
  max-height: 700px;
  display: flex;
  flex-direction: column;
}

.detection-content {
  overflow-y: auto;
  max-height: calc(700px - 60px); /* 减去header高度 */
  padding-right: 5px;
  margin-right: -5px; /* 抵消padding-right导致的宽度增加 */
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-info {
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 4px;
  margin-bottom: 12px;
}

.info-item {
  display: flex;
  margin-bottom: 8px;
  font-size: 14px;
}

.info-item:last-child {
  margin-bottom: 0;
}

.info-item label {
  color: #606266;
  flex: 0 0 70px;
}

.info-item .info-value {
  flex: 1;
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detection-stats {
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 4px;
  margin-bottom: 12px;
}

.stat-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  font-size: 14px;
}

.stat-item:last-child {
  margin-bottom: 0;
}

.stat-item label {
  flex: 0 0 70px;
  color: #606266;
}

.detection-list {
  flex: 1;
  margin-top: 12px;
}

.detection-list h4 {
  margin: 0 0 12px;
  color: #2c3e50;
}

.model-select {
  width: 240px;
}

.model-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-name {
  /* font-weight: bold; */
  color: #303133;
  margin-bottom: 2px;
}

.model-desc {
  font-size: 12px;
  color: #909399;
}

.model-format {
  font-size: 12px;
  color: #67c23a;
  margin-top: 2px;
}

.empty-model-list {
  padding: 10px;
  text-align: center;
  color: #909399;
}

.model-parameters {
  margin-top: 12px;
  margin-bottom: 12px;
}

.model-parameters h4 {
  margin-bottom: 8px;
  font-size: 14px;
  color: #303133;
}

.parameter-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.parameter-item {
  display: flex;
  font-size: 13px;
}

.parameter-item label {
  flex: 0 0 70px;
  color: #606266;
  font-weight: 500;
}

.parameter-item span {
  flex: 1;
  word-break: break-all;
}

.no-parameters {
  color: #909399;
  font-style: italic;
  font-size: 13px;
  padding: 5px 0;
}
</style> 