import sqlite3, os

db_path = './data/novel_system.db'
if not os.path.exists(db_path):
    print('DB not found, will be created fresh on next startup')
else:
    conn = sqlite3.connect(db_path)
    migrations = [
        ("medals_json", "ALTER TABLE turn_snapshots ADD COLUMN medals_json TEXT NOT NULL DEFAULT '[]'"),
        ("growth_json", "ALTER TABLE turn_snapshots ADD COLUMN growth_json TEXT NOT NULL DEFAULT '[]'"),
    ]
    for name, sql in migrations:
        try:
            conn.execute(sql)
            print(f'Added column: {name}')
        except Exception as e:
            print(f'{name}: {e}')
    conn.commit()
    conn.close()
    print('Migration complete')
