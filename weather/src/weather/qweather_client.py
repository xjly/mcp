"""QWeather API client and data normalization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from weather.config import QWeatherConfig


def _to_float(value: str | int | float | None) -> float | None:
    """Convert value to float safely."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_error(message: str, **extra: Any) -> dict[str, Any]:
    """Build a unified error payload."""
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return payload


def _normalize_hourly_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    @description 将小时级原始气象条目转换为统一输出结构。
    @reason 和风不同接口/版本字段可能存在命名差异（如 fxTime/time、windSpeed），
    统一结构能让上游工具调用方使用稳定字段，避免为每个接口写分支解析逻辑。
    """
    return {
        "time": item.get("fxTime") or item.get("time"),
        "precip_mm": _to_float(item.get("precip")),
        "wind_speed_kph": _to_float(item.get("windSpeed")),
        "wind_dir": item.get("windDir"),
        "humidity": _to_float(item.get("humidity")),
        "temp_c": _to_float(item.get("temp")),
        "raw": item,
    }


def _normalize_daily_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    @description 将天级原始气象条目转换为统一输出结构。
    @reason 天级接口往往区分 Day/Night 字段（windSpeedDay/tempMax），
    这里按“白天优先，缺失再回退通用字段”的规则统一，降低上游消费复杂度。
    """
    return {
        "time": item.get("fxDate") or item.get("date"),
        "precip_mm": _to_float(item.get("precip")),
        "wind_speed_kph": _to_float(item.get("windSpeedDay") or item.get("windSpeed")),
        "wind_dir": item.get("windDirDay") or item.get("windDir"),
        "humidity": _to_float(item.get("humidity")),
        "temp_c": _to_float(item.get("tempMax") or item.get("temp")),
        "raw": item,
    }


def _normalize_minutely_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    @description 将分钟级降水条目转换为统一输出结构。
    @reason 分钟级接口在不同套餐与版本下字段可能有细微差异，统一字段可保证
    上游只关注 `time/precip_mm/type`，并支持按 minutes 进行稳定截取。
    """
    return {
        "time": item.get("fxTime") or item.get("time"),
        "precip_mm": _to_float(item.get("precip")),
        "type": item.get("type"),
        "raw": item,
    }


def _normalize_history_date(date: str | None) -> str:
    """
    @description 规范化历史天气查询日期为和风接口可接受的 `YYYYMMDD`。
    @reason 上游输入可能来自自然语言或不同客户端，常见格式既有 `YYYYMMDD` 也有
    `YYYY-MM-DD`。统一到单一格式可避免把格式差异变成接口 400，提升工具稳定性。
    """
    if date is None or not date.strip():
        # 历史查询默认取昨天，避免默认查询未来日期导致接口直接拒绝。
        return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")

    compact = date.strip().replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return compact
    raise ValueError("date must be in YYYYMMDD or YYYY-MM-DD format")


def _coerce_weather_items(value: Any, nested_key: str) -> list[dict[str, Any]]:
    """
    @description 将历史接口中形态不稳定的数据字段统一折叠成列表。
    @reason 实际返回中，`weatherDaily/weatherHourly` 既可能直接是列表，也可能是对象
    （如 `{"daily": [...]}` 或 `{"hourly": [...]}`）。若直接对对象切片会触发
    `slice(...)` 异常，工具层会以执行错误暴露给用户。此处统一“容错解包”为列表，
    可以把不同套餐/版本的响应差异吸收到客户端内部。
    """
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        nested = value.get(nested_key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


class QWeatherClient:
    """QWeather API client."""

    def __init__(self, config: QWeatherConfig):
        self._config = config
        self._http = httpx.Client(timeout=config.timeout_seconds)

    def _validate_granularity(self, granularity: str) -> None:
        if granularity not in {"hourly", "daily"}:
            raise ValueError("granularity must be 'hourly' or 'daily'")

    def _request_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = {"key": self._config.api_key, **params}
        url = f"{self._config.base_url}{path}"
        try:
            response = self._http.get(url, params=request_params)
        except httpx.RequestError as exc:
            return _safe_error("Network request failed", category="network", detail=str(exc))

        try:
            payload = response.json()
        except ValueError:
            return _safe_error(
                "Failed to parse JSON response",
                category="protocol",
                status_code=response.status_code,
            )

        if response.status_code != 200:
            return _safe_error(
                "Upstream HTTP request failed",
                status_code=response.status_code,
                api_code=payload.get("code"),
                upstream_message=payload.get("msg"),
            )

        if payload.get("code") != "200":
            return _safe_error(
                "QWeather business error",
                status_code=response.status_code,
                api_code=payload.get("code"),
                upstream_message=payload.get("msg"),
            )

        return payload

    def search_location_id_by_name(
        self, query: str, adm: str | None = None, limit: int = 5
    ) -> dict[str, Any]:
        """Resolve city/district name to candidate location IDs."""
        if not query.strip():
            return _safe_error("query is required")

        payload = self._request_json(
            "/geo/v2/city/lookup",
            {
                "location": query.strip(),
                "adm": adm.strip() if adm else None,
                "number": max(1, min(limit, 20)),
            },
        )
        if "error" in payload:
            return payload

        locations = payload.get("location", []) or []
        normalized = [
            {
                "location_id": item.get("id"),
                "name": item.get("name"),
                "adm1": item.get("adm1"),
                "adm2": item.get("adm2"),
                "country": item.get("country"),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
            }
            for item in locations
        ]
        return {"query": query, "count": len(normalized), "locations": normalized}

    def get_weather_forecast(
        self,
        location_id: str,
        granularity: str = "hourly",
        hours: int = 24,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get forecast weather data by location_id."""
        self._validate_granularity(granularity)
        if granularity == "hourly":
            endpoint = "/v7/weather/24h"
            window_value = max(1, min(hours, 168))
        else:
            endpoint = "/v7/weather/7d"
            window_value = max(1, min(days, 30))

        payload = self._request_json(endpoint, {"location": location_id})
        if "error" in payload:
            return payload

        if granularity == "hourly":
            raw_items = payload.get("hourly", []) or []
            items = [_normalize_hourly_item(item) for item in raw_items[:window_value]]
        else:
            raw_items = payload.get("daily", []) or []
            items = [_normalize_daily_item(item) for item in raw_items[:window_value]]

        return {
            "location_id": location_id,
            "granularity": granularity,
            "window": {"unit": "hours" if granularity == "hourly" else "days", "value": window_value},
            "count": len(items),
            "source": "qweather",
            "request_time": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }

    def get_weather_history(
        self,
        location_id: str,
        granularity: str = "hourly",
        hours: int = 24,
        days: int = 7,
        date: str | None = None,
    ) -> dict[str, Any]:
        """Get historical weather data by location_id."""
        self._validate_granularity(granularity)
        if granularity == "hourly":
            window_value = max(1, min(hours, 168))
        else:
            window_value = max(1, min(days, 30))

        normalized_date = _normalize_history_date(date)

        payload = self._request_json(
            "/v7/historical/weather",
            {
                "location": location_id,
                "type": granularity,
                "date": normalized_date,
            },
        )
        if "error" in payload:
            return payload

        # QWeather historical payload naming may vary by package/version.
        # Try multiple known keys and normalize uniformly.
        if granularity == "hourly":
            raw_items = _coerce_weather_items(
                payload.get("weatherHourly")
                or payload.get("hourly")
                or payload.get("data")
                or [],
                nested_key="hourly",
            )
            items = [_normalize_hourly_item(item) for item in raw_items[:window_value]]
        else:
            raw_items = _coerce_weather_items(
                payload.get("weatherDaily")
                or payload.get("daily")
                or payload.get("data")
                or [],
                nested_key="daily",
            )
            items = [_normalize_daily_item(item) for item in raw_items[:window_value]]

        return {
            "location_id": location_id,
            "granularity": granularity,
            "date": normalized_date,
            "window": {"unit": "hours" if granularity == "hourly" else "days", "value": window_value},
            "count": len(items),
            "source": "qweather",
            "request_time": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }

    def get_minutely_precipitation(
        self,
        lon: float,
        lat: float,
        minutes: int | None = None,
    ) -> dict[str, Any]:
        """Get minutely precipitation nowcast data by longitude/latitude."""
        payload = self._request_json("/v7/minutely/5m", {"location": f"{lon},{lat}"})
        if "error" in payload:
            return payload

        raw_items = payload.get("minutely", []) or payload.get("data", []) or []
        items = [_normalize_minutely_item(item) for item in raw_items]

        if minutes is not None:
            safe_minutes = max(5, min(minutes, 120))
            keep_count = max(1, safe_minutes // 5)
            items = items[:keep_count]
        else:
            safe_minutes = None

        return {
            "location": {"lon": lon, "lat": lat},
            "minutes": safe_minutes,
            "count": len(items),
            "summary": payload.get("summary"),
            "source": "qweather",
            "request_time": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
