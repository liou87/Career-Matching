"""
测试环境：
- 每次测试会话用一个临时 SQLite 库，用 Alembic 迁移建表，顺带验证迁移本身可用
- LLM 指向一个连不上的地址：哪个测试忘了替换真实的 LLM 调用，会立刻失败，
  不会在 CI 里悄悄花钱
- 环境变量必须在 import app 之前设好，所以放在文件最前面
"""
import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="careermatch-test-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP_DIR / 'test.db'}",
    "ACCESS_TOKEN": "",
    "LLM_API_KEY": "test-key",
    "LLM_BASE_URL": "http://127.0.0.1:9",
    "LLM_MAX_RETRIES": "0",
    "LLM_TIMEOUT": "2",
    # 本地 .env 里可能配了 embedding 的 Key，测试里一律关掉，避免真实调用；
    # 向量一路的测试用假 embedding（tests/test_retrieval.py）
    "EMBEDDING_API_KEY": "",
    "SILICONFLOW_API_KEY": "",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    from app.db.session import Base, engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)
