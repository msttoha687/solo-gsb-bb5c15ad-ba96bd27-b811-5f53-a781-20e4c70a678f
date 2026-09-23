"""接口与核心逻辑测试。运行：pytest -v"""
import os

os.environ["DATABASE_PATH"] = ":memory:"  # 须在导入 app 前设置

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def artifact(client):
    resp = client.post("/api/artifacts", json={
        "name": "纸质手卷A", "annual_budget_lux_hours": 1000.0,
        "description": "一级文物",
    })
    assert resp.status_code == 201
    return resp.json()


def test_create_artifact_and_duplicate_name(client, artifact):
    assert artifact["annual_budget_lux_hours"] == 1000.0
    dup = client.post("/api/artifacts", json={
        "name": "纸质手卷A", "annual_budget_lux_hours": 500.0})
    assert dup.status_code == 409


def test_exposure_accumulates_and_remaining(client, artifact):
    aid = artifact["id"]
    resp = client.post(f"/api/artifacts/{aid}/exhibitions", json={
        "start_time": "2026-03-01T09:00:00", "end_time": "2026-03-01T17:00:00",
        "avg_lux": 50.0})
    assert resp.status_code == 201
    assert resp.json()["exposure_lux_hours"] == 400.0

    summary = client.get(f"/api/artifacts/{aid}/summary", params={"year": 2026}).json()
    assert summary["used_lux_hours"] == 400.0
    assert summary["remaining_lux_hours"] == 600.0
    assert summary["over_budget"] is False


def test_cross_year_record_splits_at_boundary(client, artifact):
    aid = artifact["id"]
    resp = client.post(f"/api/artifacts/{aid}/exhibitions", json={
        "start_time": "2025-12-31T20:00:00", "end_time": "2026-01-01T04:00:00",
        "avg_lux": 50.0})
    assert resp.status_code == 201
    body = resp.json()
    assert body["exposure_by_year"] == {"2025": 200.0, "2026": 200.0}

    s2025 = client.get(f"/api/artifacts/{aid}/summary", params={"year": 2025}).json()
    s2026 = client.get(f"/api/artifacts/{aid}/summary", params={"year": 2026}).json()
    assert s2025["used_lux_hours"] == 200.0
    assert s2026["used_lux_hours"] == 200.0


def test_overlapping_record_rejected(client, artifact):
    aid = artifact["id"]
    first = client.post(f"/api/artifacts/{aid}/exhibitions", json={
        "start_time": "2026-05-01T09:00:00", "end_time": "2026-05-10T18:00:00",
        "avg_lux": 30.0})
    assert first.status_code == 201

    # 完全包含、部分重叠、被包含，均应拒绝
    for start, end in [
        ("2026-05-05T00:00:00", "2026-05-06T00:00:00"),
        ("2026-05-09T00:00:00", "2026-05-20T00:00:00"),
        ("2026-04-01T00:00:00", "2026-06-01T00:00:00"),
    ]:
        resp = client.post(f"/api/artifacts/{aid}/exhibitions", json={
            "start_time": start, "end_time": end, "avg_lux": 10.0})
        assert resp.status_code == 409, (start, end)
        assert "重叠" in resp.json()["detail"]

    # 首尾相接不算重叠
    adjacent = client.post(f"/api/artifacts/{aid}/exhibitions", json={
        "start_time": "2026-05-10T18:00:00", "end_time": "2026-05-12T09:00:00",
        "avg_lux": 30.0})
    assert adjacent.status_code == 201


def test_over_budget_flagged(client, artifact):
    aid = artifact["id"]
    client.post(f"/api/artifacts/{aid}/exhibitions", json={
        "start_time": "2026-01-10T08:00:00", "end_time": "2026-01-10T20:00:00",
        "avg_lux": 100.0})  # 12h × 100lux = 1200 > 1000 额度
    summary = client.get("/api/summary", params={"year": 2026}).json()
    assert summary["over_budget_count"] == 1
    item = summary["items"][0]
    assert item["over_budget"] is True
    assert item["remaining_lux_hours"] == -200.0


def test_invalid_time_range_rejected(client, artifact):
    resp = client.post(f"/api/artifacts/{artifact['id']}/exhibitions", json={
        "start_time": "2026-01-02T10:00:00", "end_time": "2026-01-02T09:00:00",
        "avg_lux": 50.0})
    assert resp.status_code == 422


def test_exhibition_requires_existing_artifact(client):
    resp = client.post("/api/artifacts/999/exhibitions", json={
        "start_time": "2026-01-01T08:00:00", "end_time": "2026-01-01T09:00:00",
        "avg_lux": 50.0})
    assert resp.status_code == 404


def test_split_by_year_logic():
    from datetime import datetime
    from app.logic import split_by_year
    segs = split_by_year(datetime(2024, 12, 31, 12), datetime(2026, 1, 1, 12))
    assert segs == [(2024, 12.0), (2025, 8760.0), (2026, 12.0)]
