"""全局配置：统一从 .env 读取，禁止硬编码密钥。"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    APP_NAME: str = "电商风控智能助手"
    APP_VERSION: str = "1.0.0"

    # 数据库（PG 为生产基准，SQLite 本地降级）
    DATABASE_URL: str = "sqlite:///./risk_agent.db"

    # Redis（为空则使用进程内缓存）
    REDIS_URL: str = ""
    CONVERSATION_TTL_SECONDS: int = 86400

    # LLM
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-flash"
    LLM_TIMEOUT_SECONDS: int = 90
    LLM_TEMPERATURE: float = 0.2

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24

    # 操作员账号（8 张业务表之外的身份数据，由环境注入，格式 user:pass:role）
    AUTH_OPERATORS: str = (
        "admin:Admin@12345:admin,"
        "reviewer:Reviewer@12345:reviewer,"
        "viewer:Viewer@12345:viewer"
    )

    # 上游业务数据（Mock 订单/用户服务）
    UPSTREAM_DATA_DIR: str = "./seed"

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Agent
    AGENT_MAX_STEPS: int = 8
    AGENT_HISTORY_LIMIT: int = 20

    @field_validator("LLM_BASE_URL")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
