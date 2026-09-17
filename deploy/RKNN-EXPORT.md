# YOLO → RKNN（RK3588 NPU）

edge-ai-box 在 **`EDGE_INFERENCE=rknn`** 下通过 `src/rknn_yolo.py` 调用 **RKNN Lite** 在 NPU 上推理。`.rknn` 需在 **x86 Linux PC**（或 WSL2）上用 Rockchip **rknn-toolkit2** 从 ONNX 转换；盒子端只安装 **rknn-toolkit-lite2**。

## 1. PC 端：导出 ONNX

```bash
pip install ultralytics
yolo export model=yolov8n.pt format=onnx imgsz=640 opset=12 simplify=True
```

得到 `yolov8n.onnx`（输入一般为 `1×3×640×640` float）。

## 2. PC 端：ONNX → RKNN

安装 [rknn-toolkit2](https://github.com/airockchip/rknn-toolkit2)（版本需与板端 **librknnrt** 一致，常见 1.6.x / 2.x）。

示例脚本（与 Ultralytics YOLOv8 检测头、单输出 `(1,84,8400)` 对齐）：

```python
from rknn.api import RKNN

ONNX = "yolov8n.onnx"
RKNN_OUT = "yolov8n.rknn"

rknn = RKNN(verbose=True)
rknn.config(
    mean_values=[[0, 0, 0]],
    std_values=[[255, 255, 255]],
    target_platform="rk3588",
)
rknn.load_onnx(model=ONNX)
rknn.build(do_quantization=True, dataset="./dataset.txt")  # dataset.txt 为校准图路径列表
rknn.export_rknn(RKNN_OUT)
rknn.release()
```

量化需准备若干张与场景相近的 JPG，写入 `dataset.txt`（每行一个绝对路径）。若先验证链路，可 `do_quantization=False`（体积大、略慢，精度高）。

**输入约定**：默认 `RKNN_INPUT_UINT8=1`，推理时送 **uint8 NHWC RGB**（与 rknn_model_zoo YOLOv8 一致）。若你转换时未做 `/255` 归一化，保持 mean/std 如上即可。

## 3. 盒子上：安装 Lite 与驱动

**`rknnlite` 不会随 `pip install -r requirements*.txt` 安装**，必须从 Rockchip SDK / [rknn-toolkit2](https://github.com/airockchip/rknn-toolkit2) 仓库取 **板端 wheel**（`rknn_toolkit_lite2`），在 **已激活的 venv** 里手动 `pip install`。

```bash
source /opt/edge-ai-box/backend/.venv/bin/activate
python -V    # 3.8 须装 cp38 wheel；3.10 装 cp310，勿混用

# 确认 NPU 设备
ls -l /dev/rknpu*

# 在 PC 下载或从厂商镜像/SDK 拷贝 wheel，例如：
#   rknn-toolkit2/rknn_toolkit_lite2/packages/rknn_toolkit_lite2-*-cp38-cp38-linux_aarch64.whl
pip install /path/to/rknn_toolkit_lite2-*-cp38-*linux_aarch64.whl

python -c "from rknnlite.api import RKNNLite; print('rknnlite ok')"
```

**量产盒常无法 `git clone` GitHub**（TLS 超时）。任选其一：

**A. Windows 开发机下载再传到盒子（推荐）**

浏览器或 PowerShell 下载（Python 3.8 / aarch64，版本与 PC 转模型 toolkit 一致，常见 **2.3.2**）：

`https://github.com/airockchip/rknn-toolkit2/raw/master/rknn-toolkit-lite2/packages/rknn_toolkit_lite2-2.3.2-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`

```powershell
# 在 PC 上，保存到当前目录
scp .\rknn_toolkit_lite2-2.3.2-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl root@盒子IP:/tmp/
```

盒子上：

```bash
source /opt/edge-ai-box/backend/.venv/bin/activate
export LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
pip install /tmp/rknn_toolkit_lite2-2.3.2-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
python -c "from rknnlite.api import RKNNLite; print('rknnlite ok')"
```

**B. 盒子 wget 单文件**（网络仍可能失败，可多试或换镜像前缀）

```bash
cd /tmp
wget -O rknn_cp38.whl "https://github.com/airockchip/rknn-toolkit2/raw/master/rknn-toolkit-lite2/packages/rknn_toolkit_lite2-2.3.2-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
pip install rknn_cp38.whl
```

**C. Rockchip [RKNPU2_SDK 网盘](https://github.com/airockchip/rknn-toolkit2)**（README 链接，提取码 `rknn`）解压后，在 `rknn-toolkit-lite2/packages/` 找 **cp38** whl 拷到盒子。

**NPU 设备**：新驱动多为 **`/dev/dri/renderD129`** + `RKNPU driver v0.9.x`，不一定有 `/dev/rknpu0`；见 [BARE-METAL.md](./BARE-METAL.md) 常见问题。

`librknnrt.so` 通常在 `/usr/lib`；若 `import` 失败，设置：

```bash
export LD_LIBRARY_PATH=/usr/lib:$LD_LIBRARY_PATH
```

## 4. 配置 edge-ai-box

`backend/.env` 或 systemd 环境：

```env
EDGE_INFERENCE=rknn
RKNN_CORE_MASK=0_1_2    # 可选: 0 | 1 | 2 | 0_1 | auto
RKNN_IMGSZ=640
RKNN_INPUT_UINT8=1
```

- 将 **`yolov8n.rknn`** 上传到 Web「模型管理」，或放入 `backend/models/`。
- **参数 JSON 必填 classes**，例如：`{"classes":{"0":"person","1":"bicycle"}}`（与训练类别一致）。
- 检测配置里模型名指向该 `.rknn`（若 DB 里仍是 `.onnx` 名，同目录有同名 `.rknn` 时会自动选用 RKNN）。

重启服务：

```bash
sudo systemctl restart edge-unified
# 或 python serve_unified.py
```

日志应出现：`RKNN/NPU 适配器已加载`。

## 5. 常见问题

| 现象 | 处理 |
|------|------|
| `init_runtime` 失败 | 驱动/权限、`/dev/rknpu0`、rknnrt 与转换 toolkit 版本不一致 |
| 有框但全错/无框 | 检查 `classes`、量化数据集、输入 uint8/float 与 `RKNN_INPUT_UINT8` |
| 仍 CPU 100% | 确认 `EDGE_INFERENCE=rknn` 且加载的是 `.rknn`；解码仍在 CPU 属正常 |
| 仅 ONNX | 设置 `EDGE_INFERENCE=onnx`，无需 RKNN |

更完整的 YOLOv8 转换可参考 [rknn_model_zoo](https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yolov8).
