import { ref, computed } from 'vue'
import { useRtspPreview } from '@/composables/useRtspPreview'

function revokeBlobUrl(url) {
  if (url?.startsWith?.('blob:')) {
    URL.revokeObjectURL(url)
  }
}

/**
 * 设备画面预览：优先 RTSP 实时流，失败则调用设备 CGI 截图 API
 */
export function useDeviceFramePreview(options = {}) {
  const snapshotImage = ref(null)
  const snapshotLoading = ref(false)
  const fallbackError = ref(null)
  const previewDevice = ref(null)

  const {
    previewLoading: rtspLoading,
    previewError: rtspError,
    previewFrame,
    isStreaming,
    streamResolution,
    connect,
    reconnect,
    disconnect,
  } = useRtspPreview({
    onFrame: (dataUrl, message) => {
      options.onFrame?.(dataUrl, message)
    },
    onError: (message) => {
      options.onError?.(message)
    },
  })

  const previewLoading = computed(() => rtspLoading.value || snapshotLoading.value)
  const displayImage = computed(() => previewFrame.value || snapshotImage.value)
  const previewError = computed(() => {
    if (displayImage.value) return null
    return fallbackError.value || rtspError.value
  })

  const loadDeviceSnapshot = async (device) => {
    const ipAddress = device?.ip_address || device?.device_ip
    const channel = device?.channel || 1
    if (!ipAddress) {
      fallbackError.value = '无法获取设备画面'
      return false
    }

    snapshotLoading.value = true
    fallbackError.value = null
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 8000)
      const response = await fetch('/api/v1/devices/snapshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: device.device_id,
          ip_address: ipAddress,
          device_type: device.device_type,
          channel,
          username: device.username,
          password: device.password,
        }),
        signal: controller.signal,
      })
      clearTimeout(timeoutId)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      revokeBlobUrl(snapshotImage.value)
      snapshotImage.value = URL.createObjectURL(await response.blob())
      rtspError.value = null
      return true
    } catch {
      fallbackError.value = '无法获取设备画面，请检查设备网络与账号'
      return false
    } finally {
      snapshotLoading.value = false
    }
  }

  const resetSnapshot = () => {
    revokeBlobUrl(snapshotImage.value)
    snapshotImage.value = null
  }

  const startPreview = async (device) => {
    if (!device?.device_id) {
      fallbackError.value = '设备信息不可用'
      return false
    }

    previewDevice.value = device
    fallbackError.value = null
    resetSnapshot()
    rtspError.value = null

    try {
      await connect(device)
      return true
    } catch {
      return loadDeviceSnapshot(device)
    }
  }

  const refreshPreview = async () => {
    if (!previewDevice.value) return false
    fallbackError.value = null
    resetSnapshot()
    rtspError.value = null
    try {
      await reconnect(previewDevice.value)
      return true
    } catch {
      return loadDeviceSnapshot(previewDevice.value)
    }
  }

  const stopPreview = () => {
    disconnect()
    resetSnapshot()
    fallbackError.value = null
    previewDevice.value = null
  }

  return {
    previewLoading,
    previewError,
    displayImage,
    previewFrame,
    isStreaming,
    streamResolution,
    startPreview,
    refreshPreview,
    stopPreview,
  }
}
