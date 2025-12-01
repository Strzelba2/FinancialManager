from enum import Enum


class Currency(str, Enum):
    PLN = "PLN"
    USD = "USD" 
    EUR = "EUR"
    
    
class InstrumentType(str, Enum):
    ETF = "ETF"  
    STOCK = "STOCK" 
    BOND = "BOND"
    CURRENCY_PAIR = "CURRENCY_PAIR"
    CRYPTO_ASSET = "CRYPTO_ASSET"
    INDEX = "INDEX"
    REIT = "REIT"
 
  
class InstrumentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
