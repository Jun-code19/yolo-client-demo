<template>
  <div class="smart-events">
    <div class="page-header">
      <div class="header-content">
        <h2>事件管理</h2>
        <p>查看和管理事件订阅产生的事件记录</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshData" :loading="loading">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <el-button @click="exportEvents" :loading="exporting">
          <el-icon>
            <Download />
          </el-icon>
          导出事件
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-cards">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#409EFF">
                <Bell />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.summary.total_events || 0 }}</div>
              <div class="stat-label">总事件数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#67C23A">
                <Timer />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.summary.today_events || 0 }}</div>
              <div class="stat-label">今日事件</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#E6A23C">
                <Warning />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.alarm_smart_events.total.alarm || 0 }}</div>
              <div class="stat-label">报警事件</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#F56C6C">
                <DataAnalysis />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.alarm_smart_events.total.smart || 0 }}</div>
              <div class="stat-label">智能事件</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 过滤器 -->
    <el-card class="filter-card">
      <div class="filters">
        <el-select v-model="filters.scheme_id" placeholder="选择事件订阅" clearable style="width: 200px" @change="loadData" filterable>
          <el-option v-for="scheme in schemes" :key="scheme.id"
            :label="`${scheme.camera_name} (${scheme.event_types.join(', ')})`" :value="scheme.id" />
        </el-select>

        <el-select v-model="filters.event_type" placeholder="事件类型" clearable style="width: 150px" @change="loadData">
          <el-option label="报警事件" value="alarm" />
          <el-option label="智能事件" value="smart" />
          <el-option label="人数统计" value="number_stat" />
          <el-option label="设备日志" value="system_log" />
        </el-select>

        <el-select v-model="filters.status" placeholder="处理状态" clearable style="width: 120px" @change="loadData">
          <el-option label="未处理" value="pending" />
          <el-option label="已处理" value="processed" />
          <el-option label="已忽略" value="ignored" />
        </el-select>

        <el-date-picker v-model="dateRange" type="datetimerange" range-separator="至" start-placeholder="开始时间"
          end-placeholder="结束时间" format="YYYY-MM-DD HH:mm:ss" value-format="YYYY-MM-DD HH:mm:ss" style="width: 350px"
          @change="handleDateChange" />

        <el-input v-model="searchText" placeholder="搜索事件内容" style="width: 200px" @keyup.enter="loadData">
          <template #append>
            <el-button @click="loadData">
              <el-icon>
                <Search />
              </el-icon>
            </el-button>
          </template>
        </el-input>

        <el-button @click="clearFilters">清除筛选</el-button>
      </div>
    </el-card>

    <!-- 事件列表 -->
    <el-card class="events-list-card">
      <template #header>
        <div class="card-header">
          <span>事件列表</span>
          <div class="header-actions">
            <el-button size="small" @click="batchProcess" :disabled="selectedEvents.length === 0">
              批量处理
            </el-button>
            <el-button size="small" @click="batchIgnore" :disabled="selectedEvents.length === 0">
              批量忽略
            </el-button>
            <el-button size="small" @click="batchDelete" :disabled="selectedEvents.length === 0" type="danger">
              批量删除
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="events" v-loading="loading" @selection-change="handleSelectionChange" style="width: 100%">
        <el-table-column type="selection" width="55" />

        <el-table-column prop="event_type" label="事件类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getEventTypeTagType(row.event_type)">
              {{ getEventTypeText(row.event_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- <el-table-column prop="scheme_name" label="事件订阅" min-width="150" /> -->

        <el-table-column prop="camera_name" label="摄像机" width="120" sortable>
          <template #default="{ row }">
            <div class="camera-info">
              <span>{{ row.camera_name }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="camera_ip" label="摄像机IP" width="125" sortable></el-table-column>

        <el-table-column prop="title" label="事件标题" min-width="150">
          <template #default="{ row }">
            <div class="event-title">
              <span class="title">{{ row.title }}</span>
              <el-tag v-if="row.priority === 'high'" size="small" type="danger">高优先级</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="事件描述" min-width="200" show-overflow-tooltip />

        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="timestamp" label="发生时间" width="180" sortable>
          <template #default="{ row }">
            {{ formatDateTime(row.timestamp) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" type="info" @click="viewEvent(row)">查看</el-button>
              <el-button size="small" type="primary" @click="processEvent(row)"
                v-if="row.status === 'pending'">处理</el-button>
              <el-button size="small" type="warning" @click="ignoreEvent(row)"
                v-if="row.status === 'pending'">忽略</el-button>
              <el-button size="small" type="danger" @click="deleteEvent(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]" :total="pagination.total" layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange" @current-change="handleCurrentChange" />
      </div>
    </el-card>

    <!-- 事件详情对话框 -->
    <SmartEventDetailDialog v-model="detailDialogVisible" :event="currentEvent" />

    <!-- 处理事件对话框 -->
    <SmartEventProcessDialog v-model="processDialogVisible" :event="currentEvent" @success="handleProcessSuccess" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  Download,
  Search,
  Bell,
  Timer,
  Warning,
  DataAnalysis
} from '@element-plus/icons-vue'
import smartSchemeApi from '@/api/smart_scheme'
import SmartEventDetailDialog from './components/SmartEventDetailDialog.vue'
import SmartEventProcessDialog from './components/SmartEventProcessDialog.vue'

// 路由实例
const route = useRoute()

// 响应式数据
const loading = ref(false)
const exporting = ref(false)
const searchText = ref('')
const dateRange = ref([])
const events = ref([])
const schemes = ref([])
const selectedEvents = ref([])
const detailDialogVisible = ref(false)
const processDialogVisible = ref(false)
const currentEvent = ref(null)

const stats = reactive({
  alarm_smart_events: {
    total: {
      alarm: 0,
      smart: 0
    },
    today: {
      alarm: 0,
      smart: 0
    }
  },
  summary: {
    total_events: 0,
    today_events: 0
  }
})

const filters = reactive({
  scheme_id: null,
  event_type: null,
  status: null,
  start_date: null,
  end_date: null
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 计算属性
const searchParams = computed(() => {
  const params = {
    page: pagination.page,
    page_size: pagination.pageSize,
    ...filters
  }

  if (searchText.value) {
    params.search = searchText.value
  }

  return params
})

// 方法
const loadData = async () => {
  loading.value = true
  try {
    const [eventsRes, schemesRes] = await Promise.all([
      smartSchemeApi.getSmartEvents(searchParams.value),
      smartSchemeApi.getSchemes({ page: 1, page_size: 100 })
    ])

    events.value = eventsRes.data.items || []
    pagination.total = eventsRes.data.total || 0
    schemes.value = schemesRes.data.items || []
  } catch (error) {
 
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const loadOverviewData = async () => {
  const res = await smartSchemeApi.getEventsStatsOverview()
  Object.assign(stats, res.data)
}

const refreshData = () => {
  loadData()
  loadOverviewData()
}

const clearFilters = () => {
  Object.keys(filters).forEach(key => {
    filters[key] = null
  })
  searchText.value = ''
  dateRange.value = []
  pagination.page = 1
  loadData()
}

const handleDateChange = (dates) => {
  if (dates && dates.length === 2) {
    filters.start_date = dates[0]
    filters.end_date = dates[1]
  } else {
    filters.start_date = null
    filters.end_date = null
  }
  loadData()
}

const viewEvent = (event) => {
  currentEvent.value = { ...event }
  detailDialogVisible.value = true
}

const processEvent = (event) => {
  currentEvent.value = { ...event }
  processDialogVisible.value = true
}

const ignoreEvent = async (event) => {
  try {
    await ElMessageBox.confirm(
      `确定要忽略事件 "${event.title}" 吗？`,
      '确认忽略',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await smartSchemeApi.updateSmartEvent(event.id, { status: 'ignored' })
    ElMessage.success('事件已忽略')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('忽略失败:', error)
      ElMessage.error('忽略失败')
    }
  }
}

const deleteEvent = async (event) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除事件 "${event.title}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await smartSchemeApi.deleteSmartEvent(event.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

const handleSelectionChange = (selection) => {
  selectedEvents.value = selection
}

const batchProcess = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要批量处理选中的 ${selectedEvents.value.length} 个事件吗？`,
      '确认批量处理',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const eventIds = selectedEvents.value.map(e => e.id)
    await smartSchemeApi.batchProcessSmartEvents(eventIds)
    ElMessage.success('批量处理成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量处理失败:', error)
      ElMessage.error('批量处理失败')
    }
  }
}

const batchIgnore = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要批量忽略选中的 ${selectedEvents.value.length} 个事件吗？`,
      '确认批量忽略',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const eventIds = selectedEvents.value.map(e => e.id)
    await smartSchemeApi.batchIgnoreSmartEvents(eventIds)
    ElMessage.success('批量忽略成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量忽略失败:', error)
      ElMessage.error('批量忽略失败')
    }
  }
}

const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedEvents.value.length} 个事件吗？`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const eventIds = selectedEvents.value.map(e => e.id)
    await smartSchemeApi.batchDeleteSmartEvents(eventIds)
    ElMessage.success('批量删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量删除失败:', error)
      ElMessage.error('批量删除失败')
    }
  }
}

const exportEvents = async () => {
  try {
    exporting.value = true
    const response = await smartSchemeApi.exportEvents(searchParams.value)

    // 创建下载链接
    const blob = new Blob([response.data], { type: 'application/vnd.ms-excel' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `智能事件_${new Date().toISOString().split('T')[0]}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    ElMessage.success('导出成功')
  } catch (error) {
    console.error('导出失败:', error)
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const handleProcessSuccess = () => {
  processDialogVisible.value = false
  loadData()
}

const handleSizeChange = (size) => {
  pagination.pageSize = size
  pagination.page = 1
  loadData()
}

const handleCurrentChange = (page) => {
  pagination.page = page
  loadData()
}

// 工具方法
const getEventTypeTagType = (type) => {
  const types = {
    alarm: 'danger',
    smart: 'primary',
    number_stat: 'success',
    system_log: 'info'
  }
  return types[type] || 'info'
}

const getEventTypeText = (type) => {
  const texts = {
    alarm: '报警事件',
    smart: '智能事件',
    number_stat: '人数统计',
    system_log: '设备日志'
  }
  return texts[type] || type
}

const getStatusTagType = (status) => {
  const types = {
    pending: 'warning',
    processed: 'success',
    ignored: 'info'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    pending: '未处理',
    processed: '已处理',
    ignored: '已忽略'
  }
  return texts[status] || '未知'
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  return new Date(dateTime).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  // 检查路由查询参数，如果有 scheme_id 则自动筛选
  if (route.query.scheme_id) {
    filters.scheme_id = route.query.scheme_id
  }
  loadData()
  loadOverviewData()
})
</script>

<style scoped>
.smart-events {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}


.header-actions {
  display: flex;
  gap: 12px;
}

.stats-cards {
  margin-bottom: 20px;
}

.stat-content {
  display: flex;
  align-items: center;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.stat-icon {
  margin-right: 16px;
  font-size: 24px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  line-height: 1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
}

.filter-card {
  margin-bottom: 20px;
}

.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.events-list-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.event-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-title .title {
  font-weight: 500;
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>