"""JSON API 的请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, Field


class ArtifactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    inventory_no: str = Field(min_length=1, max_length=100)
    medium: str = Field(default="纸本", max_length=100)
    description: str = Field(default="", max_length=500)


class QuotaIn(BaseModel):
    year: int = Field(ge=1900, le=2200)
    quota_lux_hours: float = Field(ge=0)


class RecordIn(BaseModel):
    start_time: datetime
    end_time: datetime
    avg_lux: float = Field(gt=0)
    note: str = Field(default="", max_length=500)


class YearSummaryOut(BaseModel):
    artifact_id: int
    name: str
    inventory_no: str
    medium: str
    year: int
    quota_lux_hours: float | None
    used_lux_hours: float
    remaining_lux_hours: float | None
    usage_percent: float | None
    over_quota: bool
