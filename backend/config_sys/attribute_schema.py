"""属性体系（Schema）定义 — 支持任意维度扩展"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AttributeCategory(str, Enum):
    PHYSICAL = "physical"   # 物理类
    MENTAL   = "mental"     # 精神类
    SOCIAL   = "social"     # 社交类（默认不计入战斗星级）
    ENERGY   = "energy"     # 能量类
    SPECIAL  = "special"    # 特殊类


@dataclass
class AttributeDef:
    key: str
    name: str
    category: AttributeCategory
    definition: str
    extract_positive: str = ""
    extract_negative: str  = ""
    base_value: float = 1.0
    count_in_tier: bool = True
    display_order: int = 0


@dataclass
class AttributeSchemaConfig:
    schema_id: str
    name: str
    description: str
    attributes: list[AttributeDef]
    # 覆盖维度降级映射: (低, 高) -> 降级档数
    coverage_degrade_map: dict = field(default_factory=lambda: {
        (8, 10): 0,
        (6, 7):  1,
        (3, 5):  3,
        (1, 2):  6,
        (0, 0):  9,
    })

    def get_keys(self) -> list[str]:
        return [a.key for a in self.attributes]

    def get_tier_keys(self) -> list[str]:
        """仅返回计入战斗星级的属性键"""
        return [a.key for a in self.attributes if a.count_in_tier]

    def default_values(self) -> dict[str, float]:
        return {a.key: a.base_value for a in self.attributes}

    def get_degrade(self, covered_dims: int) -> int:
        for (lo, hi), deg in self.coverage_degrade_map.items():
            if lo <= covered_dims <= hi:
                return deg
        return 9  # 兜底


# ─── 内置三套属性体系 ─────────────────────────────────────────────────────────

def _build_standard_10d() -> AttributeSchemaConfig:
    return AttributeSchemaConfig(
        schema_id="standard_10d",
        name="标准十维体系",
        description="来自兑换规格_v1.md，适用于通用现代/玄幻世界观",
        attributes=[
            AttributeDef("STR", "力量",   AttributeCategory.PHYSICAL,
                "纯物理破坏力与肌肉力量（不含能量加持）",
                "最大物理输出记录", "被防御/结构挡住的失败案例", display_order=0),
            AttributeDef("DUR", "耐力",   AttributeCategory.PHYSICAL,
                "对物理伤害的直接承受与结构抵抗",
                "承受最高伤害而存活", "被明确重创/贯穿", display_order=1),
            AttributeDef("VIT", "体质",   AttributeCategory.PHYSICAL,
                "生命力总量、自然毒素/环境抵抗",
                "持续战斗时间/毒素抵抗上限", "因伤/毒明显衰弱", display_order=2),
            AttributeDef("REC", "恢复",   AttributeCategory.PHYSICAL,
                "纯被动生物恢复速率",
                "已知最快被动愈合速度", "长期未愈/需外部干预", display_order=3),
            AttributeDef("AGI", "敏捷",   AttributeCategory.PHYSICAL,
                "移动速度与物理位移能力",
                "最快位移速度记录", "被同量级攻击命中", display_order=4),
            AttributeDef("REF", "反应",   AttributeCategory.PHYSICAL,
                "神经反应速度与战场读取能力",
                "最快反应成功记录", "被高速攻击打中", display_order=5),
            AttributeDef("PER", "感知",   AttributeCategory.MENTAL,
                "自然五感敏锐范围（不含超凡感知）",
                "感知范围/精度最高记录", "被靠近未察觉", display_order=6),
            AttributeDef("MEN", "精神",   AttributeCategory.MENTAL,
                "精神力的量 — 精神能量总量、意志力强度",
                "最高精神承受表现", "精神崩溃/洗脑成功", display_order=7),
            AttributeDef("SOL", "灵魂",   AttributeCategory.MENTAL,
                "灵魂的质 — 存在本质位格强度",
                "灵魂位格强度（对即死抵抗）", "灵魂/存在受损成功", display_order=8),
            AttributeDef("CHA", "魅力",   AttributeCategory.SOCIAL,
                "外貌气质与自然语言影响力",
                "最强自然影响力", "魅力失效/被忽视",
                count_in_tier=False, display_order=9),
        ],
    )


def _build_cultivation_8d() -> AttributeSchemaConfig:
    cov = {(6, 8): 0, (4, 5): 1, (2, 3): 3, (1, 1): 5, (0, 0): 8}
    return AttributeSchemaConfig(
        schema_id="cultivation_8d",
        name="修仙八维体系",
        description="适用于东方修仙世界观",
        attributes=[
            AttributeDef("FLESH",  "肉身", AttributeCategory.PHYSICAL, "肉体强度和防御", display_order=0),
            AttributeDef("SPIRIT", "神识", AttributeCategory.MENTAL,   "神识强度和范围", display_order=1),
            AttributeDef("SWORD",  "剑意", AttributeCategory.SPECIAL,  "剑道领悟深度",   display_order=2),
            AttributeDef("LING",   "灵力", AttributeCategory.ENERGY,   "灵力储量",       display_order=3),
            AttributeDef("FATE",   "气运", AttributeCategory.SPECIAL,  "天命与机缘权重",
                         count_in_tier=False, display_order=4),
            AttributeDef("SPEED",  "身法", AttributeCategory.PHYSICAL, "移动速度与闪避", display_order=5),
            AttributeDef("WILL",   "道心", AttributeCategory.MENTAL,   "心境稳定度",     display_order=6),
            AttributeDef("KARMA",  "因果", AttributeCategory.SPECIAL,  "因果纬度影响力", display_order=7),
        ],
        coverage_degrade_map=cov,
    )


def _build_mech_6d() -> AttributeSchemaConfig:
    cov = {(5, 6): 0, (3, 4): 1, (1, 2): 4, (0, 0): 8}
    return AttributeSchemaConfig(
        schema_id="mech_6d",
        name="机甲六维体系",
        description="适用于科幻机甲世界观，属性对应机体性能参数",
        attributes=[
            AttributeDef("OUTPUT", "输出", AttributeCategory.PHYSICAL, "武器系统总火力",   display_order=0),
            AttributeDef("ARMOR",  "装甲", AttributeCategory.PHYSICAL, "装甲防护等级",     display_order=1),
            AttributeDef("SPEED",  "机动", AttributeCategory.PHYSICAL, "机体移动与闪避",   display_order=2),
            AttributeDef("SENSOR", "传感", AttributeCategory.MENTAL,   "感知与目标锁定",   display_order=3),
            AttributeDef("HACK",   "电战", AttributeCategory.SPECIAL,  "电子战与入侵能力", display_order=4),
            AttributeDef("PILOT",  "驾驶", AttributeCategory.SPECIAL,  "驾驶员与机体协同",
                         count_in_tier=False, display_order=5),
        ],
        coverage_degrade_map=cov,
    )


# 内置字典（schema_id -> config）
BUILTIN_SCHEMAS: dict[str, AttributeSchemaConfig] = {
    "standard_10d":   _build_standard_10d(),
    "cultivation_8d": _build_cultivation_8d(),
    "mech_6d":        _build_mech_6d(),
}


def get_default_attributes(schema_id: str = "standard_10d") -> dict[str, float]:
    """返回指定体系的默认属性值字典"""
    schema = BUILTIN_SCHEMAS.get(schema_id) or BUILTIN_SCHEMAS["standard_10d"]
    return schema.default_values()
