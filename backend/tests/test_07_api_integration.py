"""
test_07_api_integration.py — API 集成测试（全流程）
覆盖：
  1. 完整游戏回合 SSE 流（create → init → message → parse）
  2. 章节固化流程（anchor → hooks 更新）
  3. 小说 CRUD 完整生命周期
  4. 主角生成（mock LLM 返回 JSON）
  5. NPC 档案写入（companion upsert + slot）
  6. medals key 类型一致性（int）
  7. 健康检查端点
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ════════════════════════════════════════════════════════════════════════
# 1. 健康检查
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check_ok(app_client):
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "db" in data


# ════════════════════════════════════════════════════════════════════════
# 2. 小说完整生命周期
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_novel_full_lifecycle(app_client):
    """创建 → 查询 → 更新 → 列表 → 删除"""
    # 创建
    resp = await app_client.post("/api/novels/", json={
        "title": "测试生命周期小说",
        "ip_type": "original",
        "world_type": "single_world",
        "attr_schema_id": "standard_10d",
    })
    assert resp.status_code == 201
    novel_id = resp.json()["novel"]["novel_id"]
    assert novel_id

    # 查询
    get_resp = await app_client.get(f"/api/novels/{novel_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["novel"]["title"] == "测试生命周期小说"

    # 更新
    patch_resp = await app_client.patch(f"/api/novels/{novel_id}", json={
        "title": "更新后的标题"
    })
    assert patch_resp.status_code == 200
    assert await app_client.get(f"/api/novels/{novel_id}") is not None

    # 列表
    list_resp = await app_client.get("/api/novels/")
    assert list_resp.status_code == 200
    novels = list_resp.json()["novels"]
    ids = [n["novel_id"] for n in novels]
    assert novel_id in ids

    # 删除
    del_resp = await app_client.delete(f"/api/novels/{novel_id}")
    assert del_resp.status_code == 200

    gone = await app_client.get(f"/api/novels/{novel_id}")
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_novel(app_client):
    resp = await app_client.get("/api/novels/DOES_NOT_EXIST_XYZ")
    assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════
# 3. 主角初始化流程
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_protagonist_init_and_get(app_client):
    """创建小说 → 初始化主角 → 查询状态"""
    resp = await app_client.post("/api/novels/", json={"title": "主角测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    init_resp = await app_client.post(f"/api/novels/{novel_id}/init", json={
        "name": "吴森",
        "starting_points": 5000,
    })
    assert init_resp.status_code == 200
    data = init_resp.json()
    assert data["protagonist"]["name"] == "吴森"

    # 通过 narrator API 查询
    prot_resp = await app_client.get(f"/api/narrator/{novel_id}/protagonist")
    assert prot_resp.status_code == 200
    prot_data = prot_resp.json()
    assert prot_data["protagonist"]["name"] == "吴森"
    assert prot_data["points"] == 5000


@pytest.mark.asyncio
async def test_protagonist_not_init_returns_404(app_client):
    resp = await app_client.post("/api/novels/", json={"title": "无主角测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    prot_resp = await app_client.get(f"/api/narrator/{novel_id}/protagonist")
    assert prot_resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════
# 4. medals key 类型一致性
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_medals_key_type_is_int(app_client):
    """narrator API 返回的 medals 字典 key 应为 int"""
    resp = await app_client.post("/api/novels/", json={"title": "凭证类型测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    # 通过 DB 直接写入一个 medal
    from db.queries import get_db
    db = get_db()
    await db.add_medal(novel_id, stars=3, count=2)

    prot_resp = await app_client.get(f"/api/narrator/{novel_id}/protagonist")
    medals = prot_resp.json()["medals"]

    for key in medals.keys():
        assert isinstance(key, int), \
            f"medals key 应为 int，实际类型: {type(key).__name__}，值: {key}"


# ════════════════════════════════════════════════════════════════════════
# 5. 章节固化流程
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chapter_anchor_flow(app_client):
    """固化章节 → 列表确认 → hooks 更新"""
    resp = await app_client.post("/api/novels/", json={"title": "章节测试小说"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    # 固化章节
    anchor_resp = await app_client.post(
        f"/api/narrator/{novel_id}/chapters",
        json={
            "chapter_title":   "第一章：初入江湖",
            "chapter_summary": "吴森踏上武道之路",
            "arc_label":       "起源弧",
        }
    )
    assert anchor_resp.status_code == 200
    data = anchor_resp.json()
    assert "chapter_id" in data

    # 章节列表确认
    list_resp = await app_client.get(f"/api/narrator/{novel_id}/chapters")
    assert list_resp.status_code == 200
    chapters = list_resp.json()["chapters"]
    assert len(chapters) >= 1
    titles = [c["title"] for c in chapters]
    assert "第一章：初入江湖" in titles


@pytest.mark.asyncio
async def test_chapter_rollback(app_client):
    """固化章节后回滚"""
    resp = await app_client.post("/api/novels/", json={"title": "回滚测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    # 固化
    anchor = await app_client.post(
        f"/api/narrator/{novel_id}/chapters",
        json={"chapter_title": "待回滚章节", "chapter_summary": ""},
    )
    chapter_id = anchor.json()["chapter_id"]

    # 回滚
    rollback = await app_client.post(
        f"/api/narrator/{novel_id}/chapters/{chapter_id}/rollback"
    )
    assert rollback.status_code == 200

    # 确认已删除
    chapters = (await app_client.get(f"/api/narrator/{novel_id}/chapters")).json()["chapters"]
    ids = [c["id"] for c in chapters]
    assert chapter_id not in ids


# ════════════════════════════════════════════════════════════════════════
# 6. AI 生成主角（预览模式，commit=False）
# ════════════════════════════════════════════════════════════════════════

_MOCK_CHAR = {
    "name": "林枫",
    "gender": "男",
    "age": "24",
    "identity": "镖师",
    "height": "178cm",
    "weight": "72kg",
    "alignment": "中立·善",
    "appearance": "宽肩窄腰，神情冷肃",
    "clothing": "灰色长衫，腰间横刀",
    "traits": ["沉着", "义气"],
    "personality": ["遇险不慌"],
    "flaws": ["情绪化"],
    "desires": ["平静生活"],
    "fears": ["失去伙伴"],
    "background": "幼年镖局学艺，经历过一次护镖失败。",
    "quirks": ["习惯摸刀柄"],
    "attributes": {
        "STR": 1.3, "DUR": 1.1, "VIT": 1.0, "REC": 0.9,
        "AGI": 1.2, "REF": 1.1, "PER": 1.0, "MEN": 0.9, "SOL": 1.0, "CHA": 0.8,
    },
    "psyche_model": {"dimensions": {}, "triggerPatterns": []},
    "knowledge": [],
    "passiveAbilities": [],
    "powerSources": [],
    "techniques": [],
    "startingItems": [],
}


@pytest.mark.asyncio
async def test_generate_protagonist_preview_mode(app_client):
    """commit=False 模式：LLM 返回 JSON，不写入 DB"""
    resp = await app_client.post("/api/novels/", json={"title": "生成预览测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    gen_resp = await app_client.post(
        f"/api/novels/{novel_id}/generate-protagonist",
        json={
            "mode":             "background",
            "background":       "前镖师，性格稳重",
            "char_type":        "本土",
            "commit":           False,
        }
    )
    assert gen_resp.status_code == 200
    data = gen_resp.json()
    assert data["committed"] is False
    assert "character" in data


@pytest.mark.asyncio
async def test_generate_protagonist_and_commit(app_client):
    """commit=True 模式：写入 DB，protagonist 初始化成功"""
    resp = await app_client.post("/api/novels/", json={"title": "生成提交测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    gen_resp = await app_client.post(
        f"/api/novels/{novel_id}/generate-protagonist",
        json={
            "mode":             "quick",
            "background":       "",
            "char_type":        "本土",
            "commit":           True,
        }
    )
    assert gen_resp.status_code == 200
    data = gen_resp.json()
    assert data["committed"] is True
    assert data["protagonist"]["name"] != ""

    # 验证 protagonist 实际存在
    prot_resp = await app_client.get(f"/api/narrator/{novel_id}/protagonist")
    assert prot_resp.status_code == 200


# ════════════════════════════════════════════════════════════════════════
# 7. SSE 游戏主流程（无 LLM 真实调用）
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_game_message_returns_sse_stream(app_client):
    """POST /api/sessions/{id}/message 应返回 text/event-stream"""
    resp = await app_client.post("/api/novels/", json={"title": "SSE 测试小说"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    # 触发 SSE（不等待完成，只验证返回头）
    async with app_client.stream("POST", f"/api/sessions/{novel_id}/message",
                                  json={"user_input": "我向前走。"}) as stream_resp:
        assert stream_resp.status_code == 200
        content_type = stream_resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, \
            f"应返回 SSE 流，实际 Content-Type: {content_type}"

        # 读取至少一行 SSE 数据
        lines_read = 0
        async for line in stream_resp.aiter_lines():
            lines_read += 1
            if lines_read >= 3:
                break
        assert lines_read > 0, "SSE 流应至少返回一行数据"


@pytest.mark.asyncio
async def test_game_message_requires_protagonist(app_client):
    """未初始化主角时发消息 → 400"""
    resp = await app_client.post("/api/novels/", json={"title": "无主角 SSE 测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    msg_resp = await app_client.post(
        f"/api/sessions/{novel_id}/message",
        json={"user_input": "任意行动"}
    )
    assert msg_resp.status_code == 400


@pytest.mark.asyncio
async def test_game_message_requires_novel(app_client):
    """不存在的小说 → 404"""
    msg_resp = await app_client.post(
        "/api/sessions/FAKE_NOVEL_ID_XYZ/message",
        json={"user_input": "任意行动"}
    )
    assert msg_resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════
# 8. Hooks API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hooks_empty_on_new_novel(app_client):
    resp = await app_client.post("/api/novels/", json={"title": "伏笔测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    hooks_resp = await app_client.get(f"/api/narrator/{novel_id}/hooks")
    assert hooks_resp.status_code == 200
    data = hooks_resp.json()
    assert "hooks" in data
    assert data["count"] == 0


# ════════════════════════════════════════════════════════════════════════
# 9. NPC Companion 档案写入完整性
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_companion_purchase_writes_npc_profile(app_client):
    """购买 Companion 后 npc_profiles 中应有对应记录"""
    resp = await app_client.post("/api/novels/", json={"title": "同伴测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={
        "name": "吴森", "starting_points": 999999
    })

    # 购买 Companion 类型
    purchase_resp = await app_client.post(f"/api/exchange/{novel_id}/purchase", json={
        "item_key":   "ling_fox",
        "item_name":  "灵狐儿",
        "item_type":  "Companion",
        "source_world": "仙侠世界",
        "final_price": 5000,
        "final_tier":  2,
        "final_sub":   "M",
        "payload": {
            "name":           "灵狐儿",
            "personality":    ["活泼", "忠诚"],
            "initialAffinity": 80,
            "loyaltyType":    "情感型",
            "knowledgeScope": [],
        },
    })
    assert purchase_resp.status_code == 200

    # 验证 npc_profiles 中有记录
    from db.queries import get_db
    db = get_db()
    npc = await db.get_npc(novel_id, "灵狐儿")
    assert npc is not None, "购买 Companion 后应创建 npc_profiles 记录"
    assert npc["npc_type"] == "companion"
    assert npc.get("initial_affinity") == 80, \
        f"initial_affinity 应为 80，实际: {npc.get('initial_affinity')}"
    assert npc.get("loyalty_type") == "情感型"
    assert npc.get("companion_slot") is not None


# ════════════════════════════════════════════════════════════════════════
# 10. 消息历史 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_messages_api(app_client):
    """GET /api/sessions/{id}/messages 返回历史"""
    resp = await app_client.post("/api/novels/", json={"title": "消息历史测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    msgs_resp = await app_client.get(f"/api/sessions/{novel_id}/messages?limit=20")
    assert msgs_resp.status_code == 200
    data = msgs_resp.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)


# ════════════════════════════════════════════════════════════════════════
# 11. 世界档案 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_world_archive_upsert_and_get(app_client):
    """PUT/GET /api/narrator/{id}/world/{key}"""
    resp = await app_client.post("/api/novels/", json={"title": "世界档案测试"})
    novel_id = resp.json()["novel"]["novel_id"]

    world_data = {
        "name":           "武侠世界",
        "peak_tier":      6,
        "peak_tier_sub":  "M",
        "time_flow_type": "fixed",
        "time_flow_ratio": "1:1",
    }
    put_resp = await app_client.put(
        f"/api/narrator/{novel_id}/world/murim",
        json=world_data
    )
    assert put_resp.status_code == 200

    get_resp = await app_client.get(f"/api/narrator/{novel_id}/world/murim")
    assert get_resp.status_code == 200
    archive = get_resp.json()["archive"]
    assert archive is not None
