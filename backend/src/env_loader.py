"""轻量 .env 加载（不依赖 python-dotenv）"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_ultralytics_env() -> None:
    """禁止 Ultralytics 运行时 pip 自动升级依赖（避免 onnx 拉取 numpy 2.2+）。"""
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("ULTRALYTICS_OFFLINE", "1")
    os.environ.setdefault("YOLO_NO_ANALYTICS", "1")
    os.environ.setdefault("NO_VERSION_CHECK", "1")


def load_env_file(env_path: str = ".env") -> None:
    path = Path(env_path)
    if not path.is_file():
        return
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


# 单进程 serve_unified 默认同端口
DEFAULT_DETECT_SERVER_URL = "http://127.0.0.1:8080"


def get_detect_server_url() -> str:
    """检测服务基址；单进程为 http://127.0.0.1:8080（与 EDGE_PORT 一致）"""
    return os.getenv("DETECT_SERVER_URL", DEFAULT_DETECT_SERVER_URL).rstrip("/")
