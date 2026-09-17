<template>
  <div class="smart-scheme-hub">
    <el-tabs v-model="activePanel" class="hub-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="订阅管理" name="configs">
        <SmartSchemeManagement />
      </el-tab-pane>
      <el-tab-pane label="订阅事件" name="events">
        <SmartEvents />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SmartSchemeManagement from './SmartSchemeManagement.vue'
import SmartEvents from './SmartEvents.vue'

const route = useRoute()
const router = useRouter()
const activePanel = ref('configs')

const syncTabFromRoute = () => {
  if (route.query.tab === 'events' || route.query.scheme_id) {
    activePanel.value = 'events'
    return
  }
  activePanel.value = 'configs'
}

const handleTabChange = (tabName) => {
  const query = { ...route.query }
  if (tabName === 'events') {
    query.tab = 'events'
  } else {
    delete query.tab
    delete query.scheme_id
  }
  router.replace({ path: '/smart-schemes', query })
}

watch(() => [route.query.tab, route.query.scheme_id], syncTabFromRoute)
onMounted(syncTabFromRoute)
</script>

<style scoped>
.smart-scheme-hub {
  padding: 20px;
}

.hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.hub-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}
</style>
