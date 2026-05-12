from __future__ import annotations

import asyncio
import copy
import unittest
from datetime import date, datetime, timezone

import allure
import pytest

from app.reports.equity.ai_schema import EquityAiPayload
from app.reports.equity.web_source import (
    EquityWebSourceClient,
    EquityWebSourceFacts,
    _ParsedTable,
    _TableRow,
    final_report_payload_needs_enrichment,
    merge_web_source_report_metrics,
    merge_web_source_facts,
    _extract_attachment_links,
    _extract_notice_text_from_html,
    _latest_metric_from_table,
    _latest_peer_metric_from_table,
    _parse_insider_transaction_from_text,
    report_payload_needs_enrichment,
)
from app.reports.equity.builder import build_equity_report

from .test_builder import make_ai_payload, make_candles

pytestmark = pytest.mark.unit


LISTING_HTML = """
<html>
  <body>
    <a href="/notowania/PEKABEX">PBX (PEKABEX)</a>
    <a href="/notowania/UNIBEP">UNI (UNIBEP)</a>
  </body>
</html>
"""


PROFILE_HTML = """
<html>
  <body>
    <table>
      <tr><th>Nazwa</th><td>Pekabex S.A.</td></tr>
      <tr><th>Branża</th><td>Prefabrykacja betonowa</td></tr>
      <tr><th>Adres</th><td>Poznań</td></tr>
      <tr><th>WWW</th><td>https://pekabex.pl</td></tr>
      <tr><th>ISIN</th><td>PLPKBEX00072</td></tr>
      <tr><th>CEO</th><td>Robert Jędrzyński</td></tr>
      <tr><th>Liczba akcji</th><td>24 800 000</td></tr>
    </table>
    <div>
      <label>Profil działalności</label>
      <div>Producent prefabrykatów betonowych i generalny wykonawca.</div>
    </div>
    <p>Najbliższy raport okresowy: raport roczny 2026-04-30 czwartek</p>
  </body>
</html>
"""


RZIS_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023</th>
    <th>2024</th>
    <th>O4K (wrz 25)*</th>
    <th></th>
  </tr>
  <tr data-field="IncomeRevenues">
    <td>Przychody ze sprzedaży</td><td>1 620 000</td><td>1 740 000</td><td>1 814 000 r/r +19.7% ~branża -3.0%</td><td></td>
  </tr>
  <tr data-field="IncomeEBITDA">
    <td>EBITDA</td><td>120 000</td><td>132 000</td><td>145 000 r/r +3.0% ~branża 1.0%</td><td></td>
  </tr>
  <tr data-field="IncomeShareholderNetProfit">
    <td>Zysk netto akcjonariuszy j.d.</td><td>61 000</td><td>74 000</td><td>-4 960 r/r -115.57%</td><td></td>
  </tr>
</table>
"""


MARKET_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2024/Q4 (gru 24)</th>
    <th>2025/Q1 (mar 25)</th>
    <th>2025/Q2 (cze 25)</th>
    <th>2025/Q3 (wrz 25)</th>
    <th></th>
  </tr>
  <tr data-field="ShareAmount">
    <td>Liczba akcji</td><td>24 826 512</td><td>24 826 512</td><td>24 826 512</td><td>24 826 512</td><td></td>
  </tr>
  <tr data-field="CWK">
    <td>Cena / Wartość księgowa</td><td>0,83 ~branża 1,22</td><td>0,87 ~branża 1,42</td><td>0,86 ~branża 1,56</td><td>0,74 ~branża 1,33</td><td></td>
  </tr>
  <tr data-field="CP">
    <td>Cena / Przychody ze sprzedaży</td><td>0,25 ~branża 0,49</td><td>0,25 ~branża 0,57</td><td>0,24 ~branża 0,51</td><td>0,19 ~branża 0,59</td><td></td>
  </tr>
  <tr data-field="CZ">
    <td>Cena / Zysk</td><td>11,85 ~branża 10,56</td><td>15,94 ~branża 13,71</td><td>17,68 ~branża 13,50</td><td></td><td></td>
  </tr>
  <tr data-field="EarningsPerShare">
    <td>Zysk na akcję</td><td>2,46</td><td>2,88</td><td>3,05</td><td>-0,20</td><td></td>
  </tr>
  <tr data-field="EVEBITDA">
    <td>EV / EBITDA</td><td>5,66 ~branża 4,39</td><td>7,22 ~branża 5,06</td><td>8,02 ~branża 5,29</td><td>18,76 ~branża 5,08</td><td></td>
  </tr>
</table>
"""


BALANCE_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023</th>
    <th>2024</th>
    <th>2025/Q3</th>
  </tr>
  <tr data-field="BalanceCash">
    <td>Środki pieniężne</td><td>90 000</td><td>105 000</td><td>110 000</td>
  </tr>
  <tr data-field="BalanceTotalAssets">
    <td>Aktywa razem</td><td>1 050 000</td><td>1 160 000</td><td>1 210 000</td>
  </tr>
  <tr data-field="BalanceCapital">
    <td>Kapitał własny</td><td>520 000</td><td>565 000</td><td>590 000</td>
  </tr>
</table>
"""


CASHFLOW_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023</th>
    <th>2024</th>
    <th>O4K (wrz 25)*</th>
  </tr>
  <tr data-field="CashflowAmortization">
    <td>Amortyzacja</td><td>35 000</td><td>39 000</td><td>41 000</td>
  </tr>
  <tr data-field="CashflowChangeReceivablesOperating">
    <td>Zmiana należności z działalności operacyjnej</td><td>-8 000</td><td>2 000</td><td>-4 960</td>
  </tr>
  <tr data-field="CashflowOperating">
    <td>Przepływy pieniężne z działalności operacyjnej</td><td>84 000</td><td>97 000</td><td>9 342</td>
  </tr>
  <tr data-field="CashflowCapex">
    <td>CAPEX</td><td>52 000</td><td>48 000</td><td>50 000</td>
  </tr>
  <tr data-field="CashflowFCM">
    <td>FCF</td><td>58 000</td><td>65 000</td><td>72 000</td>
  </tr>
</table>
"""


PROFITABILITY_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023/Q4 (gru 23)</th>
    <th>2024/Q4 (gru 24)</th>
    <th>O4K (wrz 25)*</th>
    <th></th>
  </tr>
  <tr data-field="ROE">
    <td>ROE</td><td>12,4</td><td>13,8</td><td>-1,85% ~branża 6,0%</td><td></td>
  </tr>
  <tr data-field="ROIC">
    <td>ROIC</td><td>10,1</td><td>10,8</td><td>0,66% ~branża 7,0%</td><td></td>
  </tr>
</table>
"""


DEBT_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023/Q4 (gru 23)</th>
    <th>2024/Q4 (gru 24)</th>
    <th>O4K (wrz 25)*</th>
    <th></th>
  </tr>
  <tr data-field="DebtFin">
    <td>Zadłużenie finansowe netto</td><td>120 000</td><td>104 000</td><td>242 135 000</td><td></td>
  </tr>
  <tr data-field="DebtFinEBITDA">
    <td>Zadłużenie finansowe netto / EBITDA</td><td>1,0</td><td>0,8</td><td>7,39 ~branża 4,2</td><td></td>
  </tr>
  <tr data-field="CG">
    <td>Zadłużenie kapitału własnego</td><td>0,35</td><td>0,28</td><td>2,03 ~branża 1,1</td><td></td>
  </tr>
  <tr data-field="InterestCoverage">
    <td>Pokrycie odsetek</td><td>6,2</td><td>7,4</td><td>8,1</td><td></td>
  </tr>
</table>
"""


LIQUIDITY_HTML = """
<table class="report-table">
  <tr>
    <th>Pozycja</th>
    <th>2023</th>
    <th>2024</th>
    <th>O4K (wrz 25)*</th>
    <th></th>
  </tr>
  <tr data-field="QR">
    <td>Płynność szybka</td><td>1,0</td><td>1,1</td><td>1,2 ~branża 1,0</td><td></td>
  </tr>
  <tr data-field="CR">
    <td>Płynność bieżąca</td><td>1,4</td><td>1,5</td><td>1,6 ~branża 1,4</td><td></td>
  </tr>
</table>
"""


DIVIDEND_HTML = """
<script>
var chartsDataAll = {"2024":{"UZN":0.42},"2025":{"UZN":0.47}};
</script>
<table>
  <tr><th>Rok</th><th>DPS</th><th>Stopa</th><th>Ex</th><th>Pay</th></tr>
  <tr><td>2024</td><td>1,20</td><td>5,1%</td><td>10.07.2024</td><td>22.07.2024</td></tr>
  <tr><td>2025</td><td>1,40</td><td>5,6%</td><td>09.07.2025</td><td>21.07.2025</td></tr>
</table>
"""


NEWS_HTML = """
<div id="news-radar-body">
  <div class="record record-type-NEWS">
    <div class="record-header"><a href="https://espiebi.pap.pl/node/719634">PEKABEX - Zmiana terminu publikacji raportów okresowych</a></div>
    <div class="record-footer"><a class="record-author" href="#">EBI/ESPI</a><span class="record-date">2026-04-22 08:59:34</span></div>
  </div>
  <div class="record record-type-NEWS">
    <div class="record-header"><a href="https://espiebi.pap.pl/node/718232">PEKABEX - Nabycie akcji emitenta przez osobę blisko związaną z osobą pełniącą obowiązki zarządcze</a></div>
    <div class="record-footer"><a class="record-author" href="#">EBI/ESPI</a><span class="record-date">2026-04-01 12:11:53</span></div>
  </div>
  <div class="record record-type-NEWS">
    <div class="record-header"><a href="https://espiebi.pap.pl/node/714669">PEKABEX - Zbycie akcji emitenta przez osobę blisko związaną z osobą pełniącą obowiązki zarządcze</a></div>
    <div class="record-footer"><a class="record-author" href="#">EBI/ESPI</a><span class="record-date">2026-02-05 15:10:01</span></div>
  </div>
</div>
"""


SHAREHOLDERS_HTML = """
<table>
  <tr><th>Akcjonariusz</th></tr>
  <tr>
    <td>STE sp. z o.o. wraz z PWM</td>
    <td>38,10</td>
    <td></td><td></td><td></td><td></td>
    <td>31.12.2024</td>
  </tr>
  <tr>
    <td>OFE Nationale Nederlanden</td>
    <td>7,20</td>
    <td></td><td></td><td></td><td></td>
    <td>31.12.2024</td>
  </tr>
</table>
"""


INSIDER_PDF_TEXT = """
Powiadomienie o transakcji/transakcjach o którym mowa
w art. 19 ust. 1 rozporządzenia MAR
1

Dane osoby pełniącej obowiązki zarządcze/osoby blisko z nią związanej

a) Nazwa/Nazwisko

2 Powód powiadomienia
a) Stanowisko/status

b) Pierwotne powiadomienie / zmiana
3

STE spółka z ograniczoną odpowiedzialnością
ul. Stefana Batorego 16, lok. 1A
80-251 Gdańsk
Osoba blisko związana z osobą pełniącą obowiązki
zarządcze, tj. Panem Maciejem Grabskim, członkiem Rady
Nadzorczej Poznańskiej Korporacji Budowlanej Pekabex
S.A.
Pierwotne powiadomienie.

4

Szczegółowe informacje dotyczące transakcji
b) Rodzaj transakcji
Nabycie
c) Cena i wolumen

Cena
27.03.2026: 10,46 PLN
30.03.2026: 11,29 PLN
31.03.2026: 11,08 PLN

Wolumen
41 610
67 696
15 694

d) Informacje zbiorcze
− Łączny wolumen
− Cena

Łączny wolumen: 125 000
Cena:
41 610 akcji: 10,46 PLN
67 696 akcji: 11,29 PLN
15 694 akcji: 11,08 PLN

e) Data transakcji

27-03-2026, 30-03-2026, 31-03-2026

f)

XWAR
"""


INSIDER_SELL_PDF_TEXT = """
Powiadomienie o transakcji/transakcjach o którym mowa
w art. 19 ust. 1 rozporządzenia MAR
1

Dane osoby pełniącej obowiązki zarządcze/osoby blisko z nią związanej

a) Nazwa/Nazwisko

2 Powód powiadomienia
a) Stanowisko/status

b) Pierwotne powiadomienie / zmiana
3

STE spółka z ograniczoną odpowiedzialnością
Osoba blisko związana z osobą pełniącą obowiązki
zarządcze, tj. Panem Maciejem Grabskim, członkiem Rady
Nadzorczej Poznańskiej Korporacji Budowlanej Pekabex
S.A.
Pierwotne powiadomienie.

4

Szczegółowe informacje dotyczące transakcji
b) Rodzaj transakcji
Zbycie
d) Informacje zbiorcze
- Łączny wolumen
- Cena

Łączny wolumen: 4 800
Cena: 10,22 PLN

e) Data zawarcia transakcji

04-02-2026

f)

XWAR
"""


INSIDER_SELL_SIMPLE_PDF_TEXT = """
Powiadomienie o transakcji/transakcjach*, o którym mowa
w art. 19 ust. 1 rozporządzenia MAR
1.

Dane osoby pełniącej obowiązki zarządcze / osoby blisko z nią związanej:

a)

Nazwa:

Fernik Holdings ltd.

2.

Powód powiadomienia:
Dane osoby pełniącej obowiązki zarządcze, dla której podmiot zobowiązany do wypełnienia
formularza jest osobą blisko związaną
a) Imię i Nazwisko:
Robert Jędrzejowski
b) Stanowisko/Status:
Prezes Zarządu
c)
3.
a)

Powiadomienie pierwotne /
Powiadomienie pierwotne
zmiana:
Dane emitenta, uczestnika rynku uprawnień do emisji, platformy aukcyjnej, prowadzącego
aukcje lub monitorującego aukcje:
LEI:
Poznańska Korporacja Budowlana Pekabex S.A.

b) Nazwa:
4.

a)

2594007J8EIE7USAH935

Szczegółowe informacje dotyczące transakcji : rubrykę tę należy wypełnić dla (i) każdego
rodzaju instrumentu; (ii) każdego rodzaju transakcji; (iii) każdej daty; oraz (iv) każdego
miejsca, w którym przeprowadzono transakcje:
Opis instrumentu finansowego, Akcja
rodzaj instrumentu:
Kod identyfikacyjny:
PLPKBEX00072

b) Rodzaj transakcji:

Zbycie

c)

Cena i wolumen:

Cena:

12,40 PLN Wolumen:

20 000

d) Informacje zbiorcze:

Cena:

12,40 PLN Wolumen:

20 000

e)

Data:

2026-02-03

f)

Miejsce transakcji:

XWAR
"""


PAP_NOTICE_WITH_DOWNLOAD_LINK_HTML = """
<html>
  <body>
    <a href="/files/download/71337" title="Pobierz PDF">Pobierz PDF</a>
    <iframe src="/attachments/71337/report.pdf" title="Podgląd PDF"></iframe>
  </body>
</html>
"""


PAP_NOTICE_WITH_SCRIPT_DOWNLOAD_LINK_HTML = """
<html>
  <body>
    <script>
      window.noticeConfig = {"attachment": "/files/download/71999"};
    </script>
  </body>
</html>
"""


@allure.epic("Unit Tests")
@allure.feature("Stock Equity Reports")
@allure.story("Web-source enrichment parses public facts without live network access")
@allure.severity(allure.severity_level.NORMAL)
@allure.tag("reports", "parsing")
@allure.link("https://github.com/Strzelba2/FinancialManager", name="GitHub")
@allure.description(
    "Verifies web-source enrichment without live network access: HTML table parsers "
    "for financial metrics and peer comparisons, PDF text parsers for MAR insider "
    "transaction notices (buy/sell, aggregate and simple layouts), attachment link "
    "extraction, and merge helpers that fill sparse AI payloads from scraped facts."
)
class EquityWebSourceTests(unittest.TestCase):
    def test_latest_metric_from_table_skips_empty_latest_cell(self) -> None:
        table = _ParsedTable(
            headers=["2024/Q2 (cze 24)", "2024/Q3 (wrz 24)"],
            rows=[],
        )
        row = _TableRow(
            data_field="CWK",
            label="Cena / Wartość księgowa",
            values=["0,84", ""],
        )

        metric = _latest_metric_from_table(
            table,
            source_kind="ratio",
            unit="x",
            keys=("CWK",),
        )

        self.assertIsNone(metric)
        metric = _latest_metric_from_table(
            _ParsedTable(headers=table.headers, rows=[row]),
            source_kind="ratio",
            unit="x",
            keys=("CWK",),
        )
        self.assertIsNotNone(metric)
        self.assertEqual(metric.value, 0.84)
        self.assertEqual(metric.as_of, "2024-06-30")

    def test_latest_peer_metric_from_table_skips_empty_latest_cell(self) -> None:
        table = _ParsedTable(
            headers=["2024/Q2 (cze 24)", "2024/Q3 (wrz 24)"],
            rows=[
                _TableRow(
                    data_field="CWK",
                    label="Cena / Wartość księgowa",
                    values=["0,84 ~branża 1,22", ""],
                )
            ],
        )

        metric = _latest_peer_metric_from_table(
            table,
            unit="x",
            keys=("CWK",),
        )

        self.assertIsNotNone(metric)
        self.assertEqual(metric.value, 1.22)
        self.assertEqual(metric.as_of, "2024-06-30")

    def setUp(self) -> None:
        self.client = EquityWebSourceClient()

    def tearDown(self) -> None:
        asyncio.run(self.client.aclose())

    def test_listing_parser_maps_symbol_and_shortname_to_slug(self) -> None:
        mapping = self.client._parse_listing(LISTING_HTML)

        self.assertEqual(mapping["pbx"], "PEKABEX")
        self.assertEqual(mapping["pekabex"], "PEKABEX")

    def test_profile_and_financial_pages_fill_material_metrics(self) -> None:
        facts = EquityWebSourceFacts(slug="PEKABEX")

        self.client._parse_profile_page(facts, PROFILE_HTML)
        self.client._parse_financial_pages(
            facts,
            market_html=MARKET_HTML,
            profitability_html=PROFITABILITY_HTML,
            debt_html=DEBT_HTML,
            liquidity_html=LIQUIDITY_HTML,
            rzis_html=RZIS_HTML,
            balance_html=BALANCE_HTML,
            cashflow_html=CASHFLOW_HTML,
        )
        self.client._parse_dividend_page(facts, DIVIDEND_HTML)
        self.client._parse_shareholders_page(facts, SHAREHOLDERS_HTML)
        self.client._parse_news_page(facts, NEWS_HTML)
        self.client._derive_history(
            facts,
            profitability_html=PROFITABILITY_HTML,
            rzis_html=RZIS_HTML,
            debt_html=DEBT_HTML,
        )

        self.assertEqual(facts.full_name, "Pekabex S.A.")
        self.assertEqual(facts.description, "Producent prefabrykatów betonowych i generalny wykonawca.")
        self.assertEqual(facts.shares_outstanding.value, 24_826_512)
        self.assertEqual(facts.revenue_ttm.value, 1_814_000_000)
        self.assertEqual(facts.ebitda_ttm.value, 145_000_000)
        self.assertEqual(facts.net_income_ttm.value, -4_960_000)
        self.assertEqual(facts.ocf.value, 9_342_000)
        self.assertAlmostEqual(facts.bvps.value, 23.7649, places=4)
        self.assertAlmostEqual(facts.eps_ttm.value, -0.2, places=4)
        self.assertEqual(facts.cash_and_equivalents.value, 110_000_000)
        self.assertEqual(facts.net_debt.value, 242_135_000)
        self.assertEqual(facts.pe_ratio.value, 17.68)
        self.assertEqual(facts.pe_ratio.as_of, "2025-06-30")
        self.assertEqual(facts.ev_ebitda_ratio.value, 18.76)
        self.assertEqual(facts.pb_ratio.value, 0.74)
        self.assertEqual(facts.ps_ratio.value, 0.19)
        self.assertEqual(facts.industry_pe_ratio.value, 13.5)
        self.assertEqual(facts.industry_pe_ratio.as_of, "2025-06-30")
        self.assertEqual(facts.industry_ev_ebitda_ratio.value, 5.08)
        self.assertEqual(facts.industry_pb_ratio.value, 1.33)
        self.assertEqual(facts.industry_ps_ratio.value, 0.59)
        self.assertEqual(facts.roe.value, -1.85)
        self.assertEqual(facts.roic.value, 0.66)
        self.assertEqual(facts.current_ratio.value, 1.6)
        self.assertEqual(facts.quick_ratio.value, 1.2)
        self.assertEqual(facts.interest_coverage.value, 8.1)
        self.assertEqual(facts.payout_ratio.value, 47.0)
        self.assertEqual(len(facts.dividend_history), 2)
        self.assertEqual(facts.dividend_history[-1].pay_date, "2025-07-21")
        self.assertEqual(len(facts.major_shareholders), 2)
        self.assertEqual(facts.major_shareholders[0].name, "STE sp. z o.o. wraz z PWM")
        self.assertEqual(facts.trend_history[-1].year, 2025)
        self.assertEqual(facts.trend_history[-1].revenue, 1814.0)
        self.assertLess(facts.trend_history[-1].eps, 0)
        self.assertEqual(facts.trend_history[0].roe_pct, 12.4)
        self.assertEqual(facts.trend_history[0].net_debt_ebitda, 1.0)
        self.assertEqual(facts.trend_history[1].roe_pct, 13.8)
        self.assertEqual(facts.trend_history[1].net_debt_ebitda, 0.8)
        self.assertEqual(facts.trend_history[-1].net_debt_ebitda, 7.39)
        self.assertEqual(len(facts.news_events), 3)
        self.assertEqual(facts.news_events[0].date, "2026-04-22")
        self.assertEqual(facts.news_events[1].polarity, "positive")
        self.assertEqual(facts.news_events[2].polarity, "negative")
        self.assertEqual(facts.upcoming_dates[0].date, "2026-04-30")

    def test_parse_mar_pdf_text_to_insider_transaction(self) -> None:
        transaction = _parse_insider_transaction_from_text(
            INSIDER_PDF_TEXT,
            fallback_title="PEKABEX - Nabycie akcji emitenta przez osobę blisko związaną",
        )

        self.assertIsNotNone(transaction)
        assert transaction is not None
        self.assertEqual(transaction.date, "2026-03-31")
        self.assertEqual(transaction.insider, "STE spółka z ograniczoną odpowiedzialnością")
        self.assertEqual(transaction.transaction_type, "buy")
        self.assertEqual(transaction.shares, 125_000)
        self.assertEqual(transaction.currency, "PLN")
        self.assertAlmostEqual(transaction.value, 1_373_417.96)
        self.assertAlmostEqual(transaction.price, 10.9873)

    def test_parse_mar_pdf_text_to_sell_transaction_from_aggregate_section(self) -> None:
        transaction = _parse_insider_transaction_from_text(
            INSIDER_SELL_PDF_TEXT,
            fallback_title="PEKABEX - Zbycie akcji emitenta przez osobę blisko związaną",
        )

        self.assertIsNotNone(transaction)
        assert transaction is not None
        self.assertEqual(transaction.date, "2026-02-04")
        self.assertEqual(transaction.transaction_type, "sell")
        self.assertEqual(transaction.shares, 4_800)
        self.assertEqual(transaction.currency, "PLN")
        self.assertAlmostEqual(transaction.price, 10.22)
        self.assertAlmostEqual(transaction.value, 49_056.0)

    def test_parse_mar_pdf_text_to_sell_transaction_from_simple_notice_layout(self) -> None:
        transaction = _parse_insider_transaction_from_text(
            INSIDER_SELL_SIMPLE_PDF_TEXT,
            fallback_title="PEKABEX - Zbycie akcji emitenta przez osobę blisko związaną",
        )

        self.assertIsNotNone(transaction)
        assert transaction is not None
        self.assertEqual(transaction.date, "2026-02-03")
        self.assertEqual(transaction.insider, "Fernik Holdings ltd.")
        self.assertEqual(
            transaction.role,
            "Osoba blisko związana z Robert Jędrzejowski, Prezes Zarządu",
        )
        self.assertEqual(transaction.transaction_type, "sell")
        self.assertEqual(transaction.shares, 20_000)
        self.assertEqual(transaction.currency, "PLN")
        self.assertAlmostEqual(transaction.price, 12.4)
        self.assertAlmostEqual(transaction.value, 248_000.0)

    def test_extract_attachment_links_accepts_download_links_marked_as_pdf(self) -> None:
        links = _extract_attachment_links(
            PAP_NOTICE_WITH_DOWNLOAD_LINK_HTML,
            "https://espiebi.pap.pl/node/714669",
        )

        self.assertEqual(
            links,
            [
                "https://espiebi.pap.pl/files/download/71337",
                "https://espiebi.pap.pl/attachments/71337/report.pdf",
            ],
        )

    def test_extract_attachment_links_accepts_script_embedded_download_links(self) -> None:
        links = _extract_attachment_links(
            PAP_NOTICE_WITH_SCRIPT_DOWNLOAD_LINK_HTML,
            "https://espiebi.pap.pl/node/714669",
        )

        self.assertEqual(
            links,
            ["https://espiebi.pap.pl/files/download/71999"],
        )

    def test_notice_text_fallback_can_parse_sell_transaction_from_html(self) -> None:
        html = f"<html><body><article><pre>{INSIDER_SELL_PDF_TEXT}</pre></article></body></html>"

        notice_text = _extract_notice_text_from_html(html)
        self.assertIsNotNone(notice_text)
        transaction = _parse_insider_transaction_from_text(
            notice_text or "",
            fallback_title="PEKABEX - Zbycie akcji emitenta przez osobę blisko związaną",
        )

        self.assertIsNotNone(transaction)
        assert transaction is not None
        self.assertEqual(transaction.date, "2026-02-04")
        self.assertEqual(transaction.transaction_type, "sell")
        self.assertEqual(transaction.shares, 4_800)

    def test_merge_web_source_facts_fills_sparse_ai_payload(self) -> None:
        ai_payload_data = copy.deepcopy(make_ai_payload().model_dump(mode="json"))
        ai_payload_data["company"]["shares_outstanding"]["value"] = None
        ai_payload_data["fundamentals"]["revenue_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["ebitda_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["net_income_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["eps_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["ocf"]["value"] = None
        ai_payload_data["fundamentals"]["fcf"]["value"] = None
        ai_payload_data["fundamentals"]["bvps"]["value"] = None
        ai_payload_data["debt_balance"]["cash_and_equivalents"]["value"] = None
        ai_payload_data["debt_balance"]["net_debt"]["value"] = None
        ai_payload_data["debt_balance"]["current_ratio"]["value"] = None
        ai_payload_data["debt_balance"]["quick_ratio"]["value"] = None
        ai_payload_data["debt_balance"]["total_assets"]["value"] = None
        ai_payload_data["debt_balance"]["equity"]["value"] = None
        ai_payload_data["dividend"]["history"] = [{"year": 2024, "dividend_per_share": None, "yield_pct": None, "payout_ratio_pct": None, "paid": False}]
        ai_payload_data["trend_condition"]["history"] = [
            {
                "year": 2024,
                "revenue": None,
                "ebitda": None,
                "ebitda_margin_pct": None,
                "net_income": None,
                "eps": None,
                "roe_pct": None,
                "net_debt_ebitda": None,
                "dividend_per_share": None,
                "direction": "flat",
            }
        ]
        ai_payload_data["shareholders"]["major_shareholders"] = []

        facts = EquityWebSourceFacts(slug="PEKABEX")
        self.client._parse_profile_page(facts, PROFILE_HTML)
        self.client._parse_financial_pages(
            facts,
            market_html=MARKET_HTML,
            profitability_html=PROFITABILITY_HTML,
            debt_html=DEBT_HTML,
            liquidity_html=LIQUIDITY_HTML,
            rzis_html=RZIS_HTML,
            balance_html=BALANCE_HTML,
            cashflow_html=CASHFLOW_HTML,
        )
        self.client._parse_dividend_page(facts, DIVIDEND_HTML)
        self.client._parse_shareholders_page(facts, SHAREHOLDERS_HTML)
        self.client._parse_news_page(facts, NEWS_HTML)
        self.client._derive_history(
            facts,
            profitability_html=PROFITABILITY_HTML,
            rzis_html=RZIS_HTML,
            debt_html=DEBT_HTML,
        )
        insider_transaction = _parse_insider_transaction_from_text(
            INSIDER_PDF_TEXT,
            fallback_title="PEKABEX - Nabycie akcji emitenta przez osobę blisko związaną",
        )
        assert insider_transaction is not None
        insider_transaction.source_url = "https://espiebi.pap.pl/files/download/71337"
        facts.insider_transactions = [insider_transaction]

        merged = merge_web_source_facts(EquityAiPayload.model_validate(ai_payload_data), facts)

        self.assertEqual(merged.company.shares_outstanding.value, 24_826_512)
        self.assertEqual(merged.fundamentals.revenue_ttm.value, 1_814_000_000)
        self.assertEqual(merged.fundamentals.net_income_ttm.value, -4_960_000)
        self.assertEqual(merged.fundamentals.ocf.value, 9_342_000)
        self.assertAlmostEqual(merged.fundamentals.bvps.value, 23.7649, places=4)
        self.assertLess(merged.fundamentals.eps_ttm.value, 0)
        self.assertEqual(merged.dividend.history[-1].dividend_per_share, 1.4)
        self.assertEqual(merged.shareholders.major_shareholders[0].stake_pct, 38.1)
        self.assertEqual(merged.shareholders.free_float_pct.value, 54.7)
        self.assertEqual(merged.shareholders.institutional_ownership_pct.value, 7.2)
        self.assertEqual(merged.shareholders.insider_transactions[0].type, "buy")
        self.assertEqual(
            merged.shareholders.insider_transactions[0].source_url,
            "https://espiebi.pap.pl/files/download/71337",
        )
        self.assertEqual(merged.trend_condition.history[-1].year, 2025)
        self.assertEqual(merged.trend_condition.history[-1].revenue, 1814.0)
        self.assertTrue(merged.key_events.positive)
        self.assertTrue(merged.key_events.negative)
        self.assertTrue(merged.key_events.upcoming_dates)
        prompt_facts = facts.to_prompt_dict()
        self.assertEqual(prompt_facts["valuation_benchmarks"]["industry_pb_ratio"]["value"], 1.33)
        self.assertEqual(prompt_facts["valuation_benchmarks"]["industry_ps_ratio"]["value"], 0.59)
        self.assertEqual(prompt_facts["fundamentals"]["ocf"]["value"], 9_342_000)
        self.assertAlmostEqual(prompt_facts["fundamentals"]["bvps"]["value"], 23.7649, places=4)
        self.assertEqual(prompt_facts["valuation_anchors"]["peer_pb_implied_price"]["value"], 31.61)
        self.assertEqual(prompt_facts["valuation_anchors"]["peer_ps_implied_price"]["value"], 43.11)
        self.assertEqual(prompt_facts["valuation_anchors"]["peer_ev_ebitda_implied_price"]["value"], 19.92)

    def test_merge_web_source_report_metrics_overrides_market_ratios(self) -> None:
        facts = EquityWebSourceFacts(slug="PEKABEX")
        self.client._parse_financial_pages(
            facts,
            market_html=MARKET_HTML,
            profitability_html=None,
            debt_html=None,
            liquidity_html=None,
            rzis_html=None,
            balance_html=None,
            cashflow_html=None,
        )
        report, _ = build_equity_report(
            ai_payload=make_ai_payload(),
            mic="XWAR",
            symbol="PBX",
            currency="PLN",
            instrument_shortname="PEKABEX",
            instrument_name="Pekabex S.A.",
            instrument_isin="PLPKBEX00072",
            current_price=10.88,
            change_1d_pct=0.0,
            last_trade_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            candles=make_candles(),
            period="2026-Q1",
            model="gpt-5.4",
            final_generated_at=datetime(2026, 4, 21, 9, 5, tzinfo=timezone.utc),
            valid_until=date(2026, 7, 20),
        )

        merged_report = merge_web_source_report_metrics(report, facts)

        self.assertEqual(merged_report.fundamentals.pe_ratio.value, 17.68)
        self.assertEqual(merged_report.fundamentals.pe_ratio.as_of, "2025-06-30")
        self.assertEqual(merged_report.fundamentals.pe_ratio.source, "manual")
        self.assertEqual(merged_report.fundamentals.ev_ebitda.value, 18.76)
        self.assertEqual(merged_report.fundamentals.pb_ratio.value, 0.74)
        self.assertEqual(merged_report.fundamentals.ps_ratio.value, 0.19)

    def test_enrichment_helpers_detect_sparse_payloads_and_reports(self) -> None:
        ai_payload_data = copy.deepcopy(make_ai_payload().model_dump(mode="json"))
        ai_payload_data["fundamentals"]["revenue_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["ebitda_ttm"]["value"] = None
        ai_payload_data["fundamentals"]["net_income_ttm"]["value"] = None
        ai_payload_data["debt_balance"]["cash_and_equivalents"]["value"] = None
        ai_payload_data["debt_balance"]["total_assets"]["value"] = None
        ai_payload_data["shareholders"]["major_shareholders"] = []
        ai_payload_data["dividend"]["history"] = []
        ai_payload_data["trend_condition"]["history"] = []

        self.assertTrue(report_payload_needs_enrichment(ai_payload_data))

        report, _ = build_equity_report(
            ai_payload=make_ai_payload(),
            mic="XWAR",
            symbol="PBX",
            currency="PLN",
            instrument_shortname="PEKABEX",
            instrument_name="Pekabex S.A.",
            instrument_isin="PLPKBEX00072",
            current_price=10.88,
            change_1d_pct=0.0,
            last_trade_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            candles=make_candles(),
            period="2026-Q1",
            model="gpt-5.4",
            final_generated_at=datetime(2026, 4, 21, 9, 5, tzinfo=timezone.utc),
            valid_until=date(2026, 7, 20),
        )
        self.assertTrue(final_report_payload_needs_enrichment(report.model_dump(mode="json")))


if __name__ == "__main__": 
    unittest.main()
