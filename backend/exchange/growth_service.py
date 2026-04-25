"""
通用成长结算服务 — 乐观锁 + 幂等键保护
"""
from __future__ import annotations

import uuid
from typing import Optional
from loguru import logger


class GrowthService:
    """
    统一成长结算服务。
    使用乐观锁（version CAS）防止并发冲突。
    使用 event_id 幂等键防止重复结算。
    """

    async def settle_xp_batch(
        self,
        novel_id: str,
        chapter_id: str,
        xp_grants: list[dict],
        event_id: Optional[str] = None,
    ) -> list[dict]:
        """
        批量结算 XP（对应 STEP 4 calibrator 调用）。

        xp_grants = [
            {"school": "云体风身", "amount": 20, "context": "vs_stronger",
             "owned_id": "xxx"}
        ]

        Returns: 结算结果列表，每条含 {school, xp_added, level_before, level_after, owned_id}
        """
        from db.queries import get_db
        db = get_db()

        # 幂等检查
        if event_id is None:
            event_id = str(uuid.uuid4())
        if await db.growth_event_exists(event_id):
            logger.info(f"[GrowthService] 幂等跳过 {event_id}")
            return []

        results = []
        for grant in xp_grants:
            school    = grant.get("school", "")
            amount    = int(grant.get("amount", 0))
            owned_id  = grant.get("owned_id", "")
            context   = grant.get("context", "vs_equal")

            if not school or not owned_id or amount <= 0:
                continue

            # 上下文倍率
            amount = int(amount * self._context_multiplier(context))

            result = await self._settle_one_with_retry(
                db, novel_id, owned_id, school, amount
            )
            if result:
                results.append(result)

        # 记录幂等键
        await db.mark_growth_event_settled(event_id, novel_id, {"grants": results})
        return results

    async def settle_use_count(
        self,
        novel_id: str,
        owned_id: str,
        growth_key: str,
        sub_key: Optional[str] = None,
    ) -> dict:
        """记录技能使用次数 +1（不影响 XP，用于熟练度分析）"""
        from db.queries import get_db
        db = get_db()
        rec = await db.get_growth_record(novel_id, owned_id, growth_key, sub_key)
        if not rec:
            return {}
        rows_affected = 1
        if rows_affected:
            await db._exec(
                "UPDATE growth_records SET use_count=use_count+1, last_event_at=datetime('now') "
                "WHERE novel_id=? AND owned_id=? AND growth_key=? AND sub_key IS ?",
                (novel_id, owned_id, growth_key, sub_key),
            )
        return {"growth_key": growth_key, "use_count_incremented": True}

    async def _settle_one_with_retry(
        self,
        db,
        novel_id: str,
        owned_id: str,
        growth_key: str,
        xp_amount: int,
        sub_key: Optional[str] = None,
        max_retries: int = 3,
    ) -> Optional[dict]:
        """带乐观锁重试的单条 XP 结算"""
        for attempt in range(max_retries):
            rec = await db.get_growth_record(novel_id, owned_id, growth_key, sub_key)
            if rec is None:
                await db.init_growth_record(novel_id, owned_id, growth_key, sub_key)
                rec = await db.get_growth_record(novel_id, owned_id, growth_key, sub_key)
                if rec is None:
                    return None

            version = rec["version"]
            cur_xp  = rec["current_xp"]
            cur_lvl = rec["level_index"]

            # 获取当前等级阈值
            thresholds = await self._get_xp_thresholds(db, novel_id, owned_id)
            level_before = cur_lvl

            # 加 XP 并计算升级
            new_xp = cur_xp + xp_amount
            new_lvl = cur_lvl
            while new_lvl < len(thresholds) and new_xp >= thresholds[new_lvl]:
                new_xp -= thresholds[new_lvl]
                new_lvl += 1

            # CAS 更新
            rows = await db.compare_and_swap_growth_record(
                novel_id, owned_id, growth_key, sub_key,
                new_xp, new_lvl, version,
            )
            if rows == 1:
                return {
                    "owned_id":     owned_id,
                    "school":       growth_key,
                    "xp_added":     xp_amount,
                    "level_before": level_before,
                    "level_after":  new_lvl,
                    "leveled_up":   new_lvl > level_before,
                }
            logger.warning(f"[GrowthService] CAS 冲突 (attempt {attempt+1}): {growth_key}")

        return None

    async def _get_xp_thresholds(self, db, novel_id: str, owned_id: str) -> list[int]:
        """获取该物品对应的等级阈值列表"""
        try:
            from config_sys.registry import ItemTypeRegistry
            owned = await db.get_owned_item_by_id(owned_id)
            if not owned:
                return [500, 2000, 10000]
            plugin = ItemTypeRegistry.get(owned["item_type"])
            return plugin.growth_config.xp_thresholds
        except Exception:
            return [500, 2000, 10000]

    def _context_multiplier(self, context: str) -> float:
        """
        战斗上下文 XP 倍率（规格 §3.2）。
        基础 XP 量由 Chronicler 写入 amount，此处只做倍率修正。
        context 类型说明：
          vs_stronger_win  = 以弱胜强（击败）     × 2.0 （规格最高奖励）
          vs_stronger_alive= 存活且强敌受创       × 1.2
          vs_stronger      = 强敌场景参与（未胜）  × 1.0（基础强敌奖励）
          vs_equal_win     = 同级战胜             × 1.5
          vs_equal         = 同级参与（未明确胜负）× 1.0
          vs_weaker        = 碾压弱敌             × 0.3
          training         = 训练/演练            × 0.5
        """
        return {
            "vs_stronger_win":   2.0,
            "vs_stronger_alive": 1.2,
            "vs_stronger":       1.0,
            "vs_equal_win":      1.5,
            "vs_equal":          1.0,
            "vs_weaker":         0.3,
            "training":          0.5,
            "study":             0.3,   # 旧格式兼容，映射为 training
        }.get(context, 1.0)



# ── 全局单例 ──────────────────────────────────────────────────────────────
growth_service = GrowthService()
