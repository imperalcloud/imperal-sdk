# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Any


class DBClient:
    """Tier 2: Dedicated schema access."""

    def __init__(self, connection_factory):
        self._factory = connection_factory

    @asynccontextmanager
    async def acquire(self):
        conn = await self._factory.acquire()
        try:
            yield conn
        finally:
            await self._factory.release(conn)

    @asynccontextmanager
    async def session(self):
        session = await self._factory.create_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def raw(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        async with self.acquire() as conn:
            return await conn.execute(query, params)
