import logging
import os
import threading
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import check_admin_permission, get_current_user
from api.logger import log_action
from src.database import PlatformSetting, User, get_db

SETTING_KEY = "dashboard_integrations"

DEFAULT_INTEGRATIONS: Dict[str, Any] = {
    "wait_time_enabled": True,
    "wait_time_url": os.getenv("WAIT_TIME_API_URL", ""),
    "wait_time_token": os.getenv("WAIT_TIME_API_TOKEN", ""),
    "wait_time_token_style": "bearer",
    "wait_time_timeout_sec": int(os.getenv("WAIT_TIME_TIMEOUT_SEC", "60")),
    "wait_time_cache_sec": int(os.getenv("WAIT_TIME_CACHE_SEC", "90")),
    "weather_enabled": True,
    "weather_api_url": os.getenv(
        "WEATHER_API_URL",
        "https://api.seniverse.com/v3/weather/now.json",
    ),
    "weather_api_key": os.getenv("WEATHER_API_KEY", ""),
    "weather_default_lat": float(os.getenv("WEATHER_DEFAULT_LAT", "39.9042")),
    "weather_default_lon": float(os.getenv("WEATHER_DEFAULT_LON", "116.4074")),
}

SECRET_FIELDS = ("wait_time_token", "weather_api_key")

logger = logging.getLogger(__name__)

_wait_time_cache_lock = threading.Lock()
_wait_time_cache: Dict[str, Any] = {
    "key": "",
    "payload": None,
    "error": None,
    "expires_at": 0.0,
}

router = APIRouter(tags=["大屏外部数据"])


class DashboardIntegrationsModel(BaseModel):
    wait_time_enabled: bool = True
    wait_time_url: str = ""
    wait_time_token: Optional[str] = None
    wait_time_token_style: str = Field(default="bearer", description="bearer/auto/query_key/...")
    wait_time_timeout_sec: int = Field(default=60, ge=5, le=300)
    wait_time_cache_sec: int = Field(default=90, ge=30, le=600)
    weather_enabled: bool = True
    weather_api_url: str = "https://api.seniverse.com/v3/weather/now.json"
    weather_api_key: Optional[str] = None
    weather_default_lat: float = Field(default=39.9042, ge=-90, le=90)
    weather_default_lon: float = Field(default=116.4074, ge=-180, le=180)


class WaitTimeTestModel(BaseModel):
    wait_time_url: str = ""
    wait_time_token: Optional[str] = None
    wait_time_token_style: str = "bearer"
    wait_time_timeout_sec: Optional[int] = Field(default=None, ge=5, le=300)
    use_saved_token: bool = False


def _merge_defaults(stored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = deepcopy(DEFAULT_INTEGRATIONS)
    if stored:
        merged.update(stored)
    return merged


def _load_integrations(db: Session) -> Dict[str, Any]:
    row = db.query(PlatformSetting).filter(PlatformSetting.setting_key == SETTING_KEY).first()
    if row and row.setting_value:
        return _merge_defaults(row.setting_value)
    return deepcopy(DEFAULT_INTEGRATIONS)


def _save_integrations(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = db.query(PlatformSetting).filter(PlatformSetting.setting_key == SETTING_KEY).first()
    if row:
        row.setting_value = payload
    else:
        row = PlatformSetting(setting_key=SETTING_KEY, setting_value=payload)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row.setting_value


def _mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    masked = deepcopy(config)
    for field in SECRET_FIELDS:
        value = masked.get(field) or ""
        if not value:
            masked[field] = ""
            masked[f"{field}_configured"] = False
            continue
        masked[f"{field}_configured"] = True
        if len(value) <= 4:
            masked[field] = "****"
        else:
            masked[field] = "*" * (len(value) - 4) + value[-4:]
    return masked


def _apply_secret_merge(incoming: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(existing)
    merged.update({k: v for k, v in incoming.items() if k not in SECRET_FIELDS})
    for field in SECRET_FIELDS:
        new_val = incoming.get(field)
        if new_val is not None and str(new_val).strip():
            cleaned = str(new_val).strip()
            if cleaned.startswith("*"):
                continue
            merged[field] = cleaned
    return merged


def _resolve_wait_timeout(config: Optional[Dict[str, Any]] = None, override: Optional[int] = None) -> int:
    if override is not None:
        return max(5, min(int(override), 300))
    if config:
        try:
            return max(5, min(int(config.get("wait_time_timeout_sec") or 60), 300))
        except (TypeError, ValueError):
            pass
    return 60


def _resolve_wait_cache_sec(config: Optional[Dict[str, Any]] = None) -> int:
    if config:
        try:
            return max(30, min(int(config.get("wait_time_cache_sec") or 90), 600))
        except (TypeError, ValueError):
            pass
    return 90


def _cache_key(url: str, token: str, token_style: str) -> str:
    return f"{url}|{token_style}|{token[-8:] if len(token) >= 8 else token}"


def normalize_wait_time_list(raw: Any) -> Any:
    """将 WaitTime 接口嵌套结构(activeData) 展平为前端图表字段。"""
    if not isinstance(raw, list):
        return raw
    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        src = item.get("activeData") or item.get("systemData") or item
        if not isinstance(src, dict):
            src = item
        normalized.append({
            "projectId": item.get("projectId") or src.get("projectId"),
            "projectName": item.get("projectName") or src.get("projectName") or "未知项目",
            "waitingMinutes": src.get("waitingMinutes", 0),
            "peopleCount": src.get("peopleCount", 0),
            "projectInterval": src.get("projectInterval", 0),
            "currentMode": item.get("currentMode"),
        })
    return normalized


def _should_stop_after_bearer(err_text: str) -> bool:
    lowered = err_text.lower()
    return (
        "HTTP 500" in err_text
        or "HTTP 502" in err_text
        or "HTTP 503" in err_text
        or "timed out" in lowered
        or "timeout" in lowered
    )


def _append_query_token(url: str, param: str, token: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[param] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _parse_response_payload(response: requests.Response) -> Tuple[Optional[Any], Optional[str]]:
    text = (response.text or "").strip()
    if not text:
        return None, "响应体为空"

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "json" in content_type or text.startswith(("{", "[")):
        try:
            data = response.json()
        except ValueError as exc:
            return None, f"响应不是有效 JSON: {exc}; 内容: {text[:200]}"
        if data is None:
            return None, "接口返回 null"
        return data, None

    return None, f"非 JSON 响应 (Content-Type: {content_type or 'unknown'}): {text[:200]}"


def _request_wait_time_once(url: str, token: str, style: str, timeout: int = 15) -> Tuple[Optional[Any], Optional[str]]:
    # 与 curl 一致：仅 Bearer，不附加 Accept/User-Agent，避免触发对方服务异常分支
    headers: Dict[str, str] = {}
    request_url = url

    if style == "bearer" and token:
        headers["Authorization"] = f"Bearer {token}"
    elif style == "token_raw" and token:
        headers["Authorization"] = token
    elif style == "header_api_key" and token:
        headers["X-Api-Key"] = token
    elif style == "query_key" and token:
        request_url = _append_query_token(url, "key", token)
    elif style == "query_apiKey" and token:
        request_url = _append_query_token(url, "apiKey", token)
    elif style == "query_token" and token:
        request_url = _append_query_token(url, "token", token)

    try:
        response = requests.get(
            request_url,
            headers=headers,
            timeout=(10, timeout),
        )
        try:
            if response.status_code >= 400:
                snippet = (response.text or "").strip()[:200]
                return None, f"HTTP {response.status_code}" + (f": {snippet}" if snippet else "")
            payload, parse_err = _parse_response_payload(response)
            if parse_err:
                return None, parse_err
            return normalize_wait_time_list(payload), None
        finally:
            response.close()
    except requests.RequestException as exc:
        return None, str(exc)


def request_wait_time_external(
    url: str,
    token: str = "",
    token_style: str = "bearer",
    timeout: int = 60,
    *,
    force_refresh: bool = False,
    cache_sec: int = 90,
) -> Tuple[Optional[Any], Optional[str]]:
    url = (url or "").strip()
    if not url:
        return None, "未配置接口地址"

    token = (token or "").strip()
    if token.startswith("*"):
        return None, "Token 无效（疑似未保存或被脱敏值覆盖，请重新填写并保存）"

    cache_key = _cache_key(url, token, token_style)
    now = time.time()

    with _wait_time_cache_lock:
        if (
            not force_refresh
            and _wait_time_cache.get("key") == cache_key
            and _wait_time_cache.get("payload") is not None
            and now < float(_wait_time_cache.get("expires_at") or 0)
        ):
            return _wait_time_cache["payload"], None

    styles: List[str]
    if token_style == "auto":
        styles = ["bearer"] if token else ["none"]
    elif token_style in ("bearer", "token_raw", "query_key", "query_apiKey", "query_token", "header_api_key", "none"):
        styles = [token_style]
    else:
        styles = ["bearer"] if token else ["none"]

    payload: Optional[Any] = None
    err: Optional[str] = None

    with _wait_time_cache_lock:
        # 单飞：避免并发打爆外部 WaitTime 服务
        for style in styles:
            payload, err = _request_wait_time_once(url, token, style, timeout=timeout)
            if payload is not None:
                break
            err_text = err or "未知错误"
            if style == "bearer" and _should_stop_after_bearer(err_text):
                if "timed out" in err_text.lower() or "timeout" in err_text.lower():
                    err = (
                        f"Bearer 请求已发出，但外部接口在 {timeout}s 内未响应。"
                        f" 可在配置中增大「请求超时」。详情: {err_text}"
                    )
                else:
                    err = f"Bearer 请求异常：{err_text}"
                payload = None
                break
            err = err_text

        if payload is not None:
            _wait_time_cache.update({
                "key": cache_key,
                "payload": payload,
                "error": None,
                "expires_at": now + max(30, cache_sec),
            })
            return payload, None

        # 失败时若有旧缓存，返回旧数据避免反复重试
        if (
            not force_refresh
            and _wait_time_cache.get("key") == cache_key
            and _wait_time_cache.get("payload") is not None
        ):
            logger.warning("排队时长拉取失败，使用缓存: %s", err)
            return _wait_time_cache["payload"], None

        _wait_time_cache.update({
            "key": cache_key,
            "payload": None,
            "error": err,
            "expires_at": now + 30,
        })
        return None, err or "请求失败"


def fetch_wait_time_data(db: Session, *, force_refresh: bool = False) -> Tuple[Optional[Any], Optional[str]]:
    """按大屏配置请求外部排队时长接口（带缓存，避免频繁打外部服务）。"""
    config = _load_integrations(db)
    if not config.get("wait_time_enabled", True):
        return None, None

    url = (config.get("wait_time_url") or "").strip()
    if not url:
        return None, None

    token = (config.get("wait_time_token") or "").strip()
    token_style = str(config.get("wait_time_token_style") or "bearer").strip() or "bearer"
    timeout = _resolve_wait_timeout(config)
    cache_sec = _resolve_wait_cache_sec(config)
    payload, err = request_wait_time_external(
        url,
        token,
        token_style,
        timeout=timeout,
        force_refresh=force_refresh,
        cache_sec=cache_sec,
    )
    if err:
        logger.warning("排队时长接口请求失败: %s", err)
    return payload, err


@router.get("/settings/dashboard-integrations")
def get_dashboard_integrations_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _load_integrations(db)
    return {"success": True, "data": _mask_config(config)}


@router.put("/settings/dashboard-integrations")
def save_dashboard_integrations_config(
    body: DashboardIntegrationsModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_permission),
):
    existing = _load_integrations(db)
    incoming = body.model_dump()
    saved = _apply_secret_merge(incoming, existing)
    _save_integrations(db, saved)
    log_action(
        db,
        current_user.user_id,
        "update_system_config",
        SETTING_KEY,
        "更新大屏外部数据接口配置",
    )
    return {"success": True, "data": _mask_config(saved)}


@router.get("/dashboard/wait-time")
def proxy_wait_time(db: Session = Depends(get_db)):
    config = _load_integrations(db)
    if not config.get("wait_time_enabled", True):
        return {"success": True, "data": None, "message": "排队时长接口未启用"}

    url = (config.get("wait_time_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="未配置排队时长接口地址")

    payload, err = fetch_wait_time_data(db)
    if payload is None:
        raise HTTPException(status_code=502, detail=err or "排队时长接口请求失败")
    return {"success": True, "data": payload}


@router.post("/settings/dashboard-integrations/test-wait-time")
def test_wait_time_connection(
    body: WaitTimeTestModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = (body.wait_time_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请填写接口地址")

    token = (body.wait_time_token or "").strip()
    if body.use_saved_token and not token:
        saved = _load_integrations(db)
        token = (saved.get("wait_time_token") or "").strip()
    elif not token and not body.use_saved_token:
        saved = _load_integrations(db)
        if (saved.get("wait_time_url") or "").strip() == url:
            token = (saved.get("wait_time_token") or "").strip()

    if not token and body.wait_time_token_style not in ("none", "auto", "bearer"):
        raise HTTPException(status_code=400, detail="请填写 Token")

    saved = _load_integrations(db)
    timeout = _resolve_wait_timeout(saved, body.wait_time_timeout_sec)

    payload, err = request_wait_time_external(
        url,
        token,
        str(body.wait_time_token_style or "bearer"),
        timeout=timeout,
        force_refresh=True,
        cache_sec=_resolve_wait_cache_sec(saved),
    )
    if payload is None:
        raise HTTPException(
            status_code=502,
            detail=err or "排队时长接口请求失败，请检查 data-server 是否能访问该地址",
        )
    return {"success": True, "data": payload}


@router.get("/dashboard/weather")
def proxy_weather(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
):
    config = _load_integrations(db)
    if not config.get("weather_enabled", True):
        return {"success": True, "data": None, "message": "天气接口未启用"}

    api_key = (config.get("weather_api_key") or "").strip()
    api_url = (config.get("weather_api_url") or DEFAULT_INTEGRATIONS["weather_api_url"]).strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="未配置天气 API Key")

    use_lat = lat if lat is not None else float(config.get("weather_default_lat", 39.9042))
    use_lon = lon if lon is not None else float(config.get("weather_default_lon", 116.4074))
    location = f"{use_lat}:{use_lon}"

    try:
        response = requests.get(
            api_url,
            params={
                "key": api_key,
                "location": location,
                "language": "zh-Hans",
                "unit": "c",
            },
            timeout=10,
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"天气接口请求失败: {exc}") from exc
