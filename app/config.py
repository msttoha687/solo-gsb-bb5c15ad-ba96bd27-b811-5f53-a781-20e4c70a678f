"""应用配置：全部可通过环境变量覆盖。"""
import os

# SQLite 连接串，默认落在 ./data 目录（容器内为 /app/data）
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/lightquota.db")

# 管理员账号（写操作与后台页面使用 HTTP Basic 认证）
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

APP_TITLE = "纸本文物展厅光照额度管理"
