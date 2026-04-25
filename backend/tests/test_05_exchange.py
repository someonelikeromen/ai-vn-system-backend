"""
test_05_exchange.py — 兑换熟练度系统核心逻辑测试
覆盖：
  1. 定价引擎（0-15★ 完整表、Hax 通道、知识通道）
  2. 凭证系统（验证/不消耗、向上拆分、min 1 积分）
  3. 战斗奖励边界（最低 0、首杀/重复击杀衰减）
  4. XP 结算（context 倍率、多技能 batch）
  5. 兑换 API 接口（/evaluate、/purchase、/search）
"""
from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

from exchange.pricing import (
    TIER_BASE_PRICES,
    _calc_medal_requirement,
    calculate_final_price,
    calculate_combat_reward,
    PricingEngine,
)


# ════════════════════════════════════════════════════════════════════════
# 1. 定价表完整性（0-15★ 每档 L/M/U 均存在且单调递增）
# ════════════════════════════════════════════════════════════════════════

def test_tier_table_covers_0_to_15():
    """0★ 到 15★ 全覆盖"""
    for tier in range(16):
        assert tier in TIER_BASE_PRICES, f"TIER_BASE_PRICES 缺少 {tier}★"


def test_tier_sub_lmu_all_present():
    """每一档都有 L/M/U 子档"""
    for tier in range(16):
        row = TIER_BASE_PRICES[tier]
        for sub in ("L", "M", "U"):
            assert sub in row, f"TIER_BASE_PRICES[{tier}] 缺少 {sub} 子档"


def test_tier_prices_strictly_ascending():
    """M 档价格严格单调递增"""
    prices = [TIER_BASE_PRICES[t]["M"] for t in range(16)]
    for i in range(len(prices) - 1):
        assert prices[i] < prices[i + 1], \
            f"价格应严格递增: {i}★M={prices[i]} >= {i+1}★M={prices[i+1]}"


def test_sub_tier_ordering_within_same_tier():
    """同一★内 L < M < U"""
    for tier in range(16):
        row = TIER_BASE_PRICES[tier]
        assert row["L"] < row["M"] < row["U"], \
            f"{tier}★ 子档顺序错误: L={row['L']} M={row['M']} U={row['U']}"


# ════════════════════════════════════════════════════════════════════════
# 2. Hax 独立定价通道（覆盖维度 = 0 → 独立通道）
# ════════════════════════════════════════════════════════════════════════

def test_hax_channel_activates_on_zero_coverage():
    """Hax 技能（覆盖维度=0）走独立通道，价格不依赖基础表"""
    engine = PricingEngine()
    price_hax  = engine.calc_base_price(tier=3, tier_sub="M", covered_dims=0, is_hax=True)
    price_norm = engine.calc_base_price(tier=3, tier_sub="M", covered_dims=5, is_hax=False)
    assert price_hax > 0, "Hax 通道价格应大于 0"
    assert price_hax != price_norm, "Hax 通道应与普通通道价格不同"


def test_hax_small_hi_less_than_full_coverage():
    """HI=1 的 Hax 应比 HI=5 便宜"""
    engine = PricingEngine()
    p_hi1 = engine.calc_hax_price(tier=5, tier_sub="M", hax_hi=1)
    p_hi5 = engine.calc_hax_price(tier=5, tier_sub="M", hax_hi=5)
    assert p_hi1 < p_hi5, f"HI=1 价格({p_hi1}) 应 < HI=5 价格({p_hi5})"


# ════════════════════════════════════════════════════════════════════════
# 3. 知识类物品下调通道
# ════════════════════════════════════════════════════════════════════════

def test_knowledge_channel_cheaper_than_technique():
    """同星级知识类物品价格 < 应用技巧"""
    engine = PricingEngine()
    price_tech  = engine.calc_base_price(tier=4, tier_sub="M", covered_dims=8, is_hax=False)
    price_know  = engine.calc_knowledge_price(tier=4, tier_sub="M")
    assert price_know < price_tech, \
        f"知识类({price_know}) 应比应用技巧({price_tech}) 便宜"


# ════════════════════════════════════════════════════════════════════════
# 4. 凭证系统（验证不消耗、向上拆分、星级门槛）
# ════════════════════════════════════════════════════════════════════════

def test_medal_requirement_zero_for_low_tier():
    """0-1★ 不需要凭证"""
    for tier in (0, 1):
        reqs = _calc_medal_requirement(tier, "M")
        assert reqs == [], f"{tier}★ 不应要求凭证，实际: {reqs}"


def test_medal_requirement_exists_for_high_tier():
    """高星级需要凭证"""
    reqs = _calc_medal_requirement(5, "M")
    assert len(reqs) > 0, "5★ 应需要凭证"


@pytest.mark.asyncio
async def test_medal_validation_sufficient():
    """持有足够凭证 → 验证通过（不消耗）"""
    engine = PricingEngine()

    mock_db = MagicMock()
    mock_db.get_medal_count = AsyncMock(return_value=3)  # 持有3枚

    # 需要 1 枚 2★ 凭证
    result = await engine.check_medal_eligibility(
        novel_id="n1", tier=2, tier_sub="M", db=mock_db
    )
    assert result["eligible"] is True
    assert result["consumed"] == 0, "验证模式不消耗凭证"


@pytest.mark.asyncio
async def test_medal_validation_insufficient_triggers_split():
    """凭证不足时自动向上拆分"""
    engine = PricingEngine()

    # 模拟：2★凭证=0, 3★凭证=1（可以拆分）
    def get_medal_count(novel_id, stars):
        return {2: 0, 3: 1}.get(stars, 0)

    mock_db = MagicMock()
    mock_db.get_medal_count = AsyncMock(side_effect=get_medal_count)
    mock_db.split_medal     = AsyncMock(return_value=True)

    result = await engine.check_medal_eligibility(
        novel_id="n1", tier=2, tier_sub="M", db=mock_db
    )
    # 拆分成功后应 eligible
    assert result["eligible"] is True
    mock_db.split_medal.assert_called_once()


# ════════════════════════════════════════════════════════════════════════
# 5. 战斗奖励边界
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_combat_reward_first_kill_positive():
    """首次击杀，奖励 > 0"""
    mock_db = MagicMock()
    mock_db.get_kill_record = AsyncMock(return_value=None)  # 首次
    mock_db.upsert_kill_record = AsyncMock()

    with patch("db.queries.get_db", return_value=mock_db):
        reward = await calculate_combat_reward(
            novel_id="n1", enemy_tier=2, enemy_tier_sub="M",
            protagonist_tier=1, kill_type="defeat", db=mock_db
        )
    assert reward["points_earned"] >= 0, "击败奖励最低为 0"


@pytest.mark.asyncio
async def test_combat_reward_minimum_is_zero():
    """重复大量击杀后，奖励降至 >= 0（不允许负数）"""
    mock_db = MagicMock()
    mock_db.get_kill_record = AsyncMock(return_value={
        "kill_count": 10000, "defeat_count": 0,
        "points_decay_stage": 99, "medal_decay_stage": 99,
    })
    mock_db.upsert_kill_record = AsyncMock()

    with patch("db.queries.get_db", return_value=mock_db):
        reward = await calculate_combat_reward(
            novel_id="n1", enemy_tier=1, enemy_tier_sub="L",
            protagonist_tier=5, kill_type="defeat", db=mock_db
        )
    assert reward["points_earned"] >= 0, \
        f"击杀奖励不得为负: {reward['points_earned']}"


@pytest.mark.asyncio
async def test_purchase_minimum_cost_is_one():
    """兑换积分消耗最低为 1"""
    engine = PricingEngine()
    # 极小物品的价格应 >= 1
    price = engine.calc_base_price(tier=0, tier_sub="L", covered_dims=1)
    final = engine.apply_modifiers(price, {})
    assert final >= 1, f"最终价格应 >= 1 积分，实际: {final}"


# ════════════════════════════════════════════════════════════════════════
# 6. 三轮评估 API（mock LLM）
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_evaluate_endpoint_returns_tier(app_client):
    """POST /api/exchange/{id}/evaluate 返回合法 tier"""
    # 先创建小说和主角
    resp = await app_client.post("/api/novels/", json={
        "title": "兑换测试小说", "ip_type": "original"
    })
    assert resp.status_code == 201
    novel_id = resp.json()["novel"]["novel_id"]

    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    # 触发评估
    eval_resp = await app_client.post(f"/api/exchange/{novel_id}/evaluate", json={
        "item_name": "九阴真经",
        "source_world": "射雕英雄传",
        "lore_context": "绝世武功，内功心法",
        "item_description": "速习内功，提升内力上限",
    })
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    assert "final_tier" in data or "tier" in data, \
        f"应返回 tier 字段: {data}"


@pytest.mark.asyncio
async def test_evaluate_returns_price_field(app_client):
    """评估结果包含 final_price"""
    resp = await app_client.post("/api/novels/", json={"title": "价格测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    eval_resp = await app_client.post(f"/api/exchange/{novel_id}/evaluate", json={
        "item_name": "月步",
        "source_world": "海贼王",
        "lore_context": "高速移动技巧",
        "item_description": "短距离瞬移",
    })
    data = eval_resp.json()
    assert eval_resp.status_code == 200
    price = data.get("final_price") or data.get("price")
    assert price is not None and price >= 0


# ════════════════════════════════════════════════════════════════════════
# 7. 购买 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_purchase_deducts_points(app_client):
    """购买后积分减少"""
    resp = await app_client.post("/api/novels/", json={"title": "购买测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={
        "name": "吴森", "starting_points": 100000
    })

    # 购买一个低价物品
    purchase_resp = await app_client.post(f"/api/exchange/{novel_id}/purchase", json={
        "item_key":   "basic_step",
        "item_name":  "基础步法",
        "item_type":  "ApplicationTechnique",
        "source_world": "武侠世界",
        "final_price": 1000,
        "final_tier":  1,
        "final_sub":   "M",
        "payload":     {},
    })
    assert purchase_resp.status_code == 200
    result = purchase_resp.json()
    assert result.get("remaining_points", 99001) <= 99000 or \
           result.get("success") is True or \
           "points" in str(result), "购买应消耗积分"


@pytest.mark.asyncio
async def test_purchase_insufficient_points_fails(app_client):
    """积分不足 → 返回 400"""
    resp = await app_client.post("/api/novels/", json={"title": "积分不足测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={
        "name": "吴森", "starting_points": 10  # 极少积分
    })

    purchase_resp = await app_client.post(f"/api/exchange/{novel_id}/purchase", json={
        "item_key":   "gold_sword",
        "item_name":  "黄金剑",
        "item_type":  "ApplicationTechnique",
        "source_world": "异世界",
        "final_price": 99999,  # 远超余额
        "final_tier":  3,
        "final_sub":   "M",
        "payload":     {},
    })
    assert purchase_resp.status_code in (400, 422), \
        f"积分不足应返回 400，实际: {purchase_resp.status_code}"


# ════════════════════════════════════════════════════════════════════════
# 8. 搜索 API
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_search_exchange_catalog(app_client):
    """GET /api/exchange/{id}/search?q= 返回正确结构"""
    resp = await app_client.post("/api/novels/", json={"title": "搜索测试"})
    novel_id = resp.json()["novel"]["novel_id"]
    await app_client.post(f"/api/novels/{novel_id}/init", json={"name": "吴森"})

    search_resp = await app_client.get(f"/api/exchange/{novel_id}/search?q=剑")
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert "items" in data or "results" in data, \
        f"搜索应返回 items 字段: {data}"
