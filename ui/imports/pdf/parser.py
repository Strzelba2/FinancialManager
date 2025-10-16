from schemas.wallet import TransactionCreationRow
from typing import Union, IO
import tempfile
import tabula
import pandas as pd
import logging
from utils.utils import mask_account_numbers, parse_date
from utils.money import dec, parse_amount
import os
logger = logging.getLogger(__name__)


class VeloParser():
    """
    Parser for Velo Bank PDF transaction statements.

    This parser:
    - Uses `tabula` to extract a DataFrame from a known rectangular area.
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
                pages="1",
                multiple_tables=True,
                stream=True, lattice=False,
                guess=False,
                area=[210, 10, 800, 700],
                columns=[80, 160, 360, 500],
                pandas_options={'header': None},
            )
            if not dfs:
                logger.error("Failed to extract tables")
                raise Exception("Can not create table from pdf")
            
            df = pd.concat(dfs, ignore_index=True)
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)

            cols = pd.Index([str(c).strip() if c is not None else "" for c in df.columns])
            cols = cols.where(cols != "", other="col")

            df.columns = self.make_unique(cols)
            df = df.dropna(how="all")

            df_merged = self.collapse_wrapped_descriptions(df)
            out: list[TransactionCreationRow] = []

            for _, r in df_merged.iterrows():
                raw_date = str(r.get("DATA") or "").strip()
                date_val = parse_date(raw_date)
                
                if not date_val:
                    continue
                
                desc = str(r.get("OPIS TRANSAKCJI", ""))
                amount = dec(parse_amount(r.get("KWOTA")) or "0")
                amount_after = dec(parse_amount(r.get("SALDO PO", "")) or "0")
                
                out.append(TransactionCreationRow(
                    date=date_val,
                    amount=amount,
                    description=desc,
                    amount_after=amount_after
                ))
            return out
        
        finally:
            try: 
                os.remove(tmp_path)
            except Exception: 
                pass
    
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
                    
                desc = mask_account_numbers(row.get("OPIS TRANSAKCJI", ""), show_last=3)
                cur = {
                    "DATA": row.get("DATA", ""),
                    "DATA_2": row.get("DATA_2", ""),
                    "OPIS TRANSAKCJI": [row.get("OPIS TRANSAKCJI", "")],
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
