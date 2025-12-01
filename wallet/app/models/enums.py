from enum import Enum


class Currency(str, Enum):
    PLN = "PLN"
    USD = "USD" 
    EUR = "EUR"
   
    
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
    

class CapitalGainKind(str, Enum):
    DEPOSIT_INTEREST = "DEPOSIT_INTEREST"  
    BROKER_REALIZED_PNL = "BROKER_REALIZED_PNL"
    BROKER_DIVIDEND = "BROKER_DIVIDEND"  
       

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
