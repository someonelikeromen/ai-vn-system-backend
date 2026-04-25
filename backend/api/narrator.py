"""
Narrator API — 章节固化 + 世界档案 + 主角状态
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/narrator", tags=["narrator"])


class ChapterAnchorRequest(BaseModel):
    chapter_title:    str
    chapter_summary:  str = ""
    arc_label:        str = ""


@router.post("/{novel_id}/chapters")
async def anchor_chapter(novel_id: str, req: ChapterAnchorRequest):
    """
    固化当前章节（书记员 STEP 4 完成后由前端触发）。
    触发记忆压缩 + Planner 章节规划。
    """
    from db.queries import get_db
    from memory.engine import memory_engine

    db = get_db()
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    world_key = novel.get("current_world_key", "")

    # 创建章节记录
    chapter_id = await db.create_chapter(
        novel_id=novel_id,
        title=req.chapter_title,
        summary=req.chapter_summary,
        arc_label=req.arc_label,
        world_key=world_key,
    )

    # 触发记忆压缩
    removed_count = await memory_engine.consolidate(
        novel_id=novel_id,
        world_key=world_key,
        chapter_id=chapter_id,
    )

    return {
        "chapter_id":       chapter_id,
        "title":            req.chapter_title,
        "memory_compressed": removed_count,
        "message":          f"第{chapter_id}章已固化",
    }


@router.get("/{novel_id}/chapters")
async def list_chapters(novel_id: str):
    """获取章节列表"""
    from db.queries import get_db
    db = get_db()
    chapters = await db.list_chapters(novel_id)
    return {"chapters": chapters, "count": len(chapters)}


@router.post("/{novel_id}/chapters/{chapter_id}/rollback")
async def rollback_chapter(novel_id: str, chapter_id: str):
    """回滚指定章节（清除脏节点，恢复消息记录）"""
    from db.queries import get_db
    from memory.engine import memory_engine

    db = get_db()
    chapter = await db.get_chapter(novel_id, chapter_id)
    if not chapter:
        raise HTTPException(404, "章节不存在")

    created_at = chapter.get("created_at", "")

    # 记忆回滚
    rollback_result = await memory_engine.rollback(
        novel_id=novel_id,
        chapter_id=chapter_id,
        chapter_created_at=created_at,
    )

    # 删除章节和消息记录
    await db.delete_chapter(novel_id, chapter_id)

    return {
        "chapter_id":     chapter_id,
        "graph_removed":  rollback_result["graph_removed"],
        "vector_removed": rollback_result["vector_removed"],
        "message":        f"章节 {chapter_id} 已回滚",
    }


@router.get("/{novel_id}/world/{world_key}")
async def get_world_archive(novel_id: str, world_key: str):
    """获取世界档案"""
    from db.queries import get_db
    db = get_db()
    archive = await db.get_world_archive(novel_id, world_key)
    return {"world_key": world_key, "archive": archive}


@router.put("/{novel_id}/world/{world_key}")
async def upsert_world_archive(novel_id: str, world_key: str, body: dict):
    """更新世界档案"""
    from db.queries import get_db
    db = get_db()
    await db.upsert_world_archive(novel_id, world_key, body)
    return {"message": "世界档案已更新", "world_key": world_key}


@router.get("/{novel_id}/hooks")
async def get_hooks(novel_id: str, status: str = "active"):
    """获取伏笔/Hook列表"""
    from db.queries import get_db
    db = get_db()
    if status == "active":
        hooks = await db.get_active_hooks(novel_id)
    else:
        hooks = await db._fetchall(
            "SELECT * FROM narrative_hooks WHERE novel_id=? ORDER BY seeded_at DESC",
            (novel_id,)
        )
    return {"hooks": hooks, "count": len(hooks)}


@router.get("/{novel_id}/protagonist")
async def get_protagonist_full(novel_id: str):
    """获取主角完整状态（含物品/成长记录）"""
    from db.queries import get_db
    db = get_db()

    protagonist = await db.get_protagonist_state(novel_id)
    if not protagonist:
        raise HTTPException(404, "主角未初始化")

    owned_items = await db.get_owned_items(novel_id)
    medals_rows = await db._fetchall("SELECT stars, count FROM medals WHERE novel_id=?", (novel_id,))
    medals      = {int(r["stars"]): int(r["count"]) for r in medals_rows}
    points      = protagonist.get("points", 0)

    return {
        "protagonist": protagonist,
        "owned_items": owned_items,
        "medals":      medals,
        "points":      points,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 成就系统
# ═══════════════════════════════════════════════════════════════════════════

class UnlockAchievementRequest(BaseModel):
    achievement_key: str
    title: str
    description: str = ""
    chapter_id: str = ""
    reward_type: str = ""
    reward_value: Optional[dict] = None


@router.get("/{novel_id}/achievements")
async def list_achievements(novel_id: str):
    """获取小说的所有已解锁成就"""
    from db.queries import get_db
    db = get_db()
    achievements = await db.get_achievements(novel_id)
    return {"achievements": achievements, "count": len(achievements)}


@router.post("/{novel_id}/achievements/unlock", status_code=201)
async def unlock_achievement(novel_id: str, req: UnlockAchievementRequest):
    """手动解锁成就（供测试或剧情触发使用）"""
    from db.queries import get_db
    db = get_db()
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    achievement_id = await db.unlock_achievement(
        novel_id=novel_id,
        achievement_key=req.achievement_key,
        title=req.title,
        description=req.description,
        chapter_id=req.chapter_id,
        reward_type=req.reward_type,
        reward_value=req.reward_value,
    )
    if achievement_id is None:
        return {"message": "成就已存在，跳过", "already_unlocked": True}
    return {"achievement_id": achievement_id, "message": f"解锁成就：{req.title}"}


# ═══════════════════════════════════════════════════════════════════════════
# 记忆图谱调试端点
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{novel_id}/memory/nodes")
async def get_memory_nodes(
    novel_id: str,
    node_type: str = "",
    world_key: str = "",
    limit: int = 50,
):
    """
    返回记忆图谱节点列表（调试用）。
    支持按 node_type 和 world_key 过滤，最多返回 limit 条。
    """
    from memory.graph import graph_manager
    from memory.schema import NodeType

    # 构建类型过滤
    if node_type:
        try:
            types = [NodeType(node_type)]
        except ValueError:
            raise HTTPException(400, f"无效的 node_type: {node_type}")
    else:
        types = list(NodeType)

    nodes = await graph_manager.get_nodes_by_type(novel_id, types, world_key)

    # 按创建时间倒序，截断
    nodes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    nodes = nodes[:limit]

    stats = graph_manager.get_stats(novel_id)

    return {
        "stats": stats,
        "nodes": nodes,
        "returned": len(nodes),
        "world_key_filter": world_key,
        "type_filter": node_type,
    }


@router.get("/{novel_id}/npcs")
async def list_npcs(novel_id: str):
    """
    获取所有 NPC 档案列表（人际关系面板使用）。
    返回每个 NPC 的名字、类型、好感度、情感类型、外貌等信息。
    """
    import json as _json
    from db.queries import get_db
    db = get_db()

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    npc_rows = await db._fetchall(
        "SELECT name, npc_type, world_key, initial_affinity, loyalty_type, "
        "       trait_lock, knowledge_scope, capability_cap, psyche_model, "
        "       companion_slot "
        "FROM npc_profiles WHERE novel_id=? ORDER BY initial_affinity DESC",
        (novel_id,),
    )

    npcs = []
    for row in npc_rows:
        psyche = {}
        try:
            pm = row.get("psyche_model")
            if isinstance(pm, str):
                psyche = _json.loads(pm)
            elif isinstance(pm, dict):
                psyche = pm
        except Exception:
            pass

        trait_lock = []
        try:
            tl = row.get("trait_lock")
            if isinstance(tl, str):
                trait_lock = _json.loads(tl)
            elif isinstance(tl, list):
                trait_lock = tl
        except Exception:
            pass

        npcs.append({
            "name":             row["name"],
            "npc_type":         row.get("npc_type", "neutral"),
            "world_key":        row.get("world_key", ""),
            "initial_affinity": row.get("initial_affinity", 50),
            "loyalty_type":     row.get("loyalty_type", ""),
            "trait_lock":       trait_lock,
            "companion_slot":   row.get("companion_slot", 0),
            "emotion_type":     psyche.get("emotion_type", "related"),
            "emotion_tags":     psyche.get("emotion_tags", []),
            "relation_label":   psyche.get("relation_to_protagonist", ""),
            "background":       psyche.get("background", ""),
            "appearance":       psyche.get("appearance", ""),
        })

    return {"npcs": npcs, "count": len(npcs)}
