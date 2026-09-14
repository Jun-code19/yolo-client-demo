# Edge AI Box（RK3588 边缘检测盒）

纯边缘、多路监控告警产品。**本仓库只放部署与脚本**；算法与业务代码在核心仓库 [yolo-demo](../yolo-demo)（可改为 git submodule `core/`）。

## 目录关系

```
yolo-client-demo/
├── yolo-demo/          # 核心：检测、事件、推送、规则引擎、前端源码
└── edge-ai-box/        # 本产品：Docker、nginx、边缘配置、开发脚本
```

## 本地开发（Windows）

```powershell
# 终端 1 — data
.\scripts\dev-data.ps1

# 终端 2 — detect（DEPLOY_MODE=edge）
.\scripts\dev-detect.ps1

# 终端 3 — 边缘 UI
.\scripts\dev-web.ps1
```

核心路径默认 `../yolo-demo`，可设环境变量 `YOLO_CORE`。

## Docker（盒子 / 服务器）

```bash
cp env.example .env
docker compose up -d --build
```

浏览器访问 `http://<盒子IP>/`。

## 边缘模式说明

- 环境变量 `DEPLOY_MODE=edge`（detect 服务）
- 前端构建 `VITE_DEPLOY_MODE=edge`（隐藏 VLM、人员搜索、人群分析等）
- 后续：RK3588 专用镜像与 RKNN 推理在本仓库增加 `Dockerfile.detect.rk3588` 等

## 独立 Git 仓库

若要将本产品单独成库，在 `edge-ai-box` 目录：

```bash
git init -b main
git add .
git commit -m "Initial edge-ai-box product layout"
```

并将 `yolo-demo` 添加为 submodule：

```bash
git submodule add <yolo-demo-url> core
# 然后将 compose 中 YOLO_CORE 改为 ./core
```
