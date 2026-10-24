"""认证：PBKDF2 口令校验 + JWT（HS256，access_token 24h）。

风控系统内操作员账号不在 8 张业务表内（文档禁止扩展表），通过环境变量
AUTH_OPERATORS 注入，格式：username:password:role，逗号分隔。
禁止硬编码密钥：JWT_SECRET 与账号均由 .env 提供。
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


def _load_operators() -> dict[str, dict]:
    raw = settings.AUTH_OPERATORS
    operators: dict[str, dict] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            continue
        username, password, role = parts
        operators[username] = {
            "operator_id": f"OP-{username}",
            "username": username,
            "role": role,
            "password_hash": hash_password(password, salt=f"risk-agent-{username}"),
        }
    return operators


OPERATORS = _load_operators()


def authenticate(username: str, password: str) -> dict | None:
    op = OPERATORS.get(username)
    if not op or not verify_password(password, op["password_hash"]):
        return None
    return {"operator_id": op["operator_id"], "username": op["username"], "role": op["role"]}


def create_access_token(operator_id: str, role: str, username: str) -> tuple[str, int]:
    expire_seconds = settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600
    now = datetime.now(timezone.utc)
    payload = {
        "sub": operator_id,
        "role": role,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expire_seconds)).timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expire_seconds


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


__all__ = [
    "authenticate",
    "create_access_token",
    "decode_token",
    "hash_password",
    "verify_password",
    "JWTError",
]
