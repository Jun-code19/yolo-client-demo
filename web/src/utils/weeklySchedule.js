export const WEEK_DAYS = [
  { key: '0', label: '星期日' },
  { key: '1', label: '星期一' },
  { key: '2', label: '星期二' },
  { key: '3', label: '星期三' },
  { key: '4', label: '星期四' },
  { key: '5', label: '星期五' },
  { key: '6', label: '星期六' }
]

export const DAY_PRESET = {
  startMin: 8 * 60,
  endMin: 20 * 60
}

export const NIGHT_PRESET = {
  startMin: 20 * 60,
  endMin: 8 * 60
}

export const NIGHT_DISPLAY_RANGES = [
  { startMin: 0, endMin: 8 * 60 },
  { startMin: 20 * 60, endMin: 24 * 60 }
]

export const FULL_DAY_RANGE = { startMin: 0, endMin: 24 * 60 }

export function cloneRanges(ranges = []) {
  return ranges.map(item => ({ startMin: item.startMin, endMin: item.endMin }))
}

export function createFullWeekSchedule() {
  const schedule = {}
  WEEK_DAYS.forEach(day => {
    schedule[day.key] = [cloneRanges([FULL_DAY_RANGE])[0]]
  })
  return schedule
}

export function createDayPresetSchedule() {
  const schedule = {}
  WEEK_DAYS.forEach(day => {
    schedule[day.key] = cloneRanges([DAY_PRESET])
  })
  return schedule
}

export function createNightPresetSchedule() {
  const schedule = {}
  WEEK_DAYS.forEach(day => {
    schedule[day.key] = cloneRanges(NIGHT_DISPLAY_RANGES)
  })
  return schedule
}

export function minutesToHHmm(minutes) {
  const value = Math.max(0, Math.min(24 * 60, Math.round(minutes)))
  if (value >= 24 * 60) {
    return '24:00'
  }
  const hours = Math.floor(value / 60)
  const mins = value % 60
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

export function hhmmToMinutes(value, fallback = 0) {
  if (!value || !String(value).includes(':')) {
    return fallback
  }
  const [hours, minutes] = String(value).split(':').map(Number)
  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return fallback
  }
  if (hours === 24 && minutes === 0) {
    return 24 * 60
  }
  return Math.max(0, Math.min(24 * 60, hours * 60 + minutes))
}

export function normalizeRanges(ranges = [], allowEmpty = false) {
  const cleaned = (ranges || [])
    .map(item => ({
      startMin: Math.max(0, Math.min(24 * 60, Number(item.startMin ?? item.start ?? 0))),
      endMin: Math.max(0, Math.min(24 * 60, Number(item.endMin ?? item.end ?? 0)))
    }))
    .filter(item => item.endMin !== item.startMin)

  if (!cleaned.length) {
    return allowEmpty ? [] : cloneRanges([FULL_DAY_RANGE])
  }

  return cleaned
    .map(item => {
      if (item.endMin < item.startMin) {
        return item
      }
      return {
        startMin: Math.min(item.startMin, item.endMin),
        endMin: Math.max(item.startMin, item.endMin)
      }
    })
    .sort((a, b) => a.startMin - b.startMin)
}

export function isFullWeekSchedule(schedule) {
  if (!schedule) return true
  return WEEK_DAYS.every(day => {
    const ranges = normalizeRanges(schedule[day.key], true)
    return ranges.length === 1
      && ranges[0].startMin === 0
      && ranges[0].endMin === 24 * 60
  })
}

export function scheduleToBackend(schedule) {
  const result = {}
  WEEK_DAYS.forEach(day => {
    result[day.key] = normalizeRanges(schedule?.[day.key], true).map(item => ({
      start: minutesToHHmm(item.startMin),
      end: minutesToHHmm(item.endMin)
    }))
  })
  return result
}

export function scheduleFromBackend(weeklySchedule) {
  if (!weeklySchedule || typeof weeklySchedule !== 'object') {
    return createFullWeekSchedule()
  }
  const schedule = {}
  WEEK_DAYS.forEach(day => {
    const ranges = weeklySchedule[day.key] || weeklySchedule[Number(day.key)]
    if (!Array.isArray(ranges)) {
      schedule[day.key] = cloneRanges([FULL_DAY_RANGE])
      return
    }
    schedule[day.key] = normalizeRanges(
      ranges.map(item => ({
        startMin: hhmmToMinutes(item.start, 0),
        endMin: hhmmToMinutes(item.end, 24 * 60)
      })),
      true
    )
  })
  return schedule
}

export function legacyRuntimeToSchedule(runtime = {}) {
  const mode = runtime.time_period_mode || 'all'
  if (mode === 'all') {
    return createFullWeekSchedule()
  }
  if (mode === 'day_night') {
    const scope = runtime.day_night_scope || 'both'
    const dayRange = {
      startMin: hhmmToMinutes(runtime.day_start, DAY_PRESET.startMin),
      endMin: hhmmToMinutes(runtime.day_end, DAY_PRESET.endMin)
    }
    const nightRange = {
      startMin: hhmmToMinutes(runtime.night_start, NIGHT_PRESET.startMin),
      endMin: hhmmToMinutes(runtime.night_end, NIGHT_PRESET.endMin)
    }
    const schedule = {}
    WEEK_DAYS.forEach(day => {
      if (scope === 'day') {
        schedule[day.key] = cloneRanges([dayRange])
      } else if (scope === 'night') {
        schedule[day.key] = cloneRanges([
          { startMin: 0, endMin: nightRange.endMin },
          { startMin: nightRange.startMin, endMin: 24 * 60 }
        ])
      } else {
        schedule[day.key] = cloneRanges([FULL_DAY_RANGE])
      }
    })
    return schedule
  }
  const customRanges = (runtime.custom_ranges || []).map(item => ({
    startMin: hhmmToMinutes(item.start, 8 * 60),
    endMin: hhmmToMinutes(item.end, 20 * 60)
  }))
  const schedule = {}
  WEEK_DAYS.forEach(day => {
    schedule[day.key] = cloneRanges(customRanges.length ? customRanges : [FULL_DAY_RANGE])
  })
  return schedule
}

export function formatScheduleSummary(schedule) {
  if (isFullWeekSchedule(schedule)) {
    return '全时段'
  }

  const serializeDay = (dayKey) => normalizeRanges(schedule?.[dayKey], true)
    .map(item => `${minutesToHHmm(item.startMin)}-${minutesToHHmm(item.endMin)}`)
    .join(', ')

  const base = serializeDay('0')
  const allSame = WEEK_DAYS.every(day => serializeDay(day.key) === base)
  if (allSame && base) {
    return `每周 ${base}`
  }
  return '按周自定义'
}
