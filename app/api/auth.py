"""认证接口：登录换取 JWT、当前操作员信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import BizError, CurrentOperator, get_current_operator, ok
from app.schemas.risk import LoginRequest
from app.security import authenticate, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest):
    operator = authenticate(payload.username, payload.password)
    if not operator:
        raise BizError("用户名或密码错误", 401)
    token, expires_in = create_access_token(
        operator["operator_id"], operator["role"], operator["username"]
    )
    return ok({**operator, "access_token": token, "token_type": "bearer", "expires_in": expires_in})


@router.get("/me")
def me(operator: CurrentOperator = Depends(get_current_operator)):
    return ok(
        {
            "operator_id": operator.operator_id,
            "username": operator.username,
            "role": operator.role,
        }
    )
