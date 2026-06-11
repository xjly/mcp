"""Chart data parsing and MinIO URL helpers."""

import json
import os
import re
from typing import Any
from urllib.parse import urlparse, urlunparse


def _default_bucket() -> str:
    return os.getenv("DEFAULT_BUCKET") or os.getenv("MINIO_KB_BUCKET") or "kb-images"


def _default_chat_path() -> str:
    return os.getenv("DEFAULT_CHAT_IMAGES_PATH") or os.getenv("MINIO_CHAT_IMAGES_PATH") or "chat-images"


class ChartService:
    """Chart processing service."""

    def infer_chart_type(
        self,
        data: list[dict[str, Any]],
        preferred: str | None = None,
        text: str = "",
    ) -> str:
        """Infer a chart type when the caller does not provide one."""
        if preferred:
            return preferred

        water_keywords = ["水位", "流量", "压力", "降雨", "level", "flow", "trend"]
        is_water_data = any(keyword in text for keyword in water_keywords)

        if data:
            if is_water_data:
                return "area"
            if len(data) <= 7:
                return "pie"

        return "bar"

    def build_chart_spec(
        self,
        chart_type: str,
        title: str,
        data: list[dict[str, Any]],
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Build the frontend chart specification."""
        if not data:
            raise ValueError("数据不能为空")

        sample = data[0]
        fields = list(sample.keys())

        x_field = next((key for key in ("time", "date", "name", "category", "label", "x") if key in fields), None)
        y_field = next((key for key in ("level", "value", "amount", "count", "y") if key in fields), None)

        chart_spec: dict[str, Any] = {
            "type": chart_type,
            "title": title or "数据图表",
            "x_field": x_field or "name",
            "y_field": y_field or "value",
            "values": data,
        }
        if threshold is not None:
            chart_spec["threshold"] = threshold
        elif "threshold" in sample:
            chart_spec["threshold"] = sample["threshold"]

        return chart_spec

    def parse_data_json(self, data_json: Any) -> list[Any]:
        """Parse flexible JSON-like data into a list."""
        if isinstance(data_json, list):
            return data_json

        if isinstance(data_json, dict):
            if "values" in data_json and isinstance(data_json["values"], list):
                return data_json["values"]
            return [{"name": key, "value": value} for key, value in data_json.items()]

        if isinstance(data_json, str):
            clean_str = data_json.strip().strip("'").strip('"')
            if clean_str.startswith("{{") and clean_str.endswith("}}"):
                clean_str = clean_str[1:-1]

            parsers = (
                clean_str,
                clean_str.replace("'", '"'),
                re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', clean_str),
            )
            for candidate in parsers:
                try:
                    result = json.loads(candidate)
                except json.JSONDecodeError:
                    continue

                if isinstance(result, list):
                    return result
                if isinstance(result, dict):
                    if "values" in result and isinstance(result["values"], list):
                        return result["values"]
                    return [{"name": key, "value": value} for key, value in result.items()]

            numbers = re.findall(r"(\d+(?:\.\d+)?)", clean_str)
            if numbers:
                return [{"name": f"值{i + 1}", "value": float(number)} for i, number in enumerate(numbers)]

        raise ValueError(f"无法解析的数据格式: {data_json}")

    def normalize_data(self, data: list[Any]) -> list[dict[str, Any]]:
        """Normalize chart data into {name, value} items."""
        normalized: list[dict[str, Any]] = []

        for index, item in enumerate(data):
            if isinstance(item, dict):
                name = self._first_present(item, ("name", "label", "category", "x", "季度", "月份", "日期"))
                raw_value = self._first_present(item, ("value", "amount", "count", "y", "level", "数量", "数值"))

                if name is None:
                    name = f"项{index + 1}"
                if raw_value is None:
                    raw_value = next((value for value in item.values() if isinstance(value, (int, float))), 0)

                normalized.append({"name": str(name), "value": self._to_number(raw_value)})
            elif isinstance(item, (int, float)):
                normalized.append({"name": f"项{index + 1}", "value": item})
            else:
                normalized.append({"name": str(item), "value": 0})

        return normalized

    def fix_minio_url(self, url: str) -> str:
        """Normalize shorthand MinIO URLs to include the default bucket/path."""
        cleaned_url = url.strip().strip("'\"`").strip()
        endpoint = os.getenv("MINIO_ENDPOINT", "")

        if endpoint and cleaned_url.startswith(endpoint):
            cleaned_url = f"http://{cleaned_url}"

        parsed = urlparse(cleaned_url)
        path_parts = [part for part in parsed.path.lstrip("/").split("/") if part]
        default_bucket = _default_bucket()
        default_chat_path = _default_chat_path()

        if len(path_parts) == 1:
            new_path = f"/{default_bucket}/{default_chat_path}/{path_parts[0]}"
            return urlunparse(parsed._replace(path=new_path))

        if len(path_parts) == 2 and path_parts[0] == default_bucket:
            new_path = f"/{default_bucket}/{default_chat_path}/{path_parts[1]}"
            return urlunparse(parsed._replace(path=new_path))

        return cleaned_url

    def parse_minio_object(self, url: str) -> tuple[str, str]:
        """Extract bucket and object name from a MinIO URL or object path."""
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.lstrip("/").split("/") if part]

        if len(path_parts) >= 2:
            return path_parts[0], "/".join(path_parts[1:])

        if len(path_parts) == 1:
            return _default_bucket(), f"{_default_chat_path()}/{path_parts[0]}"

        raise ValueError("chart_url 中未找到有效的对象路径")

    @staticmethod
    def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in item:
                return item[key]
        return None

    @staticmethod
    def _to_number(value: Any) -> float | int:
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, list) and value:
            return ChartService._to_number(value[0])
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0


_chart_service: ChartService | None = None


def get_chart_service() -> ChartService:
    """Get the shared chart service instance."""
    global _chart_service
    if _chart_service is None:
        _chart_service = ChartService()
    return _chart_service
