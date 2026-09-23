"""纸本文物展厅光照额度管理 —— FastAPI 入口。"""
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import database, logic
from .schemas import ArtifactIn, ArtifactUpdate, ExhibitionIn

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_DB_PATH = str(BASE_DIR.parent / "data" / "light_budget.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init(os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH))
    yield
    database.conn().close()


app = FastAPI(title="纸本文物展厅光照额度管理", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------- 页面与探活

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- 藏品管理

def _artifact_or_404(artifact_id: int) -> sqlite3.Row:
    row = database.conn().execute(
        "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="藏品不存在")
    return row


def _artifact_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "annual_budget_lux_hours": row["annual_budget_lux_hours"],
        "created_at": row["created_at"],
    }


@app.post("/api/artifacts", status_code=201)
def create_artifact(payload: ArtifactIn):
    """登记藏品及其年度光照额度。"""
    with database.lock():
        try:
            cur = database.conn().execute(
                "INSERT INTO artifacts (name, description, annual_budget_lux_hours) "
                "VALUES (?, ?, ?)",
                (payload.name.strip(), payload.description.strip(),
                 payload.annual_budget_lux_hours),
            )
            database.conn().commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="同名藏品已存在")
        return _artifact_dict(_artifact_or_404(cur.lastrowid))


@app.get("/api/artifacts")
def list_artifacts():
    rows = database.conn().execute(
        "SELECT * FROM artifacts ORDER BY id").fetchall()
    return [_artifact_dict(r) for r in rows]


@app.get("/api/artifacts/{artifact_id}")
def get_artifact(artifact_id: int):
    return _artifact_dict(_artifact_or_404(artifact_id))


@app.put("/api/artifacts/{artifact_id}")
def update_artifact(artifact_id: int, payload: ArtifactUpdate):
    """调整藏品信息（如年度额度）。"""
    with database.lock():
        row = _artifact_or_404(artifact_id)
        name = payload.name.strip() if payload.name is not None else row["name"]
        budget = (payload.annual_budget_lux_hours
                  if payload.annual_budget_lux_hours is not None
                  else row["annual_budget_lux_hours"])
        description = (payload.description.strip()
                       if payload.description is not None else row["description"])
        try:
            database.conn().execute(
                "UPDATE artifacts SET name = ?, description = ?, "
                "annual_budget_lux_hours = ? WHERE id = ?",
                (name, description, budget, artifact_id))
            database.conn().commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="同名藏品已存在")
        return _artifact_dict(_artifact_or_404(artifact_id))


@app.delete("/api/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: int):
    with database.lock():
        _artifact_or_404(artifact_id)
        database.conn().execute(
            "DELETE FROM artifacts WHERE id = ?", (artifact_id,))
        database.conn().commit()


# ---------------------------------------------------------------- 展陈记录

def _exhibition_dict(row: sqlite3.Row) -> dict:
    start = datetime.fromisoformat(row["start_time"])
    end = datetime.fromisoformat(row["end_time"])
    year_split = logic.exposure_by_year(start, end, row["avg_lux"])
    return {
        "id": row["id"],
        "artifact_id": row["artifact_id"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "avg_lux": row["avg_lux"],
        "note": row["note"],
        "duration_hours": round((end - start).total_seconds() / 3600.0, 4),
        "exposure_lux_hours": round(sum(year_split.values()), 2),
        "exposure_by_year": {str(y): round(v, 2) for y, v in sorted(year_split.items())},
    }


@app.post("/api/artifacts/{artifact_id}/exhibitions", status_code=201)
def create_exhibition(artifact_id: int, payload: ExhibitionIn):
    """登记展陈记录。与已有记录时间重叠时拒绝保存（409）。"""
    start = logic.to_naive_utc(payload.start_time)
    end = logic.to_naive_utc(payload.end_time)
    start_iso, end_iso = start.isoformat(), end.isoformat()

    with database.lock():
        _artifact_or_404(artifact_id)
        overlap = logic.find_overlap(
            database.conn(), artifact_id, start_iso, end_iso)
        if overlap is not None:
            raise HTTPException(
                status_code=409,
                detail=(f"与已有展陈记录 #{overlap['id']} "
                        f"（{overlap['start_time']} ~ {overlap['end_time']}）"
                        f"时间重叠，已拒绝保存"),
            )
        cur = database.conn().execute(
            "INSERT INTO exhibitions (artifact_id, start_time, end_time, avg_lux, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (artifact_id, start_iso, end_iso, payload.avg_lux, payload.note.strip()),
        )
        database.conn().commit()
        row = database.conn().execute(
            "SELECT * FROM exhibitions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _exhibition_dict(row)


@app.get("/api/artifacts/{artifact_id}/exhibitions")
def list_exhibitions(artifact_id: int):
    _artifact_or_404(artifact_id)
    rows = database.conn().execute(
        "SELECT * FROM exhibitions WHERE artifact_id = ? ORDER BY start_time",
        (artifact_id,)).fetchall()
    return [_exhibition_dict(r) for r in rows]


@app.delete("/api/exhibitions/{exhibition_id}", status_code=204)
def delete_exhibition(exhibition_id: int):
    with database.lock():
        cur = database.conn().execute(
            "DELETE FROM exhibitions WHERE id = ?", (exhibition_id,))
        database.conn().commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="展陈记录不存在")


# ---------------------------------------------------------------- 额度汇总

def _summary_item(artifact_row: sqlite3.Row, year: int) -> dict:
    used, contributions = logic.yearly_usage(
        database.conn(), artifact_row["id"], year)
    budget = artifact_row["annual_budget_lux_hours"]
    return {
        "artifact_id": artifact_row["id"],
        "name": artifact_row["name"],
        "year": year,
        "annual_budget_lux_hours": budget,
        "used_lux_hours": round(used, 2),
        "remaining_lux_hours": round(budget - used, 2),
        "over_budget": used > budget,
        "contributions": contributions,
    }


@app.get("/api/artifacts/{artifact_id}/summary")
def artifact_summary(artifact_id: int,
                     year: int = Query(ge=1900, le=9999, description="统计年份")):
    """单个藏品指定年度的额度使用情况。"""
    row = _artifact_or_404(artifact_id)
    return _summary_item(row, year)


@app.get("/api/summary")
def overall_summary(year: int = Query(ge=1900, le=9999, description="统计年份")):
    """全部藏品指定年度汇总，超额藏品排在前面并标记 over_budget。"""
    rows = database.conn().execute(
        "SELECT * FROM artifacts ORDER BY id").fetchall()
    items = [_summary_item(r, year) for r in rows]
    items.sort(key=lambda x: (not x["over_budget"], x["artifact_id"]))
    return {
        "year": year,
        "over_budget_count": sum(1 for i in items if i["over_budget"]),
        "items": items,
    }
