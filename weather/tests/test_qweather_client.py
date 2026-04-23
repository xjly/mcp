import pytest

from weather.config import QWeatherConfig
from weather.qweather_client import (
    QWeatherClient,
    _normalize_daily_item,
    _normalize_hourly_item,
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
