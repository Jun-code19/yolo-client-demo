<template>
  <div class="rule-engine-hub">
    <el-tabs v-model="activePanel" class="hub-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="规则列表" name="rules">
        <AlertRuleManagement />
      </el-tab-pane>
      <el-tab-pane label="命中记录" name="alerts">
        <CompositeAlertList />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AlertRuleManagement from './AlertRuleManagement.vue'
import CompositeAlertList from './CompositeAlertList.vue'

const route = useRoute()
const router = useRouter()
const activePanel = ref('rules')

const syncTabFromRoute = () => {
  activePanel.value = route.query.tab === 'alerts' || route.query.rule_id ? 'alerts' : 'rules'
}

const handleTabChange = (tabName) => {
  const query = { ...route.query }
  if (tabName === 'alerts') {
    query.tab = 'alerts'
  } else {
    delete query.tab
    delete query.rule_id
  }
  router.replace({ path: '/alert-rules', query })
}

watch(() => [route.query.tab, route.query.rule_id], syncTabFromRoute)
onMounted(syncTabFromRoute)
</script>

<style scoped>
.rule-engine-hub {
  padding: 20px;
}

.hub-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.hub-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}
</style>
