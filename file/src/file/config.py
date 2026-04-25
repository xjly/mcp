"""File Template MCP Server configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class LLMConfig:
    """Runtime configuration for LLM client used in template filling."""

    api_key: str
    base_url: str
    default_model: str
    timeout_seconds: int


def get_llm_config() -> LLMConfig:
    """Load and validate configuration from environment variables."""
    api_key = (os.getenv("POLISH_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    
    if not api_key:
        raise ValueError("POLISH_API_KEY or OPENAI_API_KEY is required")

    base_url = (os.getenv("POLISH_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.siliconflow.cn/v1").strip()
    default_model = os.getenv("POLISH_MODEL", "deepseek-ai/DeepSeek-V3").strip()
    timeout_seconds = int(os.getenv("POLISH_TIMEOUT_SECONDS", "30"))

    return LLMConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        default_model=default_model,
        timeout_seconds=max(1, timeout_seconds),
    )
