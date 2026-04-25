import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
c = sqlite3.connect('./data/novel_system.db')

NOVEL_ID = "d7830720-bb9a-41d3-9009-f38133d564c1"

# 重置主角动态状态（清除已有的系统觉醒状态效果，回到觉醒前状态）
c.execute(
    "UPDATE protagonist_state SET points=0, tier=0, tier_sub='M', "
    "status_effects='[]', updated_at=datetime('now') WHERE novel_id=?",
    (NOVEL_ID,)
)
print("✓ 主角状态已重置（积分0，层级0，状态效果清空）")

# 重置 energy_pools current 恢复到 max
row = c.execute("SELECT energy_pools FROM protagonist_state WHERE novel_id=?", (NOVEL_ID,)).fetchone()
if row:
    pools = json.loads(row[0])
    for k, v in pools.items():
        if isinstance(v, dict) and 'max' in v:
            v['current'] = v['max']
    c.execute("UPDATE protagonist_state SET energy_pools=? WHERE novel_id=?",
              (json.dumps(pools, ensure_ascii=False), NOVEL_ID))
    print("✓ 能量池已满载恢复")

c.commit()

# 验证
p = c.execute("SELECT name, points, tier, tier_sub, status_effects FROM protagonist_state WHERE novel_id=?",
              (NOVEL_ID,)).fetchone()
print(f"\n[验证] 主角: {p[0]} | 积分={p[1]} | 层级={p[2]}{p[3]} | 状态效果={p[4]}")

msg_count = c.execute("SELECT COUNT(*) FROM messages WHERE novel_id=?", (NOVEL_ID,)).fetchone()[0]
hook_count = c.execute("SELECT COUNT(*) FROM narrative_hooks WHERE novel_id=?", (NOVEL_ID,)).fetchone()[0]
npc_count = c.execute("SELECT COUNT(*) FROM npc_profiles WHERE novel_id=?", (NOVEL_ID,)).fetchone()[0]
print(f"  消息: {msg_count} | 伏笔: {hook_count} | NPC档案: {npc_count}")

c.close()
print("\n✅ 重置完成，可以开始生成开局了")
