<template>
  <div class="home-container">
    <!-- 概况：设备 / 检测运行 / 告警与订阅 -->
    <el-row :gutter="20" class="stats-row">
      <el-col v-for="panel in homeOverviewPanels" :key="panel.key" :md="8" :sm="24" :xs="24">
        <el-card class="overview-panel-card" shadow="hover">
          <div class="overview-panel-head">
            <div class="overview-panel-title">
              <span class="overview-panel-icon" :style="{ color: panel.color }">
                <el-icon><component :is="panel.icon" /></el-icon>
              </span>
              <span class="overview-panel-label">{{ panel.label }}</span>
            </div>
            <div class="overview-panel-hero">{{ panel.value }}</div>
          </div>
          <div class="overview-panel-metrics">
            <div
              v-for="metric in panel.metrics"
              :key="metric.label"
              class="overview-metric-cell"
            >
              <div class="overview-metric-label">{{ metric.label }}</div>
              <div class="overview-metric-value" :class="metric.tone">{{ metric.value }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势 + 活动 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :md="16" :sm="24">
        <el-card class="overview-panel-card home-section-card" shadow="hover">
          <div class="overview-section-head">
            <div class="overview-panel-title">
              <span class="overview-panel-icon" style="color: #409eff">
                <el-icon><TrendCharts /></el-icon>
              </span>
              <span class="overview-panel-label">数据趋势分析</span>
            </div>
            <div class="chart-legend">
              <span class="legend-item"><span class="legend-color detection"></span>检测</span>
              <span class="legend-item"><span class="legend-color alert-rule"></span>规则</span>
              <span class="legend-item"><span class="legend-color scheme"></span>订阅</span>
            </div>
          </div>
          <div class="overview-section-body chart-container chart-container-trend">
            <div ref="chartRef" class="chart"></div>
          </div>
        </el-card>
      </el-col>

      <el-col :md="8" :sm="24">
        <el-card class="overview-panel-card home-section-card" shadow="hover">
          <div class="overview-section-head">
            <div class="overview-panel-title">
              <span class="overview-panel-icon" style="color: #67c23a">
                <el-icon><Clock /></el-icon>
              </span>
              <span class="overview-panel-label">最近活动</span>
            </div>
            <el-button type="primary" link @click="viewMoreEvents">更多</el-button>
          </div>
          <div class="overview-section-body activity-container activity-container-tall" ref="activityContainer">
            <div class="activity-list" :style="{ transform: `translateY(${scrollOffset}px)` }">
              <div
                v-for="activity in comprehensiveData.recent_activities"
                :key="activity.event_id"
                class="activity-item"
              >
                <div class="activity-content">
                  <div class="activity-text">{{ activity.content }}</div>
                  <div class="activity-meta">
                    <span class="activity-time">{{ activity.timestamp }}</span>
                    <el-tag size="small" :type="getActivityTagType(activity)">
                      {{ getActivitySourceLabel(activity) }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 三个饼图单独一行 -->
    <el-row :gutter="20" class="distribution-row">
      <el-col
        v-for="panel in piePanels"
        :key="panel.key"
        :lg="8"
        :md="8"
        :sm="24"
        :xs="24"
        class="pie-panel-col"
      >
        <el-card class="overview-panel-card home-section-card" shadow="hover">
          <div class="overview-section-head">
            <div class="overview-panel-title">
              <span class="overview-panel-icon" :style="{ color: panel.color }">
                <el-icon><PieChart /></el-icon>
              </span>
              <span class="overview-panel-label">{{ panel.title }}</span>
            </div>
            <el-radio-group
              v-if="panel.views.length > 1"
              v-model="pieViewMode[panel.key]"
              size="small"
              @change="() => renderSwitchablePie(panel.key)"
            >
              <el-radio-button
                v-for="view in panel.views"
                :key="view.value"
                :value="view.value"
              >
                {{ view.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
          <div class="overview-section-body distribution-chart distribution-chart-pie-row">
            <div :ref="(el) => bindPieChartRef(panel.key, el)" class="chart"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  VideoCameraFilled,
  DataLine,
  Bell,
  TrendCharts,
  Clock,
  PieChart
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import deviceApi from '@/api/device'

const router = useRouter()
const chartRef = ref(null)
const activityContainer = ref(null)

const piePanels = [
  {
    key: 'detection',
    title: '检测事件',
    color: '#409EFF',
    views: [
      { value: 'type', label: '类型' },
      { value: 'status', label: '状态' }
    ]
  },
  {
    key: 'alertRule',
    title: '规则引擎',
    color: '#67C23A',
    views: [
      { value: 'rule', label: '规则' },
      { value: 'status', label: '状态' }
    ]
  },
  {
    key: 'scheme',
    title: '订阅事件',
    color: '#E6A23C',
    views: [{ value: 'scheme', label: '方案' }]
  }
]

const pieViewMode = reactive({
  detection: 'type',
  alertRule: 'rule',
  scheme: 'scheme'
})

const pieChartRefMap = {}
const pieChartInstanceMap = {}

const bindPieChartRef = (key, el) => {
  if (el) {
    pieChartRefMap[key] = el
  }
}

let chart = null

const PIE_COLORS = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#626AEF', '#909399', '#36CFC9', '#B37FEB']

const comprehensiveData = reactive({
  summary: {},
  events: {},
  distributions: {},
  users: {},
  performance: {},
  trends: {},
  recent_activities: []
})

const loading = ref(false)
const scrollOffset = ref(0)
let scrollInterval = null

const formatDetectionTimeValue = (performance) => {
  const sampleCount = performance?.avg_detection_time_sample_count ?? 0
  if (!sampleCount) return '--'
  const value = performance?.avg_detection_time
  if (value == null || Number.isNaN(Number(value))) return '--'
  return `${Number(value).toFixed(1)} ms`
}

const homeOverviewPanels = computed(() => {
  const s = comprehensiveData.summary || {}
  const detection = comprehensiveData.events?.detection_events || {}
  const rules = comprehensiveData.events?.alert_rules || {}
  const scheme = comprehensiveData.events?.scheme_events || {}
  const pending = detection.status_distribution?.new ?? 0
  const avgTime = formatDetectionTimeValue(comprehensiveData.performance)

  return [
    {
      key: 'device',
      icon: VideoCameraFilled,
      color: '#409EFF',
      value: s.total_devices ?? 0,
      label: '设备接入',
      metrics: [
        { label: '在线', value: s.online_devices ?? 0, tone: 'tone-success' },
        { label: '离线', value: s.offline_devices ?? 0, tone: 'tone-danger' },
        {
          label: '检测路数',
          value: `${s.active_detection_configs ?? 0} / ${s.total_detection_configs ?? 0}`,
          tone: ''
        }
      ]
    },
    {
      key: 'detection',
      icon: DataLine,
      color: '#67C23A',
      value: s.active_detection_configs ?? 0,
      label: '检测运行',
      metrics: [
        {
          label: 'YOLO 模型',
          value: `${s.active_models ?? 0} / ${s.total_models ?? 0}`,
          tone: ''
        },
        { label: '今日事件', value: detection.today ?? 0, tone: 'tone-primary' },
        { label: '近 7 天均耗', value: avgTime, tone: 'tone-warn' }
      ]
    },
    {
      key: 'alert',
      icon: Bell,
      color: '#E6A23C',
      value: rules.today ?? 0,
      label: '告警与订阅',
      metrics: [
        { label: '订阅今日', value: scheme.today ?? 0, tone: 'tone-primary' },
        { label: '待处理', value: pending, tone: 'tone-danger' },
        {
          label: '规则启用',
          value: `${rules.rule_enabled ?? 0} / ${rules.rule_total ?? 0}`,
          tone: ''
        }
      ]
    }
  ]
})

// 获取完整仪表盘数据
const fetchComprehensiveData = async () => {
  loading.value = true
  try {
    const response = await deviceApi.getComprehensiveDashboardOverview()
    if (response.status === 200) {
      Object.assign(comprehensiveData, response.data)
      // 更新图表
      renderCharts()
      // 启动活动滚动
      startActivityScroll()
    }
  } catch (error) {
    console.error('获取仪表盘数据失败:', error)
    ElMessage.error('获取仪表盘数据失败')
  } finally {
    loading.value = false
  }
}

// 启动活动滚动
const startActivityScroll = () => {
  if (scrollInterval) {
    clearInterval(scrollInterval)
  }

  if (comprehensiveData.recent_activities && comprehensiveData.recent_activities.length > 0) {
    scrollInterval = setInterval(() => {
      scrollOffset.value -= 1
      // 当滚动到底部时，重置到顶部
      if (scrollOffset.value <= -comprehensiveData.recent_activities.length * 60) {
        scrollOffset.value = 0
      }
    }, 50)
  }
}

// 渲染所有图表
const renderCharts = () => {
  renderTrendChart()
  renderAllSwitchablePies()
}

const initChartInstance = (chartInstance, chartRef) => {
  if (!chartRef.value) return chartInstance
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  return chartInstance
}

const getSwitchablePieData = (key, mode) => {
  if (key === 'detection') {
    if (mode === 'type') {
      const typeDistribution = comprehensiveData.events?.detection_events?.type_distribution || {}
      return {
        seriesName: '检测事件类型',
        items: Object.entries(typeDistribution).map(([type, count]) => ({
          name: getEventTypeName(type),
          value: count
        }))
      }
    }
    const statusDistribution = comprehensiveData.events?.detection_events?.status_distribution || {}
    return {
      seriesName: '检测事件状态',
      items: Object.entries(statusDistribution).map(([status, count]) => ({
        name: getStatusLabel(status),
        value: count
      }))
    }
  }

  if (key === 'alertRule') {
    if (mode === 'rule') {
      const ruleDistribution = comprehensiveData.events?.alert_rules?.rule_distribution || {}
      return {
        seriesName: '规则命中分布',
        items: Object.entries(ruleDistribution).map(([ruleName, count]) => ({
          name: ruleName || '未命名规则',
          value: count
        }))
      }
    }
    const statusDistribution = comprehensiveData.events?.alert_rules?.status_distribution || {}
    return {
      seriesName: '规则告警状态',
      items: Object.entries(statusDistribution).map(([status, count]) => ({
        name: getAlertStatusLabel(status),
        value: count
      }))
    }
  }

  if (key === 'scheme') {
    const distribution = comprehensiveData.events?.scheme_events?.scheme_distribution || []
    return {
      seriesName: '订阅方案',
      items: distribution.map((item) => ({
        name: item.scheme_name || '未命名方案',
        value: item.count || 0
      }))
    }
  }

  return { seriesName: '', items: [] }
}

const renderSwitchablePie = (key) => {
  const chartEl = pieChartRefMap[key]
  if (!chartEl) return

  const { seriesName, items } = getSwitchablePieData(key, pieViewMode[key])
  pieChartInstanceMap[key] = renderPieChart(
    pieChartInstanceMap[key],
    { value: chartEl },
    seriesName,
    items,
    { compact: true }
  )
}

const renderAllSwitchablePies = () => {
  nextTick(() => {
    piePanels.forEach((panel) => renderSwitchablePie(panel.key))
  })
}

const renderPieChart = (chartInstance, chartRef, seriesName, items, { compact = false } = {}) => {
  if (!chartRef.value) return chartInstance

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const data = (items || []).filter((item) => item.value > 0)
  if (!data.length) {
    chartInstance.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'middle',
        textStyle: { color: '#909399', fontSize: 14, fontWeight: 'normal' }
      },
      series: []
    }, true)
    return chartInstance
  }

  chartInstance.setOption({
    color: PIE_COLORS,
    title: { show: false },
    tooltip: {
      trigger: 'item',
      formatter: '{b}<br/>{c} ({d}%)'
    },
    legend: {
      type: 'scroll',
      bottom: 0,
      left: 'center',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: compact ? 10 : 11 }
    },
    series: [
      {
        name: seriesName,
        type: 'pie',
        radius: compact ? ['34%', '56%'] : ['40%', '65%'],
        center: compact ? ['50%', '48%'] : ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          formatter: (params) => (params.percent >= (compact ? 10 : 8) ? `${params.name}\n${params.percent.toFixed(0)}%` : ''),
          fontSize: compact ? 10 : 11
        },
        labelLine: {
          show: true,
          length: 8,
          length2: 6
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.15)'
          }
        },
        data
      }
    ]
  }, true)

  return chartInstance
}

// 渲染趋势图表
const renderTrendChart = () => {
  if (!chartRef.value) return

  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  const trends = comprehensiveData.trends?.daily || []
  const dates = trends.map(item => item.date)
  const detectionData = trends.map(item => item.detection_events)
  const alertRuleData = trends.map(item => item.alert_rules)
  const schemeData = trends.map(item => item.scheme_events)

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: ['检测事件', '规则告警', '订阅事件']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        rotate: 30
      }
    },
    yAxis: {
      type: 'value',
      name: '数量'
    },
    series: [
      {
        name: '检测事件',
        type: 'line',
        data: detectionData,
        itemStyle: {
          color: '#409EFF'
        },
        smooth: true
      },
      {
        name: '规则告警',
        type: 'line',
        data: alertRuleData,
        itemStyle: {
          color: '#67C23A'
        },
        smooth: true
      },
      {
        name: '订阅事件',
        type: 'line',
        data: schemeData,
        itemStyle: {
          color: '#F56C6C'
        },
        smooth: true
      }
    ]
  }

  chart.setOption(option)
}

// 获取模型类型名称
const getEventTypeName = (eventType) => {
  const typeMap = {
    'object_detection': '目标检测',
    'yolo_verify': '二次复检',
    'yolo_analyze': '行为分析',
    'smart_behavior': '智能行为',
    'smart_person': '人员场景',
    'smart_counting': '智能人数统计',
    'segmentation': '图像分割',
    'keypoint': '关键点检测',
    'pose': '姿态估计',
    'face': '人脸识别',
    'other': '其他类型'
  }
  return typeMap[eventType] || eventType
}

const getActivitySourceLabel = (activity) => {
  const content = activity?.content || ''
  if (activity?.source === 'alert_rule') return '规则引擎'
  if (activity?.source === 'smart_scheme') return '事件订阅'
  return '本地检测'
}

const getActivityTagType = (activity) => {
  const content = activity?.content || ''
  if (activity?.source === 'alert_rule') return 'success'
  if (activity?.source === 'smart_scheme') return 'danger'
  return 'primary'
}

// 获取告警状态标签
const getAlertStatusLabel = (status) => {
  const map = {
    new: '新建',
    acknowledged: '已确认',
    ignored: '已忽略'
  }
  return map[status] || status
}

// 获取状态标签
const getStatusLabel = (status) => {
  const map = {
    'new': '新事件',
    'viewed': '已查看',
    'flagged': '已标记',
    'archived': '已归档'
  };
  return map[status] || status;
};

// 查看更多事件
const viewMoreEvents = () => {
  router.push('/detection/events')
}

// 窗口大小变化时调整图表大小
const handleResize = () => {
  if (chart) chart.resize()
  Object.values(pieChartInstanceMap).forEach((instance) => instance?.resize())
}

// 页面加载时获取数据
onMounted(() => {
  fetchComprehensiveData()
  window.addEventListener('resize', handleResize)
})

// 组件卸载时移除事件监听
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (scrollInterval) {
    clearInterval(scrollInterval)
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
  Object.keys(pieChartInstanceMap).forEach((key) => {
    pieChartInstanceMap[key]?.dispose()
    delete pieChartInstanceMap[key]
  })
})

// 监听数据变化，更新图表
watch(comprehensiveData, () => {
  renderCharts()
}, { deep: true })
</script>

<style scoped>
.home-container {
  height: 100%;
  min-width: 0;
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
  text-align: center;
}


.stats-row,
.chart-row,
.distribution-row {
  margin-bottom: 20px;
}

.overview-panel-card {
  border: 1px solid var(--edge-card-border);
  height: 100%;
  box-shadow: 0 2px 12px rgba(26, 58, 92, 0.04);
}

.overview-panel-card :deep(.el-card__body) {
  padding: 18px 20px 16px;
  background: var(--edge-card-bg);
}

.home-section-card :deep(.el-card__body) {
  padding: 18px 20px 16px;
}

.overview-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--edge-divider);
}

.overview-section-body {
  min-width: 0;
}

.overview-panel-card :deep(.el-card__body) {
  padding: 18px 20px 16px;
}

.overview-panel-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.overview-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.overview-panel-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(64, 158, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.overview-panel-icon .el-icon {
  font-size: 22px;
}

.overview-panel-label {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.overview-panel-hero {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
  flex-shrink: 0;
}

.overview-panel-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--edge-divider);
}

.overview-metric-cell {
  text-align: center;
  padding: 8px 6px;
  border-radius: 6px;
  background: rgba(64, 158, 255, 0.04);
}

.overview-metric-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
  line-height: 1.3;
}

.overview-metric-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
  word-break: break-all;
}

.overview-metric-value.tone-success {
  color: #67c23a;
}

.overview-metric-value.tone-danger {
  color: #f56c6c;
}

.overview-metric-value.tone-primary {
  color: #409eff;
}

.overview-metric-value.tone-warn {
  color: #e6a23c;
}

@media (max-width: 768px) {
  .overview-panel-metrics {
    grid-template-columns: 1fr;
  }

  .overview-metric-cell {
    display: flex;
    align-items: center;
    justify-content: space-between;
    text-align: left;
    padding: 10px 12px;
  }

  .overview-metric-label {
    margin-bottom: 0;
  }
}

.chart-container-trend,
.activity-container-tall {
  height: 300px;
}

.distribution-chart-pie-row {
  height: 260px;
}

.distribution-chart-pie-row .chart {
  height: 100%;
  min-height: 220px;
}

.chart-legend {
  display: flex;
  gap: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #606266;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  margin-right: 4px;
}

.legend-color.detection {
  background-color: #409EFF;
}

.legend-color.alert-rule {
  background-color: #67C23A;
}

.legend-color.scheme {
  background-color: #F56C6C;
}

.legend-color.logs {
  background-color: #E6A23C;
}

.chart-container {
  height: 350px;
  width: 100%;
}

.chart {
  height: 100%;
  width: 100%;
}

.activity-container {
  height: 350px;
  overflow: hidden;
  position: relative;
}

.activity-list {
  transition: transform 0.5s ease;
}

.activity-item {
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 6px;
  background: rgba(64, 158, 255, 0.04);
}

.activity-item:last-child {
  margin-bottom: 0;
}

.activity-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.activity-text {
  font-size: 13px;
  line-height: 1.4;
  color: #303133;
}

.activity-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.activity-time {
  font-size: 12px;
  color: #909399;
}

.pie-panel-col {
  margin-bottom: 16px;
}

.distribution-chart-compact {
  height: 280px;
}

.distribution-chart-bar {
  height: 340px;
}

.section-hint {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}

.distribution-chart {
  height: 300px;
  width: 100%;
}

.dual-chart-container {
  display: flex;
  gap: 20px;
  height: 380px;
}

.chart-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chart-title {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
  text-align: center;
  margin-bottom: 10px;
  padding: 8px;
  background: rgba(64, 158, 255, 0.08);
  border-radius: 4px;
}

.dual-chart-container .distribution-chart {
  flex: 1;
  height: auto;
  min-height: 250px;
}

@media screen and (max-width: 1200px) {
  .el-col {
    margin-bottom: 20px;
  }
}

@media screen and (max-width: 768px) {
  .el-card {
    margin-bottom: 16px;
  }

  .chart-container {
    height: 250px;
  }

  .distribution-chart {
    height: 200px;
  }

  .distribution-chart-compact {
    height: 240px;
  }

  .distribution-chart-bar {
    height: 280px;
  }

  .chart-legend {
    flex-direction: column;
    gap: 8px;
  }

  .dual-chart-container {
    flex-direction: column;
    height: auto;
    gap: 10px;
  }

  .dual-chart-container .distribution-chart {
    min-height: 200px;
  }
}
</style>