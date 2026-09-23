"""核心业务逻辑：有效暴露累计、跨年拆分、时间重叠检测。"""
from datetime import datetime, timezone


def to_naive_utc(dt: datetime) -> datetime:
    """带时区的时间统一转换为 UTC 并去掉时区信息，保证库内时间可比较。"""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def split_by_year(start: datetime, end: datetime) -> list[tuple[int, float]]:
    """把半开区间 [start, end) 按自然年边界拆分，返回 [(年份, 小时数), ...]。"""
    segments: list[tuple[int, float]] = []
    current = start
    while current < end:
        boundary = datetime(current.year + 1, 1, 1)
        seg_end = min(boundary, end)
        hours = (seg_end - current).total_seconds() / 3600.0
        if hours > 0:
            segments.append((current.year, hours))
        current = seg_end
    return segments


def exposure_by_year(start: datetime, end: datetime, avg_lux: float) -> dict[int, float]:
    """按年拆分并计算各年有效暴露（lux·小时）。"""
    return {year: hours * avg_lux for year, hours in split_by_year(start, end)}


def find_overlap(conn, artifact_id: int, start_iso: str, end_iso: str,
                 exclude_id: int | None = None):
    """检查同一藏品是否存在与新记录 [start_iso, end_iso) 时间重叠的展陈记录。

    半开区间判定：existing.start < new.end 且 existing.end > new.start，
    首尾相接（一条结束即另一条开始）不算重叠。
    """
    sql = ("SELECT id, start_time, end_time FROM exhibitions "
           "WHERE artifact_id = ? AND start_time < ? AND end_time > ?")
    params: list = [artifact_id, end_iso, start_iso]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " ORDER BY start_time LIMIT 1"
    return conn.execute(sql, params).fetchone()


def yearly_usage(conn, artifact_id: int, year: int) -> tuple[float, list[dict]]:
    """计算某藏品在某自然年的累计有效暴露（lux·小时）及逐条记录贡献。

    只取与该年有交集的记录，跨年记录按时间边界拆分后仅计入落在该年的部分。
    """
    year_start = f"{year:04d}-01-01T00:00:00"
    year_end = f"{year + 1:04d}-01-01T00:00:00"
    rows = conn.execute(
        "SELECT * FROM exhibitions "
        "WHERE artifact_id = ? AND start_time < ? AND end_time > ? "
        "ORDER BY start_time",
        (artifact_id, year_end, year_start),
    ).fetchall()

    total = 0.0
    contributions: list[dict] = []
    for row in rows:
        start = datetime.fromisoformat(row["start_time"])
        end = datetime.fromisoformat(row["end_time"])
        for seg_year, hours in split_by_year(start, end):
            if seg_year == year:
                amount = hours * row["avg_lux"]
                total += amount
                contributions.append({
                    "exhibition_id": row["id"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "avg_lux": row["avg_lux"],
                    "hours_in_year": round(hours, 4),
                    "exposure_lux_hours": round(amount, 2),
                })
    return total, contributions
