<template>
  <div class="detection-config-page">
    <div class="page-header">
      <div class="header-content">
        <h2>检测配置管理</h2>
        <p>管理设备检测任务配置，支持筛选与状态统计</p>
      </div>
      <div class="header-actions">
        <el-button @click="reloadConfigList" :loading="loading">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="showAddModal">
          <el-icon>
            <Plus />
          </el-icon>
          创建配置
        </el-button>
      </div>
    </div>

    <!-- 配置统计 -->
    <div class="stats-cards">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#409EFF">
                <Setting />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ configStats.total_configs || 0 }}</div>
              <div class="stat-label">配置总数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#67C23A">
                <VideoPlay />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ configStats.enabled_configs || 0 }}</div>
              <div class="stat-label">已启用</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#909399">
                <VideoPause />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ configStats.disabled_configs || 0 }}</div>
              <div class="stat-label">已禁用</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#E6A23C">
                <Clock />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ configStats.manual_configs || 0 }}</div>
              <div class="stat-label">抽帧检测</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <el-card class="filter-section">
      <el-form :model="filterForm" inline>
        <el-form-item label="设备名称">
          <el-input
            v-model="filterForm.device_name"
            placeholder="请输入设备名称"
            clearable
            style="width: 180px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>

        <el-form-item label="模型">
          <el-select
            v-model="filterForm.models_id"
            placeholder="选择模型"
            style="width: 220px"
            filterable
            clearable
            teleported
          >
            <el-option
              v-for="model in filterModelList"
              :key="model.models_id"
              :label="`${model.models_name} (${getModelTypeName(model.models_type)})`"
              :value="model.models_id"
            />
            <template #empty>暂无模型，请先在模型管理上传</template>
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filterForm.enabled" placeholder="选择状态" style="width: 120px" clearable>
            <el-option :value="true" label="启用" />
            <el-option :value="false" label="禁用" />
          </el-select>
        </el-form-item>

        <el-form-item label="检测方式">
          <el-select v-model="filterForm.frequency" placeholder="选择方式" style="width: 140px" clearable>
            <el-option value="realtime" label="实时检测" />
            <el-option value="manual" label="抽帧检测" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-space>
            <el-button type="primary" @click="handleSearch">
              <el-icon>
                <Search />
              </el-icon>
              搜索
            </el-button>
            <el-button @click="handleResetFilter">
              <el-icon>
                <Refresh />
              </el-icon>
              重置
            </el-button>
          </el-space>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="main-card">
      <!-- 配置列表 -->
      <el-table :data="configList" v-loading="loading" style="width: 100%">
        <!-- 配置类型 / 设备 / 分组列 -->
        <el-table-column label="类型" prop="config_mode" min-width="80">
          <template #default="scope">
            <el-tag :type="scope.row.config_mode === 'group' ? 'warning' : 'info'" size="small">
              {{ scope.row.config_mode === 'group' ? '按分组' : '按设备' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="设备/分组" prop="device_id" sortable min-width="140">
          <template #default="scope">
            <span v-if="scope.row.config_mode === 'group'">
              {{ scope.row.group_name || scope.row.group_id || '-' }}
            </span>
            <span v-else>{{ getDeviceName(scope.row.device_id) }}</span>
          </template>
        </el-table-column>

        <!-- 模型名称列 -->
        <el-table-column label="模型" prop="models_id" min-width="140">
          <template #default="scope">
            {{ getModelName(scope.row.models_id) }}
          </template>
        </el-table-column>

        <!-- 目标类别列 -->
        <el-table-column label="目标类别" prop="target_classes" min-width="100">
          <template #default="scope">
            <div class="target-class-tags">
              <el-tag
                v-for="className in getTargetClassLabels(scope.row)"
                :key="className"
                size="small"
                type="primary"
                style="margin-right: 4px; margin-bottom: 4px;"
              >
                {{ className }}
              </el-tag>
              <span v-if="!getTargetClassLabels(scope.row).length" class="empty-text">-</span>
            </div>
          </template>
        </el-table-column>

        <!-- 状态列 -->
        <el-table-column label="状态" prop="enabled" min-width="80">
          <template #default="scope">
            <el-tag :type="scope.row.enabled ? 'success' : 'danger'">
              {{ scope.row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 灵敏度列 -->
        <el-table-column label="灵敏度" prop="sensitivity" min-width="80">
        </el-table-column>

        <!-- 检测方式列 -->
        <el-table-column label="检测方式" prop="frequency" min-width="100">
          <template #default="scope">
            <el-tag :type="getFrequencyType(scope.row.frequency)">
              {{ scope.row.config_mode === 'group' ? '分组轮询' : getFrequencyLabel(scope.row.frequency) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="运行时段" prop="schedule_config" min-width="120">
          <template #default="scope">
            {{ getScheduleDetail(scope.row) }}
          </template>
        </el-table-column>

        <!-- 保存模式列 -->
        <el-table-column label="保存模式" prop="save_mode" min-width="150">
          <template #default="scope">
            <el-tag :type="getSaveModeType(scope.row.save_mode)">
              {{ getSaveModeLabel(scope.row.save_mode, scope.row.max_storage_days) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 区域设置列 -->
        <el-table-column label="智能方案" prop="area_coordinates" min-width="150">
          <template #default="scope">
            <el-tag v-if="scope.row.config_mode === 'group'" type="info">不适用</el-tag>
            <el-tag v-else>
              {{ getAreaTypeLabel(scope.row.area_coordinates) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 推送标签列 -->
        <el-table-column label="推送标签" prop="pushLabel" min-width="100">
          <template #default="scope">
            <el-tag v-if="getPushLabel(scope.row.area_coordinates)" type="info" size="small">
              {{ getPushLabel(scope.row.area_coordinates) }}
            </el-tag>
            <span v-else class="empty-text">-</span>
          </template>
        </el-table-column>

        <!-- 更新时间列 -->
        <!-- <el-table-column label="更新时间" prop="updated_at" sortable min-width="150">
          <template #default="scope">
            {{ formatDateTime(scope.row.updated_at) }}
          </template>
        </el-table-column> -->

        <!-- 操作列 -->
        <el-table-column label="操作" min-width="230" fixed="right">
          <template #default="scope">
            <el-button-group>
              <el-button
                type="warning"
                size="small"
                @click="scope.row.enabled ? null : setInterestArea(scope.row)"
                :disabled="scope.row.enabled || scope.row.config_mode === 'group'"
              >
                智能
              </el-button>
              <el-button type="primary" size="small" @click="scope.row.enabled ? null : editConfig(scope.row)"
                :disabled="scope.row.enabled"> <!-- 禁用按钮 -->
                编辑
              </el-button>
              <el-button :type="scope.row.enabled ? 'danger' : 'success'" size="small"
                @click="toggleEnabled(scope.row)">
                {{ scope.row.enabled ? '禁用' : '启用' }}
              </el-button>
              <el-button type="danger" size="small" @click="handleDeleteConfig(scope.row)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination" v-if="totalCount > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="totalCount"
          layout="prev, pager, next, jumper, ->, total, sizes"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 添加/编辑配置的模态框 -->
    <el-dialog 
      v-model="modalVisible" 
      :title="isEdit ? '编辑检测配置' : '创建检测配置'" 
      width="920px"
      top="5vh" 
      destroy-on-close
      :z-index="999999"
      append-to-body
      class="config-dialog high-priority-dialog"
      :modal-append-to-body="false"
    >
      <el-form ref="formRef" :model="formState" :rules="rules" label-position="top" class="config-form">
        <el-tabs v-model="activeConfigTab" class="config-tabs">
          <el-tab-pane label="基本设置" name="basic">
            <div class="section-container">
              <div class="form-section">
                <div class="config-section-block">
                  <div class="config-section-title">配置类型</div>
                  <el-form-item label="检测范围" prop="config_mode" class="form-item">
                    <el-radio-group v-model="formState.config_mode" :disabled="isEdit" class="mode-radio-group">
                      <el-radio-button value="device">按设备</el-radio-button>
                      <el-radio-button value="group">按分组</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                </div>

                <div class="config-section-block">
                  <div class="config-section-title">{{ formState.config_mode === 'group' ? '分组与模型' : '设备与模型' }}</div>
                  <div class="form-grid">
                  <div class="form-row" v-if="formState.config_mode === 'device'">
                    <el-form-item label="设备" prop="device_id" class="form-item form-item-device">
                      <el-select
                        v-model="formState.device_id"
                        placeholder="请选择设备"
                        :disabled="isEdit"
                        filterable
                        popper-append-to-body
                        @change="handleDeviceChange"
                      >
                        <el-option v-for="device in deviceList" :key="device.device_id"
                          :label="`${device.device_name} (${device.device_id})`" :value="device.device_id">
                          <div class="device-option">
                            <el-icon>
                              <VideoCamera />
                            </el-icon>
                            <span>{{ device.device_name }}</span>
                            <span class="device-id">({{ device.device_id }})</span>
                          </div>
                        </el-option>
                      </el-select>
                    </el-form-item>

                    <el-form-item label="码流" prop="stream_type" class="form-item form-item-stream" v-if="formState.config_mode === 'device'">
                      <el-select v-model="formState.stream_type" placeholder="请选择码流" :disabled="!formState.device_id">
                        <el-option label="主码流" value="main" />
                        <el-option label="辅码流" value="sub" />
                      </el-select>
                    </el-form-item>
                  </div>

                  <div class="form-row" v-else>
                    <el-form-item label="设备分组" prop="group_id" class="form-item form-item-device">
                      <el-select
                        v-model="formState.group_id"
                        placeholder="请选择设备分组"
                        :disabled="isEdit"
                        filterable
                        popper-append-to-body
                      >
                        <el-option
                          v-for="group in deviceGroups"
                          :key="group.group_id"
                          :label="group.group_name"
                          :value="group.group_id"
                        />
                      </el-select>
                    </el-form-item>
                  </div>

                  <div class="form-row form-row-group-settings" v-if="formState.config_mode === 'group'">
                    <el-form-item label="主取帧方式" class="form-item">
                      <el-select v-model="formState.group_settings.frame_source_primary" placeholder="优先">
                        <el-option label="API 截图" value="snapshot" />
                        <el-option label="RTSP 单帧" value="rtsp" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="备用取帧" class="form-item">
                      <el-select v-model="formState.group_settings.frame_source_fallback" placeholder="备用">
                        <el-option label="API 截图" value="snapshot" />
                        <el-option label="RTSP 单帧" value="rtsp" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="设备间隔" class="form-item form-item-compact-number">
                      <div class="input-with-unit">
                        <el-input-number
                          v-model="formState.group_settings.device_interval_sec"
                          :min="0.2"
                          :max="3600"
                          :step="0.5"
                          :precision="1"
                          controls-position="right"
                        />
                        <span class="unit-label">秒/台</span>
                      </div>
                    </el-form-item>
                    <el-form-item label="整轮间隔" class="form-item form-item-compact-number">
                      <div class="input-with-unit">
                        <el-input-number
                          v-model="formState.group_settings.group_round_interval_sec"
                          :min="0"
                          :max="86400"
                          :step="1"
                          :precision="1"
                          controls-position="right"
                        />
                        <span class="unit-label">秒/轮</span>
                      </div>
                    </el-form-item>
                  </div>

                  <div class="form-row form-row-three">
                    <el-form-item label="检测模型" prop="models_id" class="form-item">
                      <el-select
                        v-model="formState.models_id"
                        placeholder="请选择检测模型"
                        @change="updateTargetClasses"
                        filterable
                        teleported
                        popper-class="config-model-select-popper"
                      >
                        <el-option v-for="model in modelList" :key="model.models_id"
                          :label="`${model.models_name} (${getModelTypeName(model.models_type)})`" :value="model.models_id">
                          <div class="model-option">
                            <span>{{ model.models_name }}</span>
                            <el-tag size="small" effect="plain">{{ getModelTypeName(model.models_type) }}</el-tag>
                          </div>
                        </el-option>
                      </el-select>
                    </el-form-item>

                    <el-form-item prop="target_classes" class="form-item form-item-classes">
                      <template #label>
                        <div class="form-item-label-row">
                          <span>目标类别</span>
                          <span v-if="targetClasses.length > 0" class="label-extra">
                            <el-button link size="small" @click.stop="selectAllClasses">全选</el-button>
                            <el-button link size="small" @click.stop="clearAllClasses" v-if="formState.target_classes.length > 0">清空</el-button>
                            <span class="selected-count">{{ formState.target_classes.length }}/{{ targetClasses.length }}</span>
                          </span>
                        </div>
                      </template>
                      <el-select v-model="formState.target_classes" multiple placeholder="请选择目标类别" collapse-tags
                        collapse-tags-tooltip :max-collapse-tags="2" filterable popper-append-to-body>
                        <el-option v-for="classItem in targetClasses" :key="classItem.value" :label="classItem.label"
                          :value="classItem.value">
                          <div class="class-option">
                            <span>{{ classItem.label }}</span>
                            <span class="class-id">{{ classItem.value }}</span>
                          </div>
                        </el-option>
                      </el-select>
                    </el-form-item>

                    <el-form-item label="置信度阈值" prop="sensitivity" class="form-item sensitivity-item">
                      <div class="sensitivity-control">
                        <el-input-number
                          v-model="formState.sensitivity"
                          :min="0.1"
                          :max="0.9"
                          :step="0.05"
                          :precision="2"
                          controls-position="right"
                          class="sensitivity-input"
                        />
                        <div class="sensitivity-presets">
                          <button
                            v-for="preset in sensitivityPresets"
                            :key="preset.value"
                            type="button"
                            class="sensitivity-preset"
                            :class="{ active: isSensitivityPresetActive(preset.value) }"
                            @click="formState.sensitivity = preset.value"
                          >
                            {{ preset.label }}
                          </button>
                        </div>
                      </div>
                    </el-form-item>
                  </div>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="运行策略" name="runtime">
            <div class="section-container">
              <div class="form-section">
                <div class="config-section-block" v-if="formState.config_mode === 'device'">
                  <div class="config-section-title">检测调度</div>
                  <div class="runtime-panel">
                    <div class="runtime-mode-row">
                      <el-form-item label="检测方式" prop="frequency" class="runtime-mode-item">
                        <el-radio-group v-model="formState.frequency" class="mode-radio-group">
                          <el-radio-button value="realtime">实时检测</el-radio-button>
                          <el-radio-button value="manual">抽帧检测</el-radio-button>
                        </el-radio-group>
                      </el-form-item>
                      <el-form-item
                        v-if="formState.frequency === 'manual'"
                        label="抽帧间隔"
                        class="runtime-interval-item"
                      >
                        <div class="input-with-unit">
                          <el-input-number
                            v-model="formState.frameInterval"
                            :min="1"
                            :max="3600"
                            :step="1"
                            controls-position="right"
                          />
                          <span class="unit-label">秒 / 帧</span>
                        </div>
                      </el-form-item>
                    </div>
                    <el-form-item label="生效时段" class="runtime-schedule-item">
                      <WeeklyTimeSchedule v-model="formState.weeklySchedule" />
                    </el-form-item>
                  </div>
                </div>

                <div class="config-section-block" v-else>
                  <div class="config-section-title">分组轮询</div>
                  <div class="runtime-panel">
                    <el-alert
                      type="info"
                      :closable="false"
                      show-icon
                      title="实时轮询：依次对组内每台摄像头取一帧并执行普通检测。"
                    />
                    <el-form-item label="生效时段" class="runtime-schedule-item" style="margin-top: 16px">
                      <WeeklyTimeSchedule v-model="formState.weeklySchedule" />
                    </el-form-item>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="保存设置" name="save">
            <div class="section-container">
              <div class="form-section">
                <div class="config-section-block">
                  <div class="config-section-title">事件保存</div>
                  <el-form-item label="保存模式" prop="save_mode" class="grid-item full-width">
                  <el-radio-group v-model="formState.save_mode">
                    <el-radio-button value="none">不保存</el-radio-button>
                    <el-radio-button value="screenshot">截图</el-radio-button>
                    <el-radio-button value="video">视频</el-radio-button>
                    <el-radio-button value="both">截图+视频</el-radio-button>
                  </el-radio-group>
                </el-form-item>

                <div v-if="formState.save_mode !== 'none'" class="save-card">
                  <div class="card-content save-options-grid">
                    <el-form-item label="视频片段时长" prop="save_duration" v-if="formState.save_mode !== 'screenshot'">
                      <div class="input-with-unit">
                        <el-input-number v-model="formState.save_duration" :min="5" :max="60" :step="5"
                          controls-position="right"></el-input-number>
                        <span class="unit-label">秒</span>
                      </div>
                    </el-form-item>

                    <el-form-item label="事件保留天数" prop="max_storage_days">
                      <div class="input-with-unit">
                        <el-input-number v-model="formState.max_storage_days" :min="1" :max="90" :step="1"
                          controls-position="right"></el-input-number>
                        <span class="unit-label">天</span>
                      </div>
                    </el-form-item>
                  </div>
                </div>
                </div>

                <div v-if="formState.config_mode === 'device'" class="config-section-block">
                  <div class="config-section-title">事件推送</div>
                  <p class="section-hint">智能方案命中及检测事件推送时使用，须与数据推送配置中的 tags 匹配</p>
                  <div class="save-options-grid">
                    <el-form-item label="推送标签" class="grid-item">
                      <el-select
                        v-model="formState.pushLabel"
                        filterable
                        allow-create
                        default-first-option
                        clearable
                        placeholder="选择或输入推送标签"
                        class="w-full"
                      >
                        <el-option v-for="tag in pushTagOptions" :key="tag" :label="tag" :value="tag" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="推送间隔" class="grid-item">
                      <div class="input-with-unit">
                        <el-input-number
                          v-model="formState.alarm_interval"
                          :min="0"
                          :max="3600"
                          controls-position="right"
                        />
                        <span class="unit-label">秒</span>
                      </div>
                      <!-- <div class="field-hint">0 表示不限制间隔；大于 0 为同类告警冷却时间</div> -->
                    </el-form-item>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-form>

      <template #footer>
        <div class="dialog-footer-simple">
          <el-button @click="cancelModal" :disabled="submitLoading">取消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitLoading">
            {{ isEdit ? '保存修改' : '创建配置' }}
          </el-button>
        </div>
      </template>
    </el-dialog>


  </div>
</template>

<script>
import { defineComponent, ref, reactive, onMounted, h, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Delete, Edit, VideoPause, VideoPlay, Operation, CircleCloseFilled, Files, VideoCamera, CircleCheckFilled, Clock, Setting, CircleClose, Search, Refresh } from '@element-plus/icons-vue';
import deviceApi from '@/api/device'
import dayjs from 'dayjs';
import { detectionConfigApi } from '@/api/detection';
import { startDetection, stopDetection } from '@/api/detection_server';
import WeeklyTimeSchedule from '@/components/WeeklyTimeSchedule.vue';
import {
  createFullWeekSchedule,
  formatScheduleSummary,
  isFullWeekSchedule,
  legacyRuntimeToSchedule,
  scheduleFromBackend,
  scheduleToBackend
} from '@/utils/weeklySchedule';
import { getScenarioSummaryLabel } from '@/utils/smartScenarios';
import { usePushConfigTags } from '@/composables/usePushConfigTags';
import { DEFAULT_SMART_SCHEME_PUSH_TAG } from '@/constants/pushTags';

export default defineComponent({
  name: 'DetectionConfig',
  components: {
    Plus,
    Delete,
    Edit,
    VideoPause,
    VideoPlay,
    Operation,
    CircleCloseFilled,
    Files,
    VideoCamera,
    CircleCheckFilled,
    Clock,
    Setting,
    CircleClose,
    Search,
    Refresh,
    WeeklyTimeSchedule
  },
  setup() {
    const router = useRouter();
    const { pushTagOptions, loadPushConfigTags } = usePushConfigTags();

    // 数据加载状态
    const loading = ref(false);
    const submitLoading = ref(false);

    // 表格数据
    const configList = ref([]);
    const deviceList = ref([]);
    const deviceGroups = ref([]);
    const modelList = ref([]);
    const filterModelList = ref([]);
    const targetClasses = ref([]); // 用于存储目标类别

    // 分页相关
    const currentPage = ref(1);
    const pageSize = ref(20);
    const totalCount = ref(0);

    // 筛选相关
    const filterForm = reactive({
      device_name: '',
      models_id: '',
      enabled: '',
      frequency: ''
    });
    const isFiltering = ref(false);

    const configStats = ref({
      total_configs: 0,
      enabled_configs: 0,
      disabled_configs: 0,
      manual_configs: 0,
      realtime_configs: 0
    });

    const hasActiveFilter = () => {
      return Object.entries(filterForm).some(([_, value]) => value !== '' && value !== null && value !== undefined);
    };

    const buildConfigQueryParams = () => {
      const params = {
        skip: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value
      };

      if (filterForm.device_name?.trim()) {
        params.device_name = filterForm.device_name.trim();
      }
      if (filterForm.models_id) {
        params.models_id = filterForm.models_id;
      }
      if (filterForm.enabled !== '' && filterForm.enabled !== null && filterForm.enabled !== undefined) {
        params.enabled = filterForm.enabled;
      }
      if (filterForm.frequency) {
        params.frequency = filterForm.frequency;
      }

      return params;
    };

    // 模态框状态
    const modalVisible = ref(false);
    const isEdit = ref(false);
    const formRef = ref(null);

    // 设置感兴趣区域方法（跳转到新页面）
    const setInterestArea = (config) => {
      router.push({
        name: 'SmartConfigSetting',
        params: {
          configId: config.config_id
        },
        query: {
          deviceId: config.device_id
        }
      });
    };

    // 表单状态
    const formState = reactive({
      config_id: null,
      config_mode: 'device',
      device_id: null,
      group_id: null,
      group_settings: {
        frame_source_primary: 'snapshot',
        frame_source_fallback: 'rtsp',
        device_interval_sec: 1.0,
        group_round_interval_sec: 0
      },
      stream_type: 'main',
      models_id: null,
      enabled: true,
      sensitivity: 0.5,
      target_classes: [],
      frequency: 'realtime',
      save_mode: 'none',
      save_duration: 10,
      max_storage_days: 30,
      pushLabel: DEFAULT_SMART_SCHEME_PUSH_TAG,
      alarm_interval: 15,
      frameInterval: 5,
      weeklySchedule: createFullWeekSchedule()
    });

    const editingAreaCoordinates = ref(null);

    const smartSchemeSummary = computed(() => {
      if (!editingAreaCoordinates.value) return '已配置';
      return getAreaTypeLabel(editingAreaCoordinates.value);
    });

    const buildInferencePipeline = () => ({ mode: 'yolo_only' });

    const applyInferencePipeline = () => {};

    const resetPushSettings = () => {
      formState.pushLabel = DEFAULT_SMART_SCHEME_PUSH_TAG;
      formState.alarm_interval = 15;
    };

    const applyPushSettings = (areaCoordinates) => {
      formState.pushLabel = areaCoordinates?.pushLabel || DEFAULT_SMART_SCHEME_PUSH_TAG;
      formState.alarm_interval = areaCoordinates?.alarm_interval ?? 15;
    };

    const buildAreaCoordinatesForSubmit = () => {
      const base = editingAreaCoordinates.value
        ? { ...editingAreaCoordinates.value }
        : { version: 2, scenarios: [] };
      return {
        ...base,
        version: base.version ?? 2,
        scenarios: Array.isArray(base.scenarios) ? base.scenarios : [],
        pushLabel: (formState.pushLabel || '').trim(),
        alarm_interval: formState.alarm_interval ?? 15,
      };
    };

    const resetRuntimeDefaults = () => {
      formState.frameInterval = 5;
      formState.weeklySchedule = createFullWeekSchedule();
    };

    const buildRuntimeConfig = () => {
      const isAllTime = isFullWeekSchedule(formState.weeklySchedule);
      const runtime = {
        frame_interval: formState.frameInterval,
        time_period_mode: isAllTime ? 'all' : 'weekly'
      };
      if (!isAllTime) {
        runtime.weekly_schedule = scheduleToBackend(formState.weeklySchedule);
      }
      return runtime;
    };

    const applyRuntimeConfig = (scheduleConfig) => {
      const runtime = scheduleConfig?.runtime || {};
      formState.frameInterval = runtime.frame_interval ?? 5;
      if (runtime.time_period_mode === 'weekly' && runtime.weekly_schedule) {
        formState.weeklySchedule = scheduleFromBackend(runtime.weekly_schedule);
      } else {
        formState.weeklySchedule = legacyRuntimeToSchedule(runtime);
      }
    };

    // 格式化日期时间
    const formatDateTime = (dateStr) => {
      if (!dateStr) return '';
      return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss');
    };

    const formatSensitivity = (value) => `${Math.round(value * 100)}%`;

    const sensitivityPresets = [
      { label: '低', value: 0.3 },
      { label: '中', value: 0.5 },
      { label: '高', value: 0.7 }
    ];

    const isSensitivityPresetActive = (value) => Math.abs(formState.sensitivity - value) < 0.001;

    const syncStreamFromDevice = (deviceId) => {
      const device = deviceList.value.find(d => d.device_id === deviceId);
      if (!isEdit.value) {
        formState.stream_type = device?.stream_type || 'main';
      }
    };

    const handleDeviceChange = (deviceId) => {
      syncStreamFromDevice(deviceId);
    };

    // 步骤控制
    const activeConfigTab = ref('basic');

    // 表单校验规则
    const rules = {
      device_id: [{ required: true, message: '请选择设备', trigger: 'change' }],
      models_id: [{ required: true, message: '请选择检测模型', trigger: 'change' }],
      sensitivity: [{ required: true, message: '请设置检测灵敏度', trigger: 'change' }],
      frequency: [{ required: true, message: '请选择检测方式', trigger: 'change' }],
      save_mode: [{ required: true, message: '请选择保存模式', trigger: 'change' }]
    };

    // 更新目标类别
    const updateTargetClasses = (modelId, options = {}) => {
      const { preserveSelection = false } = options;
      const selectedModel = modelList.value.find(model => model.models_id === modelId);

      if (selectedModel && selectedModel.models_classes) {
        targetClasses.value = Object.entries(selectedModel.models_classes).map(([key, name]) => ({
          label: name,
          value: key
        }));

        if (!preserveSelection) {
          formState.target_classes = targetClasses.value.length > 0
            ? [targetClasses.value[0].value]
            : [];
        }
      } else {
        targetClasses.value = [];
        if (!preserveSelection) {
          formState.target_classes = [];
        }
      }
    }

    // 获取模型类型名称
    const getModelTypeName = (type) => {
      const typeMap = {
        'object_detection': '目标检测',
        'smart_behavior': '智能行为',
        'smart_person': '人员场景',
        'smart_counting': '智能人数统计',
        'segmentation': '图像分割',
        'keypoint': '关键点检测',
        'pose': '姿态估计',
        'face': '人脸识别',
        'other': '其他类型'
      }
      return typeMap[type] || type
    }

    const getAreaTypeLabel = (areaCoordinates) => {
      if (!areaCoordinates || Object.keys(areaCoordinates).length === 0) {
        return '未设置';
      }

      if (areaCoordinates.version === 2 || Array.isArray(areaCoordinates.scenarios)) {
        return getScenarioSummaryLabel(areaCoordinates);
      }

      let result = '';

      // 根据分析类型确定主要描述
      if (areaCoordinates.analysisType === 'behavior') {
        result = '行为分析';
        if (areaCoordinates.behaviorType === 'area') {
          result += '-区域检测';
        } else if (areaCoordinates.behaviorType === 'line') {
          result += '-拌线检测';
        }

        if (areaCoordinates.behaviorSubtype === 'directional') {
          const directionText = areaCoordinates.behaviorDirection === 'in' ? '进入' : '离开';
          result += `(${directionText})`;
        }
      } else if (areaCoordinates.analysisType === 'counting') {
        result = '人数统计';
        if (areaCoordinates.countingType === 'occupancy') {
          result += '-区域统计';
        } else if (areaCoordinates.countingType === 'flow') {
          result += '-人流统计';
        }
      } else {
        result = '无智能方案';
      }

      return result;
    }

    // 获取设备名称
    const getDeviceName = (deviceId) => {
      const device = deviceList.value.find(d => d.device_id === deviceId);
      return device ? device.device_name : deviceId;
    };

    // 获取模型名称
    const getModelName = (modelId) => {
      const model = modelList.value.find(m => m.models_id === modelId);
      return model ? model.models_name : modelId;
    };

    const getTargetClassLabels = (record) => {
      const classes = record?.target_classes || [];
      if (!classes.length) return [];

      const model = modelList.value.find(m => m.models_id === record.models_id);
      const classMap = model?.models_classes || {};

      return classes.map((classKey) => classMap[classKey] || classKey);
    };

    const getPushLabel = (areaCoordinates) => {
      const label = areaCoordinates?.pushLabel;
      return typeof label === 'string' ? label.trim() : '';
    };

    // 获取频率标签
    const getFrequencyLabel = (frequency) => {
      const map = {
        realtime: '实时检测',
        scheduled: '定时检测(已废弃)',
        manual: '抽帧检测'
      };
      return map[frequency] || frequency;
    };

    const getFrequencyType = (frequency) => {
      const map = {
        realtime: 'success',
        scheduled: 'warning',
        manual: 'info'
      };
      return map[frequency] || '';
    };

    const getScheduleDetail = (row) => {
      const runtime = row.schedule_config?.runtime;
      if (!runtime) {
        if (row.frequency === 'scheduled') {
          return '请编辑并改为实时/抽帧检测';
        }
        return row.frequency === 'manual' ? '全时段' : '';
      }

      const parts = [];
      if (row.frequency === 'manual' && runtime.frame_interval) {
        parts.push(`${runtime.frame_interval}秒/帧`);
      }
      if (runtime.time_period_mode === 'all') {
        parts.push('全时段');
      } else if (runtime.time_period_mode === 'weekly' && runtime.weekly_schedule) {
        parts.push(formatScheduleSummary(scheduleFromBackend(runtime.weekly_schedule)));
      } else if (runtime.time_period_mode === 'day_night') {
        const scopeMap = { day: '仅白天', night: '仅夜晚', both: '白天+夜晚' };
        parts.push(scopeMap[runtime.day_night_scope] || '白天/夜晚');
      } else if (runtime.time_period_mode === 'custom' && runtime.custom_ranges?.length) {
        parts.push(`自定义 ${runtime.custom_ranges.map(item => `${item.start}-${item.end}`).join(', ')}`);
      }
      return parts.join(' · ');
    };

    // 获取保存模式标签
    const getSaveModeLabel = (saveMode, maxStorageDays) => {
      const map = {
        'none': '暂无',
        'screenshot': '截图(' + maxStorageDays + '天)',
        'video': '视频(无)',
        'both': '截图(' + maxStorageDays + '天)' + '|' + '视频(无)'
      };
      return map[saveMode] || saveMode;
    };

    // 获取保存模式标签类型
    const getSaveModeType = (saveMode) => {
      const map = {
        'none': 'info',
        'screenshot': 'success',
        'video': 'warning',
        'both': 'danger'
      };
      return map[saveMode] || '';
    };

    // 加载配置统计
    const loadConfigStats = async () => {
      try {
        const response = await detectionConfigApi.getConfigsStatsOverview();
        if (response.data.status === 'success') {
          configStats.value = {
            ...configStats.value,
            ...(response.data.data || {})
          };
        }
      } catch (error) {
        configStats.value = {
          total_configs: 0,
          enabled_configs: 0,
          disabled_configs: 0,
          manual_configs: 0,
          realtime_configs: 0
        };
      }
    };

    // 加载配置列表
    const loadConfigList = async () => {
      loading.value = true;
      try {
        const response = await detectionConfigApi.getConfigs(buildConfigQueryParams());

        configList.value = response.data.data;
        totalCount.value = response.data.total;
      } catch (error) {
        ElMessage.error('获取配置列表失败: ' + error.message);
      } finally {
        loading.value = false;
      }
    };

    const reloadConfigList = async () => {
      await Promise.all([loadConfigList(), loadConfigStats()]);
    };

    const handleSearch = () => {
      currentPage.value = 1;
      isFiltering.value = hasActiveFilter();
      loadConfigList();
    };

    const handleResetFilter = () => {
      Object.assign(filterForm, {
        device_name: '',
        models_id: '',
        enabled: '',
        frequency: ''
      });
      currentPage.value = 1;
      isFiltering.value = false;
      loadConfigList();
    };

    // 加载设备列表
    const loadDeviceList = async () => {
      try {
        const response = await deviceApi.getDevices();
        deviceList.value = response.data.data;
      } catch (error) {
        ElMessage.error('获取设备列表失败: ' + error.message);
      }
    };

    const normalizeModelList = (payload) => {
      if (Array.isArray(payload)) return payload;
      if (Array.isArray(payload?.data)) return payload.data;
      return [];
    };

    const isDetectionModel = (model) => (model?.models_type || '').toLowerCase() !== 'vlm';

    // 加载模型列表
    const loadModelList = async () => {
      try {
        const response = await deviceApi.getModels();
        const allModels = normalizeModelList(response?.data).filter(isDetectionModel);
        filterModelList.value = allModels;
        // 配置表单优先展示可用模型；若无激活模型则展示全部，避免下拉为空
        const activeModels = allModels.filter((model) => model.is_active !== false);
        modelList.value = activeModels.length ? activeModels : allModels;
      } catch (error) {
        filterModelList.value = [];
        modelList.value = [];
        ElMessage.error('获取模型列表失败: ' + (error.message || '请确认 data_server 已启动'));
      }
    };

    const loadDeviceGroups = async () => {
      try {
        const response = await deviceApi.getDeviceGroups();
        deviceGroups.value = response.data?.data || [];
      } catch (error) {
        ElMessage.error('获取设备分组失败: ' + error.message);
      }
    };

    // 初始化
    onMounted(() => {
      loadDeviceList();
      loadDeviceGroups();
      loadModelList();
      loadPushConfigTags();
      reloadConfigList();
    });

    // 显示添加模态框
    const showAddModal = async () => {
      isEdit.value = false;
      activeConfigTab.value = 'basic';
      resetForm();
      await loadModelList();
      modalVisible.value = true;
    };

    // 重置表单
    const resetForm = () => {
      Object.assign(formState, {
        config_id: null,
        config_mode: 'device',
        device_id: null,
        group_id: null,
        group_settings: {
          frame_source_primary: 'snapshot',
          frame_source_fallback: 'rtsp',
          device_interval_sec: 1.0,
          group_round_interval_sec: 0
        },
        stream_type: 'main',
        models_id: null,
        enabled: false,
        sensitivity: 0.5,
        target_classes: [],
        frequency: 'realtime',
        save_mode: 'none',
        save_duration: 10,
        max_storage_days: 30
      });
      resetRuntimeDefaults();
      resetPushSettings();
      editingAreaCoordinates.value = null;

      if (formRef.value) {
        formRef.value.clearValidate();
        // formRef.value.resetFields();
      }
    };

    // 编辑配置
    const editConfig = async (record) => {
      isEdit.value = true;
      activeConfigTab.value = 'basic';
      await loadModelList();

      const frequency = record.frequency === 'scheduled' ? 'realtime' : record.frequency;
      applyRuntimeConfig(record.schedule_config);
      applyInferencePipeline();
      editingAreaCoordinates.value = record.area_coordinates || null;
      applyPushSettings(record.area_coordinates);

      Object.assign(formState, {
        config_id: record.config_id,
        config_mode: record.config_mode || 'device',
        device_id: record.device_id,
        group_id: record.group_id,
        group_settings: {
          frame_source_primary: record.group_settings?.frame_source_primary || 'snapshot',
          frame_source_fallback: record.group_settings?.frame_source_fallback || 'rtsp',
          device_interval_sec: record.group_settings?.device_interval_sec ?? 1.0,
          group_round_interval_sec: record.group_settings?.group_round_interval_sec ?? 0
        },
        stream_type: record.stream_type || deviceList.value.find(d => d.device_id === record.device_id)?.stream_type || 'main',
        models_id: record.models_id,
        enabled: record.enabled,
        sensitivity: record.sensitivity,
        target_classes: record.target_classes || [],
        frequency,
        save_mode: record.save_mode,
        save_duration: record.save_duration,
        max_storage_days: record.max_storage_days
      });

      if (record.frequency === 'scheduled') {
        ElMessage.warning('该配置原为定时检测，已按实时检测打开，请确认生效时段后保存');
      }

      updateTargetClasses(record.models_id, { preserveSelection: true });
      modalVisible.value = true;
    };

    // 提交表单
    const submitForm = async () => {
      if (formRef.value) {
        await formRef.value.validate(async (valid, fields) => {
          if (valid) {
            submitLoading.value = true;

            try {
              // 准备提交的数据
              const submitData = {
                models_id: formState.models_id,
                enabled: false,
                sensitivity: formState.sensitivity,
                target_classes: formState.target_classes,
                save_mode: formState.save_mode,
                save_duration: formState.save_duration,
                max_storage_days: formState.max_storage_days,
                schedule_config: {
                  runtime: buildRuntimeConfig(),
                  inference_pipeline: buildInferencePipeline()
                }
              };

              if (formState.config_mode === 'group') {
                submitData.config_mode = 'group';
                submitData.group_id = formState.group_id;
                submitData.group_settings = { ...formState.group_settings };
                submitData.frequency = 'realtime';
              } else {
                submitData.config_mode = 'device';
                submitData.frequency = formState.frequency;
                submitData.stream_type = formState.stream_type;
                submitData.area_coordinates = buildAreaCoordinatesForSubmit();
              }

              if (isEdit.value) {
                if (formState.config_mode === 'group') {
                  submitData.group_settings = { ...formState.group_settings };
                }
                await detectionConfigApi.updateConfig(formState.config_id, submitData);
                ElMessage.success('配置更新成功');
              } else {
                submitData.config_mode = formState.config_mode;
                if (formState.config_mode === 'group') {
                  submitData.group_id = formState.group_id;
                  submitData.group_settings = { ...formState.group_settings };
                  submitData.frequency = 'realtime';
                } else {
                  submitData.device_id = formState.device_id;
                  submitData.stream_type = formState.stream_type;
                  submitData.frequency = formState.frequency;
                  submitData.area_coordinates = buildAreaCoordinatesForSubmit();
                }
                await detectionConfigApi.createConfig(submitData);
                ElMessage.success('配置创建成功');
              }

              modalVisible.value = false;
              reloadConfigList();
            } catch (error) {
              ElMessage.error('提交失败: ' + error.message);
            } finally {
              submitLoading.value = false;
            }
          } else {
            if (formState.config_mode === 'group' && !formState.group_id) {
              activeConfigTab.value = 'basic';
            } else if (formState.config_mode === 'device' && (!formState.device_id || !formState.models_id)) {
              activeConfigTab.value = 'basic';
            } else {
              activeConfigTab.value = 'save';
            }
            ElMessage.error('请完善表单信息');
          }
        });
      }
    };

    // 取消模态框
    const cancelModal = () => {
      modalVisible.value = false;
      isEdit.value = false;
    };

    // 切换启用状态
    const toggleEnabled = async (record) => {
      try {
        if (!record.enabled) {
          // 启动任务
          const response = await startDetection(record.config_id)
          if (response.status === 'success') {
            ElMessage.success('检测任务已启动')
          } else {
            ElMessage.error(response.message || '启动任务失败')
          }
        } else {
          // 停止任务
          const response = await stopDetection(record.config_id)
          if (response.status === 'success') {
            ElMessage.success('检测任务已停止')
          } else {
            ElMessage.error(response.message || '停止任务失败')
          }
        }
        reloadConfigList();
      } catch (error) {
        ElMessage.error('操作失败: ' + error.message);
      }
    };

    const buildDeleteConfirmMessage = (record) => {
      const targetLabel = record.config_mode === 'group'
        ? (record.group_name || record.group_id || '分组')
        : getDeviceName(record.device_id);
      const modelName = getModelName(record.models_id);

      return h('div', { class: 'delete-confirm-message' }, [
        h('p', { class: 'delete-confirm-line' }, '确认删除以下检测配置及其关联数据吗？'),
        h('p', { class: 'delete-confirm-line delete-confirm-tip' }, '关联数据包括：检测事件、检测日志、性能记录配置等。'),
        h('p', { class: 'delete-confirm-line delete-confirm-devices' }, [
          h('span', { class: 'delete-confirm-label' }, record.config_mode === 'group' ? '分组：' : '设备：'),
          h('span', targetLabel)
        ]),
        h('p', { class: 'delete-confirm-line delete-confirm-devices' }, [
          h('span', { class: 'delete-confirm-label' }, '模型：'),
          h('span', modelName)
        ])
      ]);
    };

    const showDeleteConfirm = (record) => {
      return ElMessageBox.confirm(
        buildDeleteConfirmMessage(record),
        '删除确认',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          type: 'warning',
          customClass: 'config-delete-messagebox'
        }
      );
    };

    const handleDeleteConfig = (record) => {
      showDeleteConfirm(record).then(async () => {
        try {
          await detectionConfigApi.deleteConfig(record.config_id);
          ElMessage.success('配置删除成功');
          reloadConfigList();
        } catch (error) {
          ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
        }
      }).catch(() => { });
    };

    // 目标类别选择辅助方法
    const selectAllClasses = () => {
      formState.target_classes = targetClasses.value.map(item => item.value);
    };

    const clearAllClasses = () => {
      formState.target_classes = [];
    };

    // 分页处理方法
    const handleSizeChange = (val) => {
      pageSize.value = val;
      loadConfigList();
    };

    const handleCurrentChange = (val) => {
      currentPage.value = val;
      loadConfigList();
    };

    return {
      router,
      getAreaTypeLabel,
      loading,
      submitLoading,
      configList,
      deviceList,
      deviceGroups,
      modelList,
      filterModelList,
      smartSchemeSummary,
      modalVisible,
      isEdit,
      formRef,
      formState,
      pushTagOptions,
      rules,
      targetClasses,
      formatDateTime,
      formatSensitivity,
      sensitivityPresets,
      isSensitivityPresetActive,
      handleDeviceChange,
      setInterestArea,
      updateTargetClasses,
      getModelTypeName,
      getDeviceName,
      getModelName,
      getTargetClassLabels,
      getPushLabel,
      getFrequencyLabel,
      getFrequencyType,
      getSaveModeLabel,
      getSaveModeType,
      showAddModal,
      editConfig,
      submitForm,
      cancelModal,
      toggleEnabled,
      handleDeleteConfig,
      getScheduleDetail,
      selectAllClasses,
      clearAllClasses,
      activeConfigTab,
      // 分页相关
      currentPage,
      pageSize,
      totalCount,
      configStats,
      filterForm,
      handleSearch,
      handleResetFilter,
      reloadConfigList,
      handleSizeChange,
      handleCurrentChange
    };
  }
});
</script>

<style scoped>
.detection-config-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-content p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.stats-cards {
  margin-bottom: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: white;
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
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

.filter-section {
  margin-bottom: 20px;
  border-radius: 8px;
}

.filter-section .el-form {
  margin-bottom: 0;
}

.filter-section .el-form-item {
  margin-bottom: 0;
}

.main-card {
  margin-bottom: 20px;
}

.form-item-container {
  display: flex;
  justify-content: flex-start;
  gap: 20px;
}

.form-item-left {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 10px;
}

/* 基础样式 */
.divider-title {
  font-size: 16px;
  font-weight: 500;
  color: #409EFF;
}

.form-section {
  margin-bottom: 20px;
  padding: 5px 0;
}

.form-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.form-row-three {
  align-items: flex-start;
}

.form-row-three .form-item {
  flex: 1;
  min-width: 0;
  margin-bottom: 0;
}

.form-row-three .form-item-classes {
  flex: 1.2;
}

.form-row-three .sensitivity-item {
  flex: 0 0 240px;
  max-width: 260px;
}

.form-row-group-settings {
  flex-wrap: nowrap;
  align-items: flex-start;
}

.form-row-group-settings .form-item {
  flex: 1;
  min-width: 0;
  margin-bottom: 0;
}

.form-row-group-settings .form-item-compact-number {
  flex: 0 0 148px;
  max-width: 160px;
}

.form-row-group-settings .input-with-unit {
  flex-wrap: nowrap;
}

.form-row-group-settings .input-with-unit .el-input-number {
  width: 100%;
}

.form-row-group-settings .unit-label {
  white-space: nowrap;
  font-size: 12px;
}

.form-item-device {
  flex: 1;
  min-width: 280px;
  margin-bottom: 0;
}

.form-item-stream {
  flex: 0 0 160px;
  max-width: 180px;
  margin-bottom: 0;
}

.form-item-small {
  flex: 1;
  min-width: 180px;
  margin-bottom: 0;
}

.form-item-large {
  flex: 2;
  min-width: 300px;
  margin-bottom: 0;
}

.form-item {
  flex: 1;
  min-width: 220px;
  margin-bottom: 0;
}

.full-width {
  width: 100%;
}

.input-with-unit {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unit-label {
  color: #606266;
  font-size: 14px;
}

.unit-label-prefix {
  color: #606266;
  font-size: 14px;
  margin-right: 2px;
}

/* 灵敏度控件 */
.sensitivity-item :deep(.el-form-item__content) {
  width: 100%;
}

.sensitivity-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.sensitivity-input {
  width: 100%;
}

.sensitivity-input :deep(.el-input-number) {
  width: 100%;
}

.sensitivity-input :deep(.el-input__wrapper) {
  min-height: 32px;
  box-sizing: border-box;
}

.sensitivity-presets {
  display: flex;
  gap: 4px;
  width: 100%;
}

.sensitivity-preset {
  flex: 1;
  min-width: 0;
  border: 1px solid #dcdfe6;
  background: #fff;
  color: #606266;
  border-radius: 4px;
  padding: 0 4px;
  height: 28px;
  line-height: 26px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.sensitivity-preset:hover {
  color: #409eff;
  border-color: #c6e2ff;
}

.sensitivity-preset.active {
  color: #409eff;
  border-color: #409eff;
  background: #ecf5ff;
  font-weight: 500;
}

/* 目标类别标签行 */
.form-item-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}

.label-extra {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-weight: normal;
}

.label-extra .selected-count {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

/* 配置分区 */
.config-section-block {
  margin-bottom: 20px;
}

.config-section-block:last-child {
  margin-bottom: 0;
}

.config-section-title {
  margin-bottom: 14px;
  padding-left: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  line-height: 1;
  border-left: 3px solid #409eff;
}

.runtime-panel {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fcfcfd;
}

.runtime-mode-row {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 16px 24px;
  margin-bottom: 16px;
}

.runtime-mode-item,
.runtime-interval-item {
  margin-bottom: 0;
}

.runtime-mode-item :deep(.el-form-item__content),
.runtime-interval-item :deep(.el-form-item__content) {
  line-height: 32px;
}

.mode-radio-group {
  flex-wrap: nowrap;
}

.runtime-schedule-item {
  margin-bottom: 0;
}

.runtime-schedule-item :deep(.el-form-item__content) {
  display: block;
}

.range-sep {
  color: #909399;
  font-size: 13px;
}

.select-hint {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
}

.selected-count {
  color: #909399;
}

/* 设备和模型选项 */
.device-option,
.model-option,
.class-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.device-id,
.class-id {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

.save-mode-content,
.frequency-content {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 选择卡片样式 */
.frequency-options,
.save-mode-options {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

.radio-card {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.3s;
}

.radio-card.active {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.radio-card:hover {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.radio-card-content {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.radio-card-content .el-icon {
  font-size: 18px;
  margin-top: 2px;
  color: #409eff;
}

.radio-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.radio-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}

/* 定时设置 */
.mode-selector {
  margin-bottom: 20px;
  text-align: center;
}

.schedule-tabs {
  margin-bottom: 0;
}

.tab-content {
  padding: 15px 0;
}

.time-picker {
  width: 100%;
}

.time-type-selector,
.date-type-selector {
  margin-bottom: 15px;
}

.date-content {
  margin-top: 15px;
}

.time-separator {
  font-weight: bold;
  color: #606266;
  padding: 0 10px;
  font-size: 16px;
  display: flex;
  align-items: center;
}

/* 时间点样式 */
.time-points-header {
  margin-bottom: 15px;
}

.time-points-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.time-point-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background-color: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  transition: all 0.3s;
}

.time-point-item:hover {
  background-color: #ecf5ff;
}

.time-point-picker {
  width: 100%;
}

.empty-time-points {
  padding: 15px 0;
  text-align: center;
}

/* 时间范围样式 */
.time-range-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 15px;
}

/* 日期选择样式 */
.weekday-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 15px;
}

.quick-buttons {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
}

/* 执行控制样式 */
.control-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 15px;
}

.control-item {
  margin-bottom: 0;
}

.info-icon {
  color: #909399;
  cursor: pointer;
}

/* 高级保存选项 */
.advanced-save-options {
  margin-top: 15px;
}

.slider-with-value {
  padding: 5px 0;
}

/* 动画效果 */
.time-point-list-enter-active,
.time-point-list-leave-active {
  transition: all 0.3s;
}

.time-point-list-enter-from,
.time-point-list-leave-to {
  opacity: 0;
  transform: translateY(-15px);
}

/* 对话框样式 */
:deep(.el-dialog__body) {
  padding: 0 20px 10px;
  max-height: 60vh;
  overflow-y: auto;
}

:deep(.el-form-item__label) {
  font-weight: 500;
  padding-bottom: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* 响应式设计 */
@media screen and (max-width: 768px) {

  .form-row,
  .time-range-row {
    flex-direction: column;
    gap: 15px;
  }

  .time-separator {
    align-self: center;
  }

  .control-grid {
    grid-template-columns: 1fr;
  }
}

/* 定时设置部分样式 */
.schedule-section {
  margin-top: 5px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-size: 15px;
  font-weight: 500;
  color: #606266;
}

.schedule-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 15px;
  margin-top: 5px;
}

.schedule-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px;
  background-color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.3s;
}

.schedule-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.card-title {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 500;
  color: #409EFF;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 10px;
}

.card-title .el-icon {
  margin-right: 8px;
  font-size: 18px;
}

.card-content {
  padding: 4px 0;
}

.time-settings {
  margin-bottom: 15px;
}

.day-checkbox {
  margin-right: 8px;
  margin-bottom: 8px;
}

.weekday-selector {
  display: flex;
  flex-direction: column;
}

.day-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

/* 响应式处理 */
@media screen and (max-width: 768px) {
  .schedule-cards {
    grid-template-columns: 1fr;
  }
}

/* 保存设置部分样式 */
.save-section {
  margin-top: 5px;
}

.save-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px;
  background-color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.3s;
  margin-top: 15px;
}

.save-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

/* 滑块样式优化 */
.slider-with-value {
  padding: 5px 10px;
}

:deep(.el-slider__runway) {
  margin: 12px 0;
}

:deep(.el-slider__bar) {
  background-color: #409EFF;
}

:deep(.el-slider__button) {
  border-color: #409EFF;
  width: 16px;
  height: 16px;
}

:deep(.el-slider__marks-text) {
  margin-top: 8px;
  color: #606266;
}

/* 配置弹窗 */
.config-tabs {
  margin-top: -8px;
}

.config-tabs :deep(.el-tabs__content) {
  max-height: 58vh;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px 12px 24px 4px;
}

:global(.config-model-select-popper) {
  z-index: 1000001 !important;
}

.field-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.margin-ratio-control {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.margin-ratio-row {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.margin-ratio-slider {
  flex: 1;
  min-width: 0;
}

.margin-ratio-slider :deep(.el-slider__runway) {
  margin: 0;
}

.margin-ratio-input {
  flex: 0 0 112px;
  width: 112px;
}

.margin-ratio-input :deep(.el-input-number) {
  width: 100%;
}

.margin-ratio-control .unit-label {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.pipeline-limit-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
  margin-top: 4px;
  margin-bottom: 4px;
}

.pipeline-limit-hint {
  margin: 0 0 8px;
}

.pipeline-limit-row .form-item {
  margin-bottom: 0;
  min-width: 0;
}

.pipeline-limit-row :deep(.el-input-number) {
  width: 100%;
}

.pipeline-image-block {
  margin-top: 20px;
  padding-top: 18px;
  padding-bottom: 8px;
  border-top: 1px solid #ebeef5;
}

.pipeline-image-block .pipeline-image-scope-item {
  margin-bottom: 16px;
}

.pipeline-image-block .pipeline-margin-item {
  margin-bottom: 0;
}

.hint-buttons {
  display: flex;
  gap: 10px;
}

.schedule-tab-alert {
  margin-top: 8px;
}

.save-options-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.section-hint {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #909399;
}

.w-full {
  width: 100%;
}

.dialog-footer-simple {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.section-container {
  min-height: auto;
  padding: 4px 0 8px;
}

.empty-step-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 250px;
}

/* 卡片头部样式 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  width: 100%;
}

.header-right {
  margin-left: auto;
}

/* 分页样式 */
.pagination {
  margin-top: 20px;
  text-align: right;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}

.target-class-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.empty-text {
  color: #c0c4cc;
  font-size: 13px;
}
</style>

<style>
.config-delete-messagebox .delete-confirm-message {
  line-height: 1.6;
  color: #606266;
}

.config-delete-messagebox .delete-confirm-line {
  margin: 0 0 10px 0;
}

.config-delete-messagebox .delete-confirm-line:last-child {
  margin-bottom: 0;
}

.config-delete-messagebox .delete-confirm-tip {
  color: #909399;
  font-size: 13px;
}

.config-delete-messagebox .delete-confirm-label {
  color: #303133;
  font-weight: 500;
}
</style>