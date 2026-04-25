import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))

async def main():
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance
    s = get_settings()
    await init_db(str(s.db_path_resolved))
    db = await init_db_instance(str(s.db_path_resolved))
    rows = await db._fetchall("SELECT novel_id, title FROM novels ORDER BY created_at DESC LIMIT 10")
    for r in rows:
        nid = r["novel_id"]
        title = r["title"]
        msg_c = (await db._fetchone("SELECT COUNT(*) as c FROM messages WHERE novel_id=?", (nid,)) or {}).get("c", 0)
        print(f"{nid} | {title} | messages={msg_c}")

asyncio.run(main())
