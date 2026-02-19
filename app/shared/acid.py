from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def atomic(session: AsyncSession, serializable: bool = False):
    async with session.begin():
        if serializable:
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
