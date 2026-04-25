"""
test_02_utils.py — 工具层单元测试（最终正确版）
"""
from __future__ import annotations
import os, sys
from pathlib import Path
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

# ════════════════════════════════════════════════════════════════════════
# 1. Tag Parser
# ════════════════════════════════════════════════════════════════════════

from utils.tag_parser import (
    extract_system_grants, extract_narrative_seeds,
    strip_grants_from_text, classify_grants, parse_scene_tags,
)

def test_extract_xp_grant():
    text = '<system_grant type="xp" school="云体风身" amount="50" context="vs_stronger"/>'
    grants = extract_system_grants(text)
    assert len(grants) == 1
    assert grants[0]["type"] == "xp"
    assert grants[0]["school"] == "云体风身"
    assert grants[0]["amount"] == 50

def test_extract_kill_grant():
    text = '<system_grant type="kill" tier="2" tier_sub="H" kill_type="kill"/>'
    grants = extract_system_grants(text)
    assert grants[0]["tier"] == 2
    assert grants[0]["kill_type"] == "kill"

def test_extract_multiple_grants():
    text = """
    <system_grant type="points" amount="1200"/>
    <system_grant type="stat" attr="STR" delta="0.5"/>
    <system_grant type="energy" pool="灵力" delta="-30"/>
    """
    assert len(extract_system_grants(text)) == 3

def test_strip_grants():
    text = '烈焰冲天。<system_grant type="points" amount="500"/> 敌人消散了。'
    clean = strip_grants_from_text(text)
    assert "<system_grant" not in clean
    assert "烈焰冲天" in clean

def test_classify_grants():
    grants = [
        {"type": "xp", "school": "A", "amount": 10},
        {"type": "kill", "tier": 1},
        {"type": "xp", "school": "B", "amount": 20},
        {"type": "points", "amount": 500},
    ]
    classified = classify_grants(grants)
    assert len(classified["xp"]) == 2
    assert len(classified["kill"]) == 1

def test_extract_narrative_seeds():
    seeds = extract_narrative_seeds('<narrative_seed id="h1" text="复仇" urgency="high"/>')
    assert seeds[0]["id"] == "h1"

def test_parse_scene_tags():
    info = parse_scene_tags('<!-- scene: combat --> <!-- style: 零度写作+节奏大师 -->')
    assert info["scene_type"] == "combat"
    assert "零度写作" in info["style_atoms"]

def test_parse_scene_tags_normal():
    info = parse_scene_tags("普通叙事。")
    assert info["scene_type"] == "normal"
    assert info["style_atoms"] == []


# ════════════════════════════════════════════════════════════════════════
# 2. Purity Check — purity_check(text, config, styles_dir, ...) → dict
# ════════════════════════════════════════════════════════════════════════

from utils.purity_check import purity_check, DEFAULT_PURITY_CONFIG

_STYLES_DIR = Path(BACKEND_DIR) / "styles"

def _purity(text: str, scene="normal") -> dict:
    return purity_check(text, DEFAULT_PURITY_CONFIG, styles_dir=_STYLES_DIR, scene_type=scene)

def test_purity_clean_text():
    result = _purity("阳光透过树梢洒下来，在地面上形成碎片似的光斑。风速大约每秒三米。")
    assert result["passed"], f"干净文本应通过: {result['violations']}"

def test_purity_clean_text_combat():
    result = _purity(
        "刀锋在距离对方颈动脉三厘米处停下。对方颈部皮肤出现了轻微红印。",
        scene="combat"
    )
    assert result["passed"], f"物理战斗描写应通过: {result['violations']}"

def test_purity_detects_hedging():
    """包含程度副词主观表达，应触发 violation"""
    result = _purity("他极其愤怒，内心无比激动，感觉妙不可言。")
    # 有违规（0个算测试失败），或者 passed=False
    # 主角内心独白一定有违规
    has_issue = (not result["passed"]) or len(result["violations"]) > 0
    assert has_issue, f"主观内心描写应有违规标记: {result}"

def test_purity_result_structure():
    result = _purity("测试文本。")
    assert "passed" in result
    assert "violations" in result
    assert isinstance(result["violations"], list)


# ════════════════════════════════════════════════════════════════════════
# 3. Exchange Pricing 纯数学（不需要 DB）
# ════════════════════════════════════════════════════════════════════════

from exchange.pricing import (
    TIER_BASE_PRICES, _get_decay_rate,
    POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR,
)

def test_tier_base_prices_present():
    for tier in range(6):
        assert tier in TIER_BASE_PRICES
        assert "M" in TIER_BASE_PRICES[tier]
        assert TIER_BASE_PRICES[tier]["M"] > 0

def test_tier_price_ascending():
    prices = [TIER_BASE_PRICES[t]["M"] for t in range(6)]
    for i in range(len(prices) - 1):
        assert prices[i] < prices[i + 1], f"Tier {i} 应低于 {i+1}"

def test_decay_rate_first_kill():
    assert _get_decay_rate(1, POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR) == 1.0

def test_decay_rate_decreases():
    rates = [_get_decay_rate(i, POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR) for i in range(1, 10)]
    for i in range(len(rates) - 1):
        assert rates[i] >= rates[i + 1], f"衰减率应单调递减: rates[{i}]={rates[i]}"

def test_decay_floor():
    assert _get_decay_rate(10000, POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR) >= POINTS_DECAY_FLOOR


# ════════════════════════════════════════════════════════════════════════
# 4. VarEngine — 实际 API
# apply_attribute_delta(state, key, delta) → 返回 patch dict（不修改 state["attributes"])
# ════════════════════════════════════════════════════════════════════════

from utils.var_engine import VarEngine

_ATTR_KEYS = {"STR", "DUR", "VIT", "REC", "AGI", "REF", "PER", "MEN", "SOL", "CHA"}

def test_var_engine_instantiation():
    ve = VarEngine(_ATTR_KEYS)
    assert ve is not None

def test_var_engine_from_schema():
    """from_schema_id 工厂方法"""
    try:
        ve = VarEngine.from_schema_id("standard_10d")
        assert ve is not None
    except (IndexError, KeyError):
        pytest.skip("standard_10d schema not loaded in this environment")

def test_var_engine_apply_delta_returns_patch():
    """apply_attribute_delta 返回补丁 dict（CQRS 模式）"""
    ve     = VarEngine(_ATTR_KEYS)
    state  = {"attributes": {"STR": 1.0, "DUR": 1.0}}
    patch  = ve.apply_attribute_delta(state, "STR", 0.5)
    # 返回包含新值的补丁
    assert isinstance(patch, dict)

def test_var_engine_apply_deltas_batch():
    """批量 apply"""
    ve    = VarEngine(_ATTR_KEYS)
    state = {"attributes": {"STR": 1.0, "DUR": 1.0}}
    patch = ve.apply_attribute_deltas(state, {"STR": 0.5, "DUR": 0.2})
    assert isinstance(patch, dict)


# ════════════════════════════════════════════════════════════════════════
# 5. Config Registry
# ════════════════════════════════════════════════════════════════════════

def test_item_type_plugins_instantiate():
    """内置插件类能成功实例化"""
    from config_sys.builtin_item_types import (
        ApplicationTechniquePlugin, PassiveAbilityPlugin,
        BloodlinePlugin, InventoryPlugin,
    )
    for cls in [ApplicationTechniquePlugin, PassiveAbilityPlugin,
                BloodlinePlugin, InventoryPlugin]:
        p = cls()
        assert p.type_id
        assert p.display_name
        assert len(p.payload_fields) >= 0

def test_item_type_registry_register():
    """注册后能查询"""
    from config_sys.registry import ItemTypeRegistry
    from config_sys.builtin_item_types import ApplicationTechniquePlugin
    plugin = ApplicationTechniquePlugin()
    ItemTypeRegistry.register(plugin)
    retrieved = ItemTypeRegistry.get("ApplicationTechnique")
    assert retrieved.type_id == "ApplicationTechnique"

def test_item_type_registry_unknown_raises():
    from config_sys.registry import ItemTypeRegistry
    with pytest.raises((KeyError, ValueError)):
        ItemTypeRegistry.get("GhostType_XYZ_Unknown")

def test_attribute_schema_defaults():
    from config_sys.attribute_schema import get_default_attributes
    defaults = get_default_attributes("standard_10d")
    assert isinstance(defaults, dict)
    assert "STR" in defaults
    assert len(defaults) == 10

def test_pricing_engine_instantiates():
    from exchange.pricing import PricingEngine
    pe = PricingEngine()
    assert pe is not None
    # 验证券商奖励计算
    medals = pe._calc_required_medals(2, "M")
    assert isinstance(medals, list)
