from .csv.parser import (
    BaseBankParser, MBankParser, 
    IngBankParser, SaxoBankParser, 
    BossaBankParser, IngMaklerBankParser
)
from .pdf.parser import VeloParser

PARSERS: list[BaseBankParser] = [
    MBankParser(), IngBankParser(), 
    SaxoBankParser(), BossaBankParser(), 
    VeloParser(), IngMaklerBankParser()
]
