"""数据库异步查询集合 — 覆盖所有表的 CRUD 操作"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from loguru import logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class Database:
    """异步数据库访问对象（单例，由 main.py 启动时初始化）"""

    def __init__(self, db_path: str):
        self._path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA synchronous  = NORMAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        await self._conn.execute("PRAGMA cache_size   = -64000")
        logger.info("数据库连接已建立")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("数据库连接已关闭")

    # ── 事务上下文 ────────────────────────────────────────────────────────
    def transaction(self):
        return self._conn  # aiosqlite Connection 支持 async with

    async def _exec(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur

    async def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        cur = await self._conn.execute(sql, params)
        row = await cur.fetchone()
        return dict(row) if row else None

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = await self._conn.execute(sql, params)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ════════════════════════════════════════════════════════════════════════
    # 小说管理
    # ════════════════════════════════════════════════════════════════════════

    async def create_novel(
        self,
        title: str,
        ip_type: str = "original",
        world_type: str = "single_world",
        current_world_key: str = "",
        attr_schema_id: str = "standard_10d",
    ) -> str:
        novel_id = _uid()
        now = _now()
        await self._exec(
            "INSERT INTO novels (novel_id,title,ip_type,world_type,current_world_key,"
            "attr_schema_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (novel_id, title, ip_type, world_type, current_world_key, attr_schema_id, now, now),
        )
        return novel_id

    async def get_novel(self, novel_id: str) -> Optional[dict]:
        row = await self._fetchone("SELECT * FROM novels WHERE novel_id=?", (novel_id,))
        if row:
            # 反序列化 JSON 字段
            for field in ("default_style_stack",):
                if row.get(field) and isinstance(row[field], str):
                    try:
                        row[field] = json.loads(row[field])
                    except Exception:
                        row[field] = []
        return row

    async def list_novels(self, archived: bool = False) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM novels WHERE archived=? ORDER BY updated_at DESC",
            (1 if archived else 0,),
        )

    async def update_novel(self, novel_id: str, **kwargs) -> None:
        kwargs["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        await self._exec(
            f"UPDATE novels SET {sets} WHERE novel_id=?",
            (*kwargs.values(), novel_id),
        )

    async def delete_novel(self, novel_id: str) -> None:
        await self._exec("DELETE FROM novels WHERE novel_id=?", (novel_id,))

    # ════════════════════════════════════════════════════════════════════════
    # 主角状态
    # ════════════════════════════════════════════════════════════════════════

    async def init_protagonist(
        self,
        novel_id: str,
        name: str,
        world_key: str = "",
        attr_schema_id: str = "standard_10d",
    ) -> None:
        from config_sys.attribute_schema import get_default_attributes  # 避免循环导入
        default_attrs = json.dumps(get_default_attributes(attr_schema_id))
        await self._exec(
            "INSERT OR IGNORE INTO protagonist_state "
            "(novel_id,name,points,tier,tier_sub,attributes,energy_pools,status_effects,world_key,updated_at) "
            "VALUES (?,?,0,0,'M',?,'{}','[]',?,?)",
            (novel_id, name, default_attrs, world_key, _now()),
        )

    async def get_protagonist_state(self, novel_id: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM protagonist_state WHERE novel_id=?", (novel_id,)
        )
        if row:
            # 反序列化 JSON 字段
            json_fields = (
                "attributes", "energy_pools", "status_effects",
                "psyche_model_json", "knowledge_scope",
                "personality", "flaws", "desires", "fears", "quirks", "traits",
            )
            for field in json_fields:
                if row.get(field) and isinstance(row[field], str):
                    row[field] = json.loads(row[field])
        return row

    async def update_protagonist_state(self, novel_id: str, **kwargs) -> None:
        # 自动序列化 JSON 字段
        json_fields = (
            "attributes", "energy_pools", "status_effects",
            "psyche_model_json", "knowledge_scope",
            "personality", "flaws", "desires", "fears", "quirks", "traits",
        )
        for field in json_fields:
            if field in kwargs and not isinstance(kwargs[field], str):
                kwargs[field] = json.dumps(kwargs[field], ensure_ascii=False)
        kwargs["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        await self._exec(
            f"UPDATE protagonist_state SET {sets} WHERE novel_id=?",
            (*kwargs.values(), novel_id),
        )

    async def add_points(self, novel_id: str, delta: int) -> int:
        """原子增加积分，返回新余额"""
        await self._exec(
            "UPDATE protagonist_state SET points=points+?, updated_at=? WHERE novel_id=?",
            (delta, _now(), novel_id),
        )
        row = await self._fetchone(
            "SELECT points FROM protagonist_state WHERE novel_id=?", (novel_id,)
        )
        return row["points"] if row else 0

    async def deduct_points(self, novel_id: str, amount: int) -> None:
        await self._exec(
            "UPDATE protagonist_state SET points=points-?, updated_at=? WHERE novel_id=?",
            (amount, _now(), novel_id),
        )

    async def get_medal_count(self, novel_id: str, stars: int) -> int:
        row = await self._fetchone(
            "SELECT count FROM medals WHERE novel_id=? AND stars=?", (novel_id, stars)
        )
        return row["count"] if row else 0

    async def add_medal(self, novel_id: str, stars: int, count: int = 1) -> None:
        await self._exec(
            "INSERT INTO medals (novel_id,stars,count) VALUES (?,?,?) "
            "ON CONFLICT(novel_id,stars) DO UPDATE SET count=count+?",
            (novel_id, stars, count, count),
        )

    async def split_medal(
        self, novel_id: str, stars: int, count: int = 1
    ) -> dict:
        """
        规格 §2.1：凭证拆分（只能向下拆，禁止合成）。
        1枚 X★凭证 = 5枚 (X-1)★凭证。
        最低 1★，无法再拆。
        返回 {success, split_from, split_into, produced}
        """
        if stars <= 1:
            return {"success": False, "reason": "1★凭证是最低级，无法继续拆分"}
        have = await self.get_medal_count(novel_id, stars)
        if have < count:
            return {"success": False, "reason": f"持有 {have} 枚 {stars}★凭证，不足 {count} 枚"}
        # 扣除高档凭证
        await self._exec(
            "UPDATE medals SET count=count-? WHERE novel_id=? AND stars=?",
            (count, novel_id, stars),
        )
        # 增加低档凭证（1枚产出5枚）
        produced = count * 5
        target_stars = stars - 1
        await self.add_medal(novel_id, target_stars, produced)
        return {
            "success": True,
            "split_from": stars,
            "split_into": target_stars,
            "count_consumed": count,
            "produced": produced,
        }

    async def get_world_peak_tier(self, novel_id: str, world_key: str) -> tuple[int, str]:
        """获取指定世界的 peak_tier 和 peak_tier_sub（WorldTraverse 定价使用）"""
        row = await self._fetchone(
            "SELECT peak_tier, peak_tier_sub FROM world_archives "
            "WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )
        if row:
            return int(row.get("peak_tier", 0)), row.get("peak_tier_sub", "M")
        return 0, "M"

    async def append_protagonist_knowledge(self, novel_id: str, knowledge_name: str) -> None:
        row = await self._fetchone(
            "SELECT knowledge_scope FROM protagonist_state WHERE novel_id=?", (novel_id,)
        )
        if not row:
            return
        scope = json.loads(row["knowledge_scope"] or "[]")
        if knowledge_name not in scope:
            scope.append(knowledge_name)
            await self._exec(
                "UPDATE protagonist_state SET knowledge_scope=?, updated_at=? WHERE novel_id=?",
                (json.dumps(scope, ensure_ascii=False), _now(), novel_id),
            )

    # ════════════════════════════════════════════════════════════════════════
    # 物品目录与持有列表
    # ════════════════════════════════════════════════════════════════════════

    async def upsert_item_catalog(self, item: dict) -> None:
        for field in ("payload_template", "required_medals"):
            if field in item and not isinstance(item[field], str):
                item[field] = json.dumps(item[field], ensure_ascii=False)
        item.setdefault("created_at", _now())
        cols = ", ".join(item.keys())
        placeholders = ", ".join("?" * len(item))
        updates = ", ".join(f"{k}=excluded.{k}" for k in item if k != "item_key")
        await self._exec(
            f"INSERT INTO item_catalog ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(item_key) DO UPDATE SET {updates}",
            tuple(item.values()),
        )

    async def get_catalog_item(self, item_key: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM item_catalog WHERE item_key=?", (item_key,)
        )
        if row:
            for f in ("payload_template", "required_medals"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return row

    async def query_item_catalog(
        self, world_key: str = "", item_type: str = "", filters: dict = None
    ) -> list[dict]:
        conds = []
        params: list = []
        if world_key:
            conds.append("source_world=?")
            params.append(world_key)
        if item_type:
            conds.append("item_type=?")
            params.append(item_type)
        where = "WHERE " + " AND ".join(conds) if conds else ""
        rows = await self._fetchall(f"SELECT * FROM item_catalog {where} ORDER BY base_tier,base_tier_sub", tuple(params))
        for row in rows:
            for f in ("payload_template", "required_medals"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return rows

    async def search_item_catalog(self, query: str, filters: dict = None) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM item_catalog WHERE name LIKE ? OR source_world LIKE ?",
            (f"%{query}%", f"%{query}%"),
        )
        for row in rows:
            for f in ("payload_template", "required_medals"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return rows

    async def insert_owned_item(self, item: dict) -> str:
        item_id = item.get("id") or _uid()
        item["id"] = item_id
        for f in ("payload",):
            if f in item and not isinstance(item[f], str):
                item[f] = json.dumps(item[f], ensure_ascii=False)
        cols = ", ".join(item.keys())
        placeholders = ", ".join("?" * len(item))
        await self._exec(
            f"INSERT INTO owned_items ({cols}) VALUES ({placeholders})",
            tuple(item.values()),
        )
        return item_id

    async def get_owned_item_by_id(self, owned_id: str) -> Optional[dict]:
        row = await self._fetchone("SELECT * FROM owned_items WHERE id=?", (owned_id,))
        if row and isinstance(row.get("payload"), str):
            row["payload"] = json.loads(row["payload"])
        return row

    async def get_owned_items(self, novel_id: str, item_type: str = "") -> list[dict]:
        if item_type:
            rows = await self._fetchall(
                "SELECT * FROM owned_items WHERE novel_id=? AND item_type=? AND is_active=1",
                (novel_id, item_type),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM owned_items WHERE novel_id=? AND is_active=1", (novel_id,)
            )
        for row in rows:
            if isinstance(row.get("payload"), str):
                row["payload"] = json.loads(row["payload"])
        return rows

    async def get_owned_items_by_type(self, novel_id: str, item_type: str) -> list[dict]:
        return await self.get_owned_items(novel_id, item_type)

    async def is_item_owned(self, novel_id: str, item_key: str) -> bool:
        row = await self._fetchone(
            "SELECT id FROM owned_items WHERE novel_id=? AND item_key=? AND is_active=1",
            (novel_id, item_key),
        )
        return row is not None

    # ════════════════════════════════════════════════════════════════════════
    # 通用成长系统
    # ════════════════════════════════════════════════════════════════════════

    async def init_growth_record(
        self, novel_id: str, owned_id: str, growth_key: str, sub_key: str = None
    ) -> None:
        owned = await self.get_owned_item_by_id(owned_id)
        item_type = owned["item_type"] if owned else "Unknown"
        rec_id = _uid()
        await self._exec(
            "INSERT OR IGNORE INTO growth_records "
            "(id,novel_id,owned_id,item_type,growth_key,sub_key,current_xp,level_index,"
            "use_count,last_event_at,version) VALUES (?,?,?,?,?,?,0,0,0,?,0)",
            (rec_id, novel_id, owned_id, item_type, growth_key, sub_key, _now()),
        )

    async def get_growth_record(
        self, novel_id: str, owned_id: str, growth_key: str, sub_key: str = None
    ) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM growth_records WHERE novel_id=? AND owned_id=? "
            "AND growth_key=? AND sub_key IS ?",
            (novel_id, owned_id, growth_key, sub_key),
        )

    async def compare_and_swap_growth_record(
        self,
        novel_id: str, owned_id: str,
        growth_key: str, sub_key: Optional[str],
        new_xp: int, new_level_idx: int,
        expected_version: int,
    ) -> int:
        cur = await self._exec(
            "UPDATE growth_records SET current_xp=?,level_index=?,version=version+1,"
            "last_event_at=? "
            "WHERE novel_id=? AND owned_id=? AND growth_key=? AND sub_key IS ? AND version=?",
            (new_xp, new_level_idx, _now(), novel_id, owned_id, growth_key, sub_key, expected_version),
        )
        await self._conn.commit()
        return cur.rowcount

    async def growth_event_exists(self, event_id: str) -> bool:
        row = await self._fetchone(
            "SELECT event_id FROM growth_event_records WHERE event_id=?", (event_id,)
        )
        return row is not None

    async def mark_growth_event_settled(
        self, event_id: str, novel_id: str, results: dict
    ) -> None:
        await self._exec(
            "INSERT OR IGNORE INTO growth_event_records "
            "(event_id,novel_id,event_type,xp_grants,settled_at) VALUES (?,?,'settled',?,?)",
            (event_id, novel_id, json.dumps(results, ensure_ascii=False), _now()),
        )

    # ════════════════════════════════════════════════════════════════════════
    # 章节与叙事
    # ════════════════════════════════════════════════════════════════════════

    async def create_chapter(
        self,
        novel_id: str,
        title: str,
        summary: str = "",
        arc_label: str = "",
        world_key: str = "",
    ) -> str:
        """创建并固化章节记录，自动分配章节号"""
        cur = await self._conn.execute(
            "SELECT COALESCE(MAX(chapter_num),0)+1 FROM chapters WHERE novel_id=?",
            (novel_id,),
        )
        row = await cur.fetchone()
        chapter_num = row[0] if row else 1
        chapter_id  = f"ch_{novel_id[:8]}_{chapter_num:04d}"
        now = _now()
        await self._exec(
            "INSERT OR IGNORE INTO chapters "
            "(id,novel_id,chapter_num,title,world_key,summary,arc_label,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (chapter_id, novel_id, chapter_num, title, world_key, summary, arc_label, now),
        )
        return chapter_id

    async def save_chapter(
        self,
        novel_id: str,
        chapter_num: int,
        title: str = "",
        world_key: str = "",
        raw_content: str = "",
        summary: str = "",
    ) -> str:
        chapter_id = f"ch_{novel_id[:8]}_{chapter_num:04d}"
        await self._exec(
            "INSERT INTO chapters (id,novel_id,chapter_num,title,world_key,"
            "raw_content,summary,created_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(novel_id,chapter_num) DO UPDATE SET "
            "title=excluded.title,raw_content=excluded.raw_content,summary=excluded.summary",
            (chapter_id, novel_id, chapter_num, title, world_key, raw_content, summary, _now()),
        )
        return chapter_id

    async def get_chapter(self, novel_id: str, chapter_id: str) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM chapters WHERE novel_id=? AND id=?", (novel_id, chapter_id)
        )

    async def delete_chapter(self, novel_id: str, chapter_id: str) -> None:
        await self._exec(
            "DELETE FROM chapters WHERE novel_id=? AND id=?", (novel_id, chapter_id)
        )

    async def list_chapters(self, novel_id: str) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM chapters WHERE novel_id=? ORDER BY chapter_num", (novel_id,)
        )


    async def register_hook(
        self,
        novel_id: str,
        description: str,
        seeded_at_chapter: str = "",
        urgency: str = "low",
    ) -> str:
        hook_id = _uid()
        await self._exec(
            "INSERT INTO narrative_hooks (id,novel_id,description,seeded_at_chapter,urgency) "
            "VALUES (?,?,?,?,?)",
            (hook_id, novel_id, description, seeded_at_chapter, urgency),
        )
        return hook_id

    async def get_active_hooks(self, novel_id: str) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM narrative_hooks WHERE novel_id=? AND status='active' "
            "ORDER BY CASE urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 ELSE 3 END",
            (novel_id,),
        )

    async def resolve_hook(self, hook_id: str, chapter_id: str) -> None:
        await self._exec(
            "UPDATE narrative_hooks SET status='resolved',resolved_at_chapter=? WHERE id=?",
            (chapter_id, hook_id),
        )

    # ════════════════════════════════════════════════════════════════════════
    # 消息历史
    # ════════════════════════════════════════════════════════════════════════

    async def append_message(
        self,
        novel_id: str,
        role: str,
        raw_content: str,
        display_content: str = "",
        chapter_id: str = "",
    ) -> str:
        msg_id = _uid()
        cur = await self._conn.execute(
            "SELECT COALESCE(MAX(message_order),0)+1 FROM messages WHERE novel_id=?",
            (novel_id,),
        )
        row = await cur.fetchone()
        order = row[0]
        await self._exec(
            "INSERT INTO messages (id,novel_id,role,raw_content,display_content,"
            "created_at,chapter_id,message_order) VALUES (?,?,?,?,?,?,?,?)",
            (msg_id, novel_id, role, raw_content, display_content or raw_content,
             _now(), chapter_id, order),
        )
        return msg_id

    async def get_messages(self, novel_id: str, limit: int = 100) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM messages WHERE novel_id=? ORDER BY message_order DESC LIMIT ?",
            (novel_id, limit),
        )

    async def delete_messages_from(self, novel_id: str, from_order: int) -> list[str]:
        rows = await self._fetchall(
            "SELECT id FROM messages WHERE novel_id=? AND message_order>=?",
            (novel_id, from_order),
        )
        ids = [r["id"] for r in rows]
        await self._exec(
            "DELETE FROM messages WHERE novel_id=? AND message_order>=?",
            (novel_id, from_order),
        )
        return ids

    # ════════════════════════════════════════════════════════════════════════
    # NPC 档案
    # ════════════════════════════════════════════════════════════════════════

    async def upsert_npc(self, novel_id: str, name: str, data: dict) -> str:
        existing = await self._fetchone(
            "SELECT id FROM npc_profiles WHERE novel_id=? AND name=?", (novel_id, name)
        )
        if existing:
            npc_id = existing["id"]
            sets_parts = []
            vals = []
            for k, v in data.items():
                sets_parts.append(f"{k}=?")
                vals.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            await self._exec(
                f"UPDATE npc_profiles SET {', '.join(sets_parts)} WHERE id=?",
                (*vals, npc_id),
            )
        else:
            npc_id = _uid()
            for f in ("trait_lock", "knowledge_scope", "capability_cap", "psyche_model"):
                if f in data and not isinstance(data[f], str):
                    data[f] = json.dumps(data[f], ensure_ascii=False)
            data.update({"id": npc_id, "novel_id": novel_id, "name": name, "created_at": _now()})
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            await self._exec(
                f"INSERT INTO npc_profiles ({cols}) VALUES ({placeholders})",
                tuple(data.values()),
            )
        return npc_id

    async def get_npc(self, novel_id: str, name: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM npc_profiles WHERE novel_id=? AND name=?", (novel_id, name)
        )
        if row:
            for f in ("trait_lock", "knowledge_scope", "capability_cap", "psyche_model"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return row

    async def get_npcs_with_trait_lock(self, novel_id: str) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM npc_profiles WHERE novel_id=? AND trait_lock!='[]'", (novel_id,)
        )
        for row in rows:
            for f in ("trait_lock", "knowledge_scope"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return rows

    # ════════════════════════════════════════════════════════════════════════
    # Rollback Manifest
    # ════════════════════════════════════════════════════════════════════════

    async def save_rollback_manifest(
        self, novel_id: str, chapter_id: str, instructions: list[dict]
    ) -> str:
        manifest_id = _uid()
        await self._exec(
            "INSERT INTO rollback_manifests (id,novel_id,chapter_id,instructions,created_at) "
            "VALUES (?,?,?,?,?)",
            (manifest_id, novel_id, chapter_id,
             json.dumps(instructions, ensure_ascii=False), _now()),
        )
        return manifest_id

    async def get_rollback_manifests(self, novel_id: str, after_chapter_id: str) -> list[dict]:
        rows = await self._fetchall(
            "SELECT * FROM rollback_manifests WHERE novel_id=? "
            "AND created_at > (SELECT created_at FROM rollback_manifests WHERE id=?) "
            "ORDER BY created_at DESC",
            (novel_id, after_chapter_id),
        )
        for row in rows:
            if isinstance(row.get("instructions"), str):
                row["instructions"] = json.loads(row["instructions"])
        return rows

    # ════════════════════════════════════════════════════════════════════════
    # 世界档案
    # ════════════════════════════════════════════════════════════════════════

    async def upsert_world_archive(self, novel_id: str, world_key: str, data: dict) -> None:
        existing = await self._fetchone(
            "SELECT id FROM world_archives WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )
        for f in ("current_snapshot", "identity"):
            if f in data and not isinstance(data[f], str):
                data[f] = json.dumps(data[f], ensure_ascii=False)
        if existing:
            sets = ", ".join(f"{k}=?" for k in data)
            await self._exec(
                f"UPDATE world_archives SET {sets} WHERE novel_id=? AND world_key=?",
                (*data.values(), novel_id, world_key),
            )
        else:
            data.update({"id": _uid(), "novel_id": novel_id, "world_key": world_key,
                         "entered_at": _now(), "last_active_at": _now()})
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            await self._exec(
                f"INSERT INTO world_archives ({cols}) VALUES ({placeholders})",
                tuple(data.values()),
            )

    async def get_world_archive(self, novel_id: str, world_key: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM world_archives WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )
        if row:
            for f in ("current_snapshot", "identity"):
                if row.get(f) and isinstance(row[f], str):
                    row[f] = json.loads(row[f])
        return row

    async def get_world_catalog(self, novel_id: str, world_key: str) -> list[dict]:
        """获取世界兑换目录（LLM生成后缓存）"""
        row = await self._fetchone(
            "SELECT catalog_json FROM world_archives WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )
        if row and row.get("catalog_json"):
            try:
                return json.loads(row["catalog_json"])
            except Exception:
                return []
        return []

    async def upsert_world_catalog(
        self, novel_id: str, world_key: str, items: list[dict]
    ) -> None:
        """更新世界兑换目录"""
        catalog_json = json.dumps(items, ensure_ascii=False)
        existing = await self._fetchone(
            "SELECT id FROM world_archives WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )
        if existing:
            await self._exec(
                "UPDATE world_archives SET catalog_json=? WHERE novel_id=? AND world_key=?",
                (catalog_json, novel_id, world_key),
            )
        else:
            await self.upsert_world_archive(novel_id, world_key, {"catalog_json": catalog_json})

    async def clear_world_catalog(self, novel_id: str, world_key: str) -> None:
        """清除世界兑换目录缓存（触发重新生成）"""
        await self._exec(
            "UPDATE world_archives SET catalog_json=NULL WHERE novel_id=? AND world_key=?",
            (novel_id, world_key),
        )

    # ════════════════════════════════════════════════════════════════════════
    # node_sync_status
    # ════════════════════════════════════════════════════════════════════════

    async def upsert_node_sync(self, novel_id: str, node_id: str, **flags) -> None:
        await self._exec(
            "INSERT INTO node_sync_status (novel_id,node_id,created_at) VALUES (?,?,?) "
            "ON CONFLICT(novel_id,node_id) DO NOTHING",
            (novel_id, node_id, _now()),
        )
        if flags:
            sets = ", ".join(f"{k}=?" for k in flags)
            await self._exec(
                f"UPDATE node_sync_status SET {sets} WHERE novel_id=? AND node_id=?",
                (*flags.values(), novel_id, node_id),
            )

    async def mark_node_synced(self, novel_id: str, node_id: str) -> None:
        await self._exec(
            "UPDATE node_sync_status SET synced_at=? WHERE novel_id=? AND node_id=?",
            (_now(), novel_id, node_id),
        )

    async def get_unsynced_nodes(self, novel_id: str) -> list[dict]:
        return await self._fetchall(
            "SELECT * FROM node_sync_status WHERE novel_id=? AND synced_at IS NULL "
            "AND retry_count < 3",
            (novel_id,),
        )

    # ── Kill records & Decay ──────────────────────────────────────────────

    async def get_kill_record(self, novel_id: str, category: str) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM kill_records WHERE novel_id=? AND enemy_category=?",
            (novel_id, category),
        )

    async def upsert_kill_record(self, novel_id: str, category: str, data: dict) -> None:
        existing = await self.get_kill_record(novel_id, category)
        if existing:
            sets = ", ".join(f"{k}=?" for k in data)
            await self._exec(
                f"UPDATE kill_records SET {sets} WHERE novel_id=? AND enemy_category=?",
                (*data.values(), novel_id, category),
            )
        else:
            data.update({"novel_id": novel_id, "enemy_category": category})
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            await self._exec(
                f"INSERT INTO kill_records ({cols}) VALUES ({placeholders})",
                tuple(data.values()),
            )

    # ── Energy Pool ───────────────────────────────────────────────────────

    async def register_energy_pool(self, novel_id: str, pool: dict) -> None:
        """将新能量池写入 protagonist_state.energy_pools JSON"""
        row = await self._fetchone(
            "SELECT energy_pools FROM protagonist_state WHERE novel_id=?", (novel_id,)
        )
        if not row:
            return
        pools = json.loads(row["energy_pools"] or "{}")
        pool_name = pool.get("name", pool.get("type", "unnamed"))
        pools[pool_name] = {
            "current": pool.get("value", pool.get("max", 100)),
            "max": pool.get("max", 100),
            "regen": pool.get("regen", 0),
            "description": pool.get("description", ""),
        }
        await self._exec(
            "UPDATE protagonist_state SET energy_pools=?, updated_at=? WHERE novel_id=?",
            (json.dumps(pools, ensure_ascii=False), _now(), novel_id),
        )

    async def update_energy_pool(self, novel_id: str, pool_name: str, delta: int) -> None:
        row = await self._fetchone(
            "SELECT energy_pools FROM protagonist_state WHERE novel_id=?", (novel_id,)
        )
        if not row:
            return
        pools = json.loads(row["energy_pools"] or "{}")
        if pool_name in pools:
            cur = pools[pool_name].get("current", 0) + delta
            mx = pools[pool_name].get("max", float("inf"))
            pools[pool_name]["current"] = max(0, min(cur, mx))
            await self._exec(
                "UPDATE protagonist_state SET energy_pools=?, updated_at=? WHERE novel_id=?",
                (json.dumps(pools, ensure_ascii=False), _now(), novel_id),
            )

    # ════════════════════════════════════════════════════════════════════════
    # 成就系统
    # ════════════════════════════════════════════════════════════════════════

    async def get_achievements(self, novel_id: str) -> list[dict]:
        """获取小说的所有已解锁成就，按解锁时间降序排列"""
        return await self._fetchall(
            "SELECT * FROM achievements WHERE novel_id=? ORDER BY unlocked_at DESC",
            (novel_id,),
        )

    async def unlock_achievement(
        self,
        novel_id: str,
        achievement_key: str,
        title: str,
        description: str = "",
        chapter_id: str = "",
        reward_type: str = "",
        reward_value: Any = None,
    ) -> Optional[str]:
        """
        解锁成就（幂等：已存在则跳过，返回 None）。
        成功解锁返回成就 ID。
        """
        existing = await self._fetchone(
            "SELECT id FROM achievements WHERE novel_id=? AND achievement_key=?",
            (novel_id, achievement_key),
        )
        if existing:
            return None  # 已解锁，幂等

        achievement_id = _uid()
        await self._exec(
            "INSERT INTO achievements (id,novel_id,achievement_key,title,description,"
            "unlocked_at,chapter_id,reward_type,reward_value) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                achievement_id, novel_id, achievement_key, title, description,
                _now(), chapter_id or "", reward_type or "",
                json.dumps(reward_value, ensure_ascii=False) if reward_value is not None else None,
            ),
        )
        return achievement_id

    async def achievement_exists(self, novel_id: str, achievement_key: str) -> bool:
        """检查成就是否已解锁"""
        row = await self._fetchone(
            "SELECT id FROM achievements WHERE novel_id=? AND achievement_key=?",
            (novel_id, achievement_key),
        )
        return row is not None

    # ════════════════════════════════════════════════════════════════════════
    # 回合快照（per-turn rollback）
    # ════════════════════════════════════════════════════════════════════════

    async def save_turn_snapshot(
        self,
        novel_id: str,
        protagonist_before: dict,
        grants: list,
        medals: list = None,
        growth_records: list = None,
    ) -> str:
        """
        在 archiver 归档前调用，保存本轮开始时的主角/凭证/成长快照。
        自动清理，只保留最近 5 条快照。
        """
        cur = await self._conn.execute(
            "SELECT COALESCE(MAX(message_order),0)+1 FROM messages WHERE novel_id=?",
            (novel_id,),
        )
        row = await cur.fetchone()
        user_order = row[0] if row else 1

        snap_id = _uid()
        snap_time = _now()
        await self._exec(
            "INSERT OR REPLACE INTO turn_snapshots "
            "(id, novel_id, user_message_order, protagonist_json, grants_json, "
            " medals_json, growth_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                snap_id, novel_id, user_order,
                json.dumps(protagonist_before, ensure_ascii=False),
                json.dumps(grants, ensure_ascii=False),
                json.dumps([dict(m) for m in (medals or [])], ensure_ascii=False),
                json.dumps([dict(g) for g in (growth_records or [])], ensure_ascii=False),
                snap_time,
            ),
        )

        # 清理：只保留最新 5 条
        await self._exec(
            "DELETE FROM turn_snapshots WHERE novel_id=? AND id NOT IN ("
            "  SELECT id FROM turn_snapshots WHERE novel_id=? "
            "  ORDER BY created_at DESC LIMIT 5"
            ")",
            (novel_id, novel_id),
        )
        return snap_id

    async def get_recent_turn_snapshots(self, novel_id: str, limit: int = 3) -> list[dict]:
        """获取最近 N 条快照（含消息摘要及积分/tier 信息）"""
        snaps = await self._fetchall(
            "SELECT * FROM turn_snapshots WHERE novel_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (novel_id, limit),
        )
        result = []
        for s in snaps:
            user_order = s["user_message_order"]
            msgs = await self._fetchall(
                "SELECT role, display_content, message_order FROM messages "
                "WHERE novel_id=? AND message_order IN (?,?) ORDER BY message_order",
                (novel_id, user_order, user_order + 1),
            )
            p_data = json.loads(s["protagonist_json"]) if isinstance(s["protagonist_json"], str) else s["protagonist_json"]
            result.append({
                "snapshot_id":        s["id"],
                "user_message_order": user_order,
                "created_at":         s["created_at"],
                "protagonist_points": p_data.get("points", 0),
                "protagonist_name":   p_data.get("name", ""),
                "protagonist_tier":   p_data.get("tier", 0),
                "messages_preview":   [
                    {"role": m["role"], "preview": (m["display_content"] or "")[:80]}
                    for m in msgs
                ],
            })
        return result

    async def rollback_to_snapshot(self, novel_id: str, snapshot_id: str) -> dict:
        """
        完整回滚到指定快照（七层数据全部还原）：
        1. protagonist_state
        2. medals 凭证
        3. growth_records XP/等级
        4. growth_event_log 幂等键（防重复结算）
        5. narrative_hooks
        6. messages
        7. turn_snapshots 自身
        返回 snapshot_created_at 供调用方清理记忆图谱
        """
        snap = await self._fetchone(
            "SELECT * FROM turn_snapshots WHERE id=? AND novel_id=?",
            (snapshot_id, novel_id),
        )
        if not snap:
            return {"error": "快照不存在"}

        user_order      = snap["user_message_order"]
        snap_created_at = snap["created_at"]
        protagonist_data = json.loads(snap["protagonist_json"]) if isinstance(snap["protagonist_json"], str) else snap["protagonist_json"]
        medals_data      = json.loads(snap["medals_json"])       if isinstance(snap.get("medals_json"), str) else (snap.get("medals_json") or [])
        growth_data      = json.loads(snap["growth_json"])       if isinstance(snap.get("growth_json"), str)  else (snap.get("growth_json") or [])

        # ── 1. 恢复主角状态 ──────────────────────────────────────────────
        restorable = {k: v for k, v in protagonist_data.items() if k not in ("novel_id", "updated_at")}
        json_fields = (
            "attributes", "energy_pools", "status_effects",
            "psyche_model_json", "knowledge_scope",
            "personality", "flaws", "desires", "fears", "quirks", "traits",
        )
        for field in json_fields:
            if field in restorable and not isinstance(restorable[field], str):
                restorable[field] = json.dumps(restorable[field], ensure_ascii=False)
        restorable["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in restorable)
        await self._exec(
            f"UPDATE protagonist_state SET {sets} WHERE novel_id=?",
            (*restorable.values(), novel_id),
        )

        # ── 2. 恢复凭证（清空重建）──────────────────────────────────────
        await self._exec("DELETE FROM medals WHERE novel_id=?", (novel_id,))
        for m in medals_data:
            stars = m.get("stars", 0)
            count = m.get("count", 0)
            if int(count) > 0:
                await self._exec(
                    "INSERT OR REPLACE INTO medals (novel_id, stars, count) VALUES (?,?,?)",
                    (novel_id, int(stars), int(count)),
                )

        # ── 3. 恢复 XP/成长记录（直接覆写）──────────────────────────────
        for g in growth_data:
            owned_id   = g.get("owned_id", "")
            growth_key = g.get("growth_key", "")
            sub_key    = g.get("sub_key")  # may be None
            if owned_id and growth_key:
                await self._exec(
                    "UPDATE growth_records "
                    "SET current_xp=?, level_index=?, use_count=?, version=version+1, last_event_at=? "
                    "WHERE novel_id=? AND owned_id=? AND growth_key=? AND sub_key IS ?",
                    (int(g.get("current_xp", 0)), int(g.get("level_index", 0)),
                     int(g.get("use_count", 0)), _now(),
                     novel_id, owned_id, growth_key, sub_key),
                )

        # ── 4. 删除快照时间之后的幂等键 ──────────────────────────────────
        try:
            await self._exec(
                "DELETE FROM growth_event_log WHERE novel_id=? AND settled_at>=?",
                (novel_id, snap_created_at),
            )
        except Exception:
            pass

        # ── 5. 删除快照时间之后的 narrative_hooks ────────────────────────
        try:
            await self._exec(
                "DELETE FROM narrative_hooks WHERE novel_id=? AND created_at>=?",
                (novel_id, snap_created_at),
            )
        except Exception:
            pass

        # ── 6. 删除该轮及之后的消息 ──────────────────────────────────────
        deleted_msgs_rows = await self._fetchall(
            "SELECT id FROM messages WHERE novel_id=? AND message_order>=?",
            (novel_id, user_order),
        )
        deleted_msg_count = len(deleted_msgs_rows)
        await self._exec(
            "DELETE FROM messages WHERE novel_id=? AND message_order>=?",
            (novel_id, user_order),
        )

        # ── 7. 删除该快照及之后的快照 ────────────────────────────────────
        await self._exec(
            "DELETE FROM turn_snapshots WHERE novel_id=? AND created_at>=?",
            (novel_id, snap_created_at),
        )

        return {
            "snapshot_id":         snapshot_id,
            "snapshot_created_at": snap_created_at,
            "restored_to_order":   user_order,
            "deleted_messages":    deleted_msg_count,
            "protagonist_name":    protagonist_data.get("name", ""),
            "protagonist_points":  protagonist_data.get("points", 0),
            "medals_restored":     len(medals_data),
            "growth_restored":     len(growth_data),
        }


# ── 全局单例 ──────────────────────────────────────────────────────────────────
_db_instance: Optional[Database] = None


def get_db() -> Database:
    if _db_instance is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db_instance()")
    return _db_instance


async def init_db_instance(db_path: str) -> Database:
    global _db_instance
    _db_instance = Database(db_path)
    await _db_instance.connect()
    return _db_instance
