import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
c = sqlite3.connect('./data/novel_system.db')
cols = [r[1] for r in c.execute("PRAGMA table_info(protagonist_state)").fetchall()]
print("protagonist_state columns:", cols)
# 当前值
row = c.execute("SELECT * FROM protagonist_state LIMIT 1").fetchone()
if row:
    desc = c.execute("PRAGMA table_info(protagonist_state)").fetchall()
    for d, v in zip(desc, row):
        print(f"  {d[1]}: {str(v)[:60]}")
c.close()
