import os
import tempfile

# 必须在导入 app 之前设置，引擎与会话在导入时绑定
_fd, _db_path = tempfile.mkstemp(prefix="lightquota-test-", suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    from app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def auth():
    return ("admin", "testpass")
