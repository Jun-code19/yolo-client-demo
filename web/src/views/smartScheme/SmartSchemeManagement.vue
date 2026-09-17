<template>
  <div class="smart-scheme-management">
    <div class="page-header">
      <div class="header-content">
        <h2>事件订阅管理</h2>
        <p>管理监听摄像头主动上报的不同类型数据事件订阅配置</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshData" :loading="loading">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="showCreateDialog">
          <el-icon>
            <Plus />
          </el-icon>
          新建事件订阅
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
                <Monitor />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.schemes?.total || 0 }}</div>
              <div class="stat-label">总订阅数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#67C23A">
                <VideoPlay />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.schemes?.running || 0 }}</div>
              <div class="stat-label">运行中</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#E6A23C">
                <Bell />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.events?.today || 0 }}</div>
              <div class="stat-label">今日事件</div>
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
              <div class="stat-value">{{ stats.events?.total || 0 }}</div>
              <div class="stat-label">总事件数</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 过滤器 -->
    <el-card class="filter-card">
      <div class="filters">
        <el-select v-model="filters.camera_id" placeholder="选择摄像头" clearable filterable style="width: 200px" @change="loadData">
          <el-option v-for="camera in cameras" :key="camera.id" :label="camera.name" :value="camera.id" />
        </el-select>

        <el-select v-model="filters.event_type" placeholder="事件类型" clearable style="width: 150px" @change="loadData">
          <el-option label="报警事件" value="alarm" />
          <el-option label="智能事件" value="smart" />
          <el-option label="人数统计" value="number_stat" />
          <el-option label="设备日志" value="system_log" />
        </el-select>

        <el-select v-model="filters.status" placeholder="运行状态" clearable style="width: 120px" @change="loadData">
          <el-option label="运行中" value="running" />
          <el-option label="已停止" value="stopped" />
          <el-option label="错误" value="error" />
        </el-select>

        <el-input v-model="searchText" placeholder="搜索摄像头名称" style="width: 200px" @keyup.enter="loadData">
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

    <!-- 方案列表 -->
    <el-card class="scheme-list-card">
      <template #header>
        <div class="card-header">
          <span>事件订阅列表</span>
          <div class="header-actions">
            <!-- <el-button size="small" @click="batchStart" :disabled="selectedSchemes.length === 0">
              批量启动
            </el-button>
            <el-button size="small" @click="batchStop" :disabled="selectedSchemes.length === 0">
              批量停止
            </el-button> -->
            <el-button size="small" @click="batchDelete" :disabled="selectedSchemes.length === 0" type="danger">
              批量删除
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="schemes" v-loading="loading" @selection-change="handleSelectionChange" style="width: 100%">
        <el-table-column type="selection" width="55" />

        <el-table-column prop="camera_name" label="摄像机" width="150" sortable>
          <template #default="{ row }">
            <div class="camera-name">
              <span class="name">{{ row.camera_name }}</span>
              <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="camera_ip" label="摄像机IP" width="150" sortable>
          <template #default="{ row }">
            <span class="camera-ip">{{ row.camera_ip || '未知' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="camera_port" label="监听端口" min-width="50">
          <template #default="{ row }">
            <span class="camera-port">{{ row.camera_port || 37777 }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="event_types" label="订阅事件类型" min-width="150">
          <template #default="{ row }">
            <div class="event-types">
              <el-tag v-for="type in row.event_types" :key="type" :type="getEventTypeTagType(type)" size="small"
                style="margin-right: 4px; margin-bottom: 4px;">
                {{ getEventTypeText(type) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="push_tags" label="标签" min-width="140">
          <template #default="{ row }">
            <div class="push-tags">
              <el-tag
                v-for="tag in getPushTags(row.push_tags)"
                :key="tag"
                type="info"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ tag }}
              </el-tag>
              <span v-if="!getPushTags(row.push_tags).length" class="no-tags">-</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="event_count" label="事件数" width="150" sortable>
          <template #default="{ row }">
            <span class="event-count">{{ row.event_count || 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="200" sortable>
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" type="info" @click="viewScheme(row)">查看</el-button>
              <el-button size="small" type="primary" @click="editScheme(row)">编辑</el-button>
              <el-button size="small" :type="row.status === 'running' ? 'warning' : 'success'"
                @click="toggleScheme(row)">
                {{ row.status === 'running' ? '停止' : '启动' }}
              </el-button>
              <el-button size="small" type="danger" @click="deleteScheme(row)">删除</el-button>
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

    <!-- 创建/编辑对话框 -->
    <SmartSchemeDialog v-model="dialogVisible" :scheme="currentScheme" :cameras="cameras"
      @success="handleDialogSuccess" />

    <!-- 方案详情对话框 -->
    <SmartSchemeDetailDialog v-model="detailDialogVisible" :scheme="currentScheme" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  Plus,
  Search,
  Monitor,
  VideoPlay,
  Bell,
  DataAnalysis
} from '@element-plus/icons-vue'
import smartSchemeApi from '@/api/smart_scheme'
import SmartSchemeDialog from './components/SmartSchemeDialog.vue'
import SmartSchemeDetailDialog from './components/SmartSchemeDetailDialog.vue'

// 响应式数据
const loading = ref(false)
const searchText = ref('')
const schemes = ref([])
const cameras = ref([])

const selectedSchemes = ref([])
const dialogVisible = ref(false)
const detailDialogVisible = ref(false)
const currentScheme = ref(null)

const stats = reactive({
  schemes: {},
  events: {}
})

const filters = reactive({
  camera_id: null,
  event_type: null,
  status: null
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
    const [schemesRes, statsRes, camerasRes] = await Promise.all([
      smartSchemeApi.getSchemes(searchParams.value),
      smartSchemeApi.getStats(),
      smartSchemeApi.getCameras()
    ])

    schemes.value = schemesRes.data.items || []
    pagination.total = schemesRes.data.total || 0

    Object.assign(stats, statsRes.data)
    cameras.value = camerasRes.data || []
  } catch (error) {
    console.error('加载数据失败:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const refreshData = () => {
  loadData()
}

const clearFilters = () => {
  Object.keys(filters).forEach(key => {
    filters[key] = null
  })
  searchText.value = ''
  pagination.page = 1
  loadData()
}

const showCreateDialog = () => {
  currentScheme.value = null
  dialogVisible.value = true
}

const editScheme = (scheme) => {
  currentScheme.value = { ...scheme }
  dialogVisible.value = true
}

const viewScheme = (scheme) => {
  currentScheme.value = { ...scheme }
  detailDialogVisible.value = true
}

const toggleScheme = async (scheme) => {
  try {
    if (scheme.status === 'running') {
      await smartSchemeApi.stopScheme(scheme.id)
      ElMessage.success('方案已停止')
    } else {
      await smartSchemeApi.startScheme(scheme.id)
      ElMessage.success('方案已启动')
    }
    loadData()
  } catch (error) {
    console.error('操作失败:', error)
    ElMessage.error('操作失败')
  }
}

const deleteScheme = async (scheme) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除智能方案 "${scheme.name}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await smartSchemeApi.deleteScheme(scheme.id)
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
  selectedSchemes.value = selection
}

const batchStart = async () => {
  try {
    const schemeIds = selectedSchemes.value.map(s => s.id)
    await smartSchemeApi.batchStart(schemeIds)
    ElMessage.success('批量启动成功')
    loadData()
  } catch (error) {
    console.error('批量启动失败:', error)
    ElMessage.error('批量启动失败')
  }
}

const batchStop = async () => {
  try {
    const schemeIds = selectedSchemes.value.map(s => s.id)
    await smartSchemeApi.batchStop(schemeIds)
    ElMessage.success('批量停止成功')
    loadData()
  } catch (error) {
    console.error('批量停止失败:', error)
    ElMessage.error('批量停止失败')
  }
}

const batchDelete = async () => {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedSchemes.value.length} 个智能方案吗？`,
      '确认批量删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const schemeIds = selectedSchemes.value.map(s => s.id)
    await Promise.all(schemeIds.map(id => smartSchemeApi.deleteScheme(id)))
    ElMessage.success('批量删除成功')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量删除失败:', error)
      ElMessage.error('批量删除失败')
    }
  }
}

const handleDialogSuccess = () => {
  dialogVisible.value = false
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
const getStatusTagType = (status) => {
  const types = {
    running: 'success',
    stopped: 'info',
    error: 'danger'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    running: '运行中',
    stopped: '已停止',
    error: '错误'
  }
  return texts[status] || '未知'
}

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

const getPushTags = (pushTags) => {
  if (!pushTags || typeof pushTags !== 'string') return []
  return pushTags.split(',').map(tag => tag.trim()).filter(Boolean)
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return ''
  return new Date(dateTime).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  loadData()
})
</script>

<style scoped>
.smart-scheme-management {
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

.scheme-list-card {
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

.scheme-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.scheme-name .name {
  font-weight: 500;
}

.event-count {
  font-weight: 500;
  color: #409EFF;
}

.push-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.no-tags {
  color: #c0c4cc;
  font-size: 13px;
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style> 