import pytest

from weather.config import QWeatherConfig
from weather.qweather_client import (
    QWeatherClient,
    _normalize_daily_item,
    _normalize_hourly_item,
    _normalize_minutely_item,
)


def test_normalize_hourly_item_fields():
    item = {
        "fxTime": "2026-04-08T10:00+08:00",
        "precip": "1.2",
        "windSpeed": "15",
        "windDir": "东风",
        "humidity": "85",
        "temp": "24",
    }
    out = _normalize_hourly_item(item)
    assert out["time"] == "2026-04-08T10:00+08:00"
    assert out["precip_mm"] == 1.2
    assert out["wind_speed_kph"] == 15.0
    assert out["wind_dir"] == "东风"


def test_normalize_daily_item_fields():
    item = {
        "fxDate": "2026-04-08",
        "precip": "0.5",
        "windSpeedDay": "18",
        "windDirDay": "东北风",
        "humidity": "70",
        "tempMax": "30",
    }
    out = _normalize_daily_item(item)
    assert out["time"] == "2026-04-08"
    assert out["wind_speed_kph"] == 18.0
    assert out["wind_dir"] == "东北风"
    assert out["temp_c"] == 30.0


def test_validate_granularity_rejects_invalid():
    client = QWeatherClient(QWeatherConfig(api_key="k", base_url="https://x", timeout_seconds=10))
    with pytest.raises(ValueError):
        client._validate_granularity("minute")


def test_normalize_minutely_item_fields():
    item = {"fxTime": "2026-04-23T13:50+08:00", "precip": "0.3", "type": "rain"}
    out = _normalize_minutely_item(item)
    assert out["time"] == "2026-04-23T13:50+08:00"
    assert out["precip_mm"] == 0.3
    assert out["type"] == "rain"


def test_get_minutely_precipitation_slice_minutes(monkeypatch):
    client = QWeatherClient(
        QWeatherConfig(api_key="k", base_url="https://x", timeout_seconds=10)
    )

    def _fake_request_json(path: str, params: dict):
        assert path == "/v7/minutely/5m"
        assert "location" in params
        return {
            "code": "200",
            "summary": "未来两小时有小雨",
            "minutely": [
                {"fxTime": f"2026-04-23T13:{i:02d}+08:00", "precip": "0.1", "type": "rain"}
                for i in range(0, 60, 5)
            ],
        }

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    result = client.get_minutely_precipitation(lon=120.31189, lat=31.49106, minutes=30)
    assert result["count"] == 6
    assert result["minutes"] == 30


def test_get_weather_history_passes_date_param(monkeypatch):
    client = QWeatherClient(
        QWeatherConfig(api_key="k", base_url="https://x", timeout_seconds=10)
    )

    captured: dict[str, object] = {}

    def _fake_request_json(path: str, params: dict):
        captured["path"] = path
        captured["params"] = params
        return {"code": "200", "weatherHourly": []}

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    result = client.get_weather_history(
        location_id="101190401",
        granularity="hourly",
        hours=24,
        date="20260423",
    )

    assert result["granularity"] == "hourly"
    assert captured["path"] == "/v7/historical/weather"
    assert captured["params"] == {
        "location": "101190401",
        "type": "hourly",
        "date": "20260423",
    }


def test_get_weather_history_daily_payload_object_is_handled(monkeypatch):
    client = QWeatherClient(
        QWeatherConfig(api_key="k", base_url="https://x", timeout_seconds=10)
    )

    def _fake_request_json(path: str, params: dict):
        assert path == "/v7/historical/weather"
        return {
            "code": "200",
            "weatherDaily": {
                "daily": [
                    {
                        "fxDate": "2026-04-22",
                        "precip": "0.2",
                        "windSpeedDay": "10",
                        "windDirDay": "东北风",
                        "humidity": "66",
                        "tempMax": "28",
                    }
                ]
            },
        }

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    result = client.get_weather_history(
        location_id="101280101",
        granularity="daily",
        days=1,
        date="20260422",
    )
    assert result["count"] == 1
    assert result["items"][0]["time"] == "2026-04-22"


def test_get_weather_alert_current_returns_raw_alerts_and_query_params(monkeypatch):
    client = QWeatherClient(
        QWeatherConfig(api_key="k", base_url="https://x", timeout_seconds=10)
    )
    captured: dict[str, object] = {}

    def _fake_request_json(path: str, params: dict):
        captured["path"] = path
        captured["params"] = params
        return {
            "code": "200",
            "metadata": {"tag": "x"},
            "alerts": [{"id": "a1", "headline": "大风蓝色预警"}],
        }

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    result = client.get_weather_alert_current(
        lon=116.40,
        lat=39.90,
        lang="zh",
        local_time=True,
    )
    assert captured["path"] == "/weatheralert/v1/current/39.9/116.4"
    assert captured["params"] == {"lang": "zh", "localTime": "true"}
    assert result == [{"id": "a1", "headline": "大风蓝色预警"}]
