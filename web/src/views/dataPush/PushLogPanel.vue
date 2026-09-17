<template>
  <div class="push-log-panel">
    <el-alert
      type="info"
      show-icon
      :closable="false"
      class="hint-alert"
      title="推送记录保存在数据库中；顶部「成功/失败」计数来自检测服务内存，重启检测服务后会清零。"
    />

    <el-card class="filter-card">
      <div class="filters">
        <el-select
          v-model="filters.push_id"
          placeholder="推送配置"
          clearable
          filterable
          style="width: 220px"
          @change="loadLogs"
        >
          <el-option
            v-for="item in pushOptions"
            :key="item.push_id"
            :label="item.push_name"
            :value="item.push_id"
          />
        </el-select>
        <el-select
          v-model="filters.status"
          placeholder="结果"
          clearable
          style="width: 120px"
          @change="loadLogs"
        >
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failure" />
        </el-select>
        <el-button :loading="loading" @click="loadLogs">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </el-card>

    <el-card>
      <el-table :data="logs" v-loading="loading" border style="width: 100%">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="push_name" label="推送名称" width="160" show-overflow-tooltip />
        <el-table-column prop="push_method" label="方式" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ (row.push_method || '').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_summary" label="目标" min-width="180" show-overflow-tooltip />
        <el-table-column prop="message" label="说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_test" size="small" type="info">测试</el-tag>
            <span v-else>业务</span>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="80">
          <template #default="{ row }">
            {{ row.duration_ms != null ? `${row.duration_ms}ms` : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadLogs"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <el-dialog
      v-model="detailVisible"
      title="推送记录详情"
      width="640px"
      top="5vh"
      align-center
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      :z-index="999999"
      class="high-priority-dialog push-log-detail-dialog"
    >
      <el-descriptions v-if="selectedLog" :column="1" border>
        <el-descriptions-item label="时间">{{ formatTime(selectedLog.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="推送">{{ selectedLog.push_name }} ({{ selectedLog.push_id }})</el-descriptions-item>
        <el-descriptions-item label="结果">
          <el-tag :type="selectedLog.status === 'success' ? 'success' : 'danger'" size="small">
            {{ selectedLog.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="目标">{{ selectedLog.target_summary || '-' }}</el-descriptions-item>
        <el-descriptions-item label="说明">{{ selectedLog.message || '-' }}</el-descriptions-item>
        <el-descriptions-item label="标签">
          <el-tag v-for="tag in selectedLog.tags || []" :key="tag" size="small" style="margin-right: 4px">{{ tag }}</el-tag>
          <span v-if="!(selectedLog.tags || []).length">-</span>
        </el-descriptions-item>
        <el-descriptions-item label="数据摘要">
          <pre class="payload-preview">{{ formatPreview(selectedLog.payload_preview) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { dataPushApi } from '@/api/data_push'

const props = defineProps({
  pushOptions: {
    type: Array,
    default: () => []
  }
})

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const detailVisible = ref(false)
const selectedLog = ref(null)

const filters = reactive({
  push_id: '',
  status: ''
})

const loadLogs = async () => {
  loading.value = true
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (filters.push_id) params.push_id = filters.push_id
    if (filters.status) params.status = filters.status

    const response = await dataPushApi.getPushLogs(params)
    logs.value = response.data?.data || []
    total.value = response.data?.total || 0
  } catch (error) {
    ElMessage.error('加载推送记录失败')
  } finally {
    loading.value = false
  }
}

const handleSizeChange = () => {
  currentPage.value = 1
  loadLogs()
}

const showDetail = (row) => {
  selectedLog.value = row
  detailVisible.value = true
}

const formatTime = (value) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

const formatPreview = (preview) => {
  if (!preview) return '-'
  try {
    return JSON.stringify(preview, null, 2)
  } catch {
    return String(preview)
  }
}

onMounted(loadLogs)

defineExpose({ loadLogs })
</script>

<style scoped>
.push-log-panel {
  padding: 0;
}

.hint-alert {
  margin-bottom: 16px;
}

.filter-card {
  margin-bottom: 16px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.payload-preview {
  margin: 0;
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

<style>
.push-log-detail-dialog .el-dialog__body {
  max-height: min(72vh, calc(100vh - 180px));
  overflow-x: hidden;
  overflow-y: auto;
}
</style>
