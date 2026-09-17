<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="事件订阅详情"
    width="900px" top="5vh"
    :z-index="999999"
    append-to-body
    class="high-priority-dialog"
  >
    <div v-if="scheme" class="scheme-detail">
      <!-- 基本信息 -->
      <el-card class="detail-card">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
            <el-tag :type="getStatusTagType(scheme.status)">
              {{ getStatusText(scheme.status) }}
            </el-tag>
          </div>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="摄像机">
            <div class="camera-name">
              {{ scheme.camera_name }}
              <el-tag v-if="scheme.is_default" size="small" type="success" style="margin-left: 8px;">默认</el-tag>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="监听端口">
            {{ scheme.camera_port || 37777 }}
          </el-descriptions-item>
          <el-descriptions-item label="订阅ID">
            {{ scheme.id }}
          </el-descriptions-item>
          <el-descriptions-item label="订阅事件类型">
            <div class="event-types">
              <el-tag 
                v-for="type in scheme.event_types" 
                :key="type"
                :type="getEventTypeTagType(type)"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ getEventTypeText(type) }}
              </el-tag>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDateTime(scheme.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(scheme.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="事件数量">
            <span class="event-count">{{ scheme.event_count || 0 }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="订阅备注">
            {{ scheme.remarks || '暂无备注' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 推送配置 -->
      <el-card class="detail-card">
        <template #header>
          <span>推送配置</span>
        </template>
        
        <el-descriptions :column="1" border>
          <el-descriptions-item label="推送标签">
            <div class="push-tags">
              <el-tag 
                v-for="tag in scheme.push_tags?.split(',')" 
                :key="tag"
                type="info"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ tag.trim() }}
              </el-tag>
              <span v-if="!scheme.push_tags" class="no-tags">无推送标签</span>
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 运行状态 -->
      <el-card class="detail-card">
        <template #header>
          <span>运行状态</span>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="运行状态">
            <el-tag :type="getStatusTagType(scheme.status)">
              {{ getStatusText(scheme.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="启动时间">
            {{ formatDateTime(scheme.started_at) || '未启动' }}
          </el-descriptions-item>
          <el-descriptions-item label="运行时长">
            {{ formatDuration(scheme.runtime_duration) || '未运行' }}
          </el-descriptions-item>
          <el-descriptions-item label="最后心跳">
            {{ formatDateTime(scheme.last_heartbeat) || '无心跳' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 最近事件 -->
      <el-card class="detail-card">
        <template #header>
          <div class="card-header">
            <span>最近事件</span>
            <el-button size="small" @click="viewAllEvents">查看全部</el-button>
          </div>
        </template>
        
        <div v-if="recentEvents.length > 0" class="recent-events">
          <div 
            v-for="event in recentEvents" 
            :key="event.id" 
            class="event-item"
          >
            <div class="event-header">
              <el-tag :type="getEventTypeTagType(event.event_type)" size="small">
                {{ getEventTypeText(event.event_type) }}
              </el-tag>
              <span class="event-time">{{ formatDateTime(event.timestamp) }}</span>
            </div>
            <div class="event-content">
              <div class="event-title">{{ event.title }}</div>
              <div class="event-description">{{ event.description }}</div>
            </div>
          </div>
        </div>
        <div v-else class="no-events">
          <el-empty description="暂无事件" />
        </div>
      </el-card>
    </div>

    <div v-else class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import smartSchemeApi from '@/api/smart_scheme'

// Props
const props = defineProps({
  modelValue: Boolean,
  scheme: Object
})

// Emits
const emit = defineEmits(['update:modelValue', 'edit'])

// 路由实例
const router = useRouter()

// 响应式数据
const recentEvents = ref([])

// 监听器
watch(() => props.modelValue, async (newVal) => {
  if (newVal && props.scheme) {
    await loadRecentEvents()
  }
})

// 方法
const loadRecentEvents = async () => {
  try {
    const response = await smartSchemeApi.getSmartEvents({
      scheme_id: props.scheme.id,
      limit: 5
    })
    recentEvents.value = response.data.items || []
  } catch (error) {
    console.error('加载最近事件失败:', error)
  }
}

const viewAllEvents = () => {
  router.push({
    path: '/smart-schemes',
    query: {
      tab: 'events',
      scheme_id: props.scheme.id
    }
  })
}

// 工具方法
const getStatusTagType = (status) => {
  const types = {
    running: 'success',
    stopped: 'info',
    error: 'danger'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    running: '运行中',
    stopped: '已停止',
    error: '错误'
  }
  return texts[status] || '未知'
}

const getEventTypeTagType = (type) => {
  const types = {
    alarm: 'danger',
    smart: 'primary',
    number_stat: 'success',
    system_log: 'info'
  }
  return types[type] || 'info'
}

const getEventTypeText = (type) => {
  const texts = {
    alarm: '报警事件',
    smart: '智能事件',
    number_stat: '人数统计',
    system_log: '设备日志'
  }
  return texts[type] || type
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  return new Date(dateTime).toLocaleString('zh-CN')
}

const formatDuration = (seconds) => {
  if (!seconds) return ''
  
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  
  if (hours > 0) {
    return `${hours}小时${minutes}分钟${secs}秒`
  } else if (minutes > 0) {
    return `${minutes}分钟${secs}秒`
  } else {
    return `${secs}秒`
  }
}

</script>

<style scoped>
.scheme-detail {
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

.scheme-name {
  display: flex;
  align-items: center;
}

.event-count {
  font-weight: 600;
  color: #409EFF;
}

.event-types {
  display: flex;
  flex-wrap: wrap;
}

.event-filter {
  max-height: 100px;
  overflow-y: auto;
}

.event-filter pre {
  margin: 0;
  font-size: 12px;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.no-filter {
  color: #909399;
  font-style: italic;
}

.forward-template {
  max-height: 100px;
  overflow-y: auto;
}

.forward-template pre {
  margin: 0;
  font-size: 12px;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.recent-events {
  max-height: 300px;
  overflow-y: auto;
}

.event-item {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 8px;
}

.event-item:last-child {
  margin-bottom: 0;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.event-time {
  font-size: 12px;
  color: #909399;
}

.event-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.event-description {
  font-size: 14px;
  color: #606266;
  line-height: 1.4;
}

.no-events {
  padding: 20px 0;
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
.high-priority-dialog {
  z-index: 999999 !important;
}
</style> 