"""设备 RTSP 拉流地址构建（兼容大华默认格式与自定义 URL/模板）"""
from urllib.parse import quote
from typing import Any, Dict, List, Optional

# 与前端 yolo-client/src/utils/rtspUrl.js 保持一致
DAHUA_RTSP_TEMPLATE = (
    "rtsp://{username}:{password}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"
)

RTSP_URL_PRESETS: List[Dict[str, str]] = [
    {
        "value": "dahua",
        "label": "大华默认",
        "mode": "dahua",
        "url": "",
    },
    {
        "value": "hikvision",
        "label": "海康威视",
        "mode": "custom",
        "url": "rtsp://{username}:{password}@{ip}:{port}/Streaming/Channels/{hik_channel}",
    },
    {
        "value": "uniview",
        "label": "宇视",
        "mode": "custom",
        "url": "rtsp://{username}:{password}@{ip}:{port}/video{channel}/{subtype}",
    },
    {
        "value": "generic",
        "label": "通用 RTSP",
        "mode": "custom",
        "url": "rtsp://{username}:{password}@{ip}:{port}/",
    },
]


def _get_attr(device: Any, name: str, default=None):
    if isinstance(device, dict):
        return device.get(name, default)
    return getattr(device, name, default)


def _apply_template(template: str, mapping: dict) -> str:
    result = template
    for key, value in mapping.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def detect_rtsp_preset(device: Any) -> str:
    """根据已保存的 rtsp_url_mode / rtsp_url 反推拉流方式（与前端下拉选项对应）"""
    mode = (_get_attr(device, "rtsp_url_mode") or "dahua").lower()
    if mode != "custom":
        return "dahua"

    custom_url = (_get_attr(device, "rtsp_url") or "").strip()
    if not custom_url:
        return "generic"

    for preset in RTSP_URL_PRESETS:
        if preset.get("url") and preset["url"] == custom_url:
            return preset["value"]
    return "generic"


def get_rtsp_preset_label(device: Any) -> str:
    preset_value = detect_rtsp_preset(device)
    for preset in RTSP_URL_PRESETS:
        if preset["value"] == preset_value:
            return preset["label"]
    return "通用 RTSP" if (_get_attr(device, "rtsp_url_mode") or "dahua") == "custom" else "大华默认"


def get_rtsp_template_for_device(device: Any) -> str:
    """返回设备当前拉流方式对应的 RTSP 模板/格式说明"""
    preset_value = detect_rtsp_preset(device)
    if preset_value == "dahua":
        return DAHUA_RTSP_TEMPLATE
    custom_url = (_get_attr(device, "rtsp_url") or "").strip()
    return custom_url or DAHUA_RTSP_TEMPLATE


def build_rtsp_url(device: Any, stream_type: Optional[str] = None) -> str:
    """
    构建设备 RTSP 地址。

    数据库存储（与前端拉流方式下拉对应）:
      - rtsp_url_mode=dahua: 大华默认，忽略 rtsp_url
      - rtsp_url_mode=custom: 使用 rtsp_url（海康/宇视/通用均走此分支）

    模板占位符:
      {username} {password} {ip} {port} {channel} {subtype} {stream}
      {hik_channel} 海康通道码（如 101=1通道主码流, 102=1通道子码流）
    """
    mode = (_get_attr(device, "rtsp_url_mode") or "dahua").lower()
    custom_url = (_get_attr(device, "rtsp_url") or "").strip()

    stream_type = stream_type or _get_attr(device, "stream_type", "main") or "main"
    subtype = 1 if stream_type == "sub" else 0
    device_type = _get_attr(device, "device_type", "camera") or "camera"

    channel = int(_get_attr(device, "channel", 1) or 1)
    channel_for_dahua = channel if device_type == "nvr" else 1

    username = _get_attr(device, "username", "") or ""
    password = _get_attr(device, "password", "") or ""
    ip_address = _get_attr(device, "ip_address", "") or ""
    port = _get_attr(device, "port", 554) or 554

    if mode == "custom" and custom_url:
        if "{" in custom_url:
            hik_channel = channel * 100 + (1 if stream_type == "main" else 2)
            mapping = {
                "username": quote(username, safe=""),
                "password": quote(password, safe=""),
                "ip": ip_address,
                "port": port,
                "channel": channel,
                "subtype": subtype,
                "stream": stream_type,
                "hik_channel": hik_channel,
            }
            return _apply_template(custom_url, mapping)
        return custom_url

    return (
        f"rtsp://{username}:{password}@{ip_address}:{port}"
        f"/cam/realmonitor?channel={channel_for_dahua}&subtype={subtype}"
    )
