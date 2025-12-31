from .provider import MarketProvider
from .config import MarketConfig, TableLayout
from app.core.config import settings
from app.models.enums import InstrumentType

STOOQ_MARKETS = {
    "pl-wse": MarketConfig(
        id="pl-wse",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_WSE_QUOTE_URL,
        mic="XWAR",
        instrument_type=InstrumentType.STOCK,
        layout=TableLayout(min_cols=7, volume_col=5, time_col=6),
    ),
    "pl-newconnect": MarketConfig(
        id="pl-newconnect",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_NC_QUOTE_URL,
        mic="XNCO",
        instrument_type=InstrumentType.STOCK,
        layout=TableLayout(min_cols=7, volume_col=5, time_col=6),
    ),
    "stooq-commodities": MarketConfig(
        id="stooq-commodities",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_COMMODITIES_QUOTE_URL,
        mic="STCM",  
        instrument_type=InstrumentType.COMMODITY, 
        layout=TableLayout(min_cols=6, volume_col=None, time_col=5),
    ),
}

PROVIDERS = {
    "market": MarketProvider(STOOQ_MARKETS),
}


def get_provider(provider_id: str):
    return PROVIDERS[provider_id]
