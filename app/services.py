"""核心业务逻辑：有效暴露累计、跨年拆分、重叠检测、额度汇总。

约定：
- 时间段按左闭右开 [start, end) 处理，首尾相接的两条记录不算重叠；
- 有效暴露量 = 平均照度(lux) × 时长(小时)，单位 lux·小时；
- 跨年记录在自然年边界（1 月 1 日 00:00）处拆分，分别计入各年度。
"""
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AnnualQuota, Artifact, ExhibitionRecord


def split_by_year(start: datetime, end: datetime) -> Iterator[tuple[int, float]]:
    """将 [start, end) 按自然年边界拆分，逐年产出 (年份, 小时数)。"""
    if end <= start:
        raise ValueError("结束时间必须晚于开始时间")
    cursor = start
    while cursor < end:
        boundary = datetime(cursor.year + 1, 1, 1)
        seg_end = min(end, boundary)
        hours = (seg_end - cursor).total_seconds() / 3600.0
        yield cursor.year, hours
        cursor = seg_end


def exposure_by_year(start: datetime, end: datetime, avg_lux: float) -> dict[int, float]:
    """计算一条展陈记录按年份拆分的有效暴露量（lux·小时）。"""
    result: dict[int, float] = defaultdict(float)
    for year, hours in split_by_year(start, end):
        result[year] += hours * avg_lux
    return dict(result)


def find_overlap(
    records: Iterable[ExhibitionRecord],
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> ExhibitionRecord | None:
    """在已有记录中查找与 [start, end) 重叠的第一条记录（左闭右开）。"""
    for r in records:
        if exclude_id is not None and r.id == exclude_id:
            continue
        if r.start_time < end and start < r.end_time:
            return r
    return None


def artifact_has_overlap(
    db: Session, artifact_id: int, start: datetime, end: datetime
) -> ExhibitionRecord | None:
    """检查某藏品是否已存在与 [start, end) 重叠的展陈记录。"""
    stmt = select(ExhibitionRecord).where(
        ExhibitionRecord.artifact_id == artifact_id,
        ExhibitionRecord.start_time < end,
        ExhibitionRecord.end_time > start,
    )
    return db.scalars(stmt).first()


def yearly_summary(db: Session, year: int) -> list[dict]:
    """汇总某一年度所有藏品的额度、已用暴露量、剩余额度与超额标记。"""
    artifacts = db.scalars(select(Artifact).order_by(Artifact.id)).all()
    quotas = {
        q.artifact_id: q.quota_lux_hours
        for q in db.scalars(select(AnnualQuota).where(AnnualQuota.year == year))
    }

    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)
    stmt = select(ExhibitionRecord).where(
        ExhibitionRecord.start_time < year_end,
        ExhibitionRecord.end_time > year_start,
    )
    used: dict[int, float] = defaultdict(float)
    for rec in db.scalars(stmt):
        for seg_year, lux_hours in exposure_by_year(
            rec.start_time, rec.end_time, rec.avg_lux
        ).items():
            if seg_year == year:
                used[rec.artifact_id] += lux_hours

    rows = []
    for a in artifacts:
        quota = quotas.get(a.id)
        used_lh = round(used.get(a.id, 0.0), 2)
        remaining = round(quota - used_lh, 2) if quota is not None else None
        usage_pct = round(used_lh / quota * 100, 1) if quota else None
        rows.append(
            {
                "artifact_id": a.id,
                "name": a.name,
                "inventory_no": a.inventory_no,
                "medium": a.medium,
                "year": year,
                "quota_lux_hours": quota,
                "used_lux_hours": used_lh,
                "remaining_lux_hours": remaining,
                "usage_percent": usage_pct,
                "over_quota": remaining is not None and remaining < 0,
            }
        )
    return rows


def available_years(db: Session) -> list[int]:
    """汇总出现过的年份（额度与展陈记录），供页面年份切换。"""
    years = {datetime.now().year}
    years.update(db.scalars(select(AnnualQuota.year)).all())
    for (start,) in db.execute(select(ExhibitionRecord.start_time)):
        years.add(start.year)
    for (end,) in db.execute(select(ExhibitionRecord.end_time)):
        # end 为右开边界，跨年记录的最后一段属于 end 之前的时刻
        years.add(end.year if end > datetime(end.year, 1, 1) else end.year - 1)
    return sorted(years, reverse=True)
