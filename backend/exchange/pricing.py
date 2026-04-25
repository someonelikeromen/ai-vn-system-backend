"""
三轮评估协议 + Tier价格表 + Decay System
精确来自 兑换熟练度系统规格_v1.md §1.2 §2.1 §2.2 §2.3
"""
from __future__ import annotations

import math
import random
from typing import Optional
from loguru import logger


# ════════════════════════════════════════════════════════════════════════════
# TIER_BASE_PRICES — 星级基准积分表
# 来源：规格 §2.2  子档 L:M:U = 1:1.6:2.5，每主星级 ×4
# 子档命名统一为 L（下）/ M（中）/ U（上），与规格一致
# 0★~15★ 为正常兑换范围；16★/17★ 系统保留，不在此表
# ════════════════════════════════════════════════════════════════════════════

TIER_BASE_PRICES: dict[int, dict[str, int]] = {
    0:  {"L": 80,              "M": 100,              "U": 160},
    1:  {"L": 320,             "M": 500,              "U": 800},
    2:  {"L": 1_280,           "M": 2_000,            "U": 3_200},
    3:  {"L": 5_120,           "M": 8_000,            "U": 12_800},
    4:  {"L": 20_480,          "M": 32_000,           "U": 51_200},
    5:  {"L": 81_920,          "M": 128_000,          "U": 204_800},
    6:  {"L": 327_680,         "M": 512_000,          "U": 819_200},
    7:  {"L": 1_310_720,       "M": 2_048_000,        "U": 3_276_800},
    8:  {"L": 5_242_880,       "M": 8_192_000,        "U": 13_107_200},
    9:  {"L": 20_971_520,      "M": 32_768_000,       "U": 52_428_800},
    10: {"L": 83_886_080,      "M": 131_072_000,      "U": 209_715_200},
    11: {"L": 335_544_320,     "M": 524_288_000,      "U": 838_860_800},
    12: {"L": 1_342_177_280,   "M": 2_097_152_000,    "U": 3_355_443_200},
    13: {"L": 5_368_709_120,   "M": 8_388_608_000,    "U": 13_421_772_800},
    14: {"L": 21_474_836_480,  "M": 33_554_432_000,   "U": 53_687_091_200},
    15: {"L": 85_899_345_920,  "M": 134_217_728_000,  "U": 214_748_364_800},
}

# 子档排序（用于比较大小）
TIER_SUB_RANK = {"L": 0, "M": 1, "U": 2}

# 子档别名（旧代码/LLM 可能输出 P/E/H/低大写）
TIER_SUB_NORMALIZE: dict[str, str] = {
    "L": "L", "l": "L",
    "M": "M", "m": "M", "P": "M", "p": "M",   # P→M 旧格式兼容
    "U": "U", "u": "U", "E": "U", "e": "U", "H": "U", "h": "U",  # E→U 旧格式兼容
}

# GD 折扣因子（种子态，规格 §2.3 第二轮 C）
GD_FACTORS: dict[str, float] = {
    "GD-0": 0.55,
    "GD-1": 0.40,
    "GD-2": 0.25,
    "GD-3": 0.12,
    "GD-4": 0.04,
}

# 覆盖维度降级步数（规格 §2.3 1C）
# key: (lo, hi) 覆盖维度数范围；value: 降级步数（1步=1档，3步=1星）
# 0维度特殊：不走降级，进入 Hax 独立定价通道
COVERAGE_DEGRADE_MAP: dict[tuple[int, int], int] = {
    (8, 10): 0,
    (6, 7):  1,
    (3, 5):  3,
    (1, 2):  6,
}
HAX_ONLY_DIMS = 0  # covered_dims == 0 时走 Hax 独立通道


# ── Tier 工具函数 ────────────────────────────────────────────────────────────

def normalize_tier_sub(sub: str) -> str:
    return TIER_SUB_NORMALIZE.get(sub, "M")


def tier_rank(tier: int, sub: str) -> float:
    """将 (tier, sub) 转换为可比较的浮点数"""
    sub_n = TIER_SUB_RANK.get(normalize_tier_sub(sub), 1)
    return tier + sub_n / 3.0


def parse_tier_string(s: str) -> tuple[int, str]:
    """'3★M' / '3M' / '3★L' / '3L' → (3, 'L')"""
    import re
    m = re.search(r'(\d+)[★*]?\s*([LlMmPpUuEeHh])', s)
    if m:
        return int(m.group(1)), normalize_tier_sub(m.group(2))
    return 0, "M"


def apply_tier_degrade(tier: int, sub: str, steps: int) -> tuple[int, str]:
    """将 (tier, sub) 降级 steps 步（L→M→U 为一星内升，3步=1主星级）"""
    sub = normalize_tier_sub(sub)
    sub_order = ["L", "M", "U"]
    idx = tier * 3 + sub_order.index(sub)
    idx = max(0, idx - steps)
    return idx // 3, sub_order[idx % 3]


def get_coverage_degrade(covered_dims: int) -> int:
    """返回覆盖维度对应的降级步数；0维度返回 -1（标记为Hax通道）"""
    if covered_dims == HAX_ONLY_DIMS:
        return -1  # 特殊标记：走 Hax 独立通道
    for (lo, hi), deg in COVERAGE_DEGRADE_MAP.items():
        if lo <= covered_dims <= hi:
            return deg
    return 9  # 超出范围的兜底


def determine_final_tier_from_price(price: int) -> tuple[int, str]:
    """根据最终积分反查对应星级（找不超过 price 的最高档）"""
    best_tier, best_sub = 0, "L"
    best_price = 0
    for tier, subs in TIER_BASE_PRICES.items():
        for sub, bp in subs.items():
            if bp <= price and bp > best_price:
                best_price = bp
                best_tier, best_sub = tier, sub
    return best_tier, best_sub


def calculate_final_price_with_modifiers(base: int, modifiers: dict) -> int:
    """
    乘法模型连乘修正：最终积分 = 基准分 × (1 + Hax修正) × 修正因子A × 修正因子B × ...
    规格 §2.3 第二轮：每个独立修正正向=(1+系数)，负向=(1-|系数|)
    """
    mult = 1.0
    # Hax 修正（加法进 mult）
    hax_hi = modifiers.get("hax_hi", 0)
    if isinstance(hax_hi, (int, float)):
        hax_bonus = _hax_hi_to_modifier(int(hax_hi))
        mult *= (1.0 + hax_bonus)

    # 其他修正项（各自乘法）
    skip_keys = {"hax_hi", "gd_level", "eval_notes", "target_tier", "target_tier_sub"}
    for k, v in modifiers.items():
        if k in skip_keys:
            continue
        if isinstance(v, (int, float)) and v != 0:
            mult *= (1.0 + float(v))

    result = int(base * max(0.01, mult))
    return max(1, result)  # 兑换最低1分


def _hax_hi_to_modifier(hi: int) -> float:
    """规格 §2.3 第二轮 B：Hax HI 转修正系数"""
    table = {
        -1: -0.10,
         0:  0.10,
         1:  0.50,
         2:  1.50,
         3:  4.00,
         4:  9.00,
    }
    if hi in table:
        return table[hi]
    if hi >= 5:
        return 20.00  # +2000%（取下限）
    return -0.10  # hi <= -1


# ════════════════════════════════════════════════════════════════════════════
# LLM Prompts
# ════════════════════════════════════════════════════════════════════════════

# ── Round 1A System Prompt ──────────────────────────────────────────────────

ROUND_1A_SYSTEM = """
你是严格的战力评估专家，执行「兑换系统三轮评估协议 · 第一轮」。
你的每一项判断必须有原著明确依据，严禁凭空推论。

═══════════════════════════════════════════════════════
【属性提纯铁律】
- 技能/宝具/法则激活产生的增幅 → 必须剥离，只计基础态
- 需消耗能量维持的增幅 → 剥离
- 超凡感知（预知/读心）→ 剥离，归 PassiveAbility
- 物种天生物理特性（龙族皮后）→ 保留

═══════════════════════════════════════════════════════
【有效壮举时间门槛（Hard Time Gate）】
破坏类表现必须在 1 分钟内完成，方可采信为对应量级的正向依据。
以下情况【不计入】正向依据（可降星使用或记为"有条件上限"）：
  • 需持续攻击 >1分钟才累积完成破坏 → 降至实际1分钟内完成的量级
  • 需蓄力/充能 >1分钟后单次释放 → 蓄力本身不计量级；输出若在1分内完成则按输出量级，但加注"蓄力条件"
  • 明确描述为"长时间持续作用"的法则效果 → 视为 Hax 类型，不与属性破坏力对标
  • 借助特殊环境/一次性条件完成的超量破坏 → 标注"特殊条件壮举"，不计入常规属性定级

═══════════════════════════════════════════════════════
【10项属性的双向依据类型】
| 属性 | 正向依据（下限）| 反向依据（上限）|
|-----|--------------|--------------|
| STR | 最大物理输出记录 | 被某级防御/结构挡住 |
| DUR | 承受最高伤害而存活 | 被明确重创/贯穿 |
| VIT | 持续战斗时间/毒素抵抗上限 | 因伤/毒/环境明显衰弱 |
| REC | 已知最快被动愈合速度 | 长期未愈/必须外部干预 |
| AGI | 最快位移速度记录 | 被同量级攻击命中（纯移速角度）|
| REF | 最快反应成功（预判/拦截）| 被高速攻击打中（纯反应角度）|
| PER | 感知范围/精度最高记录 | 被靠近未察觉/感知被遮蔽 |
| MEN | 最高精神承受/意志强度表现 | 精神崩溃/洗脑成功 |
| SOL | 灵魂位格强度（对即死/侵蚀抵抗）| 灵魂/存在受损成功 |
| CHA | 最强自然影响力 | 魅力失效/被忽视 |
规则：以最低可信反向表现作为上限；叙事性失败同样采信（实证主义原则）。
无反向表现则根据整体量级推断上限，标注"推断"。

═══════════════════════════════════════════════════════
【属性值区间对照（0★~15★）】
0★: 1~2      | 1★: 2~20      | 2★: 20~100    | 3★: 100~500
4★: 500~2K   | 5★: 2K~10K    | 6★: 10K~50K   | 7★: 50K~200K
8★: 200K~1M  | 9★: 1M~10M    | 10★: 10M~100M | 11★: 100M~1B
12★: 1B~10B  | 13★: 10B~1T   | 14★: 1T~1000T | 15★: 1000T~不可测

子档定义（同一主星级内，以单项最高提纯值在区间内的位置）：
  L（下）：区间前 33%  |  M（中）：区间 34%~66%  |  U（上）：区间后 33%

═══════════════════════════════════════════════════════
【严禁推论（以下推断链条一律拒绝）】
  ✗ 恢复快 ≠ 无限能量
  ✗ 速度快 ≠ 超越因果
  ✗ STR高 ≠ 概念层面破坏
  ✗ 战胜强者 ≠ 属性与强者相同（可能靠技巧/Hax）
  ✗ 承受了某攻击 ≠ 对所有相同量级攻击免疫

═══════════════════════════════════════════════════════
【1C 功能维度判定（输出 covered_dimensions 字段后必须说明降级应用）】
  8~10维度且均衡 → 不降级
  6~7维度，1~2个达峰 → -1档
  3~5维度 → -1星级（-3档）
  1~2维度 → -2星级（-6档）
  0维度（纯 Hax/功能型）→ 进入 Hax 独立定价通道（不以属性定星级）

【1D 实战模拟裁判】（在属性维度>0时执行）
  一名持有该能力的 0★ 人类，对阵纯体能达到该星级的人类，胜率是否≥50%？
  胜率 ≥ 50% → 维持；胜率 < 50% → 下调至可合理获胜的最高级
  ⚠️ 1D 只能维持或下调，不能上调。
"""

ROUND_1A_USER_TEMPLATE = """
评估对象：{item_name}
来源宇宙：{source_world}

原著描述参考：
{lore_context}

━━━━━ 请执行完整 1A 评估 ━━━━━

Step 1：属性提纯（剥离技能/能量增幅，保留天生物种特性）
Step 2：找出每项属性的正向依据（下限）和反向依据（上限），标注关键原著事件
Step 3：估算提纯数值范围，对应子档（L/M/U）
Step 4：统计覆盖维度数（提纯后超过基准1.0的属性数，CHA不计入战斗维度）
Step 5：依据1C降级规则确定临时星级
Step 6：执行1D实战模拟裁判（维度>0时必须执行）

输出格式（JSON）：
{{
  "item_name": "{item_name}",
  "source_world": "{source_world}",
  "purification_notes": ["剥离了XXX技能加成", "保留了XXX物种特性"],
  "attributes": {{
    "STR": {{
      "lower_bound": "正向依据摘要（引用原著事件）",
      "upper_bound": "反向依据摘要（或'推断：基于整体量级'）",
      "purified_range": "X~Y",
      "tier_estimate": "X★L/M/U",
      "evidence": "关键原著依据（1~2句）"
    }},
    "DUR": {{}},
    "VIT": {{}},
    "REC": {{}},
    "AGI": {{}},
    "REF": {{}},
    "PER": {{}},
    "MEN": {{}},
    "SOL": {{}},
    "CHA": {{}}
  }},
  "covered_dimensions": 7,
  "peak_attr": "STR",
  "peak_tier_estimate": "3★M",
  "degrade_steps": 0,
  "temp_tier": 3,
  "temp_tier_sub": "M",
  "round_1d_verdict": "MAINTAIN",
  "round_1d_reason": "一句话说明",
  "final_temp_tier": 3,
  "final_temp_tier_sub": "M",
  "is_hax_only": false
}}
"""

# ── Round 1D Prompt（独立调用备用，PricingEngine 优先用1A内置结果）─────────

ROUND_1D_PROMPT = """
简短实战验证（仅回答 MAINTAIN 或 DOWNGRADE）：

一名持有「{item_name}」能力的普通人（0★），
对阵纯体能达到 {temp_tier}★{temp_tier_sub} 的人类，
在标准对抗条件下，胜率是否合理（≥50%）？

⚠️ 1D 只能维持或下调，不能上调。

输出格式（JSON）：
{{
  "verdict": "MAINTAIN | DOWNGRADE",
  "reason": "一句话理由",
  "suggested_tier": "{temp_tier}★{temp_tier_sub}（如MAINTAIN）或 X★L/M/U（如DOWNGRADE）"
}}
"""

# ── Round 2 Prompt ──────────────────────────────────────────────────────────

ROUND_2_SYSTEM = """
你是兑换系统价格修正评估专家，执行「三轮评估协议 · 第二轮」。
根据能力特性评估各修正维度，输出精确系数（必须使用以下规定数值，不得自由发挥）。

═══════════════════════════════════════════════════════
【修正系数精确表（规格 §2.3 第二轮修正维度总表 v1）】

A. 生命力类（值=修正系数，正数=涨价）
  寿命-长寿（数百年）: +0.05
  寿命-不老: +0.10
  再生-轻微（数小时愈合骨折）: +0.10
  再生-中度（生物级器官再生）: +0.30
  再生-强力（秒速再生断肢）: +0.50
  伪不死（死后可复活，有条件）: +1.00
  真不死（概念层面无法消灭）: +3.00 ~ +10.00（视程度）
  主动防御（需消耗能量的防护盾）: +0.20

B. Hax 等级（HI = Hax Impact，有效跨级数）
  HI ≤ -1: -0.10  （仅对低星级目标有效）
  HI = 0:  +0.10  （可作用于同星级目标，基准）
  HI = +1: +0.50  （可跨越1星作用于更强目标）
  HI = +2: +1.50
  HI = +3: +4.00
  HI = +4: +9.00
  HI ≥ +5: +20.00 （取下限，需原作强力支持）
  ⚠️ HI 为绝对标准，与使用者当前星级无关

C. 成长潜力折扣（GD，仅适用于"种子态/初始态"能力）
  GD-0（自然晋升，活着就能到顶）: 目标完整价格 × 0.55
  GD-1（训练驱动，常规条件可达）: 目标完整价格 × 0.40
  GD-2（有条件成长，需特定机遇）: 目标完整价格 × 0.25
  GD-3（稀有条件，难触发）: 目标完整价格 × 0.12
  GD-4（极限条件，几乎不可能）: 目标完整价格 × 0.04
  ⚠️ GD折扣计算：种子价格 = 目标成长态完整价格 × GD折扣因子 × (其他修正因子连乘)
  ⚠️ 如该能力是种子态，必须在 gd_level 字段输出 {"level":"GD-X","target_tier":N,"target_tier_sub":"M"}

D. 副作用类（负值=减价）
  副作用-轻微（短暂不适/小量反噬）: -0.10
  副作用-中度（明显代价，影响后续行动）: -0.30
  副作用-严重（危及生命/不可逆损伤风险）: -0.40

E. 前置条件类
  前置条件-普通（需常见资源/基础修炼）: -0.10
  前置条件-稀有（需稀有材料/特殊体质）: -0.30
  前置条件-极端（需极稀有条件/其他高星技能）: -0.50

F. 发动条件类（瞬发为基准，±0%）
  发动速度-瞬发（无需准备，即时触发）: 0.00（基准）
  发动速度-中（需短暂准备 1~5秒）: -0.10
  发动速度-慢（需咏唱/蓄力/仪式 >5秒）: -0.30
  使用条件（需特定环境/时机才能激活）: -0.10 ~ -0.30

G. 持续性类
  持续性-消耗品（一次性使用后消失）: -0.80
  持续性-有限次（N次使用）: -(1.0 - N×0.10)，最低 -0.60

H. 通用性与可反制性类
  范围限制（效果仅在特定环境/条件生效）: -0.10 ~ -0.30
  可反制性-明显（存在明确且常见的克制手段）: -0.15
  可反制性-极端（单一明确的致命克制，如日轮vs鬼）: -0.30
  专属性-血统（仅特定血统可使用）: -0.20
  专属能力（仅特定存在可持有）: -0.15

═══════════════════════════════════════════════════════
【重要：乘法模型】
最终积分 = 基准分 × (1 + Hax修正) × 修正因子A × 修正因子B × ...
不使用加法累积！每项修正独立乘法叠加。
未适用的修正项一律输出 0，不要省略字段。
"""

ROUND_2_USER_TEMPLATE = """
临时星级（第一轮结果）：{temp_tier}★{temp_tier_sub}
基准积分：{base_price}

能力描述：
{item_description}

请依照规定系数表，为以下各修正项提供精确系数值。
如该能力是种子态，gd_level 字段务必填写 {{"level":"GD-X","target_tier":N,"target_tier_sub":"L/M/U"}}。

输出格式（JSON）：
{{
  "hax_hi": 0,
  "longevity": 0,
  "regeneration": 0,
  "pseudo_immortal": 0,
  "true_immortal": 0,
  "active_defense": 0,
  "gd_level": null,
  "side_effect": 0,
  "prerequisite": 0,
  "cast_speed": 0,
  "durability": 0,
  "range_limit": 0,
  "counterability": 0,
  "exclusivity_bloodline": 0,
  "exclusivity_entity": 0,
  "eval_notes": "重要修正说明（说明最关键的1~3项修正理由）"
}}
"""


# ════════════════════════════════════════════════════════════════════════════
# PricingEngine — 三轮评估协议实现
# ════════════════════════════════════════════════════════════════════════════

class PricingEngine:
    """
    三轮评估协议实现（规格 §2.3）。
    Round 1A: LLM 逐属性评估（内置 1B/1C/1D）
    Round 2:  LLM 修正项 + Python 乘法结算
    Round 3:  价格→星级反查（含 Knowledge/WorldTraverse/Hax 特殊通道）
    """

    async def evaluate(
        self,
        item_name: str,
        source_world: str,
        lore_context: str,
        item_description: str,
        item_type: str = "PassiveAbility",
        schema_id: str = "standard_10d",
    ) -> dict:
        """执行完整三轮评估，返回最终评估报告。"""
        from utils.llm_client import get_llm_client
        llm = get_llm_client()

        # ── Round 1A（含内置 1B/1C/1D）───────────────────────────────────────
        logger.info(f"[PricingEngine] Round 1A: {item_name}")
        round_1a_user = ROUND_1A_USER_TEMPLATE.format(
            item_name=item_name,
            source_world=source_world,
            lore_context=lore_context or "（无额外原著描述）",
        )
        round_1a = await llm.chat_json(
            messages=[
                {"role": "system", "content": ROUND_1A_SYSTEM},
                {"role": "user",   "content": round_1a_user},
            ],
            role="exchange",
            temperature=0.2,
        )

        # 解析 1A 结果
        is_hax_only = bool(round_1a.get("is_hax_only", False))
        covered_dims = int(round_1a.get("covered_dimensions", 0))
        temp_tier = int(round_1a.get("final_temp_tier", round_1a.get("temp_tier", 0)))
        temp_sub  = normalize_tier_sub(
            round_1a.get("final_temp_tier_sub", round_1a.get("temp_tier_sub", "M"))
        )

        # 兜底：若 LLM 未输出 is_hax_only 但 covered_dims==0，补正
        if covered_dims == 0:
            is_hax_only = True

        # ── Knowledge 类型特殊通道：整体星级下调3档 ──────────────────────────
        if item_type == "Knowledge" and not is_hax_only:
            temp_tier, temp_sub = apply_tier_degrade(temp_tier, temp_sub, 3)
            logger.info(f"[PricingEngine] Knowledge类型下调3档→ {temp_tier}★{temp_sub}")

        # ── Round 2: 修正项 + Python 乘法 ─────────────────────────────────────
        logger.info(f"[PricingEngine] Round 2: {item_name} (temp={temp_tier}★{temp_sub})")

        if is_hax_only:
            # Hax 独立定价通道：基准 = 目标星级中档M
            hax_target_tier = temp_tier  # LLM 应在 1A 中给出 Hax 有效作用的最高目标星级
            base_price = TIER_BASE_PRICES.get(hax_target_tier, {}).get("M", 100)
        else:
            base_price = TIER_BASE_PRICES.get(temp_tier, {}).get(temp_sub, 100)

        round_2_user = ROUND_2_USER_TEMPLATE.format(
            temp_tier=temp_tier,
            temp_tier_sub=temp_sub,
            base_price=base_price,
            item_description=item_description or "（无额外描述）",
        )
        try:
            modifiers = await llm.chat_json(
                messages=[
                    {"role": "system", "content": ROUND_2_SYSTEM},
                    {"role": "user",   "content": round_2_user},
                ],
                role="exchange",
                temperature=0.2,
            )
        except Exception as e:
            logger.warning(f"[PricingEngine] Round 2 失败: {e}")
            modifiers = {}

        # GD 折扣特殊处理（种子态）
        gd = modifiers.get("gd_level")
        if gd and isinstance(gd, dict) and gd.get("level"):
            target_tier = int(gd.get("target_tier", temp_tier))
            target_sub  = normalize_tier_sub(gd.get("target_tier_sub", "M"))
            target_price = TIER_BASE_PRICES.get(target_tier, {}).get(target_sub, base_price)
            gd_factor = GD_FACTORS.get(gd.get("level", "GD-2"), 0.25)
            # 其他修正项（排除 gd_level 本身，其他正常乘法）
            other_mods = {k: v for k, v in modifiers.items()
                          if k not in ("hax_hi", "gd_level", "eval_notes")}
            other_mods["hax_hi"] = modifiers.get("hax_hi", 0)
            final_price = calculate_final_price_with_modifiers(
                int(target_price * gd_factor), other_mods
            )
        else:
            final_price = calculate_final_price_with_modifiers(base_price, modifiers)

        # 确保兑换价格最低1分
        final_price = max(1, final_price)

        # ── Round 3: 积分→星级反查 ─────────────────────────────────────────────
        final_tier, final_sub = determine_final_tier_from_price(final_price)

        # 必须凭证（资格验证，不消耗）
        required_medals = self._calc_required_medals(final_tier, final_sub)

        return {
            "item_name":       item_name,
            "item_type":       item_type,
            "source_world":    source_world,
            "round_1a":        round_1a,
            "covered_dims":    covered_dims,
            "is_hax_only":     is_hax_only,
            "temp_tier":       temp_tier,
            "temp_sub":        temp_sub,
            "modifiers":       modifiers,
            "base_price":      base_price,
            "final_price":     final_price,
            "final_tier":      final_tier,
            "final_sub":       final_sub,
            "required_medals": required_medals,
        }

    def _calc_required_medals(self, tier: int, sub: str) -> list[dict]:
        """
        规格 §2.1：持有至少1枚对应星级凭证即可购买（资格验证，不消耗）。
        0★/1★ 无需凭证，2★+ 需持有对应星级凭证。
        """
        if tier < 2:
            return []
        return [{"stars": tier, "count": 1}]

    async def evaluate_upgrade(
        self,
        novel_id: str,
        item_name: str,
        source_world: str,
        lore_context: str,
        item_description: str,
        current_owned_id: str,
        item_type: str = "PassiveAbility",
    ) -> dict:
        """
        差价定价（规格 §2.5）：已持有前置版本时，计算升级差价。
        D = 目标全价 T - 现有版本价值 C，最低1分。
        """
        from db.queries import get_db
        db = get_db()

        # 获取现有版本价值
        owned = await db.get_owned_item_by_id(current_owned_id)
        current_value = owned.get("price_paid", 0) if owned else 0

        # 评估目标形态全价
        target_result = await self.evaluate(
            item_name=item_name,
            source_world=source_world,
            lore_context=lore_context,
            item_description=item_description,
            item_type=item_type,
        )
        target_price = target_result["final_price"]

        # 差价
        diff_price = max(1, target_price - current_value)
        diff_tier, diff_sub = determine_final_tier_from_price(diff_price)

        return {
            **target_result,
            "upgrade_mode":    True,
            "current_value":   current_value,
            "diff_price":      diff_price,
            "diff_tier":       diff_tier,
            "diff_sub":        diff_sub,
            "final_price":     diff_price,     # 购买时扣差价
            "final_tier":      diff_tier,
            "final_sub":       diff_sub,
            "required_medals": self._calc_required_medals(target_result["final_tier"],
                                                           target_result["final_sub"]),
        }


# ════════════════════════════════════════════════════════════════════════════
# WorldTraverse 专项定价（规格 §C.4）
# ════════════════════════════════════════════════════════════════════════════

# 世界 peakTier 区间 → 锚点基准价（积分）
WORLD_TRAVERSE_PRICES: dict[tuple[int, int], int] = {
    (0, 2):  400,
    (3, 4):  800,
    (5, 6):  1_500,
    (7, 8):  3_000,
    (9, 99): 6_000,
}


def calculate_world_traverse_price(
    peak_tier: int,
    time_flow_ratio_str: str = "1:1",
) -> int:
    """
    规格 §C.4 WorldTraverse 定价。
    peak_tier: 该世界最强存在经三轮评估后的星级
    time_flow_ratio_str: "主世界:目标世界" 格式，如 "2:1" 表示目标世界1天=主世界0.5天
    """
    base = 6_000  # 默认9★+
    for (lo, hi), price in WORLD_TRAVERSE_PRICES.items():
        if lo <= peak_tier <= hi:
            base = price
            break

    # timeFlow 修正
    mult = 1.0
    try:
        parts = time_flow_ratio_str.split(":")
        main_part = float(parts[0])
        world_part = float(parts[1]) if len(parts) > 1 else 1.0
        # time_flow = 主世界:目标世界 的比例
        # timeFlow >= 2.0 表示目标世界时间流速快（1天主世界 = <0.5天目标世界）→ 对玩家更贵（×1.3）
        # timeFlow <= 0.5 表示目标世界时间流速慢（1天主世界 = >2天目标世界）→ 折扣（×0.8）
        if world_part > 0:
            ratio = main_part / world_part  # ratio=目标世界相对主世界的流速
            if ratio >= 2.0:
                mult = 1.3
            elif ratio <= 0.5:
                mult = 0.8
    except Exception:
        pass

    return max(1, int(base * mult))


# ════════════════════════════════════════════════════════════════════════════
# Decay System（反刷积分衰减）
# 精确来自规格 §2.1
# ════════════════════════════════════════════════════════════════════════════

POINTS_DECAY_TABLE = [
    (1,  5,  1.00),
    (6,  10, 0.90),
    (11, 15, 0.80),
    (16, 20, 0.70),
]
POINTS_DECAY_FLOOR = 0.10

MEDAL_DECAY_TABLE = [
    (1,  10, 1.00),
    (11, 20, 0.90),
    (21, 30, 0.80),
]
MEDAL_DECAY_FLOOR = 0.10

TIER_GAP_PENALTY = {
    1: {"points_mult": 0.50, "medal_mult": 0.50},
    2: {"points_mult": 0.10, "medal_mult": 0.10},
}


def _get_decay_rate(count: int, table: list, floor: float) -> float:
    for lo, hi, rate in table:
        if lo <= count <= hi:
            return rate
    # 超出表末：每满N次额外-10%，最低为 floor
    last_rate = table[-1][2]
    last_hi   = table[-1][1]
    step = (count - last_hi) // (table[-1][1] - table[-2][1]) if len(table) >= 2 else 1
    return max(floor, last_rate - step * 0.10)


async def calculate_combat_reward(
    novel_id: str,
    enemy_tier: int,
    enemy_tier_sub: str,
    protagonist_tier: int,
    kill_type: str = "defeat",
) -> dict:
    """
    完整结算一次战斗奖励（含衰减）。
    kill_type: "defeat" = 击败（无凭证），"kill" = 击杀（有凭证概率）
    规格 §2.1 Q2决策：击杀/击败奖励最低为 0（不保底），兑换最低为 1。
    """
    from db.queries import get_db
    db = get_db()

    enemy_tier_sub = normalize_tier_sub(enemy_tier_sub)
    enemy_category = f"tier{enemy_tier}_{enemy_tier_sub}"
    record = await db.get_kill_record(novel_id, enemy_category)
    kill_count   = (record["kill_count"]   if record else 0)
    defeat_count = (record["defeat_count"] if record else 0)

    # 更新计数
    if kill_type == "kill":
        kill_count += 1
    defeat_count += 1

    await db.upsert_kill_record(novel_id, enemy_category, {
        "enemy_tier":     enemy_tier,
        "enemy_tier_sub": enemy_tier_sub,
        "kill_count":     kill_count,
        "defeat_count":   defeat_count,
    })

    # 基准积分（与物品中档M基准相同）
    base_points = TIER_BASE_PRICES.get(enemy_tier, {}).get("M", 10)

    # 积分衰减
    points_rate = _get_decay_rate(defeat_count, POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR)
    points_earned = int(base_points * points_rate)

    # 弱敌倍率惩罚
    tier_gap = protagonist_tier - enemy_tier
    if tier_gap > 0:
        penalty = TIER_GAP_PENALTY.get(min(tier_gap, 2), {"points_mult": 0.10, "medal_mult": 0.10})
        points_earned = int(points_earned * penalty["points_mult"])

    # 奖励最低为 0（Q2 决策：击杀奖励不保底，允许为0）
    points_earned = max(0, points_earned)

    # 凭证掉落
    medal_drop = False
    if kill_type == "kill":
        if kill_count == 1:
            medal_drop = True  # 首杀必得
        else:
            med_rate = _get_decay_rate(kill_count, MEDAL_DECAY_TABLE, MEDAL_DECAY_FLOOR)
            if tier_gap > 0:
                pen = TIER_GAP_PENALTY.get(min(tier_gap, 2), {"medal_mult": 0.10})
                med_rate *= pen["medal_mult"]
            medal_drop = random.random() < med_rate

    return {
        "points_earned":     points_earned,
        "medal_dropped":     medal_drop,
        "enemy_tier":        enemy_tier,
        "enemy_tier_sub":    enemy_tier_sub,
        "kill_type":         kill_type,
        "points_decay_rate": points_rate,
        "kill_count":        kill_count,
        "defeat_count":      defeat_count,
    }


# ════════════════════════════════════════════════════════════════════════════
# 凭证工具函数（规格 §2.1 + Q1决策：系统自动向上拆分）
# ════════════════════════════════════════════════════════════════════════════

def check_medal_eligibility(
    medals: dict[int, int],
    required_tier: int,
) -> tuple[bool, list[dict]]:
    """
    检查是否有资格购买 required_tier★ 的兑换项（需持有至少1枚该星级凭证）。
    如果精确星级凭证不足，尝试自动向上寻找可拆分凭证。

    规格 §2.1：
    - 购买 X★ 需持有 ≥1枚 X★凭证（资格验证，凭证不消耗）
    - 拆分规则：1枚X★凭证 = 5枚(X-1)★凭证（只能向下拆，禁止合成）
    - Q1决策：自动拆分——购买时如精确星级不足，自动向上找可拆凭证

    返回：(eligible: bool, split_ops: list[dict])
    split_ops 为空=直接持有；非空=需要执行拆分操作才能满足
    """
    if required_tier < 2:
        return True, []  # 0★/1★ 无需凭证

    # 直接持有
    if medals.get(required_tier, 0) >= 1:
        return True, []

    # 向上寻找可拆分的凭证（从 required_tier+1 开始）
    for source_tier in range(required_tier + 1, 16):  # 最高到15★
        if medals.get(source_tier, 0) >= 1:
            # 计算需要拆分几层
            split_ops = []
            current_tier = source_tier
            current_medals = dict(medals)

            while current_tier > required_tier:
                split_ops.append({
                    "split_from": current_tier,
                    "split_into": current_tier - 1,
                    "count_produced": 5,
                })
                current_medals[current_tier] = current_medals.get(current_tier, 0) - 1
                current_medals[current_tier - 1] = current_medals.get(current_tier - 1, 0) + 5
                current_tier -= 1

            if current_medals.get(required_tier, 0) >= 1:
                return True, split_ops

    return False, []


# ── 全局单例 ──────────────────────────────────────────────────────────────────
pricing_engine = PricingEngine()
