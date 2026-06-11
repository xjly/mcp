"""Basic tests for Chart MCP Server tools."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def test_generate_chart_basic() -> None:
    from chart.server import generate_chart

    result = generate_chart(
        data_json=[{"name": "Q1", "value": 120}, {"name": "Q2", "value": 135}],
        chart_type="bar",
        title="季度销售数据",
    )

    assert result["ok"] is True
    assert result["chart_type"] == "bar"
    assert result["data_points"] == 2
    assert result["chart_spec"]["x_field"] == "name"
    assert result["chart_spec"]["y_field"] == "value"


def test_generate_chart_string_data() -> None:
    from chart.server import generate_chart

    result = generate_chart(
        data_json='[{"name": "测试1", "value": 10}, {"name": "测试2", "value": 20}]',
        chart_type="line",
        title="字符串解析测试",
    )

    assert result["ok"] is True
    assert result["chart_type"] == "line"
    assert result["data_points"] == 2


def test_generate_chart_rejects_empty_data() -> None:
    from chart.server import generate_chart

    result = generate_chart(data_json=[], chart_type="bar")

    assert result["ok"] is False
    assert "至少需要包含一个有效数据点" in result["error"]


def test_explain_chart_requires_url() -> None:
    from chart.server import explain_chart

    result = asyncio.run(explain_chart(chart_url=None))

    assert result["ok"] is False
    assert "chart_url" in result["error"]


def test_fix_minio_url_uses_default_path() -> None:
    from chart.chart_service import ChartService

    svc = ChartService()
    fixed_url = svc.fix_minio_url("http://minio.local/example.png")

    assert fixed_url.endswith("/kb-images/chat-images/example.png")


if __name__ == "__main__":
    test_generate_chart_basic()
    test_generate_chart_string_data()
    test_generate_chart_rejects_empty_data()
    test_explain_chart_requires_url()
    test_fix_minio_url_uses_default_path()
    print("tests ok")
