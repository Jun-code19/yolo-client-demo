"""边缘盒大屏辅助（不依赖 heatmap_routes）。"""
from sqlalchemy.orm import Session

from src.database import HeatmapDashboardConfig, PlatformSetting

DEFAULT_DASHBOARD_SCREEN_NAME = "边缘AI展示大屏"
DASHBOARD_SCREEN_NAME_SETTING_KEY = "dashboard_screen_name"


def resolve_dashboard_screen_name(db: Session) -> str:
    config = (
        db.query(HeatmapDashboardConfig)
        .filter(HeatmapDashboardConfig.is_active.is_(True))
        .order_by(HeatmapDashboardConfig.updated_at.desc())
        .first()
    )
    if config and config.screen_name:
        name = str(config.screen_name).strip()
        if name:
            return name

    setting = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.setting_key == DASHBOARD_SCREEN_NAME_SETTING_KEY)
        .first()
    )
    if setting and isinstance(setting.setting_value, dict):
        name = str(setting.setting_value.get("screen_name") or "").strip()
        if name:
            return name

    return DEFAULT_DASHBOARD_SCREEN_NAME
