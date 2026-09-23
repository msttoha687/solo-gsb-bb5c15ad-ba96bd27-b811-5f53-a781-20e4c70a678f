"""管理员 HTTP Basic 认证。"""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import ADMIN_PASSWORD, ADMIN_USERNAME

security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要管理员身份认证",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
