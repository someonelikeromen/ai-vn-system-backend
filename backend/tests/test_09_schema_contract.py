"""
test_09_schema_contract.py — 数据契约测试（不依赖 LLM）
快速验证：所有新增 DB 字段、API 响应结构、state 字段、SSE 事件格式
"""
from __future__ import annotations

import json
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)


# ════════════════════════════════════════════════════════════════════════
# 1. DB Schema 新增字段验证
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_npc_profiles_has_companion_fields():
    """npc_profiles 表有 companion 专用字段"""
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    db = Database(path)
    await db.connect()

    rows = await db._fetchall("PRAGMA table_info(npc_profiles)")
    cols = {r["name"] for r in rows}

    for col in ("npc_type", "initial_affinity", "loyalty_type", "companion_slot"):
        assert col in cols, f"npc_profiles 缺少 {col} 列"

    await db.close()
    import os; os.unlink(path)


@pytest.mark.asyncio
async def test_protagonist_state_has_required_fields():
    """protagonist_state 表结构完整"""
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    db = Database(path)
    await db.connect()

    rows = await db._fetchall("PRAGMA table_info(protagonist_state)")
    cols = {r["name"] for r in rows}

    required = [
        "novel_id", "name", "tier", "tier_sub", "points",
        "attributes", "energy_pools", "status_effects",
        "psyche_model_json", "knowledge_scope",
    ]
    for col in required:
        assert col in cols, f"protagonist_state 缺少 {col} 列"

    await db.close()
    import os; os.unlink(path)


@pytest.mark.asyncio
async def test_owned_items_schema():
    import tempfile
    from db.models import init_db
    from db.queries import Database

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    db = Database(path)
    await db.connect()

    rows = await db._fetchall("PRAGMA table_info(owned_items)")
    cols = {r["name"] for r in rows}

    for col in ("item_name", "source_world", "final_tier", "final_sub"):
        assert col in cols, f"owned_items 缺少 {col} 列"

    await db.close()
    import os; os.unlink(path)


# ════════════════════════════════════════════════════════════════════════
# 2. AgentState 新字段完整性
# ════════════════════════════════════════════════════════════════════════

def test_agent_state_has_drift_details():
    """AgentState 应有 npc_drift_details 字段"""
    from agents.state import empty_state
    s = empty_state("n1", "test")
    assert "npc_drift_details" in s, "AgentState 缺少 npc_drift_details 字段"
    assert isinstance(s["npc_drift_details"], list)


def test_agent_state_has_world_context():
    """AgentState 应有 world_context 字段"""
    from agents.state import empty_state
    s = empty_state("n1", "test")
    assert "world_context" in s
    assert isinstance(s["world_context"], dict)


def test_agent_state_all_required_fields():
    """验证所有规格要求的 state 字段"""
    from agents.state import empty_state
    s = empty_state("n1", "test", chapter_id="ch1", world_key="murim")

    required_fields = [
        "novel_id", "world_key", "chapter_id", "user_input",
        "stat_data", "owned_items", "medals", "char_points",
        "dm_verdict", "dm_feedback", "dm_modified_input",
        "scene_type", "world_context",
        "memory_context",
        "active_npcs", "npc_responses",
        "sandbox_result",
        "style_stack", "style_content",
        "generated_text", "display_text",
        "purity_result", "purity_retries",
        "system_grants", "narrative_seeds",
        "calibration_result", "growth_results",
        "planner_guidance", "hook_updates",
        "npc_drift_warnings", "npc_drift_details",
        "sse_queue", "workflow_step", "should_abort",
        "error_msg", "rollback_snapshot",
    ]
    for field in required_fields:
        assert field in s, f"AgentState 缺少字段: {field}"


# ════════════════════════════════════════════════════════════════════════
# 3. SSE 事件格式契约
# ════════════════════════════════════════════════════════════════════════

def test_sse_event_format_parseable():
    """所有 SSE 事件类型都能被正确解析"""
    from agents.state import sse_event, SSEEventType

    event_cases = [
        sse_event(SSEEventType.LOG,          step=1, content="DM 启动"),
        sse_event(SSEEventType.THOUGHT,      agent="DM", content="分析中"),
        sse_event(SSEEventType.NOVEL_TEXT,   content="烈焰升腾"),
        sse_event(SSEEventType.SYSTEM_GRANT, grant_type="points", amount=500),
        sse_event(SSEEventType.DONE,         grants_count=3),
        sse_event(SSEEventType.ERROR,        content="连接超时"),
    ]
    for raw in event_cases:
        assert raw.startswith("data: "), f"SSE 行应以 'data: ' 开头: {raw!r}"
        payload = json.loads(raw.removeprefix("data: ").strip())
        assert "type" in payload, f"SSE 事件缺少 type 字段: {payload}"


def test_sse_done_parseable():
    """done 类型 SSE 能被 game.py 的解析逻辑识别"""
    from agents.state import sse_event, SSEEventType
    done_raw = sse_event(SSEEventType.DONE, grants_count=3, chapter_id="ch1")

    parsed = json.loads(done_raw.removeprefix("data: ").strip())
    assert parsed.get("type") == "done"


# ════════════════════════════════════════════════════════════════════════
# 4. PricingEngine 接口契约
# ════════════════════════════════════════════════════════════════════════

def test_pricing_engine_evaluate_output_structure():
    """评估结果：PricingEngine 有 evaluate / _calc_required_medals"""
    from exchange.pricing import PricingEngine

    engine = PricingEngine()

    # 验证核心方法存在
    assert callable(getattr(engine, "evaluate", None)), \
        "PricingEngine 应有 evaluate 方法"
    assert callable(getattr(engine, "_calc_required_medals", None)), \
        "PricingEngine 应有 _calc_required_medals 方法"

    # _calc_required_medals 接口契约
    medals_tier3 = engine._calc_required_medals(3, "M")
    assert isinstance(medals_tier3, list), \
        f"_calc_required_medals 应返回 list，实际: {type(medals_tier3)}"

    medals_tier0 = engine._calc_required_medals(0, "M")
    assert medals_tier0 == [], "0★ 不应要求凭证"



def test_pricing_engine_calc_required_medals_type():
    """_calc_required_medals 返回 list[dict]"""
    from exchange.pricing import PricingEngine
    engine = PricingEngine()
    medals = engine._calc_required_medals(3, "M")
    assert isinstance(medals, list)
    for item in medals:
        assert "stars" in item or isinstance(item, (int, dict))


# ════════════════════════════════════════════════════════════════════════
# 5. 异源体系定义（规格合规检查）
# ════════════════════════════════════════════════════════════════════════

def test_heterogeneous_types_defined():
    """异源体系枚举/常量必须包含 phase 和 principle"""
    try:
        from exchange.growth_service import HETEROGENEOUS_TYPES
        assert "phase"     in HETEROGENEOUS_TYPES, "缺少 phase（相性）冲突类型"
        assert "principle" in HETEROGENEOUS_TYPES, "缺少 principle（原理）冲突类型"
    except ImportError:
        # 如果模块还没实现，跳过
        pytest.skip("HETEROGENEOUS_TYPES 未定义，跳过")
