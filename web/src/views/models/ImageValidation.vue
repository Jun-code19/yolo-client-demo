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
          class="upload-image"
          action="#"
          :auto-upload="false"
          :show-file-list="false"
          accept=".jpg,.jpeg,.png,.bmp,.webp"
          :on-change="handleImageChange"
          :before-upload="() => false"
          multiple
        >
          <el-button type="primary">选择图片</el-button>
        </el-upload>
        <el-button 
          type="success" 
          :disabled="!imageList.length || !selectedModel" 
          @click="startBatchDetection"
        >
          {{ isDetecting ? '停止验证' : '开始验证' }}
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="16">
        <el-card class="image-card">
          <div class="image-preview">
            <div v-if="!currentImage" class="placeholder">
              <el-icon :size="64"><Picture /></el-icon>
              <p>选择图片开始验证</p>
            </div>
            <div v-else class="preview-container">
              <img :src="currentImage.url" class="preview-image" />
              <canvas ref="canvasRef" class="detection-canvas"></canvas>
            </div>
          </div>

          <div class="image-list" v-if="imageList.length">
            <el-scrollbar>
              <div class="thumbnail-list">
                <div
                  v-for="(image, index) in imageList"
                  :key="index"
                  class="thumbnail-item"
                  :class="{ active: currentImageIndex === index }"
                  @click="selectImage(index)"
                >
                  <el-image
                    :src="image.url"
                    fit="cover"                   
                  >
                    <template #placeholder>
                      <div class="image-placeholder">
                        <el-icon><Picture /></el-icon>
                      </div>
                    </template>
                  </el-image>
                  <el-tag
                    size="small"
                    :type="image.status === 'done' ? 'success' : image.status === 'processing' ? 'warning' : 'primary'"
                  >
                    {{ getStatusText(image.status) }}
                  </el-tag>
                </div>
              </div>
            </el-scrollbar>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="detection-info">
          <template #header>
            <div class="card-header">
              <span>验证信息</span>
              <el-button-group v-if="currentImage">
                <el-button type="primary" link @click="downloadResult">导出结果</el-button>
                <el-button type="primary" link @click="downloadImage">导出图片</el-button>
              </el-button-group>
            </div>
          </template>
          
          <template v-if="currentImage">
            <div class="image-info">
              <div class="info-item">
                <label>文件名：</label>
                <span>{{ currentImage.name }}</span>
              </div>
              <div class="info-item">
                <label>大小：</label>
                <span>{{ getFileSize(currentImage.size) }}</span>
              </div>
              <div class="info-item">
                <label>分辨率：</label>
                <span>{{ currentImage.resolution || '未知' }}</span>
              </div>
            </div>

            <div class="detection-stats">
              <div class="stat-item">
                <label>验证状态：</label>
                <el-tag :type="getStatusType(currentImage.status)">
                  {{ getStatusText(currentImage.status) }}
                </el-tag>
              </div>
              <div class="stat-item">
                <label>目标数量：</label>
                <span>{{ currentImage.detectedCount || 0 }}</span>
              </div>
            </div>

            <div class="detection-results">
              <h4>验证结果</h4>
              <el-empty 
                v-if="!currentImage.results?.length" 
                description="暂无验证结果" 
              />
              <el-table
                v-else
                :data="currentImage.results"
                style="width: 100%"
                size="small"
              >
                <el-table-column prop="class" label="类别" />
                <el-table-column prop="confidence" label="置信度">
                  <template #default="{ row }">
                    {{ (row.confidence * 100).toFixed(2) }}%
                  </template>
                </el-table-column>
                <el-table-column prop="position" label="位置" />
              </el-table>
            </div>
          </template>
          <el-empty v-else description="请选择图片" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Picture } from '@element-plus/icons-vue'
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
let canvasContext = null

// 响应式变量
const imageList = ref([])
const currentImage = ref(null)
const isDetecting = ref(false)
const detectionResults = ref([])
const selectedModel = ref('')
const canvasRef = ref(null)

// 模型列表相关
const models = ref([])
const loadingModels = ref(false)
const modelDetails = ref(null)

// 计算属性
const currentImageIndex = computed(() => {
  if (currentImage.value) return imageList.value.findIndex(img => img.url === currentImage.value.url)
  return -1
})

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

// 获取默认描述
const getDefaultDescription = (type, name) => {
  if (type === 'object_detection') {
    if (name.toLowerCase().includes('yolo')) {
      if (name.toLowerCase().includes('n')) {
        return '速度最快，适合实时检测'
      } else if (name.toLowerCase().includes('s')) {
        return '速度和精度的平衡'
      } else if (name.toLowerCase().includes('m')) {
        return '中等精度'
      } else if (name.toLowerCase().includes('l')) {
        return '高精度'
      } else if (name.toLowerCase().includes('x')) {
        return '最高精度'
      }
    }
  }
  return '通用检测模型'
}
// 格式化文件大小
const formatFileSize = (size) => {
  if (size < 1024) {
    return size + ' B'
  } else if (size < 1024 * 1024) {
    return (size / 1024).toFixed(2) + ' KB'
  } else if (size < 1024 * 1024 * 1024) {
    return (size / (1024 * 1024)).toFixed(2) + ' MB'
  } else {
    return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  }
}
// 格式化日期
const formatDate = (dateStr) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

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
      startBatchDetection()
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

// 修改开始检测函数
const startBatchDetection = async () => {
  if (isDetecting.value) {
    stopDetection()
    return
  }

  if (!imageList.value.length) {
    ElMessage.warning('请先选择图片')
    return
  }

  if (!selectedModel.value) {
    ElMessage.warning('请先选择检测模型')
    return
  }

  try {
    // 更新检测状态
    isDetecting.value = true
    addDetectionRecord('info', '开始批量验证图片...')
    
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
    
    // 重置图片状态
    imageList.value.forEach(image => {
      if (image.status !== 'done') {
        image.status = 'pending'
        image.results = []
        image.detectedCount = 0
      }
    })

    // 处理每张图片
    for (let i = 0; i < imageList.value.length; i++) {
      const image = imageList.value[i]
      if (image.status === 'done') {
        addDetectionRecord('info', `跳过已处理的图片: ${image.name}`)
        continue
      }
      
      // 如果停止检测则中断处理
      if (!isDetecting.value) break
      
      try {
        // 更新图片状态
        image.status = 'processing'
        addDetectionRecord('info', `正在处理图片: ${image.name}`)
        
        // 创建canvas并绘制图片
        const img = await loadImage(image.url)
        
        // 设置处理图片的尺寸
        const maxSize = 800
        let width = img.width
        let height = img.height
        let scale = 1
        
        // 如果图片尺寸过大，则按比例缩小
        if (width > maxSize || height > maxSize) {
          scale = Math.min(maxSize / width, maxSize / height)
          width = Math.floor(width * scale)
          height = Math.floor(height * scale)
        }
        
        // 创建离屏Canvas
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        ctx.drawImage(img, 0, 0, width, height)
        
        // 转换为base64并发送
        const imageData = canvas.toDataURL('image/jpeg', 0.85)
        const base64Data = imageData.split(',')[1]
        
        if (!base64Data) {
          throw new Error('图片转换失败')
        }

        // 发送图片数据到服务器
        ws.send(JSON.stringify({
          type: 'image',
          image_id: i+1,
          image_name: image.name,
          width: width,
          height: height,
          original_width: img.width,
          original_height: img.height,
          scale: scale,
          frame: base64Data,
          timestamp: Date.now()
        }))
        
        // 等待服务器响应，设置超时
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => {
            reject(new Error('服务器响应超时'))
          }, 30000)
          
          const responseHandler = (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.type === 'detection_result' && data.image_id === i+1) {
                clearTimeout(timeout)
                ws.removeEventListener('message', responseHandler)
                resolve()
              }
            } catch (error) {
              // console.error('处理响应失败:', error)
            }
          }
          
          ws.addEventListener('message', responseHandler)
        })
        
      } catch (error) {
        // console.error('处理图片失败:', error)
        image.status = 'error'
        addDetectionRecord('error', `处理图片 ${image.name} 失败: ${error.message}`)
      }
    }
    
    // 检测完成
    addDetectionRecord('success', '批量验证完成')
    
  } catch (error) {
    // console.error('批量检测失败:', error)
    ElMessage.error('批量验证失败: ' + error.message)
    addDetectionRecord('error', '批量验证失败: ' + error.message)
  } finally {
    isDetecting.value = false
  }
}

// 加载图片辅助函数
const loadImage = (url) => {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = url
  })
}

// 修改停止检测函数
const stopDetection = () => {
  if (!isDetecting.value) return
  
  isDetecting.value = false
  addDetectionRecord('info', '验证已停止')
  
  // 将处理中的图片状态重置为待检测
  imageList.value.forEach(image => {
    if (image.status === 'processing') {
      image.status = 'pending'
    }
  })
  
  // 如果WebSocket连接打开，发送停止消息
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: 'stop' }))
    } catch (error) {
      // console.error('发送停止消息失败:', error)
    }
  }
}

// 修改处理检测结果函数
const handleDetectionResult = (result) => {
  try {
    // 检查结果有效性
    if (!result || !result.image_id || !Array.isArray(result.objects)) {
      // console.warn('收到无效的检测结果:', result)
      return
    }
    
    // 获取对应的图片
    const imageIndex = result.image_id - 1
    const image = imageList.value[imageIndex]
    
    if (!image) {
      // console.warn(`未找到ID为${imageIndex}的图片`, imageList.value)
      return
    }
    
    // 更新图片状态
    image.status = 'done'
    image.detectedCount = result.objects.length
    
    // 处理检测结果
    image.results = result.objects.map(obj => {
      // 计算检测框的位置信息
      const [x, y, w, h] = obj.bbox
      
      // 返回结构化数据
      return {
        class: obj.class,
        confidence: obj.confidence,
        position: `(${Math.round(x)}, ${Math.round(y)}, ${Math.round(w)}, ${Math.round(h)})`,
        bbox: obj.bbox
      }
    })
    
    // 记录检测结果
    if (image.results.length > 0) {
      const classes = [...new Set(image.results.map(r => r.class))].join(', ')
      addDetectionRecord('success', `图片"${image.name}"检测完成，发现 ${image.results.length} 个目标: ${classes}`)
    } else {
      addDetectionRecord('info', `图片"${image.name}"检测完成，未发现目标`)
    }
    
    // 如果当前显示的是这张图片，则绘制检测框
    if (currentImage.value === image) {
      drawDetectionBoxes(result.objects)
    }
  } catch (error) {
    // console.error('处理检测结果失败:', error)
    ElMessage.error('处理检测结果失败')
  }
}

// 修改绘制检测框函数
const drawDetectionBoxes = (objects) => {
  if (!canvasRef.value || !currentImage.value) return
  
  const canvas = canvasRef.value
  
  // 加载原图
  loadImage(currentImage.value.url).then(image => {
    // 设置canvas尺寸
    canvas.width = image.width
    canvas.height = image.height
    
    // 获取绘图上下文
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      // console.error('无法获取canvas上下文')
      return
    }
    
    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    // 不绘制原图，因为已经有img标签显示原图
    ctx.drawImage(image, 0, 0)

    // 遍历目标并绘制检测框
    objects.forEach(obj => {
      const [x, y, w, h] = obj.bbox
      
      // 获取该类别的颜色
      const color = getColorForClass(obj.class)
      
      // 绘制检测框
      ctx.lineWidth = 2
      ctx.strokeStyle = color
      ctx.strokeRect(x, y, w, h)
      
      // 绘制标签背景
      const label = `${obj.class} ${Math.round(obj.confidence * 100)}%`
      ctx.font = '14px Arial'
      const textMetrics = ctx.measureText(label)
      const textWidth = textMetrics.width
      const textHeight = 20
      
      ctx.fillStyle = color + 'CC' // 添加透明度
      ctx.fillRect(x, y - textHeight, textWidth + 10, textHeight)
      
      // 绘制标签文本
      ctx.fillStyle = '#FFFFFF'
      ctx.fillText(label, x + 5, y - 5)
    })
  }).catch(error => {
    // console.error('绘制检测框失败:', error)
  })
}

// 为每个类别生成固定的颜色
const getColorForClass = (() => {
  const colorMap = new Map()
  const colors = [
    '#FF3B30', // 红色
    '#34C759', // 绿色
    '#007AFF', // 蓝色
    '#FF9500', // 橙色
    '#AF52DE', // 紫色
    '#5856D6', // 靛蓝
    '#FF2D55', // 粉红
    '#FFCC00'  // 黄色
  ]
  let colorIndex = 0

  return (className) => {
    if (!colorMap.has(className)) {
      colorMap.set(className, colors[colorIndex % colors.length])
      colorIndex++
    }
    return colorMap.get(className)
  }
})()

// 处理图片选择
const handleImageChange = async (file) => {
  // console.log('Selected image file:', file)
  
  // 检查文件类型和大小
  const allowedTypes = ['image/jpeg', 'image/png', 'image/bmp', 'image/webp']
  const isImage = allowedTypes.includes(file.raw.type) || /\.(jpg|jpeg|png|bmp|webp)$/i.test(file.name)
  const isLt5M = file.size / 1024 / 1024 < 5

  if (!isImage) {
    ElMessage.error('请选择正确的图片格式（支持jpg、png、bmp、webp）！')
    return
  }

  if (!isLt5M) {
    ElMessage.error('图片大小不能超过 5MB！')
    return
  }

  try {
    const url = URL.createObjectURL(file.raw)
    const resolution = await getImageResolution(url)
    
    // 添加到图片列表
    const imageInfo = {
      file: file.raw,
      url,
      name: file.name,
      size: file.size,
      resolution,
      status: 'pending',
      results: []
    }

    // console.log('Image info created:', imageInfo)
    imageList.value.push(imageInfo)
    if (currentImageIndex.value === -1) {
      currentImage.value = imageInfo
    }
  } catch (error) {
    // console.error('Error processing image file:', error)
    ElMessage.error('处理图片文件时出错：' + error.message)
  }
}

// 选择图片
const selectImage = (index) => {
  currentImage.value = imageList.value[index]
  
  // 初始化画布
  const canvas = canvasRef.value
  canvasContext = canvas.getContext('2d')
  
  // 加载图片并绘制
  const img = new Image()
  img.onload = () => {
    canvas.width = img.width
    canvas.height = img.height
    canvasContext.drawImage(img, 0, 0)
  }
  img.src = imageList.value[index].url

  if (currentImage.value && currentImage.value.results && currentImage.value.results.length > 0){
    
    drawDetectionBoxes(currentImage.value.results)
    
  }
}

// 下载结果
const downloadResult = () => {
  if (!currentImage.value || !currentImage.value.results || currentImage.value.results.length === 0) {
    ElMessage.warning('当前图片无检测结果可导出')
    return
  }
  
  try {
    // 创建导出数据
    const exportData = {
      image_name: currentImage.value.name,
      detection_time: new Date().toISOString(),
      model_name: modelDetails.value?.models_name || '未知模型',
      resolution: currentImage.value.resolution,
      objects: currentImage.value.results.map(result => ({
        class: result.class,
        confidence: result.confidence,
        bbox: result.bbox
      }))
    }
    
    // 转换为JSON字符串
    const jsonData = JSON.stringify(exportData, null, 2)
    
    // 创建Blob对象
    const blob = new Blob([jsonData], { type: 'application/json' })
    
    // 创建下载链接
    const url = URL.createObjectURL(blob)
    
    // 创建临时a标签并点击
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentImage.value.name.split('.')[0]}_result.json`
    document.body.appendChild(a)
    a.click()
    
    // 清理
    setTimeout(() => {
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }, 100)
    
    ElMessage.success('检测结果导出成功')
    addDetectionRecord('success', `检测结果已导出为JSON文件`)
  } catch (error) {
    // console.error('导出检测结果失败:', error)
    ElMessage.error('导出检测结果失败: ' + error.message)
    addDetectionRecord('error', '导出检测结果失败: ' + error.message)
  }
}

// 下载图片
const downloadImage = () => {
  if (!currentImage.value || !canvasRef.value) {
    ElMessage.warning('无法导出当前图片')
    return
  }
  
  try {
    // 创建离屏Canvas绘制图片和检测框
    const canvas = document.createElement('canvas')
    const drawExportImage = async () => {
      // 加载原图
      const img = await loadImage(currentImage.value.url)
      
      // 设置Canvas尺寸
      canvas.width = img.width
      canvas.height = img.height
      
      // 获取绘图上下文
      const ctx = canvas.getContext('2d')
      
      // 绘制原图
      ctx.drawImage(img, 0, 0)
      
      // 如果有检测结果，绘制检测框
      if (currentImage.value.results && currentImage.value.results.length > 0) {
        // 绘制检测框
        currentImage.value.results.forEach(obj => {
          const [x, y, w, h] = obj.bbox
          
          // 获取该类别的颜色
          const color = getColorForClass(obj.class)
          
          // 绘制检测框
          ctx.lineWidth = 3
          ctx.strokeStyle = color
          ctx.strokeRect(x, y, w, h)
          
          // 绘制标签背景
          const label = `${obj.class} ${Math.round(obj.confidence * 100)}%`
          ctx.font = 'bold 16px Arial'
          const textMetrics = ctx.measureText(label)
          const textWidth = textMetrics.width
          const textHeight = 24
          
          ctx.fillStyle = color + 'CC' // 添加透明度
          ctx.fillRect(x, y - textHeight, textWidth + 10, textHeight)
          
          // 绘制标签文本
          ctx.fillStyle = '#FFFFFF'
          ctx.fillText(label, x + 5, y - 5)
        })
      }
      
      // 导出为图片
      const dataUrl = canvas.toDataURL('image/png')
      
      // 创建下载链接
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `${currentImage.value.name.split('.')[0]}_detected.png`
      document.body.appendChild(a)
      a.click()
      
      // 清理
      setTimeout(() => {
        document.body.removeChild(a)
      }, 100)
      
      ElMessage.success('检测图片导出成功')
      addDetectionRecord('success', `检测图片已导出为PNG文件`)
    }
    
    drawExportImage().catch(error => {
      // console.error('导出图片失败:', error)
      ElMessage.error('导出图片失败: ' + error.message)
      addDetectionRecord('error', '导出图片失败: ' + error.message)
    })
  } catch (error) {
    // console.error('导出图片失败:', error)
    ElMessage.error('导出图片失败: ' + error.message)
    addDetectionRecord('error', '导出图片失败: ' + error.message)
  }
}

// 工具函数
const getFileSize = (size) => {
  return (size / 1024 / 1024).toFixed(2) + ' MB'
}

const getStatusText = (status) => {
  const statusMap = {
    pending: '待验证',
    processing: '验证中',
    done: '已完成',
    error: '失败'
  }
  return statusMap[status] || status
}

const getStatusType = (status) => {
  const typeMap = {
    pending: 'info',
    processing: 'warning',
    done: 'success',
    error: 'danger'
  }
  return typeMap[status]
}

// 获取图片分辨率
const getImageResolution = (url) => {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      resolve(`${img.naturalWidth} × ${img.naturalHeight}`)
    }
    img.src = url
  })
}

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

// 添加WebSocket消息处理函数
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
      case 'error':
        // console.error('Server error:', data.message)
        addDetectionRecord('error', `服务器错误: ${data.message}`)
        ElMessage.error(`服务器错误: ${data.message}`)
        break
      default:
        // console.log('Unhandled message type:', data.type)
    }
  } catch (error) {
    // console.error('Error handling WebSocket message:', error)
  }
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

// 生命周期钩子
onMounted(async () => {
  await loadModels()

  if (route.query.modelId) {
    selectedModel.value = String(route.query.modelId)
  }
  
  try {
    // 初始化WebSocket连接
    await initWebSocket()
    addDetectionRecord('success', 'WebSocket连接成功')
  } catch (error) {
    // console.error('WebSocket连接失败:', error)
    addDetectionRecord('error', 'WebSocket连接失败: ' + error.message)
  }
})

onUnmounted(() => {
  // 停止检测
  if (isDetecting.value) {
    stopDetection()
  }
  
  // 关闭WebSocket连接
  if (ws) {
    try {
      ws.close()
      ws = null
    } catch (error) {
      // console.error('关闭WebSocket连接失败:', error)
    }
  }
  
  // 清理定时器
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  
  // 清理图片URL
  imageList.value.forEach(image => {
    URL.revokeObjectURL(image.url)
  })
  
  // 清空图片列表
  imageList.value = []
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

.image-card {
  margin-bottom: 20px;
}

.image-preview {
  width: 100%;
  height: 500px;
  background-color: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  overflow: hidden;
}

.placeholder {
  text-align: center;
  color: #606266;
}

.placeholder .el-icon {
  margin-bottom: 16px;
}

.preview-container {
  width: 100%;
  height: 100%;
  position: relative;
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.detection-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.image-list {
  margin-top: 20px;
  height: 120px;
}

.thumbnail-list {
  display: flex;
  gap: 12px;
  padding: 4px;
}

.thumbnail-item {
  position: relative;
  width: 100px;
  height: 100px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.3s ease;
}

.thumbnail-item.active {
  border-color: #409EFF;
}

.thumbnail-item .el-image {
  width: 100%;
  height: 100%;
}

.thumbnail-item .el-tag {
  position: absolute;
  bottom: 4px;
  right: 4px;
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f5f7fa;
}

.detection-info {
  height: 600px;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.image-info {
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 4px;
  margin-bottom: 16px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.info-item:last-child {
  margin-bottom: 0;
}

.info-item label {
  color: #606266;
}

.detection-stats {
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 4px;
  margin-bottom: 16px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stat-item:last-child {
  margin-bottom: 0;
}

.detection-results {
  flex: 1;
  overflow-y: auto;
}

.detection-results h4 {
  margin: 0 0 16px;
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
  font-weight: 500;
  color: #2c3e50;
}

.model-desc {
  font-size: 12px;
  color: #909399;
}
</style> 