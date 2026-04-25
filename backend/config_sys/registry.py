"""双注册表服务：AttributeSchemaRegistry + ItemTypeRegistry"""
from __future__ import annotations

from loguru import logger
from config_sys.attribute_schema import AttributeSchemaConfig, BUILTIN_SCHEMAS
from config_sys.item_type_plugin import ItemTypePlugin


class AttributeSchemaRegistry:
    """运行时属性 Schema 注册表（内置 + 用户自定义）"""

    _schemas: dict[str, AttributeSchemaConfig] = {}

    @classmethod
    def register(cls, schema: AttributeSchemaConfig) -> None:
        cls._schemas[schema.schema_id] = schema
        logger.debug(f"[AttributeSchemaRegistry] 注册: {schema.schema_id} ({len(schema.attributes)}维)")

    @classmethod
    def get(cls, schema_id: str) -> AttributeSchemaConfig:
        schema = cls._schemas.get(schema_id)
        if not schema:
            # 降级到标准10维
            logger.warning(f"AttributeSchema '{schema_id}' 未注册，降级到 standard_10d")
            return cls._schemas.get("standard_10d") or list(cls._schemas.values())[0]
        return schema

    @classmethod
    def list_all(cls) -> list[dict]:
        return [
            {
                "schema_id": s.schema_id,
                "name": s.name,
                "description": s.description,
                "dimensions": len(s.attributes),
                "tier_dimensions": len(s.get_tier_keys()),
                "attributes": [
                    {
                        "key": a.key,
                        "name": a.name,
                        "category": a.category.value,
                        "count_in_tier": a.count_in_tier,
                        "display_order": a.display_order,
                    }
                    for a in s.attributes
                ],
            }
            for s in cls._schemas.values()
        ]

    @classmethod
    def startup(cls) -> None:
        """启动时注册所有内置 Schema"""
        for schema in BUILTIN_SCHEMAS.values():
            cls.register(schema)
        logger.info(f"[AttributeSchemaRegistry] 启动完成，共 {len(cls._schemas)} 个 Schema")

    @classmethod
    def from_user_config(cls, novel_id: str, raw: dict) -> AttributeSchemaConfig:
        """从用户 JSON 配置动态注册自定义 Schema"""
        from config_sys.attribute_schema import AttributeDef, AttributeCategory, AttributeSchemaConfig
        attrs = []
        for a in raw.get("attributes", []):
            attrs.append(AttributeDef(
                key=a["key"],
                name=a["name"],
                category=AttributeCategory(a.get("category", "physical")),
                definition=a.get("definition", ""),
                extract_positive=a.get("extract_positive", ""),
                extract_negative=a.get("extract_negative", ""),
                base_value=a.get("base_value", 1.0),
                count_in_tier=a.get("count_in_tier", True),
                display_order=a.get("display_order", 0),
            ))
        # 解析 coverage_degrade_map（JSON不支持tuple键，用"lo-hi"格式）
        raw_degrade = raw.get("coverage_degrade_map", {})
        cov_map = {}
        for k, v in raw_degrade.items():
            parts = str(k).split("-")
            cov_map[(int(parts[0]), int(parts[1]))] = v

        custom_id = f"custom_{novel_id}_{raw['schema_id']}"
        schema = AttributeSchemaConfig(
            schema_id=custom_id,
            name=raw.get("name", custom_id),
            description=raw.get("description", ""),
            attributes=attrs,
            coverage_degrade_map=cov_map or {(8,10):0,(6,7):1,(3,5):3,(1,2):6,(0,0):9},
        )
        cls.register(schema)
        return schema


class ItemTypeRegistry:
    """运行时物品类型注册表"""

    _plugins: dict[str, ItemTypePlugin] = {}

    @classmethod
    def register(cls, plugin: ItemTypePlugin) -> None:
        cls._plugins[plugin.type_id] = plugin
        logger.debug(f"[ItemTypeRegistry] 注册: {plugin.type_id}")

    @classmethod
    def get(cls, type_id: str) -> ItemTypePlugin:
        plugin = cls._plugins.get(type_id)
        if not plugin:
            raise ValueError(f"ItemType '{type_id}' 未注册。已注册: {list(cls._plugins.keys())}")
        return plugin

    @classmethod
    def list_all(cls) -> list[dict]:
        return [p.to_dict() for p in cls._plugins.values()]

    @classmethod
    def startup(cls) -> None:
        """启动时注册所有内置物品类型"""
        from config_sys.builtin_item_types import (
            ApplicationTechniquePlugin,
            PassiveAbilityPlugin,
            PowerSourcePlugin,
            BloodlinePlugin,
            MechPlugin,
            InventoryPlugin,
            CompanionPlugin,
            KnowledgePlugin,
            WorldTraversePlugin,
        )
        for plugin in [
            ApplicationTechniquePlugin(),
            PassiveAbilityPlugin(),
            PowerSourcePlugin(),
            BloodlinePlugin(),
            MechPlugin(),
            InventoryPlugin(),
            CompanionPlugin(),
            KnowledgePlugin(),
            WorldTraversePlugin(),
        ]:
            cls.register(plugin)
        logger.info(f"[ItemTypeRegistry] 启动完成，共 {len(cls._plugins)} 个物品类型")
