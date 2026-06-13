from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import allure
import httpx
import pytest

FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _pdf_text_command(page_lines: Iterable[tuple[int, int, str]]) -> str:
    commands = ["/F1 10 Tf"]
    for x, y, text in page_lines:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"1 0 0 1 {x} {y} Tm ({escaped}) Tj")
    return "\n".join(commands) + "\n"


def _make_pdf(pages: list[list[tuple[int, int, str]]]) -> bytes:
    objects: list[bytes] = []

    def add_object(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    page_object_numbers = [3 + index * 2 for index in range(len(pages))]
    add_object("<< /Type /Catalog /Pages 2 0 R >>\n")
    add_object(
        "<< /Type /Pages /Kids ["
        + " ".join(f"{number} 0 R" for number in page_object_numbers)
        + f"] /Count {len(pages)} >>\n"
    )

    for page_index, page_lines in enumerate(pages):
        page_number = page_object_numbers[page_index]
        content_number = page_number + 1
        add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {2 + len(pages) * 2 + 1} 0 R >> >> "
            f"/Contents {content_number} 0 R >>\n"
        )
        stream = _pdf_text_command(page_lines)
        add_object(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}endstream\n")

    add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n")

    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{idx} 0 obj\n".encode("latin-1"))
        content.extend(body)
        content.extend(b"endobj\n")

    startxref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    content.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n".encode("latin-1")
    )
    return bytes(content)


def _velo_pdf_page(
    rows: list[tuple[str, str, str, str, str]],
    include_header: bool = True,
    start_y: int = 580,
    row_gap: int = 30,
) -> list[tuple[int, int, str]]:
    lines = []
    if include_header:
        lines.extend([
            (20, start_y + row_gap, "DATA"),
            (100, start_y + row_gap, "DATA_2"),
            (180, start_y + row_gap, "OPIS TRANSAKCJI"),
            (390, start_y + row_gap, "KWOTA"),
            (530, start_y + row_gap, "SALDO PO"),
        ])
    y = start_y
    for date, booking_date, description, amount, balance_after in rows:
        lines.extend([
            (20, y, date),
            (100, y, booking_date),
            (180, y, description),
            (390, y, amount),
            (530, y, balance_after),
        ])
        y -= row_gap
    return lines


@pytest.mark.component
@allure.epic("System Tests")
@allure.feature("Component")
@allure.story("Bank import parser service exposes and handles ING CSV and Velo Bank PDF formats")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("wallet", "transactions", "import", "parsing", "financial-data")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Checks the NiceGUI parser API used by the transaction modal. ING CSV is parsed "
    "end-to-end with deterministic financial rows; Velo Bank PDF is parsed from a "
    "deterministic PDF fixture and malformed PDF uploads return a controlled JSON error."
)
class TestBankTransactionImportParserApi:
    def test_parser_metadata_lists_ing_csv_and_velo_bank_pdf(self) -> None:
        response = httpx.get("http://nice-ui:8501/api/import/parsers", timeout=10.0)

        assert response.status_code == 200, response.text
        parsers = {item["name"]: item for item in response.json()}
        assert parsers["IngBank CSV"]["kind"] == "CSV"
        assert parsers["IngBank CSV"]["accept"] == ".csv"
        assert parsers["Velo Bank PDF"]["kind"] == "PDF"
        assert parsers["Velo Bank PDF"]["accept"] == ".pdf"
        assert parsers["BossaMakler CSV"]["kind"] == "CSV"
        assert parsers["BossaMakler CSV"]["supports_brokerage_history"] is True

    def test_ing_bank_csv_parser_returns_transactions_and_deposit_interest(self) -> None:
        csv_payload = (FIXTURES_DIR / "transactions_ing.csv").read_bytes()

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "IngBank CSV", "mode": "transactions"},
            files={"file": ("ing.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 4
        assert payload["rows"][0]["date"] == "2026-05-10"
        assert Decimal(str(payload["rows"][0]["amount"])) == Decimal("-45.67")
        assert Decimal(str(payload["rows"][0]["amount_after"])) == Decimal("954.33")
        assert payload["rows"][0]["description"] == "Sklep Testowy Zakupy spożywcze"
        assert payload["rows"][0]["capital_gain_kind"] is None
        assert payload["rows"][1]["date"] == "2026-05-11"
        assert Decimal(str(payload["rows"][1]["amount"])) == Decimal("1.23")
        assert Decimal(str(payload["rows"][1]["amount_after"])) == Decimal("955.56")
        assert payload["rows"][1]["capital_gain_kind"] == "DEPOSIT_INTEREST"
        assert payload["rows"][2]["date"] == "2026-05-12"
        assert Decimal(str(payload["rows"][2]["amount"])) == Decimal("10000.00")
        assert Decimal(str(payload["rows"][2]["amount_after"])) == Decimal("10955.56")
        assert "odsetki" not in payload["rows"][2]["description"].lower()
        assert payload["rows"][2]["capital_gain_kind"] is None
        assert payload["rows"][3]["date"] == "2026-05-12"
        assert Decimal(str(payload["rows"][3]["amount"])) == Decimal("1741.26")
        assert Decimal(str(payload["rows"][3]["amount_after"])) == Decimal("12696.82")
        assert "odsetki netto" in payload["rows"][3]["description"].lower()
        assert payload["rows"][3]["capital_gain_kind"] == "DEPOSIT_INTEREST"

    def test_ing_bank_csv_parser_accepts_quoted_export_header_and_uses_transaction_date(self) -> None:
        csv_payload = (FIXTURES_DIR / "transactions_ing_export_quoted_corrupted.csv").read_bytes()

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "IngBank CSV", "mode": "transactions"},
            files={"file": ("ing_export.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 45
        assert payload["count"] > 40
        row = payload["rows"][0]
        assert row["date"] == "2026-05-13"
        assert Decimal(str(row["amount"])) == Decimal("-219.05")
        assert Decimal(str(row["amount_after"])) == Decimal("2336.37")
        assert row["description"] == "Sklep Testowy P�atno�� BLIK"
        large_transfer = payload["rows"][38]
        assert Decimal(str(large_transfer["amount"])) == Decimal("-143630.00")
        assert large_transfer["description"] == "Duzy przelew Przelew �rodk�w"
        last_row = payload["rows"][-1]
        assert last_row["date"] == "2026-03-30"
        assert Decimal(str(last_row["amount"])) == Decimal("-45.00")
        assert last_row["description"] == "Kontrahent 45 Transakcja po duzym przelewie 45"

    def test_ing_makler_csv_parser_sorts_transactions_by_date_and_balance_chain(self) -> None:
        csv_payload = "\r\n".join([
            "Data transakcji;Typ transakcji;Opis transakcji;Kwota transakcji;Saldo po operacji;Waluta",
            "03-01-2026;Dywidendy;Dywidenda testowa - podatek;-10.00;140.00;PLN",
            "03-01-2026;Dywidendy;Dywidenda testowa - rozliczenie;50.00;150.00;PLN",
            "02-01-2026;Wpłaty/wypłaty;Dopłata rachunku;10.00;100.00;PLN",
            "01-01-2026;Wpłaty/wypłaty;Zasilenie rachunku;100.00;100.00;PLN",
            "01-01-2026;Blokady pod zlecenia;Blokada kupna;-30.00;70.00;PLN",
            "01-01-2026;Transakcje;Aktualizacja blokady;20.00;90.00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "IngMakler CSV", "mode": "transactions"},
            files={"file": ("ing-makler.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 6
        assert [row["date"] for row in payload["rows"]] == [
            "2026-01-01",
            "2026-01-01",
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-03",
        ]
        assert [Decimal(str(row["amount"])) for row in payload["rows"]] == [
            Decimal("100.00"),
            Decimal("-30.00"),
            Decimal("20.00"),
            Decimal("10.00"),
            Decimal("50.00"),
            Decimal("-10.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in payload["rows"]] == [
            Decimal("100.00"),
            Decimal("70.00"),
            Decimal("90.00"),
            Decimal("100.00"),
            Decimal("150.00"),
            Decimal("140.00"),
        ]

        running_balance = Decimal("0.00")
        for row in payload["rows"]:
            running_balance += Decimal(str(row["amount"]))
            assert running_balance == Decimal(str(row["amount_after"]))

        assert payload["rows"][4]["capital_gain_kind"] == "BROKER_DIVIDEND"
        assert payload["rows"][5]["capital_gain_kind"] == "BROKER_DIVIDEND"

    def test_bossa_makler_full_history_generates_balance_after_per_currency(self) -> None:
        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;waluta",
            "2026-06-04;Wypłata dywidendy TEST;;5,00;PLN",
            "2026-06-03;Wymiana waluty PLN/USD 4.0000;;25,00;USD",
            "2026-06-03;Wymiana waluty PLN/USD 4.0000;;-100,00;PLN",
            "2026-06-02;Przelew do DM BOŚ;;200,00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "brokerage_history"
        assert payload["count"] == 4
        assert [row["operation_type"] for row in payload["rows"]] == [
            "DIVIDEND",
            "FX",
            "FX",
            "TRANSFER",
        ]
        assert [row["currency"] for row in payload["rows"]] == ["PLN", "USD", "PLN", "PLN"]
        assert [Decimal(str(row["amount"])) for row in payload["rows"]] == [
            Decimal("5.00"),
            Decimal("25.00"),
            Decimal("-100.00"),
            Decimal("200.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in payload["rows"]] == [
            Decimal("105.00"),
            Decimal("25.00"),
            Decimal("100.00"),
            Decimal("200.00"),
        ]

    def test_bossa_makler_sprzedaz_and_zwrot_mapped_to_transfer(self) -> None:
        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;waluta",
            "2026-06-07;Sprzedaż JPP EUROHOLD-JPP**;;1500,00;PLN",
            "2026-06-07;Zwrot nadpłaty - przekroczony limit wpłat na IKE/IKZE 614585;;-500,00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["count"] == 2
        assert payload["rows"][0]["operation_type"] == "TRANSFER"
        assert payload["rows"][1]["operation_type"] == "TRANSFER"

    def test_bossa_makler_full_history_normalizes_market_suffix_and_falls_back_to_isin(self, stock_url: str) -> None:
        suffix = uuid4().hex[:8].upper()
        mic = f"B{suffix[:3]}"
        normalized_symbol = f"B{suffix[:5]}"
        isin_symbol = f"I{suffix[:5]}"
        normalized_isin = f"PL{uuid4().hex[:9].upper()}1"
        fallback_isin = f"PL{uuid4().hex[:9].upper()}2"

        market_response = httpx.post(
            f"{stock_url}/stock/markets",
            json={
                "mic": mic,
                "name": f"BoSSA Parser Market {suffix}",
                "country": "PL",
                "timezone": "Europe/Warsaw",
                "active": True,
                "currency": "PLN",
            },
            timeout=10.0,
        )
        assert market_response.status_code == 201, market_response.text

        for symbol, isin in ((normalized_symbol, normalized_isin), (isin_symbol, fallback_isin)):
            instrument_response = httpx.post(
                f"{stock_url}/stock/instruments",
                json={
                    "market_mic": mic,
                    "symbol": symbol,
                    "shortname": symbol,
                    "name": f"{symbol} TEST",
                    "type": "STOCK",
                    "status": "ACTIVE",
                    "currency": "PLN",
                    "isin": isin,
                    "historical_source": None,
                    "quote_source": None,
                    "popularity": 0,
                    "last_seen_at": None,
                },
                timeout=10.0,
            )
            assert instrument_response.status_code == 201, instrument_response.text

        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;waluta",
            f"2026-06-02;Rozliczenie transakcji kupna;NIEZGODNY-NC ({fallback_isin}) 2 x 5,00 PLN;-10,00;PLN",
            f"2026-06-01;Rozliczenie transakcji kupna;{normalized_symbol}-NC-FIX ({normalized_isin}) 10 x 2,00 PLN;-20,00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "brokerage_history"
        assert payload["count"] == 2
        assert [row["operation_type"] for row in payload["rows"]] == ["BUY", "BUY"]
        assert payload["rows"][0]["instrument_symbol"] == isin_symbol
        assert payload["rows"][0]["instrument_mic"] == mic
        assert Decimal(str(payload["rows"][0]["quantity"])) == Decimal("2")
        assert Decimal(str(payload["rows"][0]["price"])) == Decimal("5.00")
        assert payload["rows"][1]["instrument_symbol"] == normalized_symbol
        assert payload["rows"][1]["instrument_mic"] == mic
        assert Decimal(str(payload["rows"][1]["quantity"])) == Decimal("10")
        assert Decimal(str(payload["rows"][1]["price"])) == Decimal("2.00")
        assert all(row.get("review_reason") is None for row in payload["rows"])

    def test_bossa_makler_unknown_instrument_returns_needs_review_with_isin_and_normalized_name(self) -> None:
        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;waluta",
            "2026-06-01;Rozliczenie transakcji kupna;MISSING-NC-FIX (PLMISS000001) 10 x 2,00 PLN;-20,00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa-missing.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "brokerage_history"
        assert payload["count"] == 1
        row = payload["rows"][0]
        assert row["operation_type"] == "NEEDS_REVIEW"
        assert row["instrument_name"] == "MISSING"
        assert "MISSING" in row["review_reason"]
        assert "MISSING-NC-FIX" in row["review_reason"]
        assert "PLMISS000001" in row["review_reason"]
        assert "PLN" in row["review_reason"]

    def test_bossa_makler_zero_quantity_trade_returns_needs_review_instead_of_parser_error(self) -> None:
        csv_payload = "\r\n".join([
            "data;tytuł operacji;szczegóły;kwota;waluta",
            "2026-06-01;Rozliczenie transakcji kupna;PKOBP (PLPKO0000016) 0 x 10,00 PLN;0,00;PLN",
        ]).encode("cp1250")

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "BossaMakler CSV", "mode": "brokerage_history"},
            files={"file": ("bossa-zero-quantity.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "brokerage_history"
        assert payload["count"] == 1
        row = payload["rows"][0]
        assert row["operation_type"] == "NEEDS_REVIEW"
        assert row["price"] is None
        assert row["quantity"] is None
        assert "ilości" in row["review_reason"]

    def test_saxo_makler_csv_parses_cash_and_chf_brokerage_event_with_pln_settlement(self, stock_url: str) -> None:
        suffix = uuid4().hex[:4].upper()
        mic = f"S{suffix[:3]}"
        symbol = f"U{suffix}"
        isin = "CH0012255151"

        market_response = httpx.post(
            f"{stock_url}/stock/markets",
            json={
                "mic": mic,
                "name": f"Saxo Test Market {suffix}",
                "country": "CH",
                "timezone": "Europe/Zurich",
                "active": True,
                "currency": "CHF",
            },
            timeout=10.0,
        )
        assert market_response.status_code == 201, market_response.text

        instrument_response = httpx.post(
            f"{stock_url}/stock/instruments",
            json={
                "market_mic": mic,
                "symbol": symbol,
                "shortname": symbol,
                "name": "Swatch Group AG",
                "type": "STOCK",
                "status": "ACTIVE",
                "currency": "CHF",
                "isin": isin,
                "historical_source": None,
                "quote_source": None,
                "popularity": 0,
                "last_seen_at": None,
            },
            timeout=10.0,
        )
        assert instrument_response.status_code == 201, instrument_response.text

        csv_payload = "\r\n".join([
            "ID klienta;Data transakcji;Zdarzenie;Kwota;Saldo po operacji;Waluta;Instrument;Symbol instrumentu;Instrument ISIN;Waluta instrumentu;Rodzaj transakcji;Przelicznik konwersji",
            f"1;20-01-2026;Kupno 14 @ 30.80 CHF;-1983,55;8016,45;PLN;Swatch Group AG;{symbol}:{mic.lower()};{isin};CHF;Kupno akcji;4,598222",
        ]).encode("cp1250")

        cash_response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "SaxoMakler CSV", "mode": "transactions"},
            files={"file": ("saxo.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )
        assert cash_response.status_code == 200, cash_response.text
        cash_payload = cash_response.json()
        assert cash_payload["mode"] == "transactions"
        assert cash_payload["count"] == 1
        assert Decimal(str(cash_payload["rows"][0]["amount"])) == Decimal("-1983.55")
        assert Decimal(str(cash_payload["rows"][0]["amount_after"])) == Decimal("8016.45")
        assert "Swatch Group AG" in cash_payload["rows"][0]["description"]

        event_response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "SaxoMakler CSV", "mode": "brokerage_events"},
            files={"file": ("saxo.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )
        assert event_response.status_code == 200, event_response.text
        event_payload = event_response.json()
        assert event_payload["mode"] == "brokerage_events"
        assert event_payload["count"] == 1
        event = event_payload["rows"][0]
        assert event["instrument_symbol"] == symbol
        assert event["instrument_mic"] == mic
        assert event["kind"] == "BUY"
        assert Decimal(str(event["quantity"])) == Decimal("14.00")
        assert Decimal(str(event["price"])) == Decimal("30.80")
        assert event["currency"] == "CHF"
        assert event["settlement_currency"] == "PLN"
        assert Decimal(str(event["fx_rate"])) == Decimal("4.598222")

    def test_velo_bank_pdf_parser_returns_transactions_from_pdf_fixture(self) -> None:
        pdf_payload = (FIXTURES_DIR / "velobank_statement.pdf").read_bytes()

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 2
        assert payload["rows"][0]["date"] == "2026-05-10"
        assert Decimal(str(payload["rows"][0]["amount"])) == Decimal("-45.67")
        assert Decimal(str(payload["rows"][0]["amount_after"])) == Decimal("954.33")
        assert "Zakupy testowe" in payload["rows"][0]["description"]
        assert "456" in payload["rows"][0]["description"]
        assert "12345678901234567890123456" not in payload["rows"][0]["description"]
        assert payload["rows"][1]["date"] == "2026-05-11"
        assert Decimal(str(payload["rows"][1]["amount"])) == Decimal("5.00")
        assert Decimal(str(payload["rows"][1]["amount_after"])) == Decimal("959.33")
        assert payload["rows"][1]["description"] == "Zwrot testowy"

    def test_velo_bank_pdf_parser_reads_all_pages_and_skips_rows_without_amounts(self) -> None:
        pdf_payload = _make_pdf([
            _velo_pdf_page([
                ("10.05.2026", "10.05.2026", "Zakupy testowe", "-45,67", "954,33"),
                ("30.04.2026", "-", "Autoryzacja bez ksiegowania", "-", "-"),
            ]),
            _velo_pdf_page([
                ("11.05.2026", "11.05.2026", "Zwrot testowy", "5,00", "959,33"),
            ]),
        ])

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo-multipage.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 2
        assert [row["date"] for row in payload["rows"]] == ["2026-05-10", "2026-05-11"]
        assert [Decimal(str(row["amount"])) for row in payload["rows"]] == [
            Decimal("-45.67"),
            Decimal("5.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in payload["rows"]] == [
            Decimal("954.33"),
            Decimal("959.33"),
        ]
        assert all("Autoryzacja bez ksiegowania" not in row["description"] for row in payload["rows"])

    def test_velo_bank_pdf_parser_keeps_same_day_rows_near_top_of_last_page(self) -> None:
        pdf_payload = _make_pdf([
            _velo_pdf_page([
                ("03.06.2025", "03.06.2025", "Transakcja otwierajaca", "100,00 PLN", "100,00 PLN"),
            ]),
            _velo_pdf_page(
                [
                    ("02.06.2025", "02.06.2025", "Splata karty kredytowej", "-593,20 PLN", "1 173,75 PLN"),
                    ("02.06.2025", "02.06.2025", "Zamowienie nr 2306", "-4 131,80 PLN", "1 766,95 PLN"),
                    ("02.06.2025", "02.06.2025", "Polisa Warta", "-1 306,00 PLN", "5 898,75 PLN"),
                    ("02.06.2025", "02.06.2025", "Przelew wlasny", "7 000,00 PLN", "7 204,75 PLN"),
                ],
                include_header=False,
                start_y=700,
                row_gap=35,
            ),
        ])

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo-last-page.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        rows_for_day = [row for row in payload["rows"] if row["date"] == "2025-06-02"]
        assert len(rows_for_day) == 4
        assert [Decimal(str(row["amount"])) for row in rows_for_day] == [
            Decimal("-593.20"),
            Decimal("-4131.80"),
            Decimal("-1306.00"),
            Decimal("7000.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in rows_for_day] == [
            Decimal("1173.75"),
            Decimal("1766.95"),
            Decimal("5898.75"),
            Decimal("7204.75"),
        ]

    def test_velo_bank_pdf_parser_marks_interest_rows_as_deposit_capital_gain(self) -> None:
        pdf_payload = _make_pdf([
            _velo_pdf_page([
                ("31.05.2026", "31.05.2026", "Tytul: Podatek od odsetek", "-57,81 PLN", "195 766,43 PLN"),
                ("31.05.2026", "31.05.2026", "Tytul: Odsetki - Kapitalizacja odsetek", "304,23 PLN", "195 824,24 PLN"),
                ("30.05.2026", "30.05.2026", "Tytul: Przelew wlasny", "100,00 PLN", "195 520,01 PLN"),
            ]),
        ])

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo-interest.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 3
        assert Decimal(str(payload["rows"][0]["amount"])) == Decimal("-57.81")
        assert payload["rows"][0]["capital_gain_kind"] == "DEPOSIT_INTEREST"
        assert Decimal(str(payload["rows"][1]["amount"])) == Decimal("304.23")
        assert payload["rows"][1]["capital_gain_kind"] == "DEPOSIT_INTEREST"
        assert Decimal(str(payload["rows"][2]["amount"])) == Decimal("100.00")
        assert payload["rows"][2]["capital_gain_kind"] is None

    def test_velo_bank_pdf_parser_reads_last_money_token_when_card_description_overflows_amount_column(self) -> None:
        pdf_payload = _make_pdf([
            _velo_pdf_page([
                (
                    "23.05.2026",
                    "25.05.2026",
                    "Operacja karta w KAUFLA",
                    "ND 4660 -179,97 PLN",
                    "-740,92 PLN",
                ),
                (
                    "23.05.2026",
                    "25.05.2026",
                    "Operacja karta w ORLEN",
                    "STACJA NR 461 -210,01 PLN",
                    "-560,95 PLN",
                ),
                (
                    "23.05.2026",
                    "25.05.2026",
                    "Operacja karta w OGRODY",
                    "-32,00 PLN",
                    "-350,94 PLN",
                ),
            ]),
        ])

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo-credit-card.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 3
        assert [Decimal(str(row["amount"])) for row in payload["rows"]] == [
            Decimal("-179.97"),
            Decimal("-210.01"),
            Decimal("-32.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in payload["rows"]] == [
            Decimal("-740.92"),
            Decimal("-560.95"),
            Decimal("-350.94"),
        ]
        assert "4660" in payload["rows"][0]["description"]
        assert "STACJA NR 461" in payload["rows"][1]["description"]

    def test_velo_bank_pdf_parser_uses_booking_date_when_card_transaction_date_differs(self) -> None:
        pdf_payload = _make_pdf([
            _velo_pdf_page([
                (
                    "23.05.2026",
                    "25.05.2026",
                    "Operacja karta - sklep pierwszy",
                    "-39,69 PLN",
                    "-780,61 PLN",
                ),
                (
                    "24.05.2026",
                    "25.05.2026",
                    "Operacja karta - sklep drugi",
                    "-20,31 PLN",
                    "-740,92 PLN",
                ),
                (
                    "14.05.2026",
                    "14.05.2026",
                    "Splata karty",
                    "1000,00 PLN",
                    "0,00 PLN",
                ),
            ]),
        ])

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo-credit-card-booking-date.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 3
        assert [row["date"] for row in payload["rows"]] == [
            "2026-05-25",
            "2026-05-25",
            "2026-05-14",
        ]
        assert [Decimal(str(row["amount"])) for row in payload["rows"]] == [
            Decimal("-39.69"),
            Decimal("-20.31"),
            Decimal("1000.00"),
        ]
        assert [Decimal(str(row["amount_after"])) for row in payload["rows"]] == [
            Decimal("-780.61"),
            Decimal("-740.92"),
            Decimal("0.00"),
        ]

    def test_velo_bank_pdf_parser_returns_json_error_for_malformed_pdf(self) -> None:
        pdf_payload = (FIXTURES_DIR / "velobank_malformed.pdf").read_bytes()

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "Velo Bank PDF", "mode": "transactions"},
            files={"file": ("velo.pdf", pdf_payload, "application/pdf")},
            timeout=10.0,
        )

        assert response.status_code == 400
        payload = response.json()
        assert "detail" in payload
        assert "<html" not in str(payload).lower()

    def test_mbank_csv_parser_is_listed_in_parser_metadata(self) -> None:
        response = httpx.get("http://nice-ui:8501/api/import/parsers", timeout=10.0)

        assert response.status_code == 200, response.text
        parsers = {item["name"]: item for item in response.json()}
        assert "mBank CSV" in parsers, f"mBank CSV not found in {list(parsers)}"
        assert parsers["mBank CSV"]["kind"] == "CSV"
        assert parsers["mBank CSV"]["accept"] == ".csv"

    def test_mbank_csv_parser_returns_correct_transactions(self) -> None:
        csv_payload = (FIXTURES_DIR / "transactions_mbank.csv").read_bytes()

        response = httpx.post(
            "http://nice-ui:8501/api/import/parse",
            data={"parser_name": "mBank CSV", "mode": "transactions"},
            files={"file": ("mbank.csv", csv_payload, "text/csv")},
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == "transactions"
        assert payload["count"] == 2
        first = payload["rows"][0]
        assert first["date"] == "2026-05-10"
        assert Decimal(str(first["amount"])) == Decimal("-45.67")
        assert Decimal(str(first["amount_after"])) == Decimal("954.33")
        assert first["description"] == "Sklep testowy Zakupy spożywcze"
        assert first["capital_gain_kind"] is None
        second = payload["rows"][1]
        assert second["date"] == "2026-05-11"
        assert Decimal(str(second["amount"])) == Decimal("100.00")
        assert Decimal(str(second["amount_after"])) == Decimal("1054.33")
        assert "Wynagrodzenie" in second["description"]
        assert second["capital_gain_kind"] is None
