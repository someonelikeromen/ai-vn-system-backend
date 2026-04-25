"""
conftest.py — pytest fixtures for all integration tests
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# ── 确保 backend 在 sys.path ─────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

# ── asyncio 模式 ──────────────────────────────────────────────────────
pytest_plugins = ("pytest_asyncio",)


# ── 临时数据库 fixture ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_db_path(tmp_path_factory):
    """每次测试会话使用独立临时数据库"""
    d = tmp_path_factory.mktemp("db")
    return str(d / "test_novel.db")


@pytest_asyncio.fixture(scope="session")
async def db(tmp_db_path):
    """初始化并返回测试用数据库实例"""
    from db.models import init_db
    from db.queries import Database, init_db_instance

    await init_db(tmp_db_path)
    database = await init_db_instance(tmp_db_path)
    yield database
    await database.close()


# ── FastAPI TestClient fixture ────────────────────────────────────────

@pytest.fixture(scope="session")
def mock_llm():
    """Mock LLM client — 返回可配置的 JSON/文本响应"""
    m = MagicMock()
    m.chat = AsyncMock(return_value="Mock LLM text response")
    m.chat_json = AsyncMock(return_value={"result": "ok", "tier": 1, "tier_sub": "M"})
    m.embed = AsyncMock(return_value=[0.1] * 384)
    return m


@pytest_asyncio.fixture(scope="session")
async def app_client(tmp_db_path, mock_llm):
    """完整 FastAPI 应用的测试客户端（使用临时 DB）"""
    # 初始化 DB
    from db.models import init_db
    from db.queries import init_db_instance
    await init_db(tmp_db_path)
    await init_db_instance(tmp_db_path)

    # 注入 mock LLM
    with patch("utils.llm_client.get_llm_client", return_value=mock_llm), \
         patch("utils.llm_client.get_embedding_client", return_value=mock_llm):

        from main import app
        from httpx import AsyncClient, ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.fixture
def sync_client(tmp_db_path):
    """同步 TestClient（用于简单测试）"""
    import os
    os.environ.setdefault("DB_PATH", tmp_db_path)
    os.environ.setdefault("LLM_PROVIDER", "gemini")
    os.environ.setdefault("GEMINI_API_KEY", "test_key_mock")

    with patch("utils.llm_client.get_llm_client"), \
         patch("utils.llm_client.get_embedding_client"):
        from main import app
        with TestClient(app) as c:
            yield c
