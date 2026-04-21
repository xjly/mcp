"""工具函数"""

import json
from typing import Any


def safe_result(result: Any) -> dict | list | str | int | float | bool | None:
    """安全地转换结果为 JSON 兼容格式"""
    if result is None:
        return {}
    if isinstance(result, dict):
        return {k: safe_result(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [safe_result(item) for item in result]
    if isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, bytes):
        return "<binary_data>"
    return str(result)