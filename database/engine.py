from sqlalchemy.ext.asyncio import create_async_engine

from config import DATABASE_URL

async_engine = create_async_engine(
    DATABASE_URL,
    #echo=True,        # лог SQL-запросов (на проде False)
    future=True
)


