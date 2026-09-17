"""
边缘盒单进程入口：检测 (/api/v2、WebSocket、storage) + 管理 (/api/v1) 同一端口。

环境变量：
  EDGE_PORT — 默认 8080
  DETECT_SERVER_URL — 单进程时设为 http://127.0.0.1:8080（供 routes 内转发检测接口）
"""
import os

from src.env_loader import configure_ultralytics_env, load_env_file

configure_ultralytics_env()
load_env_file()

port = int(os.getenv("EDGE_PORT", "8080"))
os.environ.setdefault("DETECT_SERVER_URL", f"http://127.0.0.1:{port}")
os.environ.setdefault("EDGE_UNIFIED", "1")

# 检测服务 app（含 lifespan、/api/v2）
import serve_detect  # noqa: E402

from edge_bootstrap import register_management_routes  # noqa: E402

app = serve_detect.app
app.title = "Edge AI Box"
app.description = "边缘检测盒 — 检测与管理合一"

register_management_routes(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)
