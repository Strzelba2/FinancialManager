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
    ST_BASE_URL_ALT: str = ""
    ST_START_WSE_QUOTE_URL: str = ""
    ST_START_NC_QUOTE_URL: str = ""
    ST_START_COMMODITIES_QUOTE_URL: str = ""
    ST_START_CPI_QUOTE_URL: str = ""
    TIME_ZONE: ZoneInfo = ZoneInfo("Europe/Warsaw")
    GPW_BASE_URL: str = ""
    GPW_PATH: str = ""
    NC_BASE_URL: str = ""
    NC_PATH: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_REPORT_MODEL: str = "gpt-5.4"
    OPENAI_REPORT_TIMEOUT_S: float = 300.0
    OPENAI_REPORT_MAX_RETRIES: int = 0
    OPENAI_REPORT_MAX_OUTPUT_TOKENS: int = 12000
    OPENAI_REPORT_TEMPERATURE: float = 0.0
    OPENAI_REPORT_ENABLE_WEB_SEARCH: bool = True
    OPENAI_REPORT_WEB_SEARCH_MAX_TOOL_CALLS: int = 3
    OPENAI_REPORT_PROMPT_VERSION: str = "equity-v6"
    REPORT_SCHEMA_VERSION: int = 4
    EQUITY_WEB_SOURCE_ENABLED: bool = True
    EQUITY_WEB_SOURCE_BASE_URL: str = ""
    EQUITY_WEB_SOURCE_TIMEOUT_S: float = 20.0
    EQUITY_WEB_SOURCE_GPW_LISTING_PATH: str = "/gielda/akcje_gpw"
    EQUITY_WEB_SOURCE_NC_LISTING_PATH: str = "/gielda/newconnect"

    model_config = SettingsConfigDict(
        env_file="app/core/.envs/.env.local", env_ignore_empty=True, extra="ignore"
    )
 
 
settings = Settings()
