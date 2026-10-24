"""FastAPI 通用依赖：JWT 解析、统一响应封装、异常类型。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import JWTError, decode_token


class BizError(Exception):
    """业务异常：由全局处理器转成 {code, message, data}。"""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


class CurrentOperator:
    def __init__(self, operator_id: str, username: str, role: str):
        self.operator_id = operator_id
        self.username = username
        self.role = role

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Operator {self.operator_id} role={self.role}>"


def get_current_operator(authorization: str | None = Header(default=None)) -> CurrentOperator:
    """从 Authorization: Bearer <token> 解析操作员；operator_id 由后端注入，LLM 不可指定。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return CurrentOperator(
        operator_id=payload.get("sub", ""),
        username=payload.get("username", ""),
        role=payload.get("role", ""),
    )


def require_roles(*allowed: str):
    """角色校验依赖：admin 拥有全部权限，其余角色需显式列入 allowed。

    文档 2.3.2 三类角色：
      - 风控审核员 reviewer：查风险、审案件、填处理结论
      - 风控管理员 admin：维护规则/黑名单、看板
      - 数据查看人 viewer：只读（画像、历史风险记录、命中统计）
    """

    def _dependency(operator: CurrentOperator = Depends(get_current_operator)) -> CurrentOperator:
        if operator.role == "admin" or operator.role in allowed:
            return operator
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"当前角色（{operator.role}）无该操作权限，需要 {sorted({'admin', *allowed})}",
        )

    return _dependency


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(message: str, code: int = 400) -> dict:
    return {"code": code, "message": message, "data": None}


def paginate(items: list, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


__all__ = [
    "BizError",
    "CurrentOperator",
    "get_current_operator",
    "require_roles",
    "get_db",
    "ok",
    "fail",
    "paginate",
    "Session",
    "Depends",
]
