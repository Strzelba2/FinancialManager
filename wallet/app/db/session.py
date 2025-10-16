from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
import asyncio
from typing import AsyncGenerator
import logging

from app.core.config import settings 

logger = logging.getLogger(__name__)


class Database:
    """
    Asynchronous database handler using SQLAlchemy and connection pooling.
    Provides session management and initialization with retry logic.
    """
    def __init__(self):
        """
        Initialize the async SQLAlchemy engine and session factory.
        """
        logger.info("Initializing database engine")
        self.engine: AsyncEngine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=AsyncAdaptedQueuePool,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
        )
        self.async_session = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide a context-managed async session for database operations.

        Yields:
            AsyncSession: The active SQLAlchemy session.
        """
        async with self.async_session() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.warning(f"Database session rollback due to exception: {e}")
                raise

    async def init_db(self):
        """
        Attempt to verify the database connection with retries.

        Raises:
            Exception: If all connection attempts fail.
        """
        try:
            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    async with self.engine.begin() as conn:
                        await conn.execute(text("SELECT 1"))
                    logger.info("Database connection verified successfully")
                    break
                except Exception:
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to verify database connection after {max_retries} attempts"
                        )
                        raise
                    logger.warning(f"Database connection attempt {attempt + 1}")

                    await asyncio.sleep(retry_delay * (attempt + 1))

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise


db = Database()
