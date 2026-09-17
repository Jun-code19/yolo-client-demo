import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' }
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const deviceMonitorApi = {
  getConfig: () => apiClient.get('/settings/device-monitor'),
  saveConfig: (data) => apiClient.put('/settings/device-monitor', data),
  getRuntime: () => apiClient.get('/settings/device-monitor/runtime'),
  reloadScheduler: () => apiClient.post('/settings/device-monitor/reload')
}

export const PROBE_METHOD_OPTIONS = [
  { value: 'rtsp', label: 'RTSP 拉流', desc: '通道级探测，适合摄像头/NVR' },
  { value: 'tcp', label: 'TCP 端口', desc: '主机级连通' },
  { value: 'http_dahua', label: 'HTTP（大华）', desc: '新大华设备 API' },
  { value: 'ping', label: 'Ping', desc: '需启用且容器有 ping 命令' }
]

export const DEVICE_TYPE_LABELS = {
  camera: '摄像头',
  nvr: 'NVR 通道',
  default: '默认（其他类型）'
}
