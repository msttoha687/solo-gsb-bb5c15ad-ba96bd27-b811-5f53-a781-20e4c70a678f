# 纸本文物展厅光照额度管理

面向纸本文物展厅的光照额度管理 Web 应用。管理员可登记藏品的**年度光照额度**（lux·小时）与**展陈记录**（起止时间、平均照度），系统按 lux·小时累计有效暴露、计算剩余额度并标出超额藏品。

## 功能特性

- 藏品管理：登记/修改/删除藏品及其年度光照额度
- 展陈记录：登记起止时间与平均照度，自动计算暴露量（lux·h）
- **跨年拆分**：跨自然年的记录按年界（1 月 1 日 00:00）拆分，分别计入各年
- **重叠拒绝**：同一藏品时间重叠的记录拒绝保存（HTTP 409）；首尾相接不算重叠
- 年度汇总：按年统计各藏品已用/剩余额度，超额藏品红色标记并置顶
- 交互式 API 文档：FastAPI 自动生成（`/docs`）

## 快速开始（Docker Compose，一键启动）

```bash
docker compose up --build
```

访问：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000 | 管理界面 |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8000/api/health | 健康检查 |

数据持久化在名为 `light-data` 的 Docker volume 中（容器内路径 `/data/light_budget.db`）。

## 本地开发

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

运行测试：

```bash
pytest -v
```

## 配置

通过环境变量配置（`docker-compose.yml` 中已设置）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_PATH` | 容器内 `/data/light_budget.db`；本地 `./data/light_budget.db` | SQLite 数据库文件路径 |
| `PORT`（启动参数） | `8000` | 服务端口，Compose 中映射为主机 `8000:8000` |

时间约定：界面与 API 均接受 ISO 8601 时间；不带时区按本地时间处理，带时区的输入会统一转换为 UTC 后存储。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/artifacts` | 登记藏品（名称、年度额度） |
| GET | `/api/artifacts` | 藏品列表 |
| PUT / DELETE | `/api/artifacts/{id}` | 修改 / 删除藏品（级联删除记录） |
| POST | `/api/artifacts/{id}/exhibitions` | 登记展陈记录（重叠返回 409） |
| GET | `/api/artifacts/{id}/exhibitions` | 某藏品的展陈记录（含跨年拆分结果） |
| DELETE | `/api/exhibitions/{id}` | 删除展陈记录 |
| GET | `/api/artifacts/{id}/summary?year=YYYY` | 单藏品年度额度使用情况 |
| GET | `/api/summary?year=YYYY` | 全部藏品年度汇总，标出超额（`over_budget`） |

### 示例

```bash
# 登记藏品：年度额度 15000 lux·h
curl -X POST http://localhost:8000/api/artifacts \
  -H 'Content-Type: application/json' \
  -d '{"name": "宋版《史记》残卷", "annual_budget_lux_hours": 15000}'

# 登记跨年展陈记录：自动拆分计入 2025 / 2026 两年
curl -X POST http://localhost:8000/api/artifacts/1/exhibitions \
  -H 'Content-Type: application/json' \
  -d '{"start_time": "2025-12-31T20:00:00", "end_time": "2026-01-01T04:00:00", "avg_lux": 50}'

# 查看 2026 年度汇总（超额藏品会标记 over_budget: true）
curl 'http://localhost:8000/api/summary?year=2026'
```

## 技术栈与结构

Python 3.12 · FastAPI · SQLite（单文件，无需外部服务）

```
app/
  main.py       # FastAPI 路由与汇总接口
  logic.py      # 跨年拆分、重叠检测、年度暴露累计
  database.py   # SQLite 连接与建表
  schemas.py    # 请求校验模型
  static/index.html  # 管理界面（原生 JS 单页）
tests/test_app.py    # pytest 接口与逻辑测试
Dockerfile / docker-compose.yml
```
