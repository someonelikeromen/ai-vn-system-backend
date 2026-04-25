"""
finish_reset.py — 完成主角状态重置 + 记忆图谱清理
"""
import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

NOVEL_ID = sys.argv[1] if len(sys.argv) > 1 else "12c5ac18-2005-491c-b0da-1ec827bff09b"

async def main():
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance

    s = get_settings()
    await init_db(str(s.db_path_resolved))
    db = await init_db_instance(str(s.db_path_resolved))

    # 重置主角动态字段（只用实际存在的列）
    await db._exec(
        "UPDATE protagonist_state SET "
        "  points=0, tier=0, tier_sub='M', "
        "  status_effects='[]', "
        "  energy_pools='{}', "
        "  updated_at=datetime('now') "
        "WHERE novel_id=?",
        (NOVEL_ID,)
    )
    print("  ✓ 主角积分/状态已重置（档案保留）")

    # 清除记忆图谱中的非 CHARACTER 节点
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
    if preserved:
        print(f"    保留节点: {', '.join(preserved)}")

    # 清除向量数据库
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

    # 最终验证
    final_msg = (await db._fetchone("SELECT COUNT(*) as c FROM messages WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    p = await db.get_protagonist_state(NOVEL_ID)
    npc_count = (await db._fetchone("SELECT COUNT(*) as c FROM npc_profiles WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    stats = graph_manager.get_stats(NOVEL_ID)

    print(f"\n[完成] 重置结果:")
    print(f"  消息残留: {final_msg}")
    print(f"  主角: {p['name'] if p else '无'} | 积分={p.get('points',0) if p else 0} | 层级={p.get('tier',0) if p else 0}")
    print(f"  NPC档案: {npc_count} 条（保留）")
    print(f"  图谱: 节点={stats.get('node_count','?')} 边={stats.get('edge_count','?')}")

asyncio.run(main())
