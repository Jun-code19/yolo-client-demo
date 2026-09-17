<template>
  <div class="push-config-container">
    <el-tabs v-model="activePanel" class="push-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="推送配置" name="configs">
    <div class="page-header">
      <div class="header-content">
        <h2>数据推送配置</h2>
        <p>管理数据推送配置，支持 HTTP、TCP、MQTT 等多种推送方式</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadPushConfigs" :loading="loading">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <el-icon>
            <Plus />
          </el-icon> 添加推送配置
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
                <Document />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ overview.total_configs || 0 }}</div>
              <div class="stat-label">总配置数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#67C23A">
                <CircleCheck />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ overview.enabled_configs || 0 }}</div>
              <div class="stat-label">启用配置</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#E6A23C">
                <CircleCheck />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ overview.push_stats?.total_success || 0 }}</div>
              <div class="stat-label">推送成功</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-content">
            <div class="stat-icon">
              <el-icon color="#F56C6C">
                <TrendCharts />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ overview.push_stats?.success_rate || 0 }}%</div>
              <div class="stat-label">成功率</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <el-card class="filter-card">
      <div class="filters">
        <el-select v-model="filterConfigId" placeholder="按检测配置筛选" clearable filterable style="width: 180px;"
          @change="loadPushConfigs">
          <el-option v-for="config in detectionConfigs" :key="config.config_id"
            :label="config.device_name || config.config_id" :value="config.config_id" />
        </el-select>

        <el-select v-model="filterMethod" placeholder="按推送方式筛选" clearable filterable style="width: 180px;"
          @change="filterPushConfigs">
          <el-option label="HTTP" value="http" />
          <el-option label="HTTPS" value="https" />
          <el-option label="TCP" value="tcp" />
          <el-option label="MQTT" value="mqtt" />
        </el-select>

        <el-select v-model="filterTag" placeholder="按标签筛选" clearable filterable style="width: 180px;" @change="filterPushConfigs">
          <el-option v-for="tag in allTags" :key="tag" :label="tag" :value="tag" />
        </el-select>
      </div>
    </el-card>


    <el-card>
      <el-table :data="pushConfigs" style="width: 100%; margin-top: 20px;" v-loading="loading">
        <el-table-column prop="push_name" label="推送名称" width="180" />
        <el-table-column prop="push_method" label="推送方式" width="100">
          <template #default="scope">
            <el-tag :type="getMethodTagType(scope.row.push_method)" effect="plain">
              {{ scope.row.push_method.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="200">
          <template #default="scope">
            <div class="tag-container">
              <el-tag v-for="tag in scope.row.tags" :key="tag" size="small" type="info" class="tag-item">
                {{ tag }}
              </el-tag>
              <span v-if="!scope.row.tags || scope.row.tags.length === 0">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="目标地址" min-width="200">
          <template #default="scope">
            <div v-if="scope.row.push_method === 'http' || scope.row.push_method === 'https'">
              <el-tooltip :content="scope.row.http_url" placement="top" :show-after="1000">
                <span>{{ formatUrl(scope.row.http_url) }}</span>
              </el-tooltip>
            </div>
            <div v-else-if="scope.row.push_method === 'tcp'">
              {{ scope.row.tcp_host }}:{{ scope.row.tcp_port }}
            </div>
            <div v-else-if="scope.row.push_method === 'mqtt'">
              MQTT: {{ scope.row.mqtt_broker }}:{{ scope.row.mqtt_port }} | {{ scope.row.mqtt_topic }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="状态" width="150">
          <template #default="scope">
            <el-tag :type="scope.row.enabled ? 'success' : 'info'" effect="light">
              {{ scope.row.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送统计" width="150">
          <template #default="scope">
            <div v-if="pushStats[scope.row.push_id]">
              成功: {{ pushStats[scope.row.push_id].success || 0 }}<br>
              失败: {{ pushStats[scope.row.push_id].fail || 0 }}
            </div>
            <div v-else>无数据</div>
          </template>
        </el-table-column>
        <el-table-column label="最近推送" width="180">
          <template #default="scope">
            <div v-if="pushStats[scope.row.push_id] && pushStats[scope.row.push_id].last_success">
              {{ formatTime(pushStats[scope.row.push_id].last_success) }}
            </div>
            <div v-else-if="scope.row.last_push_time">
              {{ formatTime(scope.row.last_push_time) }}
            </div>
            <div v-else>-</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="scope">
            <el-button-group>
              <el-button size="small" type="info" @click="testPushConfig(scope.row)">
                测试
              </el-button>
              <el-button size="small" :type="scope.row.enabled ? 'warning' : 'success'"
                @click="togglePushConfig(scope.row)">
                {{ scope.row.enabled ? '停用' : '启用' }}
              </el-button>
              <el-button size="small" type="primary" @click="openEditDialog(scope.row)">
                编辑
              </el-button>
              <el-button size="small" type="danger" @click="confirmDelete(scope.row)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination" v-if="totalCount > 0">
        <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :page-sizes="[20, 50, 100, 200]"
          :total="totalCount" layout="prev, pager, next, jumper, ->, total, sizes" @size-change="handleSizeChange"
          @current-change="handleCurrentChange" />
      </div>
    </el-card>
      </el-tab-pane>

      <el-tab-pane label="推送记录" name="logs">
        <PushLogPanel ref="pushLogPanelRef" :push-options="pushConfigs" />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建/编辑推送配置对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑推送配置' : '创建推送配置'" width="50%" top="5vh" :z-index="999999" append-to-body class="high-priority-dialog">
      <el-form ref="pushFormRef" :model="pushForm" label-width="120px" :rules="formRules">
        <el-form-item label="推送名称" prop="push_name">
          <el-input v-model="pushForm.push_name" placeholder="请输入推送配置名称" />
        </el-form-item>

        <el-form-item label="标签" prop="tags">
          <el-select v-model="pushForm.tags" multiple filterable allow-create default-first-option
            placeholder="请选择或输入标签（可多选）" style="width: 100%;" popper-append-to-body>
            <el-option-group
              v-for="group in pushTagGroups"
              :key="group.label"
              :label="group.label"
            >
              <el-option
                v-for="tag in group.tags"
                :key="tag.value"
                :label="tag.label"
                :value="tag.value"
              />
            </el-option-group>
          </el-select>
          <div class="form-help-text">
            标签用于将推送配置应用于不同的数据源，例如：detection、device_123、alarm
          </div>
        </el-form-item>

        <el-form-item label="检测配置" prop="config_id">
          <el-select v-model="pushForm.config_id" placeholder="选择关联的检测配置（可选）" clearable filterable style="width: 100%;" popper-append-to-body>
            <el-option v-for="config in detectionConfigs" :key="config.config_id"
              :label="config.device_name || config.config_id" :value="config.config_id" />
          </el-select>
          <div class="form-help-text">
            可以不绑定特定检测配置，而是通过标签关联到不同的数据源
          </div>
        </el-form-item>

        <el-form-item label="推送方式" prop="push_method">
          <el-select v-model="pushForm.push_method" placeholder="选择推送方式" style="width: 100%;"
            @change="handleMethodChange" popper-append-to-body>
            <el-option label="HTTP" value="http" />
            <el-option label="HTTPS" value="https" />
            <el-option label="TCP" value="tcp" />
            <el-option label="MQTT" value="mqtt" />
          </el-select>
        </el-form-item>

        <!-- HTTP/HTTPS 特有字段 -->
        <template v-if="pushForm.push_method === 'http' || pushForm.push_method === 'https'">
          <el-form-item label="推送URL" prop="http_url">
            <el-input v-model="pushForm.http_url" placeholder="请输入HTTP推送URL" />
          </el-form-item>
          <el-form-item label="请求方法" prop="http_method">
            <el-select v-model="pushForm.http_method" placeholder="选择HTTP请求方法" style="width: 100%;" popper-append-to-body>
              <el-option label="POST" value="POST" />
              <el-option label="PUT" value="PUT" />
            </el-select>
          </el-form-item>
        </template>

        <!-- TCP 特有字段 -->
        <template v-if="pushForm.push_method === 'tcp'">
          <el-form-item label="TCP主机" prop="tcp_host">
            <el-input v-model="pushForm.tcp_host" placeholder="请输入TCP服务器主机" />
          </el-form-item>
          <el-form-item label="TCP端口" prop="tcp_port">
            <el-input-number v-model="pushForm.tcp_port" :min="1" :max="65535" placeholder="请输入TCP服务器端口"
              style="width: 100%;" />
          </el-form-item>
        </template>

        <!-- MQTT 特有字段 -->
        <template v-if="pushForm.push_method === 'mqtt'">
          <el-form-item label="MQTT代理" prop="mqtt_broker">
            <el-input v-model="pushForm.mqtt_broker" placeholder="请输入MQTT代理服务器地址" />
          </el-form-item>
          <el-form-item label="MQTT端口" prop="mqtt_port">
            <el-input-number v-model="pushForm.mqtt_port" :min="1" :max="65535" :step="1" placeholder="请输入MQTT端口"
              style="width: 100%;" />
          </el-form-item>
          <el-form-item label="MQTT主题" prop="mqtt_topic">
            <el-input v-model="pushForm.mqtt_topic" placeholder="请输入MQTT主题" />
          </el-form-item>
          <el-form-item label="MQTT用户名">
            <el-input v-model="pushForm.mqtt_username" placeholder="请输入MQTT用户名（可选）" />
          </el-form-item>
          <el-form-item label="MQTT密码">
            <el-input v-model="pushForm.mqtt_password" placeholder="请输入MQTT密码（可选）" type="password" show-password />
          </el-form-item>
          <el-form-item label="启用TLS">
            <el-switch v-model="pushForm.mqtt_use_tls" />
          </el-form-item>
        </template>

        <!-- 通用字段 -->
        <el-form-item label="包含图像数据">
          <el-switch v-model="pushForm.include_image" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="savePushConfig" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed } from 'vue';
import { dataPushApi } from '../../api/data_push';
import { detectionConfigApi } from '../../api/detection';
import { PUSH_TAG_GROUPS, COMMON_PUSH_TAGS } from '@/constants/pushTags';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Refresh, Document, CircleCheck, TrendCharts } from '@element-plus/icons-vue';
import PushLogPanel from './PushLogPanel.vue';

export default {
  name: 'PushConfig',
  components: {
    Plus,
    Refresh,
    Document,
    CircleCheck,
    TrendCharts,
    PushLogPanel
  },
  setup() {
    const pushConfigs = ref([]);
    const detectionConfigs = ref([]);
    const filterConfigId = ref('');
    const filterMethod = ref('');
    const filterTag = ref('');
    const pushStats = ref({});
    const overview = ref({});
    const loading = ref(false);
    const saving = ref(false);
    const dialogVisible = ref(false);
    const isEdit = ref(false);
    const activePanel = ref('configs');
    const pushLogPanelRef = ref(null);

    // 分页相关
    const currentPage = ref(1);
    const pageSize = ref(20);
    const totalCount = ref(0);
    const pushForm = reactive({
      push_id: '',
      push_name: '',
      config_id: '',
      tags: [],
      push_method: 'http',
      http_url: '',
      http_method: 'POST',
      tcp_host: '',
      tcp_port: 1883,
      mqtt_broker: '',
      mqtt_port: 1883,
      mqtt_topic: '',
      mqtt_username: '',
      mqtt_password: '',
      mqtt_use_tls: false,
      include_image: false
    });
    const pushFormRef = ref(null)

    const pushTagGroups = PUSH_TAG_GROUPS

    const allTags = computed(() => {
      const tags = new Set(COMMON_PUSH_TAGS);
      pushConfigs.value.forEach(config => {
        if (config.tags && Array.isArray(config.tags)) {
          config.tags.forEach(tag => tags.add(tag));
        }
      });
      return Array.from(tags);
    });

    const formRules = {
      push_name: [
        { required: true, message: '请输入推送名称', trigger: 'blur' }
      ],
      push_method: [
        { required: true, message: '请选择推送方式', trigger: 'change' }
      ],
      http_url: [
        { required: true, message: '请输入HTTP推送URL', trigger: 'blur' }
      ],
      tcp_host: [
        { required: true, message: '请输入TCP服务器主机', trigger: 'blur' }
      ],
      tcp_port: [
        { required: true, message: '请输入TCP服务器端口', trigger: 'blur' }
      ],
      mqtt_broker: [
        { required: true, message: '请输入MQTT代理服务器地址', trigger: 'blur' }
      ],
      mqtt_topic: [
        { required: true, message: '请输入MQTT主题', trigger: 'blur' }
      ]
    };

    const loadPushConfigs = async () => {
      loading.value = true;
      try {
        if (detectionConfigs.value.length === 0) {
          const configResponse = await detectionConfigApi.getConfigs();
          detectionConfigs.value = configResponse.data.data || [];
        }

        // 构建查询参数
        const skip = (currentPage.value - 1) * pageSize.value;
        const params = {
          skip,
          limit: pageSize.value
        };

        // 添加筛选条件
        if (filterConfigId.value) {
          params.config_id = filterConfigId.value;
        }
        if (filterTag.value) {
          params.tag = filterTag.value;
        }
        if (filterMethod.value) {
          params.method = filterMethod.value;
        }

        const response = await dataPushApi.getPushConfigs(params);
        if (response.data && response.data.data) {
          pushConfigs.value = response.data.data;
          totalCount.value = response.data.total;
          await loadPushStats();
        }
      } catch (error) {
        // console.error('加载推送配置失败:', error);
        ElMessage.error('加载推送配置失败');
      } finally {
        loading.value = false;
      }
    };

    const loadOverview = async () => {
      try {
        const response = await dataPushApi.getPushOverview();
        if (response.data && response.data.data) {
          overview.value = response.data.data;
        }
      } catch (error) {
        // console.error('加载概览统计失败:', error);
      }
    };

    const loadPushStats = async () => {
      try {
        const response = await dataPushApi.getPushStats();
        pushStats.value = response.data?.data || response.data || {};
      } catch (error) {
        // 统计来自检测服务(8080)，未启动时仅影响内存计数
      }
    };

    const handleTabChange = (tabName) => {
      if (tabName === 'logs' && pushLogPanelRef.value?.loadLogs) {
        pushLogPanelRef.value.loadLogs();
      }
    };

    const filterPushConfigs = () => {
      currentPage.value = 1; // 重置到第一页
      loadPushConfigs(); // 重新加载数据
    };

    const openCreateDialog = () => {
      isEdit.value = false;
      resetForm();
      dialogVisible.value = true;
    };

    const openEditDialog = (row) => {
      isEdit.value = true;
      resetForm();
      Object.keys(pushForm).forEach(key => {
        if (row[key] !== undefined) {
          pushForm[key] = row[key];
        }
      });
      dialogVisible.value = true;
    };

    const resetForm = () => {
      pushForm.push_id = '';
      pushForm.push_name = '';
      pushForm.config_id = '';
      pushForm.tags = [];
      pushForm.push_method = 'http';
      pushForm.http_url = '';
      pushForm.http_method = 'POST';
      pushForm.tcp_host = '';
      pushForm.tcp_port = 1883;
      pushForm.mqtt_broker = '';
      pushForm.mqtt_port = 1883;
      pushForm.mqtt_topic = '';
      pushForm.mqtt_username = '';
      pushForm.mqtt_password = '';
      pushForm.mqtt_use_tls = false;
      pushForm.include_image = false;
    };

    const handleMethodChange = () => {
      if (pushForm.value) {
        pushForm.value.clearValidate();
      }
    };

    const savePushConfig = async () => {
      if (!pushFormRef.value) return

      await pushFormRef.value.validate(async (valid) => {
        if (valid) {
          saving.value = true;
          try {
            if (isEdit.value) {
              const pushId = pushForm.push_id;
              const updateData = { ...pushForm };
              delete updateData.push_id;
              await dataPushApi.updatePushConfig(pushId, updateData);
              ElMessage.success('推送配置已更新');
            } else {
              await dataPushApi.createPushConfig(pushForm);
              ElMessage.success('推送配置已创建');
            }
            dialogVisible.value = false;
            await loadPushConfigs();
            await loadOverview();
          } catch (error) {
            // console.error('保存推送配置失败:', error);
            ElMessage.error(`保存推送配置失败: ${error.response?.data?.detail || error.message}`);
          } finally {
            saving.value = false;
          }
        }
      });
    };

    const togglePushConfig = async (row) => {
      try {
        await dataPushApi.updatePushConfig(row.push_id, { enabled: !row.enabled });
        ElMessage.success(`已${row.enabled ? '启用' : '禁用'}推送配置`);
        await loadPushConfigs();
        await loadOverview();
      } catch (error) {
        // console.error('更新推送配置状态失败:', error);
        ElMessage.error('更新推送配置状态失败');
        row.enabled = !row.enabled;
      }
    };

    const testPushConfig = async (row) => {
      try {
        loading.value = true;
        const response = await dataPushApi.testPushConfig(row.push_id);
        if (response.data.status === 'success') {
          ElMessage.success('推送测试成功!');
        } else {
          ElMessage.warning(response.data.message || '推送测试失败!');
        }
        await loadPushStats();
        if (pushLogPanelRef.value?.loadLogs) {
          pushLogPanelRef.value.loadLogs();
        }
      } catch (error) {
        // console.error('测试推送配置失败:', error);
        ElMessage.error(`测试推送配置失败: ${error.response?.data?.detail || error.message}`);
      } finally {
        loading.value = false;
      }
    };

    const confirmDelete = (row) => {
      ElMessageBox.confirm(
        '确定要删除此推送配置吗?',
        '删除确认',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
        .then(async () => {
          try {
            await dataPushApi.deletePushConfig(row.push_id);
            ElMessage.success('推送配置已删除');
            await loadPushConfigs();
            await loadOverview();
          } catch (error) {
            // console.error('删除推送配置失败:', error);
            ElMessage.error('删除推送配置失败');
          }
        })
        .catch(() => {
          // 用户取消操作
        });
    };

    const formatUrl = (url) => {
      if (!url) return '-';
      if (url.length > 40) {
        return url.substring(0, 37) + '...';
      }
      return url;
    };

    const formatTime = (timeStr) => {
      if (!timeStr) return '-';
      const date = new Date(timeStr);
      return date.toLocaleString();
    };

    const getMethodTagType = (method) => {
      switch (method) {
        case 'http': return 'success';
        case 'https': return 'success';
        case 'tcp': return 'primary';
        case 'mqtt': return 'warning';
        default: return 'info';
      }
    };

    // 分页处理方法
    const handleSizeChange = (val) => {
      pageSize.value = val;
      loadPushConfigs(); // 重新加载数据
    };

    const handleCurrentChange = (val) => {
      currentPage.value = val;
      loadPushConfigs(); // 重新加载数据
    };

    onMounted(() => {
      loadPushConfigs();
      loadOverview();
      // const statsInterval = setInterval(() => {
      //   loadPushStats();
      //   loadOverview();
      // }, 30000);

      // return () => {
      //   clearInterval(statsInterval);
      // };
    });

    return {
      pushFormRef,
      activePanel,
      pushLogPanelRef,
      handleTabChange,
      pushConfigs,
      detectionConfigs,
      filterConfigId,
      filterMethod,
      filterTag,
      pushStats,
      overview,
      loading,
      saving,
      dialogVisible,
      isEdit,
      pushForm,
      formRules,
      pushTagGroups,
      allTags,
      currentPage,
      pageSize,
      totalCount,
      loadPushConfigs,
      loadOverview,
      filterPushConfigs,
      openCreateDialog,
      openEditDialog,
      handleMethodChange,
      savePushConfig,
      togglePushConfig,
      testPushConfig,
      confirmDelete,
      formatUrl,
      formatTime,
      getMethodTagType,
      handleSizeChange,
      handleCurrentChange
    };
  }
};
</script>

<style scoped>
.push-config-container {
  padding: 20px;
}

.push-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.push-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 12px;
  padding-top: 4px;
}

.tag-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag-item {
  margin-right: 4px;
  margin-bottom: 4px;
}

.form-help-text code {
  font-size: 11px;
  color: #606266;
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
}

.form-help-text {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

.header-content p {
  max-width: 640px;
}

.filter-card {
  margin-bottom: 20px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

/* 分页样式 */
.pagination {
  margin-top: 20px;
  text-align: right;
}

/* 统计卡片样式 */
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
  font-size: 32px;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  color: #303133;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  line-height: 1.4;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}
</style>