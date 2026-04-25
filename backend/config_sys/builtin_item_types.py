"""9个内置物品类型插件实现"""
from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from config_sys.item_type_plugin import (
    GrowthConfig,
    ItemTypeField,
    ItemTypePlugin,
)

if TYPE_CHECKING:
    from db.queries import Database


# ── 共用辅助函数 ──────────────────────────────────────────────────────────────

async def _apply_attribute_deltas(
    novel_id: str, deltas: dict, db: "Database", attr_schema_keys: set[str]
) -> None:
    """将属性增量写入 protagonist_state（按 Schema 验证键名）"""
    if not deltas:
        return
    row = await db.get_protagonist_state(novel_id)
    if not row:
        return
    attrs = row.get("attributes") or {}
    for key, delta in deltas.items():
        if key in attr_schema_keys:
            attrs[key] = round(attrs.get(key, 1.0) + delta, 4)
    await db.update_protagonist_state(novel_id, attributes=attrs)


async def _update_protagonist_graph_node(
    novel_id: str, payload: dict, memory: Any
) -> None:
    """更新图谱中的主角 character 节点（若 memory 可用）"""
    if memory is None:
        return
    try:
        await memory.update_protagonist_node(novel_id, payload)
    except Exception:
        pass  # 图谱更新失败不中断主流程


# ════════════════════════════════════════════════════════════════════════════
# 1. ApplicationTechnique — 应用技术（武功/技能）
# ════════════════════════════════════════════════════════════════════════════

class ApplicationTechniquePlugin(ItemTypePlugin):
    type_id = "ApplicationTechnique"
    display_name = "应用技术"
    icon = "⚔️"
    eval_prompt_suffix = (
        "subTechniques 数组中每个招式必须包含 name/type/tier/desc/costInitial/castTime 字段。"
    )

    @property
    def payload_fields(self):
        return [
            ItemTypeField("applicationTechniques", "技能列表", "list", required=True,
                          hint="[{schoolName, school, type, description, subTechniques:[...]}]"),
            ItemTypeField("attributeDeltas", "属性增量", "json", default={},
                          hint="对应当前属性Schema的键值对增量，如{STR:0.5}"),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="sub_item",
            level_names=["入门", "熟练", "精通", "化境"],
            xp_thresholds=[500, 2000, 10000],
            xp_gain_events=["combat_use", "training", "breakthrough"],
        )

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        deltas = effects.get("attributeDeltas", {})
        attr_keys = set(kwargs.get("attr_schema_keys", [
            "STR","DUR","VIT","REC","AGI","REF","PER","MEN","SOL","CHA"
        ]))
        await _apply_attribute_deltas(novel_id, deltas, db, attr_keys)

        for tech in effects.get("applicationTechniques", []):
            school = tech.get("schoolName", "未知技能")
            await db.init_growth_record(novel_id, owned_id, school)
            for sub in tech.get("subTechniques", []):
                sub_name = sub.get("name", "")
                if sub_name:
                    await db.init_growth_record(novel_id, owned_id, school, sub_name)

        await _update_protagonist_graph_node(novel_id, payload, memory)


# ════════════════════════════════════════════════════════════════════════════
# 2. PassiveAbility — 被动能力
# ════════════════════════════════════════════════════════════════════════════

class PassiveAbilityPlugin(ItemTypePlugin):
    type_id = "PassiveAbility"
    display_name = "被动能力"
    icon = "🛡️"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("passives", "被动效果列表", "list", required=True,
                          hint="[{name, effect, trigger_condition, always_on}]"),
            ItemTypeField("attributeDeltas", "常态属性增量", "json", default={}),
            ItemTypeField("auraEffects", "光环效果", "list", default=[],
                          hint="影响同伴/队友的效果列表"),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(enabled=False)

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        deltas = effects.get("attributeDeltas", {})
        attr_keys = set(kwargs.get("attr_schema_keys", [
            "STR","DUR","VIT","REC","AGI","REF","PER","MEN","SOL","CHA"
        ]))
        await _apply_attribute_deltas(novel_id, deltas, db, attr_keys)
        # 被动能力注册（供 DM 合理性验证使用）
        await db._exec(
            "INSERT OR REPLACE INTO owned_items (id,novel_id,item_key,item_type,payload,is_active) "
            "VALUES (?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET is_active=1",
            (owned_id, novel_id, payload.get("item_key",""), "PassiveAbility",
             json.dumps(payload, ensure_ascii=False)),
        )


# ════════════════════════════════════════════════════════════════════════════
# 3. PowerSource — 能量基盘
# ════════════════════════════════════════════════════════════════════════════

class PowerSourcePlugin(ItemTypePlugin):
    type_id = "PowerSource"
    display_name = "能量基盘"
    icon = "⚡"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("powerSources", "能量基盘列表", "list", required=True),
            ItemTypeField("newEnergyPools", "新能量池", "list", required=True,
                          hint="[{name, value, max, regen, description}]"),
            ItemTypeField("attributeDeltas", "属性增量", "json", default={}),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="self",
            level_names=["炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"],
            xp_thresholds=[500, 2000, 8000, 32000, 128000, 512000, 2000000, 8000000],
            xp_gain_events=["cultivation", "combat", "enlightenment"],
        )

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        attr_keys = set(kwargs.get("attr_schema_keys", [
            "STR","DUR","VIT","REC","AGI","REF","PER","MEN","SOL","CHA"
        ]))
        await _apply_attribute_deltas(novel_id, effects.get("attributeDeltas", {}), db, attr_keys)
        for pool in effects.get("newEnergyPools", []):
            await db.register_energy_pool(novel_id, pool)
        # 以体系名作为 growth_key
        for src in effects.get("powerSources", []):
            src_name = src.get("name", "体系")
            await db.init_growth_record(novel_id, owned_id, src_name)


# ════════════════════════════════════════════════════════════════════════════
# 4. Bloodline — 血统/传承
# ════════════════════════════════════════════════════════════════════════════

class BloodlinePlugin(ItemTypePlugin):
    type_id = "Bloodline"
    display_name = "血统/传承"
    icon = "🩸"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("bloodlineName", "血统名称", "string", required=True),
            ItemTypeField("bloodlineRank", "血统等阶", "string", default="劣质",
                          hint="劣质/普通/优良/稀有/传说/神话"),
            ItemTypeField("awakening_stages", "觉醒阶段列表", "list", required=True,
                          hint="[{stage_name, unlock_condition, new_abilities, attribute_amplification}]"),
            ItemTypeField("innate_passives", "天生被动", "list", default=[]),
            ItemTypeField("attribute_amplification", "属性放大系数", "json", default={},
                          hint="永久放大系数，如{STR:1.2}"),
            ItemTypeField("bloodline_conflicts", "血统冲突列表", "list", default=[]),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="self",
            level_names=["初觉", "二觉", "三觉", "完全觉醒", "血统融合"],
            xp_thresholds=[1000, 5000, 20000, 100000],
            xp_gain_events=["bloodline_resonance", "ancestor_trial", "bloodline_battle"],
        )

    @property
    def allows_multiple(self): return False

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        # 属性放大（乘法）
        amp = effects.get("attribute_amplification", {})
        if amp:
            row = await db.get_protagonist_state(novel_id)
            attrs = row.get("attributes", {}) if row else {}
            attr_keys = set(kwargs.get("attr_schema_keys",
                                       list(attrs.keys())))
            for key, factor in amp.items():
                if key in attr_keys:
                    attrs[key] = round(attrs.get(key, 1.0) * factor, 4)
            await db.update_protagonist_state(novel_id, attributes=attrs)

        bl_name = effects.get("bloodlineName", "未知血统")
        await db.init_growth_record(novel_id, owned_id, bl_name)


# ════════════════════════════════════════════════════════════════════════════
# 5. Mech — 机甲/载具
# ════════════════════════════════════════════════════════════════════════════

class MechPlugin(ItemTypePlugin):
    type_id = "Mech"
    display_name = "机甲/载具"
    icon = "🤖"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("mechName",     "机体名称", "string", required=True),
            ItemTypeField("mechClass",    "机体级别", "string", default="量产型",
                          hint="量产型/精英型/王牌专属/传说机体/神器级"),
            ItemTypeField("mechAttributes", "机体属性面板", "json", required=True,
                          hint="使用 mech_6d Schema 的属性键值对"),
            ItemTypeField("weapons",      "武装列表", "list", required=True,
                          hint="[{name, type, damage, range, ammo, special}]"),
            ItemTypeField("systems",      "系统模块", "list", default=[]),
            ItemTypeField("pilot_interface", "驾驶员接口", "string", default="标准"),
            ItemTypeField("energy_core",  "能源核心", "json", default={}),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="self",
            level_names=["原型机", "标准型", "改良型", "王牌型", "超级机体"],
            xp_thresholds=[2000, 10000, 50000, 200000],
            xp_gain_events=["mech_combat", "maintenance", "system_upgrade"],
        )

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        mech_name = effects.get("mechName", "未知机体")
        await db.init_growth_record(novel_id, owned_id, mech_name)


# ════════════════════════════════════════════════════════════════════════════
# 6. Inventory — 物品/道具
# ════════════════════════════════════════════════════════════════════════════

class InventoryPlugin(ItemTypePlugin):
    type_id = "Inventory"
    display_name = "物品/道具"
    icon = "🎒"

    @property
    def allows_multiple(self): return True

    @property
    def payload_fields(self):
        return [
            ItemTypeField("itemName",     "物品名称", "string", required=True),
            ItemTypeField("quantity",     "数量",    "number", default=1),
            ItemTypeField("usageEffect",  "使用效果", "string"),
            ItemTypeField("usageLimit",   "使用次数", "number", default=-1,
                          hint="-1=无限次"),
            ItemTypeField("consumable",   "是否消耗品", "boolean", default=False),
            ItemTypeField("passiveEffect", "持有被动", "json", default=None),
        ]

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        # 物品无需额外初始化，payload 已通过 owned_items 存储
        pass


# ════════════════════════════════════════════════════════════════════════════
# 7. Companion — 同伴
# ════════════════════════════════════════════════════════════════════════════

class CompanionPlugin(ItemTypePlugin):
    type_id = "Companion"
    display_name = "同伴"
    icon = "👤"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("name",            "同伴姓名",   "string", required=True),
            ItemTypeField("sourceWorld",      "来源世界",   "string", required=True),
            ItemTypeField("initialAffinity",  "初始好感度", "number", default=50,
                          hint="0-100，影响同伴可靠程度"),
            ItemTypeField("loyaltyType",      "忠诚类型",   "string", default="自愿型",
                          hint="合约型|自愿型|强制型|家族型"),
            ItemTypeField("personality",      "性格描述",   "string", required=True),
            ItemTypeField("abilities",        "同伴能力",   "list",   default=[]),
            ItemTypeField("revivePrice",      "复活价倍率", "number", default=0.3,
                          hint="复活积分 = 购买价 × 此倍率"),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="self",
            level_names=["陌路人", "相识", "朋友", "挚友", "羁绊"],
            xp_thresholds=[100, 500, 2000, 10000],
            xp_gain_events=["adventure_together", "save_companion", "deep_conversation"],
        )

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        companion_name = effects.get("name", "未知同伴")
        # 将同伴写入 NPC 档案
        await db.upsert_npc(novel_id, companion_name, {
            "npc_type": "companion",
            "trait_lock": [effects.get("personality", "")],
            "knowledge_scope": [],
            "psyche_model": {
                "affinity": effects.get("initialAffinity", 50),
                "loyalty_type": effects.get("loyaltyType", "自愿型"),
                "personality": effects.get("personality", ""),
            },
        })
        await db.init_growth_record(novel_id, owned_id, companion_name)


# ════════════════════════════════════════════════════════════════════════════
# 8. Knowledge — 知识/记忆
# ════════════════════════════════════════════════════════════════════════════

class KnowledgePlugin(ItemTypePlugin):
    type_id = "Knowledge"
    display_name = "知识/记忆"
    icon = "📚"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("knowledgeName", "知识名称", "string", required=True),
            ItemTypeField("domain",        "知识领域", "string", required=True,
                          hint="如：医学/军事/炼丹/符文/语言"),
            ItemTypeField("proficiency",   "初始熟练度", "string", default="入门"),
            ItemTypeField("unlocks",       "解锁内容描述", "string"),
            ItemTypeField("knowledgeScope", "写入主角知识范围", "boolean", default=True),
        ]

    @property
    def growth_config(self):
        return GrowthConfig(
            enabled=True,
            xp_entity="self",
            level_names=["入门", "熟练", "精通", "大师"],
            xp_thresholds=[200, 1000, 5000],
            xp_gain_events=["study", "practice", "enlightenment"],
        )

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        k_name = effects.get("knowledgeName", "未知知识")
        if effects.get("knowledgeScope", True):
            await db.append_protagonist_knowledge(novel_id, k_name)
        await db.init_growth_record(novel_id, owned_id, k_name)


# ════════════════════════════════════════════════════════════════════════════
# 9. WorldTraverse — 穿越通道
# ════════════════════════════════════════════════════════════════════════════

class WorldTraversePlugin(ItemTypePlugin):
    type_id = "WorldTraverse"
    display_name = "穿越通道"
    icon = "🌌"

    @property
    def payload_fields(self):
        return [
            ItemTypeField("targetWorldKey",  "目标世界Key",  "string", required=True),
            ItemTypeField("targetWorldName", "目标世界名称", "string", required=True),
            ItemTypeField("lockDays",        "锚点锁定天数", "number", default=30),
            ItemTypeField("timeFlowRatio",   "时间流速比",   "string", default="1:1"),
            ItemTypeField("identityPackage", "身份包（可选）", "json",   default=None),
        ]

    async def on_purchase(self, novel_id, owned_id, payload, db, memory, **kwargs):
        effects = payload.get("effects", payload)
        world_key = effects.get("targetWorldKey", "unknown_world")
        world_name = effects.get("targetWorldName", world_key)
        time_ratio = effects.get("timeFlowRatio", "1:1")
        # 创建世界档案（如果不存在）
        await db.upsert_world_archive(novel_id, world_key, {
            "world_name": world_name,
            "time_flow_ratio": time_ratio,
            "identity": effects.get("identityPackage"),
        })
