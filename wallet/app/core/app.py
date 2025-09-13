from fastapi import FastAPI

from .cache.redis import Storage


class App(FastAPI):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs, docs_url=None, redoc_url=None)
        self.storage = Storage()
        
    async def startup(self):
        await self.storage.initialize()
        
    async def shutdown(self):
        await self.storage.shutdown()