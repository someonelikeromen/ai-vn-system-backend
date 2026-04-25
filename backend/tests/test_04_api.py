"""
test_04_api.py — FastAPI 端点集成测试（最终版，匹配实际路由）
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ── 独立应用 fixture ──────────────────────────────────────────────────
@pytest_asyncio.fixture
async def test_app():
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    os.environ["DB_PATH"] = path
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "test_mock_key"

    await init_db(path)

    mock_llm = MagicMock()
    mock_llm.chat      = AsyncMock(return_value="Mock")
    mock_llm.chat_json = AsyncMock(return_value={"result": "ok"})
    mock_llm.embed     = AsyncMock(return_value=[0.1] * 384)
    mock_embed = MagicMock()
    mock_embed.encode = MagicMock(return_value=[[0.1] * 384])

    with patch("utils.llm_client.get_llm_client",       return_value=mock_llm), \
         patch("utils.llm_client.get_embedding_client", return_value=mock_embed):

        import db.queries as dq
        db = Database(path)
        await db.connect()
        dq._db_instance = db

        # 手动触发注册（模拟 app lifespan startup）
        from config_sys.registry import ItemTypeRegistry, AttributeSchemaRegistry, BUILTIN_SCHEMAS
        from config_sys.builtin_item_types import (
            ApplicationTechniquePlugin, PassiveAbilityPlugin, PowerSourcePlugin,
            BloodlinePlugin, MechPlugin, InventoryPlugin, CompanionPlugin,
            KnowledgePlugin, WorldTraversePlugin,
        )
        for plugin_cls in [
            ApplicationTechniquePlugin, PassiveAbilityPlugin, PowerSourcePlugin,
            BloodlinePlugin, MechPlugin, InventoryPlugin, CompanionPlugin,
            KnowledgePlugin, WorldTraversePlugin,
        ]:
            try: ItemTypeRegistry.register(plugin_cls())
            except Exception: pass

        # BUILTIN_SCHEMAS 是 dict[str, AttributeSchemaConfig]
        for schema in BUILTIN_SCHEMAS.values():
            try: AttributeSchemaRegistry.register(schema)
            except Exception: pass

        from httpx import AsyncClient, ASGITransport
        from main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            yield client, db

    await db.close()
    os.unlink(path)


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

async def _create_novel(client, title="测试小说", **kwargs) -> str:
    """创建小说并返回 novel_id（处理实际响应格式 {novel:{novel_id:...}}）"""
    payload = {"title": title, **kwargs}
    r = await client.post("/api/novels/", json=payload)
    assert r.status_code in (200, 201), f"创建小说失败 {r.status_code}: {r.text[:200]}"
    data = r.json()
    # 实际响应: {"novel": {...}, "message": "..."}
    if "novel" in data:
        return data["novel"]["novel_id"]
    return data["novel_id"]  # 兼容旧格式


# ════════════════════════════════════════════════════════════════════════
# 1. 健康检查
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check(test_app):
    client, _ = test_app
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


# ════════════════════════════════════════════════════════════════════════
# 2. 小说 CRUD
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_novel(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "无限恐怖2.5R9")
    assert nid, "应返回 novel_id"


@pytest.mark.asyncio
async def test_list_novels(test_app):
    client, _ = test_app
    await _create_novel(client, "列表测试A")
    resp = await client.get("/api/novels/")
    assert resp.status_code == 200
    assert "novels" in resp.json()


@pytest.mark.asyncio
async def test_get_novel_not_found(test_app):
    client, _ = test_app
    resp = await client.get("/api/novels/nonexistent_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_novel_roundtrip(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "往返测试")
    g   = await client.get(f"/api/novels/{nid}")
    assert g.status_code == 200
    data = g.json()
    # GET /api/novels/{id} 可能返回 {title:...} 或 {novel:{title:...}} 或 {"title": ...}
    title = data.get("title") or data.get("novel", {}).get("title", "")
    assert title == "往返测试", f"标题不匹配: {data}"


# ════════════════════════════════════════════════════════════════════════
# 3. 主角初始化 & 查询
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_init_protagonist(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "主角测试")

    resp = await client.post(f"/api/novels/{nid}/init", json={"name": "吴森"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_protagonist(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "角色面板测试")
    await client.post(f"/api/novels/{nid}/init", json={"name": "李明"})

    resp = await client.get(f"/api/narrator/{nid}/protagonist")
    assert resp.status_code == 200
    data = resp.json()
    assert "protagonist" in data
    assert data["protagonist"]["name"] == "李明"
    assert "points" in data
    assert "medals" in data


# ════════════════════════════════════════════════════════════════════════
# 4. 章节 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_anchor_chapter(test_app):
    client, db = test_app
    nid = await _create_novel(client, "章节API测试")
    await db.append_message(nid, "user", "出发了")
    await db.append_message(nid, "assistant", "踏上旅途。")

    resp = await client.post(f"/api/narrator/{nid}/chapters", json={
        "chapter_title":   "第一章·出发",
        "chapter_summary": "开端",
        "arc_label":       "初期弧",
    })
    assert resp.status_code == 200
    assert "chapter_id" in resp.json()


@pytest.mark.asyncio
async def test_list_chapters(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "章节列表测试")
    await client.post(f"/api/narrator/{nid}/chapters", json={"chapter_title": "第一章"})
    await client.post(f"/api/narrator/{nid}/chapters", json={"chapter_title": "第二章"})

    resp = await client.get(f"/api/narrator/{nid}/chapters")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 2


# ════════════════════════════════════════════════════════════════════════
# 5. 配置 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_schemas(test_app):
    client, _ = test_app
    resp = await client.get("/api/config/schemas")
    assert resp.status_code == 200
    data = resp.json()
    assert "schemas" in data
    # 只验证至少有 1 个 schema（app 启动时注册）
    assert len(data["schemas"]) >= 1


@pytest.mark.asyncio
async def test_get_item_types(test_app):
    client, _ = test_app
    resp = await client.get("/api/config/item-types")
    assert resp.status_code == 200
    data = resp.json()
    assert "item_types" in data
    assert len(data["item_types"]) >= 1


# ════════════════════════════════════════════════════════════════════════
# 6. 记忆队列
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_memory_queue_stats(test_app):
    client, _ = test_app
    resp = await client.get("/api/memory/queue/stats")
    assert resp.status_code == 200
    data = resp.json()
    # 实际返回: {"novel_id":"queue","graph":{...},"vector_count":0,"queue":{...}}
    assert "queue" in data or "queue_size" in data or "stats" in data


# ════════════════════════════════════════════════════════════════════════
# 7. 兑换目录 & 战斗奖励
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_exchange_catalog(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "兑换测试")
    await client.post(f"/api/novels/{nid}/init", json={"name": "吴森"})

    resp = await client.get(f"/api/exchange/{nid}/catalog")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_combat_reward_preview(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "奖励预览")
    await client.post(f"/api/novels/{nid}/init", json={"name": "吴森"})

    resp = await client.get(
        f"/api/exchange/{nid}/rewards/combat",
        params={"enemy_tier": 2, "enemy_tier_sub": "M", "kill_type": "defeat"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "enemy_tier" in data
    assert "preview_points" in data
    assert data["preview_points"] > 0


# ════════════════════════════════════════════════════════════════════════
# 8. 伏笔 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_hooks_empty(test_app):
    client, _ = test_app
    nid = await _create_novel(client, "伏笔测试")

    resp = await client.get(f"/api/narrator/{nid}/hooks")
    assert resp.status_code == 200
    data = resp.json()
    assert "hooks" in data
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_get_hooks_with_data(test_app):
    client, db = test_app
    nid = await _create_novel(client, "伏笔内容测试")

    await db.register_hook(nid, "陌生黑衣人", urgency="high")
    await db.register_hook(nid, "匣子底部符文", urgency="low")

    resp = await client.get(f"/api/narrator/{nid}/hooks")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
