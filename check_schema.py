import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine('postgresql+asyncpg://omii:omii0123@localhost:5432/sih2026')
    async with engine.connect() as conn:
        for tbl in ['worker_models', 'worker_nodes', 'worker_capabilities']:
            r = await conn.execute(text(
                f"SELECT column_name, data_type, column_default, is_nullable "
                f"FROM information_schema.columns "
                f"WHERE table_name='{tbl}' ORDER BY ordinal_position"
            ))
            rows = r.fetchall()
            print(f"\n{tbl}:")
            for c, d, dflt, nullable in rows:
                print(f"  {c}: {d}  default={dflt}  nullable={nullable}")

        # Check existing FK constraints
        r = await conn.execute(text("""
            SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name IN ('worker_models','worker_capabilities')
        """))
        print("\nFK Constraints:")
        for row in r.fetchall():
            print(f"  {row}")

        # Sample existing data
        r2 = await conn.execute(text("SELECT id, node_id, endpoint, status FROM worker_nodes LIMIT 5"))
        print("\nSample worker_nodes rows:", r2.fetchall())
        r3 = await conn.execute(text("SELECT id, worker_node_id, model_id FROM worker_models LIMIT 5"))
        print("Sample worker_models rows:", r3.fetchall())

    await engine.dispose()

asyncio.run(main())
