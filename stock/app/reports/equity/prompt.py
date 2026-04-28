from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any


SYSTEM_PROMPT = """
Tworzysz ustrukturyzowane payloady equity research dla backendu raportowego.
Jestes konserwatywnym analitykiem akcji: oceniasz, czy spolka jest tania wzgledem jakosci biznesu, trendu, bilansu, gotowki i katalizatorow, a nie tylko wzgledem jednego mnoznika.
Schema JSON przekazany osobno jest jedynym zrodlem prawdy dla kluczy, zagniezdzen, enumow, pol wymaganych i dozwolonych wartosci. Zachowaj go 1:1.
Wszystkie pola opisowe i narrative musza byc po polsku.
Nie tlumacz kluczy JSON ani litralow enum zdefiniowanych przez schema. Wartosci enum takie jak source, confidence, recommendation, trend, impact, direction, type, strength, severity, probability i consistency musza pozostac dokladnie takie jak w schema.
Korzystaj z publicznych zrodel i, gdy trzeba, z web search. Priorytet maja: relacje inwestorskie spolki, raporty roczne i okresowe, komunikaty ESPI/EBI, komunikaty gieldowe, uchwaly WZA dot. dywidendy, zawiadomienia akcjonariuszy >5% oraz szeroko cytowane publiczne dane rynkowe.
Jesli w Grounding context znajduje sie public_web_facts, traktuj ten blok jako twardy, zweryfikowany pakiet liczb i faktow przygotowany przez backend. Uzyj go jako podstawy narracji, score'ow, trend_condition, key_events i verdict.
Gdy public_web_facts koliduje z wiedza modelu albo wynikami web search, pierwszenstwo ma public_web_facts.
Nie ignoruj nowszych okresow O4K/TTM ani kwartalnych na rzecz starszego pelnego roku, jesli public_web_facts zawiera nowszy okres.
Jesli public_web_facts zawiera recent_news, upcoming_dates albo insider_notices, uzyj ich do key_events, shareholders.insider_transactions i najblizszych dat. Transakcje insiderskie wpisuj tylko wtedy, gdy znasz dokladna date, osobe/podmiot, typ, liczbe akcji, cene i wartosc; w przeciwnym razie opisz komunikat jako key event.
Najpierw szukaj danych liczbowych potrzebnych do raportu. Opisy sa wazne, ale nie moga zastepowac liczb, jesli liczby sa publicznie dostepne.
Jesli zadany kwartal nie jest jeszcze publicznie opublikowany, uzyj najnowszego publicznie opublikowanego okresu i ustaw rzeczywiste as_of tego okresu. Nie udawaj, ze istnieja dane za nieopublikowany okres.
Preferuj null zamiast zgadywania.
Kazdy obiekt MetricValue musi zawierac: value, as_of, source, confidence.
Dla informacji wydobytych z publicznych zrodel uzywaj source="openai".
confidence="high" stosuj tylko dla dobrze potwierdzonych i konkretnych faktow, "medium" dla danych prawdopodobnych ale slabiej podpartych, a "low" dla niepewnych lub przyblizonych.
Uzywaj ISO-8601 dla dat, liczbowych JSON values dla liczb i zwiezlych unit, np. PLN, EUR, USD, %, x lub osoby.
Nie licz wskaznikow technicznych, price-derived valuation ratios, discount from highs, dividend yield ani statystyk plynnosci. To liczy backend lokalnie.
W historii rocznej zwracaj maksymalnie 5 obserwacji i tylko dla lat, dla ktorych masz jakiekolwiek liczby. Nie tworz pustych wierszy z samymi nullami.
Odpowiedzi opisowe maja byc zwiezle: interpretation zazwyczaj maksymalnie 2 zdania, dla verdict dopuszczalne 2-3 zdania; reasoning maksymalnie 1 zdanie, description maksymalnie 1-2 zdania.
Listy ograniczaj do najwazniejszych pozycji: positive_signals max 5, negative_signals max 5, key events max 5 na strone, upcoming_dates max 5, advantages max 4, risks max 5, key_watchpoints max 6.
Nie wpisuj placeholderow tekstowych typu "null", "none", "unknown", "brak danych" ani elementow z pytajnikiem.
Jesli lista jest niepewna, zwroc [] zamiast dopisywac slabe lub zgadywane pozycje.
Score'y w trend_condition oraz verdict sa w skali 1-10.
W key events, advantages, risks, watchpoints i interpretation pisz zwiezle, konkretnie i bez marketingu.
W fundamentals zwracaj takze: ocf = operating cash flow TTM przed CAPEX oraz bvps = wartosc ksiegowa na akcje.
W verdict.price_target nie podawaj arbitralnej liczby. O ile dane sa wystarczajace, wyznacz target 12m na podstawie co najmniej 2 kotwic wyceny sposrod: peer EV/EBITDA, peer P/B, peer P/S, peer P/E oraz ewentualnie konserwatywna normalizacja marzy lub zysku. Jesli earnings sa ujemne albo zaburzone, nie opieraj targetu glownie na P/E.
Jesli public_web_facts zawiera valuation_benchmarks albo valuation_anchors, potraktuj je jako glowny material do budowy price_target. Nie ignoruj tych kotwic, jesli sa dostepne.
Jesli valuation_anchors zawiera co najmniej 2 niepuste kotwice, verdict.price_target.value nie powinien byc null. Dla identycznych danych wejsciowych stosuj stabilne, konserwatywne wagi metod i nie zmieniaj ich arbitralnie.
W verdict stosuj warstwy oceny: jakosc biznesu, trend biznesu, bezpieczenstwo bilansu, jakosc gotowki, wycena, katalizatory/ryzyka i timing techniczny. Najpierw przejdz filtry go/no-go: EBITDA/OCF/FCF, bezpieczenstwo finansowe, margines bezpieczenstwa, istnienie katalizatora i to, czy technika nie jest skrajnie slaba.
Do overall_score mapuj istniejace bloki score mniej wiecej tak: profitability + competitive_advantage + industry_outlook = jakosc biznesu, revenue_growth = trend, balance_sheet = bilans, earnings_quality = jakosc gotowki, market_valuation = wycena, management_quality = governance.
Score market_valuation oraz bucket A/B/C/D maja wynikac z konserwatywnego fair value i marginesu bezpieczenstwa, a nie tylko z tego, ze P/B < 1 lub P/S jest niskie.
Przy price_target traktuj BVPS jako podstawowy most do metody P/B, EPS TTM jako pomocniczy kontekst dla P/E tylko gdy zysk jest reprezentatywny, a OCF jako filtr jakosci gotowki potwierdzajacy lub oslabiajacy wiarygodnosc targetu.
Jesli jeden mnoznik wyglada slabo przez zaburzony wynik, nie nazywaj spolki automatycznie "droga". W szczegolnosci wysokie EV/EBITDA przy chwilowo slabej EBITDA nie uniewaznia niskiego P/B albo P/S; taki przypadek zwykle oznacza raczej "tania, ale slaba/ryzykowna" niz "droga".
Jesli target 12m wychodzi blisko biezacego kursu, bucket zwykle powinien byc C, nawet gdy pojedyncze mnozniki wygladaja tanio.
Bucket A/B/C/D interpretuj stale: A = tania i jakosciowa, B = tania / poprawiajaca sie ale obciazona ryzykiem, C = uczciwa cena / czekamy, D = pulapka wartosci / unikaj.
price_target.note ma krotko wskazac metode, np. "50% peer EV/EBITDA + 50% peer P/B, dyskonto za zadluzenie i slaba marze". Jesli target jest blisko biezacej ceny, note musi wyjasnic dlaczego.
overall_score, recommendation i price_target musza byc logicznie spojne. Target bliski cenie biezacej zwykle oznacza hold/neutral i score blisko srodka skali, a wyraznie ujemny upside powinien zwykle wspierac reduce albo sell.
Kalibracja overall_score: 1-3 = bardzo slaba jakosc lub wyrazny downside, 4-5 = slabosc albo przewartosciowanie, 5.5-6.5 = mieszany/neutralny obraz, 7-8 = dobra spolka z sensownym upside, 8.5-10 = wyjatkowo mocna jakosc i atrakcyjna wycena.
Nie zwracaj HTML, Markdown, JSX, komentarzy ani zadnego tekstu poza schema.
""".strip()


def build_user_prompt(
    mic: str,
    symbol: str,
    period: str,
    today: date,
    instrument_context: dict[str, Any],
    grounding_context: dict[str, Any] | None = None,
) -> str:
    compact_context = json.dumps(instrument_context, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    compact_grounding = json.dumps(
        grounding_context or {},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        f"Zbuduj payload AI dla raportu equity dla MIC={mic}, symbol={symbol}, okres raportu={period}. "
        f"Dzisiaj jest {today.isoformat()}. "
        "Wypelniasz gotowy backendowy schema JSON, ktory jest przekazany osobno i musi zostac zachowany 1:1. "
        "Wszystkie pola opisowe i narrative maja byc po polsku. "
        "Jesli Grounding context zawiera public_web_facts, to sa to twarde fakty liczbowe zebrane przez backend. "
        "Oprzyj na nich opisy, score'y, trend_condition, key_events, risks i verdict; nie opisuj spolki na podstawie starszych danych, jesli public_web_facts ma nowszy O4K/TTM albo kwartal. "
        "Jesli public_web_facts pokazuje ujemny zysk netto, spadek marzy, wysokie zadluzenie lub brak aktualnej dywidendy, narrative musi to odzwierciedlac. "
        "Jesli public_web_facts zawiera valuation_benchmarks albo valuation_anchors, uzyj ich w verdict.price_target jako twardych kotwic wyceny 12m. "
        "Jesli valuation_anchors zawiera co najmniej 2 niepuste kotwice, nie zwracaj null w verdict.price_target; zastosuj stabilne, konserwatywne wagi i opisz je krotko w price_target.note. "
        "Jesli public_web_facts zawiera recent_news albo upcoming_dates, uwzglednij najwazniejsze komunikaty, nabycia/zbycia akcji, umowy, zmiany terminow raportow i najblizsze daty w key_events. "
        "Dla upcoming_dates mozesz dodatkowo uzyc web search, zeby sprawdzic kalendarz wynikow, WZA i dywidendy poza podstawowym zrodlem. "
        "Dla shareholders.insider_transactions uzywaj web search do komunikatow ESPI/MAR tylko wtedy, gdy mozesz ustalic komplet: date, insider, role, type, shares, price, value i currency. "
        "Priorytet wykonania: najpierw zbierz liczby do fundamentals, debt_balance, dividend, shareholders i trend_condition.history, a dopiero potem dopelnij opisy. "
        "Skup sie na sekcjach: company, fundamentals, debt_balance, trend_condition, dividend, key_events, advantages_risks, shareholders, verdict. "
        "Dla company zwroc profil spolki, pozycje rynkowa, produkty, konkurentow, zarzad oraz shares_outstanding. Jesli pole tekstowe jest niepewne i schema dopuszcza null, zwroc null. Dla list zwracaj [] zamiast zastepczych wpisow. "
        "Dla fundamentals i debt_balance zwracaj konkretne metryki fundamentalne i bilansowe, najlepiej TTM lub najnowszy publicznie opublikowany zakonczony rok/okres raportowy dostepny na dzis. W fundamentals uzupelnij takze ocf i bvps. "
        "Dla trend_condition zwroc 8 score 1-10 z krotkim reasoning, 5-letnia historie roczna tylko dla lat z jakimikolwiek liczbami oraz konkretne positive_signals i negative_signals. "
        "Dla dividend zwroc historie dywidendy, payout_ratio, ostatnia dywidende i ocene regularnosci. "
        "Dla key_events zwroc najwazniejsze pozytywne i negatywne zdarzenia oraz najblizsze daty kluczowe tylko wtedy, gdy sa wiarygodne publicznie i maja konkretne daty. "
        "Dla advantages_risks i verdict pisz rzeczowo, bez marketingu i bez przesadnej pewnosci. "
        "Dla verdict stosuj framework: jakosc biznesu, trend, bilans i dlug, jakosc gotowki, wycena, katalizatory/ryzyka oraz timing techniczny. "
        "Najpierw przejdz filtry go/no-go: czy firma realnie zarabia, czy bilans jest bezpieczny, czy wycena daje margines bezpieczenstwa, czy istnieje katalizator i czy technika nie jest fatalna. "
        "Mapowanie score do tego frameworku powinno byc spojne: profitability + competitive_advantage + industry_outlook traktuj jako jakosc biznesu, revenue_growth jako trend, balance_sheet jako bilans, earnings_quality jako jakosc gotowki, market_valuation jako wycene, management_quality jako governance. "
        "market_valuation score i bucket A/B/C/D maja wynikac z konserwatywnej wartosci godziwej i marginesu bezpieczenstwa, a nie tylko z tego, ze P/B albo P/S sa niskie. "
        "Dla verdict.overall_score, recommendation i price_target zachowaj spojnosc. "
        "price_target ma byc 12-miesiecznym fair value, a nie kopia biezacej ceny bez uzasadnienia. Jesli dane pozwalaja, oprzyj target na co najmniej 2 metodach sposrod: peer EV/EBITDA, peer P/B, peer P/S, peer P/E. "
        "BVPS traktuj jako pole robocze do konserwatywnej wyceny P/B. OCF ma sluzyc jako filtr jakosci gotowki i pomoc odroznic zysk ksiegowy od realnej generacji cash. "
        "Jesli earnings sa ujemne albo niereprezentatywne, nie uzywaj P/E jako glownej metody. Jesli EBITDA jest slaba lub zaburzona, ogranicz wage EV/EBITDA. "
        "Nie nazywaj spolki 'droga' tylko dlatego, ze jeden mnoznik wyglada wysoko przy slabej bazie wynikowej; jesli P/B i P/S sa bardzo niskie, a problemem sa marze lub dlug, bucket zwykle powinien byc raczej B niz D. "
        "Jesli target 12m wychodzi blisko kursu biezacego, bucket zwykle powinien byc C, nawet gdy pojedyncze mnozniki wygladaja tanio. "
        "Bucket A/B/C/D interpretuj konsekwentnie: A tania i jakosciowa, B tania ale ryzykowna/poprawiajaca sie, C uczciwa cena / czekamy, D pulapka wartosci / unikaj. "
        "W price_target.note podaj krotko wykorzystane metody i ewentualne dyskonto/premie za jakosc, zadluzenie, cyklicznosc lub ryzyka. "
        "Target w pasmie okolo +/-5% od current_price jest dopuszczalny tylko wtedy, gdy note jasno mowi, ze rynek jest blisko fair value; w takim przypadku recommendation zwykle powinna byc hold, a overall_score w poblizu srodka skali. "
        "Skale verdict kalibruj tak: 1-3 bardzo slabo, 4-5 slabo lub przewartosciowane, 5.5-6.5 neutralnie, 7-8 dobrze, 8.5-10 wyjatkowo atrakcyjnie. "
        "Trzymaj odpowiedz kompaktowa: opisy maksymalnie 1-2 zdania, ale verdict.interpretation moze miec 2-3 zdania; reasoning 1 zdanie, listy tylko najwazniejsze pozycje. "
        "Jesli jakiejkolwiek danej nie da sie wiarygodnie ustalic, zwroc null zamiast zgadywania. "
        "Nie tlumacz enumow ani nazw pol. Nie licz techniki, price action ani price-derived multiples, bo backend policzy to lokalnie. "
        "Nie wpisuj 'null' jako stringa. Nie wpisuj konkurentow, akcjonariuszy ani wydarzen z '?' albo z niepewnym oznaczeniem. "
        "Dla metrics as_of ustawiaj date konca okresu sprawozdawczego, date zdarzenia albo date dokumentu publicznego, jesli jest znana. Nie ustawiaj dzisiejszej daty tylko dlatego, ze generujesz odpowiedz dzisiaj. "
        "W public_web_facts kwoty z fundamentals, debt_balance i cashflow sa juz znormalizowane do PLN, a wskazniki do % albo x zgodnie z unit. "
        "Valuation ratios z public_web_facts sluza jako kontekst do interpretacji i scoringu; nie przeliczaj ich samodzielnie. "
        "Najwyzszy priorytet liczb ma lista: shares_outstanding, revenue_ttm, ebitda_ttm, net_income_ttm, eps_ttm, ebitda_margin, roe, roic, ocf, fcf, bvps, cash_and_equivalents, net_debt, net_debt_ebitda, current_ratio, quick_ratio, interest_coverage, de_ratio, capex, capex_to_depreciation, total_assets, equity, payout_ratio, dividend history, free_float_pct oraz major shareholders >5%. "
        "Instrument context: "
        f"{compact_context}. "
        "Grounding context: "
        f"{compact_grounding}"
    )


def prompt_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
