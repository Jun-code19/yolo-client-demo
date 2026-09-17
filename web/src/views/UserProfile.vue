<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import deviceApi from '@/api/device'
import { useRouter } from 'vue-router'

// 引入路由
const router = useRouter()

// 加载状态
const loading = ref(false)
const passwordLoading = ref(false)
const userManagementLoading = ref(false)

// 用户管理相关
const isAdmin = ref(false)
const users = ref([])
const totalUsers = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const userSearchForm = reactive({
  username: '',
  role: ''
})

// 新增用户对话框
const addUserDialogVisible = ref(false)
const addUserForm = reactive({
  user_id: '',
  username: '',
  password: '',
  confirmPassword: '',
  role: 'operator',
  allowed_devices: []
})

// 新增用户表单规则
const addUserRules = {
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
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { 
      validator: (rule, value, callback) => {
        if (value !== addUserForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      }, 
      trigger: 'blur' 
    }
  ]
}

const addUserFormRef = ref(null)

// 用户信息表单
const userForm = reactive({
  user_id: '',
  username: '',
  role: '',
  allowed_devices: []
})

// 修改密码表单
const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

// 表单规则
const userRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应在3到20个字符之间', trigger: 'blur' }
  ]
}

const passwordRules = {
  oldPassword: [
    { required: true, message: '请输入当前密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度应在6到20个字符之间', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { 
      validator: (rule, value, callback) => {
        if (value !== passwordForm.newPassword) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      }, 
      trigger: 'blur' 
    }
  ]
}

// 表单引用
const userFormRef = ref(null)
const passwordFormRef = ref(null)

// 加载用户信息
onMounted(async () => {
  try {
    loading.value = true
    
    // 从localStorage获取基本信息
    const userInfo = localStorage.getItem('userInfo')
    if (userInfo) {
      const user = JSON.parse(userInfo)
      userForm.user_id = user.user_id
      userForm.username = user.username
      userForm.role = user.role
      userForm.allowed_devices = user.allowed_devices || []
      
      // 检查是否为管理员
      isAdmin.value = user.role === 'admin'
    }
    
    // 如果需要，也可以从API获取最新信息
    const { data } = await deviceApi.getCurrentUser()
    userForm.user_id = data.user_id
    userForm.username = data.username
    userForm.role = data.role
    userForm.allowed_devices = data.allowed_devices || []
    
    // 检查是否为管理员
    isAdmin.value = data.role === 'admin'
    
    // 更新localStorage中的用户信息
    localStorage.setItem('userInfo', JSON.stringify(data))
    
    // 如果是管理员，加载用户列表
    if (isAdmin.value) {
      await loadUsers()
    }
    
  } catch (error) {
    // console.error('加载用户信息失败:', error)
    ElMessage.error('加载用户信息失败')
  } finally {
    loading.value = false
  }
})

// 加载用户列表
const loadUsers = async () => {
  try {
    userManagementLoading.value = true
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
      ...userSearchForm
    }
    
    const { data } = await deviceApi.getUsers(params)
    users.value = data.data
    totalUsers.value = data.total
  } catch (error) {
    ElMessage.error('加载用户列表失败')
  } finally {
    userManagementLoading.value = false
  }
}

// 搜索用户
const searchUsers = () => {
  currentPage.value = 1
  loadUsers()
}

// 重置搜索
const resetSearch = () => {
  userSearchForm.username = ''
  userSearchForm.role = ''
  currentPage.value = 1
  loadUsers()
}

// 分页变化
const handlePageChange = (page) => {
  currentPage.value = page
  loadUsers()
}

// 新增用户
const addUser = async () => {
  if (!addUserFormRef.value) return
  
  await addUserFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    try {
      // 创建用户数据对象（删除确认密码字段）
      const userData = { ...addUserForm }
      delete userData.confirmPassword
      
      await deviceApi.createUser(userData)
      ElMessage.success('用户创建成功')
      
      // 关闭对话框并重置表单
      addUserDialogVisible.value = false
      addUserForm.user_id = ''
      addUserForm.username = ''
      addUserForm.password = ''
      addUserForm.confirmPassword = ''
      addUserForm.role = 'operator'
      addUserForm.allowed_devices = []
      
      // 重新加载用户列表
      await loadUsers()
    } catch (error) {
      ElMessage.error(`创建用户失败: ${error.response?.data?.detail || error.message}`)
    }
  })
}

// 删除用户
const deleteUser = async (userId, username) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${username}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await deviceApi.deleteUser(userId)
    ElMessage.success('用户删除成功')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`删除用户失败: ${error.response?.data?.detail || error.message}`)
    }
  }
}

// 打开新增用户对话框
const openAddUserDialog = () => {
  addUserDialogVisible.value = true
}

// 获取角色显示名称
const getRoleDisplayName = (role) => {
  const roleMap = {
    'admin': '管理员',
    'operator': '操作员',
    'auditor': '审计员'
  }
  return roleMap[role] || role
}

// 获取角色标签类型
const getRoleTagType = (role) => {
  const typeMap = {
    'admin': 'danger',
    'operator': 'primary',
    'auditor': 'warning'
  }
  return typeMap[role] || 'info'
}

// 更新用户信息
const updateUserInfo = async () => {
  if (!userFormRef.value) return
  
  await userFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      // 更新用户信息
      await deviceApi.updateUserProfile(userForm)
      
      // 更新localStorage中的用户信息
      localStorage.setItem('userInfo', JSON.stringify(userForm))
      
      // 触发页面刷新以更新顶部导航栏的用户名
      setTimeout(() => {
        window.location.reload()
      }, 1000)
      
      ElMessage.success('用户信息更新成功，页面将自动刷新')
    } catch (error) {
      // console.error('更新用户信息失败:', error)
      ElMessage.error(`更新用户信息失败: ${error.response?.data?.detail || error.message}`)
    } finally {
      loading.value = false
    }
  })
}

// 更新密码
const updatePassword = async () => {
  if (!passwordFormRef.value) return
  
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    passwordLoading.value = true
    try {
      // 更新密码
      await deviceApi.updatePassword({
        user_id: userForm.user_id,
        old_password: passwordForm.oldPassword,
        new_password: passwordForm.newPassword
      })
      
      // 清空密码表单
      passwordForm.oldPassword = ''
      passwordForm.newPassword = ''
      passwordForm.confirmPassword = ''
      
      // 显示成功消息并询问是否立即退出登录
      ElMessageBox.confirm(
        '密码更新成功！为了安全起见，您需要使用新密码重新登录。',
        '密码已更改',
        {
          confirmButtonText: '立即退出并重新登录',
          type: 'success',
          showCancelButton: false,
          center: true
        }
      ).then(() => {
        // 清除认证信息并跳转到登录页
        localStorage.removeItem('token')
        localStorage.removeItem('userInfo')
        window.location.href = '/'
      })
    } catch (error) {
      // console.error('更新密码失败:', error)
      ElMessage.error(`更新密码失败: ${error.response?.data?.detail || error.message}`)
    } finally {
      passwordLoading.value = false
    }
  })
}
</script>

<template>
  <div class="profile-container">
    <el-card class="profile-card">
      <template #header>
        <div class="card-header">
          <h2>个人中心</h2>
        </div>
      </template>
      
      <el-tabs>
        <!-- 基本信息修改 -->
        <el-tab-pane label="个人信息">
          <el-form 
            ref="userFormRef"
            :model="userForm"
            :rules="userRules"
            label-width="100px"
            v-loading="loading"
          >
            <el-form-item label="用户ID">
              <el-input v-model="userForm.user_id" disabled />
            </el-form-item>
            
            <el-form-item label="用户名" prop="username">
              <el-input v-model="userForm.username" />
            </el-form-item>
            
            <el-form-item label="角色">
              <el-input v-model="userForm.role" disabled />
            </el-form-item>
            
            <el-form-item>
              <el-button 
                type="primary" 
                @click="updateUserInfo"
                :loading="loading"
              >
                保存修改
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        
        <!-- 密码修改 -->
        <el-tab-pane label="修改密码">
          <el-form 
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-width="100px"
            v-loading="passwordLoading"
          >
            <el-form-item label="当前密码" prop="oldPassword">
              <el-input 
                v-model="passwordForm.oldPassword" 
                type="password"
                show-password
              />
            </el-form-item>
            
            <el-form-item label="新密码" prop="newPassword">
              <el-input 
                v-model="passwordForm.newPassword" 
                type="password"
                show-password
              />
            </el-form-item>
            
            <el-form-item label="确认新密码" prop="confirmPassword">
              <el-input 
                v-model="passwordForm.confirmPassword" 
                type="password"
                show-password
              />
            </el-form-item>
            
            <el-form-item>
              <el-button 
                type="primary" 
                @click="updatePassword"
                :loading="passwordLoading"
              >
                修改密码
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        
        <!-- 用户管理（仅管理员可见） -->
        <el-tab-pane label="用户管理" v-if="isAdmin">
          <div class="user-management">
            <!-- 搜索栏 -->
            <div class="search-bar">
              <el-form :model="userSearchForm" inline>
                <el-form-item label="用户名" style="width: 160px;">
                  <el-input 
                    v-model="userSearchForm.username" 
                    placeholder="请输入用户名"
                    clearable
                    @keyup.enter="searchUsers"
                  />
                </el-form-item>
                <el-form-item label="角色" style="width: 160px;">
                  <el-select v-model="userSearchForm.role" placeholder="请选择角色" clearable>
                    <el-option label="管理员" value="admin" />
                    <el-option label="操作员" value="operator" />
                    <el-option label="审计员" value="auditor" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="searchUsers">搜索</el-button>
                  <el-button @click="resetSearch">重置</el-button>
                  <el-button type="success" @click="openAddUserDialog">新增用户</el-button>
                </el-form-item>
              </el-form>
            </div>
            
            <!-- 用户列表 -->
            <el-table 
              :data="users" 
              v-loading="userManagementLoading"
              style="width: 100%"
            >
              <el-table-column prop="user_id" label="用户ID" width="150" />
              <el-table-column prop="username" label="用户名" width="150" />
              <el-table-column prop="role" label="角色" width="150">
                <template #default="scope">
                  <el-tag :type="getRoleTagType(scope.row.role)">
                    {{ getRoleDisplayName(scope.row.role) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="allowed_devices" label="允许的设备" min-width="150">
                <template #default="scope">
                  <el-tag 
                    v-for="device in scope.row.allowed_devices" 
                    :key="device"
                    size="small"
                    style="margin-right: 5px; margin-bottom: 5px;"
                  >
                    {{ device }}
                  </el-tag>
                  <span v-if="!scope.row.allowed_devices || scope.row.allowed_devices.length === 0">
                    无限制
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="scope">
                  <el-button 
                    type="danger" 
                    size="small" 
                    @click="deleteUser(scope.row.user_id, scope.row.username)"
                    :disabled="scope.row.user_id === userForm.user_id"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            
            <!-- 分页 -->
            <div class="pagination-container">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50, 100]"
                :total="totalUsers"
                layout="total, sizes, prev, pager, next, jumper"
                @size-change="handlePageChange"
                @current-change="handlePageChange"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    
    <!-- 新增用户对话框 -->
    <el-dialog
      v-model="addUserDialogVisible"
      title="新增用户"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="addUserFormRef"
        :model="addUserForm"
        :rules="addUserRules"
        label-width="100px"
      >
        <el-form-item label="用户ID" prop="user_id">
          <el-input v-model="addUserForm.user_id" placeholder="请输入用户ID" />
        </el-form-item>
        
        <el-form-item label="用户名" prop="username">
          <el-input v-model="addUserForm.username" placeholder="请输入用户名" />
        </el-form-item>
        
        <el-form-item label="密码" prop="password">
          <el-input 
            v-model="addUserForm.password" 
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input 
            v-model="addUserForm.confirmPassword" 
            type="password"
            placeholder="请再次输入密码"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="角色" prop="role">
          <el-select v-model="addUserForm.role" placeholder="请选择角色">
            <el-option label="操作员" value="operator" />
            <el-option label="审计员" value="auditor" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="addUserDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="addUser">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.profile-container {
  padding: 20px;
}

.profile-card {
  max-width: 50vw;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h2 {
  margin-bottom: 0;
}

/* 用户管理样式 */

.search-bar {
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.search-bar .el-form {
  margin-bottom: 0;
}

.search-bar .el-form-item {
  margin-bottom: 0;
}

.search-bar .el-form-item {
  margin-bottom: 0;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.el-table {
  margin-top: 20px;
}

.el-tag {
  margin-right: 5px;
  margin-bottom: 5px;
}
</style> 