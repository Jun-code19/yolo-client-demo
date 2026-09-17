import { ref } from 'vue'
import { buildRtspUrl } from '@/utils/rtspUrl'

/**
 * RTSP 实时预览（复用 /ws/rtsp/preview，与设备管理预览一致）
 */
export function useRtspPreview(options = {}) {
  const previewLoading = ref(false)
  const previewError = ref(null)
  const previewFrame = ref(null)
  const isStreaming = ref(false)
  const streamResolution = ref('')

  let ws = null
  let connectTimer = null
  let currentDevice = null

  const clearConnectTimer = () => {
    if (connectTimer) {
      clearTimeout(connectTimer)
      connectTimer = null
    }
  }

  const disconnect = () => {
    clearConnectTimer()
    if (ws) {
      ws.onopen = null
      ws.onmessage = null
      ws.onerror = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
      ws = null
    }
    isStreaming.value = false
  }

  const handleStreamData = (message) => {
    if (message.format !== 'jpeg' || !message.data) return
    const dataUrl = `data:image/jpeg;base64,${message.data}`
    previewFrame.value = dataUrl
    if (message.width && message.height) {
      streamResolution.value = `${message.width}x${message.height}`
    }
    isStreaming.value = true
    previewLoading.value = false
    previewError.value = null
    options.onFrame?.(dataUrl, message)
  }

  const handleWsMessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      switch (message.type) {
        case 'connect_confirm':
          if (ws?.readyState === WebSocket.OPEN && currentDevice) {
            ws.send(JSON.stringify({
              type: 'preview_request',
              device_id: currentDevice.device_id,
              stream_url: buildRtspUrl(currentDevice),
            }))
          }
          break
        case 'preview_connecting':
          previewLoading.value = true
          break
        case 'preview_start':
          previewLoading.value = false
          isStreaming.value = true
          break
        case 'stream_data':
          handleStreamData(message)
          break
        case 'error':
          previewLoading.value = false
          previewError.value = message.message || '预览连接失败'
          options.onError?.(previewError.value)
          break
        default:
          break
      }
    } catch (error) {
      previewError.value = error.message || '预览消息解析失败'
    }
  }

  const connect = (device, { timeoutMs = 12000 } = {}) => {
    if (!device?.device_id) {
      previewError.value = '设备信息不可用'
      return Promise.reject(new Error(previewError.value))
    }

    disconnect()
    currentDevice = device
    previewLoading.value = true
    previewError.value = null
    previewFrame.value = null
    isStreaming.value = false
    streamResolution.value = ''

    return new Promise((resolve, reject) => {
      try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/rtsp/preview`)

        connectTimer = setTimeout(() => {
          previewLoading.value = false
          const err = new Error('预览连接超时')
          previewError.value = err.message
          disconnect()
          reject(err)
        }, timeoutMs)

        ws.onopen = () => {
          ws.send(JSON.stringify({ type: 'connect', client_type: 'preview_client' }))
        }

        ws.onmessage = (event) => {
          handleWsMessage(event)
          if (previewFrame.value) {
            clearConnectTimer()
            resolve(previewFrame.value)
          }
        }

        ws.onerror = () => {
          clearConnectTimer()
          previewLoading.value = false
          const err = new Error('WebSocket 连接错误')
          previewError.value = err.message
          reject(err)
        }

        ws.onclose = () => {
          if (previewLoading.value && !previewFrame.value) {
            clearConnectTimer()
            previewLoading.value = false
            if (!previewError.value) {
              previewError.value = '视频流连接已断开'
            }
          }
          isStreaming.value = false
        }
      } catch (error) {
        clearConnectTimer()
        previewLoading.value = false
        previewError.value = error.message || '创建预览连接失败'
        reject(error)
      }
    })
  }

  const reconnect = (device) => connect(device || currentDevice)

  return {
    previewLoading,
    previewError,
    previewFrame,
    isStreaming,
    streamResolution,
    connect,
    reconnect,
    disconnect,
  }
}
