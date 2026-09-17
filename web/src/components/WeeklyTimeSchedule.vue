<template>
  <div class="weekly-time-schedule">
    <div class="schedule-toolbar">
      <span class="toolbar-label">快捷预设</span>
      <el-button
        size="small"
        :type="activePreset === 'all' ? 'primary' : 'default'"
        @click="applyPreset('all')"
      >
        全时段
      </el-button>
      <el-button
        size="small"
        :type="activePreset === 'day' ? 'primary' : 'default'"
        @click="applyPreset('day')"
      >
        白天 (08:00-20:00)
      </el-button>
      <el-button
        size="small"
        :type="activePreset === 'night' ? 'primary' : 'default'"
        @click="applyPreset('night')"
      >
        夜晚 (20:00-08:00)
      </el-button>
      <span class="toolbar-divider" />
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="!selectedRange"
        @click="deleteSelectedRange"
      >
        删除
      </el-button>
      <el-button size="small" plain @click="clearAllSchedule">清空</el-button>
    </div>

    <div class="schedule-panel">
      <div class="schedule-axis">
        <div class="axis-label-spacer" />
        <div class="axis-track">
          <span
            v-for="tick in axisTicks"
            :key="tick.minute"
            class="axis-tick"
            :class="{ major: tick.minute % 60 === 0 }"
            :style="{ left: `${(tick.minute / (24 * 60)) * 100}%` }"
          >
            <span v-if="tick.minute % 60 === 0" class="axis-hour-label">{{ tick.minute / 60 }}</span>
          </span>
        </div>
        <div class="axis-action-spacer" />
      </div>

      <div
        v-for="day in WEEK_DAYS"
        :key="day.key"
        class="schedule-row"
      >
        <div class="day-label">{{ day.label }}</div>
        <div
          class="day-track"
          @mousedown="onTrackMouseDown($event, day.key)"
        >
          <template
            v-for="(segment, segIndex) in getDisplaySegments(day.key)"
            :key="`${day.key}-${segIndex}-${segment.startMin}-${segment.endMin}`"
          >
            <div
              class="range-bar"
              :class="{ selected: isRangeSelected(day.key, segment.rangeIndex) }"
              :style="getRangeStyle(segment)"
              @mousedown.stop="onRangeMouseDown($event, day.key, segment.rangeIndex, 'move')"
            >
              <span
                v-if="isRangeSelected(day.key, segment.rangeIndex) && segment.showStartLabel"
                class="range-time start"
              >
                {{ formatRangeTime(day.key, segment.rangeIndex, 'start') }}
              </span>
              <span
                v-if="isRangeSelected(day.key, segment.rangeIndex) && segment.showEndLabel"
                class="range-time end"
              >
                {{ formatRangeTime(day.key, segment.rangeIndex, 'end') }}
              </span>
              <span
                class="range-handle left"
                @mousedown.stop="onRangeMouseDown($event, day.key, segment.rangeIndex, 'resize-left')"
              />
              <span
                class="range-handle right"
                @mousedown.stop="onRangeMouseDown($event, day.key, segment.rangeIndex, 'resize-right')"
              />
            </div>
          </template>
        </div>
        <el-button link type="primary" class="copy-link" @click="copyDay(day.key)">复制</el-button>
      </div>
    </div>

    <el-dialog v-model="copyModalVisible" title="复制到其他日期" width="420px">
      <el-checkbox-group v-model="copyTargets" class="copy-targets">
        <el-checkbox
          v-for="day in WEEK_DAYS"
          :key="day.key"
          :label="day.key"
          :disabled="day.key === copySourceDay"
        >
          {{ day.label }}
        </el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="copyModalVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCopy">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  WEEK_DAYS,
  DAY_PRESET,
  NIGHT_DISPLAY_RANGES,
  cloneRanges,
  createDayPresetSchedule,
  createFullWeekSchedule,
  createNightPresetSchedule,
  isFullWeekSchedule,
  minutesToHHmm,
  normalizeRanges
} from '@/utils/weeklySchedule'

const SNAP_STEP = 15
const MIN_RANGE_MINUTES = 15
const DRAG_THRESHOLD = 4

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => createFullWeekSchedule()
  }
})

const emit = defineEmits(['update:modelValue'])

const axisTicks = Array.from({ length: 96 }, (_, index) => ({
  minute: index * SNAP_STEP
}))

const localSchedule = reactive(createFullWeekSchedule())
const copyModalVisible = ref(false)
const copySourceDay = ref('0')
const copyTargets = ref([])
const selectedRange = ref(null)

const dragState = reactive({
  active: false,
  moved: false,
  dayKey: '',
  mode: 'create',
  rangeIndex: -1,
  startMin: 0,
  trackRect: null,
  originStart: 0,
  originEnd: 0,
  dragStartX: 0
})

const activePreset = computed(() => {
  if (isFullWeekSchedule(localSchedule)) {
    return 'all'
  }
  const isSameOnAllDays = (matcher) => WEEK_DAYS.every(day => matcher(normalizeRanges(localSchedule[day.key], true)))

  if (isSameOnAllDays(ranges => ranges.length === 1
    && ranges[0].startMin === DAY_PRESET.startMin
    && ranges[0].endMin === DAY_PRESET.endMin)) {
    return 'day'
  }

  if (isSameOnAllDays(ranges => ranges.length === 2
    && ranges[0].startMin === NIGHT_DISPLAY_RANGES[0].startMin
    && ranges[0].endMin === NIGHT_DISPLAY_RANGES[0].endMin
    && ranges[1].startMin === NIGHT_DISPLAY_RANGES[1].startMin
    && ranges[1].endMin === NIGHT_DISPLAY_RANGES[1].endMin)) {
    return 'night'
  }

  return 'custom'
})

function syncFromProps(value) {
  WEEK_DAYS.forEach(day => {
    localSchedule[day.key] = cloneRanges(normalizeRanges(value?.[day.key], true))
  })
}

watch(
  () => props.modelValue,
  value => {
    syncFromProps(value)
  },
  { immediate: true, deep: true }
)

function emitChange() {
  const next = {}
  WEEK_DAYS.forEach(day => {
    next[day.key] = cloneRanges(normalizeRanges(localSchedule[day.key], true))
  })
  emit('update:modelValue', next)
}

function applyPreset(type) {
  const next = type === 'day'
    ? createDayPresetSchedule()
    : type === 'night'
      ? createNightPresetSchedule()
      : createFullWeekSchedule()
  syncFromProps(next)
  selectedRange.value = null
  emitChange()
}

function clearAllSchedule() {
  WEEK_DAYS.forEach(day => {
    localSchedule[day.key] = []
  })
  selectedRange.value = null
  emitChange()
}

function isOvernight(range) {
  return range.endMin <= range.startMin && range.endMin !== range.startMin
}

function getDisplaySegments(dayKey) {
  const segments = []
  const ranges = normalizeRanges(localSchedule[dayKey], true)
  ranges.forEach((range, rangeIndex) => {
    if (isOvernight(range)) {
      segments.push({
        startMin: range.startMin,
        endMin: 24 * 60,
        rangeIndex,
        showStartLabel: true,
        showEndLabel: false
      })
      segments.push({
        startMin: 0,
        endMin: range.endMin,
        rangeIndex,
        showStartLabel: false,
        showEndLabel: true
      })
      return
    }
    segments.push({
      ...range,
      rangeIndex,
      showStartLabel: true,
      showEndLabel: true
    })
  })
  return segments
}

function getRangeStyle(range) {
  const startPercent = (range.startMin / (24 * 60)) * 100
  const endPercent = (range.endMin / (24 * 60)) * 100
  return {
    left: `${startPercent}%`,
    width: `${Math.max(endPercent - startPercent, 1.5)}%`
  }
}

function snapMinutes(rawMinutes) {
  return Math.max(0, Math.min(24 * 60, Math.round(rawMinutes / SNAP_STEP) * SNAP_STEP))
}

function clientXToMinutes(clientX, trackRect) {
  const ratio = Math.max(0, Math.min(1, (clientX - trackRect.left) / trackRect.width))
  return snapMinutes(ratio * 24 * 60)
}

function isRangeSelected(dayKey, rangeIndex) {
  return selectedRange.value?.dayKey === dayKey && selectedRange.value?.rangeIndex === rangeIndex
}

function selectRange(dayKey, rangeIndex) {
  selectedRange.value = { dayKey, rangeIndex }
}

function clearSelection() {
  selectedRange.value = null
}

function formatRangeTime(dayKey, rangeIndex, edge) {
  const range = localSchedule[dayKey]?.[rangeIndex]
  if (!range) return ''
  const minute = edge === 'start' ? range.startMin : range.endMin
  return minutesToHHmm(minute)
}

function onTrackMouseDown(event, dayKey) {
  if (event.button !== 0) return
  clearSelection()
  const trackRect = event.currentTarget.getBoundingClientRect()
  const startMin = clientXToMinutes(event.clientX, trackRect)
  dragState.active = true
  dragState.moved = false
  dragState.dayKey = dayKey
  dragState.mode = 'create'
  dragState.rangeIndex = localSchedule[dayKey].length
  dragState.startMin = startMin
  dragState.trackRect = trackRect
  dragState.dragStartX = event.clientX
  localSchedule[dayKey].push({ startMin, endMin: startMin })
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}

function onRangeMouseDown(event, dayKey, index, mode) {
  if (event.button !== 0) return
  const trackRect = event.currentTarget.closest('.day-track').getBoundingClientRect()
  const range = localSchedule[dayKey][index]
  dragState.active = true
  dragState.moved = false
  dragState.dayKey = dayKey
  dragState.mode = mode
  dragState.rangeIndex = index
  dragState.trackRect = trackRect
  dragState.originStart = range.startMin
  dragState.originEnd = range.endMin
  dragState.dragStartX = event.clientX
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}

function onWindowMouseMove(event) {
  if (!dragState.active || !dragState.trackRect) return
  if (Math.abs(event.clientX - dragState.dragStartX) >= DRAG_THRESHOLD) {
    dragState.moved = true
  }

  const minute = clientXToMinutes(event.clientX, dragState.trackRect)
  const dayKey = dragState.dayKey
  const ranges = localSchedule[dayKey]
  const index = dragState.rangeIndex

  if (dragState.mode === 'create') {
    const start = Math.min(dragState.startMin, minute)
    const end = Math.max(dragState.startMin, minute)
    ranges[index] = { startMin: start, endMin: end }
    return
  }

  const range = ranges[index]
  if (dragState.mode === 'resize-left') {
    if (isOvernight(range)) {
      range.startMin = minute
    } else {
      range.startMin = Math.min(minute, range.endMin)
    }
    return
  }
  if (dragState.mode === 'resize-right') {
    if (isOvernight(range)) {
      range.endMin = minute
    } else {
      range.endMin = Math.max(minute, range.startMin)
    }
    return
  }

  const deltaX = event.clientX - dragState.dragStartX
  const deltaMin = snapMinutes((deltaX / dragState.trackRect.width) * 24 * 60)
  const duration = isOvernight({ startMin: dragState.originStart, endMin: dragState.originEnd })
    ? (24 * 60 - dragState.originStart) + dragState.originEnd
    : dragState.originEnd - dragState.originStart

  if (isOvernight({ startMin: dragState.originStart, endMin: dragState.originEnd })) {
    range.startMin = Math.max(0, Math.min(24 * 60, dragState.originStart + deltaMin))
    range.endMin = dragState.originEnd
    return
  }

  let nextStart = dragState.originStart + deltaMin
  nextStart = Math.max(0, Math.min(24 * 60 - duration, nextStart))
  range.startMin = nextStart
  range.endMin = nextStart + duration
}

function normalizeDay(dayKey) {
  localSchedule[dayKey] = normalizeRanges(localSchedule[dayKey], true)
}

function removeRange(dayKey, rangeIndex) {
  localSchedule[dayKey].splice(rangeIndex, 1)
  normalizeDay(dayKey)
  if (isRangeSelected(dayKey, rangeIndex)) {
    clearSelection()
  } else if (selectedRange.value?.dayKey === dayKey && selectedRange.value.rangeIndex > rangeIndex) {
    selectedRange.value = {
      dayKey,
      rangeIndex: selectedRange.value.rangeIndex - 1
    }
  }
  emitChange()
}

function deleteSelectedRange() {
  if (!selectedRange.value) return
  const { dayKey, rangeIndex } = selectedRange.value
  removeRange(dayKey, rangeIndex)
}

function onWindowMouseUp() {
  if (!dragState.active) return
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)

  const dayKey = dragState.dayKey
  const index = dragState.rangeIndex

  if (dragState.mode === 'create') {
    const range = localSchedule[dayKey][index]
    if (!range || Math.abs(range.endMin - range.startMin) < MIN_RANGE_MINUTES) {
      localSchedule[dayKey].splice(index, 1)
    } else {
      selectRange(dayKey, index)
    }
  } else if (dragState.mode === 'move' && !dragState.moved) {
    selectRange(dayKey, index)
  } else if (dragState.mode !== 'create') {
    selectRange(dayKey, index)
  }

  dragState.active = false
  normalizeDay(dayKey)
  emitChange()
}

function copyDay(dayKey) {
  copySourceDay.value = dayKey
  copyTargets.value = WEEK_DAYS
    .map(day => day.key)
    .filter(key => key !== dayKey)
  copyModalVisible.value = true
}

function confirmCopy() {
  const sourceRanges = cloneRanges(localSchedule[copySourceDay.value])
  copyTargets.value.forEach(key => {
    localSchedule[key] = cloneRanges(sourceRanges)
  })
  copyModalVisible.value = false
  emitChange()
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
})
</script>

<style scoped>
.weekly-time-schedule {
  width: 100%;
}

.schedule-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.toolbar-label {
  color: #606266;
  font-size: 13px;
}

.toolbar-divider {
  width: 1px;
  height: 16px;
  background: #dcdfe6;
  margin: 0 4px;
}

.schedule-panel {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}

.schedule-axis {
  display: grid;
  grid-template-columns: 72px 1fr 48px;
  align-items: end;
  margin-bottom: 8px;
}

.axis-track {
  position: relative;
  height: 28px;
  border-bottom: 1px solid #dcdfe6;
}

.axis-tick {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
  width: 1px;
  height: 4px;
  background: #e4e7ed;
}

.axis-tick.major {
  height: 8px;
  background: #dcdfe6;
}

.axis-hour-label {
  position: absolute;
  left: 50%;
  bottom: 10px;
  transform: translateX(-50%);
  font-size: 11px;
  color: #909399;
  line-height: 1;
  white-space: nowrap;
}

.schedule-row {
  display: grid;
  grid-template-columns: 72px 1fr 48px;
  align-items: center;
  margin-bottom: 8px;
}

.schedule-row:last-child {
  margin-bottom: 0;
}

.day-label {
  font-size: 13px;
  color: #303133;
}

.day-track {
  position: relative;
  height: 32px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  cursor: crosshair;
  overflow: visible;
}

.range-bar {
  position: absolute;
  top: 6px;
  bottom: 4px;
  background: #67c23a;
  border-radius: 3px;
  cursor: pointer;
  min-width: 6px;
  border: 2px solid transparent;
  box-sizing: border-box;
}

.range-bar.selected {
  background: #529b2e;
  border-color: #409eff;
  z-index: 2;
}

.range-bar:active {
  cursor: grabbing;
}

.range-time {
  position: absolute;
  top: -18px;
  font-size: 11px;
  line-height: 1;
  color: #409eff;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
}

.range-time.start {
  left: 0;
  transform: translateX(-50%);
}

.range-time.end {
  right: 0;
  transform: translateX(50%);
}

.range-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
}

.range-handle.left {
  left: -2px;
}

.range-handle.right {
  right: -2px;
}

.copy-link {
  padding: 0;
  font-size: 13px;
}

.copy-targets {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
}
</style>
