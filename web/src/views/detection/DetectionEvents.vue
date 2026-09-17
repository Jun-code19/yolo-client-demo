<template>
  <div class="detection-events-page">
    <div class="page-header">
      <div class="header-content">
        <h2>检测事件记录</h2>
        <p>查看和管理检测事件，支持批量操作和详细分析</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadEvents" :loading="loading">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <el-button @click="exportEvents">
          <el-icon>
            <Download />
          </el-icon>
          导出
        </el-button>
      </div>
    </div>

    <!-- 实时统计 -->
    <div class="stats-cards">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#409EFF">
                <Bell />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ realtimeStats.total_today || 0 }}</div>
              <div class="stat-label">今日事件</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#67C23A">
                <View />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ realtimeStats.processed_today || 0 }}</div>
              <div class="stat-label">已处理</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#E6A23C">
                <StarFilled />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ realtimeStats.flagged_today || 0 }}</div>
              <div class="stat-label">重要标记</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item">
            <div class="stat-icon">
              <el-icon color="#F56C6C">
                <Flag />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ realtimeStats.high_confidence || 0 }}</div>
              <div class="stat-label">高置信度</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <el-card class="filter-section">
      <!-- 筛选条件 -->
      <el-form :model="filterForm" inline>
        <el-form-item label="设备">
          <el-select v-model="filterForm.device_id" placeholder="选择设备" style="width: 200px" filterable clearable>
            <el-option v-for="device in deviceList" :key="device.device_id"
              :label="`${device.device_name} (${device.device_id})`" :value="device.device_id">
              <div class="device-option">
                <span>{{ device.device_name }}</span>
                <span class="device-id">({{ device.device_id }})</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="事件类型">
          <el-select v-model="filterForm.event_type" placeholder="选择类型" style="width: 150px" clearable>
            <el-option v-for="type in eventTypes" :key="type.value" :label="type.label" :value="type.value" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="选择状态" style="width: 120px" clearable>
            <el-option value="new" label="新事件" />
            <el-option value="viewed" label="已查看" />
            <el-option value="flagged" label="已标记" />
            <el-option value="archived" label="已归档" />
          </el-select>
        </el-form-item>

        <el-form-item label="日期范围">
          <el-date-picker v-model="filterForm.dateRange" type="daterange" range-separator="至" start-placeholder="开始日期"
            end-placeholder="结束日期" style="width: 300px" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSearch">
            <el-icon>
              <Search />
            </el-icon>搜索
          </el-button>
          <!-- <el-button @click="resetFilter">
            重置
          </el-button> -->
        </el-form-item>
      </el-form>
    </el-card>
    <el-card class="main-card">
      <!-- 批量操作工具栏 -->
      <div class="batch-operations" v-if="selectedEvents.length > 0">
        <!-- <el-space> -->
        <span style="font-size: small;margin-right: 12px;">已选择 {{ selectedEvents.length }} 个事件</span>
        <el-button type="primary" size="small" @click="batchUpdateStatus('viewed')">
          <el-icon>
            <View />
          </el-icon>
          批量标记已查看
        </el-button>
        <el-button type="warning" size="small" @click="batchUpdateStatus('flagged')">
          <el-icon>
            <Flag />
          </el-icon>
          批量标记重要
        </el-button>
        <el-button type="info" size="small" @click="batchUpdateStatus('archived')">
          <el-icon>
            <FolderOpened />
          </el-icon>
          批量归档
        </el-button>
        <el-button type="danger" size="small" @click="batchDeleteEvents">
          <el-icon>
            <Delete />
          </el-icon>
          批量删除
        </el-button>
        <el-button size="small" @click="clearSelection">
          清除选择
        </el-button>
        <!-- </el-space> -->
      </div>
      <!-- 事件列表 -->
      <el-table :data="eventList" :loading="loading" row-key="event_id" style="width: 100%"
        @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="device_id" label="设备" min-width="140">
          <template #default="{ row }">
            <div>
              <div>{{ getDeviceName(row.device_id) }}</div>
              <div class="device-id-text">({{ row.device_id }})</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="event_type" label="事件类型" min-width="120">
          <template #default="{ row }">
            <el-tag :type="getEventTypeColor(row.event_type)" size="small">
              {{ getEventTypeName(row.event_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 检测目标列 -->
        <el-table-column label="检测目标" min-width="150">
          <template #default="{ row }">
            <div v-if="getDetectionTargets(row).length > 0" class="detection-targets">
              <div class="targets-summary">
                <el-tag size="small" type="primary">{{ getDetectionTargets(row).length }}个目标</el-tag>
              </div>
              <div class="targets-detail">
                <div v-for="(target, index) in getDetectionTargets(row).slice(0, 2)" :key="index" class="target-item">
                  <span class="target-name">{{ target.class_name || target.name || '未知' }}</span>
                  <span class="target-confidence">{{ (target.confidence * 100).toFixed(1) }}%</span>
                </div>
                <div v-if="getDetectionTargets(row).length > 2" class="more-targets">
                  +{{ getDetectionTargets(row).length - 2 }}个
                </div>
              </div>
            </div>
            <span v-else class="text-muted">无检测目标</span>
          </template>
        </el-table-column>

        <!-- 事件描述列 -->
        <el-table-column label="事件描述" min-width="150">
          <template #default="{ row }">
            <div v-if="row.meta_data?.event_description" class="event-description">
              {{ row.meta_data.event_description }}
            </div>
            <div v-else-if="row.meta_data?.analysis_type" class="event-type-desc">
              {{ getAnalysisTypeDesc(row.meta_data.analysis_type) }}
            </div>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <el-table-column prop="confidence" label="置信度" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.confidence >= 0.8 ? 'success' : row.confidence >= 0.6 ? 'warning' : 'danger'"
              size="small">
              {{ (row.confidence * 100).toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>

        <!-- 图片列 -->
        <el-table-column label="图片" width="150">
          <template #default="{ row }">
            <div v-if="row.thumbnail_path" class="image-column">
              <div class="thumbnail-container"
                @click.stop="openImagePreview([{ title: '事件图片', path: row.thumbnail_path }], 0)">
                <img :src="getImageUrl(row.thumbnail_path)" alt="事件图片" class="table-thumbnail"
                  @error="handleImageError" />
                <div class="image-overlay">
                  <el-icon class="preview-icon">
                    <ZoomIn />
                  </el-icon>
                </div>
              </div>
            </div>
            <span v-else class="text-muted">无图片</span>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusColor(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="timestamp" label="时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.timestamp) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <!-- <el-button-group> -->
            <el-button type="primary" size="small" @click="viewEvent(row)">
              详情
            </el-button>
            <el-button type="danger" size="small" @click="deleteEvent(row)">
              删除
            </el-button>
            <!-- </el-button-group> -->
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total"
          :page-sizes="[10, 20, 50, 100]" layout="prev, pager, next, jumper, ->, total, sizes"
          @size-change="handleSizeChange" @current-change="handlePageChange" />
      </div>
    </el-card>

    <!-- 事件详情模态框 -->
    <el-dialog v-model="eventModalVisible" :title="`事件详情 - ${getEventTypeName(selectedEvent?.event_type) || ''}`"
      width="50%" destroy-on-close :close-on-click-modal="false" :z-index="999999" append-to-body top="5vh"
      class="detection-event-dialog high-priority-dialog">
      <template v-if="selectedEvent">
        <div class="event-detail">
          <!-- 基本信息 -->
          <el-descriptions :column="2" border>
            <el-descriptions-item label="事件ID">
              {{ selectedEvent.event_id }}
            </el-descriptions-item>
            <el-descriptions-item label="设备">
              <span>{{ getDeviceName(selectedEvent.device_id) }}</span>
              <span class="device-id-text">({{ selectedEvent.device_id }})</span>
            </el-descriptions-item>
            <el-descriptions-item label="事件类型">
              <el-tag :type="getEventTypeColor(selectedEvent.event_type)">
                {{ getEventTypeName(selectedEvent.event_type) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="整体置信度">
              <el-tag
                :type="selectedEvent.confidence >= 0.8 ? 'success' : selectedEvent.confidence >= 0.6 ? 'warning' : 'danger'">
                {{ (selectedEvent.confidence * 100).toFixed(2) }}%
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="发生时间">
              {{ formatDateTime(selectedEvent.timestamp) }}
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">
              {{ formatDateTime(selectedEvent.created_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="位置">
              {{ selectedEvent.location || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="保存模式">
              {{ selectedEvent.save_mode || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <!-- 状态管理区域 -->
          <div class="detail-section">
            <h4>状态管理</h4>
            <el-row :gutter="16">
              <el-col :span="12">
                <div class="status-operations">
                  <el-space direction="vertical" style="width: 100%">
                    <div>
                      <label>当前状态：</label>
                      <el-tag :type="getStatusColor(selectedEvent.status)">
                        {{ getStatusLabel(selectedEvent.status) }}
                      </el-tag>
                    </div>
                    <div>
                      <label>快速操作：</label>
                      <!-- <el-button-group size="small" > -->
                      <el-button type="success" size="small" @click="updateEventStatus(selectedEvent, 'viewed')"
                        :disabled="selectedEvent.status === 'viewed'">
                        <el-icon>
                          <View />
                        </el-icon>
                        标记已查看
                      </el-button>
                      <el-button type="warning" size="small" @click="updateEventStatus(selectedEvent, 'flagged')"
                        :disabled="selectedEvent.status === 'flagged'">
                        <el-icon>
                          <Flag />
                        </el-icon>
                        标记重要
                      </el-button>
                      <el-button type="info" size="small" @click="updateEventStatus(selectedEvent, 'archived')"
                        :disabled="selectedEvent.status === 'archived'">
                        <el-icon>
                          <FolderOpened />
                        </el-icon>
                        归档
                      </el-button>
                      <!-- </el-button-group> -->
                    </div>
                  </el-space>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="status-info">
                  <div v-if="selectedEvent.viewed_by">
                    <label>查看者：</label>{{ selectedEvent.viewed_by }}
                  </div>
                  <div v-if="selectedEvent.viewed_at">
                    <label>查看时间：</label>{{ formatDateTime(selectedEvent.viewed_at) }}
                  </div>
                </div>
              </el-col>
            </el-row>
          </div>

          <!-- 元数据信息 -->
          <div class="detail-section" v-if="selectedEvent.meta_data">
            <h4>事件详细信息</h4>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="事件描述" v-if="selectedEvent.meta_data.event_description">
                {{ selectedEvent.meta_data.event_description }}
              </el-descriptions-item>
              <el-descriptions-item label="分析类型" v-if="selectedEvent.meta_data.analysis_type">
                {{ getAnalysisTypeDesc(selectedEvent.meta_data.analysis_type) }}
              </el-descriptions-item>
              <el-descriptions-item label="计数类型" v-if="selectedEvent.meta_data.counting_type">
                {{ getCountingTypeDesc(selectedEvent.meta_data.counting_type) }}
              </el-descriptions-item>
              <el-descriptions-item label="当前计数" v-if="selectedEvent.meta_data.current_count !== undefined">
                {{ selectedEvent.meta_data.current_count }}
              </el-descriptions-item>
              <el-descriptions-item label="今日进入" v-if="selectedEvent.meta_data.today_in_count !== undefined">
                {{ selectedEvent.meta_data.today_in_count }}
              </el-descriptions-item>
              <el-descriptions-item label="今日离开" v-if="selectedEvent.meta_data.today_out_count !== undefined">
                {{ selectedEvent.meta_data.today_out_count }}
              </el-descriptions-item>
              <el-descriptions-item label="计数子类型" v-if="selectedEvent.meta_data.counting_subtype">
                {{ selectedEvent.meta_data.counting_subtype }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- VLM 管道详情 -->
          <div class="detail-section" v-if="getVlmMeta(selectedEvent)">
            <h4>VLM 分析结果</h4>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="推理模式">
                {{ selectedEvent.meta_data.pipeline_mode === 'yolo_then_verify' ? 'YOLO + 复检' : 'YOLO + 行为分析' }}
              </el-descriptions-item>
              <el-descriptions-item label="VLM 模型">
                {{ getVlmMeta(selectedEvent).model_id || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="Prompt">
                {{ getVlmMeta(selectedEvent).prompt_id || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="耗时">
                {{ getVlmMeta(selectedEvent).latency_ms ?? '-' }} ms
              </el-descriptions-item>
              <el-descriptions-item label="VLM 摘要" :span="2">
                {{ getVlmMeta(selectedEvent).result?.summary || getVlmMeta(selectedEvent).result?.reason || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="告警标签" :span="2">
                {{ formatVlmLabels(selectedEvent) }}
              </el-descriptions-item>
              <el-descriptions-item
                v-if="selectedEvent.event_type === 'yolo_verify'"
                label="复检结论"
              >
                <el-tag :type="getVlmMeta(selectedEvent).result?.verified ? 'success' : 'info'" size="small">
                  {{ getVlmMeta(selectedEvent).result?.verified ? '通过' : '未通过' }}
                </el-tag>
                <span v-if="getVlmMeta(selectedEvent).result?.confidence != null" style="margin-left: 8px">
                  置信度 {{ (getVlmMeta(selectedEvent).result.confidence * 100).toFixed(1) }}%
                </span>
              </el-descriptions-item>
            </el-descriptions>
            <el-table
              v-if="getVlmFindings(selectedEvent).length"
              :data="getVlmFindings(selectedEvent)"
              size="small"
              style="width: 100%; margin-top: 12px"
            >
              <el-table-column prop="label" label="标签" width="120" />
              <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
              <el-table-column label="置信度" width="100">
                <template #default="{ row }">
                  {{ row.confidence != null ? `${(row.confidence * 100).toFixed(1)}%` : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="severity" label="级别" width="90" />
            </el-table>
          </div>

          <!-- 检测目标详情 -->
          <div class="detail-section" v-if="getDetectionTargets(selectedEvent).length > 0">
            <h4>检测目标 ({{ getDetectionTargets(selectedEvent).length }}个)</h4>
            <el-table :data="getDetectionTargets(selectedEvent)" style="width: 100%" size="small">
              <el-table-column prop="class_name" label="目标类型" width="120">
                <template #default="{ row }">
                  <el-tag size="small">{{ row.class_name || row.name || '未知' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="confidence" label="置信度" width="120">
                <template #default="{ row }">
                  <el-tag size="small"
                    :type="row.confidence >= 0.8 ? 'success' : row.confidence >= 0.6 ? 'warning' : 'danger'">
                    {{ (row.confidence * 100).toFixed(2) }}%
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="class_id" label="类别ID" width="80">
                <template #default="{ row }">
                  <span>{{ row.class_id }}</span>
                </template>
              </el-table-column>
              <el-table-column label="边界框坐标" min-width="200">
                <template #default="{ row }">
                  <span v-if="row.bbox || row.bounding_box">
                    {{ formatBoundingBox(row.bbox || row.bounding_box) }}
                  </span>
                  <span v-else class="text-muted">-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 事件图片 -->
          <div class="detail-section" v-if="selectedEvent.thumbnail_path">
            <h4>事件图片</h4>
            <div class="event-image-container">
              <img :src="getImageUrl(selectedEvent.thumbnail_path)" alt="事件图片" class="detail-image"
                @click="openImagePreview([{ title: '事件图片', path: selectedEvent.thumbnail_path }], 0)"
                @error="handleImageError" />
            </div>
          </div>

          <!-- 备注 -->
          <div class="detail-section">
            <h4>事件备注</h4>
            <el-input v-model="eventNotes" type="textarea" :rows="3" placeholder="添加事件备注..." />
            <el-button type="primary" style="margin-top: 8px" @click="saveEventNotes">
              保存备注
            </el-button>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="eventModalVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 图片预览对话框 -->
    <el-dialog v-model="imagePreviewVisible" title="图片预览" width="50%" :close-on-click-modal="false" :z-index="100000"
      append-to-body top="5vh" class="detection-image-preview-dialog image-preview-dialog high-priority-dialog">
      <div v-if="previewImages.length > 0" class="image-preview-content">
        <!-- 图片导航 -->
        <div class="image-nav" v-if="previewImages.length > 1">
          <el-button-group>
            <el-button v-for="(img, index) in previewImages" :key="index"
              :type="index === currentImageIndex ? 'primary' : 'default'" size="small"
              @click="currentImageIndex = index">
              {{ img.title }}
            </el-button>
          </el-button-group>
        </div>

        <!-- 当前图片 -->
        <div class="current-image-container">
          <div class="image-header">
            <h3>{{ previewImages[currentImageIndex]?.title }}</h3>
          </div>
          <div class="image-display">
            <img :src="getImageUrl(previewImages[currentImageIndex]?.path)"
              :alt="previewImages[currentImageIndex]?.title" class="preview-image" @error="handleImageError" />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="imagePreviewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { defineComponent, ref, reactive, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Search, Delete, View, Star, Download, StarFilled, ArrowDown, Flag, FolderOpened, Bell, Refresh, ZoomIn } from '@element-plus/icons-vue';
import dayjs from 'dayjs';
import { detectionEventApi } from '@/api/detection';
import deviceApi from '@/api/device';

export default defineComponent({
  name: 'DetectionEvents',
  components: {
    Search,
    Delete,
    View,
    Star,
    Download,
    StarFilled,
    ArrowDown,
    Flag,
    FolderOpened,
    Bell,
    Refresh,
    ZoomIn
  },
  setup() {
    // 数据加载状态
    const loading = ref(false);

    // 表格数据
    const eventList = ref([]);
    const deviceList = ref([]);
    const eventTypes = ref([
      { label: '目标检测', value: 'object_detection' },
      { label: 'VLM 复检', value: 'yolo_verify' },
      { label: 'VLM 行为分析', value: 'yolo_analyze' },
      { label: '智能行为', value: 'smart_behavior' },
      { label: '人员场景', value: 'smart_person' },
      { label: '智能人数统计', value: 'smart_counting' },
      { label: '图像分割', value: 'segmentation' },
      { label: '关键点检测', value: 'keypoint' },
      { label: '姿态估计', value: 'pose' },
      { label: '人脸识别', value: 'face' },
      { label: '其他类型', value: 'other' }
    ]);

    // 批量操作相关
    const selectedEvents = ref([]);

    // 分页
    const page = ref(1);
    const pageSize = ref(10);
    const total = ref(0);

    // 筛选表单
    const filterForm = reactive({
      device_id: undefined,
      event_type: undefined,
      status: undefined,
      dateRange: undefined,
      min_confidence: undefined
    });

    // 事件详情模态框
    const eventModalVisible = ref(false);
    const selectedEvent = ref(null);
    const eventNotes = ref('');

    // 图片预览
    const selectedEventThumbnail = ref('');
    const imagePreviewVisible = ref(false);
    const previewImageUrl = ref('');
    const previewImages = ref([]);
    const currentImageIndex = ref(0);

    // 实时统计
    const realtimeStats = ref({
      total_today: 0,
      processed_today: 0,
      flagged_today: 0,
      high_confidence: 0
    });

    // 获取设备名称
    const getDeviceName = (deviceId) => {
      const device = deviceList.value.find(d => d.device_id === deviceId);
      return device ? device.device_name : deviceId;
    };

    // 获取事件类型颜色
    const getEventTypeColor = (eventType) => {
      const colorMap = {
        'object_detection': 'primary',
        'yolo_verify': 'success',
        'yolo_analyze': 'danger',
        'smart_behavior': 'success',
        'smart_person': 'danger',
        'smart_counting': 'warning',
        'segmentation': 'success',
        'keypoint': 'warning',
        'pose': 'danger',
        'face': 'info',
        'other': 'success'
      };
      return colorMap[eventType] || 'default';
    };

    // 获取模型类型名称
    const getEventTypeName = (eventType) => {
      const typeMap = {
        'object_detection': '目标检测',
        'yolo_verify': 'VLM 复检',
        'yolo_analyze': 'VLM 行为分析',
        'smart_behavior': '智能行为',
        'smart_person': '人员场景',
        'smart_counting': '智能人数统计',
        'segmentation': '图像分割',
        'keypoint': '关键点检测',
        'pose': '姿态估计',
        'face': '人脸识别',
        'other': '其他类型'
      }
      return typeMap[eventType] || eventType || '未知类型'
    }

    const getVlmMeta = (event) => {
      if (!event?.meta_data?.vlm) return null
      return event.meta_data.vlm
    }

    const getVlmFindings = (event) => {
      const vlm = getVlmMeta(event)
      const findings = vlm?.result?.findings
      return Array.isArray(findings) ? findings : []
    }

    const formatVlmLabels = (event) => {
      const vlm = getVlmMeta(event)
      const labels = vlm?.result?.alert_labels
      return Array.isArray(labels) && labels.length ? labels.join('、') : '-'
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

    // 获取状态颜色
    const getStatusColor = (status) => {
      const map = {
        'new': 'primary',
        'viewed': 'success',
        'flagged': 'warning',
        'archived': 'info'
      };
      return map[status] || 'default';
    };

    // 格式化日期时间
    const formatDateTime = (dateStr) => {
      if (!dateStr) return '';
      return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss');
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

    // 加载统计数据
    const loadRealtimeStats = async () => {
      try {
        // 使用后端专门的统计API
        const response = await detectionEventApi.getEventsStatsOverview();

        if (response.data.status === 'success') {
          const stats = response.data.data;
          realtimeStats.value = {
            total_today: stats.total_today || 0,
            processed_today: stats.processed_today || 0,
            flagged_today: stats.flagged_today || 0,
            high_confidence: stats.high_confidence || 0
          };
        } else {
          throw new Error('API返回状态异常');
        }
      } catch (error) {
        console.error('加载统计数据失败:', error);
        // 提供默认值
        realtimeStats.value = {
          total_today: 0,
          processed_today: 0,
          flagged_today: 0,
          high_confidence: 0
        };
      }
    };

    // 加载事件列表
    const loadEvents = async () => {
      loading.value = true;

      try {
        // 构建查询参数
        const params = {
          skip: (page.value - 1) * pageSize.value,
          limit: pageSize.value
        };

        if (filterForm.device_id) {
          params.device_id = filterForm.device_id;
        }

        if (filterForm.event_type) {
          params.event_type = filterForm.event_type;
        }

        if (filterForm.status) {
          params.status = filterForm.status;
        }

        if (filterForm.dateRange && filterForm.dateRange.length === 2) {
          const startDate = new Date(filterForm.dateRange[0]);
          const endDate = new Date(filterForm.dateRange[1]);

         // 设置开始时间为选择日期的 0 点 0 分
          startDate.setHours(0, 0, 0, 0);
          // 假设是 UTC+8，为了获取 11 号 0 点，需要减去 8 小时
          startDate.setHours(startDate.getHours() - startDate.getTimezoneOffset() / 60);

          // 设置结束时间为选择日期的 23 点 59 分
          endDate.setHours(23, 59, 59, 999);
          // 假设是 UTC+8，为了获取 11 号 23 点 59 分 59 秒，需要减去 8 小时
          endDate.setHours(endDate.getHours() - endDate.getTimezoneOffset() / 60);

          // 将日期转换为 ISO 字符串
          params.start_date = startDate.toISOString();
          params.end_date = endDate.toISOString();

        }
        console.log(params);

        if (filterForm.min_confidence) {
          params.min_confidence = filterForm.min_confidence;
        }

        const response = await detectionEventApi.getEvents(params);
        // 从修改后的API响应结构中获取数据和总数
        eventList.value = response.data.data;
        total.value = response.data.total;

        // 同时加载统计数据
        await loadRealtimeStats();
      } catch (error) {
        ElMessage.error('获取事件列表失败: ' + error.message);
      } finally {
        loading.value = false;
      }
    };

    const handleSearch = () => {
      page.value = 1;
      loadEvents();
    };

    // 重置筛选条件
    const resetFilter = () => {
      Object.assign(filterForm, {
        device_id: undefined,
        event_type: undefined,
        status: undefined,
        dateRange: undefined,
        min_confidence: undefined
      });

      page.value = 1;
      loadEvents();
    };

    // 切换页码
    const handlePageChange = (newPage) => {
      page.value = newPage;
      loadEvents();
    };

    // 切换每页显示数量
    const handleSizeChange = (newSize) => {
      pageSize.value = newSize;
      loadEvents();
    };

    // 查看事件详情
    const viewEvent = async (event) => {
      selectedEvent.value = { ...event };
      eventNotes.value = event.notes || '';
      eventModalVisible.value = true;

      // 加载缩略图
      // selectedEventThumbnail.value = await loadThumbnail(event.event_id);
      selectedEventThumbnail.value = getImageUrl(event.thumbnail_path);

      // 如果状态是新事件，自动更新为已查看
      if (event.status === 'new') {
        await updateEventStatus(event, 'viewed', false);
      }
    };

    // 更新事件状态
    const updateEventStatus = async (event, newStatus, showMessage = true) => {
      try {
        await detectionEventApi.updateEventStatus(event.event_id, newStatus);

        // 更新本地状态
        if (selectedEvent.value && selectedEvent.value.event_id === event.event_id) {
          selectedEvent.value.status = newStatus;
        }

        // 更新列表中的状态
        const index = eventList.value.findIndex(e => e.event_id === event.event_id);
        if (index !== -1) {
          eventList.value[index].status = newStatus;
        }

        if (showMessage) {
          ElMessage.success('状态更新成功');
        }

        // 重新加载统计数据
        await loadEvents();
        await loadRealtimeStats();
      } catch (error) {
        ElMessage.error('更新状态失败: ' + error.message);
      }
    };

    // 保存事件备注
    const saveEventNotes = async () => {
      if (!selectedEvent.value) return;

      try {
        await detectionEventApi.updateEventNotes(selectedEvent.value.event_id, eventNotes.value);

        // 更新本地和列表状态
        selectedEvent.value.notes = eventNotes.value;

        const index = eventList.value.findIndex(e => e.event_id === selectedEvent.value.event_id);
        if (index !== -1) {
          eventList.value[index].notes = eventNotes.value;
        }

        ElMessage.success('备注保存成功');
      } catch (error) {
        ElMessage.error('保存备注失败: ' + error.message);
      }
    };

    // 删除事件
    const deleteEvent = async (event) => {
      ElMessageBox.confirm(
        `确认删除该事件吗？`,
        '删除确认',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          type: 'warning'
        }
      ).then(async () => {
        try {
          await detectionEventApi.deleteEvent(event.event_id);

          // 从列表中移除
          eventList.value = eventList.value.filter(e => e.event_id !== event.event_id);

          // 如果正在查看该事件，关闭模态框
          if (selectedEvent.value && selectedEvent.value.event_id === event.event_id) {
            eventModalVisible.value = false;
          }

          ElMessage.success('事件已删除');

          // 重新加载统计数据
          await loadRealtimeStats();
        } catch (error) {
          ElMessage.error('删除事件失败: ' + error.message);
        }
      }).catch(() => { });
    };

    const loadThumbnail = async (eventId) => {
      try {
        const thumbnailUrl = await detectionEventApi.fetchThumbnail(eventId);
        return thumbnailUrl; // 返回图像 URL         
      } catch (error) {
        // console.error('加载缩略图失败:', error);
      }
    };

    // 获取事件图片URL
    const getImageUrl = (thumbnailPath) => {
      if (!thumbnailPath) return '';

      // 返回完整的图片URL
      return `/api/v1/files/${thumbnailPath.replace(/\\/g, '/')}`; // 替换反斜杠为正斜杠
    };

    // 获取检测目标
    const getDetectionTargets = (event) => {
      if (!event) return [];

      // 从 meta_data.yolo.detections 获取（VLM 管道事件）
      if (event.meta_data?.yolo?.detections?.length > 0) {
        return event.meta_data.yolo.detections.map(item => ({
          class_id: item.class_id,
          class_name: item.class_name || '未知',
          confidence: item.confidence || 0,
          bbox: item.bbox
        }));
      }

      // 从bounding_box获取（主要数据源）
      if (event.bounding_box && Array.isArray(event.bounding_box) && event.bounding_box.length > 0) {
        return event.bounding_box.map(item => ({
          class_id: item.class_id,
          class_name: item.class_name || '未知',
          confidence: item.confidence || 0,
          bbox: item.bbox
        }));
      }

      // 从detection_result获取
      if (event.detection_result?.detections?.length > 0) {
        return event.detection_result.detections;
      }

      // 从metadata获取
      if (event.metadata?.detections?.length > 0) {
        return event.metadata.detections;
      }

      // 从原始数据获取
      if (event.original_data?.detections?.length > 0) {
        return event.original_data.detections;
      }

      return [];
    };

    // 格式化边界框信息
    const formatBoundingBox = (bbox) => {
      if (!bbox) return '-';
      if (Array.isArray(bbox) && bbox.length === 4) {
        return `(${bbox[0]}, ${bbox[1]}) - (${bbox[2]}, ${bbox[3]})`;
      }
      if (bbox.x1 !== undefined) {
        return `(${bbox.x1}, ${bbox.y1}) - (${bbox.x2}, ${bbox.y2})`;
      }
      if (bbox.x !== undefined) {
        return `(${bbox.x}, ${bbox.y}) - (${bbox.x + bbox.w}, ${bbox.y + bbox.h})`;
      }
      return JSON.stringify(bbox);
    };

    // 打开图片预览
    const openImagePreview = (images, startIndex = 0) => {
      previewImages.value = images;
      currentImageIndex.value = startIndex;
      imagePreviewVisible.value = true;
    };



    // 处理图片加载错误
    const handleImageError = (event) => {
      event.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHZpZXdCb3g9IjAgMCA0MCA0MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjRjVGNUY1Ii8+CjxwYXRoIGQ9Ik0yMCAzMEMyNS41MjI5IDMwIDMwIDI1LjUyMjkgMzAgMjBDMzAgMTQuNDc3MSAyNS41MjI5IDEwIDIwIDEwQzE0LjQ3NzEgMTAgMTAgMTQuNDc3MSAxMCAyMEMxMCAyNS41MjI5IDE0LjQ3NzEgMzAgMjAgMzBaIiBmaWxsPSIjQ0NDQ0NDIi8+CjxwYXRoIGQ9Ik0yMCAyMi41QzIxLjM4MDcgMjIuNSAyMi41IDIxLjM4MDcgMjIuNSAyMEMyMi41IDE4LjYxOTMgMjEuMzgwNyAxNy41IDIwIDE3LjVDMTguNjE5MyAxNy41IDE3LjUgMTguNjE5MyAxNy41IDIwQzE3LjUgMjEuMzgwNyAxOC42MTkzIDIyLjUgMjAgMjIuNVoiIGZpbGw9IiNGRkZGRkYiLz4KPC9zdmc+';
      event.target.style.opacity = '0.5';
    };

    // 导出事件
    const exportEvents = () => {
      ElMessage.info('导出功能开发中...');
    };

    // 获取分析类型描述
    const getAnalysisTypeDesc = (analysisType) => {
      const typeMap = {
        'counting': '人数统计',
        'behavior': '行为分析',
        'detection': '目标检测',
        'tracking': '目标跟踪'
      };
      return typeMap[analysisType] || analysisType;
    };

    // 获取计数类型描述
    const getCountingTypeDesc = (countingType) => {
      const typeMap = {
        'flow': '人流统计',
        'occupancy': '占用统计',
        'in': '进入计数',
        'out': '离开计数',
        'bidirectional': '双向计数'
      };
      return typeMap[countingType] || countingType;
    };

    // 批量操作方法
    const handleSelectionChange = (selection) => {
      selectedEvents.value = selection;
    };

    const clearSelection = () => {
      selectedEvents.value = [];
    };

    const batchUpdateStatus = async (status) => {
      if (selectedEvents.value.length === 0) {
        ElMessage.warning('请先选择要操作的事件');
        return;
      }

      try {
        const eventIds = selectedEvents.value.map(event => event.event_id);

        // 如果API支持批量更新，使用批量API
        if (detectionEventApi.batchUpdateStatus) {
          await detectionEventApi.batchUpdateStatus(eventIds, status);
        } else {
          // 否则使用单个更新的方式
          const updatePromises = eventIds.map(eventId =>
            detectionEventApi.updateEventStatus(eventId, status)
          );
          await Promise.all(updatePromises);
        }

        // 更新本地数据
        selectedEvents.value.forEach(selectedEvent => {
          const event = eventList.value.find(e => e.event_id === selectedEvent.event_id);
          if (event) {
            event.status = status;
          }
        });

        ElMessage.success(`批量更新状态成功，共 ${eventIds.length} 个事件`);
        clearSelection();
        // 重新加载统计数据
        await loadRealtimeStats();
      } catch (error) {
        const detail = error.response?.data?.detail
        ElMessage.error('批量更新状态失败: ' + (detail || error.message))
      }
    };

    const batchDeleteEvents = async () => {
      if (selectedEvents.value.length === 0) {
        ElMessage.warning('请先选择要删除的事件');
        return;
      }

      ElMessageBox.confirm(
        `确认删除选中的 ${selectedEvents.value.length} 个事件吗？此操作将同时删除相关的图片和视频文件。`,
        '批量删除确认',
        {
          confirmButtonText: '确认删除',
          cancelButtonText: '取消',
          type: 'warning',
          dangerouslyUseHTMLString: true
        }
      ).then(async () => {
        try {
          const eventIds = selectedEvents.value.map(event => event.event_id);
          const response = await detectionEventApi.batchDeleteEvents(eventIds);

          // 从列表中移除已删除的事件
          const deletedIds = new Set(eventIds);
          eventList.value = eventList.value.filter(event => !deletedIds.has(event.event_id));

          // 如果当前查看的事件被删除，关闭模态框
          if (selectedEvent.value && deletedIds.has(selectedEvent.value.event_id)) {
            eventModalVisible.value = false;
          }

          clearSelection();

          let message = `成功删除 ${response.data.deleted_count} 个事件`;
          if (response.data.files_deleted && response.data.files_deleted.length > 0) {
            message += `，同时删除了 ${response.data.files_deleted.length} 个文件`;
          }
          if (response.data.files_failed && response.data.files_failed.length > 0) {
            message += `，${response.data.files_failed.length} 个文件删除失败`;
          }

          ElMessage.success(message);

          // 重新加载统计数据
          await loadRealtimeStats();

          // 如果有错误，显示详细信息
          if (response.data.errors && response.data.errors.length > 0) {
            console.warn('部分事件删除失败:', response.data.errors);
          }
        } catch (error) {
          ElMessage.error('批量删除事件失败: ' + error.message);
        }
      }).catch(() => { });
    };

    // 初始化
    onMounted(() => {
      loadDeviceList();
      loadEvents();
    });

    return {
      loading,
      eventList,
      deviceList,
      eventTypes,
      selectedEvents,
      page,
      pageSize,
      total,
      filterForm,
      eventModalVisible,
      selectedEvent,
      eventNotes,
      imagePreviewVisible,
      previewImageUrl,
      selectedEventThumbnail,
      previewImages,
      currentImageIndex,
      realtimeStats,
      getImageUrl,
      getDeviceName,
      getEventTypeColor,
      getEventTypeName,
      getStatusLabel,
      getStatusColor,
      formatDateTime,
      getDetectionTargets,
      getVlmMeta,
      getVlmFindings,
      formatVlmLabels,
      formatBoundingBox,
      openImagePreview,
      handleImageError,
      exportEvents,
      getAnalysisTypeDesc,
      getCountingTypeDesc,
      loadEvents,
      loadRealtimeStats,
      handleSearch,
      resetFilter,
      handlePageChange,
      handleSizeChange,
      viewEvent,
      updateEventStatus,
      saveEventNotes,
      deleteEvent,
      loadThumbnail,
      handleSelectionChange,
      clearSelection,
      batchUpdateStatus,
      batchDeleteEvents
    };
  }
});
</script>

<style scoped>
.detection-events-page {
  padding: 20px;
}

.main-card {
  margin-bottom: 20px;
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
  margin-bottom: 0px;
}

.pagination {
  margin-top: 20px;
  text-align: right;
}

/* .event-detail {
  display: flex;
  gap: 20px;
} */

.event-image {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.main-image {
  max-width: 100%;
  cursor: pointer;
  border: 1px solid #eee;
  border-radius: 4px;
}

.event-info {
  flex: 1;
}

.event-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.device-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.device-id {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

/* 统计卡片样式 */
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

/* 表格样式 */
.device-id-text {
  color: #909399;
  font-size: 12px;
}

.text-muted {
  color: #999;
}

/* 检测目标样式 */
.detection-targets {
  font-size: 12px;
}

.targets-summary {
  margin-bottom: 4px;
}

.targets-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.target-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.target-name {
  color: #333;
  font-weight: 500;
}

.target-confidence {
  color: #409eff;
  font-weight: 600;
}

.more-targets {
  color: #909399;
  font-style: italic;
  text-align: center;
  margin-top: 2px;
}

/* 图片展示样式 */
.image-column {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.thumbnail-container {
  position: relative;
  width: 60px;
  height: 45px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid #e4e7ed;
}

.table-thumbnail {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}

.thumbnail-container:hover .table-thumbnail {
  transform: scale(1.1);
}

.image-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.thumbnail-container:hover .image-overlay {
  opacity: 1;
}

.preview-icon {
  color: white;
  font-size: 16px;
}

/* 事件详情样式 */
.detection-event-dialog .detail-section {
  margin-top: 24px !important;
  padding: 20px !important;
  background-color: #f8f9fa !important;
  border-radius: 8px !important;
  border: 1px solid #e9ecef !important;
}

.detection-event-dialog .detail-section:first-child {
  margin-top: 0 !important;
}

.detection-event-dialog .detail-section h4 {
  margin: 0 0 16px 0 !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  color: #495057 !important;
  padding-bottom: 8px !important;
  border-bottom: 2px solid #dee2e6 !important;
  display: flex !important;
  align-items: center !important;
}

.detection-event-dialog .detail-section h4::before {
  content: '' !important;
  width: 4px !important;
  height: 16px !important;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  margin-right: 8px !important;
  border-radius: 2px !important;
}

/* 状态管理样式 */
.detection-event-dialog .status-operations {
  padding: 20px !important;
  background-color: #ffffff !important;
  border-radius: 8px !important;
  border: 2px solid #e3f2fd !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
}

.detection-event-dialog .status-operations label {
  font-weight: 600 !important;
  color: #1976d2 !important;
  margin-right: 12px !important;
  font-size: 15px !important;
}

.detection-event-dialog .status-info {
  padding: 20px !important;
  background-color: #ffffff !important;
  border-radius: 8px !important;
  border: 2px solid #f3e5f5 !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
}

.detection-event-dialog .status-info label {
  font-weight: 600 !important;
  color: #7b1fa2 !important;
  margin-right: 12px !important;
  font-size: 15px !important;
}

.detection-event-dialog .status-info div {
  margin-bottom: 12px !important;
  line-height: 1.6 !important;
}

.detection-event-dialog .status-info div:last-child {
  margin-bottom: 0 !important;
}

/* 事件描述样式 */
.event-description {
  color: #333;
  font-size: 13px;
  line-height: 1.4;
}

.event-type-desc {
  color: #666;
  font-size: 12px;
  font-style: italic;
}

.detection-event-dialog .event-image-container {
  text-align: center !important;
  padding: 24px !important;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8f4f8 100%) !important;
  border-radius: 12px !important;
  border: 2px solid #e1f5fe !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
}

.detection-event-dialog .detail-image {
  max-width: 100% !important;
  max-height: 400px !important;
  cursor: pointer !important;
  border-radius: 8px !important;
  transition: all 0.3s ease !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1) !important;
}

.detection-event-dialog .detail-image:hover {
  transform: scale(1.02) !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15) !important;
}

/* 图片预览对话框样式 */
.detection-image-preview-dialog.el-dialog {
  border-radius: 8px !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3) !important;
  overflow: hidden !important;
}

.detection-image-preview-dialog .el-dialog__header {
  padding: 20px 24px 16px !important;
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%) !important;
  border-bottom: none !important;
  margin: 0 !important;
}

.detection-image-preview-dialog .el-dialog__title {
  color: white !important;
  font-weight: 600 !important;
  font-size: 18px !important;
}

.detection-image-preview-dialog .el-dialog__headerbtn .el-dialog__close {
  color: white !important;
  font-size: 18px !important;
}

.detection-image-preview-dialog .el-dialog__body {
  padding: 24px !important;
  max-height: 75vh !important;
  overflow-y: auto !important;
  background-color: #ffffff !important;
}

.image-preview-content {
  display: flex !important;
  flex-direction: column !important;
  gap: 20px !important;
}

.image-nav {
  display: flex !important;
  justify-content: center !important;
  padding-bottom: 16px !important;
  border-bottom: 1px solid #e4e7ed !important;
}

.current-image-container {
  display: flex !important;
  flex-direction: column !important;
  gap: 16px !important;
}

.image-header {
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
  padding: 16px !important;
  background-color: #f5f7fa !important;
  border-radius: 8px !important;
}

.image-header h3 {
  margin: 0 !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  color: #333 !important;
}

.image-display {
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  min-height: 400px !important;
  background-color: #f8f9fa !important;
  border-radius: 8px !important;
  padding: 20px !important;
}

.preview-image {
  max-width: 100% !important;
  max-height: 500px !important;
  object-fit: contain !important;
  border-radius: 4px !important;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}

.image-preview-dialog {
  z-index: 100000 !important;
}

/* 检测事件详情对话框样式 */
.detection-event-dialog.el-dialog {
  border-radius: 8px !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3) !important;
  overflow: hidden !important;
}

.detection-event-dialog .el-dialog__header {
  padding: 20px 24px 16px !important;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  border-bottom: none !important;
  margin: 0 !important;
}

.detection-event-dialog .el-dialog__title {
  color: white !important;
  font-weight: 600 !important;
  font-size: 18px !important;
  line-height: 1.4 !important;
}

.detection-event-dialog .el-dialog__headerbtn {
  top: 20px !important;
  right: 24px !important;
}

.detection-event-dialog .el-dialog__headerbtn .el-dialog__close {
  color: white !important;
  font-size: 18px !important;
}

.detection-event-dialog .el-dialog__body {
  padding: 24px !important;
  max-height: 75vh !important;
  overflow-y: auto !important;
  background-color: #ffffff !important;
}

.detection-event-dialog .el-dialog__footer {
  padding: 16px 24px 24px !important;
  background-color: #f8f9fa !important;
  border-top: 1px solid #e9ecef !important;
  text-align: right !important;
}

/* 确保对话框内容不被外部样式影响 */
.detection-event-dialog .event-detail {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif !important;
  line-height: 1.6 !important;
  color: #333333 !important;
}

.detection-event-dialog .el-descriptions {
  margin-bottom: 0 !important;
}

.detection-event-dialog .el-descriptions__label {
  font-weight: 600 !important;
  color: #495057 !important;
}

.detection-event-dialog .el-descriptions__content {
  color: #6c757d !important;
}

/* 防止表格样式被覆盖 */
.detection-event-dialog .el-table {
  font-size: 14px !important;
}

.detection-event-dialog .el-table th {
  background-color: #f8f9fa !important;
  color: #495057 !important;
  font-weight: 600 !important;
}

.detection-event-dialog .el-table td {
  border-bottom: 1px solid #e9ecef !important;
}

/* 防止按钮样式被覆盖 */
.detection-event-dialog .el-button {
  font-weight: 500 !important;
  border-radius: 4px !important;
  transition: all 0.2s ease !important;
}

.detection-event-dialog .el-button:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1) !important;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .detection-event-dialog.el-dialog {
    width: 95vw !important;
    margin: 0 auto !important;
  }

  .detection-event-dialog .el-dialog__body {
    padding: 16px !important;
    max-height: 70vh !important;
  }

  .detection-event-dialog .detail-section {
    padding: 16px !important;
    margin-top: 16px !important;
  }

  .detection-event-dialog .detail-section h4 {
    font-size: 14px !important;
  }

  .detection-event-dialog .el-descriptions {
    font-size: 12px !important;
  }

  .detection-image-preview-dialog.el-dialog {
    width: 95vw !important;
    margin: 0 auto !important;
  }
}

@media (max-width: 480px) {
  .detection-event-dialog.el-dialog {
    width: 98vw !important;
    top: 2vh !important;
  }

  .detection-event-dialog .el-dialog__header {
    padding: 16px 20px 12px !important;
  }

  .detection-event-dialog .el-dialog__title {
    font-size: 16px !important;
  }

  .detection-event-dialog .el-dialog__body {
    padding: 12px !important;
    max-height: 75vh !important;
  }

  .detection-event-dialog .status-operations,
  .detection-event-dialog .status-info {
    padding: 16px !important;
  }

  .detection-event-dialog .event-image-container {
    padding: 16px !important;
  }

  .detection-event-dialog .detail-image {
    max-height: 250px !important;
  }
}

.batch-operations {
  padding: 12px 16px;
  background-color: #f0f9ff;
  border: 1px solid #e1f5fe;
  border-radius: 6px;
  margin-bottom: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
}
</style> 