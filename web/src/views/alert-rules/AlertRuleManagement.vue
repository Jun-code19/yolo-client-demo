<template>
  <div class="rule-page">
    <div class="card-header">
      <div class="header-content">
        <h2>规则列表</h2>
        <p>聚合检测事件与事件订阅，由检测服务每 {{ evalIntervalSec }}s 评估，命中后落库并推送</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button @click="handleEvaluate" :loading="evaluating">
          <el-icon><VideoPlay /></el-icon>
          立即评估
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建规则
        </el-button>
      </div>
    </div>

    <div class="stats-cards">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon"><el-icon color="#409EFF"><SetUp /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ rules.length }}</div>
              <div class="stat-label">规则总数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon"><el-icon color="#67C23A"><CircleCheck /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ enabledCount }}</div>
              <div class="stat-label">已启用</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon"><el-icon color="#E6A23C"><Bell /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ evalIntervalSec }}s</div>
              <div class="stat-label">评估间隔</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon"><el-icon color="#909399"><List /></el-icon></div>
            <div class="stat-info">
              <div class="stat-value">{{ sourceCount }}</div>
              <div class="stat-label">事件源类型</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <el-card class="filter-card">
      <div class="filters">
        <el-select v-model="filters.enabled" clearable placeholder="启用状态" style="width: 140px" @change="loadData">
          <el-option label="已启用" :value="true" />
          <el-option label="已禁用" :value="false" />
        </el-select>
        <el-select
          v-model="filters.device_id"
          clearable
          filterable
          placeholder="限定设备"
          style="width: 220px"
          @change="loadData"
        >
          <el-option
            v-for="device in devices"
            :key="device.device_id"
            :label="device.device_name || device.device_id"
            :value="device.device_id"
          />
        </el-select>
        <el-input
          v-model="searchText"
          placeholder="搜索规则名称"
          style="width: 220px"
          clearable
          @keyup.enter="applySearch"
        >
          <template #append>
            <el-button @click="applySearch">
              <el-icon><Search /></el-icon>
            </el-button>
          </template>
        </el-input>
        <el-button @click="clearFilters">清除筛选</el-button>
      </div>
    </el-card>

    <el-card class="table-card">
      <el-table :data="filteredRules" v-loading="loading" style="width: 100%">
        <el-table-column prop="name" label="规则名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="设备" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_name || row.device_id || '全部' }}</template>
        </el-table-column>
        <el-table-column label="组合逻辑" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.definition?.logic === 'OR' ? 'warning' : 'primary'" effect="plain">
              {{ row.definition?.logic || 'AND' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="push_tags" label="推送标签" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.push_tags || '-' }}</template>
        </el-table-column>
        <el-table-column label="触发条件" min-width="220">
          <template #default="{ row }">
            <template v-if="(row.definition?.conditions || []).length">
              <el-tooltip
                :content="formatConditionsFull(row.definition.conditions)"
                placement="top"
                :show-after="300"
                :disabled="!needsConditionsTooltip(row.definition.conditions)"
              >
                <div class="cond-tags">
                  <el-tag
                    v-for="(cond, idx) in visibleConditions(row.definition.conditions)"
                    :key="idx"
                    size="small"
                    type="info"
                    effect="plain"
                    class="cond-tag"
                  >
                    {{ formatConditionShort(cond) }}
                  </el-tag>
                  <el-tag
                    v-if="hiddenConditionCount(row.definition.conditions) > 0"
                    size="small"
                    type="info"
                    effect="plain"
                    class="cond-tag cond-tag-more"
                  >
                    +{{ hiddenConditionCount(row.definition.conditions) }}
                  </el-tag>
                </div>
              </el-tooltip>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column width="168" align="center">
          <template #header>
            <span>时间参数</span>
            <el-tooltip placement="top">
              <template #content>
                窗口 / 冷却（秒）；持续时间在各触发条件上单独配置
              </template>
              <el-icon class="header-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="time-params">
              {{ row.definition?.window_sec || 300 }} /
              {{ row.definition?.cooldown_sec || 60 }}s
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="light">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right" align="center">
          <template #default="{ row }">
            <el-button-group>
              <el-button
                size="small"
                :type="row.enabled ? 'warning' : 'success'"
                @click="toggleEnabled(row)"
              >
                {{ row.enabled ? '禁用' : '启用' }}
              </el-button>
              <el-button size="small" type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="confirmDelete(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <AlertRuleDialog ref="dialogRef" @saved="loadData" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh, Plus, Bell, SetUp, CircleCheck, List, VideoPlay, QuestionFilled, Search
} from '@element-plus/icons-vue'
import alertRuleApi, {
  formatConditionText,
  formatConditionsTooltip,
  normalizeListResponse
} from '@/api/alert_rule'
import deviceApi from '@/api/device'
import smartSchemeApi from '@/api/smart_scheme'
import AlertRuleDialog from './components/AlertRuleDialog.vue'

const loading = ref(false)
const evaluating = ref(false)
const rules = ref([])
const devices = ref([])
const smartSchemeMap = ref({})
const searchText = ref('')
const evalIntervalSec = ref(60)
const sourceCount = ref(2)
const dialogRef = ref(null)

const VISIBLE_CONDITION_COUNT = 2
const VISIBLE_CONDITION_LABEL_COUNT = 2
const conditionLookups = computed(() => ({
  smartSchemes: smartSchemeMap.value
}))

const filters = ref({
  enabled: null,
  device_id: ''
})

const enabledCount = computed(() => rules.value.filter(item => item.enabled).length)

const filteredRules = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return rules.value
  return rules.value.filter(item => (item.name || '').toLowerCase().includes(keyword))
})

const formatConditionFull = (cond) => formatConditionText(cond, conditionLookups.value)

const formatConditionShort = (cond) => formatConditionText(cond, conditionLookups.value, {
  maxLabels: VISIBLE_CONDITION_LABEL_COUNT
})

const formatConditionsFull = (conditions) => formatConditionsTooltip(conditions, conditionLookups.value)

const visibleConditions = (conditions) => (conditions || []).slice(0, VISIBLE_CONDITION_COUNT)

const hiddenConditionCount = (conditions) => Math.max(0, (conditions || []).length - VISIBLE_CONDITION_COUNT)

const isConditionTruncated = (cond) => {
  const full = formatConditionFull(cond)
  const short = formatConditionShort(cond)
  return full !== short || full.length > 36
}

const needsConditionsTooltip = (conditions) => {
  if (hiddenConditionCount(conditions) > 0) return true
  return (conditions || []).some(cond => isConditionTruncated(cond))
}

const loadReferenceMaps = async () => {
  try {
    const schemeRes = await Promise.allSettled([
      smartSchemeApi.getSchemes({ page: 1, page_size: 500 })
    ]).then(r => r[0])
    if (schemeRes.status === 'fulfilled') {
      const schemes = normalizeListResponse(schemeRes.value.data)
      smartSchemeMap.value = Object.fromEntries(
        schemes.map(scheme => [scheme.id, scheme.camera_name || scheme.id])
      )
    } else {
      smartSchemeMap.value = {}
    }
  } catch {
    smartSchemeMap.value = {}
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

const loadMeta = async () => {
  try {
    const res = await alertRuleApi.getMeta()
    evalIntervalSec.value = res.data?.eval_interval_sec || 60
    sourceCount.value = (res.data?.supported_sources || []).length || 2
  } catch {
    /* ignore */
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.enabled !== null && filters.value.enabled !== '') params.enabled = filters.value.enabled
    if (filters.value.device_id) params.device_id = filters.value.device_id
    const res = await alertRuleApi.listRules(params)
    rules.value = res.data || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载规则失败')
  } finally {
    loading.value = false
  }
}

const applySearch = () => {
  /* filteredRules 响应 searchText */
}

const clearFilters = () => {
  filters.value.enabled = null
  filters.value.device_id = ''
  searchText.value = ''
  loadData()
}

const openCreate = () => dialogRef.value?.openCreate()
const openEdit = (row) => dialogRef.value?.openEdit(row)

const toggleEnabled = async (row) => {
  try {
    await alertRuleApi.updateRule(row.rule_id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '已禁用' : '已启用')
    loadData()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '更新失败')
  }
}

const handleEvaluate = async () => {
  evaluating.value = true
  try {
    const res = await alertRuleApi.evaluate()
    const stats = res.data?.stats || {}
    ElMessage.success(
      `评估完成：命中 ${stats.fired || 0} 条，推送 ${stats.pushed || 0} 条，跳过冷却 ${stats.skipped_cooldown || 0} 条`
    )
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '评估失败（需管理员权限）')
  } finally {
    evaluating.value = false
  }
}

const confirmDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除规则「${row.name}」？`, '确认删除', { type: 'warning' })
    await alertRuleApi.deleteRule(row.rule_id)
    ElMessage.success('已删除')
    loadData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  }
}

onMounted(async () => {
  await Promise.all([loadDevices(), loadMeta(), loadReferenceMaps()])
  loadData()
})
</script>

<style scoped>
.rule-page {
  padding: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-content p {
  max-width: 640px;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.stats-cards {
  margin-bottom: 20px;
}

.stat-content {
  display: flex;
  align-items: center;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  font-size: 32px;
  margin-right: 16px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
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

.cond-tags {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  overflow: hidden;
  max-width: 100%;
  cursor: default;
}

.cond-tag {
  margin: 0;
  flex-shrink: 1;
  min-width: 0;
  max-width: 200px;
}

.cond-tag :deep(.el-tag__content) {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cond-tag-more {
  flex-shrink: 0;
  max-width: none;
}

.time-params {
  font-size: 13px;
  color: #606266;
}

.header-tip {
  margin-left: 4px;
  vertical-align: middle;
  color: #909399;
  cursor: help;
}
</style>
