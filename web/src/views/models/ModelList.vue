<template>
  <div class="local-models-management">
    <el-tabs v-model="activePanel" class="local-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="本地模型" name="models">
        <LocalModelListPanel />
      </el-tab-pane>
      <el-tab-pane label="图片验证" name="image">
        <ImageValidation />
      </el-tab-pane>
      <el-tab-pane label="视频验证" name="video">
        <VideoValidation />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LocalModelListPanel from './LocalModelListPanel.vue'
import ImageValidation from './ImageValidation.vue'
import VideoValidation from './VideoValidation.vue'

const route = useRoute()
const router = useRouter()

const activePanel = ref('models')

const syncTabFromRoute = () => {
  const tab = route.query.tab
  if (tab === 'image' || tab === 'video' || tab === 'models') {
    activePanel.value = tab
  } else {
    activePanel.value = 'models'
  }
}

const handleTabChange = (tabName) => {
  const query = tabName === 'models' ? {} : { tab: tabName }
  router.replace({ path: '/models/list', query })
}

watch(() => route.query.tab, syncTabFromRoute)

onMounted(syncTabFromRoute)
</script>

<style scoped>
.local-models-management {
  padding: 0;
}

.local-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}
</style>
