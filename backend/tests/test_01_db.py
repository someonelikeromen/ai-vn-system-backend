"""
test_01_db.py — 数据库层集成测试
- Schema 完整性（所有表存在）
- 基础 CRUD（小说/主角/章节/世界档案）
- 并发安全（乐观锁 CAS）
- 事务完整性
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import pytest
import pytest_asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ── 独立 DB 实例（不依赖全局 conftest.db，避免并发影响） ──────────────

@pytest_asyncio.fixture
async def fresh_db():
    """每个测试用例独立的数据库"""
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    db = Database(path)
    await db.connect()
    yield db
    await db.close()
    os.unlink(path)


# ════════════════════════════════════════════════════════════════════════
# 1. Schema 完整性
# ════════════════════════════════════════════════════════════════════════

EXPECTED_TABLES = [
    "novels", "protagonist_state", "medals", "item_catalog", "owned_items",
    "exchange_log", "rollback_manifests", "growth_records", "growth_event_records",
    "kill_records", "node_sync_status", "chapters", "narrative_hooks",
    "achievements", "world_archives", "npc_profiles", "messages",
]

@pytest.mark.asyncio
async def test_all_tables_exist(fresh_db):
    """验证所有必要的表都已创建"""
    rows = await fresh_db._fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    existing = {r["name"] for r in rows}
    for table in EXPECTED_TABLES:
        assert table in existing, f"Missing table: {table}"


@pytest.mark.asyncio
async def test_world_archives_has_catalog_json(fresh_db):
    """验证 world_archives.catalog_json 列存在"""
    rows = await fresh_db._fetchall("PRAGMA table_info(world_archives)")
    cols = {r["name"] for r in rows}
    assert "catalog_json" in cols, "world_archives.catalog_json column missing"


@pytest.mark.asyncio
async def test_chapters_has_arc_label(fresh_db):
    """验证 chapters.arc_label 列存在"""
    rows = await fresh_db._fetchall("PRAGMA table_info(chapters)")
    cols = {r["name"] for r in rows}
    assert "arc_label" in cols, "chapters.arc_label column missing"


@pytest.mark.asyncio
async def test_owned_items_has_item_name(fresh_db):
    """验证 owned_items 新增字段存在"""
    rows = await fresh_db._fetchall("PRAGMA table_info(owned_items)")
    cols = {r["name"] for r in rows}
    for col in ("item_name", "source_world", "final_tier", "final_sub"):
        assert col in cols, f"owned_items.{col} column missing"


# ════════════════════════════════════════════════════════════════════════
# 2. 小说 CRUD
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_novel_create_and_get(fresh_db):
    """创建小说 → 查询 → 验证字段"""
    nid = await fresh_db.create_novel(
        title="测试小说", ip_type="original",
        world_type="multi_world", attr_schema_id="standard_10d"
    )
    assert nid, "应返回 novel_id"

    novel = await fresh_db.get_novel(nid)
    assert novel is not None
    assert novel["title"] == "测试小说"
    assert novel["world_type"] == "multi_world"
    assert novel["archived"] == 0


@pytest.mark.asyncio
async def test_novel_list(fresh_db):
    """列表功能"""
    await fresh_db.create_novel(title="小说A")
    await fresh_db.create_novel(title="小说B")
    novels = await fresh_db.list_novels()
    assert len(novels) >= 2


@pytest.mark.asyncio
async def test_novel_update(fresh_db):
    """更新小说字段"""
    nid = await fresh_db.create_novel(title="原标题")
    await fresh_db.update_novel(nid, title="新标题")
    novel = await fresh_db.get_novel(nid)
    assert novel["title"] == "新标题"


# ════════════════════════════════════════════════════════════════════════
# 3. 主角状态
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_protagonist_init_and_get(fresh_db):
    """初始化主角 → 读取验证"""
    nid = await fresh_db.create_novel(title="主角测试小说")
    await fresh_db.init_protagonist(nid, name="吴森", world_key="", attr_schema_id="standard_10d")

    p = await fresh_db.get_protagonist_state(nid)
    assert p is not None
    assert p["name"] == "吴森"
    assert p["points"] == 0
    assert p["tier"] == 0
    assert isinstance(p["attributes"], dict)
    assert "STR" in p["attributes"]


@pytest.mark.asyncio
async def test_add_points(fresh_db):
    """积分增减"""
    nid = await fresh_db.create_novel(title="积分测试")
    await fresh_db.init_protagonist(nid, name="吴森")

    new_pts = await fresh_db.add_points(nid, 5000)
    assert new_pts == 5000

    new_pts2 = await fresh_db.add_points(nid, -1000)
    assert new_pts2 == 4000


@pytest.mark.asyncio
async def test_add_medal(fresh_db):
    """凭证接口"""
    nid = await fresh_db.create_novel(title="凭证测试")
    await fresh_db.init_protagonist(nid, name="吴森")

    await fresh_db.add_medal(nid, stars=1, count=5)
    count = await fresh_db.get_medal_count(nid, stars=1)
    assert count == 5

    await fresh_db.add_medal(nid, stars=1, count=3)
    count2 = await fresh_db.get_medal_count(nid, stars=1)
    assert count2 == 8


# ════════════════════════════════════════════════════════════════════════
# 4. 章节系统
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_and_list_chapters(fresh_db):
    """章节创建和列表"""
    nid = await fresh_db.create_novel(title="章节测试")
    ch_id = await fresh_db.create_chapter(
        novel_id=nid, title="第一章", summary="开端", arc_label="初期弧"
    )
    assert ch_id, "should return chapter_id"

    chapters = await fresh_db.list_chapters(nid)
    assert len(chapters) == 1
    assert chapters[0]["title"] == "第一章"


@pytest.mark.asyncio
async def test_delete_chapter(fresh_db):
    """章节删除"""
    nid = await fresh_db.create_novel(title="删除测试")
    ch_id = await fresh_db.create_chapter(nid, title="待删章节")
    await fresh_db.delete_chapter(nid, ch_id)
    chapters = await fresh_db.list_chapters(nid)
    assert all(c["id"] != ch_id for c in chapters)


# ════════════════════════════════════════════════════════════════════════
# 5. 世界档案 & 兑换目录缓存
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_world_catalog_cache(fresh_db):
    """世界兑换目录缓存写入/读取/清除"""
    nid = await fresh_db.create_novel(title="世界测试")
    world_key = "fate_world"
    items = [{"item_key": "excalibur", "item_name": "誓约胜利之剑", "item_type": "ApplicationTechnique"}]

    # 写入
    await fresh_db.upsert_world_catalog(nid, world_key, items)

    # 读取
    cached = await fresh_db.get_world_catalog(nid, world_key)
    assert len(cached) == 1
    assert cached[0]["item_key"] == "excalibur"

    # 清除
    await fresh_db.clear_world_catalog(nid, world_key)
    empty = await fresh_db.get_world_catalog(nid, world_key)
    assert empty == []


# ════════════════════════════════════════════════════════════════════════
# 6. 成长系统 — 乐观锁 CAS
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_growth_optimistic_lock(fresh_db):
    """CAS 乐观锁正确性"""
    nid     = await fresh_db.create_novel(title="成长测试")
    await fresh_db.init_protagonist(nid, name="吴森")

    # 模拟 owned_item 插入（跳过 FK 约束）
    import uuid, json
    owned_id = str(uuid.uuid4())
    await fresh_db._exec(
        "INSERT INTO owned_items (id,novel_id,item_key,item_name,item_type,payload) "
        "VALUES (?,?,?,?,?,?)",
        (owned_id, nid, "test_skill", "测试技能", "ApplicationTechnique", "{}"),
    )

    await fresh_db.init_growth_record(nid, owned_id, "破天指")
    rec0 = await fresh_db.get_growth_record(nid, owned_id, "破天指")
    assert rec0["version"] == 0
    assert rec0["current_xp"] == 0

    # 正常 CAS
    n = await fresh_db.compare_and_swap_growth_record(
        nid, owned_id, "破天指", None,
        new_xp=100, new_level_idx=0, expected_version=0
    )
    assert n == 1, "CAS 应成功"

    rec1 = await fresh_db.get_growth_record(nid, owned_id, "破天指")
    assert rec1["current_xp"] == 100
    assert rec1["version"] == 1

    # 版本冲突 CAS（应该失败）
    n_fail = await fresh_db.compare_and_swap_growth_record(
        nid, owned_id, "破天指", None,
        new_xp=999, new_level_idx=0, expected_version=0  # 旧版本号
    )
    assert n_fail == 0, "版本冲突的 CAS 不应成功"


# ════════════════════════════════════════════════════════════════════════
# 7. 消息历史
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_messages_append_and_get(fresh_db):
    """消息历史追加与查询"""
    nid = await fresh_db.create_novel(title="消息测试")
    msg1 = await fresh_db.append_message(nid, "user", "我要攻打城门！")
    msg2 = await fresh_db.append_message(nid, "assistant", "城门在一百米外轰然倒塌。")

    msgs = await fresh_db.get_messages(nid, limit=10)
    assert len(msgs) == 2, f"应有2条消息，实际 {len(msgs)}"


# ════════════════════════════════════════════════════════════════════════
# 8. Kill 记录
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_kill_record_upsert(fresh_db):
    """击杀记录 upsert"""
    nid = await fresh_db.create_novel(title="击杀测试")
    cat = "tier2_skeleton"

    rec = await fresh_db.get_kill_record(nid, cat)
    assert rec is None

    await fresh_db.upsert_kill_record(nid, cat, {
        "enemy_tier": 2, "enemy_tier_sub": "M", "kill_count": 1, "defeat_count": 0,
        "points_decay_stage": 0, "medal_decay_stage": 0,
    })

    rec2 = await fresh_db.get_kill_record(nid, cat)
    assert rec2 is not None
    assert rec2["kill_count"] == 1


# ════════════════════════════════════════════════════════════════════════
# 9. 伏笔系统
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hooks(fresh_db):
    """伏笔注册和查询"""
    nid = await fresh_db.create_novel(title="伏笔测试")

    hid1 = await fresh_db.register_hook(nid, "神秘机构暗中观察主角", urgency="high")
    hid2 = await fresh_db.register_hook(nid, "破旧符文的秘密", urgency="low")

    hooks = await fresh_db.get_active_hooks(nid)
    ids = {h["id"] for h in hooks}
    assert hid1 in ids
    assert hid2 in ids
    # high urgency 应排在 low 之前
    assert hooks[0]["urgency"] == "high"
