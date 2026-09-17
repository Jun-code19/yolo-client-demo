<template>
  <div class="board-page">
    <header class="board-header">
      <div class="header-left">
        <div class="clock">{{ currentTime }}</div>
        <div class="sync-hint" v-if="lastUpdated">数据更新 {{ lastUpdated }}</div>
      </div>
      <h1 class="header-title">{{ screenTitle }}</h1>
      <div class="header-right header-kpi-hint">
        <span>检测 {{ overviewSummary.detection_event_today ?? 0 }} 今日</span>
        <span>告警 {{ overviewSummary.composite_alert_today ?? 0 }} 今日</span>
        <span>订阅 {{ overviewSummary.smart_event_today ?? 0 }} 今日</span>
      </div>
    </header>

    <div class="board-stage">
      <section class="kpi-row">
      <div
        v-for="item in kpiList"
        :key="item.key"
        class="kpi-card"
        :class="{ highlight: item.highlight }"
      >
        <div class="kpi-value">{{ item.value }}</div>
        <div class="kpi-label">{{ item.label }}</div>
        <div class="kpi-sub">{{ item.sub }}</div>
      </div>
    </section>

      <div class="board-content">
        <section ref="boardGridRef" class="board-grid">
          <aside class="col col-left board-grid-overlay">
          <div class="panel panel-overlay">
            <div class="panel-head">近 7 天事件趋势</div>
            <div ref="trendChartRef" class="chart-box chart-side" />
              </div>
          <div class="panel panel-overlay">
            <div class="panel-head">{{ thirdPanelTitle }}</div>
            <div ref="systemChartRef" class="chart-box chart-side" />
            </div>
        </aside>

          <div class="col col-center col-center-hero">
            <div class="panel panel-center-snaps">
              <div class="panel-head">
                <span>最新抓拍</span>
                <span class="panel-meta">{{ liveMonitors.length }} 张</span>
              </div>
              <div class="panel-snaps-body">
                <div v-if="liveMonitors.length" class="snap-grid snap-grid-3x2">
                  <div v-for="item in liveMonitors" :key="item.id" class="snap-item">
                    <img
                      v-if="item.image"
                      :src="getImageUrl(item.image)"
                      :alt="item.name"
                      class="snap-img-clickable"
                      @click="openSnapPreview(item)"
                      @error="handleImageError"
                    />
                    <div v-else class="snap-placeholder">无图</div>
                    <div class="snap-meta">
                      <span :title="item.name">{{ item.name }}</span>
                      <i class="badge sm" :class="item.status">{{ item.statusText }}</i>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-tip empty-tip-snaps">暂无抓拍</div>
              </div>
            </div>
          </div>

          <aside class="col col-right board-grid-overlay">
          <div class="panel panel-overlay panel-type">
            <div class="panel-head">{{ typeChartTitle }}</div>
            <div ref="typeChartRef" class="chart-box chart-side" />
          </div>
          <div class="panel panel-overlay panel-device">
            <div class="panel-head">{{ deviceChartTitle }}</div>
            <div ref="deviceChartRef" class="chart-box chart-side" />
        </div>
          <div class="panel panel-overlay panel-alerts">
            <div class="panel-head">告警动态</div>
            <div class="panel-feed-compact panel-feed-scroll">
              <div v-if="!alertFeed.length" class="empty-tip compact">暂无告警动态</div>
              <div v-for="item in alertFeed" :key="item.id" class="feed-item feed-item-side">
                <span class="feed-tag" :class="item.source">{{ item.sourceLabel }}</span>
                <span class="feed-title" :title="item.title">{{ item.title }}</span>
                <span class="feed-time">{{ item.time }}</span>
              </div>
            </div>
          </div>
        </aside>
      </section>

        <section ref="boardFooterRef" class="board-footer board-grid-overlay">
        <div class="panel panel-overlay panel-footer panel-footer-hourly">
          <div class="panel-head">近 7 天事件时段</div>
          <div ref="hourlyChartRef" class="chart-box chart-footer" />
            </div>
        <div class="panel panel-overlay panel-footer panel-footer-events">
          <div class="panel-head">
            <span>最新检测事件</span>
            <span class="panel-meta">{{ alertHistory.length }} 条</span>
          </div>
          <div class="event-table" ref="eventTableRef">
            <div class="event-head">
              <span>类型</span>
              <span>设备</span>
              <span class="col-wide">详情</span>
              <span>置信度</span>
              <span>时间</span>
              <span>状态</span>
        </div>
            <div v-if="!alertHistory.length" class="empty-tip">暂无检测事件</div>
            <div
              v-for="row in alertHistory"
              :key="row.id"
              class="event-row event-row-clickable"
              :class="{ 'is-new': row.isNew }"
              @click="openEventDetail(row)"
            >
              <span :title="row.type">{{ row.type }}</span>
              <span :title="row.device">{{ row.device }}</span>
              <span class="col-wide" :title="row.name">{{ row.name }}</span>
              <span>{{ row.confidence }}</span>
              <span>{{ row.time }}</span>
              <span><i class="badge" :class="row.status">{{ row.statusText }}</i></span>
          </div>
        </div>
            </div>
      </section>
        </div>
      </div>

    <!-- 检测事件详情 -->
    <el-dialog
      v-model="showEventDetailDialog"
      width="860px"
      align-center
      class="board-event-dialog"
      header-class="board-dialog-header"
      body-class="board-dialog-body"
      destroy-on-close
      append-to-body
      :show-close="false"
    >
      <template #header>
        <div class="dialog-head">
          <div class="dialog-head-left">
            <span class="dialog-title">检测事件详情</span>
            <span v-if="eventDetail" class="dialog-subtitle">{{ getEventTypeName(eventDetail.event_type) }}</span>
                </div>
          <button class="dialog-close" @click="showEventDetailDialog = false">关闭</button>
              </div>
      </template>
      <div v-loading="eventDetailLoading" class="event-detail-body" element-loading-background="rgba(11,20,36,0.85)">
        <template v-if="eventDetail">
          <div class="detail-top-bar">
            <span class="detail-id">{{ eventDetail.event_id }}</span>
            <i class="badge" :class="getStatusBadge(eventDetail.status)">{{ getStatusLabel(eventDetail.status) }}</i>
            </div>
          <div class="detail-layout">
            <div class="detail-main">
              <div class="detail-stat-row">
                <div class="detail-stat">
                  <label>设备</label>
                  <span>{{ eventDetail.device_name || eventDetail.device_id || '--' }}</span>
          </div>
                <div class="detail-stat">
                  <label>置信度</label>
                  <span class="detail-highlight">{{ formatConfidence(eventDetail.confidence) }}</span>
            </div>
                <div class="detail-stat">
                  <label>检测目标</label>
                  <span class="detail-highlight">{{ getDetectionTargets(eventDetail).length }} 个</span>
          </div>
                <div class="detail-stat">
                  <label>发生时间</label>
                  <span>{{ formatDateTime(eventDetail.timestamp || eventDetail.created_at) }}</span>
                    </div>
                  </div>
              <div class="detail-panel" v-if="getEventDescription(eventDetail) !== '-'">
                <div class="detail-panel-head">事件描述</div>
                <div class="detail-panel-body">{{ getEventDescription(eventDetail) }}</div>
                </div>
              <div class="detail-panel" v-if="eventDetail.location">
                <div class="detail-panel-head">位置</div>
                <div class="detail-panel-body">{{ eventDetail.location }}</div>
              </div>
              <div class="detail-panel" v-if="getDetectionTargets(eventDetail).length">
                <div class="detail-panel-head">检测目标 ({{ getDetectionTargets(eventDetail).length }})</div>
                <div class="target-table">
                  <div class="target-head">
                    <span>类型</span><span>置信度</span><span>边界框</span>
            </div>
                  <div v-for="(t, idx) in getDetectionTargets(eventDetail)" :key="idx" class="target-row">
                    <span>{{ t.class_name || '未知' }}</span>
                    <span class="detail-highlight">{{ t.confidence != null ? `${(t.confidence * 100).toFixed(1)}%` : '--' }}</span>
                    <span>{{ formatBoundingBox(t.bbox) }}</span>
          </div>
            </div>
          </div>
        </div>
            <div v-if="eventDetail.thumbnail_path" class="detail-aside">
              <div class="detail-panel-head">事件图片</div>
              <div class="detail-image-frame" @click="openImagePreview(getImageUrl(eventDetail.thumbnail_path), getEventTypeName(eventDetail.event_type))">
                <img
                  :src="getImageUrl(eventDetail.thumbnail_path)"
                  alt="事件图片"
                  @error="handleImageError"
                />
                <span class="image-zoom-hint">点击放大</span>
      </div>
            </div>
          </div>
        </template>
          </div>
    </el-dialog>

    <!-- 抓拍 / 图片大图 -->
    <el-dialog
      v-model="showImagePreviewDialog"
      width="82%"
      :top="'4vh'"
      class="board-image-dialog"
      header-class="board-dialog-header"
      body-class="board-dialog-body board-dialog-body-image"
      destroy-on-close
      append-to-body
      :show-close="false"
    >
      <template #header>
        <div class="dialog-head">
          <span class="dialog-title">{{ imagePreviewTitle }}</span>
          <button class="dialog-close" @click="showImagePreviewDialog = false">关闭</button>
          </div>
        </template>
      <div class="image-preview-wrap">
        <img v-if="imagePreviewUrl" :src="imagePreviewUrl" alt="预览" class="preview-image" />
      </div>
      </el-dialog>
    </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { detectionEventApi } from '@/api/detection.js'
import { useDashboardData } from '@/composables/useDashboardData.js'

const {
  data,
  refreshData,
  startAutoRefresh,
  stopAutoRefresh,
  typeChartTitle,
  deviceChartTitle,
  thirdPanelTitle,
} = useDashboardData()

const currentTime = ref('')
const trendChartRef = ref(null)
const systemChartRef = ref(null)
const typeChartRef = ref(null)
const deviceChartRef = ref(null)
const hourlyChartRef = ref(null)
const eventTableRef = ref(null)
const showEventDetailDialog = ref(false)
const showImagePreviewDialog = ref(false)
const eventDetailLoading = ref(false)
const eventDetail = ref(null)
const imagePreviewUrl = ref('')
const imagePreviewTitle = ref('图片预览')

let timeTimer = null
let scrollTimer = null
let autoScrollPaused = false
let scrollPausePointerId = null
let removeScrollPauseHandlers = null
let trendChart = null
let systemChart = null
let typeChart = null
let deviceChart = null
let hourlyChart = null

const boardGridRef = ref(null)
const boardFooterRef = ref(null)
let layoutObserver = null

const kpiList = computed(() => data.kpiList)
const overviewSummary = computed(() => data.overviewSummary || {})
const alertHistory = computed(() => data.alertHistory)
const liveMonitors = computed(() => data.liveMonitors)
const lastUpdated = computed(() => data.lastUpdated)
const historicalStats = computed(() => data.historicalStats)
const performanceTrend = computed(() => data.performanceTrend)
const typeStats = computed(() => data.typeStats)
const deviceRanking = computed(() => data.deviceRanking)
const hourlyStats = computed(() => data.hourlyStats)
const alertFeed = computed(() => data.alertFeed)
const waitTimeData = computed(() => data.waitTimeData)
const useWaitTimeChart = computed(() => data.useWaitTimeChart)
const systemStatus = computed(() => data.systemStatus)
const screenTitle = computed(() => data.screenName || '边缘AI展示大屏')

const CHART_THEME = {
  text: '#cbd5e1',
  axis: 'rgba(255,138,101,0.5)',
  split: 'rgba(255,255,255,0.08)',
  tooltipBg: 'rgba(15,26,46,0.92)',
}

const getImageUrl = (path) => {
  if (!path) return ''
  return `/api/v1/files/${String(path).replace(/\\/g, '/')}`
}

const handleImageError = (e) => {
  e.target.style.display = 'none'
}

const EVENT_TYPE_MAP = {
  object_detection: '目标检测',
  yolo_verify: '二次复检',
  yolo_analyze: '行为分析',
  smart_behavior: '智能行为',
  smart_person: '人员场景',
  smart_counting: '智能人数统计',
  segmentation: '图像分割',
  keypoint: '关键点检测',
  pose: '姿态估计',
  face: '人脸识别',
  other: '其他类型',
}

const STATUS_LABEL_MAP = {
  new: '未处理',
  viewed: '已查看',
  flagged: '已标记',
  archived: '已归档',
}

const getEventTypeName = (type) => EVENT_TYPE_MAP[type] || type || '未知类型'
const getStatusLabel = (status) => STATUS_LABEL_MAP[status] || status || '未知'
const getStatusBadge = (status) => {
  const map = { new: 'danger', viewed: 'success', flagged: 'warning', archived: 'success' }
  return map[status] || 'info'
}

const formatDateTime = (iso) => {
  if (!iso) return '--'
  return new Date(iso).toLocaleString('zh-CN')
}

const formatConfidence = (val) => {
  if (val == null) return '--'
  if (typeof val === 'string') return val.includes('%') ? val : `${val}%`
  const n = val > 1 ? val : val * 100
  return `${Number(n).toFixed(1)}%`
}

const getEventDescription = (event) => {
  if (!event) return '-'
  const meta = event.meta_data
  if (meta && typeof meta === 'object') {
    return meta.event_description || meta.pushLabel || meta.summary || '-'
  }
  return '-'
}

const getDetectionTargets = (event) => {
  if (!event) return []
  if (event.meta_data?.yolo?.detections?.length) {
    return event.meta_data.yolo.detections.map((item) => ({
      class_name: item.class_name || '未知',
      confidence: item.confidence || 0,
      bbox: item.bbox,
    }))
  }
  if (Array.isArray(event.bounding_box) && event.bounding_box.length) {
    return event.bounding_box.map((item) => ({
      class_name: item.class_name || '未知',
      confidence: item.confidence || 0,
      bbox: item.bbox || item.bounding_box,
    }))
  }
  return []
}

const formatBoundingBox = (bbox) => {
  if (!bbox) return '-'
  if (Array.isArray(bbox) && bbox.length === 4) {
    return `(${bbox[0]}, ${bbox[1]}) - (${bbox[2]}, ${bbox[3]})`
  }
  if (bbox.x1 != null) return `(${bbox.x1}, ${bbox.y1}) - (${bbox.x2}, ${bbox.y2})`
  return '-'
}

const openEventDetail = async (row) => {
  showEventDetailDialog.value = true
  eventDetailLoading.value = true
  eventDetail.value = null
  try {
    const res = await detectionEventApi.getEvent(row.id)
    eventDetail.value = { ...res.data, device_name: row.device }
    await markEventViewed(row, eventDetail.value)
  } catch {
    eventDetail.value = {
      event_id: row.id,
      device_name: row.device,
      event_type: row.type,
      confidence: row.confidence,
      status: row.rawStatus || 'new',
      thumbnail_path: row.image,
      meta_data: { event_description: row.name },
    }
    await markEventViewed(row, eventDetail.value)
  } finally {
    eventDetailLoading.value = false
  }
}

const markEventViewed = async (row, detail) => {
  const currentStatus = detail?.status ?? row.rawStatus
  if (currentStatus !== 'new') return
  try {
    await detectionEventApi.updateEventStatus(row.id, 'viewed')
    if (detail) detail.status = 'viewed'
    const item = data.alertHistory.find((e) => e.id === row.id)
    if (item) {
      item.rawStatus = 'viewed'
      item.status = 'success'
      item.statusText = '已查看'
      item.isNew = false
    }
  } catch (error) {
    console.error('标记已查看失败:', error)
  }
}

const openSnapPreview = (item) => {
  if (!item.image) return
  openImagePreview(getImageUrl(item.image), item.name || '抓拍预览')
}

const openImagePreview = (url, title = '图片预览') => {
  imagePreviewUrl.value = url
  imagePreviewTitle.value = title
  showImagePreviewDialog.value = true
}

const formatDateLabel = (iso) => {
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

const emptyChartOption = (text) => ({
  backgroundColor: 'transparent',
  title: {
    text,
    left: 'center',
    top: 'middle',
    textStyle: { color: 'rgba(255,255,255,0.45)', fontSize: 13, fontWeight: 'normal' },
  },
  series: [],
})

const updateTrendChart = () => {
  if (!trendChart) return
  const rows = historicalStats.value || []
  if (!rows.length) {
    trendChart.setOption(emptyChartOption('暂无趋势数据'), true)
    return
  }
  trendChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 42, right: 16, top: 28, bottom: 28 },
    legend: {
      data: ['检测', '规则', '订阅'],
      textStyle: { color: CHART_THEME.text, fontSize: 11 },
      top: 0,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: CHART_THEME.tooltipBg,
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => formatDateLabel(r.date)),
      axisLabel: { color: CHART_THEME.text, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART_THEME.axis } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: CHART_THEME.text, fontSize: 11 },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    series: [
      { name: '检测', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5, data: rows.map((r) => r.detection), itemStyle: { color: '#4a90e2' }, areaStyle: { color: 'rgba(74,144,226,0.15)' } },
      { name: '规则', type: 'line', smooth: true, symbol: 'none', data: rows.map((r) => r.alertRule), itemStyle: { color: '#ffbf00' } },
      { name: '订阅', type: 'line', smooth: true, symbol: 'none', data: rows.map((r) => r.smart), itemStyle: { color: '#66b1ff' } },
    ],
  }, true)
}

const updateSystemChart = () => {
  if (!systemChart) return
  const s = systemStatus.value
  const items = []
  if (s.cpu?.percent != null) items.push({ name: 'CPU', value: s.cpu.percent, color: ['#66b1ff', '#ff6b6b'] })
  if (s.memory?.percent != null) items.push({ name: '内存', value: s.memory.percent, color: ['#4a90e2', '#1e3c72'] })
  if (s.disk?.percent != null) items.push({ name: '磁盘', value: s.disk.percent, color: ['#ffbf00', '#66b1ff'] })
  if (s.gpu?.percent > 0) items.push({ name: 'GPU', value: s.gpu.percent, color: ['#2ec7cd', '#1fdac5'] })
  if (!items.length) {
    systemChart.setOption(emptyChartOption('暂无资源数据'), true)
    return
  }
  systemChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 48, right: 36, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value', max: 100,
      axisLabel: { color: CHART_THEME.text, formatter: '{value}%' },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.name),
      axisLabel: { color: CHART_THEME.text },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
      type: 'bar',
      barWidth: 14,
      data: items.map((i) => ({
        value: i.value,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: i.color[0] },
            { offset: 1, color: i.color[1] },
          ]),
        },
      })),
      label: { show: true, position: 'right', formatter: '{c}%', color: '#fff', fontSize: 11 },
    }],
  }, true)
}

const updateWaitTimeChart = () => {
  if (!systemChart) return
  const rows = waitTimeData.value || []
  if (!rows.length) {
    systemChart.setOption(emptyChartOption('暂无排队数据'), true)
    return
  }
  const projectNames = rows.map((item) => item.projectName)
  systemChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 8, right: 8, top: 28, bottom: 4, containLabel: true },
    legend: {
      data: ['排队时长', '排队人数', '项目时间'],
      textStyle: { color: CHART_THEME.text, fontSize: 9 },
      top: 0,
      itemWidth: 10,
      itemHeight: 8,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: CHART_THEME.tooltipBg,
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      data: projectNames,
      axisLabel: {
        color: CHART_THEME.text,
        fontSize: 9,
        interval: 0,
        rotate: projectNames.length > 4 ? 18 : 0,
      },
      axisLine: { lineStyle: { color: CHART_THEME.axis } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: CHART_THEME.text, fontSize: 9 },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    series: [
      {
        name: '排队时长',
        type: 'bar',
        data: rows.map((item) => item.waitingMinutes),
        barWidth: '22%',
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#66b1ff' },
            { offset: 1, color: '#ff6b6b' },
          ]),
        },
      },
      {
        name: '排队人数',
        type: 'bar',
        data: rows.map((item) => item.peopleCount),
        barWidth: '22%',
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#4a90e2' },
            { offset: 1, color: '#1e3c72' },
          ]),
        },
      },
      {
        name: '项目时间',
        type: 'bar',
        data: rows.map((item) => item.projectInterval),
        barWidth: '22%',
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#2ec7cd' },
            { offset: 1, color: '#1fdac5' },
          ]),
        },
      },
    ],
  }, true)
}

const updateThirdPanelChart = () => {
  updateSystemChart()
}

const updatePerfChart = () => {
  if (!perfChart) return
  const rows = performanceTrend.value || []
  const hasData = rows.some((r) => r.avg_ms > 0)
  if (!hasData) {
    perfChart.setOption(emptyChartOption('暂无性能样本'), true)
    return
  }
  perfChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 40, right: 12, top: 16, bottom: 24 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: CHART_THEME.tooltipBg,
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params) => {
        const p = params[0]
        const raw = rows[p.dataIndex]
        return `${p.name}<br/>${p.value}ms · 样本 ${raw?.sample_count || 0}`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => formatDateLabel(r.date)),
      axisLabel: { color: CHART_THEME.text, fontSize: 10 },
      axisLine: { lineStyle: { color: CHART_THEME.axis } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART_THEME.text, fontSize: 10 },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    series: [{
      name: '均耗',
        type: 'line',
        smooth: true,
      data: rows.map((r) => r.avg_ms || 0),
      itemStyle: { color: '#2ec7cd' },
      areaStyle: { color: 'rgba(46,199,205,0.12)' },
    }],
  }, true)
}

const updateHourlyChart = () => {
  if (!hourlyChart) return
  const rows = hourlyStats.value || []
  if (!rows.some((r) => r.count > 0)) {
    hourlyChart.setOption(emptyChartOption('暂无时段数据'), true)
    return
  }
  hourlyChart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 32, right: 8, top: 12, bottom: 22 },
    tooltip: { trigger: 'axis', backgroundColor: CHART_THEME.tooltipBg, borderWidth: 0, textStyle: { color: '#fff' } },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.label),
      axisLabel: { color: CHART_THEME.text, fontSize: 9, interval: 3 },
      axisLine: { lineStyle: { color: CHART_THEME.axis } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: CHART_THEME.text, fontSize: 10 },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      barWidth: '55%',
      data: rows.map((r) => r.count),
        itemStyle: {
        borderRadius: [2, 2, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#66b1ff' },
          { offset: 1, color: 'rgba(255,138,101,0.2)' },
        ]),
      },
    }],
  }, true)
}

const updateBarChart = (chart, items, emptyText, valueLabel = '') => {
  if (!chart) return
  if (!items?.length) {
    chart.setOption(emptyChartOption(emptyText), true)
    return
  }
  const names = items.map((i) => i.name).reverse()
  const values = items.map((i) => i.value).reverse()
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: CHART_THEME.tooltipBg,
      borderWidth: 0,
      textStyle: { color: '#fff' },
      formatter: (params) => {
        const p = params[0]
        return `${p.name}<br/>${valueLabel || '数量'}：${p.value}`
      },
    },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: CHART_THEME.text, fontSize: 10 },
      splitLine: { lineStyle: { color: CHART_THEME.split, type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: { color: CHART_THEME.text, fontSize: 10, width: 72, overflow: 'truncate' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
        type: 'bar',
      barWidth: 12,
      data: values,
          itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#4a90e2' },
          { offset: 1, color: '#66b1ff' },
        ]),
      },
      label: { show: true, position: 'right', color: '#fff', fontSize: 10 },
    }],
  }, true)
}

const refreshCharts = () => {
  nextTick(() => {
    trendChart?.resize()
    systemChart?.resize()
    typeChart?.resize()
    deviceChart?.resize()
    hourlyChart?.resize()
    updateTrendChart()
    updateThirdPanelChart()
    updateHourlyChart()
    updateBarChart(typeChart, typeStats.value, '暂无类型统计')
    updateBarChart(deviceChart, deviceRanking.value, '暂无设备告警')
  })
}

const initCharts = () => {
  if (trendChartRef.value) trendChart = echarts.init(trendChartRef.value)
  if (systemChartRef.value) systemChart = echarts.init(systemChartRef.value)
  if (typeChartRef.value) typeChart = echarts.init(typeChartRef.value)
  if (deviceChartRef.value) deviceChart = echarts.init(deviceChartRef.value)
  if (hourlyChartRef.value) hourlyChart = echarts.init(hourlyChartRef.value)
  refreshCharts()
}

const onResize = () => {
  refreshCharts()
}

const observeLayout = () => {
  if (layoutObserver) layoutObserver.disconnect()
  const el = boardGridRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  layoutObserver = new ResizeObserver(() => onResize())
  layoutObserver.observe(el)
  if (boardFooterRef.value) layoutObserver.observe(boardFooterRef.value)
}

const updateClock = () => {
  currentTime.value = new Date().toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).replace(/\//g, '-')
}

const scrollContainer = (el) => {
  if (autoScrollPaused) return
  if (!el || el.scrollHeight <= el.clientHeight) return
  el.scrollTop += 1
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 2) el.scrollTop = 0
}

const pauseAutoScroll = (e) => {
  autoScrollPaused = true
  scrollPausePointerId = e.pointerId
}

const resumeAutoScroll = (e) => {
  if (scrollPausePointerId != null && e?.pointerId != null && e.pointerId !== scrollPausePointerId) return
  autoScrollPaused = false
  scrollPausePointerId = null
}

const setupScrollPauseHandlers = () => {
  const scrollPanelSelector = '.event-table, .feed-list'
  const onPointerDown = (e) => {
    if (e.target.closest?.(scrollPanelSelector)) pauseAutoScroll(e)
  }
  window.addEventListener('pointerdown', onPointerDown)
  window.addEventListener('pointerup', resumeAutoScroll)
  window.addEventListener('pointercancel', resumeAutoScroll)
  return () => {
    window.removeEventListener('pointerdown', onPointerDown)
    window.removeEventListener('pointerup', resumeAutoScroll)
    window.removeEventListener('pointercancel', resumeAutoScroll)
  }
}

const startAutoScroll = () => {
  if (scrollTimer) clearInterval(scrollTimer)
  scrollTimer = setInterval(() => {
    scrollContainer(eventTableRef.value)
  }, 50)
}

watch([
  historicalStats, typeStats, deviceRanking,
  hourlyStats, systemStatus,
], refreshCharts, { deep: true })

onMounted(async () => {
  updateClock()
  timeTimer = setInterval(updateClock, 1000)
  await refreshData()
  setTimeout(() => {
    initCharts()
    observeLayout()
  }, 80)
  startAutoRefresh(120000)
  startAutoScroll()
  removeScrollPauseHandlers = setupScrollPauseHandlers()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  if (timeTimer) clearInterval(timeTimer)
  if (scrollTimer) clearInterval(scrollTimer)
  removeScrollPauseHandlers?.()
  removeScrollPauseHandlers = null
  stopAutoRefresh()
  window.removeEventListener('resize', onResize)
  layoutObserver?.disconnect()
  trendChart?.dispose()
  systemChart?.dispose()
  typeChart?.dispose()
  deviceChart?.dispose()
  hourlyChart?.dispose()
})

</script>

<style scoped>
.board-page {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--edge-board-text);
  background: linear-gradient(
    160deg,
    var(--edge-board-bg-start) 0%,
    var(--edge-board-bg-mid) 45%,
    var(--edge-board-bg-end) 100%
  );
  font-family: 'Microsoft YaHei', sans-serif;
  --board-side-col: minmax(220px, 20%);
  --board-grid-gap: 10px;
  --board-grid-padding-x: 16px;
}

.board-stage--full-map {
  --board-side-col: minmax(168px, 16%);
  --board-grid-gap: 8px;
  --board-grid-padding-x: 10px;
}

.board-header {
  flex: 0 0 52px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid var(--edge-board-panel-border);
  background: var(--edge-board-header-bg);
}

.header-left { display: flex; flex-direction: column; gap: 1px; }
.clock { font-size: 14px; font-weight: 500; }
.sync-hint { font-size: 10px; color: rgba(255,255,255,0.45); }

.header-title {
  margin: 0;
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 1px;
  background: linear-gradient(90deg, #ffffff, #b3d8ff);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.header-right {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  font-size: 12px;
}

.header-kpi-hint span {
  color: #cbd5e1;
  white-space: nowrap;
}

.kpi-row {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 6px 16px 0;
}

.kpi-row-secondary {
  padding-top: 4px;
  padding-bottom: 2px;
}

.kpi-card {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(20, 40, 70, 0.55);
  border: 1px solid rgba(64, 158, 255, 0.22);
  min-width: 0;
}

.kpi-card-secondary {
  padding: 5px 10px;
  background: rgba(16, 32, 58, 0.45);
  border-color: rgba(64, 158, 255, 0.15);
}

.kpi-card.highlight {
  border-color: rgba(255, 107, 107, 0.5);
  box-shadow: 0 0 10px rgba(255, 107, 107, 0.15);
}

.kpi-value {
  font-size: 17px;
  font-weight: 600;
  line-height: 1.2;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-row-secondary .kpi-value {
  font-size: 15px;
  font-weight: 500;
}

.kpi-label {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(255,255,255,0.78);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-row-secondary .kpi-label {
  font-size: 10px;
  color: rgba(255,255,255,0.65);
}

.kpi-sub {
  margin-top: 1px;
  font-size: 9px;
  color: rgba(255,255,255,0.42);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.board-stage {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.board-stage--full-map .col-center-spacer {
  position: relative;
  z-index: 3;
  pointer-events: none;
}

.board-map-ui-anchor {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.board-stage--full-map .kpi-overlay {
  position: relative;
  z-index: 2;
  pointer-events: none;
}

.board-stage--full-map .kpi-overlay .kpi-card {
  pointer-events: auto;
  background: rgba(20, 40, 70, 0.42);
  border-color: rgba(64, 158, 255, 0.18);
  backdrop-filter: blur(6px);
}

.board-content {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 1;
}

.col-center {
  min-height: 0;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
}

.col-center-hero {
  min-width: 0;
  min-height: 0;
  align-self: stretch;
  display: flex;
  flex-direction: column;
}

.panel-center-snaps {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--edge-board-panel-bg);
  border: 1px solid var(--edge-board-panel-border);
  border-radius: 8px;
  pointer-events: auto;
}

.panel-center-snaps .panel-head {
  flex: 0 0 auto;
}

.panel-center-snaps .panel-snaps-body {
  padding: 4px 6px 6px;
}

.empty-tip-snaps {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.45);
  font-size: 13px;
}

.col-right .panel-alerts {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-feed-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 8px 8px;
}

.feed-item-side {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  gap: 2px 8px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 10px;
}

.feed-item-side .feed-time {
  grid-column: 2;
  color: rgba(255, 255, 255, 0.45);
  font-size: 9px;
}

.board-grid {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-columns: var(--board-side-col) 1fr var(--board-side-col);
  gap: var(--board-grid-gap);
  padding: 6px var(--board-grid-padding-x);
  overflow: hidden;
  position: relative;
  z-index: 1;
  pointer-events: none;
}

.board-grid-overlay {
  pointer-events: none;
}

.col-center-spacer {
  min-height: 0;
  min-width: 0;
}

.board-footer {
  flex: 0 0 198px;
  display: grid;
  grid-template-columns: minmax(240px, 28%) 1fr;
  gap: var(--board-grid-gap);
  padding: 0 var(--board-grid-padding-x) 8px;
  min-height: 0;
  overflow: hidden;
  position: relative;
  z-index: 1;
  pointer-events: none;
}

.board-footer.board-footer--full-map {
  flex: 0 0 188px;
  padding-bottom: 6px;
}

.board-grid--full-map .panel-overlay,
.board-footer--full-map .panel-overlay {
  background: rgba(11, 20, 36, 0.52);
  backdrop-filter: blur(10px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}

.panel-footer {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-footer-events {
  min-width: 0;
}

.panel-footer-events .event-table {
  flex: 1 1 0;
}

.col {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.col-left,
.col-right {
  min-width: 0;
}

.panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  background: var(--edge-board-panel-bg);
  border: 1px solid var(--edge-board-panel-border);
  overflow: hidden;
}

.panel-overlay {
  pointer-events: auto;
  background: rgba(16, 32, 58, 0.78);
  backdrop-filter: blur(8px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
}

.panel-head {
  flex: 0 0 auto;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #f8fafc;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-meta {
  font-size: 10px;
  font-weight: normal;
  color: rgba(255,255,255,0.45);
}

.col-left .panel,
.col-right .panel-type,
.col-right .panel-device {
  flex: 1 1 0;
  min-height: 0;
}


.panel-snaps-body {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  padding: 0 6px 6px;
  display: flex;
  flex-direction: column;
}

.panel-snaps-body .snap-grid-3x2 {
  flex: 1 1 0;
}

.chart-box {
  flex: 1 1 0;
  min-height: 0;
  width: 100%;
}

.col-left .chart-side,
.col-right .chart-side {
  flex: 1 1 0;
  min-height: 56px;
  max-height: none;
}

.chart-footer { flex: 1 1 0; min-height: 0; }

.feed-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 10px 10px;
}

.feed-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 11px;
}

.feed-tag {
  grid-row: span 2;
  align-self: start;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  line-height: 1.4;
}

.feed-tag.composite { background: rgba(255,191,0,0.2); color: #ffd666; }
.feed-tag.smart { background: rgba(74,144,226,0.2); color: #8ec5ff; }

.panel-body-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.feed-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #f1f5f9;
}

.feed-meta {
  grid-column: 2;
  color: rgba(255,255,255,0.45);
  font-size: 10px;
}

.info-block {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 16px 10px;
  margin: 0 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-section {
  flex: 0 0 auto;
}

.info-title {
  font-size: 10px;
  color: rgba(255,255,255,0.55);
  margin-bottom: 3px;
  line-height: 1.3;
}

.info-row {
  display: grid;
  grid-template-columns: minmax(0, 52%) minmax(0, 48%);
  gap: 10px;
  align-items: center;
  font-size: 10px;
  line-height: 1.5;
  padding: 4px 0;
  min-height: 18px;
}

.info-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(255,255,255,0.72);
}

.info-val {
  font-size: 10px;
  text-align: right;
  word-break: break-all;
  white-space: normal;
  line-height: 1.35;
}

.info-val-bold {
  font-weight: 700;
  color: #ffd4b8;
  flex-shrink: 0;
}

.info-val-bold.fail {
  color: #ff9a9a;
}

.info-summary {
  display: grid;
  grid-template-columns: minmax(0, 52%) minmax(0, 48%);
  gap: 10px;
  align-items: center;
  padding: 8px 0 4px;
  margin-top: 2px;
  border-top: 1px solid rgba(64, 158, 255, 0.25);
  font-size: 10px;
}

.info-row .running { color: #a8e06c; }
.info-row .error { color: #ff9a9a; }
.info-row .stopped { color: rgba(255,255,255,0.45); }

.info-empty {
  font-size: 11px;
  padding: 2px 0 4px;
}

.empty-tip.compact {
  padding: 12px;
  min-height: auto;
}

.event-table {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  font-size: 11px;
}

.event-head,
.event-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr) minmax(0, 0.65fr) minmax(0, 0.9fr) minmax(0, 0.75fr);
  gap: 6px;
  padding: 6px 10px;
  align-items: center;
}

.event-head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgba(30, 60, 100, 0.95);
  color: rgba(255,255,255,0.75);
  font-size: 11px;
}

.event-row {
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

.event-row.is-new {
  background: rgba(255, 107, 107, 0.12);
}

.event-row span,
.event-head span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-wide { min-width: 0; }

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-style: normal;
  font-size: 11px;
}

.badge.danger { background: rgba(255,107,107,0.25); color: #ff8a8a; }
.badge.warning { background: rgba(255,191,0,0.2); color: #ffd666; }
.badge.success { background: rgba(76,175,80,0.2); color: #8fd694; }
.badge.info { background: rgba(74,144,226,0.2); color: #9ec5ff; }
.badge.active { background: rgba(74,144,226,0.2); color: #9ec5ff; }
.badge.sm { font-size: 10px; padding: 1px 6px; }

.info-empty {
  font-size: 10px;
  padding: 2px 0 4px;
  color: rgba(255,255,255,0.45);
}

.snap-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  padding: 8px;
}

.snap-grid-3x2 {
  height: 100%;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 0;
}

.snap-grid-3x2 .snap-item {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.snap-grid-3x2 .snap-item img,
.snap-grid-3x2 .snap-placeholder {
  flex: 1 1 0;
  min-height: 0;
  height: auto;
  width: 100%;
  object-fit: cover;
}

.snap-grid-3x2 .snap-meta {
  flex: 0 0 auto;
  padding: 2px 4px;
  font-size: 9px;
  line-height: 1.2;
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.snap-grid-3x2 .snap-meta span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snap-grid-3x2 .snap-meta .badge {
  flex-shrink: 0;
}

.snap-item {
  border-radius: 6px;
  overflow: hidden;
  background: #0a1020;
  border: 1px solid rgba(255,255,255,0.08);
}

.snap-item img {
  width: 100%;
  height: 58px;
  object-fit: cover;
  display: block;
}

.snap-placeholder {
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255,255,255,0.35);
  font-size: 12px;
}

.snap-meta {
  padding: 6px 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  min-width: 0;
}

.snap-meta span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snap-meta .badge {
  flex-shrink: 0;
}

.empty-tip {
  padding: 24px;
  text-align: center;
  color: rgba(255,255,255,0.4);
  font-size: 13px;
}

.dialog-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #fff;
  gap: 12px;
}

.dialog-head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.dialog-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.dialog-subtitle {
  font-size: 12px;
  color: rgba(255, 212, 184, 0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dialog-close {
  background: rgba(64, 158, 255, 0.18);
  border: 1px solid rgba(64, 158, 255, 0.35);
  color: #ffd4b8;
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.dialog-close:hover {
  background: rgba(64, 158, 255, 0.32);
}

.info-row .fail { color: #ff9a9a; }

.event-row-clickable {
  cursor: pointer;
  transition: background 0.15s;
}

.event-row-clickable:hover {
  background: rgba(74, 144, 226, 0.15);
}

.snap-img-clickable {
  cursor: zoom-in;
}

.snap-img-clickable:hover {
  opacity: 0.9;
}

.event-detail-body {
  min-height: 160px;
  color: #e2e8f0;
}

.detail-top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(64, 158, 255, 0.2);
}

.detail-id {
  font-size: 11px;
  color: rgba(255,255,255,0.45);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-layout {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 14px;
  align-items: start;
}

.detail-layout:not(:has(.detail-aside)) {
  grid-template-columns: 1fr;
}

.detail-stat-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.detail-stat {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(20, 40, 70, 0.55);
  border: 1px solid rgba(64, 158, 255, 0.18);
}

.detail-stat label {
  display: block;
  font-size: 10px;
  color: rgba(255,255,255,0.48);
  margin-bottom: 4px;
}

.detail-stat span {
  font-size: 13px;
  color: #f1f5f9;
  word-break: break-all;
}

.detail-highlight {
  color: #ffd4b8 !important;
  font-weight: 600;
}

.detail-panel {
  margin-bottom: 12px;
  border-radius: 8px;
  background: rgba(16, 32, 58, 0.5);
  border: 1px solid rgba(255,255,255,0.06);
  overflow: hidden;
}

.detail-panel-head {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(255,255,255,0.75);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.03);
}

.detail-panel-body {
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255,255,255,0.85);
}

.detail-aside {
  position: sticky;
  top: 0;
}

.detail-image-frame {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(64, 158, 255, 0.25);
  background: #0a1020;
  cursor: zoom-in;
}

.detail-image-frame img {
  display: block;
  width: 100%;
  max-height: 320px;
  object-fit: contain;
}

.image-zoom-hint {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  color: rgba(255,255,255,0.8);
  background: rgba(0,0,0,0.55);
}

.target-table {
  font-size: 11px;
}

.target-head,
.target-row {
  display: grid;
  grid-template-columns: 1fr 0.75fr 1.25fr;
  gap: 8px;
  padding: 7px 12px;
}

.target-head {
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.55);
  font-size: 10px;
}

.target-row {
  border-top: 1px solid rgba(255,255,255,0.05);
}

.target-row span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-preview-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 55vh;
  padding: 16px;
  background: linear-gradient(160deg, #0b1424 0%, #152a4a 100%);
}

.preview-image {
  max-width: 100%;
  max-height: 78vh;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid rgba(64, 158, 255, 0.25);
  box-shadow: 0 8px 32px rgba(0,0,0,0.45);
}

:deep(.board-event-dialog.el-dialog),
:deep(.board-image-dialog.el-dialog) {
  --el-dialog-bg-color: #152a4a;
  --el-text-color-primary: #e2e8f0;
  --el-text-color-regular: #cbd5e1;
  background: linear-gradient(160deg, #0b1424 0%, #152a4a 45%, #1a3358 100%) !important;
  border: 1px solid rgba(64, 158, 255, 0.35);
  border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

:deep(.board-event-dialog .el-dialog__header),
:deep(.board-image-dialog .el-dialog__header) {
  padding: 14px 18px;
  margin: 0;
  border-bottom: 1px solid rgba(64, 158, 255, 0.22);
  background: rgba(10, 20, 40, 0.65) !important;
}

:deep(.board-event-dialog .el-dialog__body),
:deep(.board-image-dialog .el-dialog__body) {
  padding: 16px 18px 18px;
  background: linear-gradient(160deg, #0b1424 0%, #152a4a 45%, #1a3358 100%) !important;
  color: #e2e8f0 !important;
}

:deep(.board-event-dialog .el-dialog__footer),
:deep(.board-image-dialog .el-dialog__footer) {
  padding: 12px 18px;
  background: rgba(10, 20, 40, 0.65) !important;
  border-top: 1px solid rgba(64, 158, 255, 0.18);
}

:deep(.board-event-dialog .el-loading-mask),
:deep(.board-image-dialog .el-loading-mask) {
  background-color: rgba(11, 20, 36, 0.88) !important;
}

:deep(.el-overlay) {
  background-color: rgba(5, 12, 24, 0.72) !important;
}

@media (max-width: 900px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }
  .detail-aside {
    position: static;
  }
}

@media (max-width: 1600px) {
  .board-page {
    --board-side-col: minmax(208px, 19%);
  }
  .board-stage--full-map {
    --board-side-col: minmax(168px, 16%);
  }
}

@media (max-width: 1400px) {
  .kpi-row { grid-template-columns: repeat(3, 1fr); }
  .board-page {
    --board-side-col: minmax(196px, 18%);
  }
  .board-stage--full-map {
    --board-side-col: minmax(168px, 16%);
  }
  .board-footer { flex: 0 0 192px; }
  .board-footer.board-footer--full-map { flex: 0 0 186px; }
}

@media (max-width: 1280px) {
  .board-page {
    --board-side-col: minmax(184px, 17%);
    --board-grid-gap: 8px;
    --board-grid-padding-x: 12px;
  }
  .board-stage--full-map {
    --board-side-col: minmax(164px, 16%);
    --board-grid-padding-x: 8px;
  }
  .col-left .chart-side,
  .col-right .chart-side {
    min-height: 64px;
  }
}

@media (max-width: 1100px) {
  .board-page {
    --board-side-col: minmax(176px, 16%);
    --board-grid-gap: 6px;
    --board-grid-padding-x: 8px;
  }
  .board-stage--full-map {
    --board-side-col: minmax(160px, 16%);
  }
  .panel-head { font-size: 11px; padding: 6px 10px; }
  .col-left .chart-side,
  .col-right .chart-side {
    min-height: 72px;
  }
}
</style>

<style>
/* append-to-body 弹窗需全局样式，避免底部白底 */
.board-event-dialog.el-dialog,
.board-image-dialog.el-dialog {
  --el-dialog-bg-color: #152a4a;
  --el-text-color-primary: #e2e8f0;
  --el-text-color-regular: #cbd5e1;
  --el-dialog-padding-primary: 0;
  background: linear-gradient(160deg, #0b1424 0%, #152a4a 45%, #1a3358 100%) !important;
  border: 1px solid rgba(64, 158, 255, 0.35);
  border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.55);
  overflow: hidden;
}

.board-dialog-header {
  padding: 14px 18px !important;
  margin: 0 !important;
  border-bottom: 1px solid rgba(64, 158, 255, 0.22);
  background: rgba(10, 20, 40, 0.65) !important;
}

.board-dialog-body {
  padding: 16px 18px 18px !important;
  background: linear-gradient(160deg, #0b1424 0%, #152a4a 45%, #1a3358 100%) !important;
  color: #e2e8f0 !important;
}

.board-dialog-body-image {
  padding: 0 !important;
}

.board-event-dialog .el-dialog__footer,
.board-image-dialog .el-dialog__footer {
  background: rgba(10, 20, 40, 0.65) !important;
  border-top: 1px solid rgba(64, 158, 255, 0.18);
}

.board-event-dialog .el-loading-mask,
.board-image-dialog .el-loading-mask {
  background-color: rgba(11, 20, 36, 0.88) !important;
}

.board-event-dialog .el-descriptions,
.board-event-dialog .el-descriptions__label,
.board-event-dialog .el-descriptions__content {
  color: #e2e8f0;
}

/* 展板滚动条深色主题 */
html:has(.board-page),
body:has(.board-page) {
  background: #0b1424;
  scrollbar-width: thin;
  scrollbar-color: rgba(64, 158, 255, 0.42) rgba(11, 20, 36, 0.92);
}

.board-page,
.board-page * {
  scrollbar-width: thin;
  scrollbar-color: rgba(64, 158, 255, 0.42) rgba(11, 20, 36, 0.92);
}

html:has(.board-page)::-webkit-scrollbar,
body:has(.board-page)::-webkit-scrollbar,
.board-page::-webkit-scrollbar,
.board-page *::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

html:has(.board-page)::-webkit-scrollbar-track,
body:has(.board-page)::-webkit-scrollbar-track,
.board-page::-webkit-scrollbar-track,
.board-page *::-webkit-scrollbar-track {
  background: rgba(11, 20, 36, 0.92);
  border-radius: 4px;
}

html:has(.board-page)::-webkit-scrollbar-thumb,
body:has(.board-page)::-webkit-scrollbar-thumb,
.board-page::-webkit-scrollbar-thumb,
.board-page *::-webkit-scrollbar-thumb {
  background: rgba(64, 158, 255, 0.38);
  border-radius: 4px;
  border: 1px solid rgba(11, 20, 36, 0.6);
}

html:has(.board-page)::-webkit-scrollbar-thumb:hover,
body:has(.board-page)::-webkit-scrollbar-thumb:hover,
.board-page::-webkit-scrollbar-thumb:hover,
.board-page *::-webkit-scrollbar-thumb:hover {
  background: rgba(64, 158, 255, 0.58);
}

.board-event-dialog,
.board-event-dialog *,
.board-image-dialog,
.board-image-dialog * {
  scrollbar-width: thin;
  scrollbar-color: rgba(64, 158, 255, 0.42) rgba(11, 20, 36, 0.92);
}

.board-event-dialog::-webkit-scrollbar,
.board-event-dialog *::-webkit-scrollbar,
.board-image-dialog::-webkit-scrollbar,
.board-image-dialog *::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.board-event-dialog::-webkit-scrollbar-track,
.board-event-dialog *::-webkit-scrollbar-track,
.board-image-dialog::-webkit-scrollbar-track,
.board-image-dialog *::-webkit-scrollbar-track {
  background: rgba(11, 20, 36, 0.92);
  border-radius: 4px;
}

.board-event-dialog::-webkit-scrollbar-thumb,
.board-event-dialog *::-webkit-scrollbar-thumb,
.board-image-dialog::-webkit-scrollbar-thumb,
.board-image-dialog *::-webkit-scrollbar-thumb {
  background: rgba(64, 158, 255, 0.38);
  border-radius: 4px;
}
</style>
