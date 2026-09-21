import { apiV1 } from './http'

export const deviceMonitorApi = {
  getConfig: () => apiV1.get('/settings/device-monitor'),
  saveConfig: (data) => apiV1.put('/settings/device-monitor', data),
  getRuntime: () => apiV1.get('/settings/device-monitor/runtime'),
  reloadScheduler: () => apiV1.post('/settings/device-monitor/reload'),
}

export const PROBE_METHOD_OPTIONS = [
  { value: 'rtsp', label: 'RTSP 拉流', desc: '通道级探测，适合摄像头/NVR' },
  { value: 'tcp', label: 'TCP 端口', desc: '主机级连通' },
  { value: 'http_dahua', label: 'HTTP（大华）', desc: '新大华设备 API' },
  { value: 'ping', label: 'Ping', desc: '需启用且容器有 ping 命令' },
]

export const DEVICE_TYPE_LABELS = {
  camera: '摄像头',
  nvr: 'NVR 通道',
  default: '默认（其他类型）',
}
