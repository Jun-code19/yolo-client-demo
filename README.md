# Edge AI Box（边缘 AI 检测盒）

**独立产品仓库**：与 `yolo-demo` 无耦合，面向 **RK3588 量产（NPU）** 与 **Windows 本地开发**。

## 能力范围

| 包含 | 不包含（平台版在 yolo-demo） |
|------|------------------------------|
| 多路 YOLO 检测、事件、预览 WebSocket | 人员搜索 / ReID |
| 规则引擎、推送、**事件订阅** | **事件监听**（TCP/MQTT/HTTP 接入） |
| 设备 / 分组、模型、系统管理 | VLM、人群分析、热力图、边缘节点纳管 |

## 两种使用场景

| 场景 | 环境 | 推理 | 文档 |
|------|------|------|------|
| **RK3588 量产 / NPU** | 盒子 Linux + venv + systemd + Nginx | **`EDGE_INFERENCE=rknn`** + **`.rknn`** | [deploy/BARE-METAL.md](deploy/BARE-METAL.md)、[deploy/RKNN-EXPORT.md](deploy/RKNN-EXPORT.md) |
| **Windows 本地开发** | PostgreSQL + `dev-unified.ps1` + `web` dev | 默认 **`onnx`（CPU）**；可选 **`ultralytics` + `.pt`** | 下文 |

- 单进程入口：**`serve_unified.py` → 8080**（`/api/v1` 管理 + `/api/v2` 检测 + WebSocket）。
- 数据库库名：**`edge_box`**。
- 开发机用 **ONNX** 验证业务；**NPU 仅盒子 + RKNN**（见 RKNN 转换文档）。

```
edge-ai-box/
├── backend/          # serve_unified.py、api/、src/
├── web/
├── deploy/           # RK3588 部署、Nginx、systemd、RKNN 说明
└── scripts/          # setup-backend.ps1、dev-unified.ps1
```

## Windows 本地开发

1. 安装 **PostgreSQL**，创建库 **`edge_box`**。
2. 在 `edge-ai-box` 根目录：

```powershell
# 与 RK3588 运行时一致（ONNX、无 torch）
.\scripts\setup-backend.ps1 -Onnx

copy backend\.env.example backend\.env
# 编辑 DATABASE_URL=postgresql://postgres:密码@127.0.0.1:5432/edge_box
```

若要调试 **`.pt` 模型**：`.\scripts\setup-backend.ps1`，`.env` 设 `EDGE_INFERENCE=ultralytics`。

3. 启动：

```powershell
.\scripts\dev-unified.ps1    # http://127.0.0.1:8080
cd web; npm run dev            # http://127.0.0.1:5173 → 代理 8080
```

模型放 **`backend/models/`**（开发用 `.onnx`；盒子量产用 `.rknn`）。

## RK3588 量产（摘要）

1. 按 **[deploy/BARE-METAL.md](deploy/BARE-METAL.md)** 安装 Postgres、venv（**`requirements.rk3588-py38.txt`**，系统 Python 3.8）、Nginx、systemd。
2. PC 上把 YOLO 转为 **`.rknn`**：**[deploy/RKNN-EXPORT.md](deploy/RKNN-EXPORT.md)**。
3. 盒子 **`EDGE_INFERENCE=rknn`**，安装 **rknn-toolkit-lite2**，上传模型并在参数中填写 **`classes`**。

总览与约束：**[deploy/RK3588.md](deploy/RK3588.md)**。

## 与 yolo-demo 的关系

本仓库由平台版拷贝后独立演进；同步逻辑请手动 cherry-pick。
