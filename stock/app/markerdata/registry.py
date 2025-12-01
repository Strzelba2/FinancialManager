from .provider import MarketProvider
from .config import MarketConfig
from app.core.config import settings
from app.models.enums import InstrumentType

STOOQ_MARKETS = {
    "pl-wse": MarketConfig(
        id="pl-wse",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_WSE_QUOTE_URL,
        mic="XWAR",
        instrument_type=InstrumentType.STOCK,
    ),
    "pl-newconnect": MarketConfig(
        id="pl-newconnect",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_NC_QUOTE_URL,
        mic="XNCO",
        instrument_type=InstrumentType.STOCK,
    ),
}

PROVIDERS = {
    "market": MarketProvider(STOOQ_MARKETS),
}


def get_provider(provider_id: str):
    return PROVIDERS[provider_id]
