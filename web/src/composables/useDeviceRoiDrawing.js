import { ref, reactive, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

export function normalizeAreaCoordinates(raw) {
  if (!raw || typeof raw !== 'object') {
    return { enabled: false, points: [] }
  }
  const points = Array.isArray(raw.points)
    ? raw.points.map((p) => ({ x: Number(p.x), y: Number(p.y) }))
    : []
  let enabled = false
  if (raw.enabled === true) {
    enabled = true
  } else if (raw.enabled === false) {
    enabled = false
  } else if (points.length >= 3) {
    enabled = true
  }
  return { enabled, points }
}

export function useDeviceRoiDrawing() {
  const areaConfig = reactive({
    enabled: false,
    points: [],
  })
  const drawingCanvas = ref(null)
  const frameImageRef = ref(null)
  const isDrawing = ref(false)
  const draftPoints = ref([])
  const areaSaveLoading = ref(false)
  let canvasResizeObserver = null

  const getImageDisplayRect = () => {
    const image = frameImageRef.value
    const wrapper = image?.parentElement
    if (!image || !wrapper) return null
    const w = image.clientWidth || image.videoWidth
    const h = image.clientHeight || image.videoHeight
    if (!w || !h) return null
    const naturalW = image.naturalWidth || image.videoWidth || w
    const naturalH = image.naturalHeight || image.videoHeight || h
    if (!naturalW || !naturalH) return null
    const containerWidth = wrapper.clientWidth
    const containerHeight = wrapper.clientHeight
    if (!containerWidth || !containerHeight) return null
    const imageRatio = naturalW / naturalH
    const containerRatio = containerWidth / containerHeight
    let displayWidth
    let displayHeight
    let offsetX
    let offsetY
    if (imageRatio > containerRatio) {
      displayWidth = containerWidth
      displayHeight = containerWidth / imageRatio
      offsetX = 0
      offsetY = (containerHeight - displayHeight) / 2
    } else {
      displayHeight = containerHeight
      displayWidth = containerHeight * imageRatio
      offsetX = (containerWidth - displayWidth) / 2
      offsetY = 0
    }
    return { displayWidth, displayHeight, offsetX, offsetY }
  }

  const syncCanvasLayout = () => {
    if (!drawingCanvas.value || !frameImageRef.value) return false
    const rect = getImageDisplayRect()
    if (!rect) return false
    const canvas = drawingCanvas.value
    const { displayWidth, displayHeight, offsetX, offsetY } = rect
    const dpr = window.devicePixelRatio || 1
    canvas.style.left = `${offsetX}px`
    canvas.style.top = `${offsetY}px`
    canvas.style.width = `${displayWidth}px`
    canvas.style.height = `${displayHeight}px`
    canvas.width = Math.round(displayWidth * dpr)
    canvas.height = Math.round(displayHeight * dpr)
    const ctx = canvas.getContext('2d')
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    return true
  }

  const drawPolygon = (polygonPoints, options = {}) => {
    if (!drawingCanvas.value || !polygonPoints?.length) return
    const canvas = drawingCanvas.value
    const ctx = canvas.getContext('2d')
    const displayWidth = canvas.clientWidth
    const displayHeight = canvas.clientHeight
    const { strokeStyle = '#00ff00', fillStyle = 'rgba(0, 255, 0, 0.15)', closed = true } = options

    ctx.save()
    ctx.strokeStyle = strokeStyle
    ctx.lineWidth = 2
    ctx.beginPath()
    polygonPoints.forEach((point, index) => {
      const x = Math.round(point.x * displayWidth) + 0.5
      const y = Math.round(point.y * displayHeight) + 0.5
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    if (closed && polygonPoints.length >= 3) {
      ctx.closePath()
      ctx.fillStyle = fillStyle
      ctx.fill()
    }
    ctx.stroke()
    polygonPoints.forEach((point) => {
      ctx.beginPath()
      ctx.arc(Math.round(point.x * displayWidth), Math.round(point.y * displayHeight), 4, 0, Math.PI * 2)
      ctx.fillStyle = '#ff4444'
      ctx.fill()
    })
    ctx.restore()
  }

  const redrawCanvas = (previewPoint = null) => {
    if (!drawingCanvas.value) return
    const canvas = drawingCanvas.value
    const ctx = canvas.getContext('2d')
    const w = canvas.clientWidth
    const h = canvas.clientHeight
    ctx.clearRect(0, 0, w, h)

    if (areaConfig.points?.length && !isDrawing.value) {
      drawPolygon(areaConfig.points)
    }

    if (draftPoints.value.length) {
      drawPolygon(draftPoints.value, { closed: false })
      if (previewPoint && draftPoints.value.length) {
        const last = draftPoints.value[draftPoints.value.length - 1]
        ctx.beginPath()
        ctx.strokeStyle = '#00ff00'
        ctx.moveTo(last.x * w, last.y * h)
        ctx.lineTo(previewPoint.x * w, previewPoint.y * h)
        ctx.stroke()
      }
    }
  }

  const refreshCanvasDrawing = () => {
    if (syncCanvasLayout()) redrawCanvas()
  }

  const setupCanvasResizeObserver = () => {
    canvasResizeObserver?.disconnect()
    canvasResizeObserver = null
    const wrapper = frameImageRef.value?.parentElement
    if (!wrapper || typeof ResizeObserver === 'undefined') return
    canvasResizeObserver = new ResizeObserver(() => refreshCanvasDrawing())
    canvasResizeObserver.observe(wrapper)
  }

  const onFrameMediaLoaded = () => {
    requestAnimationFrame(() => {
      refreshCanvasDrawing()
      setupCanvasResizeObserver()
    })
  }

  const loadAreaFromDevice = (device) => {
    const normalized = normalizeAreaCoordinates(device?.area_coordinates)
    areaConfig.enabled = normalized.enabled
    areaConfig.points = normalized.points.map((p) => ({ ...p }))
    draftPoints.value = []
    isDrawing.value = false
    refreshCanvasDrawing()
  }

  const resetAreaDraft = () => {
    areaConfig.enabled = false
    areaConfig.points = []
    clearDrawing()
  }

  const startDrawing = () => {
    if (!areaConfig.enabled) {
      ElMessage.warning('请先启用区域')
      return
    }
    isDrawing.value = true
    draftPoints.value = []
    areaConfig.points = []
    redrawCanvas()
  }

  const clearDrawing = () => {
    draftPoints.value = []
    areaConfig.points = []
    isDrawing.value = false
    redrawCanvas()
  }

  const handleMouseDown = (e) => {
    if (!isDrawing.value) return
    const canvas = drawingCanvas.value
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    if (x < 0 || x > 1 || y < 0 || y > 1) return
    draftPoints.value.push({ x, y })
    redrawCanvas()
  }

  const handleMouseMove = (e) => {
    if (!isDrawing.value || !draftPoints.value.length) return
    const canvas = drawingCanvas.value
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    if (x < 0 || x > 1 || y < 0 || y > 1) return
    redrawCanvas({ x, y })
  }

  const handleRightClick = () => {
    if (!isDrawing.value || draftPoints.value.length < 3) return
    areaConfig.points = [...draftPoints.value]
    isDrawing.value = false
    redrawCanvas()
    ElMessage.success('区域绘制完成')
  }

  const canSaveArea = () => {
    if (!areaConfig.enabled) return true
    return areaConfig.points.length >= 3
  }

  const saveAreaConfig = async (deviceId, deviceApi) => {
    if (!deviceId) throw new Error('设备ID无效')
    if (areaConfig.enabled && areaConfig.points.length < 3) {
      throw new Error('启用区域时请绘制有效多边形，至少需要3个点')
    }
    areaSaveLoading.value = true
    try {
      await deviceApi.updateDevice(deviceId, {
        area_coordinates: {
          enabled: areaConfig.enabled,
          points: areaConfig.points || [],
        },
      })
      ElMessage.success('区域配置已保存')
    } finally {
      areaSaveLoading.value = false
    }
  }

  const teardownDrawing = () => {
    canvasResizeObserver?.disconnect()
    canvasResizeObserver = null
    isDrawing.value = false
    draftPoints.value = []
  }

  onUnmounted(teardownDrawing)

  return {
    areaConfig,
    drawingCanvas,
    frameImageRef,
    isDrawing,
    areaSaveLoading,
    loadAreaFromDevice,
    resetAreaDraft,
    startDrawing,
    clearDrawing,
    handleMouseDown,
    handleMouseMove,
    handleRightClick,
    onFrameMediaLoaded,
    refreshCanvasDrawing,
    teardownDrawing,
    canSaveArea,
    saveAreaConfig,
  }
}
