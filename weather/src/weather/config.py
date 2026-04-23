"""QWeather configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class QWeatherConfig:
    """Runtime configuration for QWeather client."""

    api_key: str
    base_url: str
    timeout_seconds: int


def get_qweather_config() -> QWeatherConfig:
    """Load and validate configuration from environment variables."""
    api_key = os.getenv("QWEATHER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("QWEATHER_API_KEY is required")

    base_url = os.getenv("QWEATHER_BASE_URL", "https://devapi.qweather.com").strip()
    timeout_seconds = int(os.getenv("QWEATHER_TIMEOUT_SECONDS", "30"))

    return QWeatherConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout_seconds=max(1, timeout_seconds),
    )
