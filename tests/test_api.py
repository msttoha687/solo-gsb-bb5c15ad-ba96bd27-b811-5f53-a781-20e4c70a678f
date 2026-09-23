from datetime import datetime


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_page_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "年度" in r.text


def test_write_requires_auth(client):
    r = client.post("/api/artifacts", json={"name": "x", "inventory_no": "X-1"})
    assert r.status_code == 401


def test_full_quota_flow(client, auth):
    # 登记藏品
    r = client.post(
        "/api/artifacts",
        json={"name": "宋本画册", "inventory_no": "P-100", "medium": "纸本", "description": ""},
        auth=auth,
    )
    assert r.status_code == 201
    aid = r.json()["id"]

    # 重复编号拒绝
    r = client.post(
        "/api/artifacts",
        json={"name": "重复", "inventory_no": "P-100"},
        auth=auth,
    )
    assert r.status_code == 409

    # 设置年度额度 1000 lux·h
    r = client.put(
        f"/api/artifacts/{aid}/quota",
        json={"year": 2026, "quota_lux_hours": 1000.0},
        auth=auth,
    )
    assert r.status_code == 200

    # 展陈 10 小时 × 50 lux = 500 lux·h
    r = client.post(
        f"/api/artifacts/{aid}/records",
        json={
            "start_time": "2026-03-01T09:00",
            "end_time": "2026-03-01T19:00",
            "avg_lux": 50.0,
        },
        auth=auth,
    )
    assert r.status_code == 201
    assert r.json()["exposure_by_year"] == {"2026": 500.0}

    r = client.get("/api/summary?year=2026")
    assert r.status_code == 200
    row = next(x for x in r.json() if x["artifact_id"] == aid)
    assert row["used_lux_hours"] == 500.0
    assert row["remaining_lux_hours"] == 500.0
    assert row["usage_percent"] == 50.0
    assert row["over_quota"] is False


def test_overlap_rejected(client, auth):
    r = client.post("/api/artifacts", json={"name": "卷轴", "inventory_no": "P-200"}, auth=auth)
    aid = r.json()["id"]
    rec = {
        "start_time": "2026-05-01T09:00",
        "end_time": "2026-05-01T17:00",
        "avg_lux": 40.0,
    }
    assert client.post(f"/api/artifacts/{aid}/records", json=rec, auth=auth).status_code == 201

    # 重叠记录拒绝
    bad = {**rec, "start_time": "2026-05-01T10:00", "end_time": "2026-05-01T12:00"}
    r = client.post(f"/api/artifacts/{aid}/records", json=bad, auth=auth)
    assert r.status_code == 409

    # 首尾相接允许
    touch = {**rec, "start_time": "2026-05-01T17:00", "end_time": "2026-05-01T18:00"}
    assert client.post(f"/api/artifacts/{aid}/records", json=touch, auth=auth).status_code == 201


def test_invalid_record_rejected(client, auth):
    r = client.post("/api/artifacts", json={"name": "信札", "inventory_no": "P-300"}, auth=auth)
    aid = r.json()["id"]
    # 结束早于开始
    r = client.post(
        f"/api/artifacts/{aid}/records",
        json={"start_time": "2026-03-01T10:00", "end_time": "2026-03-01T09:00", "avg_lux": 50},
        auth=auth,
    )
    assert r.status_code == 422
    # 照度非正
    r = client.post(
        f"/api/artifacts/{aid}/records",
        json={"start_time": "2026-03-01T09:00", "end_time": "2026-03-01T10:00", "avg_lux": 0},
        auth=auth,
    )
    assert r.status_code == 422


def test_over_quota_flag(client, auth):
    r = client.post("/api/artifacts", json={"name": "古籍", "inventory_no": "P-400"}, auth=auth)
    aid = r.json()["id"]
    client.put(
        f"/api/artifacts/{aid}/quota",
        json={"year": 2026, "quota_lux_hours": 100.0},
        auth=auth,
    )
    # 8 小时 × 20 lux = 160 > 100 → 超额
    client.post(
        f"/api/artifacts/{aid}/records",
        json={"start_time": "2026-03-01T09:00", "end_time": "2026-03-01T17:00", "avg_lux": 20.0},
        auth=auth,
    )
    row = next(
        x for x in client.get("/api/summary?year=2026").json() if x["artifact_id"] == aid
    )
    assert row["used_lux_hours"] == 160.0
    assert row["remaining_lux_hours"] == -60.0
    assert row["over_quota"] is True


def test_cross_year_record_split(client, auth):
    r = client.post("/api/artifacts", json={"name": "书画", "inventory_no": "P-500"}, auth=auth)
    aid = r.json()["id"]
    client.put(f"/api/artifacts/{aid}/quota", json={"year": 2025, "quota_lux_hours": 10000}, auth=auth)
    client.put(f"/api/artifacts/{aid}/quota", json={"year": 2026, "quota_lux_hours": 10000}, auth=auth)

    # 2025-12-31 20:00 ~ 2026-01-01 04:00，50 lux → 各 200 lux·h
    r = client.post(
        f"/api/artifacts/{aid}/records",
        json={"start_time": "2025-12-31T20:00", "end_time": "2026-01-01T04:00", "avg_lux": 50.0},
        auth=auth,
    )
    assert r.status_code == 201

    row_2025 = next(x for x in client.get("/api/summary?year=2025").json() if x["artifact_id"] == aid)
    row_2026 = next(x for x in client.get("/api/summary?year=2026").json() if x["artifact_id"] == aid)
    assert row_2025["used_lux_hours"] == 200.0
    assert row_2026["used_lux_hours"] == 200.0
    assert row_2025["over_quota"] is False


def test_record_not_found(client, auth):
    assert client.delete("/api/records/9999", auth=auth).status_code == 404
