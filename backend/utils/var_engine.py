"""
VarEngine — Path-based 状态树更新引擎（Schema 感知版）
对应 ai-vn-game-system/varEngine.js 的 Python 移植与升级版本。
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from loguru import logger


class AttributeKeyError(ValueError):
    pass


class VarEngine:
    """
    Path-based 状态树更新引擎。
    通过 VarEngine(attr_schema_keys) 实例化，
    属性操作自动按当前 Schema 验证键名合法性。
    """

    def __init__(self, attr_schema_keys: set[str]):
        self.attr_keys = attr_schema_keys

    @classmethod
    def from_schema_id(cls, schema_id: str = "standard_10d") -> "VarEngine":
        """从 Schema ID 快速构建"""
        from config_sys.registry import AttributeSchemaRegistry
        schema = AttributeSchemaRegistry.get(schema_id)
        return cls(set(schema.get_keys()))

    @classmethod
    def default(cls) -> "VarEngine":
        """标准 10 维默认实例（不依赖注册表时使用）"""
        return cls({"STR", "DUR", "VIT", "REC", "AGI", "REF", "PER", "MEN", "SOL", "CHA"})

    # ── 属性专用方法（带 Schema 验证）────────────────────────────────────

    def apply_attribute_delta(self, state: dict, attr_key: str, delta: float) -> dict:
        """单属性增量（验证键名）"""
        if attr_key not in self.attr_keys:
            raise AttributeKeyError(
                f"属性键 '{attr_key}' 不在当前 Schema 中。合法键: {sorted(self.attr_keys)}"
            )
        return self.update(state, f"CharacterSheet.Attributes.{attr_key}", "add", delta)

    def apply_attribute_deltas(self, state: dict, deltas: dict[str, float]) -> dict:
        """批量属性增量（payload.attributeDeltas 标准入口）"""
        for key, delta in deltas.items():
            if delta != 0:
                try:
                    state = self.apply_attribute_delta(state, key, delta)
                except AttributeKeyError as e:
                    logger.warning(f"[VarEngine] 跳过无效属性: {e}")
        return state

    def apply_attribute_amplification(self, state: dict, amp: dict[str, float]) -> dict:
        """属性放大系数（血统插件用：current = base × amp）"""
        for key, factor in amp.items():
            if key not in self.attr_keys:
                continue
            state = self.update(state, f"CharacterSheet.Attributes.{key}", "multiply", factor)
        return state

    # ── 通用路径操作 ──────────────────────────────────────────────────────

    def update(self, state: dict, path: str, op: str, value: Any) -> dict:
        """
        Path-based 状态树更新。

        支持的 op:
          set      — 直接赋值
          add      — 数值叠加
          multiply — 数值乘法（结果保留4位小数）
          push     — 追加到列表
          remove   — 从列表中删除（按 id 字段匹配）
          merge    — dict 浅合并
          set_max  — 仅在 value > 当前值时赋值（用于记录最高值）
          set_min  — 仅在 value < 当前值时赋值

        Examples:
            engine.update(state, "CharacterSheet.CoreSystem.Points", "add", 100)
            engine.update(state, "CharacterSheet.EnergyPools.chakra.current", "add", -30)
            engine.update(state, "CharacterSheet.Loadout.Inventory", "push", item_dict)
        """
        state = copy.deepcopy(state)
        keys = path.split(".")
        current = state

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        last_key = keys[-1]

        if op == "set":
            current[last_key] = value
        elif op == "add":
            current[last_key] = current.get(last_key, 0) + value
        elif op == "multiply":
            current[last_key] = round(current.get(last_key, 0) * value, 4)
        elif op == "push":
            if not isinstance(current.get(last_key), list):
                current[last_key] = []
            current[last_key].append(value)
        elif op == "remove":
            if isinstance(current.get(last_key), list):
                current[last_key] = [
                    item for item in current[last_key]
                    if item.get("id") != value
                ]
        elif op == "merge":
            if not isinstance(current.get(last_key), dict):
                current[last_key] = {}
            current[last_key].update(value)
        elif op == "set_max":
            current[last_key] = max(current.get(last_key, value), value)
        elif op == "set_min":
            current[last_key] = min(current.get(last_key, value), value)
        else:
            raise ValueError(f"[VarEngine] 不支持的操作: {op}")

        return state

    def apply_system_grants(self, state: dict, tags: list[dict]) -> dict:
        """
        批量处理 <system_grant> 标签提取出的更新指令。
        tag 格式: {type: "xp"|"stat"|"item"|"kill"|"points"|"energy", ...}
        """
        for tag in tags:
            t = tag.get("type", "")
            try:
                if t == "points":
                    state = self.update(
                        state, "CharacterSheet.CoreSystem.Points", "add", tag["amount"]
                    )

                elif t == "stat":
                    state = self.apply_attribute_delta(state, tag["attr"], tag["delta"])

                elif t == "item":
                    state = self.update(
                        state, "CharacterSheet.Loadout.Inventory", "push", tag["item"]
                    )

                elif t == "energy":
                    pool_name = tag["pool"]
                    delta = tag["delta"]
                    path = f"CharacterSheet.EnergyPools.{pool_name}.current"
                    state = self.update(state, path, "add", delta)
                    # 能量池边界约束
                    pool_data = (
                        state.get("CharacterSheet", {})
                        .get("EnergyPools", {})
                        .get(pool_name, {})
                    )
                    cur_val = pool_data.get("current", 0)
                    max_val = pool_data.get("max", float("inf"))
                    if pool_data:
                        pool_data["current"] = max(0, min(cur_val, max_val))

                elif t == "hp_damage":
                    state = self.update(
                        state, "CharacterSheet.EnergyPools.hp.current", "add", tag["amount"]
                    )

                elif t == "xp":
                    # XP 标签仅记录，实际结算由 GrowthService 处理
                    logger.debug(f"[VarEngine] XP标签记录（延迟结算）: {tag}")

                elif t == "kill":
                    logger.debug(f"[VarEngine] 击杀标签记录（由Calibrator结算）: {tag}")

                else:
                    logger.warning(f"[VarEngine] 未知标签类型: {t}")

            except AttributeKeyError as e:
                logger.warning(f"[VarEngine] 跳过无效属性标签: {e}")
            except Exception as e:
                logger.error(f"[VarEngine] 处理标签异常 {tag}: {e}")

        return state

    def clamp_energy_pools(self, state: dict) -> dict:
        """确保所有能量池不超过 max，不低于 0"""
        state = copy.deepcopy(state)
        pools = state.get("CharacterSheet", {}).get("EnergyPools", {})
        for pool_name, pool_data in pools.items():
            if isinstance(pool_data, dict):
                cur = pool_data.get("current", 0)
                mx = pool_data.get("max", float("inf"))
                pool_data["current"] = max(0, min(cur, mx))
        return state
