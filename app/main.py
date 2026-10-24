"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --reload --port 8000
文档：
    /docs      OpenAPI
    /api/health 健康检查
前端构建产物存在时（frontend/dist）自动挂载到 /，实现单端口演示。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import agent as agent_api
from app.api import auth as auth_api
from app.api import risk as risk_api
from app.config import settings
from app.database import Base, engine
from app.deps import BizError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("risk_agent")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="电商风险控制系统 —— 规则引擎 + 特征计算 + 决策建案 + 风控 Agent",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # 本地 SQLite 便捷建表；生产 PostgreSQL 请使用 alembic upgrade head
    import app.models  # noqa: F401  确保模型注册到 metadata

    Base.metadata.create_all(bind=engine)
    logger.info("database ready: %s", settings.DATABASE_URL.split("@")[-1])


@app.exception_handler(BizError)
async def biz_error_handler(_request: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(status_code=200, content={"code": exc.code, "message": exc.message, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(
        status_code=200,
        content={
            "code": 422,
            "message": f"参数校验失败 {loc}: {first.get('msg', '')}".strip(),
            "data": None,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


app.include_router(auth_api.router)
app.include_router(risk_api.router)
app.include_router(agent_api.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "llm_model": settings.LLM_MODEL,
            "llm_base_url": settings.LLM_BASE_URL,
            "database": settings.DATABASE_URL.split("://")[0],
        },
    }


# 前端静态资源（构建后单端口访问）
_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
    logger.info("frontend mounted: %s", _dist)
