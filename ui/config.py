from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    ENVIRONMENT: Literal["local", "production"] = "local"
    
    NICEGUI_REDIS_URL: str = ""
    SECRET_KEY: str = ""
    WALLET_API_URL: str = ""
        
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )
 
 
settings = Settings()