from .provider import MarketProvider
from .config import MarketConfig, TableLayout
from app.core.config import settings
from app.models.enums import InstrumentType

MARKETS = {
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
    "commodities": MarketConfig(
        id="commodities",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_COMMODITIES_QUOTE_URL,
        mic="STCM",  
        instrument_type=InstrumentType.COMMODITY, 
        layout=TableLayout(min_cols=6, volume_col=None, time_col=5),
    ),
    "cpi": MarketConfig(
        id="commodities",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_CPI_QUOTE_URL,
        mic="MCRO",  
        instrument_type=InstrumentType.MACRO, 
        layout=TableLayout(min_cols=5, volume_col=None, time_col=4),
    ),
    "pln_currency": MarketConfig(
        id="pln_currency",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_PLN_CURRENCY_QUOTE_URL,
        mic="PLNC",  
        instrument_type=InstrumentType.CURRENCY_PAIR,
        layout=TableLayout(min_cols=6, volume_col=None, time_col=5),
    ),
    "global_indexs": MarketConfig(
        id="global_indexs",
        base_url=settings.ST_BASE_URL,
        start_path=settings.ST_START_PLN_INDEXS_QUOTE_URL,
        mic="GLIX",
        instrument_type=InstrumentType.INDEX,
        layout=TableLayout(min_cols=6, volume_col=None, time_col=5),
    )
}

MARKET_INGEST_KEYS = tuple(MARKETS.keys())

PROVIDERS = {
    "market": MarketProvider(MARKETS),
}


def get_provider(provider_id: str):
    return PROVIDERS[provider_id]
