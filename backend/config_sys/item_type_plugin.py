"""物品类型插件接口 — 所有 ItemType 必须实现此接口"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from db.queries import Database


@dataclass
class ItemTypeField:
    """物品类型的 payload 字段定义"""
    key: str
    display_name: str
    field_type: str   # "string" | "number" | "boolean" | "json" | "list"
    required: bool = False
    default: Any = None
    hint: str = ""    # 填写提示（给 LLM payload 生成 Prompt 用）


@dataclass
class GrowthConfig:
    """成长系统配置"""
    enabled: bool = False
    xp_entity: str = "self"   # "self" = 物品整体, "sub_item" = 子技能级别
    level_names: list[str] = field(
        default_factory=lambda: ["入门", "熟练", "精通", "化境"]
    )
    xp_thresholds: list[int] = field(
        default_factory=lambda: [500, 2000, 10000]
    )
    # 允许触发 XP 的事件类型
    xp_gain_events: list[str] = field(
        default_factory=lambda: ["combat_use", "training"]
    )


class ItemTypePlugin(ABC):
    """物品类型插件接口（所有类型必须实现）"""

    @property
    @abstractmethod
    def type_id(self) -> str:
        """唯一类型键，如 'ApplicationTechnique'"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """前端显示名"""
        ...

    @property
    @abstractmethod
    def icon(self) -> str:
        """前端图标（emoji 或 icon key）"""
        ...

    @property
    @abstractmethod
    def payload_fields(self) -> list[ItemTypeField]:
        """该类型物品的 payload 字段定义列表"""
        ...

    @property
    def growth_config(self) -> GrowthConfig:
        """成长系统配置（默认不启用，子类覆盖即可开启）"""
        return GrowthConfig(enabled=False)

    @property
    def allows_multiple(self) -> bool:
        """是否允许同类多份（True=允许，False=同key唯一）"""
        return False

    @property
    def eval_prompt_suffix(self) -> str:
        """评估时追加到 Round 1A Prompt 末尾的类型专属提示"""
        return ""

    @abstractmethod
    async def on_purchase(
        self,
        novel_id: str,
        owned_id: str,
        payload: dict,
        db: "Database",
        memory: Any,
        **kwargs,
    ) -> None:
        """购买后执行的类型专属同步逻辑（属性增量/能量池/XP初始化等）"""
        ...

    async def on_upgrade(
        self,
        novel_id: str,
        owned_id: str,
        old_payload: dict,
        new_payload: dict,
        db: "Database",
        memory: Any,
        **kwargs,
    ) -> None:
        """升级时执行的逻辑（默认替换 payload，子类可覆盖）"""
        import json
        await db._exec(
            "UPDATE owned_items SET payload=? WHERE id=?",
            (json.dumps(new_payload, ensure_ascii=False), owned_id),
        )

    async def on_remove(
        self,
        novel_id: str,
        owned_id: str,
        payload: dict,
        db: "Database",
        memory: Any,
        **kwargs,
    ) -> None:
        """移除/撤销时执行的清理逻辑（默认什么都不做）"""
        pass

    def get_payload_prompt(
        self,
        item_name: str,
        source_world: str,
        final_tier: int,
        final_tier_sub: str,
        lore_summary: str,
        round_1a: dict,
    ) -> str:
        """生成该类型的 payload JSON 生成 Prompt（子类可覆盖）"""
        fields_hint = "\n".join(
            f'  "{f.key}": {f.hint or f.display_name}{"（必填）" if f.required else ""}'
            for f in self.payload_fields
        )
        return f"""
根据评估结果，为 {self.display_name} 类型物品生成 payload JSON。

物品：{item_name}（来自 {source_world}）
星级：{final_tier}★{final_tier_sub}
原著描述：{lore_summary}

输出 JSON，必须包含以下字段：
{{
  "effects": {{
{fields_hint}
  }}
}}

{self.eval_prompt_suffix}
只输出 JSON，不要添加任何说明。
"""

    def to_dict(self) -> dict:
        """序列化为前端可用的字典"""
        return {
            "type_id": self.type_id,
            "display_name": self.display_name,
            "icon": self.icon,
            "allows_multiple": self.allows_multiple,
            "has_growth": self.growth_config.enabled,
            "growth_levels": self.growth_config.level_names if self.growth_config.enabled else [],
            "payload_fields": [
                {
                    "key": f.key,
                    "display_name": f.display_name,
                    "field_type": f.field_type,
                    "required": f.required,
                    "default": f.default,
                    "hint": f.hint,
                }
                for f in self.payload_fields
            ],
        }
