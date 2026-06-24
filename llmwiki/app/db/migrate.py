"""Tiny SQL migration runner for environments that do not use Alembic yet.

Usage:
  python -m app.db.migrate

Migrations live in app/db/migrations/*.sql and are recorded in schema_migrations.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from app.core.config import get_settings


async def apply_migrations(dsn: str | None = None) -> list[str]:
    settings = get_settings()
    con = await asyncpg.connect(dsn or settings.pg_dsn)
    applied: list[str] = []
    try:
        await con.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        root = Path(__file__).with_name("migrations")
        for path in sorted(root.glob("*.sql")):
            version = path.name
            exists = await con.fetchval("SELECT 1 FROM schema_migrations WHERE version=$1", version)
            if exists:
                continue
            async with con.transaction():
                await con.execute(path.read_text(encoding="utf-8"))
                await con.execute("INSERT INTO schema_migrations(version) VALUES ($1)", version)
            applied.append(version)
        return applied
    finally:
        await con.close()


if __name__ == "__main__":
    done = asyncio.run(apply_migrations())
    print("applied migrations:", ", ".join(done) if done else "none")
