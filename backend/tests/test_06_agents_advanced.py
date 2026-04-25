"""
test_06_agents_advanced.py — Agent 进阶测试
覆盖：
  1. NPC drift 检测（LLM 裁判：none/minor/severe）
  2. Planner 沙盒结果注入验证
  3. Calibrator XP context 倍率
  4. Sandbox 能量池注入校验
  5. Graph 并发 state 隔离（NPC+Sandbox 不相互覆盖）
  6. DM world_context 锁定检测
  7. Chronicler sandbox_context 三字段注入
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ════════════════════════════════════════════════════════════════════════
# 1. NPC Drift 检测
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_planner_npc_drift_none():
    """行为完全符合特质 → drift_level=none"""
    from agents.calibrator import NPC_DRIFT_SYSTEM_PROMPT
    from agents.state import empty_state

    state = empty_state("novel_001", "行动", chapter_id="ch_001")
    state["display_text"]   = "他冷静地扫视着混乱的房间。"
    state["user_input"]     = "观察"
    state["npc_responses"]  = [{
        "npc_name": "冷剑山人",
        "planned_action": "冷静观察敌人",
        "dialogue": "静。",
        "emotion": "冷静",
    }]
    state["narrative_seeds"] = []
    state["sandbox_result"]  = {}

    mock_db = MagicMock()
    mock_db.get_npc = AsyncMock(return_value={
        "name": "冷剑山人",
        "trait_lock": ["极度冷静", "少言寡语"],
        "npc_type": "human",
    })
    mock_db.register_hook = AsyncMock()

    # LLM 返回无漂移
    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(return_value={
        "npc_name": "冷剑山人",
        "drift_level": "none",
        "drift_reason": "",
        "offending_behavior": "",
        "offending_traits": [],
        # 规划器主输出
        "arc_progress": "稳定",
        "next_turn_hint": "继续",
        "hooks_to_activate": [],
        "hooks_to_register": [],
        "npc_drift_warnings": [],
    })

    with patch("db.queries.get_db", return_value=mock_db), \
         patch("utils.llm_client.get_llm_client", return_value=mock_llm):
        from agents.calibrator import run_planner
        result = await run_planner(state)

    assert isinstance(result, dict)
    assert result.get("npc_drift_warnings", []) == [], \
        "无漂移时警告列表应为空"


@pytest.mark.asyncio
async def test_planner_npc_drift_severe_logged():
    """严重漂移 → state['npc_drift_warnings'] 非空"""
    from agents.state import empty_state

    state = empty_state("novel_002", "行动", chapter_id="ch_001")
    state["display_text"]   = "他突然歇斯底里地大叫起来。"
    state["user_input"]     = "挑衅"
    state["npc_responses"]  = [{
        "npc_name": "冷剑山人",
        "planned_action": "发疯大叫",
        "dialogue": "啊啊啊啊！！！",
        "emotion": "崩溃",
    }]
    state["narrative_seeds"] = []
    state["sandbox_result"]  = {}

    mock_db = MagicMock()
    mock_db.get_npc = AsyncMock(return_value={
        "name": "冷剑山人",
        "trait_lock": ["极度冷静", "从不失态"],
        "npc_type": "human",
    })
    mock_db.register_hook = AsyncMock()

    call_count = {"n": 0}

    async def llm_side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # drift 检测调用
            return {
                "npc_name": "冷剑山人",
                "drift_level": "severe",
                "drift_reason": "冷静特质被完全违反",
                "offending_behavior": "发疯大叫",
                "offending_traits": ["极度冷静"],
            }
        else:
            # 规划器主调用
            return {
                "arc_progress": "", "next_turn_hint": "",
                "hooks_to_activate": [], "hooks_to_register": [],
                "npc_drift_warnings": ["冷剑山人: [SEVERE] 违反冷静特质"],
            }

    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(side_effect=llm_side_effect)

    with patch("db.queries.get_db", return_value=mock_db), \
         patch("utils.llm_client.get_llm_client", return_value=mock_llm):
        from agents.calibrator import run_planner
        result = await run_planner(state)

    assert result.get("npc_drift_warnings"), "严重漂移应产生警告"
    assert any("severe" in w.lower() or "SEVERE" in w
               for w in result["npc_drift_warnings"]), "警告中应包含 SEVERE"


# ════════════════════════════════════════════════════════════════════════
# 2. Planner 沙盒结果注入
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_planner_injests_sandbox_result():
    """sandbox_result 的内容应出现在 Planner LLM 调用的 user prompt 中"""
    from agents.state import empty_state

    state = empty_state("novel_003", "战斗", chapter_id="ch_001")
    state["display_text"] = "双方对峙。"
    state["sandbox_result"] = {
        "expected_consequences": "主角将被击飞",
        "combat_strategy":       "利用速度差绕后",
        "warnings":              ["能量接近耗尽"],
    }
    state["npc_responses"]  = []
    state["narrative_seeds"] = []

    captured_prompts = []

    async def capture_chat_json(**kwargs):
        messages = kwargs.get("messages", [])
        for m in messages:
            if m["role"] == "user":
                captured_prompts.append(m["content"])
        return {
            "arc_progress": "", "next_turn_hint": "",
            "hooks_to_activate": [], "hooks_to_register": [],
            "npc_drift_warnings": [],
        }

    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(side_effect=capture_chat_json)
    mock_db = MagicMock()
    mock_db.get_npc = AsyncMock(return_value=None)
    mock_db.register_hook = AsyncMock()

    with patch("db.queries.get_db", return_value=mock_db), \
         patch("utils.llm_client.get_llm_client", return_value=mock_llm):
        from agents.calibrator import run_planner
        await run_planner(state)

    combined = " ".join(captured_prompts)
    assert "主角将被击飞" in combined, "sandbox expected_consequences 应注入 prompt"
    assert "利用速度差绕后" in combined, "sandbox combat_strategy 应注入 prompt"


# ════════════════════════════════════════════════════════════════════════
# 3. Calibrator XP context 倍率正确性
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_xp_context_multiplier_vs_stronger_win_highest():
    """vs_stronger_win 倍率 > vs_equal_win > vs_weaker"""
    from exchange.growth_service import GrowthService

    gs = GrowthService.__new__(GrowthService)
    # 直接测试倍率表
    multipliers = {
        ctx: gs._context_multiplier(ctx)
        for ctx in ("vs_stronger_win", "vs_equal_win", "vs_weaker", "training")
    }
    assert multipliers["vs_stronger_win"] > multipliers["vs_equal_win"], \
        "以弱胜强倍率应最高"
    assert multipliers["vs_equal_win"] > multipliers["vs_weaker"], \
        "同级胜利应高于碾压弱敌"
    assert multipliers["vs_weaker"] >= 0, "碾压弱敌倍率应 >= 0"


@pytest.mark.asyncio
async def test_xp_context_vs_stronger_alive_positive():
    """vs_stronger_alive（强敌中存活）倍率 > 0"""
    from exchange.growth_service import GrowthService
    gs = GrowthService.__new__(GrowthService)
    m = gs._context_multiplier("vs_stronger_alive")
    assert m > 0, "在强敌中存活应获得正向 XP 倍率"


# ════════════════════════════════════════════════════════════════════════
# 4. Sandbox 能量池注入
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sandbox_prompt_contains_energy_pools():
    """stat_data 有能量池时，sandbox prompt 应包含能量池信息"""
    from agents.state import empty_state

    state = empty_state("novel_004", "战斗攻击", chapter_id="ch_001")
    state["scene_type"] = "combat"
    state["stat_data"] = {
        "tier": 3, "tier_sub": "M",
        "energy_pools": {
            "灵力": {"current": 30, "max": 200},
            "霸气": {"current": 150, "max": 200},
        }
    }
    state["npc_responses"] = []

    captured = []

    async def capture(**kwargs):
        for m in kwargs.get("messages", []):
            if m["role"] == "user":
                captured.append(m["content"])
        return {"expected_consequences": "ok", "warnings": []}

    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(side_effect=capture)

    with patch("utils.llm_client.get_llm_client", return_value=mock_llm):
        from agents.calibrator import run_sandbox
        await run_sandbox(state)

    combined = " ".join(captured)
    assert "灵力" in combined, "能量池名称应出现在沙盒 prompt 中"
    assert "30/200" in combined or "30" in combined, "能量池数值应出现在 prompt 中"


# ════════════════════════════════════════════════════════════════════════
# 5. Graph 并发 state 隔离
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_npc_sandbox_concurrent_no_state_race():
    """NPC 和 Sandbox 并发执行时，结果互不覆盖"""
    from agents.state import empty_state
    from agents.graph import npc_sandbox_node

    state = empty_state("novel_005", "测试", chapter_id="ch_001")
    state["scene_type"]   = "combat"
    state["stat_data"]    = {"tier": 1, "tier_sub": "M", "energy_pools": {}}
    state["active_npcs"]  = []
    state["npc_responses"] = []
    state["sandbox_result"] = {}

    expected_npc_responses  = [{"npc_name": "TestNPC", "planned_action": "待机"}]
    expected_sandbox_result = {"expected_consequences": "平局", "warnings": []}

    async def fake_npc(s):
        await asyncio.sleep(0.01)
        s["npc_responses"] = expected_npc_responses
        return s

    async def fake_sandbox(s):
        await asyncio.sleep(0.01)
        s["sandbox_result"] = expected_sandbox_result
        return s

    with patch("agents.npc.run_npc_actors", side_effect=fake_npc), \
         patch("agents.calibrator.run_sandbox", side_effect=fake_sandbox):
        result = await npc_sandbox_node(state)

    # 两个字段都应正确写入主 state
    assert result["npc_responses"] == expected_npc_responses, \
        "NPC 结果应写入 state"
    assert result["sandbox_result"] == expected_sandbox_result, \
        "Sandbox 结果应写入 state"


# ════════════════════════════════════════════════════════════════════════
# 6. DM world_context 锁定检测
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_dm_rejects_world_locked_traverse():
    """主角在 world_locked_until 期间触发穿越 → DM 应 reject"""
    from agents.state import empty_state

    state = empty_state("novel_006", "我要穿越回原世界", chapter_id="ch_001")

    mock_db = MagicMock()
    mock_db.get_protagonist_state = AsyncMock(return_value={
        "name": "吴森", "tier": 2, "tier_sub": "M", "points": 5000,
        "attributes": {}, "energy_pools": {},
        "world_locked_until": "2999-01-01T00:00:00",  # 锁定至遥远未来
    })
    mock_db._fetchall = AsyncMock(return_value=[])
    mock_db.get_messages   = AsyncMock(return_value=[])
    mock_db.get_active_hooks = AsyncMock(return_value=[])
    mock_db._fetchone = AsyncMock(return_value={
        "time_flow_ratio": "1:1",
        "time_flow_type": "fixed",
        "peak_tier": 5,
        "peak_tier_sub": "M",
        "world_name": "武侠世界",
        "entered_at": "2024-01-01",
    })

    mock_memory = MagicMock()
    mock_memory.recall = AsyncMock(return_value={"core": [], "recalled": []})

    mock_llm = MagicMock()
    # DM 返回 reject（世界锁定）
    mock_llm.chat_json = AsyncMock(return_value={
        "verdict":        "reject",
        "feedback":       "世界穿越锁定中，无法离开",
        "modified_input": "",
        "scene_type":     "normal",
        "active_npcs":    [],
        "thought":        "主角被锁定",
    })

    with patch("db.queries.get_db", return_value=mock_db), \
         patch("memory.engine.memory_engine", mock_memory), \
         patch("utils.llm_client.get_llm_client", return_value=mock_llm), \
         patch("utils.locks.NovelStateRefreshBus.is_dirty", return_value=False):
        from agents.dm import run_dm
        result = await run_dm(state)

    assert result.get("should_abort") is True, \
        "被 DM reject 后应 abort"
    assert result.get("dm_verdict") == "reject"


# ════════════════════════════════════════════════════════════════════════
# 7. Chronicler sandbox_context 三字段注入
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chronicler_sandbox_three_fields_injected():
    """Chronicler 的 user_prompt 应包含沙盒三字段"""
    from agents.state import empty_state

    state = empty_state("novel_007", "攻击", chapter_id="ch_001")
    state["dm_verdict"]   = "pass"
    state["scene_type"]   = "combat"
    state["style_stack"]  = ["零度写作"]
    state["style_content"] = ""
    state["stat_data"]    = {"name": "吴森", "tier": 2, "tier_sub": "M", "points": 100}
    state["memory_context"] = {"core": [], "recalled": []}
    state["npc_responses"] = []
    state["sandbox_result"] = {
        "expected_consequences": "敌人被击伤",
        "combat_strategy":       "贴身缠斗",
        "energy_interaction":    "两系能量同源相容",
        "warnings":              [],
    }

    captured_user_prompts = []

    async def capture_chat(**kwargs):
        for m in kwargs.get("messages", []):
            if m["role"] == "user":
                captured_user_prompts.append(m["content"])
        return "桩状石块倒塌，扬起碎屑。"

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=capture_chat)

    mock_db = MagicMock()
    mock_db.get_owned_items = AsyncMock(return_value=[])

    with patch("utils.llm_client.get_llm_client", return_value=mock_llm), \
         patch("db.queries.get_db", return_value=mock_db):
        from agents.chronicler import run_chronicler
        result = await run_chronicler(state)

    combined = " ".join(captured_user_prompts)
    assert "敌人被击伤" in combined, "expected_consequences 应注入 Chronicler prompt"
    assert "贴身缠斗" in combined, "combat_strategy 应注入 Chronicler prompt"
    assert "两系能量同源相容" in combined, "energy_interaction 应注入 Chronicler prompt"


# ════════════════════════════════════════════════════════════════════════
# 8. NPC companion 好感度注入
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_npc_companion_affinity_injected_into_prompt():
    """Companion NPC 的好感度/忠诚类型应注入 simulate_npc prompt"""
    from agents.state import empty_state

    state = empty_state("novel_008", "和同伴说话", chapter_id="ch_001")
    state["scene_type"]   = "dialogue"
    state["stat_data"]    = {"tier": 1, "tier_sub": "M"}
    state["active_npcs"]  = ["灵狐儿"]
    state["npc_responses"] = []

    mock_db = MagicMock()
    mock_db.get_npc = AsyncMock(return_value={
        "name":            "灵狐儿",
        "npc_type":        "companion",
        "trait_lock":      ["忠诚", "活泼"],
        "knowledge_scope": [],
        "capability_cap":  {},
        "psyche_model":    {},
        "initial_affinity": 85,
        "loyalty_type":    "情感型",
    })

    captured = []

    async def capture_chat_json(**kwargs):
        for m in kwargs.get("messages", []):
            if m["role"] == "user":
                captured.append(m["content"])
        return {
            "npc_name": "灵狐儿",
            "thought": "",
            "planned_action": "微笑",
            "dialogue": "主人，您回来了！",
            "emotion": "高兴",
        }

    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(side_effect=capture_chat_json)

    with patch("utils.llm_client.get_llm_client", return_value=mock_llm), \
         patch("db.queries.get_db", return_value=mock_db):
        from agents.npc import run_npc_actors
        result = await run_npc_actors(state)

    combined = " ".join(captured)
    assert "85" in combined or "好感度" in combined, \
        "同伴好感度应注入 NPC prompt"
    assert "情感型" in combined, "同伴忠诚类型应注入 NPC prompt"
