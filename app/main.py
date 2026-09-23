"""FastAPI 入口：管理页面 + JSON API。"""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import services
from .auth import require_admin
from .config import APP_TITLE
from .db import Base, engine, get_db
from .models import AnnualQuota, Artifact, ExhibitionRecord
from .schemas import ArtifactIn, QuotaIn, RecordIn, YearSummaryOut

BASE_DIR = Path(__file__).resolve().parent

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_TITLE, version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------- 工具 ----------

def render(request: Request, template: str, **ctx):
    """渲染模板，并透传 ?msg= / ?error= 提示。"""
    ctx.setdefault("msg", request.query_params.get("msg"))
    ctx.setdefault("error", request.query_params.get("error"))
    return templates.TemplateResponse(request, template, ctx)


def redirect(url: str, msg: str | None = None, error: str | None = None):
    params = {k: v for k, v in {"msg": msg, "error": error}.items() if v}
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def parse_dt(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} 时间格式不正确")


def validate_record(start: datetime, end: datetime, avg_lux: float) -> str | None:
    if end <= start:
        return "结束时间必须晚于开始时间"
    if avg_lux <= 0:
        return "平均照度必须大于 0"
    return None


# ---------- 页面 ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, year: int | None = None, db: Session = Depends(get_db)):
    year = year or datetime.now().year
    return render(
        request,
        "index.html",
        rows=services.yearly_summary(db, year),
        year=year,
        years=services.available_years(db),
    )


@app.get("/artifacts", response_class=HTMLResponse)
def artifact_list(request: Request, db: Session = Depends(get_db)):
    artifacts = db.scalars(select(Artifact).order_by(Artifact.id)).all()
    return render(request, "artifacts.html", artifacts=artifacts)


@app.post("/artifacts")
def create_artifact(
    name: str = Form(...),
    inventory_no: str = Form(...),
    medium: str = Form("纸本"),
    description: str = Form(""),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    artifact = Artifact(
        name=name.strip(), inventory_no=inventory_no.strip(),
        medium=medium.strip() or "纸本", description=description.strip(),
    )
    db.add(artifact)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect("/artifacts", error=f"藏品编号 {inventory_no} 已存在")
    return redirect("/artifacts", msg=f"藏品《{artifact.name}》已登记")


@app.post("/artifacts/{artifact_id}/delete")
def delete_artifact(
    artifact_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        return redirect("/artifacts", error="藏品不存在")
    db.delete(artifact)
    db.commit()
    return redirect("/artifacts", msg=f"藏品《{artifact.name}》及其额度、展陈记录已删除")


@app.get("/artifacts/{artifact_id}", response_class=HTMLResponse)
def artifact_detail(artifact_id: int, request: Request, db: Session = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        return redirect("/artifacts", error="藏品不存在")
    quotas = sorted(artifact.quotas, key=lambda q: q.year, reverse=True)
    records = sorted(artifact.records, key=lambda r: r.start_time, reverse=True)
    record_rows = [
        {
            "rec": r,
            "duration_hours": round(
                (r.end_time - r.start_time).total_seconds() / 3600, 2
            ),
            "exposure": services.exposure_by_year(r.start_time, r.end_time, r.avg_lux),
        }
        for r in records
    ]
    years = sorted({q.year for q in quotas} | {datetime.now().year}, reverse=True)
    summaries = {y: services.yearly_summary(db, y) for y in years}
    usage = {
        y: next((r for r in rows if r["artifact_id"] == artifact_id), None)
        for y, rows in summaries.items()
    }
    return render(
        request,
        "artifact_detail.html",
        artifact=artifact,
        quotas=quotas,
        record_rows=record_rows,
        usage=usage,
        default_year=datetime.now().year,
    )


@app.post("/artifacts/{artifact_id}/quota")
def set_quota(
    artifact_id: int,
    year: int = Form(...),
    quota_lux_hours: float = Form(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    back = f"/artifacts/{artifact_id}"
    if db.get(Artifact, artifact_id) is None:
        return redirect("/artifacts", error="藏品不存在")
    if not (1900 <= year <= 2200):
        return redirect(back, error="年份需在 1900–2200 之间")
    if quota_lux_hours < 0:
        return redirect(back, error="额度不能为负数")
    quota = db.scalars(
        select(AnnualQuota).where(
            AnnualQuota.artifact_id == artifact_id, AnnualQuota.year == year
        )
    ).first()
    if quota is None:
        db.add(AnnualQuota(
            artifact_id=artifact_id, year=year, quota_lux_hours=quota_lux_hours
        ))
    else:
        quota.quota_lux_hours = quota_lux_hours
    db.commit()
    return redirect(back, msg=f"{year} 年度额度已保存")


@app.post("/artifacts/{artifact_id}/records")
def create_record(
    artifact_id: int,
    start_time: str = Form(...),
    end_time: str = Form(...),
    avg_lux: float = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    back = f"/artifacts/{artifact_id}"
    if db.get(Artifact, artifact_id) is None:
        return redirect("/artifacts", error="藏品不存在")
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
    except ValueError:
        return redirect(back, error="时间格式不正确")
    if err := validate_record(start, end, avg_lux):
        return redirect(back, error=err)
    overlap = services.artifact_has_overlap(db, artifact_id, start, end)
    if overlap is not None:
        return redirect(
            back,
            error=(
                "与已有展陈记录时间重叠，已拒绝保存："
                f"{overlap.start_time:%Y-%m-%d %H:%M} ~ {overlap.end_time:%Y-%m-%d %H:%M}"
            ),
        )
    db.add(ExhibitionRecord(
        artifact_id=artifact_id, start_time=start, end_time=end,
        avg_lux=avg_lux, note=note.strip(),
    ))
    db.commit()
    return redirect(back, msg="展陈记录已保存")


@app.post("/records/{record_id}/delete")
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    record = db.get(ExhibitionRecord, record_id)
    if record is None:
        return redirect("/artifacts", error="记录不存在")
    artifact_id = record.artifact_id
    db.delete(record)
    db.commit()
    return redirect(f"/artifacts/{artifact_id}", msg="展陈记录已删除")


# ---------- JSON API ----------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/summary", response_model=list[YearSummaryOut])
def api_summary(year: int | None = None, db: Session = Depends(get_db)):
    return services.yearly_summary(db, year or datetime.now().year)


@app.post("/api/artifacts", status_code=201)
def api_create_artifact(
    payload: ArtifactIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    artifact = Artifact(**payload.model_dump())
    db.add(artifact)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="藏品编号已存在")
    return {"id": artifact.id, "name": artifact.name}


@app.put("/api/artifacts/{artifact_id}/quota")
def api_set_quota(
    artifact_id: int,
    payload: QuotaIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    if db.get(Artifact, artifact_id) is None:
        raise HTTPException(status_code=404, detail="藏品不存在")
    quota = db.scalars(
        select(AnnualQuota).where(
            AnnualQuota.artifact_id == artifact_id, AnnualQuota.year == payload.year
        )
    ).first()
    if quota is None:
        quota = AnnualQuota(artifact_id=artifact_id, year=payload.year,
                            quota_lux_hours=payload.quota_lux_hours)
        db.add(quota)
    else:
        quota.quota_lux_hours = payload.quota_lux_hours
    db.commit()
    return {"artifact_id": artifact_id, "year": payload.year,
            "quota_lux_hours": payload.quota_lux_hours}


@app.post("/api/artifacts/{artifact_id}/records", status_code=201)
def api_create_record(
    artifact_id: int,
    payload: RecordIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    if db.get(Artifact, artifact_id) is None:
        raise HTTPException(status_code=404, detail="藏品不存在")
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=422, detail="结束时间必须晚于开始时间")
    overlap = services.artifact_has_overlap(
        db, artifact_id, payload.start_time, payload.end_time
    )
    if overlap is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "与已有展陈记录时间重叠，已拒绝保存："
                f"{overlap.start_time.isoformat()} ~ {overlap.end_time.isoformat()}"
            ),
        )
    record = ExhibitionRecord(artifact_id=artifact_id, **payload.model_dump())
    db.add(record)
    db.commit()
    return {
        "id": record.id,
        "exposure_by_year": services.exposure_by_year(
            record.start_time, record.end_time, record.avg_lux
        ),
    }


@app.delete("/api/records/{record_id}", status_code=204)
def api_delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    record = db.get(ExhibitionRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
