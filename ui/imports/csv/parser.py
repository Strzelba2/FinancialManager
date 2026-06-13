import io
import re
import csv
from decimal import Decimal
from typing import Iterable, Tuple
from schemas.wallet import (
    TransactionCreationRow, CapitalGainKind, BrokerageEventImportRow, BrokerageEventKind,
    BrokerageHistoryImportRow, Currency, InstrumentCurrency
    )
from utils.money import dec, parse_amount, dec2
from utils.utils import read_bytes, parse_date
from clients.stock_client import StockClient
from exceptions import MissingRequiredColumnsError
import logging

logger = logging.getLogger(__name__)


ING_INTEREST_AMOUNT_RE = re.compile(
    r'\bodsetk\w*[^\d+-]{0,80}([+-]?\d[\d\s\u00A0.]*(?:,\d{2}|\.\d{2}))\s*(?:z[łl�]|pln)?',
    re.IGNORECASE,
)


def _join_non_empty(*parts: str | None) -> str:
    return ' '.join(part.strip() for part in parts if part and part.strip())


def _extract_interest_amount(description: str) -> Decimal | None:
    match = ING_INTEREST_AMOUNT_RE.search(description)
    if not match:
        return None
    parsed = parse_amount(match.group(1))
    if parsed is None:
        return None
    return dec2(parsed)


def _description_without_interest_amount(description: str) -> str:
    cleaned = ING_INTEREST_AMOUNT_RE.sub('', description, count=1)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -:;')
    return cleaned or description


def _money_key(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _order_transaction_rows_by_balance_chain(
    rows: list[TransactionCreationRow],
    opening_balance: Decimal | None = None,
    prefer_reversed_source_order: bool = False,
) -> list[TransactionCreationRow]:
    if len(rows) <= 1:
        return list(rows)

    nodes: list[tuple[int, Decimal, Decimal]] = []
    for idx, row in enumerate(rows):
        after = _money_key(row.amount_after)
        before = _money_key(after - row.amount)
        nodes.append((idx, before, after))

    before_by_idx = {idx: before for idx, before, _ in nodes}
    after_by_idx = {idx: after for idx, _, after in nodes}

    if opening_balance is not None:
        opening = _money_key(opening_balance)
        start_nodes = [node for node in nodes if node[1] == opening]
    else:
        after_values = {after for _, _, after in nodes}
        start_nodes = [node for node in nodes if node[1] not in after_values]

    preferred_indexes = (
        list(reversed(range(len(rows))))
        if prefer_reversed_source_order
        else list(range(len(rows)))
    )
    preferred_position = {idx: position for position, idx in enumerate(preferred_indexes)}
    start_nodes = sorted(start_nodes, key=lambda node: preferred_position[node[0]])
    solution: list[int] | None = None

    def walk(current_idx: int, used: set[int], ordered: list[int]) -> None:
        nonlocal solution
        if solution is not None:
            return
        if len(ordered) == len(rows):
            solution = list(ordered)
            return

        current_after = after_by_idx[current_idx]
        candidates = sorted(
            [
                idx
                for idx in range(len(rows))
                if idx not in used and before_by_idx[idx] == current_after
            ],
            key=lambda idx: preferred_position[idx],
        )

        for candidate_idx in candidates:
            used.add(candidate_idx)
            ordered.append(candidate_idx)
            walk(candidate_idx, used, ordered)
            ordered.pop()
            used.remove(candidate_idx)

    for start_idx, _, _ in start_nodes:
        walk(start_idx, {start_idx}, [start_idx])
        if solution is not None:
            return [rows[idx] for idx in solution]

    return list(rows)


def _group_consecutive_transaction_rows_by_date(
    rows: list[TransactionCreationRow],
) -> list[list[TransactionCreationRow]]:
    groups: list[list[TransactionCreationRow]] = []
    for row in rows:
        if not groups or groups[-1][0].date != row.date:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _flatten_ordered_transaction_date_groups(
    groups: list[list[TransactionCreationRow]],
    prefer_reversed_source_order: bool = False,
) -> list[TransactionCreationRow]:
    ordered_rows: list[TransactionCreationRow] = []
    opening_balance: Decimal | None = None

    for group in groups:
        ordered_group = _order_transaction_rows_by_balance_chain(
            group,
            opening_balance=opening_balance,
            prefer_reversed_source_order=prefer_reversed_source_order,
        )
        ordered_rows.extend(ordered_group)
        if ordered_group:
            opening_balance = _money_key(ordered_group[-1].amount_after)
        else:
            opening_balance = None

    return ordered_rows


def _normalize_transaction_creation_rows_order(
    rows: list[TransactionCreationRow],
) -> list[TransactionCreationRow]:
    if len(rows) <= 1:
        return list(rows)

    is_ascending = all(rows[i].date <= rows[i + 1].date for i in range(len(rows) - 1))
    if is_ascending:
        return _flatten_ordered_transaction_date_groups(
            _group_consecutive_transaction_rows_by_date(rows),
        )

    is_descending = all(rows[i].date >= rows[i + 1].date for i in range(len(rows) - 1))
    if is_descending:
        return _flatten_ordered_transaction_date_groups(
            list(reversed(_group_consecutive_transaction_rows_by_date(rows))),
            prefer_reversed_source_order=True,
        )

    logger.warning("Mixed transaction order detected; applying stable date sort")
    sorted_rows = sorted(rows, key=lambda row: row.date)
    return _flatten_ordered_transaction_date_groups(
        _group_consecutive_transaction_rows_by_date(sorted_rows),
    )


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
    supports_brokerage_history: bool = False
    supports_full_import: bool = False
    
    def __init__(self):
        self.header_variants = [
            r'Data\s+transakcji',
            r'Data\s+operacji',
            r'Data\s+ksi(?:ę|e|.)gowania',
            r'ID\s+klienta',
        ]
        self.header_start_pattern = re.compile(
            r'^\s*#?\s*["\']?(?:' + r'|'.join(self.header_variants) + r')\b',
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
        - "Data transakcji"
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
            date = parse_date(
                r.get("Data transakcji")
                or r.get("Data operacji")
                or r.get("Data księgowania")
                or r.get("Data ksi�gowania")
            )
            if not date:
                continue
            amount = dec(parse_amount(r.get('Kwota transakcji (waluta rachunku)', '0')))
            amount_after = dec(parse_amount(r.get('Saldo po transakcji', '0')))
            desc = _join_non_empty(
                r.get('Dane kontrahenta'),
                r.get('Tytuł') or r.get('Tytu�'),
            )

            interest_amount = _extract_interest_amount(desc)
            if interest_amount and amount > 0 and Decimal("0") < interest_amount < amount:
                principal_amount = dec2(amount - interest_amount)
                parsed.append(TransactionCreationRow(
                    date=date,
                    amount=principal_amount,
                    description=_description_without_interest_amount(desc),
                    amount_after=dec2(amount_after - interest_amount),
                ))
                parsed.append(TransactionCreationRow(
                    date=date,
                    amount=interest_amount,
                    description=desc,
                    amount_after=amount_after,
                    capital_gain_kind=CapitalGainKind.DEPOSIT_INTEREST.name,
                ))
                continue

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
    Parser for SaxoMakler CSV statements (semicolon-delimited, Polish encoding).

    Expected columns (actual Saxo export headers):
        - "ID klienta"            — used for sniff / header detection
        - "Data transakcji"       — transaction date (Polish month names supported)
        - "Zdarzenie"             — event description (Dywidenda / Reinwestycja dywidendy /
                                    Kupno N @ P CCY / Sprzedaż -N @ P CCY / Wpłata / Wypłata …)
        - "Kwota"                 — amount in account currency
        - "Saldo po operacji"     — running balance in account currency
        - "Waluta"                — account currency (PLN / EUR)
        - "Instrument"            — full instrument name (e.g. "Swatch Group AG")
        - "Symbol instrumentu"    — exchange symbol (e.g. "UHRN:xswx")
        - "Instrument ISIN"       — ISIN (e.g. "CH0012255144")
        - "Waluta instrumentu"    — instrument native currency (EUR / CHF / PLN …)
        - "Rodzaj transakcji"     — broad operation kind (used in cash transaction description)

    Cash transactions (parse):
        - "Dywidenda" and "Reinwestycja dywidendy" → BROKER_DIVIDEND capital gain
        - Trailing empty rows (Saxo exports many blank semicolon lines) are skipped.

    Brokerage events (parse_brokerage_events):
        - Only BUY / SELL rows are emitted; "Kupno N @ P CCY" and "Sprzedaż -N @ P CCY"
          are parsed from the Zdarzenie field.
        - Instrument resolved: name → symbol prefix (before ":") → ISIN, whichever matches
          first in the stock service.
        - Currency taken from the Zdarzenie pattern (instrument native currency).
    """

    name = 'SaxoMakler CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'

    supports_brokerage_events = True
    supports_full_import = True

    # "Kupno 58 @ 8.04 EUR"  or  "Sprzedaż -111 @ 10.34 EUR".
    # The "ż" in "Sprzedaż" can decode to ż/ž/z (Saxo uses byte 0xBE), so match
    # the "Sprzeda" stem followed by any non-space diacritic char(s).
    _TRADE_RE = re.compile(
        r'^(?P<side>Kupno|Sprzeda\S*)\s+(?P<qty>-?\d+)\s+@\s+(?P<price>[\d.,]+)\s+(?P<ccy>[A-Z]{3})',
        re.IGNORECASE,
    )

    def __init__(self):
        super().__init__()
        # Override base header variants so find_table_start() locates the Saxo header row.
        self.header_variants = [r'ID\s+klienta']
        self.header_start_pattern = re.compile(
            r'^\s*#?\s*["\']?(?:' + r'|'.join(self.header_variants) + r')\b',
            re.IGNORECASE,
        )

    def sniff(self, header: list[str]) -> bool:
        hdr = {h.strip().lower() for h in header}
        return 'id klienta' in hdr and 'zdarzenie' in hdr

    @staticmethod
    def _is_empty_row(r: dict[str, str]) -> bool:
        return not any((v or '').strip() for v in r.values())

    @staticmethod
    def _cg_kind_for_zdarzenie(zdarzenie: str) -> str | None:
        z = zdarzenie.strip().lower()
        if z in ('dywidenda', 'reinwestycja dywidendy'):
            return CapitalGainKind.BROKER_DIVIDEND.name
        return None

    @staticmethod
    def _normalize_trade_date(value: str | None) -> str | None:
        """Repair the only PL month abbreviation with a diacritic — "paź" (October).

        Saxo's "ź" decodes inconsistently from its encoding (e.g. "paŤ"), so
        parse_date would not recognise the month and the row would be dropped.
        Other month abbreviations are ASCII and unaffected.
        """
        if not value:
            return value
        return re.sub(r'(?<=-)pa[^-\s]*(?=-)', 'paz', value, flags=re.IGNORECASE)

    def parse(self, rows: Iterable[dict[str, str]]) -> list[TransactionCreationRow]:
        parsed: list[TransactionCreationRow] = []
        for r in rows:
            if self._is_empty_row(r):
                continue
            date = parse_date(self._normalize_trade_date(r.get("Data transakcji")))
            if not date:
                continue

            amount_raw = parse_amount(r.get('Kwota', '0'))
            amount_after_raw = parse_amount(r.get('Saldo po operacji', '0'))
            if amount_raw is None or amount_after_raw is None:
                continue

            zdarzenie = (r.get('Zdarzenie') or '').strip()
            desc = _join_non_empty(r.get('Rodzaj transakcji'), r.get('Instrument'), zdarzenie)

            parsed.append(TransactionCreationRow(
                date=date,
                amount=dec(amount_raw),
                description=desc,
                amount_after=dec(amount_after_raw),
                capital_gain_kind=self._cg_kind_for_zdarzenie(zdarzenie),
            ))
        return parsed

    def _parse_trade_zdarzenie(self, zdarzenie: str) -> tuple[str, int, Decimal, str] | None:
        """Parse 'Kupno 58 @ 8.04 EUR' or 'Sprzedaż -111 @ 10.34 EUR'.

        Returns (side_lower, qty_abs, price, ccy_upper) or None.
        """
        m = self._TRADE_RE.match((zdarzenie or '').strip())
        if not m:
            return None
        side = m.group('side').lower()
        qty = abs(int(m.group('qty')))
        if qty == 0:
            return None
        price_str = m.group('price').replace(',', '.')
        try:
            price = dec2(price_str)
        except Exception:
            return None
        return side, qty, price, m.group('ccy').upper()

    async def _resolve_instrument(
        self,
        stock_client: "StockClient",
        name: str,
        symbol_raw: str | None,
        isin: str | None,
    ) -> tuple[str, str, str] | None:
        """Look up instrument: full name → symbol prefix → ISIN.

        When ISIN is present, a candidate list result is cross-checked by ISIN first
        before falling back to the first hit (same pattern as Bossa).
        """
        symbol_short = ((symbol_raw or '').split(':')[0].strip().upper()) or None
        isin_norm = ((isin or '').strip().upper()) or None

        candidates = [c for c in [name.strip() or None, symbol_short, isin_norm] if c]
        seen: set[str] = set()

        for candidate in candidates:
            key = candidate.upper()
            if key in seen:
                continue
            seen.add(key)

            try:
                instr_data = await stock_client.search_instrument_by_shortname(candidate)
            except Exception as e:
                logger.exception("Saxo stock lookup failed for %r: %s", candidate, e)
                continue

            if not instr_data:
                continue

            if isin_norm:
                for item in instr_data:
                    if (item.get('isin') or '').strip().upper() == isin_norm:
                        return item['symbol'], item['mic'], item.get('name') or name

            inst = instr_data[0]
            return inst['symbol'], inst['mic'], inst.get('name') or name

        logger.warning(
            "Saxo: no instrument found name=%r symbol=%r isin=%r", name, symbol_raw, isin
        )
        return None

    async def parse_brokerage_events(
        self,
        rows: Iterable[dict[str, str]],
        stock_client: "StockClient",
    ) -> list[BrokerageEventImportRow]:
        """Parse BUY / SELL brokerage events from a Saxo CSV.

        Only rows whose Zdarzenie field matches "Kupno N @ P CCY" or
        "Sprzedaż -N @ P CCY" are emitted; all other rows are silently skipped.
        Instrument is resolved against the stock service (name → symbol → ISIN).
        """
        events: list[BrokerageEventImportRow] = []

        for r in rows:
            if self._is_empty_row(r):
                continue

            date = parse_date(self._normalize_trade_date(r.get("Data transakcji")))
            if not date:
                continue

            zdarzenie = (r.get('Zdarzenie') or '').strip()
            trade = self._parse_trade_zdarzenie(zdarzenie)
            if trade is None:
                continue

            side, qty, price, ccy_str = trade
            kind = BrokerageEventKind.BUY if 'kupno' in side else BrokerageEventKind.SELL

            try:
                currency = InstrumentCurrency(ccy_str)
            except Exception:
                logger.warning("Saxo: unknown instrument currency %r in zdarzenie %r — skipping", ccy_str, zdarzenie)
                continue

            # Cash settles in the account currency (column "Waluta", PLN/USD/EUR);
            # "Przelicznik konwersji" converts instrument currency -> account currency.
            settlement_currency = None
            settlement_raw = (r.get('Waluta') or '').strip().upper()
            if settlement_raw:
                try:
                    settlement_currency = Currency(settlement_raw)
                except Exception:
                    settlement_currency = None
            fx_rate = parse_amount(r.get('Przelicznik konwersji'))

            name = (r.get('Instrument') or '').strip()
            symbol_raw = (r.get('Symbol instrumentu') or '').strip()
            isin = (r.get('Instrument ISIN') or '').strip().upper() or None

            if not name and not isin:
                logger.warning("Saxo: no instrument name or ISIN in row, zdarzenie=%r — skipping", zdarzenie)
                continue

            instrument = await self._resolve_instrument(stock_client, name, symbol_raw, isin)
            if instrument is None:
                logger.warning("Saxo: instrument not found name=%r isin=%r — skipping row", name, isin)
                continue

            symbol, mic, inst_name = instrument

            events.append(BrokerageEventImportRow(
                trade_at=date,
                instrument_symbol=symbol,
                instrument_mic=mic,
                instrument_name=inst_name,
                kind=kind,
                quantity=dec(str(qty)),
                price=price,
                currency=currency,
                split_ratio=dec("0"),
                settlement_currency=settlement_currency,
                fx_rate=dec(str(fx_rate)) if fx_rate is not None else None,
            ))

        return events
  
    
class BossaBankParser(BaseBankParser):
    """
    Parser for BOSSA Bank CSV statements.

    Expected columns:
        - "data"
        - "kwota"
        - "tytuł operacji"
        - "szczegóły"
        - "waluta"

    "Saldo po operacji" can be present, but empty rows are calculated from the full
    history in source order from oldest to newest, separately for each currency.
    """
    name = 'BossaMakler CSV'
    kind = 'CSV'
    accept = '.csv'
    upload_label = 'Drop CSV here or click'
    
    supports_brokerage_events = True
    supports_brokerage_history = True
    
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
        for row_number, r, date, _currency, amount, amount_after in self._history_rows_with_balances(rows):
            desc = _join_non_empty(r.get('tytuł operacji'), r.get('szczegóły'))
            
            cg_kind = None
            if "dywidendy" in (r.get('tytuł operacji') or "").lower():
                cg_kind = CapitalGainKind.BROKER_DIVIDEND.name

            parsed.append(TransactionCreationRow(
                date=date,
                amount=amount,
                description=desc,
                amount_after=amount_after,
                capital_gain_kind=cg_kind,
            ))
        return parsed

    @staticmethod
    def _required_history_columns() -> tuple[str, ...]:
        return ("data", "tytuł operacji", "szczegóły", "kwota", "waluta")

    def _history_rows_with_balances(
        self,
        rows: Iterable[dict[str, str]],
    ) -> list[tuple[int, dict[str, str], object, Currency, Decimal, Decimal]]:
        materialized = list(enumerate(rows, start=2))
        prepared: dict[int, tuple[int, dict[str, str], object, Currency, Decimal, Decimal]] = {}
        running_by_currency: dict[Currency, Decimal] = {}

        for row_number, row in reversed(materialized):
            missing = [col for col in self._required_history_columns() if col not in row]
            if missing:
                raise MissingRequiredColumnsError(
                    f"Proszę dodać kolumny: {', '.join(missing)}"
                )

            date = parse_date(row.get("data"))
            if not date:
                continue

            currency_raw = (row.get("waluta") or "").strip().upper()
            try:
                currency = Currency(currency_raw)
            except Exception as e:
                raise ValueError(f"Row {row_number}: nieobsługiwana waluta {currency_raw!r}.") from e

            amount_raw = parse_amount(row.get("kwota"))
            if amount_raw is None:
                raise ValueError(f"Row {row_number}: nieprawidłowa kwota operacji.")

            amount = dec2(amount_raw)
            amount_after_raw = parse_amount(row.get("Saldo po operacji")) if "Saldo po operacji" in row else None
            if amount_after_raw is None:
                previous = running_by_currency.get(currency, Decimal("0.00"))
                amount_after = dec2(previous + amount)
            else:
                amount_after = dec2(amount_after_raw)

            running_by_currency[currency] = amount_after
            prepared[row_number] = (row_number, row, date, currency, amount, amount_after)

        return [
            prepared[row_number]
            for row_number, _row in materialized
            if row_number in prepared
        ]

    @staticmethod
    def _parse_trade_details(details: str) -> tuple[str, str | None, Decimal, str] | None:
        match = re.search(
            r"^\s*(?P<shortname>.+?)\s+\((?P<isin>[^)]*)\)\s+"
            r"(?P<quantity>[\d\s.,]+)\s+x\s+"
            r"(?P<price>[\d\s.,]+)\s+"
            r"(?P<currency>PLN|USD|EUR)\b",
            details or "",
            re.IGNORECASE,
        )
        if not match:
            return None
        quantity_raw = parse_amount(match.group("quantity"))
        currency = match.group("currency").upper()
        if quantity_raw is None:
            return None
        quantity = dec(quantity_raw)
        if quantity <= 0:
            return None
        shortname = match.group("shortname").strip()
        isin = (match.group("isin") or "").strip().upper() or None
        return shortname, isin, quantity, currency

    @staticmethod
    def _normalize_bossa_instrument_name(shortname: str) -> str:
        normalized = re.sub(r"\s+", " ", shortname or "").strip()
        if not normalized:
            return ""
        normalized = re.split(r"\s*-\s*", normalized, maxsplit=1)[0].strip()
        return normalized or (shortname or "").strip()

    @staticmethod
    def _parse_forced_sell_shortname(title: str) -> str | None:
        match = re.search(r"Wykup\s+akcji\s+(.+?)(?:\s+\(|$)", title or "", re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip()

    async def _resolve_instrument(
        self,
        stock_client: "StockClient",
        shortname: str,
        isin: str | None = None,
    ) -> tuple[str, str, str] | None:
        normalized = self._normalize_bossa_instrument_name(shortname)
        isin = (isin or "").strip().upper() or None
        candidates = [
            candidate
            for candidate in (normalized, (shortname or "").strip(), isin)
            if candidate
        ]
        seen: set[str] = set()

        for candidate in candidates:
            candidate_key = candidate.upper()
            if candidate_key in seen:
                continue
            seen.add(candidate_key)

            try:
                instr_data = await stock_client.search_instrument_by_shortname(candidate)
            except Exception as e:
                logger.exception(f"Stock lookup failed for '{candidate}': {e}")
                continue

            if not instr_data:
                continue

            if isin:
                for item in instr_data:
                    if (item.get("isin") or "").strip().upper() == isin:
                        inst = item
                        return (
                            inst["symbol"],
                            inst["mic"],
                            inst.get("name") or normalized or shortname,
                        )

            for item in instr_data:
                symbol = (item.get("symbol") or "").strip().upper()
                item_shortname = (item.get("shortname") or "").strip().upper()
                if symbol == normalized.upper() or item_shortname == normalized.upper():
                    inst = item
                    return (
                        inst["symbol"],
                        inst["mic"],
                        inst.get("name") or normalized or shortname,
                    )

            inst = instr_data[0]
            return (
                inst["symbol"],
                inst["mic"],
                inst.get("name") or normalized or shortname,
            )

        logger.warning(
            "No instrument found for BoSSA shortname=%r normalized=%r isin=%r",
            shortname,
            normalized,
            isin,
        )
        return None

    @classmethod
    def _missing_instrument_reason(cls, raw_shortname: str | None, isin: str | None, currency: Currency) -> tuple[str, str]:
        normalized = cls._normalize_bossa_instrument_name(raw_shortname or "")
        display_name = normalized or raw_shortname or "instrument"
        raw_note = (
            f" (BoSSA: {raw_shortname.strip()})"
            if raw_shortname and raw_shortname.strip() and raw_shortname.strip() != display_name
            else ""
        )
        reason = (
            f"Nie znaleziono instrumentu {display_name}{raw_note}"
            f"{f' (ISIN: {isin})' if isin else ''}, waluta {currency.value}. "
            "Dodaj instrument w stock/notowaniach przed importem."
        )
        return (
            display_name,
            reason,
        )

    async def parse_brokerage_history(
        self,
        rows: Iterable[dict[str, str]],
        stock_client: "StockClient",
    ) -> list[BrokerageHistoryImportRow]:
        parsed: list[BrokerageHistoryImportRow] = []
        for row_number, r, date, currency, amount, amount_after in self._history_rows_with_balances(rows):
            title = (r.get("tytuł operacji") or "").strip()
            details = (r.get("szczegóły") or "").strip()
            description = _join_non_empty(title, details)[:255]
            title_lower = title.lower()

            base = {
                "row_number": row_number,
                "trade_at": date,
                "currency": currency,
                "amount": amount,
                "amount_after": amount_after,
                "description": description,
            }

            if "rozliczenie transakcji kupna" in title_lower or "rozliczenie transakcji sprzeda" in title_lower:
                details_data = self._parse_trade_details(details)
                if details_data is None:
                    parsed.append(BrokerageHistoryImportRow(
                        **base,
                        operation_type="NEEDS_REVIEW",
                        review_reason="Nie można odczytać instrumentu, ilości lub waluty z pola szczegóły.",
                    ))
                    continue

                shortname, isin, quantity, details_currency = details_data
                if details_currency != currency.value:
                    raise ValueError(
                        f"Row {row_number}: waluta w szczegółach ({details_currency}) "
                        f"nie zgadza się z kolumną waluta ({currency.value})."
                    )

                instrument = await self._resolve_instrument(stock_client, shortname, isin)
                if instrument is None:
                    display_name, review_reason = self._missing_instrument_reason(shortname, isin, currency)
                    parsed.append(BrokerageHistoryImportRow(
                        **base,
                        operation_type="NEEDS_REVIEW",
                        instrument_name=display_name,
                        review_reason=review_reason,
                    ))
                    continue

                symbol, mic, name = instrument
                event_kind = (
                    BrokerageEventKind.BUY
                    if "kupna" in title_lower
                    else BrokerageEventKind.SELL
                )
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type=event_kind.value,
                    instrument_symbol=symbol,
                    instrument_mic=mic,
                    instrument_name=name,
                    event_kind=event_kind,
                    quantity=quantity,
                    price=dec2(abs(amount) / quantity),
                    split_ratio=dec("0"),
                ))
                continue

            if title_lower.startswith("wypłata dywidendy") or title_lower.startswith("wyplata dywidendy"):
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="DIVIDEND",
                    capital_gain_kind=CapitalGainKind.BROKER_DIVIDEND.name,
                ))
                continue

            if "przelew do dm" in title_lower:
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="TRANSFER",
                ))
                continue

            if title_lower.startswith("wymiana waluty"):
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="FX",
                ))
                continue

            if title_lower.startswith("wykup akcji"):
                shortname = self._parse_forced_sell_shortname(title)
                instrument = await self._resolve_instrument(stock_client, shortname or "")
                if shortname is None or instrument is None:
                    display_name, review_reason = self._missing_instrument_reason(shortname, None, currency)
                    parsed.append(BrokerageHistoryImportRow(
                        **base,
                        operation_type="NEEDS_REVIEW",
                        instrument_name=display_name,
                        review_reason=review_reason,
                    ))
                    continue

                symbol, mic, name = instrument
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="FORCED_SELL",
                    instrument_symbol=symbol,
                    instrument_mic=mic,
                    instrument_name=name,
                    event_kind=BrokerageEventKind.SELL,
                    split_ratio=dec("0"),
                ))
                continue

            if title_lower.startswith("sprzedaż "):
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="TRANSFER",
                ))
                continue

            if title_lower.startswith("zwrot nadpłaty"):
                parsed.append(BrokerageHistoryImportRow(
                    **base,
                    operation_type="TRANSFER",
                ))
                continue

            parsed.append(BrokerageHistoryImportRow(
                **base,
                operation_type="NEEDS_REVIEW",
                review_reason=f"Nieobsługiwana operacja BoSSA: {title}.",
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

            quantity_raw = parse_amount(quantity_data)
            amount_raw = parse_amount(r.get("kwota", "0"))
            if quantity_raw is None or amount_raw is None:
                continue
            quantity = dec(quantity_raw)
            if quantity <= 0:
                continue
            amount = abs(dec(amount_raw))

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
            
        return _normalize_transaction_creation_rows_order(parsed)

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

            quantity_raw = parse_amount(r.get("Ilość", "0"))
            amount_raw = parse_amount(r.get("Kwota z Prowizją", "0"))
            if quantity_raw is None or amount_raw is None:
                continue
            quantity = dec(quantity_raw)
            if quantity <= 0:
                continue
            amount = abs(dec(amount_raw))
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
