<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑规则' : '新建规则'"
    width="50%"
    top="5vh"
    destroy-on-close
    append-to-body
    class="rule-dialog high-priority-dialog"
    @closed="handleClosed"
  >
    <div v-loading="referenceLoading" class="dialog-body">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-divider content-position="left">基本信息</el-divider>

        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：区域入侵 + 订阅事件" />
        </el-form-item>

        <div class="form-row-2">
          <el-form-item label="设备">
            <el-select
              v-model="form.device_id"
              clearable
              filterable
              placeholder="全部"
              class="w-full"
              popper-class="rule-select-popper"
            >
              <el-option
                v-for="device in deviceList"
                :key="device.device_id"
                :label="formatDeviceLabel(device)"
                :value="device.device_id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="推送标签">
            <el-select
              v-model="form.push_tags"
              clearable
              filterable
              allow-create
              default-first-option
              placeholder="匹配推送配置"
              class="w-full"
              popper-class="rule-select-popper"
            >
              <el-option v-for="tag in pushTagOptions" :key="tag" :label="tag" :value="tag" />
            </el-select>
          </el-form-item>
        </div>

        <div class="form-row-3">
          <el-form-item label="启用">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number v-model="form.priority" :min="0" :max="10000" controls-position="right" class="w-full" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" placeholder="可选" />
          </el-form-item>
        </div>

        <el-divider content-position="left">匹配逻辑</el-divider>

        <div class="form-row-2">
          <el-form-item label="组合">
            <el-radio-group v-model="form.definition.logic">
              <el-radio-button value="AND">全部满足</el-radio-button>
              <el-radio-button value="OR">任一满足</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="同设备">
            <el-switch v-model="form.definition.same_device" />
          </el-form-item>
        </div>

        <div class="form-row-2 timing-row">
          <el-form-item label="窗口">
            <el-input-number
              v-model="form.definition.window_sec"
              :min="10"
              :max="86400"
              :disabled="form.definition.logic === 'OR'"
              controls-position="right"
              class="w-full"
            />
          </el-form-item>
          <el-form-item label="冷却">
            <el-input-number v-model="form.definition.cooldown_sec" :min="0" :max="86400" controls-position="right" class="w-full" />
          </el-form-item>
        </div>

        <el-divider content-position="left">
          <span>触发条件</span>
          <el-button type="primary" link class="divider-btn" @click="addCondition">添加</el-button>
        </el-divider>

        <div v-for="(cond, index) in form.definition.conditions" :key="index" class="cond-block">
          <div class="cond-row">
            <span class="cond-idx">{{ index + 1 }}</span>
            <el-select
              v-model="cond.source"
              class="cond-source"
              popper-class="rule-select-popper"
              @change="resetConditionFields(cond)"
            >
              <el-option v-for="opt in SOURCE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>

            <template v-if="cond.source === 'detection_event'">
              <el-select
                v-model="cond.match_mode"
                placeholder="匹配方式"
                class="cond-field"
                popper-class="rule-select-popper"
                @change="onDetectionMatchModeChange(cond)"
              >
                <el-option v-for="opt in DETECTION_MATCH_MODES" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <template v-if="cond.match_mode === 'target' || cond.match_mode === 'absence'">
                <el-select
                  v-model="cond.target_classes"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  clearable
                  filterable
                  allow-create
                  placeholder="目标类别"
                  class="cond-field"
                  popper-class="rule-select-popper"
                >
                  <el-option v-for="opt in TARGET_CLASS_PRESETS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <template v-if="cond.match_mode === 'target'">
                  <el-select v-model="cond.count_op" placeholder="数量" class="cond-field cond-field-sm" popper-class="rule-select-popper">
                    <el-option v-for="opt in COUNT_OPS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <el-input-number v-model="cond.count_value" :min="0" :max="9999" controls-position="right" class="cond-field cond-field-sm" />
                </template>
              </template>
              <template v-else>
                <el-select
                  v-model="cond.scenario_type"
                  clearable
                  filterable
                  placeholder="场景类型"
                  class="cond-field"
                  popper-class="rule-select-popper"
                >
                  <el-option v-for="opt in SCENARIO_TYPES" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-select
                  v-model="cond.label"
                  clearable
                  filterable
                  allow-create
                  placeholder="子事件类型"
                  class="cond-field"
                  popper-class="rule-select-popper"
                >
                  <el-option
                    v-for="opt in DETECTION_META_EVENT_TYPES"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </template>
            </template>

            <template v-else-if="cond.source === 'smart_event'">
              <el-select
                v-model="cond.scheme_id"
                clearable
                filterable
                placeholder="订阅方案"
                class="cond-field"
                popper-class="rule-select-popper"
              >
                <el-option
                  v-for="scheme in smartSchemes"
                  :key="scheme.id"
                  :label="formatSchemeLabel(scheme)"
                  :value="scheme.id"
                />
              </el-select>
              <el-select
                v-model="cond.event_type"
                clearable
                filterable
                placeholder="订阅事件类型"
                class="cond-field"
                popper-class="rule-select-popper"
              >
                <el-option v-for="opt in SMART_EVENT_TYPES" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </template>

            <template v-if="shouldShowConditionDuration(cond)">
              <span class="cond-duration-label">持续</span>
              <el-input-number
                v-model="cond.duration_sec"
                :min="0"
                :max="86400"
                controls-position="right"
                class="cond-field cond-field-sm"
              />
            </template>

            <el-button
              type="danger"
              link
              :disabled="form.definition.conditions.length <= 1"
              class="cond-del"
              @click="removeCondition(index)"
            >
              删除
            </el-button>
          </div>
        </div>
      </el-form>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import alertRuleApi, {
  SOURCE_OPTIONS,
  DETECTION_META_EVENT_TYPES,
  DETECTION_MATCH_MODES,
  COUNT_OPS,
  TARGET_CLASS_PRESETS,
  SCENARIO_TYPES,
  SMART_EVENT_TYPES,
  defaultCondition,
  defaultDefinition,
  conditionSupportsDuration,
  normalizeListResponse
} from '@/api/alert_rule'
import deviceApi from '@/api/device'
import smartSchemeApi from '@/api/smart_scheme'
import { usePushConfigTags } from '@/composables/usePushConfigTags'

const emit = defineEmits(['saved'])

const visible = ref(false)
const isEdit = ref(false)
const editingId = ref('')
const submitting = ref(false)
const referenceLoading = ref(false)
const formRef = ref(null)
const deviceList = ref([])
const smartSchemes = ref([])
const { pushTagOptions, loadPushConfigTags } = usePushConfigTags()

const form = reactive({
  name: '',
  description: '',
  enabled: true,
  device_id: '',
  priority: 100,
  push_tags: '',
  definition: defaultDefinition()
})

const rules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }]
}

const formatDeviceLabel = (device) => {
  const name = device.device_name || device.device_id
  return device.ip_address ? `${name} (${device.ip_address})` : name
}

const formatSchemeLabel = (scheme) => {
  const name = scheme.camera_name || scheme.camera_id || scheme.id
  const types = (scheme.event_types || []).join('/')
  return types ? `${name} (${types})` : name
}

const shouldShowConditionDuration = (cond) => conditionSupportsDuration(cond)

const resetConditionFields = (cond) => {
  const source = cond.source
  const defaults = defaultCondition()
  Object.assign(cond, {
    ...defaults,
    source,
    needs_alert_only: false,
  })
}

const onDetectionMatchModeChange = (cond) => {
  if (cond.match_mode === 'target' || cond.match_mode === 'absence') {
    cond.label = ''
    cond.scenario_type = ''
    cond.event_type = ''
    if (!Array.isArray(cond.target_classes)) cond.target_classes = []
    if (!cond.count_op) cond.count_op = 'gte'
    if (cond.count_value == null) cond.count_value = 1
  } else {
    cond.target_classes = []
    cond.count_op = 'gte'
    cond.count_value = 1
    cond.event_type = ''
    cond.duration_sec = 0
  }
}

const addCondition = () => {
  form.definition.conditions.push(defaultCondition())
}

const removeCondition = (index) => {
  form.definition.conditions.splice(index, 1)
}

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.enabled = true
  form.device_id = ''
  form.priority = 100
  form.push_tags = ''
  form.definition = defaultDefinition()
}

const loadReferenceData = async () => {
  referenceLoading.value = true
  try {
    const results = await Promise.allSettled([
      deviceApi.getDevices({ skip: 0, limit: 500 }),
      smartSchemeApi.getSchemes({ page: 1, page_size: 500 }),
      loadPushConfigTags()
    ])

    if (results[0].status === 'fulfilled') {
      deviceList.value = normalizeListResponse(results[0].value.data)
    } else {
      deviceList.value = []
    }

    if (results[1].status === 'fulfilled') {
      smartSchemes.value = normalizeListResponse(results[1].value.data)
    } else {
      smartSchemes.value = []
    }
  } catch {
    deviceList.value = []
    smartSchemes.value = []
    ElMessage.warning('选项加载失败，请确认服务已启动')
  } finally {
    referenceLoading.value = false
  }
}

const openCreate = async () => {
  isEdit.value = false
  editingId.value = ''
  resetForm()
  visible.value = true
  await loadReferenceData()
}

const openEdit = async (row) => {
  isEdit.value = true
  editingId.value = row.rule_id
  form.name = row.name
  form.description = row.description || ''
  form.enabled = row.enabled
  form.device_id = row.device_id || ''
  form.priority = row.priority ?? 100
  form.push_tags = row.push_tags || ''
  form.definition = {
    ...defaultDefinition(),
    ...(row.definition || {}),
    conditions: (row.definition?.conditions?.length ? row.definition.conditions : [defaultCondition()]).map(item => {
      const merged = {
        ...defaultCondition(),
        ...item,
        needs_alert_only: false,
        target_classes: Array.isArray(item.target_classes) ? [...item.target_classes] : [],
        match_mode: item.match_mode || (item.label ? 'event' : 'target'),
        count_op: item.count_op || 'gte',
        count_value: item.count_value ?? 1,
        duration_sec: item.duration_sec ?? row.definition?.duration_sec ?? 0,
      }
      if ((!merged.labels || !merged.labels.length) && merged.label) {
        merged.labels = [merged.label]
      }
      if (!Array.isArray(merged.labels)) {
        merged.labels = []
      }
      return merged
    })
  }
  visible.value = true
  await loadReferenceData()
}

const cleanCondition = (cond) => {
  const supportsDuration = conditionSupportsDuration(cond)
  const payload = {
    source: cond.source,
    duration_sec: supportsDuration ? (Number(cond.duration_sec) || 0) : 0,
  }
  if (cond.source === 'detection_event') {
    payload.match_mode = cond.match_mode || 'event'
    if (cond.scenario_type) payload.scenario_type = cond.scenario_type
    if (cond.scenario_id) payload.scenario_id = cond.scenario_id
    if (cond.analysis_type) payload.analysis_type = cond.analysis_type
    if (payload.match_mode === 'target' || payload.match_mode === 'absence') {
      if (Array.isArray(cond.target_classes) && cond.target_classes.length) {
        payload.target_classes = cond.target_classes.map(item => String(item).trim()).filter(Boolean)
      }
      if (payload.match_mode === 'target') {
        if (cond.count_op) payload.count_op = cond.count_op
        if (cond.count_value != null && cond.count_value !== '') payload.count_value = cond.count_value
      }
    } else if (cond.label) {
      payload.label = cond.label
    }
  } else if (cond.source === 'smart_event') {
    if (cond.scheme_id) payload.scheme_id = cond.scheme_id
    if (cond.event_type) payload.event_type = cond.event_type
    if (cond.label) payload.label = cond.label
  } else {
    if (cond.event_type) payload.event_type = cond.event_type
    if (cond.label) payload.label = cond.label
  }
  return payload
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate()
  if (!form.definition.conditions.length) {
    ElMessage.warning('请至少添加一个条件')
    return
  }

  const payload = {
    name: form.name,
    description: form.description || null,
    enabled: form.enabled,
    device_id: form.device_id || null,
    priority: form.priority,
    push_tags: form.push_tags || null,
    definition: {
      logic: form.definition.logic,
      same_device: form.definition.same_device,
      window_sec: form.definition.window_sec,
      duration_sec: form.definition.duration_sec,
      cooldown_sec: form.definition.cooldown_sec,
      conditions: form.definition.conditions.map(cleanCondition)
    }
  }

  submitting.value = true
  try {
    if (isEdit.value) {
      await alertRuleApi.updateRule(editingId.value, payload)
      ElMessage.success('规则已更新')
    } else {
      await alertRuleApi.createRule(payload)
      ElMessage.success('规则已创建')
    }
    visible.value = false
    emit('saved')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    submitting.value = false
  }
}

const handleClosed = () => {
  formRef.value?.resetFields()
}

defineExpose({ openCreate, openEdit })
</script>

<style scoped>
.dialog-body {
  max-height: calc(80vh - 120px);
  overflow-x: hidden;
  overflow-y: auto;
}

.w-full {
  width: 100%;
}

.form-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

.form-row-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0 12px;
}

.timing-row :deep(.el-form-item__label) {
  font-size: 12px;
}

.divider-btn {
  margin-left: 8px;
  vertical-align: baseline;
}

.cond-block {
  border-bottom: 1px solid #f0f2f5;
}

.cond-block:last-child {
  border-bottom: none;
}

.cond-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}

.cond-idx {
  flex: 0 0 20px;
  font-size: 12px;
  color: #909399;
  text-align: center;
}

.cond-source {
  width: 120px;
  flex-shrink: 0;
}

.cond-field {
  flex: 1;
  min-width: 100px;
}

.cond-field-sm {
  flex: 0 0 88px;
  min-width: 72px;
  max-width: 120px;
}

.cond-check {
  flex-shrink: 0;
  margin-right: 4px;
}

.cond-del {
  margin-left: auto;
  flex-shrink: 0;
}

.cond-duration-label {
  font-size: 12px;
  color: #606266;
  flex-shrink: 0;
}

:deep(.el-divider) {
  margin: 20px 0 16px;
}

:deep(.el-divider__text) {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

:deep(.el-form-item) {
  margin-bottom: 18px;
}

:deep(.el-input-number.w-full) {
  width: 100%;
}
</style>

<style>
.rule-dialog .el-dialog__body {
  padding: 16px 20px 8px;
  overflow-x: hidden;
}

.high-priority-dialog {
  z-index: 999999 !important;
}

.rule-select-popper {
  z-index: 1000000 !important;
}
</style>
