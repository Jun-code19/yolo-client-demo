<template>
  <div class="system-container">
    <div class="page-header">
      <!-- <h2>系统管理</h2> -->
      <el-tabs v-model="activeTab" class="system-tabs">
        <el-tab-pane label="系统状态" name="status"></el-tab-pane>
        <el-tab-pane label="系统日志" name="logs"></el-tab-pane>
        <el-tab-pane label="检测日志" name="detection_logs"></el-tab-pane>
        <el-tab-pane label="设备监控" name="device_monitor"></el-tab-pane>
      </el-tabs>
    </div>

    <!-- 系统状态面板 -->
    <div v-if="activeTab === 'status'" class="status-panel" v-loading="statusLoading">
      <div class="status-header">
        <span class="status-hint">每 5 秒自动刷新 · 当前时间以服务端为准</span>
        <el-button type="primary" @click="refreshStatus">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <el-card class="status-card info-card">
        <template #header>
          <div class="card-header">
            <span>盒子信息</span>
            <el-tag type="success" v-if="systemStatus.status === 'normal'">运行正常</el-tag>
            <el-tag type="warning" v-else-if="systemStatus.status === 'warning'">需要注意</el-tag>
            <el-tag type="danger" v-else>异常</el-tag>
          </div>
        </template>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="主机名">{{ systemInfo.hostname || '—' }}</el-descriptions-item>
          <el-descriptions-item label="应用版本">
            {{ systemInfo.app_name }} {{ systemInfo.app_version }}
          </el-descriptions-item>
          <el-descriptions-item label="推理后端">
            <el-tag size="small" type="info">{{ inferenceLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="当前时间">{{ systemInfo.current_time || '—' }}</el-descriptions-item>
          <el-descriptions-item label="开机时间">{{ systemInfo.boot_time || '—' }}</el-descriptions-item>
          <el-descriptions-item label="运行时长">{{ systemInfo.uptime_text || '—' }}</el-descriptions-item>
          <el-descriptions-item label="系统">{{ systemInfo.platform || '—' }}</el-descriptions-item>
          <el-descriptions-item label="架构">{{ systemInfo.architecture || '—' }}</el-descriptions-item>
          <el-descriptions-item label="Python">{{ systemInfo.python_version || '—' }}</el-descriptions-item>
          <el-descriptions-item label="已启用检测任务" :span="3">
            {{ detectionInfo.enabled_configs }} 个
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="status-card">
        <template #header>
          <div class="card-header">
            <span>系统资源</span>
          </div>
        </template>
        <el-row :gutter="16" class="resource-grid">
          <el-col :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>CPU</span>
                <span>{{ systemStatus.cpu.percent }}%</span>
              </div>
              <el-progress :percentage="systemStatus.cpu.percent" :status="getCpuStatus(systemStatus.cpu.percent)" />
              <div class="item-footer">
                <span>逻辑核: {{ systemStatus.cpu.total }}</span>
                <span>约占用: {{ systemStatus.cpu.used }} 核</span>
              </div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>内存</span>
                <span>{{ systemStatus.memory.percent }}%</span>
              </div>
              <el-progress :percentage="systemStatus.memory.percent" :status="getMemoryStatus(systemStatus.memory.percent)" />
              <div class="item-footer">
                <span>总计: {{ systemStatus.memory.total }} GB</span>
                <span>已用: {{ systemStatus.memory.used }} GB</span>
              </div>
            </div>
          </el-col>
          <el-col v-if="showNpu" :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>NPU</span>
                <span v-if="npuInfo.load_percent != null">{{ npuInfo.load_percent }}%</span>
                <span v-else class="npu-idle">{{ npuInfo.status_text }}</span>
              </div>
              <el-progress
                v-if="npuInfo.load_percent != null"
                :percentage="npuInfo.load_percent"
                :status="getNpuStatus(npuInfo.load_percent)"
              />
              <el-progress v-else :percentage="0" :show-text="false" />
              <div class="item-footer npu-footer">
                <span>驱动: {{ npuInfo.driver_version || '—' }}</span>
                <span v-if="npuInfo.load_readable">{{ npuInfo.load_readable }}</span>
                <span v-else>{{ npuInfo.status_text }}</span>
              </div>
            </div>
          </el-col>
          <el-col v-if="showGpu" :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>GPU</span>
                <span>{{ systemStatus.gpu.percent }}%</span>
              </div>
              <el-progress :percentage="systemStatus.gpu.percent" :status="getGpuStatus(systemStatus.gpu.percent)" />
              <div class="item-footer">
                <span>显存: {{ systemStatus.gpu.total }} GB</span>
                <span>已用: {{ systemStatus.gpu.used }} GB</span>
              </div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>系统盘</span>
                <span>{{ systemStatus.disk.percent }}%</span>
              </div>
              <el-progress :percentage="systemStatus.disk.percent" :status="getDiskStatus(systemStatus.disk.percent)" />
              <div class="item-footer">
                <span>{{ systemStatus.disk.path || '/' }}</span>
                <span>{{ systemStatus.disk.used }} / {{ systemStatus.disk.total }} GB</span>
              </div>
            </div>
          </el-col>
          <el-col :xs="24" :sm="12" :lg="8">
            <div class="resource-item">
              <div class="item-header">
                <span>应用目录</span>
                <span>{{ dataStorage.percent }}%</span>
              </div>
              <el-progress :percentage="dataStorage.percent" :status="getDiskStatus(dataStorage.percent)" />
              <div class="item-footer">
                <span>{{ dataStorage.path || 'backend' }}</span>
                <span>{{ dataStorage.used }} / {{ dataStorage.total }} GB</span>
              </div>
            </div>
          </el-col>
        </el-row>
      </el-card>
    </div>

    <!-- 系统日志面板 -->
    <div v-if="activeTab === 'logs'">
      <div class="logs-panel">
        <!-- 筛选条件 -->
        <el-card class="filter-card">
          <el-form :inline="true" :model="logFilters" class="filter-form">
            <el-form-item label="时间范围">
              <el-date-picker v-model="logFilters.dateRange" type="daterange" range-separator="至"
                start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" />
            </el-form-item>
            <el-form-item label="操作类型">
              <el-select v-model="logFilters.actionType" placeholder="请选择操作类型" clearable
                style="width: 180px; margin-right: 10px">
                <el-option-group v-for="(group, key) in actionTypes" :key="key" :label="group.label">
                  <el-option v-for="(label, value) in group.options" :key="value" :label="label" :value="value">
                    <div class="model-option">
                      <span class="model-name">{{ label }}</span>
                      <span class="model-desc">{{ value }}</span>
                    </div>
                  </el-option>
                </el-option-group>
              </el-select>
              <el-input v-model="logFilters.actionType" placeholder="请输入自定义操作类型" style="width: 180px; margin-right: 10px"></el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="resetFilter">重置</el-button>
            </el-form-item>
            <el-form-item class="action-buttons">
              <el-button type="primary" @click="handleExport">
                <el-icon>
                  <Download />
                </el-icon>导出日志
              </el-button>
              <el-button type="danger" @click="handleClear">
                <el-icon>
                  <Delete />
                </el-icon>清除日志
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 日志列表 -->
        <el-card class="log-list">
          <el-table :data="sysLogs" style="width: 100%" v-loading="logsLoading">
            <!-- <el-table-column prop="log_id" label="日志ID" width="80" /> -->
            <el-table-column prop="user_id" label="用户ID" min-width="120" />
            <el-table-column prop="action_type" label="操作类型" min-width="120">
              <template #default="{ row }">
                <el-tag :type="getActionTypeTag(row.action_type)">
                  {{ getActionTypeText(row.action_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="target_id" label="目标ID" min-width="120" />
            <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
            <el-table-column prop="log_time" label="操作时间" min-width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.log_time) }}
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination">
            <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :total="total"
              :page-sizes="[10, 20, 50, 100]" layout="prev, pager, next, jumper, ->, total, sizes"
              @size-change="handleSizeChange" @current-change="handleCurrentChange" />
          </div>
        </el-card>
      </div>
    </div>

    <!-- 检测日志面板 -->
    <div v-if="activeTab === 'detection_logs'">
      <div class="logs-panel">
        <!-- 筛选条件 -->
        <el-card class="filter-card">
          <el-form :inline="true" class="filter-form">
            <el-form-item label="时间范围">
              <el-date-picker v-model="detectionLogFilters.dateRange" type="daterange" range-separator="至"
                start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD" />
            </el-form-item>
            <el-form-item label="操作类型">
              <el-select v-model="detectionLogFilters.operation" placeholder="请选择操作类型" clearable
                style="width: 180px; margin-right: 10px">
                <el-option label="启动" value="start"></el-option>
                <el-option label="停止" value="stop"></el-option>
                <el-option label="自动启动" value="auto_start"></el-option>
                <el-option label="自动停止" value="auto_stop"></el-option>
                <el-option label="定时设置" value="schedule"></el-option>
                <el-option label="取消定时" value="unschedule"></el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="detectionLogFilters.status" placeholder="请选择状态" clearable
                style="width: 120px; margin-right: 10px">
                <el-option label="成功" value="success"></el-option>
                <el-option label="失败" value="failed"></el-option>
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleDetectionLogSearch">查询</el-button>
              <el-button @click="resetDetectionLogFilter">重置</el-button>
            </el-form-item>
            <el-form-item class="action-buttons">
              <el-button type="primary" @click="handleExportDetectionLogs">
                <el-icon>
                  <Download />
                </el-icon>导出日志
              </el-button>
              <el-button type="danger" @click="handleClearDetectionLogs">
                <el-icon>
                  <Delete />
                </el-icon>清除日志
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 日志列表 -->
        <el-card class="log-list">
          <el-table :data="detectionLogs" style="width: 100%" v-loading="detectionLogsLoading">
            <el-table-column prop="device_name" label="设备名称" min-width="120" />
            <el-table-column prop="config_name" label="检测配置" min-width="120" />
            <el-table-column prop="operation" label="操作类型" min-width="100">
              <template #default="{ row }">
                <el-tag :type="getOperationTypeTag(row.operation)">
                  {{ getOperationTypeText(row.operation) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'">
                  {{ row.status === 'success' ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="详情" min-width="200" show-overflow-tooltip />
            <el-table-column prop="username" label="执行用户" min-width="100" />
            <el-table-column prop="created_at" label="操作时间" min-width="180">
              <template #default="{ row }">
                {{ formatDateTime(row.created_at) }}
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination">
            <el-pagination v-model:current-page="detectionLogCurrentPage" v-model:page-size="detectionLogPageSize"
              :total="detectionLogTotal" :page-sizes="[10, 20, 50, 100]"
              layout="prev, pager, next, jumper, ->, total, sizes" @size-change="handleDetectionLogSizeChange"
              @current-change="handleDetectionLogCurrentChange" />
          </div>
        </el-card>
      </div>
    </div>

    <!-- 设备监控配置 -->
    <div v-if="activeTab === 'device_monitor'" class="integrations-panel">
      <el-card>
        <template #header>
          <div class="card-header">
            <div>
              <div class="panel-title">设备在线监控</div>
              <div class="panel-desc">配置 RTSP/TCP/HTTP 探活策略；NVR 通道建议优先 RTSP</div>
            </div>
          </div>
        </template>
        <DeviceMonitorConfig />
      </el-card>
    </div>

    <!-- 清除日志对话框 -->
    <el-dialog v-model="clearDialogVisible" title="清除系统日志" width="400px">
      <el-form :model="clearForm" label-width="120px">
        <el-form-item label="清除天数">
          <el-input-number v-model="clearForm.days" :min="1" :max="365" :step="1" step-strictly />
        </el-form-item>
        <el-form-item>
          <span class="warning-text">注意：此操作将永久删除指定天数前的所有日志记录，且不可恢复！</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="clearDialogVisible = false">取消</el-button>
          <el-button type="danger" @click="confirmClear" :loading="clearing">
            确认清除
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 清除检测日志对话框 -->
    <el-dialog v-model="clearDetectionLogDialogVisible" title="清除检测日志" width="400px">
      <el-form :model="clearDetectionLogForm" label-width="120px">
        <el-form-item label="清除天数">
          <el-input-number v-model="clearDetectionLogForm.days" :min="1" :max="365" :step="1" step-strictly />
        </el-form-item>
        <el-form-item>
          <span class="warning-text">注意：此操作将永久删除指定天数前的所有检测日志记录，且不可恢复！</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="clearDetectionLogDialogVisible = false">取消</el-button>
          <el-button type="danger" @click="confirmClearDetectionLog" :loading="clearingDetectionLog">
            确认清除
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh, Download, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import systemLogApi from '@/api/system_log'
import DeviceMonitorConfig from '@/components/DeviceMonitorConfig.vue'

const route = useRoute()

// 选项卡控制
const activeTab = ref('status')

const syncTabFromRoute = () => {
  const tab = route.query.tab
  if (tab === 'map_config' || tab === 'integrations') {
    activeTab.value = 'status'
  } else if (tab === 'device_monitor') {
    activeTab.value = 'device_monitor'
  }
}

watch(() => route.query.tab, syncTabFromRoute)

const defaultDisk = () => ({ path: '', percent: 0, total: 0, used: 0, free: 0 })

// 系统状态数据
const statusLoading = ref(false)
const systemStatus = ref({
  status: 'normal',
  cpu: { percent: 0, total: 0, used: 0 },
  memory: { percent: 0, total: 0, used: 0 },
  gpu: { percent: 0, total: 0, used: 0 },
  disk: defaultDisk()
})
const systemInfo = ref({
  hostname: '',
  platform: '',
  architecture: '',
  python_version: '',
  app_name: 'edge-ai-box',
  app_version: '',
  edge_inference: '',
  current_time: '',
  boot_time: '',
  uptime_text: ''
})
const npuInfo = ref({
  available: false,
  backend: '',
  driver_version: '',
  load_percent: null,
  load_readable: '',
  load_error: '',
  status_text: ''
})
const dataStorage = ref(defaultDisk())
const detectionInfo = ref({ enabled_configs: 0 })

const inferenceLabel = computed(() => {
  const b = (systemInfo.value.edge_inference || '').toLowerCase()
  if (b === 'rknn') return 'RKNN（NPU）'
  if (b === 'ultralytics') return 'Ultralytics（GPU/CPU）'
  if (b === 'onnx') return 'ONNX（CPU）'
  return b || '—'
})

const showNpu = computed(() => {
  const b = (systemInfo.value.edge_inference || '').toLowerCase()
  return b === 'rknn' || npuInfo.value.available
})

const showGpu = computed(() => {
  const g = systemStatus.value.gpu
  return (g.total || 0) > 0 || (g.percent || 0) > 0
})

// 检测日志
const detectionLogs = ref([])

// 刷新状态
const refreshStatus = async (silent = false) => {
  if (!silent) {
    statusLoading.value = true
  }
  try {
    const response = await systemLogApi.getSystemStatus()

    if (response.status === 200) {
      const d = response.data
      systemStatus.value = {
        status: d.status || 'normal',
        cpu: d.cpu || systemStatus.value.cpu,
        memory: d.memory || systemStatus.value.memory,
        gpu: d.gpu || systemStatus.value.gpu,
        disk: d.disk || defaultDisk()
      }
      if (d.system) {
        systemInfo.value = { ...systemInfo.value, ...d.system }
      }
      if (d.npu) {
        npuInfo.value = { ...npuInfo.value, ...d.npu }
      }
      if (d.data_storage) {
        dataStorage.value = d.data_storage
      }
      if (d.detection) {
        detectionInfo.value = d.detection
      }
    }
  } catch (error) {
    const detail = error.response?.data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : (detail ? JSON.stringify(detail) : error.message)
    ElMessage.error(msg ? `获取系统状态失败：${msg}` : '获取系统状态失败，请检查服务是否已启动')
  } finally {
    if (!silent) {
      statusLoading.value = false
    }
  }
}

// 资源状态判断
const getCpuStatus = (value) => value > 90 ? 'exception' : value > 70 ? 'warning' : 'success'
const getMemoryStatus = (value) => value > 90 ? 'exception' : value > 80 ? 'warning' : 'success'
const getGpuStatus = (value) => value > 90 ? 'exception' : value > 70 ? 'warning' : 'success'
const getDiskStatus = (value) => value > 90 ? 'exception' : value > 80 ? 'warning' : 'success'
const getNpuStatus = (value) => value > 90 ? 'exception' : value > 70 ? 'warning' : 'success'

// 定时刷新
let refreshInterval

// =========================
// 系统日志部分（从SystemLogs.vue集成）
// =========================

// 日志数据
const logsLoading = ref(false)
const sysLogs = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const clearDialogVisible = ref(false)
const clearing = ref(false)
const clearForm = reactive({
  days: 30
})

// 日志筛选条件
const logFilters = reactive({
  dateRange: [],
  actionType: '',
  userId: ''
})

// 操作类型映射
const actionTypes = {
  device: {
    label: '设备管理',
    options: {
      'create_device': '创建设备',
      'update_device': '更新设备',
      'delete_device': '删除设备',
      'device_status_change': '设备状态变更'
    }
  },
  detectionconfig: {
    label: '检测管理',
    options: {
      'create_detection_config': '创建检测配置',
      'update_detection_config': '更新检测配置',
      'delete_detection_config': '删除检测配置',
      'start_detection': '启动检测任务',
      'stop_detection': '停止检测任务'
    }
  },
  detectionevent: {
    label: '检测事件',
    options: {
      'create_detection_event': '创建检测事件',
      'update_detection_event': '更新检测事件',
      'delete_detection_event': '删除检测事件',
      'export_detection_events': '导出检测事件'
    }
  },
  model: {
    label: '模型管理',
    options: {
      'upload_model': '上传模型',
      'delete_model': '删除模型',
      'toggle_model': '启用/禁用模型',
      'update_model_config': '更新模型配置'
    }
  },
  push: {
    label: '推送管理',
    options: {
      'create_data_push': '创建推送配置',
      'update_data_push': '更新推送配置',
      'delete_data_push': '删除推送配置',
      'toggle_data_push': '启用/禁用推送配置'
    }
  },
  system: {
    label: '系统管理',
    options: {
      'clear_system_logs': '清除系统日志',
      'export_system_logs': '导出系统日志',
      'update_system_config': '更新系统配置',
      'restart_service': '重启服务'
    }
  },
  user: {
    label: '用户管理',
    options: {
      'create_user': '创建用户',
      'update_user': '更新用户',
      'delete_user': '删除用户',
      'update_user_permission': '更新用户权限',
      'change_password': '修改密码',
      'login': '用户登录',
      'logout': '用户登出'
    }
  },
  data: {
    label: '数据管理',
    options: {
      'export_data': '导出数据',
      'import_data': '导入数据',
      'backup_system': '系统备份',
      'restore_system': '系统恢复'
    }
  }
}

// 加载日志数据
const loadLogData = async () => {
  logsLoading.value = true
  try {
    const skip = (currentPage.value - 1) * pageSize.value
    const params = {
      skip,
      limit: pageSize.value
    }

    if (logFilters.userId) {
      params.user_id = logFilters.userId
    }

    if (logFilters.actionType) {
      params.action_type = logFilters.actionType
    }

    if (logFilters.dateRange && logFilters.dateRange.length === 2) {
      params.start_date = logFilters.dateRange[0]
      params.end_date = logFilters.dateRange[1]
    }

    const response = await systemLogApi.getSyslogs(params)
    sysLogs.value = response.data.data
    total.value = response.data.total
  } catch (error) {
    ElMessage.error('加载日志数据失败，请检查网络连接或服务器状态')
  } finally {
    logsLoading.value = false
  }
}

// 分页处理
const handleSizeChange = (val) => {
  pageSize.value = val
  loadLogData()
}

const handleCurrentChange = (val) => {
  currentPage.value = val
  loadLogData()
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  const date = new Date(dateTime)
  return date.toLocaleString('zh-CN')
}

// 获取操作类型文本
const getActionTypeText = (type) => {
  for (const group of Object.values(actionTypes)) {
    if (group.options[type]) {
      return group.options[type]
    }
  }
  return type
}

// 获取操作类型标签样式
const getActionTypeTag = (type) => {
  const typeTagMap = {
    // 设备管理
    'create_device': 'success',
    'update_device': 'warning',
    'delete_device': 'danger',
    'device_status_change': 'info',
    // 检测管理
    'create_detection_config': 'success',
    'update_detection_config': 'warning',
    'delete_detection_config': 'danger',
    'toggle_detection_config': 'info',
    'create_detection_event': 'success',
    'update_detection_event': 'warning',
    'delete_detection_event': 'danger',
    'export_detection_events': 'success',
    // 模型管理
    'upload_model': 'success',
    'delete_model': 'danger',
    'toggle_model': 'info',
    'update_model_config': 'warning',
    // 推送管理
    'create_push_config': 'success',
    'update_push_config': 'warning',
    'delete_push_config': 'danger',
    'toggle_push_config': 'info',
    // 系统管理
    'clear_system_logs': 'success',
    'export_system_logs': 'success',
    'update_system_config': 'warning',
    'restart_service': 'warning',
    // 用户管理
    'create_user': 'success',
    'update_user': 'warning',
    'delete_user': 'danger',
    'update_user_permission': 'info',
    'change_password': 'success',
    'login': 'success',
    'logout': 'success',
    // 数据管理
    'export_data': 'success',
    'import_data': 'success',
    'backup_system': 'success',
    'restore_system': 'success'
  }
  return typeTagMap[type] || ''
}

// 处理导出
const handleExport = async () => {
  try {
    const params = {}
    if (logFilters.dateRange && logFilters.dateRange.length === 2) {
      params.start_date = logFilters.dateRange[0]
      params.end_date = logFilters.dateRange[1]
    }
    if (logFilters.actionType) {
      params.action_type = logFilters.actionType
    }

    const response = await systemLogApi.exportSystemLogs(params)
    const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `system_logs_${new Date().toISOString().split('T')[0]}.json`
    link.click()
    window.URL.revokeObjectURL(url)

    ElMessage.success('日志导出成功')
  } catch (error) {
    ElMessage.error('日志导出失败')
  }
}

// 处理清除日志
const handleClear = () => {
  clearDialogVisible.value = true
}

// 确认清除日志
const confirmClear = async () => {
  try {
    clearing.value = true
    await systemLogApi.clearSystemLogs(clearForm.days)
    ElMessage.success('日志清除成功')
    clearDialogVisible.value = false
    loadLogData()
  } catch (error) {
    ElMessage.error('日志清除失败')
  } finally {
    clearing.value = false
  }
}

// 处理查询
const handleSearch = () => {
  currentPage.value = 1
  loadLogData()
}

// 重置筛选条件
const resetFilter = () => {
  logFilters.dateRange = []
  logFilters.actionType = ''
  logFilters.userId = ''
  handleSearch()
}

// 检测日志数据
const detectionLogsLoading = ref(false)
const detectionLogCurrentPage = ref(1)
const detectionLogPageSize = ref(10)
const detectionLogTotal = ref(0)

// 检测日志筛选条件
const detectionLogFilters = reactive({
  dateRange: [],
  operation: '',
  status: '',
  device_id: '',
  config_id: ''
})

// 操作类型文本映射
const operationTypeMap = {
  'start': '启动',
  'stop': '停止',
  'auto_start': '自动启动',
  'auto_stop': '自动停止',
  'schedule': '定时设置',
  'unschedule': '取消定时'
}

// 获取操作类型文本
const getOperationTypeText = (type) => {
  return operationTypeMap[type] || type
}

// 获取操作类型标签颜色
const getOperationTypeTag = (type) => {
  const tagMap = {
    'start': 'success',
    'stop': 'danger',
    'auto_start': 'success',
    'auto_stop': 'warning',
    'schedule': 'info',
    'unschedule': 'info'
  }
  return tagMap[type] || 'info'
}

// 加载检测日志数据
const loadDetectionLogData = async () => {
  detectionLogsLoading.value = true
  try {
    const skip = (detectionLogCurrentPage.value - 1) * detectionLogPageSize.value
    const params = {
      skip,
      limit: detectionLogPageSize.value
    }

    if (detectionLogFilters.operation) {
      params.operation = detectionLogFilters.operation
    }

    if (detectionLogFilters.status) {
      params.status = detectionLogFilters.status
    }

    if (detectionLogFilters.device_id) {
      params.device_id = detectionLogFilters.device_id
    }

    if (detectionLogFilters.config_id) {
      params.config_id = detectionLogFilters.config_id
    }

    if (detectionLogFilters.dateRange && detectionLogFilters.dateRange.length === 2) {
      params.start_date = detectionLogFilters.dateRange[0]
      params.end_date = detectionLogFilters.dateRange[1]
    }

    const response = await systemLogApi.getDetectionLogs(params)
    detectionLogs.value = response.data.data
    detectionLogTotal.value = response.data.total
  } catch (error) {
    ElMessage.error('加载检测日志数据失败，请检查网络连接或服务器状态')
  } finally {
    detectionLogsLoading.value = false
  }
}

// 检测日志分页处理
const handleDetectionLogSizeChange = (val) => {
  detectionLogPageSize.value = val
  loadDetectionLogData()
}

const handleDetectionLogCurrentChange = (val) => {
  detectionLogCurrentPage.value = val
  loadDetectionLogData()
}

// 处理检测日志查询
const handleDetectionLogSearch = () => {
  detectionLogCurrentPage.value = 1
  loadDetectionLogData()
}

// 重置检测日志筛选条件
const resetDetectionLogFilter = () => {
  detectionLogFilters.dateRange = []
  detectionLogFilters.operation = ''
  detectionLogFilters.status = ''
  detectionLogFilters.device_id = ''
  detectionLogFilters.config_id = ''
  handleDetectionLogSearch()
}

// 检测日志清除相关
const clearDetectionLogDialogVisible = ref(false)
const clearingDetectionLog = ref(false)
const clearDetectionLogForm = reactive({
  days: 30
})

// 处理导出检测日志
const handleExportDetectionLogs = async () => {
  try {
    const params = {}
    if (detectionLogFilters.dateRange && detectionLogFilters.dateRange.length === 2) {
      params.start_date = detectionLogFilters.dateRange[0]
      params.end_date = detectionLogFilters.dateRange[1]
    }
    if (detectionLogFilters.operation) {
      params.operation = detectionLogFilters.operation
    }
    if (detectionLogFilters.status) {
      params.status = detectionLogFilters.status
    }
    if (detectionLogFilters.device_id) {
      params.device_id = detectionLogFilters.device_id
    }
    if (detectionLogFilters.config_id) {
      params.config_id = detectionLogFilters.config_id
    }

    const response = await systemLogApi.exportDetectionLogs(params)

    // 处理文件下载
    const blob = new Blob([response.data], {
      type: response.headers['content-type']
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `detection_logs_${new Date().toISOString().split('T')[0]}.xlsx`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    ElMessage.success('检测日志导出成功')
  } catch (error) {
    // console.error('导出检测日志失败:', error)
    ElMessage.error('检测日志导出失败')
  }
}

// 处理清除检测日志
const handleClearDetectionLogs = () => {
  clearDetectionLogDialogVisible.value = true
}

// 确认清除检测日志
const confirmClearDetectionLog = async () => {
  try {
    clearingDetectionLog.value = true
    await systemLogApi.clearDetectionLogs(clearDetectionLogForm.days)
    ElMessage.success('检测日志清除成功')
    clearDetectionLogDialogVisible.value = false
    loadDetectionLogData()
  } catch (error) {
    // console.error('清除检测日志失败:', error)
    ElMessage.error('检测日志清除失败')
  } finally {
    clearingDetectionLog.value = false
  }
}

// 页面初始化
onMounted(() => {
  syncTabFromRoute()
  refreshStatus(false)
  refreshInterval = setInterval(() => refreshStatus(true), 5000)

  // 加载系统日志
  loadLogData()

  // 加载检测日志
  loadDetectionLogData()
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.system-container {
  padding: 20px;
}

.model-option {
  display: flex;
  flex-direction: column;
}

.model-name {
  /* font-weight: bold; */
  color: #303133;
  margin-bottom: 2px;
}

.model-desc {
  font-size: 12px;
  color: #909399;
}

.page-header {
  display: flex;
  flex-direction: column;
  margin-bottom: 20px;
}


.system-tabs {
  margin-bottom: 10px;
}

.status-panel {
  max-width: 1200px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.status-hint {
  font-size: 13px;
  color: #909399;
}

.info-card :deep(.el-descriptions__label) {
  width: 110px;
}

.resource-grid .el-col {
  margin-bottom: 16px;
}

.npu-idle {
  font-size: 12px;
  color: #909399;
}

.npu-footer {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.status-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.resource-item {
  background-color: #f8fafc;
  padding: 16px;
  border-radius: 8px;
}

.item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #64748b;
  font-size: 14px;
}

.item-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}

.service-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background-color: #f8fafc;
  border-radius: 8px;
}

.service-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-icon {
  font-size: 18px;
}

.status-icon.running {
  color: #67c23a;
}

.status-icon.stopped {
  color: #f56c6c;
}

.status-icon.starting,
.status-icon.stopping {
  color: #e6a23c;
}

.service-name {
  font-size: 14px;
  color: #2c3e50;
}

.mt-20 {
  margin-top: 20px;
}

/* 系统日志样式 */
.filter-options {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}

.filter-card {
  margin-bottom: 20px;
  border-radius: 8px;
}

.filter-card .el-form {
  margin-bottom: 0;
}

.filter-card .el-form-item {
  margin-bottom: 0;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.log-list {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.logs-panel {
  margin-top: 20px;
}

.integrations-panel {
  margin-top: 20px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.panel-desc {
  margin-top: 4px;
  font-size: 13px;
  color: #909399;
  font-weight: normal;
}

.header-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.warning-text {
  color: #f56c6c;
  font-size: 14px;
}

.action-buttons {
  margin-left: auto;
}
</style> 