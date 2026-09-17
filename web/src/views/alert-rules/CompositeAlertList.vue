<template>
  <div class="alert-page">
    <div class="card-header">
      <div class="header-content">
        <h2>命中记录</h2>
        <p>规则评估命中后的告警记录，包含匹配事件快照；可确认或忽略处理</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <el-card class="filter-card">
      <div class="filters">
        <el-select
          v-model="filters.rule_id"
          clearable
          filterable
          placeholder="按规则筛选"
          style="width: 220px"
          @change="loadData"
        >
          <el-option v-for="rule in ruleOptions" :key="rule.rule_id" :label="rule.name" :value="rule.rule_id" />
        </el-select>
        <el-select
          v-model="filters.device_id"
          clearable
          filterable
          placeholder="按设备筛选"
          style="width: 200px"
          @change="loadData"
        >
          <el-option
            v-for="device in devices"
            :key="device.device_id"
            :label="device.device_name || device.device_id"
            :value="device.device_id"
          />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="处理状态" style="width: 140px" @change="loadData">
          <el-option label="新建" value="new" />
          <el-option label="已确认" value="acknowledged" />
          <el-option label="已忽略" value="ignored" />
        </el-select>
        <el-button @click="clearFilters">清除筛选</el-button>
      </div>
    </el-card>

    <el-card class="table-card">
      <el-table :data="alerts" v-loading="loading" style="width: 100%">
        <el-table-column prop="title" label="告警标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="rule_name" label="关联规则" width="140" show-overflow-tooltip />
        <el-table-column label="涉及设备" min-width="160">
          <template #default="{ row }">
            <div v-if="formatInvolvedDevices(row, deviceMap).length" class="device-tags">
              <el-tag
                v-for="name in formatInvolvedDevices(row, deviceMap)"
                :key="`${row.alert_id}-${name}`"
                size="small"
                type="info"
                effect="plain"
                class="device-tag"
              >
                {{ name }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="匹配事件数" width="100" align="center">
          <template #default="{ row }">{{ row.matched_events?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="light">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="命中时间" width="170">
          <template #default="{ row }">{{ formatTime(row.fired_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right" align="center">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" @click="openDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'new'"
                size="small"
                type="success"
                @click="updateStatus(row, 'acknowledged')"
              >
                确认
              </el-button>
              <el-button
                v-if="row.status !== 'ignored'"
                size="small"
                type="info"
                @click="updateStatus(row, 'ignored')"
              >
                忽略
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination" v-if="total > filters.limit">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="filters.limit"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, prev, pager, next, sizes"
          @current-change="loadData"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="drawerVisible"
      title="命中详情"
      width="560px"
      top="5vh"
      align-center
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      :z-index="999999"
      class="high-priority-dialog alert-hit-detail-dialog"
    >
      <template v-if="currentAlert">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="标题">{{ currentAlert.title }}</el-descriptions-item>
          <el-descriptions-item label="规则">{{ currentAlert.rule_name || currentAlert.rule_id }}</el-descriptions-item>
          <el-descriptions-item label="涉及设备">
            <div v-if="formatInvolvedDevices(currentAlert, deviceMap).length" class="device-tags">
              <el-tag
                v-for="name in formatInvolvedDevices(currentAlert, deviceMap)"
                :key="name"
                size="small"
                type="info"
                effect="plain"
                class="device-tag"
              >
                {{ name }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="摘要">{{ currentAlert.summary || '-' }}</el-descriptions-item>
          <el-descriptions-item label="命中时间">{{ formatTime(currentAlert.fired_at) }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">匹配事件</h4>
        <el-collapse accordion>
          <el-collapse-item
            v-for="(evt, idx) in currentAlert.matched_events || []"
            :key="idx"
            :title="formatMatchedEventTitle(evt, deviceMap)"
            :name="idx"
          >
            <el-descriptions :column="1" border size="small" class="event-desc">
              <el-descriptions-item label="设备">
                {{ resolveEventDeviceName(evt) }}
              </el-descriptions-item>
              <el-descriptions-item label="时间">{{ formatTime(evt.timestamp) }}</el-descriptions-item>
              <el-descriptions-item label="标签">
                <span v-if="(evt.labels || []).length">{{ (evt.labels || []).join(' / ') }}</span>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="evt.event_type" label="类型">{{ evt.event_type }}</el-descriptions-item>
              <el-descriptions-item v-if="evt.payload?.job_id" label="巡检任务">{{ evt.payload.job_id }}</el-descriptions-item>
              <el-descriptions-item v-if="evt.payload?.summary" label="摘要">{{ evt.payload.summary }}</el-descriptions-item>
              <el-descriptions-item v-if="(evt.payload?.alert_labels || []).length" label="告警标签">
                {{ (evt.payload.alert_labels || []).join(' / ') }}
              </el-descriptions-item>
            </el-descriptions>
            <details class="raw-json">
              <summary>原始数据</summary>
              <pre class="json-block">{{ formatJson(evt) }}</pre>
            </details>
          </el-collapse-item>
        </el-collapse>

        <h4 class="section-title">规则快照</h4>
        <pre class="json-block">{{ formatJson(currentAlert.definition_snapshot) }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import alertRuleApi, {
  formatInvolvedDevices,
  formatMatchedEventTitle,
  normalizeListResponse
} from '@/api/alert_rule'
import deviceApi from '@/api/device'

const route = useRoute()
const loading = ref(false)
const alerts = ref([])
const ruleOptions = ref([])
const devices = ref([])
const total = ref(0)
const page = ref(1)
const drawerVisible = ref(false)
const currentAlert = ref(null)

const filters = ref({
  rule_id: '',
  device_id: '',
  status: '',
  limit: 50,
  offset: 0
})

const statusLabel = (status) => ({
  new: '新建',
  acknowledged: '已确认',
  ignored: '已忽略'
}[status] || status)

const statusTagType = (status) => ({
  new: 'danger',
  acknowledged: 'success',
  ignored: 'info'
}[status] || 'info')

const deviceMap = computed(() =>
  Object.fromEntries(
    devices.value.map(device => [device.device_id, device.device_name || device.device_id])
  )
)

const resolveEventDeviceName = (evt) => {
  if (!evt?.device_id) return '-'
  return deviceMap.value[evt.device_id] || evt.device_id
}

const formatTime = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

const formatJson = (value) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const loadRuleOptions = async () => {
  try {
    const res = await alertRuleApi.listRules()
    ruleOptions.value = res.data || []
  } catch {
    ruleOptions.value = []
  }
}

const loadDevices = async () => {
  try {
    const res = await deviceApi.getDevices({ skip: 0, limit: 500 })
    devices.value = normalizeListResponse(res.data)
  } catch {
    devices.value = []
  }
}

const loadData = async () => {
  loading.value = true
  filters.value.offset = (page.value - 1) * filters.value.limit
  try {
    const params = {
      limit: filters.value.limit,
      offset: filters.value.offset
    }
    if (filters.value.rule_id) params.rule_id = filters.value.rule_id
    if (filters.value.device_id) params.device_id = filters.value.device_id
    if (filters.value.status) params.status = filters.value.status

    const res = await alertRuleApi.listAlerts(params)
    alerts.value = res.data || []
    total.value = alerts.value.length >= filters.value.limit
      ? filters.value.offset + alerts.value.length + 1
      : filters.value.offset + alerts.value.length
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载命中记录失败')
  } finally {
    loading.value = false
  }
}

const clearFilters = () => {
  filters.value.rule_id = ''
  filters.value.device_id = ''
  filters.value.status = ''
  page.value = 1
  loadData()
}

const handleSizeChange = () => {
  page.value = 1
  loadData()
}

const openDetail = (row) => {
  currentAlert.value = row
  drawerVisible.value = true
}

const updateStatus = async (row, status) => {
  try {
    await alertRuleApi.updateAlertStatus(row.alert_id, status)
    ElMessage.success('状态已更新')
    loadData()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '更新失败')
  }
}

watch(
  () => route.query.rule_id,
  (ruleId) => {
    if (ruleId) {
      filters.value.rule_id = ruleId
      loadData()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await Promise.all([loadRuleOptions(), loadDevices()])
  if (route.query.rule_id) filters.value.rule_id = route.query.rule_id
  loadData()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}


.header-actions {
  flex-shrink: 0;
}

.filter-card {
  margin-bottom: 20px;
}

.table-card :deep(.el-table) {
  margin-top: 4px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.section-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.json-block {
  margin: 8px 0 0;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  overflow: auto;
  max-height: 280px;
}

.device-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.device-tag {
  margin: 0;
}

.event-desc {
  margin-bottom: 8px;
}

.raw-json summary {
  cursor: pointer;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>

<style>
.alert-hit-detail-dialog .el-dialog__body {
  max-height: min(72vh, calc(100vh - 180px));
  overflow-x: hidden;
  overflow-y: auto;
}
</style>
