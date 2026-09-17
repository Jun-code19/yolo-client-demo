import { ref } from 'vue'
import { dataPushApi } from '@/api/data_push'

/** 从推送配置列表收集已使用过的标签（不含内置预设） */
export function usePushConfigTags() {
  const pushTagOptions = ref([])
  const loading = ref(false)

  const loadPushConfigTags = async () => {
    loading.value = true
    try {
      const res = await dataPushApi.getPushConfigs({ skip: 0, limit: 500 })
      const configs = res.data?.data || []
      const tags = new Set()
      configs.forEach((cfg) => {
        ;(cfg.tags || []).forEach((tag) => {
          if (tag) tags.add(tag)
        })
      })
      pushTagOptions.value = Array.from(tags).sort()
    } catch {
      pushTagOptions.value = []
    } finally {
      loading.value = false
    }
  }

  return { pushTagOptions, loading, loadPushConfigTags }
}
