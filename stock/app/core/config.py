from pydantic_settings import BaseSettings, SettingsConfigDict
from zoneinfo import ZoneInfo
from typing import Literal


class Settings(BaseSettings):
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    
    PROJECT_NAME: str = ""
    PROJECT_DESCRIPTION: str = ""
    SITE_NAME: str = ""
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    ST_BASE_URL: str = ""
    ST_START_WSE_QUOTE_URL: str = ""
    ST_START_NC_QUOTE_URL: str = ""
    TIME_ZONE: ZoneInfo = ZoneInfo("Europe/Warsaw")
    GPW_BASE_URL: str = ""
    GPW_PATH: str = ""
    NC_BASE_URL: str = ""
    NC_PATH: str = ""
    
    model_config = SettingsConfigDict(
        env_file="app/core/.envs/.env.local", env_ignore_empty=True, extra="ignore"
    )
 
 
settings = Settings()