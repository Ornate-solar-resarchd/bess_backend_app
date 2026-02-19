from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.shared.base_model import Base


async_engine = create_async_engine(settings.database_url, echo=settings.sql_echo, future=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    if not settings.auto_create_tables:
        return
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
