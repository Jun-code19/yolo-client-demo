"""detect-server：复合告警规则评估（含推送）"""
from fastapi import APIRouter

from src.alert_rule_common import get_eval_interval_sec
from src.alert_rule_engine import evaluate_rules

router = APIRouter(prefix="/alert-rules", tags=["复合告警规则"])


@router.post("/evaluate")
def trigger_evaluate():
    stats = evaluate_rules()
    return {"success": True, "stats": stats}


@router.get("/meta")
def get_runtime_meta():
    return {"eval_interval_sec": get_eval_interval_sec(), "runtime": "detect-server"}
