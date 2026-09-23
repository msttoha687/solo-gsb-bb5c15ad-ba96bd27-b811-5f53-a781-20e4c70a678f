# 纸本文物展厅光照额度管理

面向纸本文物展厅的光照额度管理 Web 应用：管理员可登记藏品的年度光照额度及展陈记录（起止时间、平均照度），系统按 **lux·小时** 累计有效暴露、计算剩余额度并标出超额藏品；跨年度记录按时间边界拆分计入各年，重叠记录拒绝保存。

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2.0 + SQLite
- 前端：Jinja2 服务端渲染 + 原生 CSS
- 部署：Dockerfile + docker compose 一键启动

## 一键启动（推荐）

```bash
git clone <仓库地址>
cd <仓库目录>
docker compose up --build
```

启动后访问 `http://localhost:8000`。

- 管理页面：`http://localhost:8000/`（年度总览）、`/artifacts`（藏品管理）
- JSON API：`http://localhost:8000/api/summary?year=2026`
- 健康检查：`http://localhost:8000/healthz`
- 管理员认证：默认用户名 `admin`、密码 `admin123`（可用环境变量覆盖，见下表）

首次启动数据库为空，可通过「藏品管理」页面登记，或导入演示数据：

```bash
docker compose exec web python -m app.seed
```

数据持久化在名为 `lightquota-data` 的 Docker volume 中，重启/重建容器均不会丢失。

## 本地开发

```bash
python3 -m pip install -r requirements-dev.txt   # 或使用 venv
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

本地默认使用 `./data/lightquota.db`（首次运行自动创建目录），访问 `http://127.0.0.1:8000`。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/lightquota.db` | SQLite 连接串；容器内固定为 `sqlite:////app/data/lightquota.db` |
| `ADMIN_USERNAME` | `admin` | 管理员用户名（HTTP Basic） |
| `ADMIN_PASSWORD` | `admin123` | 管理员密码（HTTP Basic），**生产环境务必修改** |

在 `docker-compose.yml` 中可直接修改 `ADMIN_PASSWORD`，或通过 `.env` 文件注入。

## 核心规则

1. **有效暴露量** = 平均照度（lux） × 展览时长（小时），单位 lux·小时。
2. **年度拆分**：跨年度的展陈记录以自然年 1 月 1 日 00:00 为边界拆分，分别计入各年度的累计与额度。例如 2025-12-31 20:00 至 2026-01-01 04:00、50 lux 的记录，计入 2025 年 200 lux·h、2026 年 200 lux·h。
3. **重叠检测**：同一藏品的时间段按左闭右开 `[start, end)` 判定，首尾相接（如 17:00 结束、17:00 开始）不算重叠，允许连续换展；任何真正重叠的记录在保存时都会被拒绝（页面表单与 JSON API 均返回错误）。
4. **超额标记**：年度累计暴露量超过年度额度时，该藏品在总览与详情页标红并显示「超额」。

## JSON API

写接口均需 HTTP Basic 认证。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/healthz` | 健康检查 |
| `GET` | `/api/summary?year=2026` | 年度额度/使用/剩余汇总 |
| `POST` | `/api/artifacts` | 登记藏品 |
| `PUT` | `/api/artifacts/{id}/quota` | 设置年度额度 |
| `POST` | `/api/artifacts/{id}/records` | 新增展陈记录（重叠时返回 409） |
| `DELETE` | `/api/records/{id}` | 删除展陈记录 |

新增展陈记录示例：

```bash
curl -u admin:admin123 -X POST http://localhost:8000/api/artifacts/1/records \
  -H 'Content-Type: application/json' \
  -d '{"start_time":"2026-03-01T09:00","end_time":"2026-03-01T19:00","avg_lux":50,"note":"春季特展"}'
```

## 测试

```bash
python3 -m pytest -q
```

测试覆盖：年度拆分（含闰年、跨年、多年份）、重叠边界、完整额度流程、超额标记、API 认证与错误码。

## 项目结构

```
app/
  main.py        FastAPI 路由（页面 + API）
  services.py    核心业务逻辑（拆分、重叠、汇总）
  models.py      SQLAlchemy 数据模型
  schemas.py     Pydantic 请求模型
  db.py          数据库引擎
  auth.py        HTTP Basic 认证
  seed.py        演示数据
  templates/     Jinja2 模板
  static/        样式
tests/           pytest 测试
Dockerfile / docker-compose.yml
```
