from enum import Enum


class Currency(str, Enum):
    PLN = "PLN"
    USD = "USD" 
    EUR = "EUR"
   
    
class AccountType(str, Enum):
    CURRENT = "CURRENT"  
    SAVINGS = "SAVINGS" 
       

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
  
    
class TransactionType(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"

    
class PropertyType(str, Enum):
    APARTMENT = "APARTMENT",
    LAND = "LAND",
    HAUSE = "HAUSE"
  
    
class MetalType(str, Enum):
    GOLD = "GOLD"
    SILVER = "SILVER"
    PLATINUM = "PLATINUM"
    PALLADIUM = "PALLADIUM"
