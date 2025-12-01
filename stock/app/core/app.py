from fastapi import FastAPI
import logging

from .cache.redis import Storage

logger = logging.getLogger(__name__)


class App(FastAPI):
    """Application class extending FastAPI with a shared Storage instance."""
    def __init__(self, **kwargs) -> None:
        """
        Initialize the application.

        Args:
            **kwargs: Keyword arguments forwarded to the FastAPI constructor.
        """
        logger.info("Initializing App instance")
        super().__init__(**kwargs)
        self.storage = Storage()
        logger.debug("Storage instance created and attached to App")
        
    async def startup(self):
        """
        Initialize resources on application startup.

        This method is intended to be registered as a FastAPI startup event
        handler and is responsible for initializing the shared Storage.
        """
        logger.info("App startup: initializing storage")
        await self.storage.initialize()
        logger.info("App startup: storage initialized successfully")
        
    async def shutdown(self):
        """
        Clean up resources on application shutdown.

        This method is intended to be registered as a FastAPI shutdown event
        handler and is responsible for gracefully shutting down the Storage.
        """
        logger.info("App shutdown: shutting down storage")
        await self.storage.shutdown()
        logger.info("App shutdown: storage shutdown completed")