"""演示数据：python -m app.seed

创建两件示例藏品、当年额度与若干展陈记录（含一条跨年记录），便于快速体验。
"""
from datetime import datetime, timedelta

from .db import Base, SessionLocal, engine
from .models import AnnualQuota, Artifact, ExhibitionRecord


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Artifact).count() > 0:
            print("已有数据，跳过种子导入。")
            return
        year = datetime.now().year

        a1 = Artifact(name="宋摹本《兰亭序》", inventory_no="P-0001",
                      medium="纸本", description="一级文物，低照度展柜")
        a2 = Artifact(name="清代山水册页", inventory_no="P-0002",
                      medium="纸本设色", description="轮换展出")
        db.add_all([a1, a2])
        db.flush()

        db.add_all([
            AnnualQuota(artifact_id=a1.id, year=year, quota_lux_hours=120_000),
            AnnualQuota(artifact_id=a2.id, year=year, quota_lux_hours=80_000),
        ])

        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        db.add_all([
            ExhibitionRecord(
                artifact_id=a1.id,
                start_time=now - timedelta(days=30),
                end_time=now - timedelta(days=30) + timedelta(hours=8 * 20),
                avg_lux=50, note="春季特展",
            ),
            # 跨年记录：上一年 12 月下旬延续到当年 1 月
            ExhibitionRecord(
                artifact_id=a2.id,
                start_time=datetime(year - 1, 12, 20, 9),
                end_time=datetime(year, 1, 10, 17),
                avg_lux=45, note="跨年迎新展",
            ),
        ])
        db.commit()
        print("种子数据已导入：2 件藏品、当年额度、2 条展陈记录（含 1 条跨年记录）。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
