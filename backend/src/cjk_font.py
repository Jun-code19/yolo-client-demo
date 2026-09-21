"""OpenCV 预览/叠加用中文字体（PIL ImageFont）。"""
from __future__ import annotations

import glob
import logging
import os
from functools import lru_cache
from typing import List, Optional, Tuple

from PIL import ImageFont

logger = logging.getLogger(__name__)

_WINDOWS_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
)

_LINUX_GLOBS = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)

_LINUX_GLOB_PATTERNS = (
    "/usr/share/fonts/**/wqy-*.ttc",
    "/usr/share/fonts/**/NotoSansCJK*.ttc",
    "/usr/share/fonts/**/NotoSansSC*.otf",
    "/usr/share/fonts/**/DroidSansFallback*.ttf",
)


def _dedupe(paths: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for p in paths:
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _glob_fonts() -> List[str]:
    found: List[str] = []
    for pattern in _LINUX_GLOB_PATTERNS:
        found.extend(glob.glob(pattern, recursive=True))
    return sorted(found)


@lru_cache(maxsize=1)
def find_cjk_font_path() -> Optional[str]:
    env = (os.environ.get("EDGE_CJK_FONT") or "").strip()
    candidates: List[str] = []
    if env:
        candidates.append(env)
    if os.name == "nt":
        candidates.extend(_WINDOWS_CANDIDATES)
    else:
        candidates.extend(_LINUX_GLOBS)
        candidates.extend(_glob_fonts())
    for path in _dedupe(candidates):
        if os.path.isfile(path):
            return path
    logger.warning(
        "未找到中文字体，预览中文可能显示为 ? 或跳过。"
        "请安装 fonts-wqy-zenhei / fonts-noto-cjk，或设置环境变量 EDGE_CJK_FONT=/path/to/font.ttc"
    )
    return None


def load_cjk_font(size: int) -> Optional[ImageFont.FreeTypeFont]:
    path = find_cjk_font_path()
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        logger.warning("加载字体失败 %s: %s", path, exc)
        find_cjk_font_path.cache_clear()
        return None


def load_cjk_font_pair(
    large_size: int = 30, small_size: int = 16
) -> Tuple[Optional[ImageFont.FreeTypeFont], Optional[ImageFont.FreeTypeFont], Optional[str]]:
    path = find_cjk_font_path()
    if not path:
        return None, None, None
    try:
        return ImageFont.truetype(path, large_size), ImageFont.truetype(path, small_size), path
    except OSError as exc:
        logger.warning("加载字体失败 %s: %s", path, exc)
        return None, None, None


def ascii_fallback_text(text: str) -> str:
    """无中文字体时用 OpenCV 绘制 ASCII 安全字符串。"""
    if not text:
        return ""
    return "".join(ch if ord(ch) < 128 else "?" for ch in str(text))
