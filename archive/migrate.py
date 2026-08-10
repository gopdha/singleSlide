#!/usr/bin/env python3
"""
Applies schema.sql to whatever Postgres DATABASE_URL points at. Safe to re-run —
every statement in schema.sql is CREATE TABLE IF NOT EXISTS.

Usage:
    DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python3 migrate.py
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set. Export it and retry, e.g.:")
        print('  DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python3 migrate.py')
        sys.exit(1)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    print(f"Connecting to Postgres...")
    conn = await asyncpg.connect(database_url)
    try:
        print("Applying schema.sql (CREATE TABLE IF NOT EXISTS — safe to re-run)...")
        await conn.execute(schema_sql)

        tables = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('projects', 'preference_profiles', 'weekly_reports',
                                  'feature_snapshots', 'initiative_snapshots')
            ORDER BY table_name
            """
        )
        print(f"\nTables present after migration: {[t['table_name'] for t in tables]}")
        assert len(tables) == 5, f"Expected 5 tables, found {len(tables)} — migration may be incomplete."
        print("\nPASS  all 5 tables exist.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
