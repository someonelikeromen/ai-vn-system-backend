import sqlite3, os, json

db = './data/novel_system.db'
if not os.path.exists(db):
    print('NO_DB')
else:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    novels = conn.execute('SELECT novel_id, title FROM novels WHERE archived=0 ORDER BY created_at DESC LIMIT 5').fetchall()
    for n in novels:
        print(f'NOVEL: {n["novel_id"]} | {n["title"]}')
    if not novels:
        print('NO_NOVELS')
    p = conn.execute('SELECT novel_id, name FROM protagonist_state ORDER BY updated_at DESC LIMIT 3').fetchall()
    for row in p:
        print(f'PROTAGONIST: {row["novel_id"]} | {row["name"]}')
    conn.close()
