import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
c = sqlite3.connect('./data/novel_system.db')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print("Tables:", tables)
c.close()
