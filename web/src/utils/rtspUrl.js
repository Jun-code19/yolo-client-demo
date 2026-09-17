/**
 * 设备 RTSP 拉流地址构建（与后端 src/rtsp_url.py 逻辑一致）
 */

export const DAHUA_RTSP_TEMPLATE =
  'rtsp://{username}:{password}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}'

export const RTSP_URL_PRESETS = [
  {
    value: 'dahua',
    label: '大华默认',
    mode: 'dahua',
    url: '',
    hint: '通道与码流由上方配置自动代入'
  },
  {
    value: 'hikvision',
    label: '海康威视',
    mode: 'custom',
    url: 'rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/{hik_channel}',
    hint: '{hik_channel} 由通道与码流自动计算（如 101）'
  },
  {
    value: 'uniview',
    label: '宇视',
    mode: 'custom',
    url: 'rtsp://{username}:{password}@{ip}:{port}/video{channel}/{subtype}',
    hint: 'subtype：0 主码流，1 辅码流'
  },
  {
    value: 'generic',
    label: '通用 RTSP',
    mode: 'custom',
    url: 'rtsp://{username}:{password}@{ip}:{port}/',
    hint: '可填完整 URL 或模板，占位符：{username} {password} {ip} {port} {channel} {subtype} {hik_channel}'
  }
]

const encodeCredential = (value) => encodeURIComponent(value || '')

const applyTemplate = (template, mapping) => {
  let result = template
  Object.entries(mapping).forEach(([key, value]) => {
    result = result.split(`{${key}}`).join(String(value))
  })
  return result
}

export const getRtspPreset = (presetValue) =>
  RTSP_URL_PRESETS.find((item) => item.value === presetValue)

export const detectRtspPreset = (device) => {
  const mode = (device?.rtsp_url_mode || 'dahua').toLowerCase()
  if (mode !== 'custom') {
    return 'dahua'
  }

  const url = (device?.rtsp_url || '').trim()
  if (!url) {
    return 'generic'
  }

  const matchedPreset = RTSP_URL_PRESETS.find(
    (preset) => preset.url && preset.url === url
  )
  return matchedPreset?.value || 'generic'
}

export const getRtspPresetLabel = (device) => {
  const preset = getRtspPreset(detectRtspPreset(device))
  if (preset) {
    return preset.label
  }
  return (device?.rtsp_url_mode || 'dahua') === 'custom' ? '通用 RTSP' : '大华默认'
}

export const applyRtspPreset = (presetValue, form) => {
  const preset = getRtspPreset(presetValue)
  if (!preset || !form) {
    return
  }

  form.rtsp_url_mode = preset.mode
  form.rtsp_url = preset.url || ''
}

export const buildRtspUrl = (device) => {
  if (!device) return ''

  const mode = (device.rtsp_url_mode || 'dahua').toLowerCase()
  const customUrl = (device.rtsp_url || '').trim()

  const streamType = device.stream_type || 'main'
  const subtype = streamType === 'sub' ? 1 : 0
  const deviceType = device.device_type || 'camera'
  const channel = Number(device.channel || 1)
  const channelForDahua = deviceType === 'nvr' ? channel : 1

  const username = device.username || ''
  const password = device.password || ''
  const ip = device.ip_address || ''
  const port = device.port || 554

  if (mode === 'custom' && customUrl) {
    if (customUrl.includes('{')) {
      const hikChannel = channel * 100 + (streamType === 'main' ? 1 : 2)
      return applyTemplate(customUrl, {
        username: encodeCredential(username),
        password: encodeCredential(password),
        ip,
        port,
        channel,
        subtype,
        stream: streamType,
        hik_channel: hikChannel
      })
    }
    return customUrl
  }

  return `rtsp://${username}:${password}@${ip}:${port}/cam/realmonitor?channel=${channelForDahua}&subtype=${subtype}`
}

/** @deprecated 使用 getRtspPresetLabel */
export const getRtspUrlModeLabel = (mode) => {
  if (!mode || mode === 'dahua') return '大华默认'
  if (mode === 'custom') return '自定义'
  return mode
}
