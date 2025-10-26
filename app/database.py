import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

from config import DATABASE_URL, DB_ECHO, LOG_LEVEL
import logging
from models import Base

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
                
logger = logging.getLogger(__name__)
logger.info(__name__)

engine = create_async_engine(
    DATABASE_URL,
    echo=DB_ECHO,  
    poolclass=StaticPool,
    pool_pre_ping=True,          
    pool_recycle=3600,           
    connect_args={
        "check_same_thread": False,
        "timeout": 30,           
        "isolation_level": None, 
    }
)

async_sessionmaker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True
)

async def create_db():
    """Создание всех таблиц в базе данных с критическими оптимизациями SQLite"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            await conn.execute(text("PRAGMA journal_mode=WAL"))           
            await conn.execute(text("PRAGMA synchronous=NORMAL"))         
            await conn.execute(text("PRAGMA cache_size=100000"))          
            await conn.execute(text("PRAGMA temp_store=MEMORY"))          
            await conn.execute(text("PRAGMA mmap_size=268435456"))        
            await conn.execute(text("PRAGMA page_size=4096"))             
            await conn.execute(text("PRAGMA busy_timeout=30000"))         
            await conn.execute(text("PRAGMA wal_autocheckpoint=1000"))    
            await conn.execute(text("PRAGMA optimize"))                   
            
        logger.info("База данных успешно инициализирована с оптимизациями для мгновенных записей")
    except Exception as e:
        logger.error(f"Ошибка создания базы данных: {e}")
        raise

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Получение оптимизированной асинхронной сессии базы данных"""
    async with async_sessionmaker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка сессии БД: {e}")
            raise
        finally:
            await session.close()

async def drop_db():
    """Удаление всех таблиц (для тестирования)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("База данных очищена")

async def reset_db():
    """Пересоздание базы данных"""
    await drop_db()
    await create_db()
    logger.warning("База данных пересоздана")

if __name__ == "__main__":
    async def test_connection():
        try:
            await create_db()
            print("Тест подключения к БД прошел успешно")
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
    
    asyncio.run(test_connection())