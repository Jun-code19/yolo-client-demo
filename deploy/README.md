# 部署与 RK3588 文档索引

| 文档 / 文件 | 用途 |
|-------------|------|
| [BARE-METAL.md](./BARE-METAL.md) | **量产主流程**：依赖、venv、Nginx、systemd、NPU 监控、FAQ |
| [RK3588.md](./RK3588.md) | 推理对照、量产摘要、监控入口 |
| [RKNN-EXPORT.md](./RKNN-EXPORT.md) | PC 上 ONNX → `.rknn`、板端 rknnlite |
| [nginx.bare-metal.conf](./nginx.bare-metal.conf) | 静态 `web/dist` + 反代 8080 + WebSocket |
| [edge-unified.service](./edge-unified.service) | 主服务 `serve_unified.py`（User=edge） |
| [edge-rknpu-debugfs.service](./edge-rknpu-debugfs.service) | 启动时 NPU 负载快照 |
| [edge-rknpu-debugfs-refresh.timer](./edge-rknpu-debugfs-refresh.timer) | 每 5s 刷新 `/run/edge-ai-box/rknpu-load` |
| [edge-rknpu-debugfs-pre.sh](./edge-rknpu-debugfs-pre.sh) | 上述单元执行的脚本（注意 LF，勿 CRLF） |

快速启用（在 `/opt/edge-ai-box` 已同步代码后）见 **BARE-METAL.md §5**。
