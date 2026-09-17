<template>
  <div class="dashboard-integration-config" :class="{ 'is-compact': compact }">
    <el-form :model="integrationConfig" :label-width="compact ? '120px' : '140px'" class="integration-form">
      <el-divider content-position="left">排队时长</el-divider>
      <el-form-item label="启用">
        <el-switch v-model="integrationConfig.wait_time_enabled" />
      </el-form-item>
      <el-form-item label="接口地址">
        <el-input
          v-model="integrationConfig.wait_time_url"
          placeholder="例如 http://10.73.2.248:5000/api/WaitTime"
          clearable
        />
      </el-form-item>
      <el-form-item label="Token 传递">
        <el-select v-model="integrationConfig.wait_time_token_style" style="width: 100%">
          <el-option label="自动尝试（Bearer / 原始 Authorization / ?key= / ?apiKey= / ?token= / X-Api-Key）" value="auto" />
          <el-option label="Bearer 请求头（推荐，你的接口已验证可用）" value="bearer" />
          <el-option label="Authorization 原始值（不加 Bearer 前缀）" value="token_raw" />
          <el-option label="请求头 X-Api-Key" value="header_api_key" />
          <el-option label="URL 参数 ?key=" value="query_key" />
          <el-option label="URL 参数 ?apiKey=" value="query_apiKey" />
          <el-option label="URL 参数 ?token=" value="query_token" />
          <el-option label="不带 Token" value="none" />
        </el-select>
      </el-form-item>
      <el-form-item label="Bearer Token">
        <el-input
          v-model="integrationConfig.wait_time_token"
          type="password"
          show-password
          :placeholder="integrationConfig.wait_time_token_configured ? '留空则不修改已保存的 Token' : '请输入 Token'"
          clearable
        />
        <div v-if="integrationConfig.wait_time_token_configured" class="secret-hint">
          <el-icon class="secret-hint-icon"><InfoFilled /></el-icon>
          <span>当前已保存：<code>{{ integrationConfig.wait_time_token_masked }}</code></span>
        </div>
      </el-form-item>
      <el-form-item label="缓存/超时">
        <div class="timing-inline-row">
          <div class="timing-inline-item">
            <span class="timing-inline-name">缓存</span>
            <el-input-number
              v-model="integrationConfig.wait_time_cache_sec"
              :min="30"
              :max="600"
              :step="30"
              controls-position="right"
            />
            <span class="timing-inline-suffix">秒</span>
          </div>
          <div class="timing-inline-item">
            <span class="timing-inline-name">超时</span>
            <el-input-number
              v-model="integrationConfig.wait_time_timeout_sec"
              :min="10"
              :max="300"
              :step="5"
              controls-position="right"
            />
            <span class="timing-inline-suffix">秒</span>
          </div>
        </div>
        <div class="form-tip">缓存复用结果避免频繁请求；超时慢接口建议 60~120 秒</div>
      </el-form-item>
      <el-form-item>
        <el-button :loading="testingWaitTime" @click="testWaitTimeConnection">测试排队接口</el-button>
      </el-form-item>

      <el-divider content-position="left">天气</el-divider>
      <el-form-item label="启用">
        <el-switch v-model="integrationConfig.weather_enabled" />
      </el-form-item>
      <el-form-item label="API 地址">
        <el-input
          v-model="integrationConfig.weather_api_url"
          placeholder="https://api.seniverse.com/v3/weather/now.json"
          clearable
        />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input
          v-model="integrationConfig.weather_api_key"
          type="password"
          show-password
          :placeholder="integrationConfig.weather_api_key_configured ? '留空则不修改已保存的 Key' : '请输入心知天气 API Key'"
          clearable
        />
        <div v-if="integrationConfig.weather_api_key_configured" class="secret-hint">
          <el-icon class="secret-hint-icon"><InfoFilled /></el-icon>
          <span>当前已保存：<code>{{ integrationConfig.weather_api_key_masked }}</code></span>
        </div>
      </el-form-item>
      <el-form-item label="默认坐标">
        <div class="coord-row">
          <div class="coord-item">
            <span class="coord-label">纬度</span>
            <el-input-number
              v-model="integrationConfig.weather_default_lat"
              :step="0.0001"
              :precision="4"
              controls-position="right"
            />
          </div>
          <div class="coord-item">
            <span class="coord-label">经度</span>
            <el-input-number
              v-model="integrationConfig.weather_default_lon"
              :step="0.0001"
              :precision="4"
              controls-position="right"
            />
          </div>
        </div>
      </el-form-item>
      <el-form-item label="定位">
        <div class="location-actions">
          <el-button type="primary" plain :loading="locating" @click="fetchCurrentLocation">
            获取当前位置
          </el-button>
          <el-button :loading="testingWeather" @click="testWeatherConnection">测试天气接口</el-button>
        </div>
        <div v-if="locationHint" class="integration-hint">{{ locationHint }}</div>
      </el-form-item>
      <el-form-item v-if="weatherPreview.city" label="预览">
        <el-tag type="success">{{ weatherPreview.city }}</el-tag>
        <el-tag type="info" style="margin-left: 8px;">{{ weatherPreview.temperature }}</el-tag>
        <el-tag style="margin-left: 8px;">{{ weatherPreview.text }}</el-tag>
      </el-form-item>

      <div class="integration-hint">
        密钥保存在服务端，大屏通过本平台 API 代理请求。Token 传递方式请选 <strong>Bearer 请求头</strong>。
        若测试返回「Token 认证已通过，但外部接口内部错误(500)」，说明本平台配置正确，需排查 WaitTime 服务端日志。
      </div>
    </el-form>

    <div class="config-actions">
      <el-button @click="loadConfig">重置</el-button>
      <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { dashboardIntegrationApi, getWeatherData } from '@/api/dashboard'

const props = defineProps({
  compact: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['saved'])

const saving = ref(false)
const locating = ref(false)
const testingWeather = ref(false)
const testingWaitTime = ref(false)
const locationHint = ref('')

const integrationConfig = reactive({
  wait_time_enabled: true,
  wait_time_url: '',
  wait_time_token: '',
  wait_time_token_style: 'bearer',
  wait_time_timeout_sec: 60,
  wait_time_cache_sec: 90,
  wait_time_token_configured: false,
  wait_time_token_masked: '',
  weather_enabled: true,
  weather_api_url: 'https://api.seniverse.com/v3/weather/now.json',
  weather_api_key: '',
  weather_api_key_configured: false,
  weather_api_key_masked: '',
  weather_default_lat: 39.9042,
  weather_default_lon: 116.4074
})

const weatherPreview = reactive({
  city: '',
  temperature: '',
  text: ''
})

const applyPayload = (payload) => {
  if (!payload) return
  const tokenConfigured = !!payload.wait_time_token_configured
  const keyConfigured = !!payload.weather_api_key_configured
  Object.assign(integrationConfig, {
    wait_time_enabled: payload.wait_time_enabled ?? true,
    wait_time_url: payload.wait_time_url || '',
    wait_time_token: '',
    wait_time_token_style: payload.wait_time_token_style || 'bearer',
    wait_time_timeout_sec: payload.wait_time_timeout_sec ?? 60,
    wait_time_cache_sec: payload.wait_time_cache_sec ?? 90,
    wait_time_token_configured: tokenConfigured,
    wait_time_token_masked: tokenConfigured ? (payload.wait_time_token || '****') : '',
    weather_enabled: payload.weather_enabled ?? true,
    weather_api_url: payload.weather_api_url || 'https://api.seniverse.com/v3/weather/now.json',
    weather_api_key: '',
    weather_api_key_configured: keyConfigured,
    weather_api_key_masked: keyConfigured ? (payload.weather_api_key || '****') : '',
    weather_default_lat: payload.weather_default_lat ?? 39.9042,
    weather_default_lon: payload.weather_default_lon ?? 116.4074
  })
}

const loadConfig = async () => {
  try {
    const response = await dashboardIntegrationApi.getConfig()
    applyPayload(response.data?.data)
    weatherPreview.city = ''
    weatherPreview.temperature = ''
    weatherPreview.text = ''
    locationHint.value = ''
  } catch (error) {
    console.error('加载外部数据配置失败:', error)
    ElMessage.error('加载外部数据配置失败')
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const body = {
      wait_time_enabled: integrationConfig.wait_time_enabled,
      wait_time_url: integrationConfig.wait_time_url?.trim() || '',
      wait_time_token_style: integrationConfig.wait_time_token_style || 'bearer',
      wait_time_timeout_sec: integrationConfig.wait_time_timeout_sec || 60,
      wait_time_cache_sec: integrationConfig.wait_time_cache_sec || 90,
      weather_enabled: integrationConfig.weather_enabled,
      weather_api_url: integrationConfig.weather_api_url?.trim() || 'https://api.seniverse.com/v3/weather/now.json',
      weather_default_lat: integrationConfig.weather_default_lat,
      weather_default_lon: integrationConfig.weather_default_lon
    }
    if (integrationConfig.wait_time_token?.trim()) {
      body.wait_time_token = integrationConfig.wait_time_token.trim()
    }
    if (integrationConfig.weather_api_key?.trim()) {
      body.weather_api_key = integrationConfig.weather_api_key.trim()
    }

    const response = await dashboardIntegrationApi.saveConfig(body)
    if (response.data?.success) {
      applyPayload(response.data.data)
      ElMessage.success('外部数据配置已保存')
      emit('saved')
    } else {
      throw new Error(response.data?.message || '保存失败')
    }
  } catch (error) {
    console.error('保存外部数据配置失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const fetchCurrentLocation = () => {
  if (!navigator.geolocation) {
    ElMessage.warning('当前浏览器不支持地理位置')
    return
  }

  locating.value = true
  locationHint.value = ''

  navigator.geolocation.getCurrentPosition(
    (position) => {
      integrationConfig.weather_default_lat = Number(position.coords.latitude.toFixed(4))
      integrationConfig.weather_default_lon = Number(position.coords.longitude.toFixed(4))
      locationHint.value = `已定位：纬度 ${integrationConfig.weather_default_lat}，经度 ${integrationConfig.weather_default_lon}`
      ElMessage.success('已获取当前位置，请保存配置后生效')
      locating.value = false
    },
    (error) => {
      const message = error?.message || '请检查浏览器定位权限'
      ElMessage.error(`定位失败：${message}`)
      locating.value = false
    },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
  )
}

const updateWeatherPreview = (data) => {
  const result = data?.results?.[0]
  if (!result) {
    weatherPreview.city = ''
    weatherPreview.temperature = ''
    weatherPreview.text = ''
    return false
  }
  weatherPreview.city = result.location?.name || '未知城市'
  weatherPreview.temperature = `${result.now?.temperature ?? '--'}°C`
  weatherPreview.text = result.now?.text || '--'
  return true
}

const testWeatherConnection = async () => {
  testingWeather.value = true
  try {
    const data = await getWeatherData(
      integrationConfig.weather_default_lat,
      integrationConfig.weather_default_lon
    )
    if (updateWeatherPreview(data)) {
      ElMessage.success('天气接口连接正常')
    } else {
      ElMessage.warning('接口已响应，但未返回有效天气数据')
    }
  } catch (error) {
    console.error('测试天气接口失败:', error)
    ElMessage.error(error.response?.data?.detail || '天气接口测试失败，请先保存 Key 配置')
  } finally {
    testingWeather.value = false
  }
}

const testWaitTimeConnection = async () => {
  testingWaitTime.value = true
  try {
    const response = await dashboardIntegrationApi.testWaitTime({
      wait_time_url: integrationConfig.wait_time_url?.trim() || '',
      wait_time_token: integrationConfig.wait_time_token?.trim() || undefined,
      wait_time_token_style: integrationConfig.wait_time_token_style || 'bearer',
      wait_time_timeout_sec: integrationConfig.wait_time_timeout_sec || 60,
      use_saved_token: !integrationConfig.wait_time_token?.trim() && integrationConfig.wait_time_token_configured,
    })
    const data = response.data?.data
    if (data === null || data === undefined) {
      ElMessage.warning('排队接口未启用或未返回数据')
    } else {
      ElMessage.success('排队接口连接正常（使用当前表单配置测试）')
    }
  } catch (error) {
    console.error('测试排队接口失败:', error)
    const detail = error.response?.data?.detail
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || JSON.stringify(item)).join('；')
      : (detail || error.message || '排队接口测试失败')
    ElMessage.error(message)
  } finally {
    testingWaitTime.value = false
  }
}

onMounted(() => {
  loadConfig()
})

defineExpose({
  loadConfig,
  saveConfig
})
</script>

<style scoped>
.dashboard-integration-config {
  max-width: 760px;
}

.dashboard-integration-config.is-compact {
  max-width: none;
}

.integration-form :deep(.el-form-item__content) {
  flex-wrap: wrap;
  align-items: flex-start;
}

.form-tip {
  flex: 1 0 100%;
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.timing-inline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 20px;
  width: 100%;
}

.timing-inline-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timing-inline-name {
  flex-shrink: 0;
  font-size: 13px;
  color: #606266;
}

.timing-inline-item :deep(.el-input-number) {
  width: 120px;
}

.timing-inline-suffix {
  flex-shrink: 0;
  font-size: 13px;
  color: #909399;
}

.location-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.coord-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  width: 100%;
}

.coord-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 200px;
  min-width: 0;
}

.coord-label {
  flex-shrink: 0;
  font-size: 13px;
  color: #606266;
}

.coord-item :deep(.el-input-number) {
  width: 100%;
  max-width: 180px;
}

.integration-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
  line-height: 1.5;
}

.secret-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.secret-hint-icon {
  color: #409eff;
  flex-shrink: 0;
}

.secret-hint code {
  padding: 2px 6px;
  border-radius: 4px;
  background: #f5f7fa;
  color: #303133;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.config-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>
