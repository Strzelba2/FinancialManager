from schemas.wallet import TransactionCreationRow, CapitalGainKind
from typing import Union, IO
import tempfile
import re
import tabula
import pandas as pd
import logging
from utils.utils import mask_account_numbers, parse_date
from utils.money import dec, parse_amount
import os
logger = logging.getLogger(__name__)

VELO_DEPOSIT_INTEREST_RE = re.compile(r"\bodset", re.IGNORECASE)
VELO_MONEY_TOKEN_RE = re.compile(
    r"[-+]?\d[\d\s\u00A0]*(?:,\d{2}|\.\d{2})\s*(?:PLN|z[łl�])?",
    re.IGNORECASE,
)


def deposit_interest_kind_for_description(description: str) -> str | None:
    if VELO_DEPOSIT_INTEREST_RE.search(description):
        return CapitalGainKind.DEPOSIT_INTEREST.name
    return None


def split_velo_money_cell(value: object) -> tuple[str, object | None]:
    text = "" if value is None else str(value).strip()
    matches = list(VELO_MONEY_TOKEN_RE.finditer(text))
    if not matches:
        return "", parse_amount(text)

    amount_match = matches[-1]
    prefix = f"{text[:amount_match.start()]} {text[amount_match.end():]}".strip(" ,;:-")
    return prefix, parse_amount(amount_match.group(0))


def parse_velo_money_cell(value: object) -> object | None:
    _, amount = split_velo_money_cell(value)
    return amount


class VeloParser():
    """
    Parser for Velo Bank PDF transaction statements.

    This parser:
    - Uses `tabula` to extract DataFrames from all statement pages.
    - Normalizes wrapped description lines across rows.
    - Parses and validates columns like "KWOTA", "DATA", and "SALDO PO".

    Expected columns in the PDF:
        - "DATA"
        - "DATA_2"
        - "OPIS TRANSAKCJI"
        - "KWOTA"
        - "SALDO PO"
    """
    name = 'Velo Bank PDF'
    kind = 'PDF'
    accept = '.pdf'
    upload_label = 'Drop PDF here or click'
    table_columns = ["DATA", "DATA_2", "OPIS TRANSAKCJI", "KWOTA", "SALDO PO"]

    def parse(self, file_obj: Union[bytes, IO[bytes]]) -> list[TransactionCreationRow]:
        """
        Parse the uploaded PDF and return a list of transactions.

        Args:
            file_obj: Bytes or file-like object of the uploaded PDF.

        Returns:
            List of TransactionCreationRow instances.
        """

        if hasattr(file_obj, "read"):
            try:
                file_obj.seek(0)
            except Exception:
                pass
            file_bytes = file_obj.read()
        else:
            file_bytes = file_obj
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
            
        try:
            dfs = tabula.read_pdf(
                tmp_path,
                pages="all",
                multiple_tables=True,
                stream=True, lattice=False,
                guess=False,
                area=[120, 10, 800, 700],
                columns=[80, 160, 360, 500],
                pandas_options={'header': None},
            )
            dfs = [df for df in dfs if df is not None and not df.empty]
            if not dfs:
                logger.error("Failed to extract tables")
                raise Exception("Can not create table from pdf")
            
            df = self.normalize_tables(dfs)
            if df.empty:
                logger.error("Failed to normalize extracted PDF tables")
                raise Exception("Can not create table from pdf")

            df_merged = self.collapse_wrapped_descriptions(df)
            out: list[TransactionCreationRow] = []

            for _, r in df_merged.iterrows():
                raw_transaction_date = str(r.get("DATA") or "").strip()
                raw_booking_date = str(r.get("DATA_2") or "").strip()
                raw_date = raw_booking_date or raw_transaction_date
                date_val = parse_date(raw_date) or parse_date(raw_transaction_date)
                
                if not date_val:
                    continue
                
                desc = str(r.get("OPIS TRANSAKCJI", ""))
                amount_raw = parse_velo_money_cell(r.get("KWOTA"))
                amount_after_raw = parse_velo_money_cell(r.get("SALDO PO", ""))
                if amount_raw is None or amount_after_raw is None:
                    logger.debug("Skipping Velo PDF row without amount or balance date=%s desc=%s", raw_date, desc)
                    continue
                amount = dec(amount_raw)
                amount_after = dec(amount_after_raw)
                cg_kind = deposit_interest_kind_for_description(desc)
                
                out.append(TransactionCreationRow(
                    date=date_val,
                    amount=amount,
                    description=desc,
                    amount_after=amount_after,
                    capital_gain_kind=cg_kind,
                ))
            return out
        
        finally:
            try: 
                os.remove(tmp_path)
            except Exception: 
                pass

    def normalize_tables(self, dfs: list[pd.DataFrame]) -> pd.DataFrame:
        """
        Normalize Tabula tables from statement pages into the parser's fixed schema.

        Velo statements repeat or omit the table header depending on the page. Later
        pages may start directly with transaction rows near the top margin, so each
        extracted table is normalized independently instead of using the first row
        from the whole concatenated extraction as the global header.
        """
        frames: list[pd.DataFrame] = []

        for raw_df in dfs:
            df = raw_df.dropna(how="all").copy()
            if df.empty:
                continue

            df = df.iloc[:, :len(self.table_columns)]
            while df.shape[1] < len(self.table_columns):
                df[df.shape[1]] = ""

            header_idx = self.find_header_row(df)
            if header_idx is not None:
                df = df.iloc[header_idx + 1:].reset_index(drop=True)
                if not df.empty and self.is_subheader_row(df.iloc[0]):
                    df = df.iloc[1:].reset_index(drop=True)

            if df.empty:
                continue

            df.columns = self.table_columns
            frames.append(df)

        if not frames:
            return pd.DataFrame(columns=self.table_columns)

        return pd.concat(frames, ignore_index=True).dropna(how="all")

    def find_header_row(self, df: pd.DataFrame) -> int | None:
        for idx, row in df.iterrows():
            text = " ".join(self.cell_text(value).upper() for value in row.tolist())
            if "OPIS TRANSAKCJI" in text:
                return idx
        return None

    def is_subheader_row(self, row: pd.Series) -> bool:
        text = " ".join(self.cell_text(value).upper() for value in row.tolist())
        return "KSIĘGOWANIA" in text or text.count("TRANSAKCJI") >= 2

    @staticmethod
    def cell_text(value: object) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()
    
    def collapse_wrapped_descriptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge continuation lines into a single transaction row.

        A wrapped description row has empty 'DATA' and 'DATA_2' fields.

        Returns:
            A new DataFrame with long descriptions collapsed into one row.
        """
        logger.debug("Collapsing wrapped transaction descriptions")
        for col in ["DATA", "DATA_2", "OPIS TRANSAKCJI", "KWOTA", "SALDO PO"]:
            if col in df.columns:
                df[col] = df[col].astype(str).replace({"nan": "", "None": ""}).str.strip()

        out = []
        cur = None

        for _, row in df.iterrows():
            is_cont = (row.get("DATA", "") == "") and (row.get("DATA_2", "") == "")

            if not is_cont: 
                if cur:
                    desc = " ".join(cur["OPIS TRANSAKCJI"]).strip()
                    desc = mask_account_numbers(desc, show_last=3)
                    cur["OPIS TRANSAKCJI"] = desc
                    out.append(cur)
                    
                desc = self.description_with_amount_overflow(
                    row.get("OPIS TRANSAKCJI", ""),
                    row.get("KWOTA", ""),
                )
                desc = mask_account_numbers(desc, show_last=3)
                cur = {
                    "DATA": row.get("DATA", ""),
                    "DATA_2": row.get("DATA_2", ""),
                    "OPIS TRANSAKCJI": [desc],
                    "KWOTA": row.get("KWOTA", ""),
                    "SALDO PO": row.get("SALDO PO", ""),
                }
            else:
                part = row.get("OPIS TRANSAKCJI", "")
                part = mask_account_numbers(part, show_last=3)
                if cur is None:
                    cur = {
                        "DATA": "", "DATA_2": "",
                        "OPIS TRANSAKCJI": [],
                        "KWOTA": "", "SALDO PO": ""
                    }
                if part:
                    cur["OPIS TRANSAKCJI"].append(part)

        if cur:
            desc = " ".join(cur["OPIS TRANSAKCJI"]).strip()
            desc = mask_account_numbers(desc, show_last=3) 
            cur["OPIS TRANSAKCJI"] = desc
            out.append(cur)

        return pd.DataFrame(out, columns=["DATA", "DATA_2", "OPIS TRANSAKCJI", "KWOTA", "SALDO PO"])

    @staticmethod
    def description_with_amount_overflow(description: object, amount_cell: object) -> str:
        prefix, _ = split_velo_money_cell(amount_cell)
        parts = [str(description or "").strip()]
        if prefix:
            parts.append(prefix)
        return " ".join(part for part in parts if part)
    
    @staticmethod
    def make_unique(index: pd.Index) -> pd.Index:
        """
        Ensure column names are unique by appending a suffix if needed.
        """
        seen, out = {}, []
        for name in index:
            base = name
            if base not in seen:
                seen[base] = 1 
                out.append(base)
            else:
                seen[base] += 1 
                out.append(f"{base}_{seen[base]}")
        return pd.Index(out)
