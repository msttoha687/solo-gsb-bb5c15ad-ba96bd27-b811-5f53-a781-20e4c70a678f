"""数据模型：藏品、年度光照额度、展陈记录。"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Artifact(Base):
    """藏品（纸本文物）。"""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    inventory_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    medium: Mapped[str] = mapped_column(String(100), default="纸本", nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    quotas: Mapped[list["AnnualQuota"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )
    records: Mapped[list["ExhibitionRecord"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class AnnualQuota(Base):
    """某藏品在某一年度的光照额度（单位：lux·小时）。"""

    __tablename__ = "annual_quotas"
    __table_args__ = (
        UniqueConstraint("artifact_id", "year", name="uq_quota_artifact_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_lux_hours: Mapped[float] = mapped_column(Float, nullable=False)

    artifact: Mapped[Artifact] = relationship(back_populates="quotas")


class ExhibitionRecord(Base):
    """展陈记录：起止时间与平均照度。同一藏品的时间段不得重叠。"""

    __tablename__ = "exhibition_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    avg_lux: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    artifact: Mapped[Artifact] = relationship(back_populates="records")
