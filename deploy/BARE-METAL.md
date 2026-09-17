# RK3588 量产部署（Linux 裸机）

在盒子上使用 **Python venv + PostgreSQL + Nginx + systemd** 运行 `serve_unified.py`，推理 **`EDGE_INFERENCE=rknn`**。

## 1. 系统依赖

Debian / Ubuntu（arm64）示例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql ffmpeg nginx
```

创建数据库（按需改密码）：

```bash
sudo -u postgres psql -c "CREATE DATABASE edge_box;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'admin123';"
```

## 2. 部署目录

```bash
sudo mkdir -p /opt/edge-ai-box
sudo chown -R $USER:$USER /opt/edge-ai-box
# 将本仓库同步到 /opt/edge-ai-box
```

持久化目录：

| 路径 | 说明 |
|------|------|
| `backend/models/` | **`.rknn`**（量产） |
| `backend/storage/` | 事件图、抓拍 |
| `backend/uploads/` | 上传文件 |

## 3. Python 与 RKNN 运行时

```bash
cd /opt/edge-ai-box/backend
python3 -m venv .venv
source .venv/bin/activate
python -V       # 期望 3.8.x
pip install -U pip
pip install -r requirements.rk3588-py38.txt
# rknnlite 不在 requirements 里：安装 SDK 中 cp38 的 rknn_toolkit_lite2 whl（见 RKNN-EXPORT.md 第 3 节）
# pip install /path/to/rknn_toolkit_lite2-*-cp38-*linux_aarch64.whl
python -c "from rknnlite.api import RKNNLite; print('rknnlite ok')"
```

配置 **`backend/.env`**：

```env
DATABASE_URL=postgresql://postgres:你的密码@127.0.0.1:5432/edge_box
DETECT_SERVER_URL=http://127.0.0.1:8080
EDGE_INFERENCE=rknn
RKNN_CORE_MASK=0_1_2
EDGE_PORT=8080
```

首次启动（表结构由 ORM `create_all` 创建）：

```bash
source .venv/bin/activate
python serve_unified.py
```

## 4. 前端与 Nginx

在 **Windows 开发机** 构建后拷到盒子：

```bash
cd web && npm ci && npm run build
# 同步 web/dist 到 /opt/edge-ai-box/web/dist
```

Nginx：

```bash
sudo cp /opt/edge-ai-box/deploy/nginx.bare-metal.conf /etc/nginx/sites-available/edge-ai-box
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/edge-ai-box /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

若仍见 **Welcome to nginx!**，说明还在用默认站点，确认 `ls /etc/nginx/sites-enabled/` 只有 `edge-ai-box`，且存在 **`/opt/edge-ai-box/web/dist/index.html`**。

访问 **`http://盒子IP/`**（API 仍在本机 **8080**）。

## 5. 开机自启

```bash
sudo useradd -r -s /bin/false edge || true
sudo chown -R edge:edge /opt/edge-ai-box/backend/storage /opt/edge-ai-box/backend/uploads /opt/edge-ai-box/backend/models

sudo cp /opt/edge-ai-box/deploy/edge-unified.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edge-unified
journalctl -u edge-unified -f
```

## 6. 看日志

| 场景 | 命令 |
|------|------|
| **systemd 跑后端**（推荐） | `sudo journalctl -u edge-unified -f`（`-f` 跟踪；去掉 `-f` 翻历史；`-n 200` 最近 200 行） |
| 服务状态 | `sudo systemctl status edge-unified` |
| **手跑** `python serve_unified.py` | 日志在当前终端 stdout；检测/NPU 相关多为 `INFO:serve_detect`、`src.*` |
| **Nginx** | `sudo tail -f /var/log/nginx/error.log`；访问日志 `access.log` |
| **PostgreSQL** | `sudo tail -f /var/log/postgresql/postgresql-*-main.log`（路径因安装而异） |

RKNN 加载成功时在 **edge-unified** 日志里搜：`RKNN/NPU 适配器已加载`、`init_runtime`、检测任务启动行。

## 7. 模型与检测

- 上传 **`.rknn`**，参数 JSON **必填 `classes`**（见 [RKNN-EXPORT.md](./RKNN-EXPORT.md)）。
- Web「检测配置」启用任务；路数按 NPU 与拉流能力压测。
- 仅 **object_detection / face**；不支持 pose/segmentation。

## 8. 常见问题

- **`No matching distribution found for numpy==1.26.4`**：在盒子上误用了 **`requirements.rk3588.txt`**。请 `pip install -r requirements.rk3588-py38.txt`（Python 3.8）。
- **没有 `/dev/rknpu*` 但有 `fdab0000.npu` + `/dev/dri/renderD129`**：RK3588 新驱动走 **DRM**（`card1` / `renderD129`），**不必**绑定 `rknpu_dev.*.auto`，**不要**把 `renderD129` 软链成 `/dev/rknpu`（会报 `unsupported target type`）。确认：`readlink /sys/bus/platform/drivers/RKNPU/fdab0000.npu`；`sudo cat /sys/kernel/debug/rknpu/version`；安装与驱动匹配的 **librknnrt + rknn_toolkit_lite2** 后直接测 `RKNNLite().init_runtime()`。
- **既没有 `/dev/rknpu*` 也没有 `renderD129`**：NPU 驱动未就绪，查 `dmesg | grep RKNPU`、`librknnrt`、厂商镜像。
- **找不到 `rknn_toolkit_lite2*.whl`**：见 [RKNN-EXPORT.md](./RKNN-EXPORT.md) 第 3 节 `git clone` 安装 **cp38** wheel。
- **NPU init 失败**：驱动、`/dev/rknpu*`、rknnrt 与转换 toolkit 版本一致（建议 PC 与板端同为 toolkit **2.3.2**）。
- **连不上数据库**：`DATABASE_URL`、PostgreSQL、`pg_hba.conf`。
- **502**：Nginx `root` 指向 `web/dist`；`systemctl status edge-unified`。
- **WebSocket**：见 `nginx.bare-metal.conf` 中 `/ws/` 配置。

Windows 开发见根目录 **[README.md](../README.md)**。
