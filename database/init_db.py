from sqlalchemy.ext.asyncio import AsyncEngine

from .engine import async_engine
from .base import Base
from .models import Person, Vision
  # ОБЯЗАТЕЛЬНО: чтобы модели зарегистрировались


async def init_db(engine: AsyncEngine = async_engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)