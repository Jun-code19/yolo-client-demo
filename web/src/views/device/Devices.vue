<template>
  <div class="devices-container">
    <div class="page-header">
      <h2>视频设备管理</h2>
      <el-space wrap>
        <el-dropdown @command="handleExport">
          <el-button type="primary">
            <el-icon>
              <Download />
            </el-icon>导出
            <el-icon>
              <ArrowDown />
            </el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="data">导出数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="handleImport">
          <el-icon>
            <Upload />
          </el-icon>导入
        </el-button>
        <el-button type="primary" @click="handleAdd">
          <el-icon>
            <Plus />
          </el-icon>添加设备
        </el-button>
      </el-space>
    </div>
    <!-- 筛选区域 -->
    <el-card class="filter-section">
        <el-form :model="filterForm" inline>
          <el-form-item label="设备类型">
            <el-select v-model="filterForm.device_type" placeholder="请选择设备类型" clearable style="width: 150px;">
              <el-option label="摄像头" value="camera" />
              <el-option label="硬盘录像机" value="nvr" />
            </el-select>
          </el-form-item>

          <el-form-item label="设备状态">
            <el-select v-model="filterForm.status" placeholder="请选择状态" clearable style="width: 120px;">
              <el-option label="在线" :value="true" />
              <el-option label="离线" :value="false" />
            </el-select>
          </el-form-item>

          <el-form-item label="设备名称">
            <el-input v-model="filterForm.device_name" placeholder="请输入设备名称" clearable style="width: 150px;" />
          </el-form-item>

          <!-- <el-form-item label="IP地址">
            <el-input v-model="filterForm.area" placeholder="请输入区域" clearable style="width: 120px;" />
          </el-form-item> -->

          <el-form-item>
            <el-space>
              <el-button type="primary" @click="handleFilter" :loading="loading">
                <el-icon>
                  <Search />
                </el-icon>搜索
              </el-button>
              <el-button @click="handleResetFilter">
                <el-icon>
                  <Refresh />
                </el-icon>重置
              </el-button>
            </el-space>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 设备列表 -->
    <el-card class="device-list">
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-radio-group v-model="viewMode" size="default" @change="handleViewModeChange">
            <el-radio-button value="tree">
              <el-icon><Share /></el-icon>
              树形
            </el-radio-button>
            <el-radio-button value="card">
              <el-icon><Grid /></el-icon>
              卡片
            </el-radio-button>
          </el-radio-group>
        </div>
        <div class="toolbar-right">
        <span v-if="viewMode === 'tree' && selectedDevices.length > 0" class="selection-tip">
          已选择 {{ selectedDevices.length }} 项
        </span>
        <el-dropdown
          v-if="viewMode === 'tree' && selectedDevices.length > 0"
          @command="handleBatchMoveGroup"
        >
          <el-button size="small" type="primary">
            移动到分组
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="__ungrouped__">未分组</el-dropdown-item>
              <el-dropdown-item
                v-for="group in deviceGroups"
                :key="group.group_id"
                :command="group.group_id"
              >
                {{ group.group_name }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          v-if="viewMode === 'tree'"
          size="small"
          type="danger"
          :disabled="selectedDevices.length === 0"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
        </div>
      </div>

      <!-- 树形 + 列表 -->
      <div v-if="viewMode === 'tree'" class="tree-layout" v-loading="loading">
        <aside class="tree-panel">
          <div class="tree-panel-header">
            <span>设备分组</span>
            <el-button link type="primary" size="small" @click="openGroupManageDialog">
              <el-icon><Setting /></el-icon>
              管理分组
            </el-button>
          </div>
          <el-tree
            :data="groupTreeData"
            node-key="id"
            highlight-current
            :current-node-key="selectedTreeKey"
            default-expand-all
            :expand-on-click-node="false"
            @node-click="handleTreeNodeClick"
          >
            <template #default="{ data }">
              <div class="tree-node">
                <el-icon v-if="data.id === '__all__'"><Monitor /></el-icon>
                <el-icon v-else-if="data.id === '__ungrouped__'"><FolderOpened /></el-icon>
                <el-icon v-else><Folder /></el-icon>
                <span class="tree-node-label">{{ data.label }}</span>
                <el-tag size="small" type="info" round>{{ data.count }}</el-tag>
              </div>
            </template>
          </el-tree>
        </aside>
        <main class="tree-content">
          <div class="tree-content-title">
            <h3>{{ selectedTreeLabel }}</h3>
            <span class="tree-content-sub">{{ treeFilteredDevices.length }} 台设备</span>
          </div>
          <el-table
            :data="paginatedTreeDevices"
            style="width: 100%"
            stripe
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="55" />
            <el-table-column prop="device_id" label="设备ID" sortable min-width="120" />
            <el-table-column prop="device_name" label="设备名称" sortable min-width="150" />
            <el-table-column v-if="selectedTreeKey === '__all__'" prop="group_name" label="分组" min-width="110">
              <template #default="{ row }">
                <el-tag v-if="row.group_name" size="small" type="info">{{ row.group_name }}</el-tag>
                <span v-else class="text-muted">未分组</span>
              </template>
            </el-table-column>
            <el-table-column prop="device_type" label="设备类型" sortable min-width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="getDeviceTypeTag(row.device_type)">
                  {{ getDeviceTypeName(row.device_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" label="IP地址" sortable min-width="120" />
            <el-table-column prop="port" label="端口" width="72" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status ? 'success' : 'danger'">
                  {{ row.status ? '在线' : '离线' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_heartbeat" label="最后心跳" min-width="160">
              <template #default="{ row }">
                {{ formatDateTime(row.last_heartbeat) }}
              </template>
            </el-table-column>
            <el-table-column prop="stream_type" label="码流" width="80">
              <template #default="{ row }">
                {{ row.stream_type === 'sub' ? '辅码流' : '主码流' }}
              </template>
            </el-table-column>
            <el-table-column prop="rtsp_url_mode" label="拉流方式" min-width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.rtsp_url_mode === 'custom' ? 'warning' : 'info'">
                  {{ getRtspPresetLabel(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-button-group>
                  <el-button type="warning" link @click="handlePreview(row)">画面</el-button>
                  <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
                  <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
                </el-button-group>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination tree-pagination">
            <el-pagination
              v-model:current-page="treePage"
              v-model:page-size="treePageSize"
              :total="treeFilteredDevices.length"
              :page-sizes="[20, 50, 100, 200]"
              layout="prev, pager, next, jumper, ->, total, sizes"
              @size-change="handleTreeSizeChange"
              @current-change="handleTreePageChange"
            />
          </div>
        </main>
      </div>

      <!-- 卡片分组视图 -->
      <div v-else v-loading="loading" class="card-grid-view">
        <div class="card-view-header">
          <span class="card-view-title">分组概览</span>
          <el-button size="small" @click="openGroupManageDialog">
            <el-icon><Setting /></el-icon>
            管理分组
          </el-button>
        </div>
        <el-empty v-if="groupOverview.length === 0" description="暂无设备数据" />
        <el-row v-else :gutter="16">
          <el-col
            v-for="group in groupOverview"
            :key="group.group_id || '__ungrouped__'"
            :xs="24"
            :sm="12"
            :lg="8"
            :xl="6"
          >
            <el-card class="group-card" shadow="hover">
              <template #header>
                <div class="group-card-header">
                  <div class="group-card-title">
                    <el-icon class="group-card-icon"><Folder /></el-icon>
                    <span>{{ group.group_name }}</span>
                  </div>
                  <div class="group-card-actions">
                    <el-tag size="small">{{ group.device_count }} 台</el-tag>
                    <el-button
                      v-if="group.group_id"
                      link
                      type="primary"
                      size="small"
                      @click="openEditGroupDialog(group)"
                    >
                      编辑
                    </el-button>
                  </div>
                </div>
              </template>
              <div v-if="group.description" class="group-card-desc">{{ group.description }}</div>
              <div class="group-card-stats">
                <span class="online">在线 {{ countOnline(group.devices) }}</span>
                <span class="offline">离线 {{ countOffline(group.devices) }}</span>
              </div>
              <div class="group-device-list">
                <el-empty v-if="!group.devices?.length" description="暂无设备" :image-size="48" />
                <div
                  v-for="device in group.devices"
                  :key="device.device_id"
                  class="group-device-item"
                >
                  <div class="device-item-main">
                    <el-icon :class="device.status ? 'status-online' : 'status-offline'">
                      <VideoCamera />
                    </el-icon>
                    <div class="device-item-info">
                      <div class="device-item-name">{{ device.device_name }}</div>
                      <div class="device-item-meta">{{ device.ip_address }} · {{ getRtspPresetLabel(device) }}</div>
                    </div>
                  </div>
                  <el-button-group class="device-item-actions">
                    <el-button link type="warning" size="small" @click="handlePreview(device)">画面</el-button>
                    <el-button link type="primary" size="small" @click="handleEdit(device)">编辑</el-button>
                  </el-button-group>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- 添加/编辑设备对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="dialogType === 'add' ? '添加设备' : '编辑设备'" 
      width="40%" top="5vh"
      destroy-on-close
      :z-index="999999"
      append-to-body
      class="high-priority-dialog"
    >
      <el-form ref="deviceFormRef" :model="deviceForm" :rules="deviceRules" label-width="100px">
        <el-form-item label="设备ID" prop="device_id">
          <el-input v-model="deviceForm.device_id" placeholder="请输入设备ID" :disabled="dialogType === 'edit'" />
        </el-form-item>
        <el-form-item label="设备名称" prop="device_name">
          <el-input v-model="deviceForm.device_name" placeholder="请输入设备名称" />
        </el-form-item>
        <el-form-item label="设备类型" prop="device_type">
          <el-select v-model="deviceForm.device_type" placeholder="请选择设备类型" style="width: 100%">
            <el-option label="摄像头" value="camera" />
            <el-option label="硬盘录像机" value="nvr" />
          </el-select>
        </el-form-item>
        <el-form-item label="通道号" prop="channel" v-if="deviceForm.device_type === 'nvr'">
          <el-input-number v-model="deviceForm.channel" :min="1" :max="128" placeholder="请输入通道号" style="width: 100%" />
        </el-form-item>
        <el-form-item label="码流选择" prop="stream_type">
          <el-select v-model="deviceForm.stream_type" placeholder="请选择码流" style="width: 100%">
            <el-option label="主码流" value="main" />
            <el-option label="辅码流" value="sub" />
          </el-select>
        </el-form-item>
        <template v-if="['camera', 'nvr'].includes(deviceForm.device_type)">
          <el-form-item label="拉流方式" prop="selectedRtspPreset">
            <el-select
              v-model="selectedRtspPreset"
              placeholder="请选择拉流方式"
              style="width: 100%"
              @change="handleRtspPresetChange"
            >
              <el-option
                v-for="preset in RTSP_URL_PRESETS"
                :key="preset.value"
                :label="preset.label"
                :value="preset.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="RTSP 格式" prop="rtsp_url">
            <el-input
              :model-value="displayRtspFormat"
              type="textarea"
              :rows="2"
              :readonly="selectedRtspPreset === 'dahua'"
              :placeholder="selectedRtspPreset === 'dahua' ? '' : 'RTSP 地址或模板'"
              @update:model-value="handleRtspFormatInput"
            />
            <div class="form-hint rtsp-form-hint">
              <div>{{ rtspPresetHint }}</div>
              <div>示例：{{ rtspPreviewExample }}</div>
            </div>
          </el-form-item>
        </template>
        <el-form-item label="位置" prop="location">
          <el-input v-model="deviceForm.location" placeholder="请输入设备位置" />
        </el-form-item>
        <el-form-item label="所属分组" prop="group_id">
          <el-select v-model="deviceForm.group_id" placeholder="未分组" clearable style="width: 100%">
            <el-option
              v-for="group in deviceGroups"
              :key="group.group_id"
              :label="group.group_name"
              :value="group.group_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="区域" prop="area">
          <el-input v-model="deviceForm.area" placeholder="请输入设备区域" />
        </el-form-item>
        <el-form-item label="IP地址" prop="ip_address">
          <el-input v-model="deviceForm.ip_address" placeholder="请输入IP地址" />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="deviceForm.port" :min="1" :max="65535" placeholder="请输入端口号" style="width: 100%" />
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="deviceForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="deviceForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            确认
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 设备画面（实时预览 + 区域画线） -->
    <el-dialog 
      v-model="previewVisible" 
      :title="`设备画面 · ${currentDevice?.device_name || ''}`"
      width="72%" top="4vh"
      destroy-on-close 
      @close="stopPreview"
      :z-index="100000"
      append-to-body
      class="preview-dialog high-priority-dialog"
    >
      <div class="frame-dialog-toolbar">
        <el-space wrap>
          <el-switch
            v-model="areaConfig.enabled"
            active-text="启用区域"
            inactive-text="未启用"
          />
          <el-button type="primary" size="small" @click="startDrawing" :disabled="!areaConfig.enabled">
            开始绘制
          </el-button>
          <el-button size="small" @click="clearDrawing" :disabled="!areaConfig.enabled">清除区域</el-button>
        </el-space>
        <el-text type="info" size="small">左键添加顶点，右键完成（至少3点）</el-text>
      </div>

      <div class="preview-container">
        <div v-if="previewLoading" class="loading-wrapper">
          <el-skeleton animated :rows="8" />
          <div class="loading-text">正在连接设备，请稍候...</div>
        </div>
        <div v-else-if="previewError && !displayImage" class="error-wrapper">
          <el-icon :size="64">
            <CircleClose />
          </el-icon>
          <p>{{ previewError }}</p>
          <el-button @click="retryPreview">重试</el-button>
        </div>
        <div v-else-if="!displayImage" class="video-placeholder">
          <el-icon :size="64">
            <VideoCamera />
          </el-icon>
          <p>等待画面...</p>
        </div>
        <div v-else ref="previewWrapperRef" class="video-wrapper">
          <img
            :ref="(el) => { frameImageRef = el }"
            :src="displayImage"
            class="preview-image"
            @load="onPreviewFrameLoaded"
          />
          <canvas
            ref="drawingCanvas"
            class="drawing-canvas"
            @mousedown="handleMouseDown"
            @mousemove="handleMouseMove"
            @contextmenu.prevent="handleRightClick"
          />
          <div class="stream-info">
            <span>{{ currentDevice?.device_name || '未知设备' }}</span>
            <el-tag v-if="isStreaming" size="small" type="success" effect="dark">实时</el-tag>
            <span v-if="streamResolution">{{ streamResolution }}</span>
          </div>
        </div>
      </div>

      <div class="preview-controls">
        <el-space wrap>
          <el-button @click="takeSnapshot" :disabled="!displayImage">
            <el-icon><Camera /></el-icon>截图
          </el-button>
          <el-button @click="toggleFullscreen" :disabled="!displayImage">
            <el-icon><FullScreen /></el-icon>{{ isFullscreen ? '退出全屏' : '全屏' }}
          </el-button>
        </el-space>
      </div>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="previewVisible = false">关闭</el-button>
          <el-button
            type="primary"
            :loading="areaSaveLoading"
            :disabled="!canSaveArea()"
            @click="handleSaveAreaConfig"
          >
            保存区域
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 分组管理对话框 -->
    <el-dialog
      v-model="groupManageVisible"
      title="设备分组管理"
      width="680px"
      destroy-on-close
      append-to-body
    >
      <el-form :inline="true" :model="newGroupForm" class="group-create-form">
        <el-form-item label="组名称">
          <el-input v-model="newGroupForm.group_name" placeholder="新分组名称" style="width: 160px" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="newGroupForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="groupSaving" @click="handleCreateGroup">添加分组</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="deviceGroups" stripe border max-height="360">
        <el-table-column prop="group_name" label="组名称" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip />
        <el-table-column prop="sort_order" label="排序" width="70" />
        <el-table-column prop="device_count" label="设备数" width="80" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditGroupDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDeleteGroup(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 编辑分组对话框 -->
    <el-dialog v-model="groupEditVisible" title="编辑分组" width="480px" destroy-on-close append-to-body>
      <el-form :model="editGroupForm" label-width="80px">
        <el-form-item label="组名称" required>
          <el-input v-model="editGroupForm.group_name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editGroupForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editGroupForm.sort_order" :min="0" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="groupSaving" @click="handleSaveGroupEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 导入对话框 -->
    <el-dialog 
      v-model="importDialogVisible" 
      title="导入设备" 
      width="30%" top="5vh"
      destroy-on-close
      :z-index="100001"
      append-to-body
      class="import-dialog high-priority-dialog"
    >
      <el-upload class="upload-demo" drag action="#" :auto-upload="false" :on-change="handleFileChange" :limit="1"
        accept=".xlsx,.xls,.csv">
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            请上传 Excel(.xlsx/.xls) 或 CSV(.csv) 格式文件，文件大小不超过 10MB。
            旧模板不含 rtsp_url_mode / rtsp_url 时，将默认使用大华拉流方式。
          </div>
        </template>
      </el-upload>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="importDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitImport" :loading="importing">
            确认导入
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, h, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, VideoCamera, CircleClose, Camera, Download, ArrowDown, Upload, UploadFilled, Search, Refresh, FullScreen, Folder, Setting, Share, Grid, Monitor, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import deviceApi from '@/api/device'
import { useDeviceRoiDrawing } from '@/composables/useDeviceRoiDrawing'
import { useDeviceFramePreview } from '@/composables/useDeviceFramePreview'

const router = useRouter()
import {
  buildRtspUrl,
  getRtspPresetLabel,
  RTSP_URL_PRESETS,
  DAHUA_RTSP_TEMPLATE,
  detectRtspPreset,
  applyRtspPreset,
  getRtspPreset
} from '@/utils/rtspUrl'

const selectedRtspPreset = ref('dahua')

const VIEW_MODE_KEY = 'devices_view_mode'
const rawViewMode = localStorage.getItem(VIEW_MODE_KEY) || 'tree'
const viewMode = ref(
  rawViewMode === 'card' ? 'card' : 'tree'
)
if (rawViewMode === 'list' || rawViewMode === 'group') {
  localStorage.setItem(VIEW_MODE_KEY, rawViewMode === 'group' ? 'card' : 'tree')
}
const deviceGroups = ref([])
const groupOverview = ref([])
const selectedTreeKey = ref('__all__')
const groupManageVisible = ref(false)
const groupEditVisible = ref(false)
const groupSaving = ref(false)
const newGroupForm = reactive({
  group_name: '',
  sort_order: 0,
})
const editGroupForm = reactive({
  group_id: '',
  group_name: '',
  description: '',
  sort_order: 0,
})

const displayRtspFormat = computed(() => {
  if (selectedRtspPreset.value === 'dahua') {
    return DAHUA_RTSP_TEMPLATE
  }
  return deviceForm.rtsp_url || ''
})

const rtspPresetHint = computed(() => {
  const preset = getRtspPreset(selectedRtspPreset.value)
  return preset?.hint || ''
})

const rtspPreviewExample = computed(() => {
  return previewRtspUrl.value || '请先填写 IP、账号等信息'
})

const previewRtspUrl = computed(() => {
  if (!deviceForm.ip_address || !deviceForm.username) {
    return ''
  }
  return buildRtspUrl(deviceForm)
})

// 设备数据
const loading = ref(false)
const treePage = ref(1)
const treePageSize = ref(20)
const selectedDevices = ref([])

// 对话框控制
const dialogVisible = ref(false)
const dialogType = ref('add')
const previewVisible = ref(false)
const submitting = ref(false)

// 表单相关
const deviceFormRef = ref(null)
const deviceForm = reactive({
  device_id: '',
  device_name: '',
  device_type: 'camera',
  ip_address: '',
  port: 554,
  username: '',
  password: '',
  channel: 1,
  stream_type: 'main',
  rtsp_url_mode: 'dahua',
  rtsp_url: '',
  location: '',
  area: '',
  group_id: null
})

const deviceRules = {
  device_id: [{ required: true, message: '请输入设备ID', trigger: 'blur' }],
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  device_type: [{ required: true, message: '请选择设备类型', trigger: 'change' }],
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    {
      pattern: /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
      message: '请输入正确的IP地址',
      trigger: 'blur'
    }
  ],
  port: [{ required: true, message: '请输入端口号', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  rtsp_url: [{
    validator: (_rule, value, callback) => {
      if (selectedRtspPreset.value !== 'dahua' && (!value || !String(value).trim())) {
        callback(new Error('当前拉流方式需填写 RTSP 格式'))
      } else {
        callback()
      }
    },
    trigger: 'blur'
  }]
}

// 预览相关
const currentDevice = ref(null)
const previewWrapperRef = ref(null)
const isFullscreen = ref(false)

const {
  areaConfig,
  drawingCanvas,
  frameImageRef,
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
} = useDeviceRoiDrawing()

const {
  previewLoading,
  previewError,
  displayImage,
  isStreaming,
  streamResolution,
  startPreview: startDevicePreview,
  refreshPreview: refreshDevicePreview,
  stopPreview: stopDevicePreview,
} = useDeviceFramePreview({
  onFrame: () => {
    requestAnimationFrame(() => {
      if (frameImageRef.value?.complete) {
        refreshCanvasDrawing()
      }
    })
  },
})

const onPreviewFrameLoaded = () => {
  onFrameMediaLoaded()
}

// 导入相关
const importDialogVisible = ref(false)
const importFile = ref(null)
const importing = ref(false)

// 筛选相关
const filterForm = reactive({
  device_type: '',
  status: '',
  device_name: '',
  ip_address: '',
  location: '',
  area: ''
})

// 跟踪当前是否在筛选状态
const isFiltering = ref(false)

const hasActiveFilter = () => {
  return Object.entries(filterForm).some(([_, value]) => value !== '' && value !== null && value !== undefined)
}

const groupTreeData = computed(() => {
  const ungrouped = groupOverview.value.find(g => !g.group_id)
  const ungroupedCount = ungrouped?.device_count || 0
  const totalCount = groupOverview.value.reduce((sum, g) => sum + (g.device_count || 0), 0)

  const groupNodes = deviceGroups.value.map((group) => {
    const overview = groupOverview.value.find(g => g.group_id === group.group_id)
    return {
      id: group.group_id,
      label: group.group_name,
      count: overview?.device_count ?? group.device_count ?? 0,
      group_id: group.group_id,
    }
  })

  return [
    { id: '__all__', label: '全部设备', count: totalCount, group_id: null },
    ...groupNodes,
    { id: '__ungrouped__', label: '未分组', count: ungroupedCount, group_id: '__ungrouped__' },
  ]
})

const selectedTreeLabel = computed(() => {
  const node = groupTreeData.value.find(item => item.id === selectedTreeKey.value)
  return node?.label || '全部设备'
})

const treeFilteredDevices = computed(() => {
  if (selectedTreeKey.value === '__all__') {
    return groupOverview.value.flatMap(g => g.devices || [])
  }
  const target = groupOverview.value.find(g => {
    if (selectedTreeKey.value === '__ungrouped__') return !g.group_id
    return g.group_id === selectedTreeKey.value
  })
  return target?.devices || []
})

const paginatedTreeDevices = computed(() => {
  const start = (treePage.value - 1) * treePageSize.value
  return treeFilteredDevices.value.slice(start, start + treePageSize.value)
})

watch(selectedTreeKey, () => {
  treePage.value = 1
  selectedDevices.value = []
})

watch(treeFilteredDevices, () => {
  const maxPage = Math.max(1, Math.ceil(treeFilteredDevices.value.length / treePageSize.value))
  if (treePage.value > maxPage) {
    treePage.value = maxPage
  }
})

const countOnline = (devices = []) => devices.filter(d => d.status).length
const countOffline = (devices = []) => devices.filter(d => !d.status).length

const reloadDevices = () => {
  loadGroupOverview(isFiltering.value || hasActiveFilter())
}

const loadDeviceGroups = async () => {
  try {
    const res = await deviceApi.getDeviceGroups()
    deviceGroups.value = res.data?.data || []
  } catch (error) {
    deviceGroups.value = []
  }
}

const loadGroupOverview = async (useFilter = false) => {
  loading.value = true
  try {
    const params = useFilter
      ? {
          device_type: filterForm.device_type,
          status: filterForm.status,
          device_name: filterForm.device_name,
        }
      : {}
    const response = await deviceApi.getDeviceGroupsOverview(params)
    groupOverview.value = response.data?.data || []
  } catch (error) {
    ElMessage.error('加载分组视图失败')
  } finally {
    loading.value = false
  }
}

const handleTreeNodeClick = (data) => {
  selectedTreeKey.value = data.id
}

const handleViewModeChange = () => {
  localStorage.setItem(VIEW_MODE_KEY, viewMode.value)
  selectedDevices.value = []
  if (viewMode.value === 'tree') {
    selectedTreeKey.value = '__all__'
  }
  reloadDevices()
}

const openGroupManageDialog = async () => {
  await loadDeviceGroups()
  groupManageVisible.value = true
}

const openEditGroupDialog = (group) => {
  if (!group?.group_id) return
  Object.assign(editGroupForm, {
    group_id: group.group_id,
    group_name: group.group_name,
    description: group.description || '',
    sort_order: group.sort_order ?? 0,
  })
  groupEditVisible.value = true
}

const handleCreateGroup = async () => {
  if (!newGroupForm.group_name?.trim()) {
    ElMessage.warning('请输入分组名称')
    return
  }
  groupSaving.value = true
  try {
    await deviceApi.createDeviceGroup({
      group_name: newGroupForm.group_name.trim(),
      sort_order: newGroupForm.sort_order,
    })
    ElMessage.success('分组创建成功')
    newGroupForm.group_name = ''
    newGroupForm.sort_order = 0
    await loadDeviceGroups()
    reloadDevices()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '创建分组失败')
  } finally {
    groupSaving.value = false
  }
}

const handleSaveGroupEdit = async () => {
  if (!editGroupForm.group_name?.trim()) {
    ElMessage.warning('请输入分组名称')
    return
  }
  groupSaving.value = true
  try {
    await deviceApi.updateDeviceGroup(editGroupForm.group_id, {
      group_name: editGroupForm.group_name.trim(),
      description: editGroupForm.description,
      sort_order: editGroupForm.sort_order,
    })
    ElMessage.success('分组已更新')
    groupEditVisible.value = false
    await loadDeviceGroups()
    reloadDevices()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '更新分组失败')
  } finally {
    groupSaving.value = false
  }
}

const getApiErrorMessage = (error, fallback = '操作失败') => {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map(item => item.msg || item.message || String(item)).join('；')
  }
  return error.message || fallback
}

const handleDeleteGroup = (group) => {
  ElMessageBox.confirm(
    `删除分组「${group.group_name}」？组内设备将移至未分组；若存在按分组运行的检测任务，将解除关联并停用。`,
    '删除确认',
    { type: 'warning' }
  ).then(async () => {
    try {
      const res = await deviceApi.deleteDeviceGroup(group.group_id)
      ElMessage.success(res.data?.message || '分组已删除')
      await loadDeviceGroups()
      reloadDevices()
      if (selectedTreeKey.value === group.group_id) {
        selectedTreeKey.value = '__all__'
      }
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, '删除分组失败'))
    }
  }).catch(() => {})
}

const handleBatchMoveGroup = async (groupId) => {
  if (selectedDevices.value.length === 0) return
  try {
    const deviceIds = selectedDevices.value.map(item => item.device_id)
    await deviceApi.assignDevicesToGroup(groupId, deviceIds)
    ElMessage.success('设备分组已更新')
    selectedDevices.value = []
    reloadDevices()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '移动分组失败')
  }
}

// 刷新状态
const refreshStatus = async () => {
  try {
    // 获取设备在线状态
    const response = await deviceApi.getDevicesStatus()
    if (response.status === 200) {
      reloadDevices()
    } else {
      ElMessage.error('获取设备在线状态失败')
    }
  } catch (error) {
    ElMessage.error('获取设备在线状态失败')
  }
}

// 处理全屏状态变化
const handleFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
}

// 初始化
onMounted(() => {
  loadDeviceGroups()
  loadGroupOverview()
  // refreshStatus()
  // refreshInterval = setInterval(refreshStatus, 60000)
  
  // 监听全屏状态变化
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
  document.addEventListener('mozfullscreenchange', handleFullscreenChange)
  document.addEventListener('MSFullscreenChange', handleFullscreenChange)
  
  // 监听键盘事件
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  stopPreview()
  if (isFullscreen.value) {
    exitFullscreen()
  }
  
  // 移除全屏状态监听
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
  document.removeEventListener('mozfullscreenchange', handleFullscreenChange)
  document.removeEventListener('MSFullscreenChange', handleFullscreenChange)
  
  // 移除键盘事件监听
  document.removeEventListener('keydown', handleKeyDown)
})

// 处理键盘事件
const handleKeyDown = (event) => {
  if (event.key === 'Escape' && isFullscreen.value) {
    exitFullscreen()
  }
}

// 树形列表分页
const handleTreeSizeChange = (val) => {
  treePageSize.value = val
  treePage.value = 1
}

const handleTreePageChange = (val) => {
  treePage.value = val
}

// 添加设备
const handleAdd = () => {
  dialogType.value = 'add'
  dialogVisible.value = true
  Object.assign(deviceForm, {
    device_id: '',
    device_name: '',
    device_type: 'camera',
    ip_address: '',
    port: 554,
    username: '',
    password: '',
    channel: 1,
    stream_type: 'main',
    rtsp_url_mode: 'dahua',
    rtsp_url: '',
    location: '',
    area: '',
    group_id: null
  })
  selectedRtspPreset.value = 'dahua'
}

// 编辑设备
const handleEdit = (row) => {
  dialogType.value = 'edit'
  dialogVisible.value = true
  Object.assign(deviceForm, {
    device_id: row.device_id,
    device_name: row.device_name,
    device_type: row.device_type,
    ip_address: row.ip_address,
    port: row.port,
    username: row.username,
    password: row.password,
    channel: row.channel || 1,
    stream_type: row.stream_type || 'main',
    rtsp_url_mode: row.rtsp_url_mode || 'dahua',
    rtsp_url: row.rtsp_url || '',
    location: row.location || '',
    area: row.area || '',
    group_id: row.group_id || null
  })
  syncRtspPresetFromForm()
}

const syncRtspPresetFromForm = () => {
  selectedRtspPreset.value = detectRtspPreset(deviceForm)
}

const handleRtspPresetChange = (presetValue) => {
  applyRtspPreset(presetValue, deviceForm)
}

const handleRtspFormatInput = (value) => {
  if (selectedRtspPreset.value === 'dahua') {
    return
  }
  deviceForm.rtsp_url = value
  deviceForm.rtsp_url_mode = 'custom'
  const preset = getRtspPreset(selectedRtspPreset.value)
  if (preset?.url && value !== preset.url && selectedRtspPreset.value !== 'generic') {
    selectedRtspPreset.value = 'generic'
  }
}

const prepareRtspFormForSubmit = () => {
  applyRtspPreset(selectedRtspPreset.value, deviceForm)
  if (selectedRtspPreset.value === 'dahua') {
    deviceForm.rtsp_url = ''
  }
}

// 提交表单
const handleSubmit = async () => {
  if (!deviceFormRef.value) return

  await deviceFormRef.value.validate(async (valid) => {
    if (!valid) return

    prepareRtspFormForSubmit()
    submitting.value = true
    try {
      if (dialogType.value === 'add') {
        // 创建设备
        await deviceApi.createDevice(deviceForm)
        ElMessage.success('设备添加成功')
      } else {
        // 更新设备信息
        await deviceApi.updateDevice(deviceForm.device_id, deviceForm)
        ElMessage.success('设备更新成功')
      }
      dialogVisible.value = false
      reloadDevices()
    } catch (error) {
      // console.error('操作失败:', error)
      ElMessage.error(`操作失败: ${error.response?.data?.detail || error.message}`)
    } finally {
      submitting.value = false
    }
  })
}

// 删除设备
const buildDeleteConfirmMessage = (deviceNames) => {
  const count = deviceNames.length
  const namesText = deviceNames.join('、')
  const actionText = count > 1
    ? `确认批量删除以下 ${count} 个设备及其关联数据吗？`
    : '确认删除以下设备及其关联数据吗？'

  return h('div', { class: 'delete-confirm-message' }, [
    h('p', { class: 'delete-confirm-line' }, actionText),
    h('p', { class: 'delete-confirm-line delete-confirm-tip' }, '关联数据包括：检测配置、检测事件、性能记录等。'),
    h('p', { class: 'delete-confirm-line delete-confirm-devices' }, [
      h('span', { class: 'delete-confirm-label' }, '设备：'),
      h('span', namesText)
    ])
  ])
}

const showDeleteConfirm = (title, deviceNames) => {
  return ElMessageBox.confirm(
    buildDeleteConfirmMessage(deviceNames),
    title,
    {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'device-delete-messagebox'
    }
  )
}

const handleDelete = (row) => {
  showDeleteConfirm('删除确认', [row.device_name]).then(async () => {
    try {
      await deviceApi.deleteDevice(row.device_id)
      ElMessage.success('删除成功')
      reloadDevices()
    } catch (error) {
      // console.error('删除失败:', error)
      ElMessage.error(`删除失败: ${error.response?.data?.detail || error.message}`)
    }
  }).catch(() => { })
}

const handleSelectionChange = (selection) => {
  selectedDevices.value = selection
}

const handleBatchDelete = () => {
  if (selectedDevices.value.length === 0) {
    ElMessage.warning('请先选择要删除的设备')
    return
  }

  const deviceNames = selectedDevices.value.map(item => item.device_name)
  showDeleteConfirm('批量删除确认', deviceNames).then(async () => {
    try {
      const deviceIds = selectedDevices.value.map(item => item.device_id)
      const response = await deviceApi.batchDeleteDevices(deviceIds)
      const deletedCount = response.data?.deleted_count ?? deviceIds.length
      const errors = response.data?.errors || []

      if (errors.length > 0) {
        ElMessage.warning(`已删除 ${deletedCount} 个设备，部分失败：${errors.join('；')}`)
      } else {
        ElMessage.success(`成功删除 ${deletedCount} 个设备`)
      }

      selectedDevices.value = []
      reloadDevices()
    } catch (error) {
      ElMessage.error(`批量删除失败: ${error.response?.data?.detail || error.message}`)
    }
  }).catch(() => { })
}

// 打开设备画面（实时预览 + 区域画线）
const handlePreview = async (row) => {
  currentDevice.value = row
  previewVisible.value = true
  isFullscreen.value = false
  resetAreaDraft()

  try {
    const response = await deviceApi.getDevice(row.device_id)
    currentDevice.value = response.data || row
    loadAreaFromDevice(currentDevice.value)
  } catch {
    currentDevice.value = row
    loadAreaFromDevice(row)
  }

  if (currentDevice.value?.device_type !== 'camera' && currentDevice.value?.device_type !== 'nvr') {
    ElMessage.warning('当前设备类型暂不支持画面预览')
    return
  }

  await startDevicePreview(currentDevice.value)
}

const handleSaveAreaConfig = async () => {
  if (!currentDevice.value?.device_id) return
  try {
    await saveAreaConfig(currentDevice.value.device_id, deviceApi)
    await reloadDevices()
  } catch (error) {
    ElMessage.error(error.message || '保存区域失败')
  }
}

const downloadSnapshot = (canvas) => {
  try {
    const image = canvas.toDataURL('image/png')
    const link = document.createElement('a')
    link.href = image
    link.download = `${currentDevice.value?.device_name || 'device'}_${new Date().toISOString().replace(/:/g, '-')}.png`
    link.click()
    ElMessage.success('截图已保存')
  } catch (error) {
    ElMessage.error('保存截图失败')
  }
}

const takeSnapshot = () => {
  const img = frameImageRef.value
  if (!img || !displayImage.value) {
    ElMessage.warning('当前没有可用画面，无法截图')
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = img.naturalWidth || img.clientWidth || 640
  canvas.height = img.naturalHeight || img.clientHeight || 480
  canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
  downloadSnapshot(canvas)
}

const retryPreview = async () => {
  if (currentDevice.value) {
    await refreshDevicePreview()
  }
}

const stopPreview = () => {
  stopDevicePreview()
  if (isFullscreen.value) {
    exitFullscreen()
  }
  teardownDrawing()
}

const toggleFullscreen = async () => {
  if (isFullscreen.value) {
    exitFullscreen()
    return
  }
  const el = previewWrapperRef.value
  if (!el?.requestFullscreen) {
    ElMessage.warning('当前浏览器不支持全屏')
    return
  }
  try {
    await el.requestFullscreen()
    isFullscreen.value = true
  } catch (error) {
    ElMessage.error(`进入全屏失败: ${error.message}`)
  }
}

const exitFullscreen = () => {
  if (document.fullscreenElement) {
    document.exitFullscreen?.()
  }
  isFullscreen.value = false
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  const date = new Date(dateTime)
  return date.toLocaleString('zh-CN')
}

// 获取设备类型名称
const getDeviceTypeName = (type) => {
  const typeMap = {
    'camera': '摄像头',
    'nvr': '硬盘录像机',
  }
  return typeMap[type] || type
}

// 获取设备类型标签样式
const getDeviceTypeTag = (type) => {
  const typeTagMap = {
    'camera': 'info',
    'nvr': 'success',
  }
  return typeTagMap[type] || 'info'
}

// 导入功能
const handleImport = () => {
  importDialogVisible.value = true
  importFile.value = null
}

const handleFileChange = (file) => {
  if (!file) return

  // 检查文件类型
  const validTypes = [
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv'
  ]

  if (!validTypes.includes(file.raw.type)) {
    ElMessage.error('请上传Excel或CSV格式的文件')
    return false
  }

  // 检查文件大小，不超过10MB
  const isLt10M = file.size / 1024 / 1024 < 10
  if (!isLt10M) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }

  importFile.value = file.raw
}

const submitImport = async () => {
  if (!importFile.value) {
    ElMessage.warning('请先选择要导入的文件')
    return
  }

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)

    const response = await deviceApi.importDevices(formData)

    if (response.status === 200) {
      ElMessage.success('导入成功')
      importDialogVisible.value = false
      reloadDevices()
    } else {
      ElMessage.error(`导入失败: ${response.data.detail || '未知错误'}`)
    }
  } catch (error) {
    // console.error('导入设备失败:', error)
    ElMessage.error(`导入失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    importing.value = false
  }
}

// 导出功能
const handleExport = async (command) => {
  try {
    let response
    let filename

    if (command === 'template') {
      // 导出模板
      response = await deviceApi.exportDeviceTemplate()
      filename = '设备导入模板.xlsx'
    } else if (command === 'data') {
      // 导出数据
      response = await deviceApi.exportDevices()
      filename = `设备数据_${new Date().toISOString().split('T')[0]}.xlsx`
    }

    // 处理文件下载
    if (response && response.data) {
      const blob = new Blob([response.data], {
        type: response.headers['content-type'] 
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      
      ElMessage.success('导出成功')
    }
  } catch (error) {
    // console.error('导出失败:', error)
    ElMessage.error(`导出失败: ${error.response?.data?.detail || error.message}`)
  }
}

// 筛选功能
const handleFilter = () => {
  treePage.value = 1
  isFiltering.value = hasActiveFilter()
  reloadDevices()
}

const handleResetFilter = () => {
  Object.assign(filterForm, {
    device_type: '',
    status: '',
    device_name: '',
    ip_address: '',
    location: '',
    area: ''
  })
  treePage.value = 1
  isFiltering.value = false
  reloadDevices()
}
</script>

<style scoped>
.devices-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.device-list {
  margin-bottom: 20px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-right {
  margin-left: auto;
}

.selection-tip {
  color: #606266;
  font-size: 13px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

.tree-pagination {
  margin-top: 16px;
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: min(52vh, 520px);
  min-height: 360px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.frame-dialog-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.video-placeholder {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: #909399;
}

.loading-wrapper {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 100%;
}

.loading-text {
  margin-top: 10px;
  color: #909399;
}

.error-wrapper {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  color: #f56c6c;
  gap: 10px;
}

.video-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
}

.video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background-color: #000;
  pointer-events: none;
  user-select: none;
}

.stream-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  background-color: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  pointer-events: none;
  z-index: 2;
}

.drawing-canvas {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 3;
  cursor: crosshair;
}

.preview-controls {
  margin-top: 15px;
  padding: 0 10px;
  display: flex;
  justify-content: flex-end;
}

.preview-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background-color: #000;
  pointer-events: none;
  user-select: none;
}

.upload-demo {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}

.el-upload__tip {
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}

.el-icon--upload {
  font-size: 48px;
  color: #409eff;
  margin-bottom: 10px;
}

.filter-section {
  margin-bottom: 20px;
  /* padding: 20px; */
  /* background-color: #f8f9fa; */
  border-radius: 8px;
  /* border: 1px solid #e9ecef; */
}

.filter-section .el-form {
  margin-bottom: 0;
}

.filter-section .el-form-item {
  margin-bottom: 0;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}

.preview-dialog {
  z-index: 100000 !important;
}

.import-dialog {
  z-index: 100001 !important;
}

/* 全屏样式 */
.video-player:fullscreen {
  object-fit: contain;
}

.video-player:-webkit-full-screen {
  object-fit: contain;
}

.video-player:-moz-full-screen {
  object-fit: contain;
}

.video-player:-ms-fullscreen {
  object-fit: contain;
}

/* 全屏按钮样式 */
.preview-controls .el-button {
  min-width: 80px;
}

/* 全屏时的图像显示 */
.fullscreen-image {
  max-width: 100vw;
  max-height: 100vh;
  object-fit: contain;
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.rtsp-form-hint {
  word-break: break-all;
}

.rtsp-form-hint > div + div {
  margin-top: 4px;
}

.text-muted {
  color: #909399;
  font-size: 12px;
}

.tree-layout {
  display: flex;
  gap: 16px;
  min-height: 520px;
}

.tree-panel {
  width: 260px;
  flex-shrink: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafbfc;
  padding: 12px;
}

.tree-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
  color: #303133;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  padding-right: 8px;
}

.tree-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-content {
  flex: 1;
  min-width: 0;
}

.tree-content-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.tree-content-title h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.tree-content-sub {
  color: #909399;
  font-size: 13px;
}

.card-grid-view {
  min-height: 200px;
}

.card-view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-view-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.group-card {
  margin-bottom: 16px;
  height: calc(100% - 16px);
}

.group-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.group-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #303133;
  min-width: 0;
}

.group-card-title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-card-icon {
  color: #409eff;
  flex-shrink: 0;
}

.group-card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.group-card-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 10px;
  line-height: 1.5;
}

.group-card-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 12px;
}

.group-card-stats .online {
  color: #67c23a;
}

.group-card-stats .offline {
  color: #f56c6c;
}

.group-device-list {
  max-height: 280px;
  overflow-y: auto;
}

.group-device-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f2f5;
}

.group-device-item:last-child {
  border-bottom: none;
}

.device-item-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.status-online {
  color: #67c23a;
  font-size: 18px;
}

.status-offline {
  color: #c0c4cc;
  font-size: 18px;
}

.device-item-info {
  min-width: 0;
}

.device-item-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-item-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-item-actions {
  flex-shrink: 0;
}

.group-create-form {
  margin-bottom: 16px;
}
</style>

<style>
.device-delete-messagebox .form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.delete-confirm-message {
  line-height: 1.6;
  color: #606266;
}

.device-delete-messagebox .delete-confirm-line {
  margin: 0 0 10px 0;
}

.device-delete-messagebox .delete-confirm-line:last-child {
  margin-bottom: 0;
}

.device-delete-messagebox .delete-confirm-tip {
  color: #909399;
  font-size: 13px;
}

.device-delete-messagebox .delete-confirm-label {
  color: #303133;
  font-weight: 500;
}
</style>
