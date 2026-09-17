<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    :title="isEdit ? '编辑事件订阅' : '新建事件订阅'"
    width="800px"
    :close-on-click-modal="false"
    :z-index="999999"
    append-to-body
    class="high-priority-dialog"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      v-loading="loading"
    >
      <!-- 基本信息 -->
      <el-divider content-position="left">基本信息</el-divider>
      
      <el-form-item label="摄像机" prop="camera_id">
        <el-select v-model="form.camera_id" placeholder="请选择摄像机" style="width: 100%" popper-append-to-body filterable>
          <el-option
            v-for="camera in cameras"
            :key="camera.id"
            :label="camera.name"
            :value="camera.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="监听端口" prop="camera_port">
        <el-input-number 
          v-model="form.camera_port" 
          :min="1" 
          :max="65535" 
          placeholder="请输入端口号"
          style="width: 100%"
        />
        <div class="form-tip">默认端口：37777</div>
      </el-form-item>

      <!-- 事件订阅配置 -->
      <el-divider content-position="left">事件订阅配置</el-divider>
      
      <el-form-item label="订阅事件" prop="event_types">
        <el-checkbox-group v-model="form.event_types">
          <el-checkbox label="alarm">报警事件</el-checkbox>
          <el-checkbox label="smart">智能事件</el-checkbox>
          <el-checkbox label="number_stat">人数统计</el-checkbox>
          <el-checkbox label="system_log">设备日志</el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <el-form-item label="报警间隔" prop="alarm_interval" v-if="form.event_types.includes('number_stat')">
        <el-input-number 
          v-model="form.alarm_interval" 
          :min="0" 
          :max="3600" 
          placeholder="请输入报警间隔时间(秒)"
          style="width: 100%"
        />
        <div class="form-tip">0表示不限制间隔时间，建议设置为60-300秒</div>
      </el-form-item>

      <!-- 推送配置 -->
      <el-divider content-position="left">推送配置</el-divider>
      
      <el-form-item label="推送标签" prop="push_tags">
        <el-select
          v-model="pushTagsArray"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          collapse-tags-tooltip
          placeholder="选择或输入推送标签"
          style="width: 100%"
          popper-append-to-body
        >
          <el-option
            v-for="tag in pushTagOptions"
            :key="tag"
            :label="tag"
            :value="tag"
          />
        </el-select>
        <div class="form-tip">
          默认 <code>subscribe_event</code>，需与「数据推送配置」中的标签一致才会投递
        </div>
      </el-form-item>

      <!-- 备注信息 -->
      <el-divider content-position="left">备注信息</el-divider>
      
      <el-form-item label="备注" prop="remarks">
        <el-input
          v-model="form.remarks"
          type="textarea"
          :rows="3"
          placeholder="请输入备注信息"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          {{ isEdit ? '更新' : '创建' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import smartSchemeApi from '@/api/smart_scheme'
import { usePushConfigTags } from '@/composables/usePushConfigTags'
import { DEFAULT_SUBSCRIBE_PUSH_TAG } from '@/constants/pushTags'
// Props
const props = defineProps({
  modelValue: Boolean,
  scheme: Object,
  cameras: {
    type: Array,
    default: () => []
  }
})

// Emits
const emit = defineEmits(['update:modelValue', 'success'])

// 响应式数据
const formRef = ref(null)
const loading = ref(false)
const submitting = ref(false)
const { pushTagOptions, loadPushConfigTags } = usePushConfigTags()

const pushTagsArray = computed({
  get() {
    return form.push_tags
      ? form.push_tags.split(',').map((t) => t.trim()).filter(Boolean)
      : []
  },
  set(values) {
    form.push_tags = (values || [])
      .map((t) => String(t).trim())
      .filter(Boolean)
      .join(',')
  },
})
const form = reactive({
  camera_id: null,
  camera_port: 37777,
  // event_types: ['alarm', 'smart', 'system_log'],
  event_types: ['system_log'],
  alarm_interval: 60,
  push_tags: '',
  remarks: ''
})

// 表单验证规则
const rules = {
  camera_id: [
    { required: true, message: '请选择摄像机', trigger: 'change' }
  ],
  camera_port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
    { type: 'number', min: 1, max: 65535, message: '端口号必须在1-65535之间', trigger: 'blur' }
  ],
  event_types: [
    { required: true, message: '请选择至少一个事件类型', trigger: 'change' }
  ],
  alarm_interval: [
    { type: 'number', min: 0, max: 3600, message: '报警间隔时间必须在0-3600秒之间', trigger: 'blur' }
  ]
}

// 计算属性
const isEdit = computed(() => !!props.scheme)

// 监听器
watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    nextTick(() => {
      initForm()
      loadPushConfigTags()
    })
  }
})
// 方法
const initForm = () => {
  if (props.scheme) {
    // 编辑模式，填充表单数据
    Object.keys(form).forEach(key => {
      if (props.scheme[key] !== undefined) {
        form[key] = props.scheme[key]
      }
    })
  } else {
    // 新建模式，重置表单
    Object.keys(form).forEach(key => {
      if (key === 'event_types') {
        // form[key] = ['alarm', 'smart', 'system_log']
        form[key] = ['system_log']
      } else if (key === 'camera_port') {
        form[key] = 37777
      } else if (key === 'alarm_interval') {
        form[key] = 60
      } else if (key === 'push_tags') {
        form[key] = DEFAULT_SUBSCRIBE_PUSH_TAG
      } else {
        form[key] = ''
      }    })
  }
}

const handleCameraChange = (cameraId) => {
  if (cameraId) {
    const selectedCamera = props.cameras.find(camera => camera.id === cameraId)
    if (selectedCamera && selectedCamera.port) {
      form.camera_port = selectedCamera.port
    }
  }
}

const submitForm = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
    submitting.value = true
    
    const submitData = { ...form }
    
    if (isEdit.value) {
      await smartSchemeApi.updateScheme(props.scheme.id, submitData)
      ElMessage.success('事件订阅更新成功')
    } else {
      await smartSchemeApi.createScheme(submitData)
      ElMessage.success('事件订阅创建成功')
    }
    
    emit('success')
  } catch (error) {
    if (error !== false) { // 不是表单验证错误
      console.error('提交失败:', error)
      ElMessage.error('提交失败')
    }
  } finally {
    submitting.value = false
  }
}


</script>

<style scoped>
.form-tip code {
  font-size: 11px;
  color: #606266;
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
}

.form-tip {  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

:deep(.el-divider__text) {
  font-weight: 600;
  color: #409EFF;
}

:deep(.el-form-item__label) {
  font-weight: 500;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}
</style> 