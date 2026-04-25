"""
reset_novel_content.py
重置小说正文内容（消息、记忆图谱对话节点、快照），保留：
- protagonist_state（主角状态）
- npc_profiles（NPC档案）
- protagonist 基础 CHARACTER 节点（图谱）
"""
import asyncio, sys, os, json, glob

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

# 重置目标：从命令行传入，或使用默认值
NOVEL_ID = sys.argv[1] if len(sys.argv) > 1 else "12c5ac18-2005-491c-b0da-1ec827bff09b"

async def main():
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance

    s = get_settings()
    await init_db(str(s.db_path_resolved))
    db = await init_db_instance(str(s.db_path_resolved))

    print(f"[重置] novel_id={NOVEL_ID}")

    # ── 1. 统计当前状态 ─────────────────────────────────────────────
    msg_count   = (await db._fetchone("SELECT COUNT(*) as c FROM messages WHERE novel_id=?",            (NOVEL_ID,)) or {}).get('c', 0)
    snap_count  = (await db._fetchone("SELECT COUNT(*) as c FROM turn_snapshots WHERE novel_id=?",      (NOVEL_ID,)) or {}).get('c', 0)
    hook_count  = (await db._fetchone("SELECT COUNT(*) as c FROM narrative_hooks WHERE novel_id=?",     (NOVEL_ID,)) or {}).get('c', 0)
    chap_count  = (await db._fetchone("SELECT COUNT(*) as c FROM chapters WHERE novel_id=?",            (NOVEL_ID,)) or {}).get('c', 0)
    growth_count= (await db._fetchone("SELECT COUNT(*) as c FROM growth_records WHERE novel_id=?",      (NOVEL_ID,)) or {}).get('c', 0)
    event_count = (await db._fetchone("SELECT COUNT(*) as c FROM growth_event_records WHERE novel_id=?",(NOVEL_ID,)) or {}).get('c', 0)
    medal_count = (await db._fetchone("SELECT COUNT(*) as c FROM medals WHERE novel_id=?",              (NOVEL_ID,)) or {}).get('c', 0)
    ach_count   = (await db._fetchone("SELECT COUNT(*) as c FROM achievements WHERE novel_id=?",        (NOVEL_ID,)) or {}).get('c', 0)
    exch_count  = (await db._fetchone("SELECT COUNT(*) as c FROM exchange_log WHERE novel_id=?",        (NOVEL_ID,)) or {}).get('c', 0)
    item_count  = (await db._fetchone("SELECT COUNT(*) as c FROM owned_items WHERE novel_id=?",         (NOVEL_ID,)) or {}).get('c', 0)

    print(f"  消息:            {msg_count}")
    print(f"  快照:            {snap_count}")
    print(f"  伏笔:            {hook_count}")
    print(f"  章节锚点:        {chap_count}")
    print(f"  成长记录:        {growth_count}")
    print(f"  成长事件记录:    {event_count}")
    print(f"  凭证(medals):    {medal_count}")
    print(f"  成就:            {ach_count}")
    print(f"  兑换日志:        {exch_count}")
    print(f"  拥有物品:        {item_count}")

    # ── 2. 清除正文数据 ─────────────────────────────────────────────
    await db._exec("DELETE FROM messages WHERE novel_id=?",              (NOVEL_ID,))
    print(f"  ✓ 消息已清空")
    await db._exec("DELETE FROM turn_snapshots WHERE novel_id=?",        (NOVEL_ID,))
    print(f"  ✓ 快照已清空")
    await db._exec("DELETE FROM narrative_hooks WHERE novel_id=?",       (NOVEL_ID,))
    print(f"  ✓ 伏笔已清空")
    await db._exec("DELETE FROM chapters WHERE novel_id=?",              (NOVEL_ID,))
    print(f"  ✓ 章节锚点已清空")
    await db._exec("DELETE FROM growth_records WHERE novel_id=?",        (NOVEL_ID,))
    print(f"  ✓ 成长记录已清空")
    await db._exec("DELETE FROM growth_event_records WHERE novel_id=?",  (NOVEL_ID,))
    print(f"  ✓ 成长事件记录已清空")
    await db._exec("DELETE FROM medals WHERE novel_id=?",                (NOVEL_ID,))
    print(f"  ✓ 凭证已清空")
    await db._exec("DELETE FROM achievements WHERE novel_id=?",          (NOVEL_ID,))
    print(f"  ✓ 成就已清空")
    await db._exec("DELETE FROM exchange_log WHERE novel_id=?",          (NOVEL_ID,))
    print(f"  ✓ 兑换日志已清空")
    await db._exec("DELETE FROM owned_items WHERE novel_id=?",           (NOVEL_ID,))
    print(f"  ✓ 拥有物品已清空（起始物品保留在档案，需重新初始化）")

    # ── 3. 重置主角积分/状态（保留档案，仅重置动态字段）──────────────
    await db._exec(
        "UPDATE protagonist_state SET "
        "  points=0, xp=0, tier=0, tier_sub='M', "
        "  status_effects='[]', active_buffs='[]', "
        "  updated_at=datetime('now') "
        "WHERE novel_id=?",
        (NOVEL_ID,)
    )
    print(f"  ✓ 主角积分/状态已重置（档案保留）")

    # ── 4. 清除记忆图谱中的对话节点（保留 CHARACTER 节点）────────────
    from memory.graph import graph_manager
    from memory.schema import NodeType

    graph = graph_manager.get(NOVEL_ID)
    to_remove = []
    preserved = []
    for nid, data in graph._G.nodes(data=True):
        nt = data.get('node_type', '')
        if nt == NodeType.CHARACTER.value:
            preserved.append(data.get('title', nid[:8]))
        else:
            to_remove.append(nid)

    removed = await graph_manager.remove_nodes(NOVEL_ID, to_remove)
    print(f"  ✓ 图谱清理: 删除 {removed} 个叙事节点，保留 {len(preserved)} 个角色节点")
    print(f"    保留节点: {', '.join(preserved)}")

    # ── 5. 清除向量数据库（对话向量）───────────────────────────────
    try:
        from memory.vector import vector_manager
        vm = await vector_manager.get_or_create(NOVEL_ID)
        deleted_vecs = 0
        for nt in ['event', 'rule', 'thread', 'location', 'reflection', 'pov_memory']:
            try:
                coll = vm._chroma_col
                results = coll.get(where={"node_type": nt})
                ids = results.get('ids', [])
                if ids:
                    coll.delete(ids=ids)
                    deleted_vecs += len(ids)
            except Exception:
                pass
        print(f"  ✓ 向量库清理: 删除 {deleted_vecs} 条向量")
    except Exception as e:
        print(f"  ⚠ 向量库清理跳过: {e}")

    # ── 6. 最终验证 ──────────────────────────────────────────────────
    final_msg = (await db._fetchone("SELECT COUNT(*) as c FROM messages WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    p = await db.get_protagonist_state(NOVEL_ID)
    npc_count = (await db._fetchone("SELECT COUNT(*) as c FROM npc_profiles WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    stats = graph_manager.get_stats(NOVEL_ID)

    print(f"\n[完成] 重置结果:")
    print(f"  消息残留: {final_msg}")
    print(f"  主角: {p['name'] if p else '无'} | 积分={p.get('points',0) if p else 0} | 层级={p.get('tier',0) if p else 0}")
    print(f"  NPC档案: {npc_count} 条（保留）")
    print(f"  图谱: 节点={stats.get('node_count','?')} 边={stats.get('edge_count','?')}")

if __name__ == '__main__':
    asyncio.run(main())
