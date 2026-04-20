"""PostgreSQL Reporter MCP Server - 水务数据查询与统计服务

提供闸站和水质监测数据的只读查询能力
"""

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from reporter.config import get_db_connection

# =============================================================================
# === MCP 服务器定义 ===
# =============================================================================

mcp = FastMCP(
    "reporter",
    instructions="""
## 水务数据查询与统计服务

### 服务能力
本服务提供闸站和水质监测数据的只读查询能力：

**闸站数据查询：**
- **get_gate_stations**: 获取所有闸站列表及位置信息
- **get_gate_station_devices**: 获取指定闸站的所有设备
- **get_gate_station_data**: 按设备类型查询闸站实时数据（内河水位/外河水位/雨量/泵/闸门/快速闸门）
- **get_gate_station_overview**: 获取所有闸站最新数据概览

**水质监测查询：**
- **get_water_quality_stations**: 获取所有水质监测站列表
- **get_water_quality_data**: 查询水质监测数据（最新/历史）
- **get_water_quality_overview**: 获取所有水质监测站最新数据概览

### 数据说明
- 闸站数据来自 gate_station_device_data，设备类型包括：
  - internal_fluviograph（内河水位）、external_fluviograph（外河水位）、udometer（雨量）
  - pump（泵）、gate（闸门）、quick_gate（快速闸门）
- 水质数据来自 water_quality_monitoring_station_data，包含 COD、氨氮、溶解氧、水质等级

### 安全限制
- 仅支持只读查询
- 禁止任何写操作
- 查询超时默认 30 秒
""",
)


# =============================================================================
# === 辅助函数 ===
# =============================================================================


def _safe_result(result: Any) -> Any:
    """安全地转换查询结果为 JSON 兼容格式"""
    if result is None:
        return None
    if isinstance(result, dict):
        return {k: _safe_result(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [_safe_result(item) for item in result]
    if isinstance(result, (str, int, float, bool)):
        return result
    if hasattr(result, "__str__"):
        return str(result)
    return result


# =============================================================================
# === 闸站数据查询 ===
# =============================================================================


@mcp.tool()
async def get_gate_stations() -> str:
    """
    获取所有闸站列表及位置信息。

    Returns:
        JSON 字符串，包含所有闸站信息
    """
    query = """
    SELECT id, gate_station_name, ST_X(geom::geometry) as lng, ST_Y(geom::geometry) as lat
    FROM gate_station_info
    ORDER BY id
    """

    async with get_db_connection() as conn:
        rows = await conn.fetch(query)

    stations = [
        {"id": r["id"], "name": r["gate_station_name"], "lng": r["lng"], "lat": r["lat"]}
        for r in rows
    ]

    return json.dumps({"count": len(stations), "stations": stations}, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_gate_station_devices(station_name: str | None = None) -> str:
    """
    获取闸站设备列表。

    Args:
        station_name: 闸站名称（可选，不填则返回所有设备）

    Returns:
        JSON 字符串，包含设备列表
    """
    if station_name:
        query = """
        SELECT d.device_id, d.device_name, d.station_id, s.gate_station_name,
               t.type_id, t.type_name
        FROM gate_station_devices d
        JOIN gate_station_info s ON d.station_id = s.id
        JOIN gate_station_device_types t ON d.type_id = t.type_id
        WHERE s.gate_station_name = $1
        ORDER BY t.type_id, d.device_id
        """
        params = (station_name,)
    else:
        query = """
        SELECT d.device_id, d.device_name, d.station_id, s.gate_station_name,
               t.type_id, t.type_name
        FROM gate_station_devices d
        JOIN gate_station_info s ON d.station_id = s.id
        JOIN gate_station_device_types t ON d.type_id = t.type_id
        ORDER BY s.gate_station_name, t.type_id, d.device_id
        """
        params = None

    async with get_db_connection() as conn:
        rows = await conn.fetch(query, *([params]) if params else [])

    devices = [
        {
            "device_id": r["device_id"],
            "device_name": r["device_name"],
            "station_id": r["station_id"],
            "station_name": r["gate_station_name"],
            "type_id": r["type_id"],
            "type_name": r["type_name"],
        }
        for r in rows
    ]

    return json.dumps({"count": len(devices), "devices": devices}, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_gate_station_data(
    station_name: str | None = None,
    device_type: str | None = None,
    limit: int = 100,
) -> str:
    """
    按设备类型查询闸站实时数据。

    Args:
        station_name: 闸站名称（可选）
        device_type: 设备类型，可选值：
            - internal_fluviograph（内河水位）
            - external_fluviograph（外河水位）
            - udometer（雨量）
            - pump（泵）
            - gate（闸门）
            - quick_gate（快速闸门）
        limit: 返回条数上限，默认100

    Returns:
        JSON 字符串，包含最新设备数据
    """
    type_name_map = {
        "internal_fluviograph": "内河水位",
        "external_fluviograph": "外河水位",
        "udometer": "雨量",
        "pump": "泵",
        "gate": "闸门",
        "quick_gate": "快速闸门",
    }

    device_type_cn = type_name_map.get(device_type, device_type) if device_type else None

    # Build query with latest data per device
    conditions = []
    params = []
    param_idx = 1

    if station_name:
        conditions.append(f"s.gate_station_name = ${param_idx}")
        params.append(station_name)
        param_idx += 1

    if device_type:
        conditions.append(f"t.type_name = ${param_idx}")
        params.append(device_type)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
    WITH LatestData AS (
        SELECT DISTINCT ON (dd.device_id)
            dd.device_id,
            dd.device_value,
            dd.device_status,
            dd.create_time
        FROM gate_station_device_data dd
        ORDER BY dd.device_id, dd.create_time DESC
    )
    SELECT
        d.device_id,
        d.device_name,
        s.gate_station_name as station_name,
        t.type_name,
        t.type_id,
        ld.device_value,
        ld.device_status,
        ld.create_time as data_time
    FROM LatestData ld
    JOIN gate_station_devices d ON ld.device_id = d.device_id
    JOIN gate_station_info s ON d.station_id = s.id
    JOIN gate_station_device_types t ON d.type_id = t.type_id
    WHERE {where_clause}
    ORDER BY s.gate_station_name, t.type_id, d.device_id
    LIMIT ${param_idx}
    """
    params.append(limit)

    async with get_db_connection() as conn:
        rows = await conn.fetch(query, *params)

    data = [
        {
            "device_id": r["device_id"],
            "device_name": r["device_name"],
            "station_name": r["station_name"],
            "type_name": r["type_name"],
            "type_name_cn": type_name_map.get(r["type_name"], r["type_name"]),
            "value": r["device_value"],
            "status": r["device_status"],
            "data_time": r["data_time"].isoformat() if r["data_time"] else None,
        }
        for r in rows
    ]

    return json.dumps(
        {
            "count": len(data),
            "filters": {"station_name": station_name, "device_type": device_type},
            "data": data,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_gate_station_overview() -> str:
    """
    获取所有闸站最新数据概览，按设备类型汇总。

    Returns:
        JSON 字符串，包含各设备类型的最新数据统计
    """
    query = """
    WITH LatestData AS (
        SELECT DISTINCT ON (dd.device_id)
            dd.device_id,
            dd.device_value,
            dd.device_status,
            dd.create_time
        FROM gate_station_device_data dd
        ORDER BY dd.device_id, dd.create_time DESC
    )
    SELECT
        t.type_name,
        t.type_id,
        COUNT(*) as device_count,
        SUM(CASE WHEN ld.device_status = true THEN 1 ELSE 0 END) as active_count,
        ROUND(AVG(ld.device_value)::numeric, 2) as avg_value,
        MIN(ld.device_value) as min_value,
        MAX(ld.device_value) as max_value,
        MAX(ld.create_time) as latest_time
    FROM LatestData ld
    JOIN gate_station_devices d ON ld.device_id = d.device_id
    JOIN gate_station_info s ON d.station_id = s.id
    JOIN gate_station_device_types t ON d.type_id = t.type_id
    GROUP BY t.type_id, t.type_name
    ORDER BY t.type_id
    """

    type_name_map = {
        "internal_fluviograph": "内河水位",
        "external_fluviograph": "外河水位",
        "udometer": "雨量",
        "pump": "泵",
        "gate": "闸门",
        "quick_gate": "快速闸门",
    }

    async with get_db_connection() as conn:
        rows = await conn.fetch(query)

    overview = []
    for r in rows:
        overview.append(
            {
                "type_id": r["type_id"],
                "type_name": r["type_name"],
                "type_name_cn": type_name_map.get(r["type_name"], r["type_name"]),
                "device_count": r["device_count"],
                "active_count": r["active_count"],
                "avg_value": r["avg_value"],
                "min_value": r["min_value"],
                "max_value": r["max_value"],
                "latest_time": r["latest_time"].isoformat() if r["latest_time"] else None,
            }
        )

    return json.dumps({"overview": overview}, ensure_ascii=False, indent=2)


# =============================================================================
# === 水质监测查询 ===
# =============================================================================


@mcp.tool()
async def get_water_quality_stations() -> str:
    """
    获取所有水质监测站列表及位置信息。

    Returns:
        JSON 字符串，包含所有水质监测站信息
    """
    query = """
    SELECT id, station_location_code, station_name,
           ST_X(geom::geometry) as lng, ST_Y(geom::geometry) as lat
    FROM water_quality_monitoring_station_info
    ORDER BY id
    """

    async with get_db_connection() as conn:
        rows = await conn.fetch(query)

    stations = [
        {
            "id": r["id"],
            "code": r["station_location_code"],
            "name": r["station_name"],
            "lng": r["lng"],
            "lat": r["lat"],
        }
        for r in rows
    ]

    return json.dumps({"count": len(stations), "stations": stations}, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_water_quality_data(
    station_name: str | None = None,
    hours: int = 24,
    limit: int = 100,
) -> str:
    """
    查询水质监测数据。

    Args:
        station_name: 监测站名称（可选，不填则返回所有站）
        hours: 时间范围（小时），默认24，即查询最近24小时数据
        limit: 返回条数上限，默认100

    Returns:
        JSON 字符串，包含水质数据
    """
    conditions = ["wq.create_time >= NOW() - INTERVAL '1 hour' * $1"]
    params = [hours]
    param_idx = 2

    if station_name:
        conditions.append(f"s.station_name = ${param_idx}")
        params.append(station_name)
        param_idx += 1

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT
        wq.id,
        wq.station_id,
        s.station_name,
        s.station_location_code,
        wq.cod,
        wq.ammonia_nitrogen,
        wq.dissolved_oxygen,
        wq.water_quality_grade,
        wq.create_time
    FROM water_quality_monitoring_station_data wq
    JOIN water_quality_monitoring_station_info s ON wq.station_id = s.id
    WHERE {where_clause}
    ORDER BY wq.create_time DESC
    LIMIT ${param_idx}
    """
    params.append(limit)

    async with get_db_connection() as conn:
        rows = await conn.fetch(query, *params)

    data = [
        {
            "id": r["id"],
            "station_id": r["station_id"],
            "station_name": r["station_name"],
            "station_code": r["station_location_code"],
            "cod": r["cod"],
            "ammonia_nitrogen": r["ammonia_nitrogen"],
            "dissolved_oxygen": r["dissolved_oxygen"],
            "water_quality_grade": r["water_quality_grade"],
            "create_time": r["create_time"].isoformat() if r["create_time"] else None,
        }
        for r in rows
    ]

    return json.dumps(
        {
            "count": len(data),
            "filters": {"station_name": station_name, "hours": hours},
            "data": data,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def get_water_quality_latest() -> str:
    """
    获取所有水质监测站的最新数据。

    Returns:
        JSON 字符串，包含各监测站最新水质数据
    """
    query = """
    WITH LatestData AS (
        SELECT DISTINCT ON (station_id)
            station_id,
            cod,
            ammonia_nitrogen,
            dissolved_oxygen,
            water_quality_grade,
            create_time
        FROM water_quality_monitoring_station_data
        ORDER BY station_id, create_time DESC
    )
    SELECT
        s.id,
        s.station_name,
        s.station_location_code,
        ST_X(s.geom::geometry) as lng,
        ST_Y(s.geom::geometry) as lat,
        ld.cod,
        ld.ammonia_nitrogen,
        ld.dissolved_oxygen,
        ld.water_quality_grade,
        ld.create_time
    FROM LatestData ld
    JOIN water_quality_monitoring_station_info s ON ld.station_id = s.id
    ORDER BY s.id
    """

    async with get_db_connection() as conn:
        rows = await conn.fetch(query)

    data = [
        {
            "id": r["id"],
            "station_name": r["station_name"],
            "station_code": r["station_location_code"],
            "lng": r["lng"],
            "lat": r["lat"],
            "cod": r["cod"],
            "ammonia_nitrogen": r["ammonia_nitrogen"],
            "dissolved_oxygen": r["dissolved_oxygen"],
            "water_quality_grade": r["water_quality_grade"],
            "create_time": r["create_time"].isoformat() if r["create_time"] else None,
        }
        for r in rows
    ]

    return json.dumps(
        {
            "count": len(data),
            "summary": {
                "total_stations": len(data),
                "grade_counts": _count_grades(data),
            },
            "data": data,
        },
        ensure_ascii=False,
        indent=2,
    )


def _count_grades(data: list) -> dict:
    counts = {}
    for item in data:
        grade = item.get("water_quality_grade") or "未知"
        counts[grade] = counts.get(grade, 0) + 1
    return counts


# =============================================================================
# === 启动入口 ===
# =============================================================================


def main():
    """主入口函数"""
    mcp.run()