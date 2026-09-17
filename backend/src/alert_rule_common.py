"""复合告警规则共享常量（data-server / detect-server 均可导入，无调度器依赖）"""
from __future__ import annotations

import os

DEFAULT_EVAL_INTERVAL_SEC = 60
DEFAULT_WINDOW_SEC = 300
DEFAULT_COOLDOWN_SEC = 60

SUPPORTED_SOURCES = {"detection_event", "external_event", "smart_event"}

DETECTION_MATCH_MODES = {"event", "target", "absence"}
COUNT_OPS = {"gte", "lte", "eq", "gt", "lt"}


def get_eval_interval_sec() -> int:
    raw = os.getenv("ALERT_RULE_EVAL_INTERVAL_SEC", str(DEFAULT_EVAL_INTERVAL_SEC))
    try:
        value = int(raw)
        return max(10, value)
    except (TypeError, ValueError):
        return DEFAULT_EVAL_INTERVAL_SEC
