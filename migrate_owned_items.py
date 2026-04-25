"""迁移脚本：给 owned_items 表添加 description/is_equipped/can_unequip 列"""
import sqlite3, glob

dbs = glob.glob('backend/data/*.db') + glob.glob('backend/*.db') + glob.glob('data/*.db')
print('Found DBs:', dbs)

for db_path in dbs:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cols = [r[1] for r in cur.execute('PRAGMA table_info(owned_items)')]
    print(f'{db_path} columns: {cols}')
    migrations = [
        ('description', 'TEXT DEFAULT ""'),
        ('is_equipped',  'INTEGER DEFAULT 1'),
        ('can_unequip',  'INTEGER DEFAULT 1'),
    ]
    for col, defn in migrations:
        if col not in cols:
            cur.execute(f'ALTER TABLE owned_items ADD COLUMN {col} {defn}')
            print(f'  + Added column: {col}')
        else:
            print(f'  ~ Already exists: {col}')
    con.commit()
    con.close()

print('Migration complete.')
