"""边缘盒：管理 API（/api/v1）与库表迁移；检测运行时见 serve_detect（/api/v2）。"""
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def ensure_edge_schema() -> None:
    """新库由 ORM 模型一次性建表；不跑历史 ALTER 补丁。"""
    from src.database import Base, engine

    Base.metadata.create_all(bind=engine)


def register_management_routes(app: FastAPI) -> None:
    from api.routes import router

    app.include_router(router, prefix="/api/v1")

    from api.smart_scheme_routes import router as smart_scheme_router
    from api.base_dashboard import router as dashboard_router
    from api.dashboard_integrations import router as dashboard_integrations_router
    from api.device_monitor_settings import router as device_monitor_settings_router
    from api.device_monitor_routes import router as device_monitor_runtime_router
    from api.device_group_routes import router as device_group_router
    from api.alert_rule_routes import router as alert_rule_router

    app.include_router(smart_scheme_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(dashboard_integrations_router, prefix="/api/v1")
    app.include_router(device_monitor_settings_router, prefix="/api/v1")
    app.include_router(device_monitor_runtime_router, prefix="/api/v1")
    app.include_router(device_group_router, prefix="/api/v1")
    app.include_router(alert_rule_router, prefix="/api/v1")

    logger.info("Edge management API mounted at /api/v1")
