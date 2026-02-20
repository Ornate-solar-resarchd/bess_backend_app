from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def atomic(session: AsyncSession, serializable: bool = False):
    depth = int(session.info.get("_atomic_depth", 0))
    session.info["_atomic_depth"] = depth + 1
    owns_boundary = depth == 0

    try:
        if not owns_boundary:
            # Nested atomic() call: outer context controls commit/rollback.
            yield session
            return

        if session.in_transaction():
            # Transaction already started (commonly by prior read due autobegin).
            # Reuse it and close it at the boundary of this atomic block.
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()
            return

        async with session.begin():
            if serializable:
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    finally:
        new_depth = int(session.info.get("_atomic_depth", 1)) - 1
        if new_depth <= 0:
            session.info.pop("_atomic_depth", None)
        else:
            session.info["_atomic_depth"] = new_depth
