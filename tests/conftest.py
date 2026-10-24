"""pytest 全局配置：使用独立测试库，避免污染开发库。"""

from __future__ import annotations

import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parents[1] / "test_risk_agent.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ.setdefault("UPSTREAM_DATA_DIR", "./seed")

if TEST_DB.exists():
    TEST_DB.unlink()
