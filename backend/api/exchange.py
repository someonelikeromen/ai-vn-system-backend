"""
Exchange Agent (Agent 9) — 兑换商务官
Exchange API 路由
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
import json as _json
import uuid
from loguru import logger

router = APIRouter(prefix="/api/exchange", tags=["exchange"])


# ════════════════════════════════════════════════════════════════════════════
# 兑换目录生成（规格 §4.2 A）
# ════════════════════════════════════════════════════════════════════════════

async def generate_exchange_catalog(novel_id: str, world_key: str) -> list[dict]:
    """
    生成当前世界的兑换目录（LLM 生成列表 → 并发三轮精确评估 → 缓存精确结果）。
    规格 §4.2 A：5条生成规则全部执行。
    改进：目录物品不再使用 estimated_price（猜测值），改用三轮评估协议给出精确价格，
    前端点击时可直接使用缓存结果，无需二次调用 LLM。
    """
    from db.queries import get_db
    from utils.llm_client import get_llm_client
    from exchange.pricing import TIER_BASE_PRICES, normalize_tier_sub, pricing_engine

    db = get_db()
    llm = get_llm_client()

    # 尝试读取缓存
    existing = await db.get_world_catalog(novel_id, world_key)
    if existing:
        return existing

    novel    = await db.get_novel(novel_id)
    novel_title = novel.get("title", "未命名小说") if novel else "未命名小说"

    protagonist = await db.get_protagonist_state(novel_id)
    tier        = int(protagonist.get("tier", 0)) if protagonist else 0
    tier_sub    = normalize_tier_sub(protagonist.get("tier_sub", "M")) if protagonist else "M"
    points      = int(protagonist.get("points", 0)) if protagonist else 0

    # 门控：主角星级+2以上 → 灰显标注（可见但无法兑换）
    locked_above_tier = tier + 2

    # 积分预筛：当前积分80%以上价格 → 标注"珍贵"（评估后用精确价格重新判断）
    precious_threshold = int(points * 0.80)

    # 获取已持有物品（避免推荐重复）
    owned_items = await db.get_owned_items(novel_id)
    owned_keys  = [item.get("item_key", "") for item in owned_items]
    owned_names = [item.get("item_name", "") for item in owned_items]

    prompt = f"""你是跨次元兑换商（神通谱）。根据以下信息，为主角生成一份当前世界的兑换目录。

小说：{novel_title}
当前世界：{world_key or "本源世界"}
主角当前战力：{tier}★{tier_sub}
主角当前积分：{points}

━━━ 生成规则 ━━━
1. 生成 7~10 个可兑换物品（含不同类型：技能/被动/体质/道具/知识）
2. 物品星级范围：主角当前星级 ±1 为主（{max(0,tier-1)}★~{tier+1}★）
3. 战力门控：{locked_above_tier}★以上的物品必须设置 "locked": true（可见但无法购买，需要 {locked_above_tier}★凭证）
4. 必须包含至少1个 GD-0/GD-1 的种子态成长物品（价格低，成长潜力高）
5. 必须包含3个"限时特供"物品（与当前世界主题强相关），在 "is_limited": true 字段标注
6. 每个物品符合当前世界观的文化逻辑
7. 凭证门控：{tier}★以上物品在 required_medals 里标注所需凭证星级
8. 已持有物品不重复推荐（已持有：{owned_names[:5] if owned_names else '无'}）
注意：estimated_price 只是占位符，系统将用三轮评估覆盖真实价格，无需精确。

━━━ 物品类型说明 ━━━
- PassiveAbility：被动能力/天赋
- PowerSource：能量基盘（必须在 payload 里说明能量池名和初始量）
- ApplicationTechnique：应用技巧/流派（含proficiencyLevel字段）
- Inventory：物品/装备（拿起即用）
- Knowledge：知识/理论（系统自动下调3档定价）
- WorldTraverse：世界穿越坐标（一次性消耗）
- Companion：同伴（独立人格，写入同伴栏）

输出格式（JSON 数组）：
[
  {{
    "item_key": "unique_snake_case_key",
    "item_name": "物品名称（含来源）",
    "item_type": "ApplicationTechnique",
    "source_world": "{world_key or '本源'}",
    "description": "描述（含关键效果和数据，50字以内）",
    "base_tier": {tier},
    "base_tier_sub": "M",
    "is_gd": false,
    "gd_target_tier": null,
    "gd_level": null,
    "estimated_price": 1000,
    "required_medals": [],
    "locked": false,
    "is_limited": false,
    "is_precious": false,
    "proficiency_level": "入门"
  }}
]
"""

    try:
        items = await llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            role="exchange",
            temperature=0.6,
        )
        if not isinstance(items, list):
            items = items.get("items", []) if isinstance(items, dict) else []
    except Exception as e:
        logger.warning(f"[Catalog] 目录列表生成失败: {e}")
        items = []

    if not items:
        return []

    # ── 并发三轮精确评估（限并发=3，避免压垮 LLM）────────────────────────────
    # 目录物品已有 item_name / item_type / description，足够跑完整三轮协议。
    # 生成后将精确结果写入物品，前端点击时可直接跳过 API 调用。
    sem = asyncio.Semaphore(3)

    async def _evaluate_one(item: dict) -> dict:
        async with sem:
            try:
                result = await pricing_engine.evaluate(
                    item_name=item.get("item_name", ""),
                    source_world=item.get("source_world", world_key or "本源"),
                    lore_context="",
                    item_description=item.get("description", ""),
                    item_type=item.get("item_type", "PassiveAbility"),
                )
                final_tier  = result["final_tier"]
                final_sub   = result["final_sub"]
                final_price = result["final_price"]
                return {
                    **item,
                    # 覆盖精确值
                    "final_tier":      final_tier,
                    "final_sub":       final_sub,
                    "final_price":     final_price,
                    "estimated_price": final_price,   # 兼容旧字段
                    "required_medals": result.get("required_medals", []),
                    # 用精确星级重新判断门控和珍贵标注
                    "locked":          final_tier > locked_above_tier,
                    "is_precious":     precious_threshold > 0 and final_price >= precious_threshold,
                    # 完整评估报告供前端直接使用，跳过重复 LLM 调用
                    "eval_result":     result,
                }
            except Exception as e:
                logger.warning(f"[Catalog] 三轮评估失败 {item.get('item_name')}: {e}")
                return item   # 降级：保留原始 LLM 估算值

    logger.info(f"[Catalog] 开始并发三轮评估，物品数={len(items)}")
    evaluated = await asyncio.gather(*[_evaluate_one(it) for it in items])
    items = list(evaluated)
    logger.info(f"[Catalog] 三轮评估完成，已生成精确价格")

    # 持久化精确结果
    await db.upsert_world_catalog(novel_id, world_key, items)

    return items


# ════════════════════════════════════════════════════════════════════════════
# Exchange Agent 评估入口
# ════════════════════════════════════════════════════════════════════════════

async def run_exchange_evaluation(
    novel_id: str,
    item_name: str,
    source_world: str,
    lore_context: str,
    item_description: str,
    item_type: str = "PassiveAbility",
    schema_id: str = "standard_10d",
) -> dict:
    """完整评估流程（供 API 层调用）"""
    from exchange.pricing import pricing_engine
    return await pricing_engine.evaluate(
        item_name=item_name,
        source_world=source_world,
        lore_context=lore_context,
        item_description=item_description,
        item_type=item_type,
        schema_id=schema_id,
    )


# ════════════════════════════════════════════════════════════════════════════
# Exchange API 路由
# ════════════════════════════════════════════════════════════════════════════

class EvaluateRequest(BaseModel):
    item_name:        str
    source_world:     str  = ""
    lore_context:     str  = ""
    item_description: str  = ""
    item_type:        str  = "PassiveAbility"
    # 差价升级模式
    upgrade_from_owned_id: Optional[str] = None


class PurchaseRequest(BaseModel):
    item_key:     str
    item_name:    str
    item_type:    str
    source_world: str  = ""
    final_price:  int
    final_tier:   int
    final_sub:    str  = "M"
    payload:      dict = {}
    # Companion 复活模式
    revive_mode:          bool           = False
    original_companion_id: Optional[str] = None


class SearchRequest(BaseModel):
    query:     str  = ""
    max_price: Optional[int] = None
    item_type: Optional[str] = None
    min_tier:  Optional[int] = None
    max_tier:  Optional[int] = None
    world_id:  Optional[str] = None


@router.get("/{novel_id}/catalog")
async def get_catalog(novel_id: str, refresh: bool = False):
    """获取当前世界兑换目录（规格 §4.2 A）"""
    from db.queries import get_db
    db = get_db()

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    world_key = novel.get("current_world_key", "")

    if refresh:
        await db.clear_world_catalog(novel_id, world_key)

    items = await generate_exchange_catalog(novel_id, world_key)
    return {"items": items, "world_key": world_key, "count": len(items)}


@router.post("/{novel_id}/evaluate")
async def evaluate_item(novel_id: str, req: EvaluateRequest):
    """三轮评估协议（获取价格报告）"""
    from db.queries import get_db
    from exchange.pricing import pricing_engine
    db = get_db()

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    schema_id = novel.get("attr_schema_id", "standard_10d")

    # 差价升级模式
    if req.upgrade_from_owned_id:
        result = await pricing_engine.evaluate_upgrade(
            novel_id=novel_id,
            item_name=req.item_name,
            source_world=req.source_world,
            lore_context=req.lore_context,
            item_description=req.item_description,
            current_owned_id=req.upgrade_from_owned_id,
            item_type=req.item_type,
        )
    else:
        result = await run_exchange_evaluation(
            novel_id=novel_id,
            item_name=req.item_name,
            source_world=req.source_world,
            lore_context=req.lore_context,
            item_description=req.item_description,
            item_type=req.item_type,
            schema_id=schema_id,
        )
    return result


@router.post("/{novel_id}/purchase")
async def purchase_item(novel_id: str, req: PurchaseRequest):
    """
    用户确认兑换 — 执行扣款 + 写入物品/同伴栏 + 初始化 XP。
    规格 §2.1：凭证为资格验证（不消耗），购买时自动向上拆分不足的凭证。
    """
    from db.queries import get_db
    from config_sys.registry import ItemTypeRegistry
    from exchange.pricing import check_medal_eligibility, normalize_tier_sub
    db = get_db()

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    protagonist = await db.get_protagonist_state(novel_id)
    if not protagonist:
        raise HTTPException(400, "主角未初始化")

    final_sub = normalize_tier_sub(req.final_sub)
    final_price = max(1, req.final_price)  # 兑换最低1分（Q2决策）

    # ── Companion 复活模式（价格=全价×30%）─────────────────────────────────
    if req.revive_mode and req.original_companion_id:
        # 复活不走凭证验证（沿用原始面板）
        current_points = protagonist.get("points", 0)
        if current_points < final_price:
            raise HTTPException(400, f"积分不足：现有 {current_points}，需要 {final_price}")
        await db.add_points(novel_id, -final_price)
        # 重新激活同伴
        await db._exec(
            "UPDATE owned_items SET is_active=1 WHERE id=? AND novel_id=?",
            (req.original_companion_id, novel_id),
        )
        return {
            "success":     True,
            "revive_mode": True,
            "item_name":   req.item_name,
            "item_id":     req.original_companion_id,
            "price_paid":  final_price,
            "points_left": current_points - final_price,
        }

    # ── 检查积分 ──────────────────────────────────────────────────────────
    current_points = protagonist.get("points", 0)
    if current_points < final_price:
        raise HTTPException(400, f"积分不足：现有 {current_points}，需要 {final_price}")

    # ── 凭证资格验证 + 自动拆分（规格 §2.1，Q1决策：系统自动拆分）────────────
    medals_rows = await db._fetchall(
        "SELECT stars, count FROM medals WHERE novel_id=?", (novel_id,)
    )
    medals = {r["stars"]: r["count"] for r in medals_rows}

    eligible, split_ops = check_medal_eligibility(medals, req.final_tier)
    if not eligible:
        raise HTTPException(
            400,
            f"凭证不足：需要 {req.final_tier}★凭证（或更高可拆分凭证），"
            f"当前持有: {medals}"
        )

    # 执行拆分操作
    for op in split_ops:
        src  = op["split_from"]
        dst  = op["split_into"]
        prod = op["count_produced"]
        await db._exec(
            "UPDATE medals SET count=count-1 WHERE novel_id=? AND stars=?",
            (novel_id, src),
        )
        await db.add_medal(novel_id, dst, prod)

    # ── 扣款（凭证不消耗，只扣积分）────────────────────────────────────────
    await db.add_points(novel_id, -final_price)

    # ── 写入物品 ──────────────────────────────────────────────────────────
    owned_id = str(uuid.uuid4())
    is_companion = (req.item_type == "Companion")

    try:
        await db._exec(
            "INSERT OR IGNORE INTO owned_items "
            "(id,novel_id,item_key,item_name,item_type,source_world,final_tier,final_sub,"
            "price_paid,payload,is_active) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
            (
                owned_id, novel_id, req.item_key, req.item_name,
                req.item_type, req.source_world, req.final_tier, final_sub,
                final_price,
                _json.dumps(req.payload or {}, ensure_ascii=False),
            ),
        )
    except Exception as e:
        # 回滚积分
        await db.add_points(novel_id, final_price)
        raise HTTPException(500, f"物品写入失败: {e}")

    # ── Companion 同伴栏处理（Q3决策：payload方案，但写入同伴栏标记）─────────
    if is_companion:
        try:
            payload = req.payload or {}
            companion_name = payload.get("name", req.item_name)
            affinity     = int(payload.get("initialAffinity", 50))
            loyalty_type = payload.get("loyaltyType", "中性")
            await db.upsert_npc(
                novel_id=novel_id,
                name=companion_name,
                data={
                    "npc_type":        "companion",
                    "world_key":       req.source_world,
                    "trait_lock":      payload.get("personality", []),
                    "knowledge_scope": payload.get("knowledgeScope", []),
                    "capability_cap":  {
                        "tier":     req.final_tier,
                        "tier_sub": final_sub,
                    },
                    "psyche_model": {
                        "owned_item_id": owned_id,
                        "source_world":  req.source_world,
                    },
                    # 独立列
                    "initial_affinity": affinity,
                    "loyalty_type":     loyalty_type,
                    "companion_slot":   1,  # 暂用 slot=1，后续可支持多同伴排序
                },
            )
        except Exception:
            pass  # 同伴档案写入失败不回滚物品


    # ── 调用 ItemTypePlugin.on_purchase() ────────────────────────────────
    try:
        plugin = ItemTypeRegistry.get(req.item_type)
        await plugin.on_purchase(
            novel_id, owned_id, req.payload or {},
            db=db, memory=None,
        )
    except Exception:
        pass

    return {
        "success":       True,
        "item_name":     req.item_name,
        "item_id":       owned_id,
        "item_type":     req.item_type,
        "is_companion":  is_companion,
        "price_paid":    final_price,
        "points_left":   current_points - final_price,
        "split_ops":     split_ops,   # 返回拆分操作记录
    }


@router.post("/{novel_id}/search")
async def search_catalog(novel_id: str, req: SearchRequest):
    """
    主动搜索兑换目录（规格 §4.2 B）。
    支持关键词 + 条件过滤；超出凭证门控的物品标注 [LOCKED]。
    """
    from db.queries import get_db
    from exchange.pricing import normalize_tier_sub, TIER_BASE_PRICES
    db = get_db()

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")
    world_key = novel.get("current_world_key", "")

    protagonist = await db.get_protagonist_state(novel_id)
    tier = int(protagonist.get("tier", 0)) if protagonist else 0

    # 从已缓存目录搜索
    all_items = await db.get_world_catalog(novel_id, world_key)
    if not all_items:
        all_items = await generate_exchange_catalog(novel_id, world_key)

    results = []
    for item in all_items:
        # 关键词过滤
        if req.query:
            q = req.query.lower()
            searchable = (
                item.get("item_name", "").lower() + " " +
                item.get("description", "").lower() + " " +
                item.get("source_world", "").lower() + " " +
                item.get("item_type", "").lower()
            )
            if q not in searchable:
                continue

        item_tier = int(item.get("base_tier", 0))
        est_price = int(item.get("estimated_price", 0))

        # 条件过滤
        if req.max_price is not None and est_price > req.max_price:
            continue
        if req.item_type and item.get("item_type") != req.item_type:
            continue
        if req.min_tier is not None and item_tier < req.min_tier:
            continue
        if req.max_tier is not None and item_tier > req.max_tier:
            continue
        if req.world_id and item.get("source_world") != req.world_id:
            continue

        # 门控标注（超出主角星级+2）
        item_copy = dict(item)
        if item_tier > tier + 2:
            item_copy["locked"] = True
            item_copy["locked_reason"] = f"[LOCKED: 需要 {item_tier}★凭证]"
        else:
            item_copy["locked"] = item.get("locked", False)

        results.append(item_copy)

    return {
        "results": results,
        "total":   len(results),
        "query":   req.query,
        "world_key": world_key,
    }


@router.get("/{novel_id}/rewards/combat")
async def preview_combat_reward(
    novel_id: str, enemy_tier: int, enemy_tier_sub: str = "M", kill_type: str = "defeat"
):
    """预览战斗奖励（不实际结算）"""
    from db.queries import get_db
    from exchange.pricing import (
        TIER_BASE_PRICES, _get_decay_rate,
        POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR,
        normalize_tier_sub,
    )
    db = get_db()

    protagonist = await db.get_protagonist_state(novel_id)
    protagonist_tier = int(protagonist.get("tier", 0)) if protagonist else 0

    sub = normalize_tier_sub(enemy_tier_sub)
    base = TIER_BASE_PRICES.get(enemy_tier, {}).get("M", 10)
    rate = _get_decay_rate(1, POINTS_DECAY_TABLE, POINTS_DECAY_FLOOR)
    preview_points = max(0, int(base * rate))  # Q2决策：奖励可为0

    return {
        "enemy_tier":       enemy_tier,
        "enemy_tier_sub":   sub,
        "base_points":      base,
        "preview_points":   preview_points,
        "protagonist_tier": protagonist_tier,
        "note": "实际积分含衰减，此为首次击败估算值（奖励可能为0）",
    }


@router.post("/{novel_id}/companion/{companion_owned_id}/revive")
async def revive_companion(novel_id: str, companion_owned_id: str):
    """
    复活同伴（规格 §2.4）：价格 = 原购买价格 × 30%。
    沿用原始面板，好感从死亡前状态恢复。
    """
    from db.queries import get_db
    db = get_db()

    owned = await db.get_owned_item_by_id(companion_owned_id)
    if not owned or owned.get("novel_id") != novel_id:
        raise HTTPException(404, "同伴档案不存在")
    if owned.get("item_type") != "Companion":
        raise HTTPException(400, "该物品不是同伴类型")

    original_price = int(owned.get("price_paid", 0))
    revive_price   = max(1, int(original_price * 0.30))

    protagonist = await db.get_protagonist_state(novel_id)
    current_points = int(protagonist.get("points", 0)) if protagonist else 0

    if current_points < revive_price:
        raise HTTPException(
            400,
            f"积分不足：复活价格 {revive_price}（原价 {original_price} × 30%），现有 {current_points}"
        )

    await db.add_points(novel_id, -revive_price)
    await db._exec(
        "UPDATE owned_items SET is_active=1 WHERE id=? AND novel_id=?",
        (companion_owned_id, novel_id),
    )

    return {
        "success":       True,
        "companion_id":  companion_owned_id,
        "item_name":     owned.get("item_name", ""),
        "revive_price":  revive_price,
        "original_price": original_price,
        "points_left":   current_points - revive_price,
    }
