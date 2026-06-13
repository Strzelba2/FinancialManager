from enum import Enum


class Currency(str, Enum):
    PLN = "PLN"
    USD = "USD"
    EUR = "EUR"


class InstrumentCurrency(str, Enum):
    """Quote/trade currency of an instrument or brokerage event.

    Superset of the base reporting ``Currency`` (PLN/USD/EUR). Instruments may be
    quoted in additional currencies (e.g. CHF, GBP); positions are tracked in this
    currency and converted to a base reporting currency via FX. Cash settlement and
    capital gains stay in the base ``Currency``.
    """
    PLN = "PLN"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CHF = "CHF"


class AccountType(str, Enum):
    CURRENT = "CURRENT"  
    SAVINGS = "SAVINGS" 
    BROKERAGE = "BROKERAGE"
    CREDIT = "CREDIT"
    

class BrokerageEventKind(str, Enum):
    TRADE_BUY = "BUY"
    TRADE_SELL = "SELL"
    SPLIT = "SPLIT"
    DIV = "DIV"
    ADJUSTMENT = "ADJUSTMENT"
    CONVERSION = "CONVERSION"
    

class CapitalGainKind(str, Enum):
    DEPOSIT_INTEREST = "DEPOSIT_INTEREST"  
    BROKER_REALIZED_PNL = "BROKER_REALIZED_PNL"
    BROKER_DIVIDEND = "BROKER_DIVIDEND"  
    METAL_REALIZED_PNL = "METAL_REALIZED_PNL"
    REAL_ESTATE_REALIZED_PNL = "REAL_ESTATE_REALIZED_PNL"
       

class TaxWrapper(str, Enum):
    NONE = "NONE"
    IKE = "IKE"
    IKZE = "IKZE"


class InstrumentType(str, Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    BOND = "BOND"
    FUND = "FUND"
    CRYPTO = "CRYPTO"
    
    
class PropertyType(str, Enum):
    APARTMENT = "APARTMENT",
    LAND = "LAND",
    HAUSE = "HAUSE"
  
    
class MetalType(str, Enum):
    GOLD = "GOLD"
    SILVER = "SILVER"
    PLATINUM = "PLATINUM"
    PALLADIUM = "PALLADIUM"
