"""迁移脚本：给 protagonist_state 表添加角色档案字段"""
import sqlite3, glob

NEW_COLS = [
    ("gender",      "TEXT DEFAULT ''"),
    ("age",         "TEXT DEFAULT ''"),
    ("identity",    "TEXT DEFAULT ''"),
    ("height",      "TEXT DEFAULT ''"),
    ("weight",      "TEXT DEFAULT ''"),
    ("alignment",   "TEXT DEFAULT ''"),
    ("appearance",  "TEXT DEFAULT ''"),
    ("clothing",    "TEXT DEFAULT ''"),
    ("background",  "TEXT DEFAULT ''"),
    ("personality", "JSON DEFAULT '[]'"),
    ("flaws",       "JSON DEFAULT '[]'"),
    ("desires",     "JSON DEFAULT '[]'"),
    ("fears",       "JSON DEFAULT '[]'"),
    ("quirks",      "JSON DEFAULT '[]'"),
    ("traits",      "JSON DEFAULT '[]'"),
]

dbs = glob.glob('backend/data/*.db') + glob.glob('backend/*.db') + glob.glob('data/*.db')
print('Found DBs:', dbs)

for db_path in dbs:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    existing = [r[1] for r in cur.execute('PRAGMA table_info(protagonist_state)')]
    print(f'\n{db_path} existing cols: {existing}')
    for col, defn in NEW_COLS:
        if col not in existing:
            cur.execute(f'ALTER TABLE protagonist_state ADD COLUMN {col} {defn}')
            print(f'  + Added: {col}')
        else:
            print(f'  ~ Skip:  {col}')
    con.commit()
    con.close()

print('\nMigration complete.')
