from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://bb_user:bb_pass@localhost:5432/breaking_bad_game"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    from database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed forum categories
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from database.models import ForumCategory
        result = await session.execute(select(ForumCategory))
        if not result.scalars().first():
            cats = [
                ForumCategory(name="Рынок", slug="market", description="Купля-продажа товаров", icon="💊", order=1),
                ForumCategory(name="Кланы", slug="clans", description="Объявления кланов", icon="🤝", order=2),
                ForumCategory(name="Объявления", slug="ads", description="Общие объявления", icon="📢", order=3),
                ForumCategory(name="Разыскиваются", slug="wanted", description="Охота на игроков", icon="🔫", order=4),
                ForumCategory(name="Общение", slug="general", description="Флуд и разговоры", icon="💬", order=5),
            ]
            session.add_all(cats)
            await session.commit()
