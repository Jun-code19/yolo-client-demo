<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="处理事件"
    width="30%" top="5vh"
    :close-on-click-modal="false"
    :z-index="999999"
    append-to-body
    class="high-priority-dialog"
  >
    <div v-if="event" class="event-process">
      <!-- 事件信息 -->
      <el-card class="event-info-card">
        <template #header>
          <span>事件信息</span>
        </template>
        
        <el-descriptions :column="1" border>
          <el-descriptions-item label="事件标题">
            {{ event.title }}
          </el-descriptions-item>
          <el-descriptions-item label="事件类型">
            <el-tag :type="getEventTypeTagType(event.event_type)">
              {{ getEventTypeText(event.event_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="摄像机">
            {{ event.camera_name }}
          </el-descriptions-item>
          <el-descriptions-item label="摄像机IP">
            {{ event.camera_ip }}
          </el-descriptions-item>
          <el-descriptions-item label="发生时间">
            {{ formatDateTime(event.timestamp) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 处理表单 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
        class="process-form"
      >
        <el-form-item label="处理方式" prop="action">
          <el-radio-group v-model="form.action">
            <el-radio label="process">标记为已处理</el-radio>
            <el-radio label="ignore">标记为已忽略</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="处理结果" prop="result">
          <el-select v-model="form.result" placeholder="请选择处理结果" style="width: 100%" popper-append-to-body>
            <el-option label="正常" value="normal" />
            <el-option label="误报" value="false_alarm" />
            <el-option label="需要进一步调查" value="investigation_needed" />
            <el-option label="已解决" value="resolved" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>

        <el-form-item label="处理备注" prop="comment">
          <el-input
            v-model="form.comment"
            type="textarea"
            :rows="4"
            placeholder="请输入处理备注信息"
          />
        </el-form-item>
      </el-form>
    </div>

    <div v-else class="loading-container">
      <el-skeleton :rows="6" animated />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          确认处理
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import smartSchemeApi from '@/api/smart_scheme'

// Props
const props = defineProps({
  modelValue: Boolean,
  event: Object
})

// Emits
const emit = defineEmits(['update:modelValue', 'success'])

// 响应式数据
const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  action: 'process',
  result: '',
  comment: '',
})

// 表单验证规则
const rules = {
  action: [
    { required: true, message: '请选择处理方式', trigger: 'change' }
  ],
  result: [
    { required: true, message: '请选择处理结果', trigger: 'change' }
  ],
}

// 计算属性
const event = computed(() => props.event)

// 监听器
watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    nextTick(() => {
      initForm()
    })
  }
})

// 方法
const initForm = () => {
  // 重置表单
  form.action = 'process'
  form.result = ''
  form.comment = ''
}

const submitForm = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    submitting.value = true
    
    const processData = {
      status: form.action === 'process' ? 'processed' : 'ignored',
      processing_result: form.result,
      processing_comment: form.comment
    }
    
    await smartSchemeApi.updateSmartEvent(event.value.id, processData)
    ElMessage.success('事件处理成功')
    emit('success')
  } catch (error) {
    if (error !== false) { // 不是表单验证错误
      console.error('处理失败:', error)
      ElMessage.error('处理失败')
    }
  } finally {
    submitting.value = false
  }
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

const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  return new Date(dateTime).toLocaleString('zh-CN')
}
</script>

<style scoped>
.event-process {
  max-height: 70vh;
  overflow-y: auto;
}

.event-info-card {
  margin-bottom: 20px;
}

.process-form {
  margin-top: 20px;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
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

:deep(.el-form-item__label) {
  font-weight: 500;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}
</style> 