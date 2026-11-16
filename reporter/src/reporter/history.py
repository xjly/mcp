"""Bounded PostgreSQL history queries and schemas for the reporting tools."""

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

GroupBy = Literal["hour", "day"]
Limit = Annotated[int, Field(ge=1, le=1000, description="单页记录上限，最大 1000。")]
Offset = Annotated[int, Field(ge=0, le=2_147_483_647, description="分页偏移。")]
TimestampInput = Annotated[
    str, Field(description="ISO 8601 日期或时间戳。未提供时区时按上海时间解释。")
]
SHANGHAI = timezone(timedelta(hours=8))
MAX_RANGE = timedelta(days=366)


def shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def history_bounds(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    try:
        start = shanghai_time(datetime.fromisoformat(start_time))
        end = shanghai_time(datetime.fromisoformat(end_time))
    except (ValueError, OverflowError):
        raise ToolError(
            "请使用 ISO 8601 格式填写起止时间，例如 2026-11-16T09:00:00+08:00。"
        ) from None
    if start >= end:
        raise ToolError("开始时间必须早于结束时间。")
    if end - start > MAX_RANGE:
        raise ToolError("报表时间范围不能超过 366 天，请分段查询。")

    # Both database timestamp types accept these values. PostgreSQL uses the
    # connection's Shanghai time zone when either column is timestamptz.
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def finite_number(value: float | Decimal | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


Measurement = Annotated[float | None, BeforeValidator(finite_number)]
LocalTimestamp = Annotated[datetime, AfterValidator(shanghai_time)]


class MetricStats(BaseModel):
    count: int
    min: Measurement
    max: Measurement
    avg: Measurement


class GateDevice(BaseModel):
    device_id: int
    device_name: str | None
    station_id: int
    station_name: str | None
    type_id: int
    type_name: str | None


class GateReading(GateDevice):
    id: int
    data_time: LocalTimestamp
    value: Measurement
    status: bool | None


class GateAggregate(GateDevice):
    bucket_start: LocalTimestamp
    sample_count: int
    active_samples: int
    value: MetricStats


class WaterStation(BaseModel):
    station_id: int
    station_name: str | None
    station_code: str | None


class WaterReading(WaterStation):
    id: int
    create_time: LocalTimestamp
    cod: Measurement
    ammonia_nitrogen: Measurement
    dissolved_oxygen: Measurement
    water_quality_grade: str | None


class WaterAggregate(WaterStation):
    bucket_start: LocalTimestamp
    sample_count: int
    cod: MetricStats
    ammonia_nitrogen: MetricStats
    dissolved_oxygen: MetricStats


class HistoryPage[T](BaseModel):
    start_time: LocalTimestamp
    end_time: LocalTimestamp
    group_by: GroupBy | None
    count: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None
    rows: list[T]


GateHistory = HistoryPage[GateReading | GateAggregate]
WaterHistory = HistoryPage[WaterReading | WaterAggregate]


_GATE_SOURCE = """
    FROM gate_station_device_data dd
    JOIN gate_station_devices d ON dd.device_id = d.device_id
    JOIN gate_station_info s ON d.station_id = s.id
    JOIN gate_station_device_types t ON d.type_id = t.type_id
    WHERE dd.create_time >= $1::timestamp AND dd.create_time < $2::timestamp
      AND ($3::text IS NULL OR s.gate_station_name = $3)
      AND ($4::text IS NULL OR t.type_name = $4)
"""

GATE_RAW = f"""
    SELECT dd.id, d.device_id, d.device_name, d.station_id, s.gate_station_name AS station_name,
           t.type_id, t.type_name, dd.device_value AS value, dd.device_status AS status,
           dd.create_time AS data_time
    {_GATE_SOURCE}
    ORDER BY data_time DESC, id DESC
    LIMIT $5 OFFSET $6
"""

GATE_GROUPED = f"""
    WITH observations AS (
        SELECT date_trunc($5::text, dd.create_time) AS bucket_start,
               d.device_id, d.device_name, d.station_id, s.gate_station_name AS station_name,
               t.type_id, t.type_name, dd.device_status AS status,
               CASE WHEN dd.device_value > '-Infinity'::float8
                       AND dd.device_value < 'Infinity'::float8 THEN dd.device_value END AS value
        {_GATE_SOURCE}
    )
    SELECT bucket_start, device_id, device_name, station_id, station_name, type_id, type_name,
           COUNT(*) AS sample_count, COUNT(*) FILTER (WHERE status) AS active_samples,
           COUNT(value) AS value_count, MIN(value) AS value_min,
           MAX(value) AS value_max, AVG(value) AS value_avg
    FROM observations
    GROUP BY bucket_start, device_id, device_name, station_id, station_name, type_id, type_name
    ORDER BY bucket_start DESC, station_id, device_id
    LIMIT $6 OFFSET $7
"""

_WATER_SOURCE = """
    FROM water_quality_monitoring_station_data wq
    JOIN water_quality_monitoring_station_info s ON wq.station_id = s.id
    WHERE wq.create_time >= $1::timestamp AND wq.create_time < $2::timestamp
      AND ($3::text IS NULL OR s.station_name = $3)
"""

WATER_RAW = f"""
    SELECT wq.id, wq.station_id, s.station_name, s.station_location_code AS station_code,
           wq.create_time, wq.cod, wq.ammonia_nitrogen, wq.dissolved_oxygen, wq.water_quality_grade
    {_WATER_SOURCE}
    ORDER BY wq.create_time DESC, wq.id DESC
    LIMIT $4 OFFSET $5
"""

WATER_GROUPED = f"""
    WITH observations AS (
        SELECT date_trunc($4::text, wq.create_time) AS bucket_start,
               wq.station_id, s.station_name, s.station_location_code AS station_code,
               CASE WHEN wq.cod > '-Infinity'::float8
                       AND wq.cod < 'Infinity'::float8 THEN wq.cod END AS cod,
               CASE WHEN wq.ammonia_nitrogen > '-Infinity'::float8
                       AND wq.ammonia_nitrogen < 'Infinity'::float8 THEN wq.ammonia_nitrogen END AS ammonia,
               CASE WHEN wq.dissolved_oxygen > '-Infinity'::float8
                       AND wq.dissolved_oxygen < 'Infinity'::float8 THEN wq.dissolved_oxygen END AS oxygen
        {_WATER_SOURCE}
    )
    SELECT bucket_start, station_id, station_name, station_code, COUNT(*) AS sample_count,
           COUNT(cod) AS cod_count, MIN(cod) AS cod_min, MAX(cod) AS cod_max, AVG(cod) AS cod_avg,
           COUNT(ammonia) AS ammonia_count, MIN(ammonia) AS ammonia_min,
           MAX(ammonia) AS ammonia_max, AVG(ammonia) AS ammonia_avg,
           COUNT(oxygen) AS oxygen_count, MIN(oxygen) AS oxygen_min,
           MAX(oxygen) AS oxygen_max, AVG(oxygen) AS oxygen_avg
    FROM observations
    GROUP BY bucket_start, station_id, station_name, station_code
    ORDER BY bucket_start DESC, station_id
    LIMIT $5 OFFSET $6
"""
