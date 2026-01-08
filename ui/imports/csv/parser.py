import io
import re
import csv
from typing import Iterable, Tuple
from schemas.wallet import (
    TransactionCreationRow, CapitalGainKind, BrokerageEventImportRow, BrokerageEventKind,
    Currency
    )
from utils.money import dec, parse_amount, dec2
from utils.utils import read_bytes, parse_date
from clients.stock_client import StockClient
from exceptions import MissingRequiredColumnsError
import logging

logger = logging.getLogger(__name__)


class BaseBankParser:
    """
    Base parser for generic Polish bank CSVs.

    Designed to:
    - Normalize encoding from uploaded files (PL banks often use non-UTF encodings).
    - Automatically locate the header row using common variants (e.g., "Data księgowania").
    - Guess the delimiter (comma, semicolon, or tab).
    - Convert rows into `TransactionCreationRow` objects.

    Extend this class for bank-specific formats.
    """
    name = 'Generic CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    supports_brokerage_events: bool = False
    
    def __init__(self):
        self.header_variants = [
            r'Data\s+transakcji',
            r'Data\s+operacji',
            r'Data\s+ksi(?:ę|e)gowania',
            r'ID\s+klienta',
        ]
        self.header_start_pattern = re.compile(
            r'^\s*#?\s*(?:' + r'|'.join(self.header_variants) + r')\b',
            re.IGNORECASE,
        )

    def sniff(self, header: list[str]) -> bool:
        """
        Naively determine if a header line looks like a valid transaction file.

        Args:
            header: List of header strings.

        Returns:
            True if it contains basic expected fields.
        """
        return set(h.lower() for h in header).issuperset({'date', 'amount'})

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Convert CSV rows into structured transaction rows.

        Args:
            rows: Dict rows from a CSV DictReader.

        Returns:
            List of TransactionCreationRow instances.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            desc = r.get('description') or r.get('title') or r.get('details') or ''
            parsed.append(TransactionCreationRow(
                date=r.get('date') or r.get('booking date') or r.get('transaction_date') or '',
                amount=dec(r.get('amount', '0')),
                description=desc,
            ))
        return parsed
    
    def decode_bytes_pl(self, upload_content) -> str:
        """
        Decode uploaded file content using common Polish encodings.

        Args:
            upload_content: NiceGUI Upload content or file-like.

        Returns:
            UTF-8 decoded string.
        """
        b = read_bytes(upload_content)
        for enc in ('utf-8-sig', 'utf-8', 'cp1250', 'windows-1250',
                    'iso-8859-2', 'latin2', 'latin-1'):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode('utf-8', errors='replace')
    
    def find_table_start(self, lines: list[str]) -> int:
        """
        Detect the line index where the CSV table begins.

        Args:
            lines: List of text lines.

        Returns:
            Index of the header row.

        Raises:
            ValueError if no header line found.
        """
        for i, ln in enumerate(lines):
            if self.header_start_pattern.search(ln):
                return i

        logger.error("No recognizable header found")
        raise ValueError('Can not find header in table')
    
    def guess_delimiter(self, header_line: str) -> str:
        """
        Guess the CSV delimiter used in a given line.

        Args:
            header_line: Raw header string.

        Returns:
            Detected delimiter: ',', ';', or '\\t'
        """
        s = header_line.replace('\u00A0', ' ')

        if '\t' in s:
            return '\t'

        counts = {';': s.count(';'), ',': s.count(',')}
        if counts[';'] == counts[','] == 0:
            return ',' 

        return ';' if counts[';'] >= counts[','] else ','
    
    def open_mb_dictreader_from_bytes(self, b: bytes) -> Tuple[csv.DictReader, list[str]]:
        """
        Prepare a CSV DictReader starting from the detected table.

        Args:
            b: Raw bytes from an uploaded file.

        Returns:
            Tuple of (csv.DictReader, header_fields)

        Raises:
            ValueError if the file has no usable header or rows.
        """
        text = self.decode_bytes_pl(b)
        lines = text.splitlines()

        start = self.find_table_start(lines)
        header_line = lines[start]
        delim = self.guess_delimiter(header_line)

        src = io.StringIO('\n'.join(lines[start:]))
        row_reader = csv.reader(src, delimiter=delim, quotechar='"', skipinitialspace=True)

        raw_header = next(row_reader, None)
        if not raw_header:
            raise ValueError('Pusty nagłówek CSV.')

        fieldnames = [h.lstrip('#').strip() for h in raw_header]

        data_stream = io.StringIO('\n'.join(lines[start+1:]))
        dict_reader = csv.DictReader(
            data_stream,
            fieldnames=fieldnames,
            delimiter=delim,
            quotechar='"',
            skipinitialspace=True,
        )
        return dict_reader, fieldnames


class MBankParser(BaseBankParser):
    """
    Parser for mBank CSV statements.

    Expected columns include:
        - "Data księgowania"
        - "Kwota"
        - "Saldo po operacji"
        - "Opis operacji"
        - "Tytuł"

    Example row:
        {
            "Data księgowania": "2024-10-05",
            "Kwota": "123.45",
            "Saldo po operacji": "1500.00",
            "Opis operacji": "Przelew zewnętrzny",
            "Tytuł": "Zakupy online"
        }
    """
    name = 'mBank CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    def __init__(self):
        super().__init__()

    def sniff(self, header: list[str]) -> bool:
        """
        Determine if this parser is appropriate for the given CSV header.
        """
        hdr = [h.strip().lower() for h in header]
        return {'data operacji', 'kwota'} <= set(hdr)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Parse mBank CSV rows into TransactionCreationRow instances.

        Args:
            rows: Iterable of CSV dict rows.

        Returns:
            A list of TransactionCreationRow objects.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            date = parse_date(r.get("Data księgowania"))
            if not date:
                continue
            amount = dec(parse_amount(r.get('Kwota', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po operacji', '0')))
            desc = ' '.join([r.get('Opis operacji'), r.get('Tytuł')])

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after
            ))
        return parsed
    
    
class IngBankParser(BaseBankParser):
    """
    Parser for ING Bank CSV statements.

    Expected columns include:
        - "Data księgowania"
        - "Kwota transakcji (waluta rachunku)"
        - "Saldo po transakcji"
        - "Dane kontrahenta"
        - "Tytuł"
    """
    name = 'IngBank CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    def __init__(self):
        super().__init__()

    def sniff(self, header: list[str]) -> bool:
        """
        Determine if this parser is appropriate for the given CSV header.
        """
        hdr = [h.strip().lower() for h in header]
        return {'data operacji', 'kwota'} <= set(hdr)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Parse ING Bank CSV rows into TransactionCreationRow instances.

        Args:
            rows: Iterable of CSV dict rows.

        Returns:
            A list of TransactionCreationRow objects.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            date = parse_date(r.get("Data księgowania"))
            if not date:
                continue
            amount = dec(parse_amount(r.get('Kwota transakcji (waluta rachunku)', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po transakcji', '0')))
            desc = ' '.join([r.get('Dane kontrahenta'), r.get('Tytuł')])
            
            cg_kind = None
            if 'odsetki' in desc.lower():
                cg_kind = CapitalGainKind.DEPOSIT_INTEREST.name

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after,
                capital_gain_kind=cg_kind,
            ))
        return parsed
   
    
class SaxoBankParser(BaseBankParser):
    """
    Parser for Saxo Bank CSV statements.

    Expected columns:
        - "Data transakcji"
        - "Zablokowana kwota"
        - "Saldo po operacji"
        - "Rodzaj"
        - "Instrument"
        - "Zdarzenie"

    Raises:
        MissingRequiredColumnsError:
            If required columns (e.g., 'Saldo po operacji') are missing.
    """
    name = 'SaxoMakler CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'

    def __init__(self):
        super().__init__()

    def sniff(self, header: list[str]) -> bool:
        """
        Determine if this parser is appropriate for the given CSV header.
        """
        hdr = [h.strip().lower() for h in header]
        return {'data operacji', 'kwota'} <= set(hdr)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Parse Saxo Bank CSV rows into TransactionCreationRow instances.

        Args:
            rows: Iterable of CSV dict rows.

        Returns:
            A list of TransactionCreationRow objects.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            if "Saldo po operacji" not in r.keys():
                raise MissingRequiredColumnsError("Proszę dodać kolumnę: Saldo po operacji, z poprawnym saldem")
            date = parse_date(r.get("Data transakcji"))
            if not date:
                continue
            amount = dec(parse_amount(r.get('Zablokowana kwota', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po operacji', '0')))
            desc = ' '.join([r.get('Rodzaj'), ":",  r.get('Instrument'), "-",  r.get('Zdarzenie')])
            
            cg_kind = None
            if "Dywidenda" in r.get('Zdarzenie'):
                cg_kind = CapitalGainKind.BROKER_DIVIDEND.name

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after,
                capital_gain_kind=cg_kind,
            ))
        return parsed
  
    
class BossaBankParser(BaseBankParser):
    """
    Parser for BOSSA Bank CSV statements.

    Expected columns:
        - "data"
        - "kwota"
        - "Saldo po operacji"
        - "tytuł operacji"
        - "szczegóły"

    Raises:
        MissingRequiredColumnsError:
            If required columns (e.g., 'Saldo po operacji') are missing.
    """
    name = 'BossaMakler CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    supports_brokerage_events = True
    
    def __init__(self):
        super().__init__()
        self.header_variants = [
            r'data'
        ]
        
        self.header_start_pattern = re.compile(
            r'^\s*#?\s*(?:' + r'|'.join(self.header_variants) + r')\b',
            re.IGNORECASE,
        )

    def sniff(self, header: list[str]) -> bool:
        """
        Determine if this parser is appropriate for the given CSV header.
        """
        hdr = [h.strip().lower() for h in header]
        return {'data operacji', 'kwota'} <= set(hdr)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Parse BOSSA CSV rows into TransactionCreationRow instances.

        Args:
            rows: Iterable of CSV dict rows.

        Returns:
            A list of TransactionCreationRow objects.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            if "Saldo po operacji" not in r.keys():
                raise MissingRequiredColumnsError("Proszę dodać kolumnę: Saldo po operacji, z poprawnym saldem")
            date = parse_date(r.get("data"))
            if not date:
                continue
            amount = dec(parse_amount(r.get('kwota', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po operacji', '0')))
            desc = ' '.join([r.get('tytuł operacji'),  r.get('szczegóły')])
            
            cg_kind = None
            if "dywidendy" in r.get('tytuł operacji'):
                cg_kind = CapitalGainKind.BROKER_DIVIDEND.name

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after,
                capital_gain_kind=cg_kind,
            ))
        return parsed
    
    async def parse_brokerage_events(
        self,
        rows: Iterable[dict[str, str]],
        stock_client: "StockClient",
    ) -> list[BrokerageEventImportRow]:
        """
        Parse raw brokerage operation rows into normalized `BrokerageEventImportRow` objects.

        Expected input format (per row, dict with Polish keys):
            - "data": string date (parsed by `parse_date`)
            - "tytuł operacji": text describing operation, used to detect BUY/SELL
            - "szczegóły": details, from which shortname, quantity and currency are extracted
            - "kwota": operation amount as string

        Logic:
            - Skip rows with invalid/absent date.
            - Recognize only BUY/SELL (based on "kupna"/"sprzedaży" in "tytuł operacji").
            - Extract:
                * shortname, quantity, currency from "szczegóły".
                * amount from "kwota".
            - Resolve instrument using `stock_client.search_instrument_by_shortname`.
            - Compute price = amount / quantity.
            - Build `BrokerageEventImportRow` with resolved instrument and parsed values.

        Args:
            rows: Iterable of dicts representing raw brokerage operation rows.
            stock_client: Stock service client used to resolve instrument metadata.

        Returns:
            List of successfully parsed `BrokerageEventImportRow` objects.
            Invalid / unrecognized rows are silently skipped (with logging).
        """
        logger.info("parse_brokerage_events: start parsing brokerage rows")

        events: list[BrokerageEventImportRow] = []

        for r in rows:
            date = parse_date(r.get("data"))
            if not date:
                continue

            kind_raw = (r.get("tytuł operacji") or "").lower()
            if "kupna" in kind_raw:
                kind = BrokerageEventKind.BUY
            elif "sprzedaży" in kind_raw:
                kind = BrokerageEventKind.SELL
            else:
                continue

            try:
                data = (r.get("szczegóły").strip()).split(" ")
                shortname = data[0].split("-")[0]
                quantity_data = data[2]
                currency_data = data[5]
            except Exception:
                continue
            
            if not shortname:
                continue

            try:
                instr_data = await stock_client.search_instrument_by_shortname(shortname)
                if not instr_data:
                    logger.warning(f"No instrument found for shortname='{shortname}'")
                    continue

                inst = instr_data[0]
                symbol = inst["symbol"]
                mic = inst["mic"]
                name = inst.get("name") or shortname
                isin = inst.get("isin")
                inst_short = inst.get("shortname") or shortname
                currency = Currency(currency_data)
            except Exception as e:  
                logger.exception(f"Stock lookup failed for '{shortname}': {e}")
                continue

            quantity = dec(parse_amount(quantity_data))
            amount = abs(dec(parse_amount(r.get("kwota", "0"))))

            price = dec2(amount/quantity)

            events.append(
                BrokerageEventImportRow(
                    trade_at=date,
                    instrument_symbol=symbol,
                    instrument_mic=mic,
                    instrument_name=name,
                    instrument_isin=isin,
                    instrument_shortname=inst_short,
                    kind=kind,
                    quantity=quantity,
                    price=price,
                    currency=currency,
                    split_ratio=dec("0"),
                )
            )

        return events


class IngMaklerBankParser(BaseBankParser):
    """
    Parser for ING Makler CSV (brokerage) statements.

    Expected columns:
        - "Data transakcji"
        - "Kwota transakcji"
        - "Saldo po operacji"
        - "Typ transakcji"
        - "Opis transakcji"

    Raises:
        MissingRequiredColumnsError:
            If required columns (e.g., 'Saldo po operacji') are missing.
    """
    name = 'IngMakler CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    supports_brokerage_events = True
    
    def __init__(self):
        super().__init__()

    def sniff(self, header: list[str]) -> bool:
        """
        Determine if this parser is appropriate for the given CSV header.
        """
        hdr = [h.strip().lower() for h in header]
        return {'data operacji', 'kwota'} <= set(hdr)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        """
        Parse ING Makler CSV rows into TransactionCreationRow instances.

        Args:
            rows: Iterable of CSV dict rows.

        Returns:
            A list of TransactionCreationRow objects.
        """
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            logger.info(f"row: {r}")
            if "Saldo po operacji" not in r.keys():
                raise MissingRequiredColumnsError("Proszę dodać kolumnę: Saldo po operacji, z poprawnym saldem")
            date = parse_date(r.get("Data transakcji"))
            if not date:
                continue
            amount = dec(parse_amount(r.get('Kwota transakcji', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po operacji', '0')))
            desc = ' '.join([r.get('Typ transakcji'), ": ",  r.get('Opis transakcji')])

            cg_kind = None
            if "Dywidendy" in r.get('Typ transakcji'):
                cg_kind = CapitalGainKind.BROKER_DIVIDEND.name

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after,
                capital_gain_kind=cg_kind,
            ))
            
        return parsed

    async def parse_brokerage_events(
        self,
        rows: Iterable[dict[str, str]],
        stock_client: "StockClient",
    ) -> list[BrokerageEventImportRow]:
        """
        Parse ING Makler CSV rows into `BrokerageEventImportRow` objects
        and enrich instrument data using the stock service.

        Expected CSV column names (Polish):
            - "Data transakcji": transaction date (parsed via `parse_date`)
            - "Typ Transakcji": operation type ("kupno", "sprzedaż", etc.)
            - "Instrument": instrument shortname / name
            - "Ilość": quantity
            - "Kwota z Prowizją": total amount including commission
            - "Waluta": transaction currency code (e.g. "PLN")

        Logic:
            - Rows without a parsable date are skipped.
            - Only BUY/SELL operations are recognized, based on "Typ Transakcji".
            - Instruments are resolved via `stock_client.search_instrument_by_shortname`.
            - Price is computed as: price = amount / quantity.
            - Failed lookups or malformed rows are skipped (with logging).

        Args:
            rows: Iterable of dicts representing CSV rows.
            stock_client: Stock service client used to resolve instrument metadata.

        Returns:
            A list of successfully parsed `BrokerageEventImportRow` instances.
        """
        logger.info("parse_brokerage_events[ING]: start parsing brokerage rows")
        events: list[BrokerageEventImportRow] = []

        for r in rows:
            logger.info(r.get("Data transakcji"))
            date = parse_date(r.get("Data transakcji"))
            logger.info(date)
            if not date:
                continue

            kind_raw = (r.get("Typ Transakcji") or "").lower()
            if "kupno" in kind_raw:
                kind = BrokerageEventKind.BUY
            elif "sprzeda" in kind_raw:
                kind = BrokerageEventKind.SELL
            else:
                continue

            shortname = (r.get("Instrument") or "").strip()
            if not shortname:
                continue

            try:
                instr_data = await stock_client.search_instrument_by_shortname(shortname)
                if not instr_data:
                    logger.warning(f"No instrument found for shortname='{shortname}'")
                    continue

                inst = instr_data[0]
                symbol = inst["symbol"]
                mic = inst["mic"]
                name = inst.get("name") or shortname
                isin = inst.get("isin")
                inst_short = inst.get("shortname") or shortname
                currency = Currency(r.get("Waluta"))
            except Exception as e:
                logger.exception(f"Stock lookup failed for '{shortname}': {e}")
                continue

            quantity = dec(parse_amount(r.get("Ilość", "0")))
            amount = abs(dec(parse_amount(r.get("Kwota z Prowizją", "0"))))
            price = dec2(amount/quantity)

            events.append(
                BrokerageEventImportRow(
                    trade_at=date,
                    instrument_symbol=symbol,
                    instrument_mic=mic,
                    instrument_name=name,
                    instrument_isin=isin,
                    instrument_shortname=inst_short,
                    kind=kind,
                    quantity=quantity,
                    price=price,
                    currency=currency,
                    split_ratio=dec("0"),
                )
            )

        return events