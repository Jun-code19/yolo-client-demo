# RK3588 量产部署（Linux 裸机）

在盒子上使用 **Python venv + PostgreSQL + Nginx + systemd** 运行 `serve_unified.py`，推理 **`EDGE_INFERENCE=rknn`**。

## 1. 系统依赖

Debian / Ubuntu（arm64）示例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql ffmpeg nginx \
  fonts-wqy-zenhei fonts-noto-cjk
```

- **ffmpeg**：RTSP 探活、部分解码场景。
- **中文字体**：预览/叠加绘制中文类名、人数统计；缺字体时可能报 `latin-1` 编码错误或显示为 `?`。可选环境变量 **`EDGE_CJK_FONT=/path/to/font.ttc`**。

创建数据库（按需改密码）：

```bash
sudo -u postgres psql -c "CREATE DATABASE edge_box;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'admin123';"
```

## 2. 部署目录

```bash
sudo mkdir -p /opt/edge-ai-box
sudo chown -R $USER:$USER /opt/edge-ai-box
# 将本仓库同步到 /opt/edge-ai-box（git rsync/scp 均可）
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

配置 **`backend/.env`**（`edge-unified.service` 通过 **`EnvironmentFile=`** 加载；`systemctl show -p Environment` 为空属正常）：

```env
DATABASE_URL=postgresql://postgres:你的密码@127.0.0.1:5432/edge_box
DETECT_SERVER_URL=http://127.0.0.1:8080
EDGE_INFERENCE=rknn
RKNN_CORE_MASK=0_1_2
RKNN_INPUT_UINT8=1
EDGE_PORT=8080
# 可选
# EDGE_APP_VERSION=1.0.0
# EDGE_CJK_FONT=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
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

## 5. 开机自启（systemd）

### 5.1 运行用户与目录权限

```bash
sudo useradd -r -s /bin/false edge || true
sudo usermod -aG render,video edge
sudo chown -R edge:edge /opt/edge-ai-box/backend/storage \
  /opt/edge-ai-box/backend/uploads \
  /opt/edge-ai-box/backend/models
```

NPU 走 DRM 时需 **`render` / `video`** 组，改组后需 **`systemctl restart edge-unified`**。

### 5.2 单元说明

| 单元 | 作用 |
|------|------|
| **`edge-unified.service`** | 主进程：`serve_unified.py`（User=`edge`） |
| **`edge-rknpu-debugfs.service`** | 启动时挂载 debugfs，生成 NPU 负载快照 |
| **`edge-rknpu-debugfs-refresh.timer`** | 每 5 秒刷新 `/run/edge-ai-box/rknpu-load` |

`deploy/` 内脚本在 Windows 拷贝到盒子后建议去 CRLF：

```bash
sudo sed -i 's/\r$//' /opt/edge-ai-box/deploy/edge-rknpu-debugfs-pre.sh
sudo chmod +x /opt/edge-ai-box/deploy/edge-rknpu-debugfs-pre.sh
```

### 5.3 安装并启用

```bash
sudo cp /opt/edge-ai-box/deploy/edge-rknpu-debugfs.service /etc/systemd/system/
sudo cp /opt/edge-ai-box/deploy/edge-rknpu-debugfs-refresh.service /etc/systemd/system/
sudo cp /opt/edge-ai-box/deploy/edge-rknpu-debugfs-refresh.timer /etc/systemd/system/
sudo cp /opt/edge-ai-box/deploy/edge-unified.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edge-rknpu-debugfs edge-rknpu-debugfs-refresh.timer edge-unified
```

检查：

```bash
sudo systemctl status edge-unified edge-rknpu-debugfs edge-rknpu-debugfs-refresh.timer
sudo journalctl -u edge-unified -n 50 --no-pager
```

### 5.4 代码更新后

```bash
# 同步仓库后
cd /opt/edge-ai-box/backend && source .venv/bin/activate
# 若 requirements 有变：pip install -r requirements.rk3588-py38.txt
sudo cp /opt/edge-ai-box/deploy/*.service /opt/edge-ai-box/deploy/*.timer /etc/systemd/system/ 2>/dev/null || true
sudo sed -i 's/\r$//' /opt/edge-ai-box/deploy/edge-rknpu-debugfs-pre.sh
sudo systemctl daemon-reload
sudo systemctl restart edge-rknpu-debugfs edge-unified
# 前端有改：在 PC 上 npm run build，再同步 web/dist
sudo systemctl reload nginx
```

## 6. 日志与 NPU 监控

### 6.1 看日志

| 场景 | 命令 |
|------|------|
| **systemd 跑后端**（推荐） | `sudo journalctl -u edge-unified -f` |
| 服务状态 | `sudo systemctl status edge-unified` |
| **手跑** `python serve_unified.py` | 日志在当前终端 stdout |
| **Nginx** | `sudo tail -f /var/log/nginx/error.log` |
| **PostgreSQL** | `sudo tail -f /var/log/postgresql/postgresql-*-main.log` |

RKNN 加载成功时在 **edge-unified** 日志里搜：`RKNN/NPU 适配器已加载`、`init_runtime`、检测任务启动行。

### 6.2 NPU 是否在跑

```bash
grep EDGE_INFERENCE /opt/edge-ai-box/backend/.env
sudo journalctl -u edge-unified -n 300 | grep -E 'RKNN|NPU|init_runtime'
watch -n 1 'sudo cat /sys/kernel/debug/rknpu/load 2>/dev/null'
```

有检测任务时 `load` 中 Core0/1/2 通常会有百分比。

### 6.3 Web / API 上的 NPU 负载

内核数据在 **debugfs**（`/sys/kernel/debug/rknpu/load`），**edge 用户往往无法直接进入该目录**。因此：

1. **`edge-rknpu-debugfs-pre.sh`**（root）把内容写入 **`/run/edge-ai-box/rknpu-load`**（`root:edge`，644）。
2. **`edge-rknpu-debugfs-refresh.timer`** 每 5 秒刷新。
3. 后端 **`/api/v1/system/status`**、展板 **`/api/v1/dashboard/system-status`** 优先读 debugfs，失败则读 `/run/edge-ai-box/`。

验证（以 edge 为准，与 Web 一致）：

```bash
sudo systemctl start edge-rknpu-debugfs
sudo systemctl start edge-rknpu-debugfs-refresh.timer
sudo -u edge cat /run/edge-ai-box/rknpu-load
```

Web：**系统管理 → 系统状态**、**数据展板 → 系统资源**（约 5 秒刷新）。

## 7. 模型与检测

- 上传 **`.rknn`**，参数 JSON **必填 `classes`**（见 [RKNN-EXPORT.md](./RKNN-EXPORT.md)）。
- Web「检测配置」启用任务；路数按 NPU 与拉流能力压测。
- **多路检测 / 多个 `.rknn`**：同模型多任务共用 RKNN 实例；**NPU 推理进程内全局串行**（避免多任务并发踩 NPU 内存）。路数多时延迟排队属正常。
- 仅 **object_detection / face**；不支持 pose/segmentation。

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| **`No matching distribution found for numpy==1.26.4`** | 盒子上用 **`requirements.rk3588-py38.txt`**（Python 3.8），勿用 `requirements.rk3588.txt`。 |
| **无 `/dev/rknpu*` 有 `renderD129`** | 新驱动走 **DRM**；确认 `readlink .../fdab0000.npu`、`librknnrt`、**`edge` 在 render/video 组**。 |
| **`Can not find dynamic library` / librknnrt** | `sudo ln -sf /usr/lib/aarch64-linux-gnu/librknnrt.so /usr/lib/librknnrt.so && sudo ldconfig` |
| **toolkit 2.3.2 vs runtime 1.5.2 警告** | 若 `init_runtime` 成功且检测正常，可先观察；异常再对齐 PC/板端 rknn 版本。 |
| **Web NPU 无百分比** | 确认 timer 与 `sudo -u edge cat /run/edge-ai-box/rknpu-load`；重启 `edge-rknpu-debugfs*` 与 `edge-unified`。 |
| **`edge-rknpu-debugfs` failed / `set:` 报错** | 脚本 CRLF：`sudo sed -i 's/\r$//' .../edge-rknpu-debugfs-pre.sh`；手动 `sudo /bin/sh .../edge-rknpu-debugfs-pre.sh`。 |
| **`edge-unified` 因 ExecStartPre 启动失败** | 使用当前 **`edge-unified.service`（无 ExecStartPre）** + 独立 **`edge-rknpu-debugfs`** 单元。 |
| **绘制文字失败 latin-1 / `\u4eba`** | `apt install fonts-wqy-zenhei` 或设置 **`EDGE_CJK_FONT`**；部署含 **`backend/src/cjk_font.py`** 的后端。 |
| **设备监控配置 401** | 需登录；Token 过期后重新登录。 |
| **502** | Nginx `root` → `web/dist`；`systemctl status edge-unified`。 |
| **连不上数据库** | `DATABASE_URL`、PostgreSQL、`pg_hba.conf`。 |

Windows 开发见根目录 **[README.md](../README.md)**。
