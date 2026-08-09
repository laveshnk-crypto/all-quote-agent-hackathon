import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# fallback db url with custom one
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/auto_quote_db"
    )

# intialize async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Session factory for handling async transactions

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# base class for sqlalchemy models to inherit form
class Base(DeclarativeBase):
    pass

# fastapi router dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()