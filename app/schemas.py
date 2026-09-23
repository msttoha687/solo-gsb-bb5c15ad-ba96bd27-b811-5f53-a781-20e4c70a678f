"""请求/响应数据模型。"""
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ArtifactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="藏品名称")
    annual_budget_lux_hours: float = Field(gt=0, description="年度光照额度（lux·小时）")
    description: str = Field(default="", max_length=2000, description="备注说明")


class ArtifactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    annual_budget_lux_hours: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=2000)


class ExhibitionIn(BaseModel):
    start_time: datetime = Field(description="展陈开始时间，ISO 8601")
    end_time: datetime = Field(description="展陈结束时间，ISO 8601")
    avg_lux: float = Field(ge=0, description="平均照度（lux）")
    note: str = Field(default="", max_length=2000, description="备注")

    @model_validator(mode="after")
    def check_time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间")
        return self
