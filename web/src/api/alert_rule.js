import axios from 'axios'
import { ElMessage } from 'element-plus'

const apiClient = axios.create({
  baseURL: '/api/v1/alert-rules',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000
})

apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      ElMessage.error('登录已过期，请重新登录')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const SOURCE_OPTIONS = [
  { value: 'detection_event', label: '检测事件' },
  { value: 'smart_event', label: '事件订阅' }
]

export const SOURCE_LABELS = Object.fromEntries(SOURCE_OPTIONS.map(item => [item.value, item.label]))

export const DETECTION_EVENT_TYPES = [
  { value: 'smart_person', label: '智能人员场景' },
  { value: 'smart_behavior', label: '智能行为' },
  { value: 'smart_counting', label: '人数统计' },
  { value: 'detection', label: '普通检测' },
]

export const SCENARIO_TYPES = [
  { value: 'leave_post', label: '离岗检测' },
  { value: 'crowd_gather', label: '聚众检测' },
  { value: 'loitering', label: '徘徊检测' },
  { value: 'behavior', label: '行为分析' },
  { value: 'counting', label: '人数统计' }
]

export const DETECTION_MATCH_MODES = [
  { value: 'event', label: '子事件类型' },
  { value: 'target', label: '目标类别/数量' },
  { value: 'absence', label: '持续不在 (NOT)' }
]

export const COUNT_OPS = [
  { value: 'gte', label: '≥' },
  { value: 'gt', label: '>' },
  { value: 'eq', label: '=' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' }
]

export const TARGET_CLASS_PRESETS = [
  { value: 'person', label: '人' },
  { value: 'car', label: '车' }
]

/** 检测事件 meta.event_type 子类型（与 smart_scenarios / run_detection_task 对齐） */
export const DETECTION_META_EVENT_TYPES = [
  { value: 'leave_post_alert', label: '离岗告警' },
  { value: 'crowd_gather_alert', label: '聚众告警' },
  { value: 'loitering_alert', label: '徘徊告警' },
  { value: 'line_cross', label: '越线（任意方向）' },
  { value: 'line_cross_in', label: '越线进入' },
  { value: 'line_cross_out', label: '越线离开' },
  { value: 'area_enter', label: '进入区域' },
  { value: 'area_exit', label: '离开区域' },
  { value: 'occupancy_alert', label: '区域人数超限' },
  { value: 'occupancy_report', label: '区域人数上报' },
  { value: 'occupancy_change_increase', label: '人数增加' },
  { value: 'occupancy_change_decrease', label: '人数减少' }
]

export const EXTERNAL_EVENT_TYPES = [
  { value: 'detection', label: 'detection（算法检测）' },
  { value: 'alarm', label: 'alarm（报警）' },
  { value: 'status', label: 'status（状态）' },
  { value: 'command', label: 'command（指令）' },
  { value: 'heartbeat', label: 'heartbeat（心跳）' },
  { value: 'other', label: 'other（其他）' }
]

export const SMART_EVENT_TYPES = [
  { value: 'alarm', label: '报警事件' },
  { value: 'smart', label: '智能事件' },
  { value: 'number_stat', label: '人数统计' },
  { value: 'system_log', label: '设备日志' }
]

const labelMap = (options) => Object.fromEntries(options.map(o => [o.value, o.label]))

export const DETECTION_EVENT_TYPE_LABELS = labelMap(DETECTION_EVENT_TYPES)
export const SCENARIO_TYPE_LABELS = labelMap(SCENARIO_TYPES)
export const DETECTION_MATCH_MODE_LABELS = labelMap(DETECTION_MATCH_MODES)
export const COUNT_OP_LABELS = labelMap(COUNT_OPS)
export const TARGET_CLASS_LABELS = labelMap(TARGET_CLASS_PRESETS)
export const DETECTION_META_EVENT_LABELS = labelMap(DETECTION_META_EVENT_TYPES)
export const EXTERNAL_EVENT_TYPE_LABELS = labelMap(EXTERNAL_EVENT_TYPES)
export const SMART_EVENT_TYPE_LABELS = labelMap(SMART_EVENT_TYPES)

/** 统一解析列表接口返回（兼容 data / items / 直接数组） */
export function normalizeListResponse(payload) {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.jobs)) return payload.jobs
  return []
}

export const defaultDefinition = () => ({
  logic: 'AND',
  same_device: true,
  window_sec: 300,
  duration_sec: 0,
  cooldown_sec: 60,
  conditions: [defaultCondition()]
})

export const defaultCondition = () => ({
  source: 'detection_event',
  match_mode: 'target',
  label: '',
  labels: [],
  event_type: '',
  target_classes: [],
  count_op: 'gte',
  count_value: 1,
  change_direction: '',
  duration_sec: 0,
  job_id: '',
  needs_alert_only: false,
  scenario_type: '',
  scenario_id: '',
  analysis_type: '',
  scheme_id: ''
})

/** 条件中的展示用标签列表（兼容 label / labels） */
export function getConditionLabels(cond) {
  if (Array.isArray(cond?.labels) && cond.labels.length) {
    return cond.labels.filter(Boolean)
  }
  if (cond?.label) return [cond.label]
  return []
}

/** 是否在该条件上配置持续秒数（仅检测事件的目标类别/NOT） */
export function conditionSupportsDuration(cond) {
  return cond?.source === 'detection_event'
    && (cond.match_mode === 'target' || cond.match_mode === 'absence')
}

/** 格式化单条触发条件（列表/详情展示） */
export function formatConditionText(cond, lookups = {}, options = {}) {
  if (!cond?.source) return '-'
  const { maxLabels } = options
  const sourceLabel = SOURCE_LABELS[cond.source] || cond.source
  const parts = [sourceLabel]

  if (cond.source === 'vlm_finding') {
    parts.push('(已废弃条件)')
    if (cond.job_id) {
      parts.push(cond.job_id)
    }
    const labelList = getConditionLabels(cond)
    if (labelList.length) {
      if (maxLabels && labelList.length > maxLabels) {
        parts.push(`标签:${labelList.slice(0, maxLabels).join('/')}+${labelList.length - maxLabels}`)
      } else {
        parts.push(`标签:${labelList.join('/')}`)
      }
    }
    if (cond.needs_alert_only !== false) parts.push('仅告警')
    return parts.join(' · ')
  }

  if (cond.source === 'detection_event') {
    const modeLabel = DETECTION_MATCH_MODE_LABELS[cond.match_mode] || cond.match_mode
    if (modeLabel) parts.push(modeLabel)
    if (cond.match_mode === 'target' || cond.match_mode === 'absence') {
      const classes = (cond.target_classes || []).map(c => TARGET_CLASS_LABELS[c] || c).filter(Boolean)
      if (classes.length) parts.push(`类别:${classes.join('/')}`)
      if (cond.match_mode === 'target' && cond.count_op && cond.count_value != null && cond.count_value !== '') {
        parts.push(`数量${COUNT_OP_LABELS[cond.count_op] || cond.count_op}${cond.count_value}`)
      }
      if (cond.match_mode === 'absence') parts.push('持续不在')
    } else {
      if (cond.scenario_type) {
        parts.push(SCENARIO_TYPE_LABELS[cond.scenario_type] || cond.scenario_type)
      }
      if (cond.label) {
        parts.push(DETECTION_META_EVENT_LABELS[cond.label] || cond.label)
      }
    }
    if (conditionSupportsDuration(cond) && cond.duration_sec > 0) {
      parts.push(`持续${cond.duration_sec}s`)
    }
    return parts.join(' · ')
  }

  if (cond.source === 'external_event') {
    if (cond.event_type) {
      parts.push(EXTERNAL_EVENT_TYPE_LABELS[cond.event_type] || cond.event_type)
    }
    if (cond.label) parts.push(`引擎:${cond.label}`)
    return parts.join(' · ')
  }

  if (cond.source === 'smart_event') {
    if (cond.scheme_id) {
      const schemeName = lookups.smartSchemes?.[cond.scheme_id]
      parts.push(schemeName || cond.scheme_id)
    }
    if (cond.event_type) {
      parts.push(SMART_EVENT_TYPE_LABELS[cond.event_type] || cond.event_type)
    }
    return parts.join(' · ')
  }

  const extra = cond.label || cond.event_type || cond.scenario_type || ''
  const base = extra ? `${sourceLabel}:${extra}` : sourceLabel
  return base
}

/** 规则列表：多条触发条件 tooltip 全文 */
export function formatConditionsTooltip(conditions, lookups = {}) {
  return (conditions || [])
    .map(cond => formatConditionText(cond, lookups))
    .join('\n')
}

/** 涉及设备展示（列表/详情） */
export function formatInvolvedDevices(alert, deviceMap = {}) {
  const fromApi = Array.isArray(alert?.involved_devices) ? alert.involved_devices : []
  if (fromApi.length) {
    return fromApi.map(item => item.device_name || item.device_id).filter(Boolean)
  }
  const ids = new Set()
  if (alert?.device_id) ids.add(alert.device_id)
  for (const evt of alert?.matched_events || []) {
    if (evt?.device_id) ids.add(evt.device_id)
  }
  return [...ids].map(id => deviceMap[id] || id)
}

/** 匹配事件折叠标题 */
export function formatMatchedEventTitle(evt, deviceMap = {}) {
  const source = SOURCE_LABELS[evt?.source] || evt?.source || '事件'
  const deviceId = evt?.device_id
  const deviceName = deviceId ? (deviceMap[deviceId] || deviceId) : '未知设备'
  const labelPart = (evt?.labels || []).slice(0, 3).join('/') || evt?.event_type || evt?.source_id || '-'
  return `${source} · ${deviceName} · ${labelPart}`
}

/** 匹配事件摘要行（详情抽屉） */
export function formatMatchedEventSummary(evt) {
  const parts = []
  if (evt?.timestamp) {
    parts.push(new Date(evt.timestamp).toLocaleString('zh-CN'))
  }
  if (evt?.event_type) parts.push(evt.event_type)
  if (evt?.payload?.summary) parts.push(String(evt.payload.summary).slice(0, 120))
  else if (evt?.payload?.job_id) parts.push(`任务:${evt.payload.job_id}`)
  return parts.join(' · ') || '-'
}

export const alertRuleApi = {
  getMeta() {
    return apiClient.get('/meta')
  },
  listRules(params = {}) {
    return apiClient.get('', { params })
  },
  getRule(ruleId) {
    return apiClient.get(`/${ruleId}`)
  },
  createRule(data) {
    return apiClient.post('', data)
  },
  updateRule(ruleId, data) {
    return apiClient.put(`/${ruleId}`, data)
  },
  deleteRule(ruleId) {
    return apiClient.delete(`/${ruleId}`)
  },
  evaluate() {
    return apiClient.post('/evaluate')
  },
  listAlerts(params = {}) {
    return apiClient.get('/alerts/list', { params })
  },
  updateAlertStatus(alertId, status) {
    return apiClient.patch(`/alerts/${alertId}/status`, null, { params: { status } })
  }
}

export default alertRuleApi
