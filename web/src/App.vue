<script setup>
import { ref, reactive, onMounted, computed, onBeforeUnmount } from 'vue'
import { HomeFilled, DataLine, VideoCamera, Fold, Expand, Monitor, UserFilled, Connection, QuestionFilled, Tools, Bell, SetUp, List } from '@element-plus/icons-vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import deviceApi from '@/api/device'

const router = useRouter()
const route = useRoute()
const username = ref('')
const isCollapse = ref(false)
let tokenCheckInterval = null

// 是否显示登录页
const showLogin = computed(() => {
  return !localStorage.getItem('token')
})

// 是否显示数据大屏
const isDashboard = computed(() => {
  return route.path === '/dashboard'
})

onMounted(async () => {
  // 从本地存储中获取用户信息
  const userInfo = localStorage.getItem('userInfo')
  if (userInfo) {
    const user = JSON.parse(userInfo)
    username.value = user.username
  }

  // 开始定期检查token有效性
  if (localStorage.getItem('token')) {
    // 立即验证一次token
    checkTokenValidity()

    // 设置定期检查，每5分钟检查一次
    tokenCheckInterval = setInterval(checkTokenValidity, 5 * 60 * 1000)
  }
})

onBeforeUnmount(() => {
  // 组件卸载前清除定时器
  if (tokenCheckInterval) {
    clearInterval(tokenCheckInterval)
  }
})

// 检查token有效性
const checkTokenValidity = async () => {
  try {
    await deviceApi.validateToken()
    // console.log('Token is valid')
  } catch (error) {
    // console.error('Token validation failed:', error)
    if (error.response && error.response.status === 401) {
      // token无效，自动退出
      handleLogout()
      ElMessage.error('登录已过期，请重新登录')
    }
  }
}

const handleLogout = () => {
  // 清除所有认证相关的存储
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  username.value = ''

  // 强制刷新页面，确保登录状态更新
  // console.log("正在退出登录...");
  window.location.href = '/'
}

// 处理下拉菜单命令
const handleDropdownCommand = (command) => {
  if (command === 'logout') {
    handleLogout()
  } else if (command === 'profile') {
    router.push('/profile')
  }
}

// 打开帮助页面
const openHelp = () => {
  window.open('/help.html', '_blank')
}

// 打开数据大屏
const openDashboard = () => {
  window.open('/dashboard', '_blank')
}
</script>

<template>
  <!-- 数据大屏独立显示 -->
  <router-view v-if="isDashboard"></router-view>

  <!-- 使用路由系统显示登录页或主应用界面 -->
  <router-view v-else-if="showLogin"></router-view>

  <!-- 主应用界面 -->
  <el-container v-else class="layout-container">
    <el-aside :width="isCollapse ? '64px' : '240px'" class="transition-width">
      <div class="logo-container">
        <img src="./assets/fangte_dark.ico" alt="Logo" class="logo-img" />
        <span class="logo-text" v-show="!isCollapse">边缘 AI 检测盒</span>
      </div>
      <el-menu
        :default-active="route.path"
        class="el-menu-vertical edge-sidebar-menu"
        :router="true"
        :collapse="isCollapse"
      >
        <el-menu-item index="/">
          <el-icon>
            <HomeFilled />
          </el-icon>
          <template #title>首页</template>
        </el-menu-item>

        <el-sub-menu index="detection">
          <template #title>
            <el-icon>
              <Monitor />
            </el-icon>
            <span>目标检测</span>
          </template>

          <el-menu-item index="/realtime">
            <el-icon>
              <VideoCamera />
            </el-icon>
            <template #title>实时检测</template>
          </el-menu-item>

          <el-menu-item index="/detection/config">
            <el-icon>
              <Tools />
            </el-icon>
            <template #title>检测配置</template>
          </el-menu-item>

          <el-menu-item index="/detection/events">
            <el-icon>
              <Bell />
            </el-icon>
            <template #title>检测事件</template>
          </el-menu-item>

        </el-sub-menu>

        <el-menu-item index="/alert-rules">
          <el-icon>
            <SetUp />
          </el-icon>
          <template #title>规则引擎</template>
        </el-menu-item>

        <el-menu-item index="/devices">
          <el-icon>
            <VideoCamera />
          </el-icon>
          <template #title>视频设备</template>
        </el-menu-item>

        <el-sub-menu index="models">
          <template #title>
            <el-icon>
              <DataLine />
            </el-icon>
            <span>模型管理</span>
          </template>
          <el-menu-item index="/models/list">
            <el-icon>
              <List />
            </el-icon>
            <template #title>本地模型</template>
          </el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/push/config">
          <el-icon>
            <Connection />
          </el-icon>
          <template #title>推送配置</template>
        </el-menu-item>

        <el-menu-item index="/smart-schemes">
          <el-icon>
            <Connection />
          </el-icon>
          <template #title>事件订阅</template>
        </el-menu-item>

        <el-menu-item index="/system">
          <el-icon>
            <Tools />
          </el-icon>
          <template #title>系统管理</template>
        </el-menu-item>

        <!-- <el-menu-item @click="openDashboard">
          <el-icon>
            <DataLine />
          </el-icon>
          <template #title>数据大屏</template>
        </el-menu-item> -->

      </el-menu>
    </el-aside>
    <el-container class="right-container">
      <el-header height="64px">
        <div class="header-content">
          <div class="header-left">
            <el-button class="collapse-btn" @click="isCollapse = !isCollapse">
              <el-icon :size="14">
                <Fold v-if="!isCollapse" />
                <Expand v-else />
              </el-icon>
            </el-button>
          </div>
          <div class="header-right">
            <el-button class="dashboard-btn" @click="openDashboard">
              <el-icon>
                <DataLine />
              </el-icon>
              <template #title>数据大屏</template>
            </el-button>
            <el-button class="help-btn" @click="openHelp">
              <el-icon>
                <QuestionFilled />
              </el-icon>
              帮助
            </el-button>
            <el-dropdown @command="handleDropdownCommand">
              <div class="user-info">
                <span class="username">{{ username }}</span>
                <el-avatar :size="32" :icon="UserFilled" />
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                  <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-header>
      <el-main>
        <router-view></router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
/* 应用布局 — 边缘 AI 主题 */
.layout-container {
  width: 100%;
  height: 100%;
  background: var(--edge-bg-page);
}

.right-container {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--edge-bg-content);
  position: relative;
}

.el-aside {
  background: var(--edge-sidebar-bg);
  color: #fff;
  height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
  box-shadow: 4px 0 24px rgba(15, 36, 56, 0.35);
  position: relative;
}

.transition-width {
  transition: width 0.3s ease-in-out;
}

.logo-container {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: var(--edge-sidebar-logo-bg);
  overflow: hidden;
  border-bottom: 1px solid var(--edge-sidebar-border);
  position: relative;
  z-index: 2;
}

.logo-img {
  width: 32px;
  height: 32px;
  margin-right: 16px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.25));
}

.logo-text {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.el-menu {
  border-right: none;
  width: 100%;
  background: transparent !important;
  position: relative;
  z-index: 2;
}

:deep(.el-menu-item) {
  height: 50px;
  line-height: 50px;
  margin: 6px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
  color: rgba(255, 255, 255, 0.9) !important;
}

/* 折叠状态下的菜单整体样式 */
:deep(.el-menu--collapse) {
  width: 64px !important;
}

/* 折叠状态下的菜单项样式 - 使用更高优先级选择器 */
:deep(.el-aside .el-menu--collapse .el-menu-item) {
  width: 40px !important;
  margin: 6px 12px !important;
  padding: 0 !important;
  text-align: center !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 40px !important;
  overflow: hidden !important;
  position: relative !important;
}

/* 折叠状态下菜单项的所有子元素都居中 */
:deep(.el-aside .el-menu--collapse .el-menu-item *) {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 100% !important;
  text-align: center !important;
}

/* 折叠状态下的图标样式 */
:deep(.el-aside .el-menu--collapse .el-menu-item .el-icon) {
  margin: 0 !important;
  font-size: 18px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 18px !important;
  height: 18px !important;
  position: relative !important;
  z-index: 10 !important;
}

/* 隐藏所有文本内容 */
:deep(.el-aside .el-menu--collapse .el-menu-item span:not(.el-icon)) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
}

/* 折叠状态下的子菜单样式 */
:deep(.el-aside .el-menu--collapse .el-sub-menu) {
  width: 40px !important;
  margin: 6px 12px !important;
  min-width: 40px !important;
  overflow: hidden !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu .el-sub-menu__title) {
  padding: 0 !important;
  text-align: center !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 40px !important;
  min-width: 40px !important;
  overflow: hidden !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu .el-sub-menu__title .el-icon) {
  margin: 0 !important;
  font-size: 18px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 18px !important;
  height: 18px !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu .el-sub-menu__title span:not(.el-icon)) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

/* 隐藏子菜单箭头 - 多种可能的类名 */
:deep(.el-aside .el-menu--collapse .el-sub-menu .el-sub-menu__icon-arrow) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu__icon-arrow) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

:deep(.el-aside .el-menu--collapse .el-icon-arrow-down) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

:deep(.el-aside .el-menu--collapse .el-icon-arrow-right) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

:deep(.el-aside .el-menu--collapse [class*="arrow"]) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

/* 强制隐藏所有子菜单标题中的箭头相关元素 */
:deep(.el-aside .el-menu--collapse .el-sub-menu__title > .el-icon:last-child) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu__title > *:last-child:not(.el-icon:first-child)) {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}

/* 额外的箭头隐藏策略 - 如果上面的方法不行，用覆盖层遮盖 */
:deep(.el-aside .el-menu--collapse .el-sub-menu__title) {
  overflow: hidden !important;
  position: relative !important;
}

:deep(.el-aside .el-menu--collapse .el-sub-menu__title::after) {
  content: '' !important;
  position: absolute !important;
  right: 0 !important;
  top: 0 !important;
  width: 15px !important;
  height: 100% !important;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.08), rgba(255, 255, 255, 0.08)) !important;
  z-index: 999 !important;
  pointer-events: none !important;
}

/* Element Plus Tooltip 包装器处理 */
:deep(.el-aside .el-menu--collapse .el-tooltip) {
  width: 100% !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

:deep(.el-aside .el-menu--collapse .el-tooltip__trigger) {
  width: 100% !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0 !important;
}

/* 强制所有内容居中 */
:deep(.el-aside .el-menu--collapse) {
  text-align: center !important;
}

:deep(.el-aside .el-menu--collapse > *) {
  text-align: center !important;
}

:deep(.el-menu-item::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.2), transparent);
  transition: left 0.5s ease;
}

:deep(.el-menu-item:hover) {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.2), rgba(255, 255, 255, 0.15)) !important;
  border-color: rgba(64, 158, 255, 0.4);
  box-shadow: 0 4px 15px rgba(64, 158, 255, 0.3);
  color: #ffffff !important;
}

:deep(.el-menu-item:hover::before) {
  left: 100%;
}

:deep(.el-menu-item.is-active) {
  background: var(--edge-sidebar-item-active) !important;
  border: 1px solid rgba(255, 255, 255, 0.25);
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.35);
  color: #ffffff !important;
}

:deep(.el-menu-item .el-icon) {
  font-size: 18px;
  margin-right: 8px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
}

:deep(.el-sub-menu) {
  margin: 6px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}

:deep(.el-sub-menu::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.1), transparent);
  transition: left 0.5s ease;
  z-index: 0;
}

:deep(.el-sub-menu:hover) {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(64, 158, 255, 0.3);
  box-shadow: 0 4px 15px rgba(64, 158, 255, 0.2);
}

:deep(.el-sub-menu:hover::before) {
  left: 100%;
}

:deep(.el-sub-menu.is-opened) {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.1), rgba(255, 255, 255, 0.12));
  border-color: rgba(64, 158, 255, 0.4);
  box-shadow:
    0 6px 20px rgba(64, 158, 255, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

:deep(.el-sub-menu__title) {
  height: 50px;
  line-height: 50px;
  color: rgba(255, 255, 255, 0.9) !important;
  background: transparent !important;
  border-radius: 12px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  z-index: 2;
  padding: 0 20px !important;
}

:deep(.el-sub-menu__title::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.15), transparent);
  transition: left 0.4s ease;
  border-radius: 12px;
}

:deep(.el-sub-menu__title:hover) {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.2), rgba(255, 255, 255, 0.15)) !important;
  color: #ffffff !important;
  border-radius: 12px;
}

:deep(.el-sub-menu__title:hover::before) {
  left: 100%;
}

:deep(.el-sub-menu.is-opened .el-sub-menu__title) {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.25), rgba(74, 144, 226, 0.15)) !important;
  color: #ffffff !important;
}

:deep(.el-sub-menu__title .el-icon) {
  font-size: 18px;
  margin-right: 8px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.1));
  transition: transform 0.3s ease;
}

:deep(.el-sub-menu__title:hover .el-icon) {
  transform: scale(1.1);
}

:deep(.el-sub-menu .el-sub-menu__icon-arrow) {
  font-size: 14px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: rgba(255, 255, 255, 0.7);
}

:deep(.el-sub-menu.is-opened .el-sub-menu__icon-arrow) {
  transform: rotate(180deg);
  color: #ffffff;
}

:deep(.el-menu--inline) {
  background: rgba(0, 0, 0, 0.1) !important;
  border-radius: 0 0 8px 8px;
  padding: 8px 0;
  margin-top: 4px;
}

:deep(.el-menu--inline .el-menu-item) {
  margin: 2px 8px;
  padding-left: 24px !important;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  height: 42px;
  line-height: 42px;
  color: rgba(255, 255, 255, 0.8) !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

:deep(.el-menu--inline .el-menu-item::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(74, 144, 226, 0.15), transparent);
  transition: left 0.4s ease;
}

:deep(.el-menu--inline .el-menu-item:hover) {
  background: linear-gradient(135deg, rgba(74, 144, 226, 0.2), rgba(255, 255, 255, 0.1)) !important;
  border-color: rgba(74, 144, 226, 0.4);
  color: #ffffff !important;
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.2);
}

:deep(.el-menu--inline .el-menu-item:hover::before) {
  left: 100%;
}

:deep(.el-menu--inline .el-menu-item.is-active) {
  background: var(--edge-sidebar-item-active) !important;
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #ffffff !important;
  box-shadow:
    0 4px 12px rgba(74, 144, 226, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.el-header {
  background: var(--edge-header-bg);
  border-bottom: 1px solid var(--edge-header-border);
  padding: 0 24px;
  position: relative;
  z-index: 999;
  height: 64px !important;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8), 0 4px 16px rgba(26, 58, 92, 0.06);
}

.el-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--edge-primary-deeper), var(--edge-primary), var(--edge-accent));
  opacity: 0.85;
}

.header-content {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
  z-index: 2;
}

.header-left {
  display: flex;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  height: 36px;
  width: 36px;
  padding: 0;
  font-size: 15px;
  border: 2px solid rgba(74, 144, 226, 0.2);
  background: linear-gradient(135deg, #ffffff, #f8fbff);
  color: #1e3c72;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.1);
  position: relative;
  overflow: hidden;
}

.collapse-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(74, 144, 226, 0.1), transparent);
  transition: left 0.3s ease;
}

.collapse-btn:hover {
  background: linear-gradient(135deg, #4a90e2, #1e3c72);
  color: #ffffff;
  border-color: #4a90e2;
  transform: scale(1.1);
  box-shadow: 0 4px 15px rgba(74, 144, 226, 0.3);
}

.collapse-btn:hover::before {
  left: 100%;
}

.help-btn {
  height: 36px;
  padding: 0 16px;
  font-size: 14px;
  border: 2px solid rgba(64, 158, 255, 0.2);
  background: linear-gradient(135deg, #ffffff, #f0f7ff);
  color: var(--edge-primary);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
  position: relative;
  overflow: hidden;
  margin-left: 0 !important; /* 强制移除Element Plus的默认左外边距 */
}

.help-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.1), transparent);
  transition: left 0.3s ease;
}

.help-btn:hover {
  background: linear-gradient(135deg, var(--edge-primary), var(--edge-primary-dark));
  color: #ffffff;
  border-color: var(--edge-primary);
  transform: scale(1.05);
  box-shadow: 0 4px 15px rgba(64, 158, 255, 0.3);
}

.help-btn:hover::before {
  left: 100%;
}

.dashboard-btn {
  height: 36px;
  padding: 0 16px;
  font-size: 14px;
  border: 1px solid var(--edge-card-border);
  background: #ffffff;
  color: var(--edge-primary);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.1);
  position: relative;
  overflow: hidden;
  margin-left: 0 !important; /* 强制移除Element Plus的默认左外边距 */
}

.dashboard-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(74, 144, 226, 0.1), transparent);
  transition: left 0.3s ease;
}

.dashboard-btn:hover {
  background: linear-gradient(135deg, var(--edge-primary), var(--edge-primary-dark));
  color: #ffffff;
  border-color: var(--edge-primary);
  transform: scale(1.05);
  box-shadow: 0 4px 15px rgba(74, 144, 226, 0.3);
}

.dashboard-btn:hover::before {
  left: 100%;
}

.user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(74, 144, 226, 0.1), rgba(255, 255, 255, 0.8));
  border: 1px solid rgba(74, 144, 226, 0.2);
  transition: all 0.3s ease;
  backdrop-filter: blur(10px);
}

.user-info:hover {
  background: linear-gradient(135deg, rgba(74, 144, 226, 0.2), rgba(255, 255, 255, 0.9));
  border-color: #4a90e2;
  transform: translateY(-1px);
  box-shadow: 0 4px 15px rgba(74, 144, 226, 0.2);
}

.username {
  margin-right: 8px;
  font-weight: 600;
  color: #1e3c72;
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
}

:deep(.el-avatar) {
  background: linear-gradient(135deg, var(--edge-primary), var(--edge-primary-dark)) !important;
  border: 2px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 2px 8px rgba(74, 144, 226, 0.2);
}

/* El-main 样式优化 - 主页面背景方案 */
:deep(.el-main) {
  position: relative;
  z-index: 2;
  background: var(--edge-bg-content);
  padding: 20px;
  min-height: calc(100vh - 64px);
}

:deep(.el-main::before) {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background:
    radial-gradient(circle at 12% 18%, rgba(64, 158, 255, 0.06) 0%, transparent 42%),
    radial-gradient(circle at 88% 82%, rgba(54, 207, 201, 0.05) 0%, transparent 40%);
  pointer-events: none;
  z-index: -1;
}

/* 响应式设计 */
@media screen and (max-width: 768px) {
  .logo-container {
    padding: 0 12px;
  }

  .logo-img {
    width: 28px;
    height: 28px;
    margin-right: 12px;
  }

  .logo-text {
    font-size: 14px;
  }

  :deep(.el-menu-item) {
    margin: 4px 8px;
    height: 45px;
    line-height: 45px;
  }

  :deep(.el-sub-menu) {
    margin: 4px 8px;
  }

  .header-content {
    padding: 0 12px;
  }

  .collapse-btn,
  .help-btn {
    height: 32px;
    font-size: 12px;
  }

  .help-btn {
    padding: 0 12px;
  }
}
</style>
