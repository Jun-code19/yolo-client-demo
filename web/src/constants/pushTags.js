/** 数据推送预定义标签（与各业务模块推送 tags 对齐） */
export const PUSH_TAG_GROUPS = [
  {
    label: '事件订阅',
    tags: [
      { value: 'subscribe_event', label: 'subscribe_event（订阅事件）' },
    ],
  },
  {
    label: '检测与告警',
    tags: [
      { value: 'detection', label: 'detection（普通检测）' },
      { value: 'smart_scheme', label: 'smart_scheme（智能方案）' },
      { value: 'alarm', label: 'alarm（告警事件）' },
      { value: 'composite_alert', label: 'composite_alert（复合告警）' },
    ],
  },
  {
    label: '通用',
    tags: [
      { value: 'system', label: 'system（系统事件）' },
      { value: 'statistics', label: 'statistics（统计数据）' },
    ],
  },
]

export const COMMON_PUSH_TAGS = PUSH_TAG_GROUPS.flatMap((group) =>
  group.tags.map((tag) => tag.value)
)

export const DEFAULT_SUBSCRIBE_PUSH_TAG = 'subscribe_event'

export const DEFAULT_SMART_SCHEME_PUSH_TAG = 'smart_scheme'
