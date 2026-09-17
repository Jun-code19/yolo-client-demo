"""单帧取图：API 截图 / RTSP 单帧，支持主备静默切换"""
import hashlib
import logging
import os
import re
import secrets
import socket
import threading
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import requests

from src.rtsp_url import build_rtsp_url

logger = logging.getLogger(__name__)

RTSP_URL_PREFIXES = ("rtsp://", "rtsps://")


def open_rtsp_capture(rtsp_url: str) -> cv2.VideoCapture:
    """用 FFMPEG 后端打开 RTSP，避免 Windows 上默认走 CAP_IMAGES。"""
    url = (rtsp_url or "").strip()
    if url.lower().startswith(RTSP_URL_PREFIXES):
        # 海康等设备在 Windows 上 UDP 不稳定，优先 TCP；5s 超时避免长时间阻塞
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
        return cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    return cv2.VideoCapture(url)


def probe_rtsp_host(rtsp_url: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """探测 RTSP 主机端口是否可达，返回 (可达, 主机:端口)。"""
    url = (rtsp_url or "").strip()
    if not url.lower().startswith(RTSP_URL_PREFIXES):
        return True, ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 554
        if not host:
            return True, ""
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{host}:{port}"
    except OSError:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = parsed.hostname or "unknown"
            port = parsed.port or 554
            return False, f"{host}:{port}"
        except Exception:
            return False, "unknown"


DEFAULT_GROUP_SETTINGS = {
    "frame_source_primary": "snapshot",
    "frame_source_fallback": "rtsp",
    "device_interval_sec": 1.0,
    "group_round_interval_sec": 0.0,
}

SNAPSHOT_TIMEOUT_SEC = 5
RTSP_FRAME_TIMEOUT_SEC = 5

class FrameAcquisitionService:
    """按设备缓存成功取帧方式，失败时静默切换主/备方案"""

    def __init__(self):
        self._method_cache: Dict[str, str] = {}

    def get_frame(self, device, settings: Optional[dict] = None, stream_type: str = "main"):
        settings = settings or {}
        primary = (settings.get("frame_source_primary") or "snapshot").lower()
        fallback = (settings.get("frame_source_fallback") or "rtsp").lower()
        if primary not in ("snapshot", "rtsp"):
            primary = "snapshot"
        if fallback not in ("snapshot", "rtsp"):
            fallback = "rtsp"
        if primary == fallback:
            fallback = "rtsp" if primary == "snapshot" else "snapshot"

        device_id = device.device_id
        method_map = {"snapshot": self._get_frame_via_snapshot, "rtsp": self._get_frame_via_rtsp}

        cached = self._method_cache.get(device_id)
        if cached in method_map:
            frame = method_map[cached](device, stream_type)
            if frame is not None:
                return frame
            del self._method_cache[device_id]

        for method_name in (primary, fallback):
            getter = method_map[method_name]
            frame = getter(device, stream_type)
            if frame is not None:
                self._method_cache[device_id] = method_name
                return frame

        return None

    def _get_frame_via_snapshot(self, device, stream_type: str = "main"):
        try:
            if device.device_type and device.device_type.lower() == "nvr":
                channel = device.channel or 1
                snapshot_url = (
                    f"http://{device.ip_address}/cgi-bin/snapshot.cgi"
                    f"?channel={channel}&type=0"
                )
            else:
                snapshot_url = (
                    f"http://{device.ip_address}/cgi-bin/snapshot.cgi?channel=1&type=0"
                )

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            first_response = requests.get(
                snapshot_url, headers=headers, timeout=SNAPSHOT_TIMEOUT_SEC
            )

            if first_response.status_code == 200:
                return self._decode_image(first_response.content)

            if first_response.status_code == 401:
                auth_header = first_response.headers.get("www-authenticate", "")
                if "Digest" in auth_header:
                    auth_value = self._generate_digest_auth(
                        auth_header,
                        device.username,
                        device.password,
                        "GET",
                        snapshot_url,
                    )
                    auth_headers = {**headers, "Authorization": auth_value}
                    auth_response = requests.get(
                        snapshot_url, headers=auth_headers, timeout=SNAPSHOT_TIMEOUT_SEC
                    )
                    if auth_response.status_code == 200:
                        return self._decode_image(auth_response.content)
                elif "Basic" in auth_header or auth_header:
                    import base64

                    credentials = f"{device.username}:{device.password}"
                    encoded = base64.b64encode(credentials.encode()).decode()
                    basic_headers = {**headers, "Authorization": f"Basic {encoded}"}
                    basic_response = requests.get(
                        snapshot_url, headers=basic_headers, timeout=SNAPSHOT_TIMEOUT_SEC
                    )
                    if basic_response.status_code == 200:
                        return self._decode_image(basic_response.content)
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return None
        except Exception as exc:
            logger.debug("API 截图失败 %s: %s", device.device_id, exc)
            return None

    def _get_frame_via_rtsp(self, device, stream_type: str = "main"):
        effective_stream = stream_type or getattr(device, "stream_type", None) or "main"
        rtsp_url = build_rtsp_url(device, stream_type=effective_stream)
        result = {"frame": None}

        def _read_once():
            cap = None
            try:
                cap = open_rtsp_capture(rtsp_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    return
                ret, frame = cap.read()
                if ret and frame is not None:
                    result["frame"] = frame
            except Exception as exc:
                logger.debug("RTSP 单帧失败 %s: %s", device.device_id, exc)
            finally:
                if cap is not None:
                    cap.release()

        thread = threading.Thread(target=_read_once, daemon=True)
        thread.start()
        thread.join(timeout=RTSP_FRAME_TIMEOUT_SEC)
        if thread.is_alive():
            logger.debug("RTSP 单帧超时 %ss: %s", RTSP_FRAME_TIMEOUT_SEC, device.device_id)
            return None
        return result["frame"]
    @staticmethod
    def _decode_image(content: bytes):
        if not content or len(content) < 4:
            return None
        # 部分摄像机会在 JPEG 前附带额外字节，定位 SOI 标记 0xFFD8
        start = content.find(b"\xff\xd8")
        if start < 0:
            return None
        if start > 0:
            content = content[start:]
        image_array = np.frombuffer(content, np.uint8)
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame
    @staticmethod
    def _generate_digest_auth(
        auth_header: str, username: str, password: str, method: str, uri: str
    ) -> str:
        auth_info = {}
        pattern = r'(\w+)="([^"]*)"'
        for key, value in re.findall(pattern, auth_header):
            auth_info[key] = value

        realm = auth_info.get("realm", "")
        nonce = auth_info.get("nonce", "")
        qop = auth_info.get("qop", "")
        algorithm = auth_info.get("algorithm", "MD5")
        cnonce = secrets.token_hex(8)
        nc = "00000001"

        ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        if qop:
            response = hashlib.md5(
                f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
            ).hexdigest()
        else:
            response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

        auth_response = (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", algorithm={algorithm}, response="{response}"'
        )
        if qop:
            auth_response += f', qop={qop}, nc={nc}, cnonce="{cnonce}"'
        return auth_response


frame_acquisition = FrameAcquisitionService()
