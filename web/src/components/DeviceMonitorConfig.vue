<template>
  <div class="device-monitor-config">
    <el-alert
      v-if="runtime"
      :type="runtime.rtsp_probe_mode === 'ffprobe' ? 'success' : runtime.rtsp_probe_mode === 'opencv' ? 'warning' : 'error'"
      :closable="false"
      show-icon
      class="runtime-alert"
    >
      <template #title>
        检测服务探活能力：
        <strong>{{ probeModeLabel }}</strong>
        <el-tag v-if="runtime.monitor_running" type="success" size="small" style="margin-left: 8px">监控运行中</el-tag>
        <el-tag v-else type="info" size="small" style="margin-left: 8px">监控未启动</el-tag>
      </template>
      <div class="runtime-detail">
        ffprobe {{ runtime.ffprobe_available ? '✓' : '✗' }} ·
        ffmpeg {{ runtime.ffmpeg_available ? '✓' : '✗' }} ·
        OpenCV {{ runtime.opencv_available ? '✓' : '✗' }}
        <span v-if="runtime.rtsp_probe_hint"> — {{ runtime.rtsp_probe_hint }}</span>
      </div>
    </el-alert>

    <el-form :model="form" label-width="140px" v-loading="loading">
      <el-divider content-position="left">调度</el-divider>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="状态检测间隔">
            <el-input-number v-model="form.check_interval" :min="30" :max="86400" :step="60" style="width: 100%" />
            <div class="field-hint">秒，建议 300（5 分钟）</div>
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">判定与重试</el-divider>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="离线阈值">
            <el-input-number v-model="form.offline_threshold" :min="1" :max="20" style="width: 100%" />
            <div class="field-hint">连续失败次数</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="单次重试">
            <el-input-number v-model="form.retry_count" :min="1" :max="10" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="重试间隔(秒)">
            <el-input-number v-model="form.retry_delay_seconds" :min="0" :max="30" :step="0.5" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="设备间隔(秒)">
        <el-input-number v-model="form.per_device_delay_seconds" :min="0" :max="5" :step="0.1" />
        <span class="field-hint inline-hint">每检测一台设备后的间隔，避免压垮 NVR</span>
      </el-form-item>

      <el-divider content-position="left">探活参数</el-divider>
      <el-row :gutter="16">
        <el-col :span="8">
          <el-form-item label="RTSP 超时">
            <el-input-number v-model="form.rtsp_timeout_seconds" :min="2" :max="60" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="TCP 超时">
            <el-input-number v-model="form.tcp_timeout_seconds" :min="1" :max="30" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="HTTP 超时">
            <el-input-number v-model="form.http_timeout_seconds" :min="1" :max="30" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="RTSP 探测码流">
            <el-radio-group v-model="form.rtsp_stream_for_probe">
              <el-radio value="sub">子码流（更快）</el-radio>
              <el-radio value="main">主码流</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="启用 Ping">
            <el-switch v-model="form.enable_ping" />
            <span class="field-hint inline-hint">部分环境无 ping 命令；无法测 NVR 单通道</span>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16">
        <el-col :span="16">
          <el-form-item label="大华 HTTP 路径">
            <el-input v-model="form.http_dahua_path" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="大华 HTTP 端口">
            <el-input-number v-model="form.http_dahua_port" :min="1" :max="65535" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">按设备类型的探活顺序</el-divider>
      <div class="methods-hint">按顺序尝试，前者成功则不再尝试后者。单设备可在设备表设置 <code>monitor_method</code> 强制指定。</div>
      <el-form-item
        v-for="(label, key) in deviceTypeLabels"
        :key="key"
        :label="label"
      >
        <el-select
          v-model="form.default_methods_by_type[key]"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="选择探活方式"
          style="width: 100%"
        >
          <el-option
            v-for="opt in probeMethodOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          >
            <div class="method-option">
              <span>{{ opt.label }}</span>
              <span class="method-desc">{{ opt.desc }}</span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <div class="integration-hint">
        配置保存在数据库，检测服务下次巡检时自动生效。环境变量仍可覆盖部分项（部署用）。
      </div>
    </el-form>

    <div class="config-actions">
      <el-button @click="loadAll">重置</el-button>
      <el-button :loading="loadingRuntime" @click="loadRuntime">刷新运行状态</el-button>
      <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  deviceMonitorApi,
  PROBE_METHOD_OPTIONS,
  DEVICE_TYPE_LABELS
} from '@/api/device_monitor'

const loading = ref(false)
const saving = ref(false)
const loadingRuntime = ref(false)
const runtime = ref(null)
const probeMethodOptions = PROBE_METHOD_OPTIONS
const deviceTypeLabels = DEVICE_TYPE_LABELS

const defaultMethods = () => ({
  camera: ['rtsp', 'tcp'],
  nvr: ['rtsp', 'tcp'],
  default: ['rtsp', 'tcp', 'http_dahua']
})

const form = reactive({
  check_interval: 300,
  offline_threshold: 3,
  retry_count: 3,
  retry_delay_seconds: 1,
  per_device_delay_seconds: 0.2,
  rtsp_timeout_seconds: 6,
  tcp_timeout_seconds: 3,
  http_timeout_seconds: 3,
  enable_ping: false,
  rtsp_stream_for_probe: 'sub',
  http_dahua_path: '/cgi-bin/api/tcpConnect/tcpTest',
  http_dahua_port: 80,
  default_methods_by_type: defaultMethods()
})

const probeModeLabel = computed(() => {
  const mode = runtime.value?.rtsp_probe_mode
  if (mode === 'ffprobe') return 'ffprobe（推荐）'
  if (mode === 'opencv') return 'OpenCV 回退'
  if (mode === 'none') return '无可用 RTSP 探针'
  return '未知'
})

const applyConfig = (data) => {
  Object.assign(form, {
    check_interval: data.check_interval ?? 300,
    offline_threshold: data.offline_threshold ?? 3,
    retry_count: data.retry_count ?? 3,
    retry_delay_seconds: data.retry_delay_seconds ?? 1,
    per_device_delay_seconds: data.per_device_delay_seconds ?? 0.2,
    rtsp_timeout_seconds: data.rtsp_timeout_seconds ?? 6,
    tcp_timeout_seconds: data.tcp_timeout_seconds ?? 3,
    http_timeout_seconds: data.http_timeout_seconds ?? 3,
    enable_ping: !!data.enable_ping,
    rtsp_stream_for_probe: data.rtsp_stream_for_probe || 'sub',
    http_dahua_path: data.http_dahua_path || '/cgi-bin/api/tcpConnect/tcpTest',
    http_dahua_port: data.http_dahua_port ?? 80,
    default_methods_by_type: {
      ...defaultMethods(),
      ...(data.default_methods_by_type || {})
    }
  })
}

const loadConfig = async () => {
  const res = await deviceMonitorApi.getConfig()
  applyConfig(res.data?.data || res.data)
}

const loadRuntime = async () => {
  loadingRuntime.value = true
  try {
    const res = await deviceMonitorApi.getRuntime()
    runtime.value = res.data?.data || res.data
  } catch (error) {
    runtime.value = null
    ElMessage.warning('无法获取检测服务运行状态，请确认 serve_unified 已启动')
  } finally {
    loadingRuntime.value = false
  }
}

const loadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadConfig(), loadRuntime()])
  } catch (error) {
    ElMessage.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const payload = {
      ...form,
      default_methods_by_type: { ...form.default_methods_by_type }
    }
    await deviceMonitorApi.saveConfig(payload)
    try {
      await deviceMonitorApi.reloadScheduler()
    } catch (_) {
      /* 检测服务未启动时忽略 */
    }
    ElMessage.success('设备监控配置已保存')
    await loadConfig()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.device-monitor-config {
  max-width: 920px;
}

.runtime-alert {
  margin-bottom: 20px;
}

.runtime-detail {
  font-size: 13px;
  margin-top: 4px;
}

.field-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  margin-top: 4px;
}

.inline-hint {
  margin-left: 8px;
  margin-top: 0;
}

.methods-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 16px 140px;
}

.method-option {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
  padding: 2px 0;
}

.method-desc {
  font-size: 12px;
  color: #909399;
}

.integration-hint {
  margin-top: 8px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.config-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

code {
  background: #eef1f6;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
