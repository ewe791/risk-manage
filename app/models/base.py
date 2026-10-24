"""模型公共组件：可移植 JSONB 类型、主键生成、时间基准。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base  # noqa: F401  统一从 database 暴露 Base

# PostgreSQL 使用 JSONB，SQLite 降级为 JSON；模型层与迁移层共用同一表达式
JSONType = JSON().with_variant(JSONB(astext_type=None), "postgresql")


class UTCDateTime(TypeDecorator):
    """统一 UTC 时间列：写入补 UTC，读出保证 tz-aware。

    SQLite 不保存时区，读回是 naive datetime，序列化后缺 "Z"，
    前端按本地时间解析会差 8 小时；在类型层修正，避免逐个接口处理。
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


# 统一带时区时间列类型（UTC 存储）
TS = UTCDateTime()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gen_id(prefix: str) -> str:
    """业务可读主键，例如 RA-3f9a1c2b。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


__all__ = ["Base", "JSONType", "TS", "utcnow", "gen_id"]
