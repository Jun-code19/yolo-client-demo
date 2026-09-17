/**
 * 智能场景目录
 */

/** @deprecated 兼容旧引用，请用 SCENARIO_GROUPS */
export const SCENARIO_TYPE_OPTIONS = [];

export const SCENARIO_GROUPS = [
  {
    key: 'intrusion',
    label: '入侵检测',
    items: [
      { type: 'line_intrusion', label: '绊线入侵', available: true },
      { type: 'area_intrusion', label: '区域入侵', available: true },
    ],
  },
  {
    key: 'person',
    label: '人员场景',
    items: [
      { type: 'crowd_gather', label: '人员聚集', available: true },
      { type: 'leave_post', label: '离岗检测', available: true },
      { type: 'loitering', label: '徘徊检测', available: true },
    ],
  },
  {
    key: 'statistics',
    label: '人数统计',
    items: [
      { type: 'occupancy', label: '区域人数', available: true },
      { type: 'flow_count', label: '人流统计', available: true },
    ],
  },
];

SCENARIO_GROUPS.forEach((group) => {
  group.items.forEach((item) => SCENARIO_TYPE_OPTIONS.push(item));
});

const TYPE_LABEL_MAP = SCENARIO_TYPE_OPTIONS.reduce((acc, item) => {
  acc[item.type] = item.label;
  return acc;
}, {});

/** 后端实际处理的 type */
const BACKEND_TYPE_MAP = {
  line_intrusion: 'behavior',
  area_intrusion: 'behavior',
  occupancy: 'counting',
  flow_count: 'counting',
};

export function getScenarioTypeLabel(type) {
  return TYPE_LABEL_MAP[type] || type || '未知场景';
}

export function createScenarioId() {
  return `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function baseScenario(type, name) {
  return {
    id: createScenarioId(),
    catalogType: type,
    type: BACKEND_TYPE_MAP[type] || type,
    name,
    enabled: true,
    points: [],
    params: {},
    pushLabel: '',
  };
}

export function createScenario(type) {
  const meta = SCENARIO_TYPE_OPTIONS.find((item) => item.type === type);
  if (!meta?.available) {
    throw new Error(`${meta?.label || type} 暂未开放`);
  }

  if (type === 'line_intrusion') {
    return {
      ...baseScenario(type, '绊线入侵'),
      behaviorType: 'line',
      behaviorSubtype: 'simple',
      behaviorDirection: 'in',
    };
  }

  if (type === 'area_intrusion') {
    return {
      ...baseScenario(type, '区域入侵'),
      behaviorType: 'area',
      behaviorSubtype: 'directional',
      behaviorDirection: 'in',
    };
  }

  if (type === 'leave_post') {
    return {
      ...baseScenario(type, '离岗检测'),
      params: { minPersons: 1, durationSec: 300 },
    };
  }

  if (type === 'crowd_gather') {
    return {
      ...baseScenario(type, '人员聚集'),
      params: { minPersons: 5, durationSec: 30 },
    };
  }

  if (type === 'loitering') {
    return {
      ...baseScenario(type, '徘徊检测'),
      params: { minPersons: 1, durationSec: 60 },
    };
  }

  if (type === 'occupancy') {
    return {
      ...baseScenario(type, '区域人数'),
      countingType: 'occupancy',
      occupancyAreas: [],
      countingInterval: 5,
      maxCapacity: 100,
      smoothWindow: 3,
      decreaseHoldFrames: 2,
      countBias: 0,
      countScale: 1,
      countPointMode: 'foot',
      countMinHits: 3,
      enableAlert: false,
      alertThreshold: 50,
    };
  }

  if (type === 'flow_count') {
    return {
      ...baseScenario(type, '人流统计'),
      countingType: 'flow',
      flowDirection: 'bidirectional',
      flowPeriod: 'detect_in',
    };
  }

  // 兼容旧 type
  if (type === 'behavior') {
    return {
      ...baseScenario(type, '行为分析'),
      behaviorType: 'area',
      behaviorSubtype: 'simple',
      behaviorDirection: 'in',
    };
  }

  if (type === 'counting') {
    return createScenario('occupancy');
  }

  return baseScenario(type, meta?.label || type);
}

export function getRuleDisplayType(scenario) {
  if (!scenario) return '';
  if (scenario.catalogType) {
    return getScenarioTypeLabel(scenario.catalogType);
  }
  if (scenario.type === 'behavior') {
    if (scenario.behaviorType === 'line') return '绊线入侵';
    return '区域入侵';
  }
  if (scenario.type === 'counting') {
    return scenario.countingType === 'flow' ? '人流统计' : '区域人数统计';
  }
  return getScenarioTypeLabel(scenario.type);
}

export function migrateAreaCoordinates(areaCoordinates) {
  if (!areaCoordinates || Object.keys(areaCoordinates).length === 0) {
    return {
      version: 2,
      alarm_interval: 15,
      pushLabel: '',
      scenarios: [],
    };
  }

  if (areaCoordinates.version === 2 || Array.isArray(areaCoordinates.scenarios)) {
    return {
      version: 2,
      alarm_interval: areaCoordinates.alarm_interval ?? 15,
      pushLabel: areaCoordinates.pushLabel || '',
      scenarios: (areaCoordinates.scenarios || []).map((scenario) => migrateLegacyScenario({ ...scenario })),
    };
  }

  if (!areaCoordinates.analysisType || areaCoordinates.analysisType === 'none') {
    return {
      version: 2,
      alarm_interval: areaCoordinates.alarm_interval ?? 15,
      pushLabel: areaCoordinates.pushLabel || '',
      scenarios: [],
    };
  }

  return {
    version: 2,
    alarm_interval: areaCoordinates.alarm_interval ?? 15,
    pushLabel: areaCoordinates.pushLabel || '',
    scenarios: [migrateLegacyScenario({
      ...areaCoordinates,
      id: areaCoordinates.id || 'legacy-1',
      enabled: true,
      type: areaCoordinates.analysisType === 'behavior' ? 'behavior' : 'counting',
      points: areaCoordinates.points || [],
      params: {},
    })],
  };
}

function migrateLegacyScenario(scenario) {
  if (!scenario.catalogType) {
    if (scenario.type === 'behavior') {
      scenario.catalogType = scenario.behaviorType === 'line' ? 'line_intrusion' : 'area_intrusion';
    } else if (scenario.type === 'counting') {
      scenario.catalogType = scenario.countingType === 'flow' ? 'flow_count' : 'occupancy';
    } else if (scenario.type === 'leave_post' || scenario.type === 'crowd_gather' || scenario.type === 'loitering') {
      scenario.catalogType = scenario.type;
    }
  }
  if (!scenario.params) {
    scenario.params = {};
  }
  return scenario;
}

export function buildAreaCoordinatesPayload(multiConfig) {
  return {
    version: 2,
    alarm_interval: multiConfig.alarm_interval ?? 15,
    pushLabel: multiConfig.pushLabel || '',
    scenarios: (multiConfig.scenarios || []).map((scenario) => ({ ...scenario })),
  };
}

export function getScenarioDrawMode(scenario) {
  if (!scenario) return null;
  const catalog = scenario.catalogType;
  if (catalog === 'line_intrusion' || catalog === 'flow_count') return 'line';
  if (catalog === 'area_intrusion' || catalog === 'leave_post' || catalog === 'crowd_gather' || catalog === 'loitering') {
    return 'area';
  }
  if (catalog === 'occupancy') return 'area';
  if (scenario.type === 'behavior') {
    return scenario.behaviorType === 'line' ? 'line' : 'area';
  }
  if (scenario.type === 'counting') {
    return scenario.countingType === 'flow' ? 'line' : 'area';
  }
  if (scenario.type === 'leave_post' || scenario.type === 'crowd_gather' || scenario.type === 'loitering') {
    return 'area';
  }
  return 'area';
}

export function shouldCloseScenarioArea(scenario) {
  return getScenarioDrawMode(scenario) === 'area';
}

export function getScenarioSummaryLabel(areaCoordinates) {
  const migrated = migrateAreaCoordinates(areaCoordinates);
  const scenarios = (migrated.scenarios || []).filter((item) => item.enabled !== false);
  if (!scenarios.length) {
    return '无智能方案';
  }
  if (scenarios.length === 1) {
    return getRuleDisplayType(scenarios[0]);
  }
  const labels = [...new Set(scenarios.map((item) => getRuleDisplayType(item)))];
  return `${scenarios.length}个场景（${labels.join('、')}）`;
}

export function validateScenario(scenario, index = 0) {
  const prefix = scenario.name || `场景${index + 1}`;
  const drawMode = getScenarioDrawMode(scenario);

  if (drawMode === 'area') {
    if (scenario.catalogType === 'occupancy' || (scenario.type === 'counting' && scenario.countingType === 'occupancy')) {
      const areas = scenario.occupancyAreas || [];
      if (!areas.length) {
        throw new Error(`${prefix}：请至少绘制一个统计区域`);
      }
      for (const area of areas) {
        if (!area.points || area.points.length < 3) {
          throw new Error(`${area.name || prefix}：区域至少需要3个顶点`);
        }
      }
      return;
    }
    if (!scenario.points || scenario.points.length < 3) {
      throw new Error(`${prefix}：请绘制至少3个顶点的区域`);
    }
    return;
  }

  if (drawMode === 'line') {
    if (!scenario.points || scenario.points.length < 2) {
      throw new Error(`${prefix}：请绘制有效的拌线（至少2个点）`);
    }
  }
}

export function createDefaultRuleName(index) {
  return `场景-${index}`;
}

export function isDurationScenario(scenario) {
  if (!scenario) return false;
  const key = scenario.catalogType || scenario.type;
  return key === 'leave_post' || key === 'crowd_gather' || key === 'loitering';
}

export function isLineScenario(scenario) {
  if (!scenario) return false;
  return scenario.catalogType === 'line_intrusion'
    || scenario.catalogType === 'flow_count'
    || (scenario.type === 'behavior' && scenario.behaviorType === 'line')
    || (scenario.type === 'counting' && scenario.countingType === 'flow');
}

export function isOccupancyScenario(scenario) {
  if (!scenario) return false;
  return scenario.catalogType === 'occupancy'
    || (scenario.type === 'counting' && scenario.countingType === 'occupancy');
}
