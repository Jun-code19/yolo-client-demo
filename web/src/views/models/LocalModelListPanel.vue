<template>
  <div class="local-model-panel">
    <div class="panel-header">
      <el-alert type="info" show-icon :closable="false" class="info-alert">
        <template #title>
          {{ uploadPolicy.hint || '管理本地上传的检测模型。' }}
          <span v-if="uploadPolicy.inference_backend" class="policy-tag">
            推理：{{ uploadPolicy.inference_backend }}
          </span>
        </template>
      </el-alert>
      <div class="panel-actions">
        <el-button type="primary" @click="showUploadDialog">上传新模型</el-button>
        <el-button @click="loadModels">刷新</el-button>
      </div>
    </div>

    <!-- 模型列表 -->
    <el-card v-loading="loading">
      <el-tabs type="border-card">
        <!-- 按模型类型分组展示 -->
        <el-tab-pane v-for="(models, type) in groupedModels" :key="type" :label="getModelTypeName(type)">
          <el-table :data="models" border style="width: 100%">
            <el-table-column prop="models_name" label="模型名称" sortable width="180" />
            <el-table-column prop="format" label="格式" width="100">
              <template #default="scope">
                <el-tag>{{ scope.row.format.toUpperCase() }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="file_size" label="文件大小" sortable width="120">
              <template #default="scope">
                {{ formatFileSize(scope.row.file_size) }}
              </template>
            </el-table-column>
            <el-table-column prop="upload_time" label="上传时间" sortable width="180">
              <template #default="scope">
                {{ formatDate(scope.row.upload_time) }}
              </template>
            </el-table-column>
            <el-table-column prop="is_active" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.is_active ? 'success' : 'info'">
                  {{ scope.row.is_active ? '已激活' : '未激活' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="340" fixed="right">
              <template #default="scope">
                <el-button-group>
                  <el-button type="info" size="small" @click="viewModelDetails(scope.row)">
                    详情
                  </el-button>
                  <el-button
                    type="success"
                    size="small"
                    :loading="downloadingModelId === scope.row.models_id"
                    @click="downloadModelFile(scope.row)"
                  >
                    下载
                  </el-button>
                  <el-button type="primary" size="small" @click="editModel(scope.row)">
                    编辑
                  </el-button>
                  <el-button :type="scope.row.is_active ? 'warning' : 'success'" size="small"
                    @click="toggleModelActive(scope.row)">
                    {{ scope.row.is_active ? '停用' : '启用' }}
                  </el-button>
                  <el-button type="danger" size="small" @click="confirmDelete(scope.row)">
                    删除
                  </el-button>
                </el-button-group>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 如果没有模型 -->
        <div v-if="!Object.keys(groupedModels).length" class="no-data">
          <el-empty :description="emptyModelHint"></el-empty>
        </div>
      </el-tabs>
    </el-card>

    <!-- 上传模型对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传模型" width="30%" top="5vh" :z-index="999999" append-to-body
      class="high-priority-dialog upload-model-dialog">
      <el-form :model="uploadForm" label-width="80px" :rules="uploadRules" ref="uploadFormRef"
        class="upload-model-form">
        <el-form-item label="模型名称" prop="modelName">
          <el-input v-model="uploadForm.modelName" placeholder="请输入模型名称"></el-input>
        </el-form-item>

        <el-form-item label="模型类型" prop="modelType">
          <el-select v-model="uploadForm.modelType" placeholder="请选择模型类型" style="width: 100%" popper-append-to-body>
            <el-option
              v-for="opt in modelTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <p v-if="uploadModelTypeHint" class="field-hint">{{ uploadModelTypeHint }}</p>
        </el-form-item>

        <el-form-item label="模型文件" prop="modelFile">
          <el-upload class="model-upload" drag action="#" :auto-upload="false" :limit="1"
            :accept="uploadAcceptAttr" :on-change="handleFileChange" :on-exceed="handleExceed"
            :on-remove="handleRemove" :file-list="uploadForm.fileList" :before-upload="beforeUpload">
            <div class="upload-dragger-inner">
              <el-icon class="el-icon--upload"><upload-filled /></el-icon>
              <div class="el-upload__text">
                拖拽文件到此处或<em>点击上传</em>
              </div>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                允许格式：{{ uploadPolicy.extensions.join(' / ') || '.onnx / .rknn' }}（Ultralytics 导出 YOLO ONNX）<br>
                边缘 RKNN/ONNX 仅支持「目标检测」「人脸检测」。无内置类别时：参数名 <code>classes</code>，参数值如 <code>{"0":"person"}</code>；RKNN 任意类型均必填 classes<br>
                <span style="color: #f56c6c;">单文件 ≤ 2GB；上传完成后还需「校验加载」，请稍候勿关页面</span>
              </div>
            </template>
          </el-upload>

          <!-- 上传进度显示 -->
          <div v-if="uploadProgress.visible" class="upload-progress">
            <div class="progress-info">
              <span>{{ uploadProgress.fileName }}</span>
              <span>{{ uploadProgress.percent }}%</span>
            </div>
            <el-progress :percentage="uploadProgress.percent" :status="uploadProgress.status"
              :show-text="false"></el-progress>
            <div class="progress-details">
              <span>已上传: {{ formatFileSize(uploadProgress.loaded) }}</span>
              <span>总大小: {{ formatFileSize(uploadProgress.total) }}</span>
              <span v-if="uploadProgress.speed">速度: {{ uploadProgress.speed }}</span>
              <span v-if="uploadProgress.remainingTime">剩余时间: {{ uploadProgress.remainingTime }}</span>
            </div>
            <p v-if="uploadProgress.phase === 'processing'" class="processing-hint">
              文件已传完，正在校验并加载模型（可能需要 1～3 分钟）…
            </p>
          </div>
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="uploadForm.description" placeholder="可选"></el-input>
        </el-form-item>

        <el-form-item label="模型参数" class="model-params-form-item">
          <div class="model-params-panel">
            <p class="model-params-hint">
              可选。RKNN 必填 <code>classes</code>；无内置类别时在参数值填 JSON，如 <code>{"0":"person"}</code>
            </p>
            <div v-if="uploadForm.parameters.length" class="model-params-table">
              <div class="model-params-row model-params-row--head">
                <span>参数名</span>
                <span>参数值</span>
                <span class="col-action">操作</span>
              </div>
              <div v-for="(param, index) in uploadForm.parameters" :key="index" class="model-params-row">
                <el-input v-model="param.key" placeholder="classes" clearable />
                <el-input v-model="param.value" placeholder='{"0":"person"}' clearable />
                <el-button link type="danger" @click="removeParam(index)">删除</el-button>
              </div>
            </div>
            <div class="model-params-actions">
              <el-button link type="primary" @click="addParam">+ 添加一行</el-button>
              <el-button link type="primary" @click="fillClassesParamPreset">填入 classes 示例</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="cancelUpload">{{ uploading ? '取消上传' : '取消' }}</el-button>
          <el-button type="primary" @click="uploadModel" :loading="uploading">
            {{ uploadButtonLabel }}
          </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 模型详情对话框 -->
    <el-dialog v-model="detailsDialogVisible" title="模型详情" width="50%" top="5vh" :z-index="999999" append-to-body
      class="high-priority-dialog">
      <div v-if="selectedModel" class="model-details">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="模型ID">{{ selectedModel.models_id }}</el-descriptions-item>
          <el-descriptions-item label="模型名称">{{ selectedModel.models_name }}</el-descriptions-item>
          <el-descriptions-item label="模型类型">{{ getModelTypeName(selectedModel.models_type) }}</el-descriptions-item>
          <el-descriptions-item label="文件格式">{{ selectedModel.format.toUpperCase() }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatFileSize(selectedModel.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedModel.is_active ? 'success' : 'info'">
              {{ selectedModel.is_active ? '已激活' : '未激活' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="上传时间">{{ formatDate(selectedModel.upload_time) }}</el-descriptions-item>
          <el-descriptions-item label="最后使用">{{ selectedModel.last_used ? formatDate(selectedModel.last_used) : '暂未使用'
            }}</el-descriptions-item>
          <el-descriptions-item label="文件路径" :span="2">{{ selectedModel.file_path }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ selectedModel.description || '暂无描述' }}</el-descriptions-item>
          <!-- 新增的类别信息展示 -->
          <el-descriptions-item label="检测类别" :span="2">
            <div>
              <div v-if="Array.isArray(selectedModel.models_classes) && selectedModel.models_classes.length > 5">
                <el-tag v-for="(name, index) in selectedModel.models_classes.slice(0, 5)" :key="index"
                  style="margin-right: 5px;">
                  {{ name.name }}
                </el-tag>
                <el-link type="primary" @click="showAllClasses">查看所有类别，共计{{ selectedModel.models_classes.length
                  }}个</el-link>
              </div>
              <div v-else>
                <el-tag v-for="(name, index) in selectedModel.models_classes" :key="index" style="margin-right: 5px;">
                  {{ name.name }}
                </el-tag>
              </div>
            </div>
          </el-descriptions-item>
        </el-descriptions>

        <h3 class="mt-4">模型参数</h3>
        <el-table v-if="selectedModel.parameters && Object.keys(selectedModel.parameters).length"
          :data="formatParameters(selectedModel.parameters)" border style="width: 100%" class="mt-2">
          <el-table-column prop="key" label="参数名" width="200" />
          <el-table-column prop="value" label="参数值" />
        </el-table>
        <el-empty v-else description="暂无参数信息"></el-empty>
      </div>
    </el-dialog>

    <!-- 编辑模型对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑模型信息" width="30%" top="5vh" :z-index="999999" append-to-body
      class="high-priority-dialog">
      <el-form :model="editForm" label-width="80px" :rules="editRules" ref="editFormRef">
        <el-form-item label="模型名称" prop="models_name">
          <el-input v-model="editForm.models_name" placeholder="请输入模型名称"></el-input>
        </el-form-item>

        <el-form-item label="模型类型" prop="models_type">
          <el-select v-model="editForm.models_type" placeholder="请选择模型类型" style="width: 100%" popper-append-to-body>
            <el-option
              v-for="opt in modelTypeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <p v-if="editModelTypeHint" class="field-hint">{{ editModelTypeHint }}</p>
        </el-form-item>

        <el-form-item v-if="!isEdgeInference" label="IS_GPU" prop="is_gpu" style="display: flex; align-items: center;">
          <el-switch v-model="editForm.is_gpu" />
          <el-tooltip content="使用GPU进行推理,主机不支持则不起作用" placement="right">
            <el-icon><InfoFilled /></el-icon>
          </el-tooltip>
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="请输入模型描述（可选）"></el-input>
        </el-form-item>

        <el-form-item label="模型参数" class="model-params-form-item">
          <div class="model-params-panel">
            <p class="model-params-hint">修改自定义键值；参数值支持 JSON 字符串</p>
            <div v-if="editForm.parameters.length" class="model-params-table">
              <div class="model-params-row model-params-row--head">
                <span>参数名</span>
                <span>参数值</span>
                <span class="col-action">操作</span>
              </div>
              <div v-for="(param, index) in editForm.parameters" :key="index" class="model-params-row">
                <el-input v-model="param.key" placeholder="classes" clearable />
                <el-input v-model="param.value" placeholder='{"0":"person"}' clearable />
                <el-button link type="danger" @click="removeEditParam(index)">删除</el-button>
              </div>
            </div>
            <div class="model-params-actions">
              <el-button link type="primary" @click="addEditParam">+ 添加一行</el-button>
              <el-button link type="primary" @click="fillEditClassesParamPreset">填入 classes 示例</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="updateModel" :loading="updating">更新</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 查看所有类别对话框 -->
    <el-dialog v-model="allClassesDialogVisible" title="所有检测类别" width="80%" draggable top="5vh" :z-index="999999"
      append-to-body class="high-priority-dialog">
      <div style="max-height: 500px; overflow-y: auto;">
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;">
          <div v-for="(item, index) in selectedModel.models_classes" :key="index" :style="{
            display: 'flex',
            justifyContent: 'space-between',
            border: hoveredIndex === index ? '1px solid #409EFF' : '1px solid #dcdfe6',
            padding: '10px',
            borderRadius: '4px',
            transition: 'all 0.3s',
            cursor: 'pointer'
          }" @mouseover="hoveredIndex = index" @mouseleave="hoveredIndex = null">
            <span
              :style="{ borderRight: '1px solid #dcdfe6', paddingRight: '10px', color: hoveredIndex === index ? '#409EFF' : 'inherit' }">
              {{ item.id }}
            </span>
            <span :style="{ color: hoveredIndex === index ? '#409EFF' : 'inherit' }">{{ item.name }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="allClassesDialogVisible = false">关闭</el-button>
        </span>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, InfoFilled } from '@element-plus/icons-vue'
import deviceApi from '@/api/device'

const MODEL_TYPE_LABELS = {
  object_detection: '目标检测',
  face: '人脸检测',
  segmentation: '图像分割',
  keypoint: '关键点检测',
  pose: '姿态估计',
  other: '其他类型'
}

const MODEL_TYPE_HINTS = {
  object_detection: 'YOLO/ONNX 目标检测；边缘盒请使用 .onnx 或 .rknn。',
  face: '人脸检测；若 ONNX 无 metadata，请在参数中填写 classes。',
  segmentation: '仅 ultralytics 开发环境；边缘 ONNX 不支持。',
  pose: '仅 ultralytics 开发环境；边缘 ONNX 不支持。',
  keypoint: '仅 ultralytics 开发环境。',
  other: '仅 ultralytics 开发环境。'
}

const MODEL_TYPE_ORDER = [
  'object_detection',
  'face',
  'segmentation',
  'keypoint',
  'pose',
  'other'
]

const defaultUploadPolicy = () => ({
  inference_backend: 'onnx',
  extensions: ['.onnx', '.rknn'],
  model_types: ['object_detection', 'face'],
  hint: '边缘盒 ONNX/RKNN 仅支持「目标检测」「人脸检测」两种类型。'
})

const uploadPolicy = ref(defaultUploadPolicy())

const modelTypeOptions = computed(() => {
  const allowed = new Set(uploadPolicy.value.model_types || [])
  return MODEL_TYPE_ORDER.filter((value) => allowed.has(value)).map((value) => ({
    value,
    label: MODEL_TYPE_LABELS[value] || value
  }))
})

/** 上传默认类型：优先目标检测，避免后端 sorted 把 face 排到第一位 */
const defaultUploadModelType = () => {
  const allowed = uploadPolicy.value.model_types || []
  if (allowed.includes('object_detection')) return 'object_detection'
  return allowed[0] || ''
}

const uploadAcceptAttr = computed(() =>
  (uploadPolicy.value.extensions || ['.onnx', '.rknn']).join(',')
)

const emptyModelHint = computed(() => {
  const exts = uploadPolicy.value.extensions?.join(' / ') || '.onnx / .rknn'
  return `暂无本地模型，请上传 ${exts}`
})

const isEdgeInference = computed(() =>
  ['onnx', 'rknn'].includes(uploadPolicy.value.inference_backend)
)

const uploadButtonLabel = computed(() => {
  if (!uploading.value) return '上传'
  if (uploadProgress.value.phase === 'processing') return '校验加载中…'
  return '上传中…'
})

const formatApiDetail = (detail) => {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || item.message || JSON.stringify(item)).join('; ')
  }
  if (typeof detail === 'object') return detail.msg || detail.message || JSON.stringify(detail)
  return String(detail)
}

const buildUploadParameters = (rows) => {
  const params = {}
  for (const p of rows || []) {
    const key = String(p.key || '').trim()
    const rawValue = String(p.value ?? '').trim()
    if (!key || !rawValue) continue
    try {
      params[key] = JSON.parse(rawValue)
    } catch {
      params[key] = rawValue
    }
  }
  const classes = params.classes
  if (classes && typeof classes === 'object' && classes.classes && typeof classes.classes === 'object') {
    params.classes = classes.classes
  }
  return params
}

const hasModelClassesParam = (params) => {
  const classes = params?.classes
  if (!classes) return false
  if (typeof classes === 'string') return classes.trim().length > 0
  if (Array.isArray(classes)) return classes.length > 0
  if (typeof classes === 'object') return Object.keys(classes).length > 0
  return false
}

const uploadModelTypeHint = computed(() => MODEL_TYPE_HINTS[uploadForm.value.modelType] || '')
const editModelTypeHint = computed(() => MODEL_TYPE_HINTS[editForm.value.models_type] || '')

// 数据加载状态
const loading = ref(false)
const uploading = ref(false)
const updating = ref(false)
const downloadingModelId = ref(null)

// 模型列表
const models = ref([])

// 对话框显示状态
const uploadDialogVisible = ref(false)
const detailsDialogVisible = ref(false)
const editDialogVisible = ref(false)
const allClassesDialogVisible = ref(false);

// 选中的模型
const selectedModel = ref(null)

// 上传表单
const uploadFormRef = ref(null)
const uploadForm = ref({
  modelName: '',
  modelType: '',
  description: '',
  modelFile: null,
  fileList: [],
  parameters: []
})

// 编辑表单
const editFormRef = ref(null)
const editForm = ref({
  models_name: '',
  models_type: '',
  is_gpu: false,
  description: '',
  parameters: []
})

// 表单验证规则
const uploadRules = {
  modelName: [
    { required: true, message: '请输入模型名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  modelType: [
    { required: true, message: '请选择模型类型', trigger: 'change' }
  ],
  modelFile: [
    {
      validator: (_rule, _value, callback) => {
        if (uploadForm.value.modelFile) callback()
        else callback(new Error('请上传模型文件'))
      },
      trigger: 'change'
    }
  ]
}

// 编辑表单验证规则
const editRules = {
  models_name: [
    { required: true, message: '请输入模型名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  models_type: [
    { required: true, message: '请选择模型类型', trigger: 'change' }
  ]
}

// 新增的 hoveredIndex 变量
const hoveredIndex = ref(null);

// 上传进度追踪
const uploadProgress = ref({
  visible: false,
  phase: 'idle',
  percent: 0,
  status: '',
  fileName: '',
  loaded: 0,
  total: 0,
  speed: '',
  remainingTime: '',
  startTime: null
})

// 取消上传的控制器
let uploadController = null;

const isChinese = (str) => {
  return /[\u4e00-\u9fa5]/.test(str); // 正则表达式检查是否包含中文字符
}

// 按模型类型分组（仅本地模型，排除 VLM/API 远程模型）
const groupedModels = computed(() => {
  const groups = {}
  models.value
    .filter(model => model.models_type !== 'vlm' && model.format !== 'api')
    .forEach(model => {
      if (!groups[model.models_type]) {
        groups[model.models_type] = []
      }
      groups[model.models_type].push(model)
    })
  return groups
})

const isLocalModel = (model) => model.models_type !== 'vlm' && model.format !== 'api'

// 加载模型列表
const loadModels = async () => {
  loading.value = true
  try {
    const { data } = await deviceApi.getModels()
    models.value = (data || []).filter(isLocalModel)
  } catch (error) {
    // console.error('加载模型列表失败:', error)
    ElMessage.error('加载模型列表失败')
  } finally {
    loading.value = false
  }
}

const loadUploadPolicy = async () => {
  try {
    const { data } = await deviceApi.getModelUploadPolicy()
    if (data) {
      uploadPolicy.value = { ...defaultUploadPolicy(), ...data }
    }
  } catch {
    uploadPolicy.value = defaultUploadPolicy()
  }
}

// 初始化
onMounted(() => {
  loadUploadPolicy()
  loadModels()
})

// 显示上传对话框
const showUploadDialog = () => {
  uploadForm.value = {
    modelName: '',
    modelType: defaultUploadModelType(),
    description: '',
    modelFile: null,
    fileList: [],
    parameters: []
  }
  uploadProgress.value.visible = false
  uploadProgress.value.phase = 'idle'
  uploadDialogVisible.value = true
}

// 文件变更处理
const handleFileChange = (file, fileList) => {
  uploadForm.value.modelFile = file?.raw || null
  uploadForm.value.fileList = fileList.slice(-1)
  if (!uploadForm.value.modelName && file?.name) {
    uploadForm.value.modelName = file.name.replace(/\.(onnx|rknn|pt)$/i, '')
  }
  uploadFormRef.value?.validateField('modelFile').catch(() => {})
}

// 上传前检查
const beforeUpload = (file) => {
  // 检查文件大小 (2GB = 2 * 1024 * 1024 * 1024)
  const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
  if (file.size > maxSize) {
    ElMessage.error(`文件大小不能超过 2GB，当前文件大小为 ${formatFileSize(file.size)}`);
    return false;
  }

  // 检查文件格式
  const allowedFormats = uploadPolicy.value.extensions?.length
    ? uploadPolicy.value.extensions
    : ['.onnx', '.rknn']
  const fileName = file.name.toLowerCase()
  const isValidFormat = allowedFormats.some((format) => fileName.endsWith(format.toLowerCase()))

  if (!isValidFormat) {
    ElMessage.error(`请上传允许格式：${allowedFormats.join(' / ')}`)
    return false
  }

  // 大文件上传提示
  if (file.size > 100 * 1024 * 1024) { // 100MB以上
    ElMessage.warning('检测到大文件，上传可能需要较长时间，请耐心等待');
  }

  return true;
}

// 文件数量超出限制
const handleExceed = () => {
  ElMessage.warning('只能上传一个模型文件')
}

// 移除文件
const handleRemove = () => {
  uploadForm.value.modelFile = null
}

const CLASSES_PARAM_PRESET = { key: 'classes', value: '{"0":"person"}' }

const upsertClassesParam = (parameters) => {
  const row = parameters.find((p) => String(p.key || '').trim() === 'classes')
  if (row) {
    row.value = CLASSES_PARAM_PRESET.value
    return
  }
  parameters.push({ ...CLASSES_PARAM_PRESET })
}

// 添加参数
const addParam = () => {
  uploadForm.value.parameters.push({ key: '', value: '' })
}

const fillClassesParamPreset = () => {
  upsertClassesParam(uploadForm.value.parameters)
}

// 移除参数
const removeParam = (index) => {
  uploadForm.value.parameters.splice(index, 1)
}

// 上传模型
const uploadModel = async () => {
  if (!uploadFormRef.value) return

  await uploadFormRef.value.validate(async (valid) => {
    if (!valid) return

    if (!uploadForm.value.modelFile) {
      ElMessage.error('请上传模型文件')
      return
    }

    // 再次检查文件大小
    if (!beforeUpload(uploadForm.value.modelFile)) {
      return
    }

    const uploadParams = buildUploadParameters(uploadForm.value.parameters)
    const fileName = uploadForm.value.modelFile.name || ''
    const fileExt = fileName.slice(fileName.lastIndexOf('.')).toLowerCase()
    const needsClasses =
      fileExt === '.rknn' ||
      (fileExt === '.onnx' && uploadForm.value.modelType === 'face')
    if (needsClasses && !hasModelClassesParam(uploadParams)) {
      ElMessage.error(
        '缺少 classes 参数：请先点「添加参数」，参数名填 classes，参数值填 {"0":"face"}（须英文双引号）'
      )
      return
    }

    uploading.value = true

    // 初始化进度追踪
    uploadProgress.value = {
      visible: true,
      phase: 'upload',
      percent: 0,
      status: 'active',
      fileName: uploadForm.value.modelFile.name,
      loaded: 0,
      total: uploadForm.value.modelFile.size,
      speed: '',
      remainingTime: '',
      startTime: Date.now()
    }

    try {
      // 创建FormData
      const formData = new FormData()
      formData.append('models_file', uploadForm.value.modelFile)
      formData.append('models_name', uploadForm.value.modelName)
      formData.append('models_type', uploadForm.value.modelType)

      if (uploadForm.value.description) {
        formData.append('description', uploadForm.value.description)
      }

      if (Object.keys(uploadParams).length > 0) {
        formData.append('parameters', JSON.stringify(uploadParams))
      }

      // 创建上传控制器
      uploadController = new AbortController()

      // 发送请求，使用优化的上传API
      const response = await deviceApi.uploadModelWithProgress(formData, {
        signal: uploadController.signal,
        onUploadProgress: (progressEvent) => {
          updateUploadProgress(progressEvent)
        }
      })

      // 上传成功
      uploadProgress.value.status = 'success'
      uploadProgress.value.percent = 100

      const uploadedModelId = response.data?.models_id
      ElMessage.success(
        uploadedModelId ? `模型上传成功，ID：${uploadedModelId}` : '模型上传成功'
      )
      uploadDialogVisible.value = false

      // 延迟隐藏进度条
      setTimeout(() => {
        uploadProgress.value.visible = false
      }, 2000)

      loadModels() // 重新加载模型列表
    } catch (error) {
      // 检查是否是用户取消的请求
      if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        // 用户取消，不显示错误消息
        return
      }

      uploadProgress.value.status = 'exception'

      // 针对不同错误类型显示不同消息
      let errorMessage = '上传模型失败'
      if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
        errorMessage = '上传超时，请检查网络连接或尝试上传较小的文件'
      } else if (error.response?.status === 413) {
        errorMessage = '文件太大，请选择小于2GB的模型文件'
      } else if (error.response?.data?.detail) {
        errorMessage = `上传失败: ${formatApiDetail(error.response.data.detail)}`
      } else {
        errorMessage = `上传失败: ${error.message}`
      }

      ElMessage.error(errorMessage)

      // 延迟隐藏进度条
      setTimeout(() => {
        uploadProgress.value.visible = false
      }, 3000)
    } finally {
      uploading.value = false
      uploadController = null
    }
  })
}

// 更新上传进度
const updateUploadProgress = (progressEvent) => {
  const { loaded, total } = progressEvent
  const percent = Math.round((loaded / total) * 100)
  const currentTime = Date.now()
  const elapsedTime = (currentTime - uploadProgress.value.startTime) / 1000 // 秒

  uploadProgress.value.loaded = loaded
  uploadProgress.value.percent = percent

  if (total > 0 && loaded >= total) {
    uploadProgress.value.phase = 'processing'
    uploadProgress.value.percent = 100
  }

  if (elapsedTime > 1) { // 至少1秒后开始计算速度
    const speed = loaded / elapsedTime // 字节/秒
    uploadProgress.value.speed = formatSpeed(speed)

    if (speed > 0) {
      const remainingBytes = total - loaded
      const remainingSeconds = remainingBytes / speed
      uploadProgress.value.remainingTime = formatTime(remainingSeconds)
    }
  }
}

// 格式化速度
const formatSpeed = (bytesPerSecond) => {
  if (bytesPerSecond < 1024) {
    return `${bytesPerSecond.toFixed(0)} B/s`
  } else if (bytesPerSecond < 1024 * 1024) {
    return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  } else {
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`
  }
}

// 格式化时间
const formatTime = (seconds) => {
  if (seconds < 60) {
    return `${Math.round(seconds)}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = Math.round(seconds % 60)
    return `${minutes}分${remainingSeconds}秒`
  } else {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${minutes}分钟`
  }
}

// 取消上传
const cancelUpload = () => {
  if (uploading.value && uploadController) {
    // 取消正在进行的上传请求
    uploadController.abort()
    uploadController = null

    // 重置状态
    uploading.value = false
    uploadProgress.value.visible = false
    uploadProgress.value.status = 'exception'

    ElMessage.warning('上传已取消')
  }

  // 关闭对话框
  uploadDialogVisible.value = false

  // 重置表单
  uploadForm.value = {
    modelName: '',
    modelType: '',
    description: '',
    modelFile: null,
    fileList: [],
    parameters: []
  }
}

// 查看模型详情
const viewModelDetails = (model) => {
  // 深拷贝模型数据，避免直接引用
  const modelCopy = JSON.parse(JSON.stringify(model));

  // 将 models_classes 转换为数组（仅在不是数组时进行转换）
  if (modelCopy.models_classes && typeof modelCopy.models_classes === 'object' && !Array.isArray(modelCopy.models_classes)) {
    modelCopy.models_classes = Object.entries(modelCopy.models_classes).map(([key, value]) => ({
      id: key,
      name: value
    })); // 转换为数组格式
  }

  selectedModel.value = modelCopy; // 使用深拷贝的模型数据
  detailsDialogVisible.value = true;
}

// 显示所有类别对话框
const showAllClasses = () => {
  allClassesDialogVisible.value = true;
}

// 编辑模型
const editModel = (model) => {
  // 初始化编辑表单
  editForm.value = {
    models_name: model.models_name,
    models_type: model.models_type,
    is_gpu: model.is_gpu,
    description: model.description || '',
    parameters: formatParametersForEdit(model.parameters)
  }

  // 存储当前编辑的模型ID
  editForm.value.models_id = model.models_id

  editDialogVisible.value = true
}

// 格式化参数为编辑表单格式
const formatParametersForEdit = (params) => {
  if (!params) return []
  return Object.entries(params).map(([key, value]) => ({
    key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value)
  }))
}

// 添加编辑参数
const addEditParam = () => {
  editForm.value.parameters.push({ key: '', value: '' })
}

const fillEditClassesParamPreset = () => {
  upsertClassesParam(editForm.value.parameters)
}

// 移除编辑参数
const removeEditParam = (index) => {
  editForm.value.parameters.splice(index, 1)
}

// 更新模型
const updateModel = async () => {
  if (!editFormRef.value) return

  await editFormRef.value.validate(async (valid) => {
    if (!valid) return

    updating.value = true
    try {
      // 准备更新数据
      const updateData = {
        models_name: editForm.value.models_name,
        models_type: editForm.value.models_type,
        is_gpu: editForm.value.is_gpu,
        description: editForm.value.description
      }

      // 处理自定义参数
      if (editForm.value.parameters.length > 0) {
        const params = {}
        editForm.value.parameters.forEach(p => {
          if (p.key && p.value) {
            // 尝试解析JSON，如果失败则作为字符串处理
            try {
              params[p.key] = JSON.parse(p.value)
            } catch {
              params[p.key] = p.value
            }
          }
        })
        updateData.parameters = params
      }

      // 发送更新请求
      await deviceApi.updateModel(editForm.value.models_id, updateData)

      ElMessage.success('模型信息更新成功')
      editDialogVisible.value = false
      loadModels() // 重新加载模型列表
    } catch (error) {
      // console.error('更新模型失败:', error)
      ElMessage.error(`更新模型失败: ${error.response?.data?.detail || error.message}`)
    } finally {
      updating.value = false
    }
  })
}

// 构建下载文件名
const buildDownloadFilename = (model) => {
  const ext = model.format ? `.${String(model.format).replace(/^\./, '')}` : ''
  const safeName = String(model.models_name || 'model')
    .trim()
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'model'
  if (ext && safeName.toLowerCase().endsWith(ext.toLowerCase())) {
    return safeName
  }
  return `${safeName}${ext}`
}

// 下载模型文件
const downloadModelFile = async (model) => {
  downloadingModelId.value = model.models_id
  try {
    const response = await deviceApi.downloadModel(model.models_id)
    const blob = new Blob([response.data], {
      type: response.headers['content-type'] || 'application/octet-stream'
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', buildDownloadFilename(model))
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('模型下载已开始')
  } catch (error) {
    ElMessage.error(`下载模型失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    downloadingModelId.value = null
  }
}

// 切换模型激活状态
const toggleModelActive = async (model) => {
  try {
    const newStatus = !model.is_active
    await deviceApi.toggleModelActive(model.models_id, newStatus)
    model.is_active = newStatus
    ElMessage.success(`模型已${newStatus ? '激活' : '停用'}`)
  } catch (error) {
    // console.error('更新模型状态失败:', error)
    ElMessage.error(`更新模型状态失败: ${error.response?.data?.detail || error.message}`)
  }
}

// 确认删除模型
const confirmDelete = (model) => {
  ElMessageBox.confirm(
    `确定要删除模型"${model.models_name}"吗？此操作将永久删除该模型文件，且无法恢复。`,
    '删除确认',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await deviceApi.deleteModel(model.models_id)
      ElMessage.success('模型删除成功')
      loadModels() // 重新加载模型列表
    } catch (error) {
      // console.error('删除模型失败:', error)
      ElMessage.error(`删除模型失败: ${error.response?.data?.detail || error.message}`)
    }
  }).catch(() => {
    // 取消删除
  })
}

// 格式化文件大小
const formatFileSize = (size) => {
  if (size < 1024) {
    return size + ' B'
  } else if (size < 1024 * 1024) {
    return (size / 1024).toFixed(2) + ' KB'
  } else if (size < 1024 * 1024 * 1024) {
    return (size / (1024 * 1024)).toFixed(2) + ' MB'
  } else {
    return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  }
}

// 格式化日期
const formatDate = (dateStr) => {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 获取模型类型名称
const getModelTypeName = (type) => MODEL_TYPE_LABELS[type] || type

// 格式化参数为表格数据
const formatParameters = (params) => {
  if (!params) return []
  return Object.entries(params).map(([key, value]) => {
    return {
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value)
    }
  })
}
</script>

<style scoped>
.local-model-panel {
  padding: 0;
}

.panel-header {
  margin-bottom: 16px;
}

.policy-tag {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.processing-hint {
  margin-top: 10px;
  font-size: 13px;
  color: #e6a23c;
}

.info-alert {
  margin-bottom: 12px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-model-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.model-upload {
  width: 100%;
}

.model-upload :deep(.el-upload) {
  width: 100%;
}

.model-upload :deep(.el-upload-dragger) {
  width: 100%;
  min-height: 52px;
  height: auto;
  padding: 10px 16px;
}

.model-upload .upload-dragger-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.model-upload :deep(.el-icon--upload) {
  margin-bottom: 0;
  font-size: 40px;
}

.model-upload :deep(.el-upload-list) {
  margin-top: 6px;
}

.model-params-form-item :deep(.el-form-item__content) {
  line-height: normal;
}

.model-params-panel {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-blank);
  box-sizing: border-box;
}

.model-params-hint {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.model-params-hint code {
  font-size: 12px;
}

.model-params-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.model-params-row {
  display: grid;
  grid-template-columns: minmax(88px, 28%) 1fr auto;
  gap: 8px;
  align-items: center;
}

.model-params-row--head {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.model-params-row--head .col-action {
  text-align: center;
}

.model-params-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-top: 8px;
}

.no-data {
  padding: 40px 0;
  text-align: center;
}

.mt-2 {
  margin-top: 8px;
}

.mt-4 {
  margin-top: 16px;
}

.model-details {
  max-height: 600px;
  overflow-y: auto;
}

.upload-progress {
  margin-top: 15px;
  padding: 15px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background-color: #fafafa;
  width: 100%;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  color: #606266;
}

.progress-details {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.progress-details span {
  flex: 1;
  text-align: center;
}

.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
}

/* 高优先级对话框样式 - 确保不被菜单和头部遮挡 */
.high-priority-dialog {
  z-index: 999999 !important;
}
</style>