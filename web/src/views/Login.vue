<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Monitor, UserFilled, Lock } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import deviceApi from '@/api/device'

const router = useRouter()
const loading = ref(false)

// 系统初始化状态
const isInitializing = ref(false)
const isSystemInitialized = ref(true)

// 登录表单
const loginForm = reactive({
  username: '',
  password: ''
})

// 管理员注册表单
const adminForm = reactive({
  user_id: '',
  username: '',
  password: '',
  password_confirm: '',
  role: 'admin',
  allowed_devices: []
})

// 表单验证规则
const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应在3到20个字符之间', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度应在6到20个字符之间', trigger: 'blur' }
  ]
}

// 管理员注册表单规则
const adminRules = {
  user_id: [
    { required: true, message: '请输入用户ID', trigger: 'blur' },
    { min: 3, max: 20, message: '用户ID长度应在3到20个字符之间', trigger: 'blur' }
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应在3到20个字符之间', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度应在6到20个字符之间', trigger: 'blur' }
  ],
  password_confirm: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== adminForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

const loginFormRef = ref(null)
const adminFormRef = ref(null)

onMounted(async () => {
  // 检查系统是否初始化
  try {
    const { data } = await deviceApi.checkSystemInitialized()
    isSystemInitialized.value = data.initialized
  } catch (error) {
    // console.error('检查系统初始化状态失败:', error)
  }
})

// 登录处理
const handleLogin = async () => {
  if (!loginFormRef.value) return

  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const response = await deviceApi.login(loginForm.username, loginForm.password)
      const { access_token } = response.data

      // 保存token
      localStorage.setItem('token', access_token)

      // 获取用户信息
      const userInfo = await deviceApi.getCurrentUser()
      localStorage.setItem('userInfo', JSON.stringify(userInfo.data))

      ElMessage.success('登录成功')

      // 重置表单
      loginForm.username = ''
      loginForm.password = ''

      // 强制刷新页面，确保登录状态更新并跳转
      window.location.href = '/'
    } catch (error) {
      // console.error('登录失败:', error)
      let errorMsg = '登录失败: 用户名或密码错误'

      // 显示详细错误信息以便调试
      if (error.response) {
        errorMsg += `\n状态码: ${error.response.status}`
        // console.error("错误详情:", error.response.data);
        if (error.response.data && error.response.data.detail) {
          errorMsg += `\n详情: ${error.response.data.detail}`
        }
      }

      ElMessage.error(errorMsg)
    } finally {
      loading.value = false
    }
  })
}

// 创建管理员账户
const handleInitSystem = async () => {
  if (!adminFormRef.value) return

  await adminFormRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      // 创建管理员数据对象（删除确认密码字段）
      const adminData = { ...adminForm }
      delete adminData.password_confirm

      await deviceApi.initializeSystem(adminData)
      ElMessage.success('系统初始化成功，管理员账户已创建')
      isInitializing.value = false
      isSystemInitialized.value = true

      // 使用刚创建的管理员账户登录
      loginForm.username = adminForm.username
      loginForm.password = adminForm.password

      // 清空管理员表单
      adminForm.user_id = ''
      adminForm.username = ''
      adminForm.password = ''
      adminForm.password_confirm = ''
    } catch (error) {
      // console.error('初始化系统失败:', error)
      ElMessage.error(`初始化失败: ${error.response?.data?.detail || error.message}`)
    } finally {
      loading.value = false
    }
  })
}

// 切换到初始化系统界面
const showInitForm = () => {
  isInitializing.value = true
}

// 返回登录页
const backToLogin = () => {
  isInitializing.value = false
}

</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-brand">
        <div class="login-brand-icon">
          <el-icon :size="28"><Monitor /></el-icon>
        </div>
        <h1>边缘 AI 检测盒</h1>
        <p v-if="isSystemInitialized">检测 · 规则 · 订阅 · 展示大屏</p>
        <p v-else>首次使用请先创建管理员</p>
      </div>

      <div class="login-form">
          <!-- 系统未初始化时显示初始化设置 -->
          <template v-if="!isSystemInitialized">
            <div v-if="!isInitializing" class="init-notice">
              <el-alert title="系统尚未初始化" type="info" description="检测到系统是首次使用，请先创建一个管理员账户。" show-icon :closable="false" />
              <el-button type="primary" @click="showInitForm" style="width: 100%; margin-top: 16px;">
                创建管理员账户
              </el-button>
            </div>

            <!-- 管理员注册表单 -->
            <template v-if="isInitializing">
              <el-form ref="adminFormRef" :model="adminForm" :rules="adminRules" label-width="0"
                @keyup.enter="handleInitSystem">
                <el-form-item prop="user_id">
                  <el-input v-model="adminForm.user_id" placeholder="请输入用户ID" :prefix-icon="UserFilled" size="large" />
                </el-form-item>

                <el-form-item prop="username">
                  <el-input v-model="adminForm.username" placeholder="请输入用户名" :prefix-icon="UserFilled" size="large" />
                </el-form-item>

                <el-form-item prop="password">
                  <el-input v-model="adminForm.password" type="password" placeholder="请输入密码" :prefix-icon="Lock"
                    show-password size="large" />
                </el-form-item>

                <el-form-item prop="password_confirm">
                  <el-input v-model="adminForm.password_confirm" type="password" placeholder="请再次输入密码"
                    :prefix-icon="Lock" show-password size="large" />
                </el-form-item>

                <el-form-item>
                  <div class="form-actions">
                    <el-button @click="backToLogin">返回</el-button>
                    <el-button type="primary" @click="handleInitSystem" :loading="loading" class="init-button">
                      创建管理员
                    </el-button>
                  </div>
                </el-form-item>
              </el-form>
            </template>
          </template>

          <!-- 登录表单 -->
          <template v-else>
            <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-width="0"
              @keyup.enter="handleLogin">
              <el-form-item prop="username">
                <el-input v-model="loginForm.username" placeholder="请输入用户名" :prefix-icon="UserFilled" size="large" />
              </el-form-item>

              <el-form-item prop="password">
                <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" :prefix-icon="Lock"
                  show-password size="large" />
              </el-form-item>

              <el-form-item>
                <el-button type="primary" class="login-button" :loading="loading" @click="handleLogin" size="large"
                  :disabled="loading">
                  {{ loading ? '登录中…' : '登录' }}
                </el-button>
              </el-form-item>
            </el-form>
          </template>
        </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    var(--edge-primary-deeper) 0%,
    var(--edge-primary-dark) 45%,
    var(--edge-primary) 100%
  );
}

.login-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 15% 20%, rgba(255, 255, 255, 0.1) 0%, transparent 55%),
    radial-gradient(ellipse 70% 50% at 85% 75%, rgba(54, 207, 201, 0.2) 0%, transparent 50%);
  pointer-events: none;
}

.login-card {
  position: relative;
  z-index: 1;
  width: min(420px, 100%);
  padding: 32px 28px 28px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  border-radius: 12px;
  box-shadow: var(--edge-card-shadow);
  border: 1px solid var(--edge-card-border);
  overflow: hidden;
}

.login-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(
    90deg,
    var(--edge-primary-deeper),
    var(--edge-primary),
    var(--edge-accent)
  );
}

.login-brand {
  text-align: center;
  margin-bottom: 28px;
}

.login-brand-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 12px;
  border-radius: 10px;
  background: rgba(64, 158, 255, 0.12);
  color: var(--edge-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-brand h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: var(--edge-text-primary);
}

.login-brand p {
  margin: 0;
  font-size: 13px;
  color: var(--edge-text-muted);
}

.login-form {
  width: 100%;
}

:deep(.el-form-item) {
  margin-bottom: 18px;
}

:deep(.el-input__wrapper) {
  border-radius: 8px;
}

.login-button,
.init-button {
  width: 100%;
}

.init-notice {
  margin-top: 4px;
}

.form-actions {
  display: flex;
  gap: 12px;
}

.form-actions .el-button {
  flex: 1;
}
</style> 