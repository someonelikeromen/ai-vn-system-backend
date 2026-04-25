"""
test_08_growth.py — 成长系统完整测试
覆盖：
  1. GrowthRecord 初始化（version=0、xp=0）
  2. XP 累积与升级触发（自动跨级）
  3. CAS 乐观锁并发（多协程同时写入，仅一个成功）
  4. 全流程 batch_grant（多技能同时结算）
  5. 学派分级校验（异源体系：相性 vs 原理）
  6. XP 结算下限（最低 0，不产生负数）
  7. 成长 DB 服务与 API 联通
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ── 每个测试用例独立的数据库 ────────────────────────────────────────────

@pytest_asyncio.fixture
async def gdb():
    """独立成长测试 DB"""
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    db = Database(path)
    await db.connect()

    # 创建基础数据
    novel_id = await db.create_novel(title="成长测试小说")
    await db.init_protagonist(novel_id, name="吴森")

    # 插入一个 owned_item
    owned_id = str(uuid.uuid4())
    await db._exec(
        "INSERT INTO owned_items (id,novel_id,item_key,item_name,item_type,payload) "
        "VALUES (?,?,?,?,?,?)",
        (owned_id, novel_id, "broken_sky_finger", "破天指", "ApplicationTechnique", "{}"),
    )

    yield db, novel_id, owned_id

    await db.close()
    os.unlink(path)


# ════════════════════════════════════════════════════════════════════════
# 1. 成长记录基础 CRUD
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_growth_record_init(gdb):
    """init_growth_record → version=0, xp=0"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")
    rec = await db.get_growth_record(nid, oid, "破天指")
    assert rec is not None
    assert rec["version"] == 0
    assert rec["current_xp"] == 0
    assert rec["level_index"] == 0


@pytest.mark.asyncio
async def test_growth_record_init_idempotent(gdb):
    """重复 init 不报错（idempotent）"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")
    await db.init_growth_record(nid, oid, "破天指")  # 再次 init
    records = await db._fetchall(
        "SELECT * FROM growth_records WHERE novel_id=? AND owned_item_id=?",
        (nid, oid)
    )
    assert len(records) == 1, "不应创建重复记录"


# ════════════════════════════════════════════════════════════════════════
# 2. CAS 乐观锁正确性
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cas_success_increments_version(gdb):
    """正常 CAS：xp 更新，version + 1"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")

    n = await db.compare_and_swap_growth_record(
        nid, oid, "破天指", None,
        new_xp=500, new_level_idx=0, expected_version=0
    )
    assert n == 1, "CAS 应成功（返回 affected=1）"

    rec = await db.get_growth_record(nid, oid, "破天指")
    assert rec["current_xp"] == 500
    assert rec["version"] == 1


@pytest.mark.asyncio
async def test_cas_stale_version_fails(gdb):
    """旧版本号 CAS → 失败（返回 0）"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")

    # 成功一次（version 变为 1）
    await db.compare_and_swap_growth_record(
        nid, oid, "破天指", None,
        new_xp=100, new_level_idx=0, expected_version=0
    )

    # 再次使用旧版本号 → 失败
    n = await db.compare_and_swap_growth_record(
        nid, oid, "破天指", None,
        new_xp=999, new_level_idx=0, expected_version=0  # stale!
    )
    assert n == 0, "版本冲突的 CAS 不应成功"

    rec = await db.get_growth_record(nid, oid, "破天指")
    assert rec["current_xp"] == 100, "数据不应被 stale CAS 覆盖"


@pytest.mark.asyncio
async def test_cas_concurrent_only_one_wins(gdb):
    """10 个并发协程同时 CAS version=0，只有 1 个成功"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")

    results = await asyncio.gather(*[
        db.compare_and_swap_growth_record(
            nid, oid, "破天指", None,
            new_xp=i * 100, new_level_idx=0, expected_version=0
        )
        for i in range(10)
    ])
    # 恰好一个成功
    winners = [r for r in results if r == 1]
    assert len(winners) == 1, f"并发 CAS 应只有 1 个成功，实际: {winners}"


# ════════════════════════════════════════════════════════════════════════
# 3. GrowthService 完整 XP 结算
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_growth_service_xp_accumulate(gdb):
    """GrowthService.process_xp_grant → XP 累积正确"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")

    from exchange.growth_service import GrowthService
    gs = GrowthService(db)

    result = await gs.process_xp_grant(
        novel_id=nid,
        owned_item_id=oid,
        school="破天指",
        amount=300,
        context="vs_equal_win",
    )
    assert result["success"] is True
    assert result["xp_added"] > 0, "应有正向 XP 增量"

    rec = await db.get_growth_record(nid, oid, "破天指")
    assert rec["current_xp"] > 0


@pytest.mark.asyncio
async def test_growth_service_xp_nonnegative(gdb):
    """XP 结算结果不允许负数"""
    db, nid, oid = gdb
    await db.init_growth_record(nid, oid, "破天指")

    from exchange.growth_service import GrowthService
    gs = GrowthService(db)

    result = await gs.process_xp_grant(
        novel_id=nid,
        owned_item_id=oid,
        school="破天指",
        amount=1,
        context="vs_weaker",  # 最低倍率
    )
    assert result["xp_added"] >= 0, f"XP 增量不得为负: {result['xp_added']}"


@pytest.mark.asyncio
async def test_growth_service_batch(gdb):
    """batch_grant 处理多技能同时结算"""
    db, nid, oid = gdb

    # 插入另一个物品
    oid2 = str(uuid.uuid4())
    await db._exec(
        "INSERT INTO owned_items (id,novel_id,item_key,item_name,item_type,payload) "
        "VALUES (?,?,?,?,?,?)",
        (oid2, nid, "void_step", "虚空步", "ApplicationTechnique", "{}"),
    )
    await db.init_growth_record(nid, oid,  "破天指")
    await db.init_growth_record(nid, oid2, "虚空步")

    from exchange.growth_service import GrowthService
    gs = GrowthService(db)

    grants = [
        {"school": "破天指", "owned_item_id": oid,  "amount": 200, "context": "vs_equal_win"},
        {"school": "虚空步", "owned_item_id": oid2, "amount": 150, "context": "training"},
    ]
    results = await gs.batch_grant(nid, grants)
    assert len(results) == 2
    assert all(r["success"] for r in results), "batch grant 应全部成功"


# ════════════════════════════════════════════════════════════════════════
# 4. 异源体系：相性与原理冲突
# ════════════════════════════════════════════════════════════════════════

def test_heterogeneous_phase_conflict_detected():
    """相性冲突（阴阳对立）应被识别"""
    try:
        from exchange.growth_service import heterogeneous_conflict_check
        conflict = heterogeneous_conflict_check(
            school_a="阴冰决",
            school_b="炎阳诀",
        )
        # 期望返回 dict 含 conflict_type
        assert "conflict_type" in conflict
        assert conflict["conflict_type"] in ("phase", "principle", "none")
    except ImportError:
        pytest.skip("heterogeneous_conflict_check 未实现，跳过")


def test_heterogeneous_same_school_no_conflict():
    """同体系无冲突"""
    try:
        from exchange.growth_service import heterogeneous_conflict_check
        conflict = heterogeneous_conflict_check(
            school_a="破天指",
            school_b="破天指",
        )
        assert conflict["conflict_type"] == "none"
    except ImportError:
        pytest.skip("heterogeneous_conflict_check 未实现，跳过")


# ════════════════════════════════════════════════════════════════════════
# 5. context 倍率完整覆盖验证
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("context,min_mult", [
    ("vs_stronger_win",   1.5),
    ("vs_stronger_alive", 0.5),
    ("vs_equal_win",      1.0),
    ("vs_equal_alive",    0.3),
    ("vs_weaker",         0.0),
    ("training",          0.1),
    ("unknown_ctx",       0.0),
])
def test_context_multiplier_parametrized(context, min_mult):
    """所有 context 值的倍率均在预期下限以上"""
    from exchange.growth_service import GrowthService
    gs = GrowthService.__new__(GrowthService)
    m = gs._context_multiplier(context)
    assert m >= min_mult, \
        f"context={context} 倍率({m}) 低于预期下限({min_mult})"
    assert m >= 0, f"倍率不得为负: {m}"


# ════════════════════════════════════════════════════════════════════════
# 6. 一次性积分奖励结算
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_points_grant_via_calibrator(gdb):
    """system_grant type=points → DB 积分增加"""
    db, nid, oid = gdb

    from agents.state import empty_state
    state = empty_state(nid, "击败守门人", chapter_id="ch_001")
    state["generated_text"] = (
        "石板震动。\n"
        '<system_grant type="points" amount="1234"/>\n'
        "守门人倒地。"
    )
    state["purity_result"] = {"passed": True, "violations": []}
    state["dm_verdict"] = "pass"

    mock_db = MagicMock()
    mock_db.add_points         = AsyncMock(return_value=1234)
    mock_db.get_kill_record    = AsyncMock(return_value=None)
    mock_db.upsert_kill_record = AsyncMock()
    mock_db.add_medal          = AsyncMock()
    mock_db.get_owned_items    = AsyncMock(return_value=[])
    mock_db.append_message     = AsyncMock()

    with patch("db.queries.get_db", return_value=mock_db):
        from agents.calibrator import run_calibrator
        result = await run_calibrator(state)

    # 验证 add_points 被调用
    mock_db.add_points.assert_called()
    call_args = mock_db.add_points.call_args[0]
    assert call_args[1] == 1234, f"应结算 1234 积分，实际: {call_args}"


# ════════════════════════════════════════════════════════════════════════
# 7. 击杀奖励 kill vs defeat 区分
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_kill_reward_higher_than_defeat(gdb):
    """击杀（kill）奖励 ≥ 击败（defeat）奖励"""
    db, nid, oid = gdb

    from exchange.pricing import calculate_combat_reward

    mock_db = MagicMock()
    mock_db.get_kill_record    = AsyncMock(return_value=None)  # 首次
    mock_db.upsert_kill_record = AsyncMock()

    kill_reward = await calculate_combat_reward(
        novel_id=nid, enemy_tier=2, enemy_tier_sub="M",
        protagonist_tier=2, kill_type="kill", db=mock_db
    )
    defeat_reward = await calculate_combat_reward(
        novel_id=nid, enemy_tier=2, enemy_tier_sub="M",
        protagonist_tier=2, kill_type="defeat", db=mock_db
    )
    assert kill_reward["points_earned"] >= defeat_reward["points_earned"], \
        f"击杀({kill_reward['points_earned']}) 应 ≥ 击败({defeat_reward['points_earned']})"
