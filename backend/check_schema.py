import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance
    s = get_settings()
    await init_db(str(s.db_path_resolved))
    db = await init_db_instance(str(s.db_path_resolved))
    rows = await db._fetchall("PRAGMA table_info(protagonist_state)")
    for r in rows:
        print(dict(r))

asyncio.run(main())
