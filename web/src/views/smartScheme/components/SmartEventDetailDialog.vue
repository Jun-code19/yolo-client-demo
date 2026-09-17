<template>
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" title="事件详情"
    width="50%" top="5vh"  :z-index="999999" append-to-body class="high-priority-dialog">
    <div v-if="event" class="event-detail">
      <!-- 基本信息 -->
      <el-card class="detail-card">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
            <el-tag :type="getStatusTagType(event.status)">
              {{ getStatusText(event.status) }}
            </el-tag>
          </div>
        </template>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="事件类型">
            <el-tag :type="getEventTypeTagType(event.event_type)">
              {{ getEventTypeText(event.event_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag :type="getPriorityTagType(event.priority)">
              {{ getPriorityText(event.priority) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="摄像机">
            {{ event.camera_name }}
          </el-descriptions-item>
          <el-descriptions-item label="摄像机IP">
            {{ event.camera_ip }}
          </el-descriptions-item>
          <el-descriptions-item label="事件标题">
            {{ event.title }}
          </el-descriptions-item>
          <el-descriptions-item label="发生时间">
            {{ formatDateTime(event.timestamp) }}
          </el-descriptions-item>
          <el-descriptions-item label="事件描述" :span="2">
            {{ event.description || '暂无描述' }}
          </el-descriptions-item>

        </el-descriptions>
      </el-card>

      <!-- 事件数据 -->
      <el-card class="detail-card">
        <template #header>
          <span>事件数据</span>
        </template>

        <div class="event-data">
          <div v-if="event.event_data" class="data-content">
            <pre>{{ formatJson(event.event_data) }}</pre>
          </div>
          <div v-else class="no-data">
            <el-empty description="暂无事件数据" />
          </div>
        </div>
      </el-card>

      <!-- 检测结果 -->
      <el-card class="detail-card" v-if="event.detection_results">
        <template #header>
          <span>检测结果</span>
        </template>

        <div class="detection-results">
          <div v-for="(result, index) in event.detection_results" :key="index" class="result-item">
            <div class="result-header">
              <span class="result-type">{{ result.type }}</span>
              <span class="result-confidence">置信度: {{ (result.confidence * 100).toFixed(1) }}%</span>
            </div>
            <div class="result-details">
              <div v-if="result.bbox" class="bbox-info">
                <span>边界框: ({{ result.bbox.x }}, {{ result.bbox.y }}, {{ result.bbox.width }}, {{ result.bbox.height
                  }})</span>
              </div>
              <div v-if="result.attributes" class="attributes">
                <div v-for="(value, key) in result.attributes" :key="key" class="attribute">
                  <span class="attr-key">{{ key }}:</span>
                  <span class="attr-value">{{ value }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 图像信息 -->
      <el-card class="detail-card" v-if="event.image_url || event.video_url">
        <template #header>
          <span>媒体信息</span>
        </template>

        <div class="media-info">
          <div v-if="event.image_url" class="image-section">
            <h4>事件图像</h4>
            <div class="image-container">
              <el-image :src="event.image_url" :preview-src-list="[event.image_url]" fit="contain"
                style="width: 200px; height: 150px;" />
            </div>
          </div>

          <div v-if="event.video_url" class="video-section">
            <h4>事件视频</h4>
            <div class="video-container">
              <video :src="event.video_url" controls style="width: 300px; height: 200px;">
                您的浏览器不支持视频播放
              </video>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 处理记录 -->
      <el-card class="detail-card" v-if="event.processing_records">
        <template #header>
          <span>处理记录</span>
        </template>

        <div class="processing-records">
          <div class="record-header">
            <span class="record-time">{{ formatDateTime(event.processing_records.processed_at) }}</span>
            <el-tag :type="getActionTagType(event.processing_records.processing_result)" size="small">
              {{ getActionText(event.processing_records.processing_result) }}
            </el-tag>
          </div>
          <div class="record-content">
            <div class="record-operator">操作人: {{ event.processing_records.processing_by || '管理员' }}</div>
            <div class="record-comment" v-if="event.processing_records.processing_comment">
              备注: {{ event.processing_records.processing_comment }}
            </div>
          </div>
        </div>
      </el-card>

      <!-- 转发记录 -->
      <el-card class="detail-card" v-if="event.forward_records && event.forward_records.length > 0">
        <template #header>
          <span>转发记录</span>
        </template>

        <div class="forward-records">
          <div v-for="(record, index) in event.forward_records" :key="index" class="record-item">
            <div class="record-header">
              <span class="record-time">{{ formatDateTime(record.timestamp) }}</span>
              <el-tag :type="record.success ? 'success' : 'danger'" size="small">
                {{ record.success ? '成功' : '失败' }}
              </el-tag>
            </div>
            <div class="record-content">
              <div class="record-target">目标: {{ record.target_url }}</div>
              <div class="record-message" v-if="record.message">
                消息: {{ record.message }}
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <div v-else class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
        <el-button type="primary" @click="processEvent" v-if="event && event.status === 'pending'">
          处理事件
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

// Props
const props = defineProps({
  modelValue: Boolean,
  event: Object
})

// Emits
const emit = defineEmits(['update:modelValue', 'process'])

// 计算属性
const event = computed(() => props.event)

// 方法
const processEvent = () => {
  emit('process', event.value)
  emit('update:modelValue', false)
}

// 工具方法
const getEventTypeTagType = (type) => {
  const types = {
    alarm: 'danger',
    smart: 'primary',
    number_stat: 'success',
    motion: 'warning',
    face: 'success',
    vehicle: 'info'
  }
  return types[type] || 'info'
}

const getEventTypeText = (type) => {
  const texts = {
    alarm: '报警事件',
    smart: '智能事件',
    number_stat: '人数统计',
    motion: '运动检测',
    face: '人脸识别',
    vehicle: '车辆检测'
  }
  return texts[type] || type
}

const getStatusTagType = (status) => {
  const types = {
    pending: 'warning',
    processed: 'success',
    ignored: 'info'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    pending: '未处理',
    processed: '已处理',
    ignored: '已忽略'
  }
  return texts[status] || '未知'
}

const getPriorityTagType = (priority) => {
  const types = {
    high: 'danger',
    medium: 'warning',
    low: 'info',
    normal: 'info'
  }
  return types[priority] || 'info'
}

const getPriorityText = (priority) => {
  const texts = {
    high: '高优先级',
    medium: '中优先级',
    low: '低优先级',
    normal: '普通'
  }
  return texts[priority] || '未知'
}

const getActionTagType = (action) => {
  const types = {
    normal: 'primary',
    false_alarm: 'danger',
    investigation_needed: 'warning',
    resolved: 'success',
    other: 'info'
  }
  return types[action] || 'info'
}

const getActionText = (action) => {
  const texts = {
    normal: '正常',
    false_alarm: '误报',
    investigation_needed: '需要进一步调查',
    resolved: '已解决',
    other: '其他'
  }
  return texts[action] || '未知'
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  return new Date(dateTime).toLocaleString('zh-CN')
}

const formatJson = (jsonString) => {
  try {
    const parsed = typeof jsonString === 'string' ? JSON.parse(jsonString) : jsonString
    return JSON.stringify(parsed, null, 2)
  } catch {
    return jsonString
  }
}
</script>

<style scoped>
.event-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.detail-card {
  margin-bottom: 16px;
}

.detail-card:last-child {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.event-data {
  max-height: 200px;
  overflow-y: auto;
}

.data-content pre {
  margin: 0;
  font-size: 12px;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.no-data {
  padding: 20px 0;
}

.detection-results {
  max-height: 300px;
  overflow-y: auto;
}

.result-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 8px;
}

.result-item:last-child {
  margin-bottom: 0;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.result-type {
  font-weight: 500;
  color: #303133;
}

.result-confidence {
  font-size: 12px;
  color: #909399;
}

.result-details {
  font-size: 14px;
  color: #606266;
}

.bbox-info {
  margin-bottom: 4px;
}

.attributes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.attribute {
  display: flex;
  align-items: center;
  gap: 4px;
}

.attr-key {
  font-weight: 500;
  color: #303133;
}

.attr-value {
  color: #606266;
}

.media-info {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.image-section,
.video-section {
  flex: 1;
  min-width: 200px;
}

.image-section h4,
.video-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.image-container,
.video-container {
  display: flex;
  justify-content: center;
}

.processing-records,
.forward-records {
  max-height: 300px;
  overflow-y: auto;
}

.record-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 8px;
}

.record-item:last-child {
  margin-bottom: 0;
}

.record-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.record-time {
  font-size: 12px;
  color: #909399;
}

.record-content {
  font-size: 14px;
  color: #606266;
}

.record-operator {
  margin-bottom: 4px;
}

.record-comment,
.record-target,
.record-message {
  font-style: italic;
}

.loading-container {
  padding: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

:deep(.el-descriptions__label) {
  font-weight: 500;
  width: 120px;
}

:deep(.el-descriptions__content) {
  word-break: break-all;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog{
  z-index: 999999 !important;
}
</style> 