from pydantic_settings import BaseSettings, SettingsConfigDict
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
    AUTH_URL: str = ""
    STOCK_API_URL: str = ""
    TOP_N_PERFORMANCE: int = 5
    
    model_config = SettingsConfigDict(
        env_file="app/core/.envs/.env.local", env_ignore_empty=True, extra="ignore"
    )
 
 
settings = Settings()