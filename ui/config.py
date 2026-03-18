from pydantic_settings import BaseSettings, SettingsConfigDict
import os
# from typing import Literal

ENVIRONMENT = os.getenv("ENV_TYPE", "local")


class Settings(BaseSettings):
    # ENVIRONMENT: Literal["local", "production"] = "local"
    
    NICEGUI_REDIS_URL: str = ""
    SECRET_KEY: str = ""
    WALLET_API_URL: str = ""
    STOCK_API_URL: str = ""
    UI_API_URL: str = ""
    CELERY_STOCK_WORKER: bool = False
    AUTH_URL: str = ""
        
    model_config = SettingsConfigDict(
        env_file=None if ENVIRONMENT == "prod" else ".env",
        env_ignore_empty=True,
        extra="ignore",
    )
 

settings = Settings()