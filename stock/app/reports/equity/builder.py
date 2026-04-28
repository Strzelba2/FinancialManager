from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from .ai_schema import EquityAiPayload
from .local_metrics import (
    aggregate_candles_weekly,
    bollinger,
    closes,
    compute_52w_range,
    determine_trend,
    detect_anomalous_sessions,
    dividend_growth_cagr,
    iso_date,
    latest_positive_dividend_amount,
    liquidity_score,
    macd,
    min_confidence,
    obv_state,
    rsi,
    safe_percent,
    safe_ratio,
    sma,
    sort_candles,
    stoch_rsi,
    support_resistance,
    to_float,
    ytd_change_pct,
)
from .schemas import (
    CompanyInfo,
    DebtBalance,
    Dividend,
    EquityReport,
    Fundamentals,
    MetricValue,
    Recommendation,
    ReportMeta,
    Technical,
    ValuationMatrix,
    Verdict,
    VolumeAndLiquidity,
)


def _dt_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _metric(
    value: Any,
    as_of: date | datetime | str,
    source: str,
    confidence: str,
    unit: str | None = None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(
        value=value,
        as_of=iso_date(as_of) if isinstance(as_of, date) and not isinstance(as_of, datetime) else (as_of.isoformat(timespec="seconds") if isinstance(as_of, datetime) else str(as_of)),
        source=source,
        confidence=confidence,
        unit=unit,
        note=note,
    )


def _price_vs_level(price: float, level: float | None) -> str:
    if level is None:
        return "above"
    return "above" if price >= level else "below"


def _text_or_default(value: str | None, default: str = "") -> str:
    return value if value is not None else default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _mean(values: Sequence[float | None], default: float = 5.0) -> float:
    filtered = [float(item) for item in values if item is not None]
    if not filtered:
        return default
    return sum(filtered) / len(filtered)


def _valuation_score(
    pb_ratio: float | None,
    ps_ratio: float | None,
    pe_ratio: float | None,
    ev_ebitda: float | None,
    fcf_yield: float | None,
) -> float:
    signals: list[float] = []

    if pb_ratio is not None:
        if pb_ratio <= 0.8:
            signals.append(1.0)
        elif pb_ratio <= 1.2:
            signals.append(0.5)
        elif pb_ratio >= 3.0:
            signals.append(-1.0)
        elif pb_ratio >= 2.0:
            signals.append(-0.5)
        else:
            signals.append(0.0)

    if ps_ratio is not None:
        if ps_ratio <= 0.5:
            signals.append(1.0)
        elif ps_ratio <= 0.9:
            signals.append(0.5)
        elif ps_ratio >= 2.0:
            signals.append(-1.0)
        elif ps_ratio >= 1.2:
            signals.append(-0.5)
        else:
            signals.append(0.0)

    if pe_ratio is not None:
        if pe_ratio <= 10.0:
            signals.append(1.0)
        elif pe_ratio <= 15.0:
            signals.append(0.5)
        elif pe_ratio >= 30.0:
            signals.append(-1.0)
        elif pe_ratio >= 20.0:
            signals.append(-0.5)
        else:
            signals.append(0.0)

    if ev_ebitda is not None:
        if ev_ebitda <= 6.0:
            signals.append(1.0)
        elif ev_ebitda <= 8.0:
            signals.append(0.5)
        elif ev_ebitda >= 16.0:
            signals.append(-1.0)
        elif ev_ebitda >= 12.0:
            signals.append(-0.5)
        else:
            signals.append(0.0)

    if fcf_yield is not None:
        if fcf_yield >= 8.0:
            signals.append(0.5)
        elif fcf_yield >= 5.0:
            signals.append(0.25)
        elif fcf_yield <= 0.0:
            signals.append(-1.0)
        elif fcf_yield <= 2.0:
            signals.append(-0.5)
        else:
            signals.append(0.0)

    if not signals:
        return 5.0
    return round(_clamp(5.5 + (_mean(signals, default=0.0) * 2.2), 1.0, 10.0), 1)


def _quadrant_from_scores(
    valuation_score: float,
    condition_score: float,
    upside_pct: float | None,
    has_price_target: bool,
    pb_ratio: float | None,
    ps_ratio: float | None,
) -> str:
    ratio_discount = (
        valuation_score >= 5.8
        or (pb_ratio is not None and pb_ratio <= 1.0)
        or (ps_ratio is not None and ps_ratio <= 0.6)
    )
    if has_price_target and upside_pct is not None:
        cheap = upside_pct >= 15.0 or (upside_pct >= 8.0 and ratio_discount)
    else:
        cheap = ratio_discount
    healthy = condition_score >= 6.0
    if cheap and healthy:
        return "A"
    if cheap:
        return "B"
    if healthy:
        return "C"
    return "D"


def _recommendation_from_context(
    overall_score: float,
    upside_pct: float,
    valuation_quadrant: str,
    trend: str,
) -> Recommendation:
    if upside_pct >= 25.0 and overall_score >= 7.8:
        return "strong_buy"
    if upside_pct >= 12.0 and overall_score >= 6.4:
        return "buy"
    if upside_pct <= -20.0 and overall_score <= 4.0:
        return "sell"
    if upside_pct <= -8.0:
        return "reduce"
    if abs(upside_pct) <= 5.0:
        if overall_score <= 4.0 and trend == "bearish":
            return "reduce"
        return "hold"
    if valuation_quadrant == "A" and overall_score >= 7.0 and trend != "bearish":
        return "buy"
    if valuation_quadrant == "D" and overall_score <= 4.5:
        return "reduce"
    return "hold"


def _default_valuation_matrix(
    current_quadrant: str,
    momentum_signal: str,
    momentum_label: str,
    momentum_reasoning: str,
) -> ValuationMatrix:
    return ValuationMatrix(
        current_quadrant=current_quadrant,
        quadrants=ValuationMatrix.Quadrants(
            A=ValuationMatrix.Quadrant(
                title="Tania i jakosciowa",
                description="Wycena daje margines bezpieczenstwa, a biznes, bilans i gotowka wspieraja teze inwestycyjna.",
            ),
            B=ValuationMatrix.Quadrant(
                title="Tania / poprawiajaca sie",
                description="Cena wyglada atrakcyjnie, ale marze, cash flow, bilans albo katalizator nadal wymagaja potwierdzenia.",
            ),
            C=ValuationMatrix.Quadrant(
                title="Uczciwa cena / czekamy",
                description="Spolka moze byc solidna, ale kurs jest blisko konserwatywnie szacowanej wartosci godziwej albo brakuje potwierdzenia.",
            ),
            D=ValuationMatrix.Quadrant(
                title="Pulapka wartosci / unikaj",
                description="Slabsza kondycja nie jest dzis rekompensowana wystarczajacym marginesem bezpieczenstwa.",
            ),
        ),
        momentum=ValuationMatrix.Momentum(
            signal=momentum_signal,
            label=momentum_label,
            reasoning=momentum_reasoning,
        ),
    )


def _momentum_context(
    overall_score: float,
    upside_pct: float,
    trend: str,
    macd_signal: str,
    current_quadrant: str,
) -> tuple[str, str, str]:
    if current_quadrant == "A" and overall_score >= 7.0 and upside_pct >= 12.0 and trend == "bullish" and macd_signal == "bullish":
        return "buy_now", "Kup teraz", "Fundamenty i technika sa jednoczesnie wspierajace, wiec timing wejscia wyglada korzystnie."
    if current_quadrant in {"A", "B"} and overall_score >= 5.8 and upside_pct >= 8.0 and trend != "bearish":
        return "accumulate", "Akumuluj", "Wycena pozostaje wspierajaca, ale wejscie lepiej budowac stopniowo."
    if current_quadrant == "D" or upside_pct <= -8.0:
        return "avoid", "Unikaj", "Slaba kondycja albo ujemny margines bezpieczenstwa nie daja obecnie dobrego punktu wejscia."
    if current_quadrant == "C" and upside_pct <= 0.0:
        return "too_expensive", "Za drogo na pospiech", "Jakosc moze byc akceptowalna, ale biezaca relacja ceny do potencjalu nie premiuje agresywnego wejscia."
    return "wait", "Czekaj na potwierdzenie", "Fundamenty moga byc akceptowalne, ale potrzeba mocniejszego sygnalu z wynikow albo z wykresu."


def _verdict_interpretation(
    valuation_quadrant: str,
    recommendation: Recommendation,
    overall_score: float,
    upside_pct: float,
    pb_ratio: float | None,
    ps_ratio: float | None,
    net_debt_ebitda: float | None,
    trend: str,
    base_case_description: str,
) -> str:
    recommendation_label = {
        "strong_buy": "kupuj agresywnie",
        "buy": "kupuj",
        "hold": "trzymaj",
        "reduce": "redukuj",
        "sell": "sprzedaj",
    }[recommendation]
    valuation_bits: list[str] = []
    if pb_ratio is not None:
        valuation_bits.append(f"C/WK {pb_ratio:.2f}")
    if ps_ratio is not None:
        valuation_bits.append(f"C/P {ps_ratio:.2f}")

    if valuation_quadrant == "A":
        first_sentence = (
            "Konserwatywna wycena sugeruje wyrazne dyskonto do wartosci godziwej, "
            "a jakosc biznesu i bilans nie podwazaja tezy inwestycyjnej."
        )
    elif valuation_quadrant == "B":
        first_sentence = (
            "Konserwatywna wycena nadal sugeruje dyskonto do wartosci godziwej, "
            "ale teza inwestycyjna wymaga poprawy w marzach, cash flow, bilansie albo katalizatorach."
        )
    elif abs(upside_pct) <= 5.0:
        first_sentence = "Konserwatywna wycena stawia spolke blisko wartosci godziwej, wiec margines bezpieczenstwa jest dzis ograniczony."
    elif valuation_bits:
        first_sentence = (
            f"Obecna cena nie daje wyraznego marginesu bezpieczenstwa mimo widocznych mnoznikow ({', '.join(valuation_bits)})."
        )
    else:
        first_sentence = "Obecna cena nie daje wystarczajacego marginesu bezpieczenstwa wobec jakosci biznesu i ryzyk bilansowych."

    leverage_part = ""
    if net_debt_ebitda is not None:
        if net_debt_ebitda >= 4.0:
            leverage_part = f" Dlug netto/EBITDA na poziomie {net_debt_ebitda:.2f}x pozostaje glownym ograniczeniem dla re-ratingu."
        elif net_debt_ebitda <= 1.5:
            leverage_part = f" Bilans jest wspierany przez umiarkowany dlug netto/EBITDA na poziomie {net_debt_ebitda:.2f}x."

    if abs(upside_pct) <= 5.0:
        second_sentence = (
            f"Target 12m pozostaje blisko biezacego kursu, dlatego rekomendacja jest '{recommendation_label}' i score "
            f"{overall_score:.1f}/10 powinien pozostawac w neutralnym pasmie, a nie sugerowac skrajnego scenariusza."
        )
    else:
        direction = "potencjal wzrostu" if upside_pct > 0 else "ryzyko spadku"
        second_sentence = (
            f"Na dzis raport widzi {direction} rzedu {upside_pct:+.1f}%, co wspiera rekomendacje '{recommendation_label}' "
            f"przy score {overall_score:.1f}/10."
        )

    third_sentence = f"Scenariusz bazowy zaklada: {base_case_description.lower()}." if base_case_description else ""
    timing_sentence = (
        f" Technicznie obraz pozostaje {trend}, wiec timing sluzy raczej jako filtr wejscia niz zrodlo samej wyceny."
    )
    return f"{first_sentence}{leverage_part} {second_sentence} {third_sentence}{timing_sentence}".strip()


def _latest_ai_as_of(value: Any) -> str:
    latest: datetime | None = None

    def _parse(raw: str) -> datetime | None:
        try:
            normalized = raw.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except ValueError:
            try:
                return datetime.fromisoformat(f"{raw}T00:00:00+00:00")
            except ValueError:
                return None

    def _walk(node: Any) -> None:
        nonlocal latest
        if hasattr(node, "model_dump"):
            _walk(node.model_dump())
            return
        if isinstance(node, dict):
            if {"as_of", "source", "confidence"}.issubset(node.keys()):
                parsed = _parse(str(node["as_of"]))
                if parsed is not None and (latest is None or parsed > latest):
                    latest = parsed
            for child in node.values():
                _walk(child)
            return
        if isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(value)
    if latest is None:
        return ""
    return latest.date().isoformat()


def _technical_interpretation(
    trend: str,
    price: float,
    ma20: float | None,
    ma50: float | None,
    ma200: float | None,
    macd_signal: str,
    rsi_value: float | None,
    bb_width_pct: float | None,
) -> str:
    parts: list[str] = ["Wskazniki techniczne sa liczone na swiecach tygodniowych."]
    if ma20 is not None and ma50 is not None and ma200 is not None:
        parts.append(
            f"Cena {price:.2f} PLN jest {'powyzej' if price >= ma20 else 'ponizej'} MA20, "
            f"{'powyzej' if price >= ma50 else 'ponizej'} MA50 i "
            f"{'powyzej' if price >= ma200 else 'ponizej'} MA200."
        )
    parts.append(
        f"Trend ogolny pozostaje {trend} na bazie polozenia ceny wobec MA50/MA200 i sygnalu MACD ({macd_signal})."
    )
    if rsi_value is not None:
        if rsi_value >= 70:
            parts.append(f"RSI {rsi_value:.1f} wskazuje strefe wykupienia.")
        elif rsi_value <= 30:
            parts.append(f"RSI {rsi_value:.1f} wskazuje strefe wyprzedania.")
        else:
            parts.append(f"RSI {rsi_value:.1f} pozostaje neutralny.")
    if bb_width_pct is not None:
        parts.append(f"Szerokosc wsteg Bollingera wynosi {bb_width_pct:.1f}%, co obrazuje biezaca zmiennosc.")
    return " ".join(parts)


def _volume_interpretation(
    avg_volume_30d: float | None,
    current_volume: float | None,
    volume_ratio: float | None,
    obv_trend: str,
    liquidity_score_value: float,
    anomalous_count: int,
) -> str:
    parts: list[str] = []
    if avg_volume_30d is not None:
        parts.append(f"Sredni wolumen 30D wynosi ok. {int(round(avg_volume_30d))} akcji na sesje.")
    if current_volume is not None and volume_ratio is not None:
        parts.append(
            f"Biezacy wolumen to {int(round(current_volume))} akcji, czyli {volume_ratio:.2f}x sredniej."
        )
    parts.append(
        f"OBV jest oceniany jako {obv_trend}, a plynnosc ma score {liquidity_score_value:.1f}/10."
    )
    if anomalous_count:
        parts.append(f"W ostatnich 90 sesjach wykryto {anomalous_count} sesji z ponadprzecietnym wolumenem.")
    parts.append("Spread bid-ask nie jest obecnie dostepny w stock-service, dlatego nie jest uwzgledniany ilosciowo.")
    return " ".join(parts)


def build_equity_report(
    ai_payload: EquityAiPayload,
    mic: str,
    symbol: str,
    currency: str,
    instrument_shortname: str | None,
    instrument_name: str | None,
    instrument_isin: str | None,
    current_price: float,
    change_1d_pct: float,
    last_trade_at: datetime,
    candles: Sequence[Any],
    period: str,
    model: str,
    final_generated_at: datetime,
    valid_until: date,
) -> tuple[EquityReport, date]:
    normalized_candles = sort_candles(candles)
    technical_candles = aggregate_candles_weekly(normalized_candles)
    technical_close_values = closes(technical_candles)
    quote_date = last_trade_at.date()
    candle_latest_date = normalized_candles[-1]["date_quote"] if normalized_candles else quote_date
    market_data_as_of = max(quote_date, candle_latest_date)

    ma20 = sma(technical_close_values, 20)
    ma50 = sma(technical_close_values, 50)
    ma200 = sma(technical_close_values, 200)
    macd_data = macd(technical_close_values)
    rsi_value = rsi(technical_close_values)
    stoch_data = stoch_rsi(technical_close_values)
    bb_data = bollinger(technical_close_values, period=66)
    obv_trend, obv_signal = obv_state(normalized_candles)
    support_resistance_data = support_resistance(technical_candles, current_price)
    anomalous_sessions = detect_anomalous_sessions(normalized_candles)

    week_52_high, week_52_low = compute_52w_range(normalized_candles)
    if week_52_high is None:
        week_52_high = current_price
    if week_52_low is None:
        week_52_low = current_price

    change_ytd_pct = ytd_change_pct(normalized_candles, current_price, quote_date) or 0.0
    discount_from_peak_pct = safe_percent(week_52_high - current_price, week_52_high) or 0.0

    shares_outstanding = to_float(ai_payload.company.shares_outstanding.value)
    market_cap = (current_price * shares_outstanding) if shares_outstanding is not None else 0.0
    revenue_ttm = to_float(ai_payload.fundamentals.revenue_ttm.value)
    ebitda_ttm = to_float(ai_payload.fundamentals.ebitda_ttm.value)
    eps_ttm = to_float(ai_payload.fundamentals.eps_ttm.value)
    ocf_value = to_float(ai_payload.fundamentals.ocf.value)
    fcf_value = to_float(ai_payload.fundamentals.fcf.value)
    net_debt = to_float(ai_payload.debt_balance.net_debt.value)
    capex_value = to_float(ai_payload.debt_balance.capex.value)
    equity_value = to_float(ai_payload.debt_balance.equity.value)
    free_float_pct = to_float(ai_payload.shareholders.free_float_pct.value)
    bvps_value = safe_ratio(equity_value, shares_outstanding)

    fcf_yield_value = safe_percent(fcf_value, market_cap)
    pe_ratio_value = safe_ratio(current_price, eps_ttm)
    ev_ebitda_value = safe_ratio((market_cap + (net_debt or 0.0)) if ebitda_ttm else None, ebitda_ttm)
    pb_ratio_value = safe_ratio(market_cap, equity_value)
    ps_ratio_value = safe_ratio(market_cap, revenue_ttm)

    last_dividend_amount = (
        ai_payload.dividend.last_dividend.amount
        if ai_payload.dividend.last_dividend is not None
        else latest_positive_dividend_amount(ai_payload.dividend.history)
    )
    dividend_yield_value = safe_percent(last_dividend_amount, current_price)
    dividend_growth_3y_value = dividend_growth_cagr(ai_payload.dividend.history, years=3)
    float_shares_value = (
        shares_outstanding * free_float_pct / 100.0
        if shares_outstanding is not None and free_float_pct is not None
        else None
    )

    avg_volume_30d_raw = None
    if len(normalized_candles) >= 30:
        volumes = [row["volume"] for row in normalized_candles[-30:] if row.get("volume") is not None]
        if volumes:
            avg_volume_30d_raw = sum(volumes) / len(volumes)
    current_volume_raw = (
        normalized_candles[-1].get("volume")
        if normalized_candles and normalized_candles[-1].get("date_quote") == candle_latest_date
        else None
    )
    if current_volume_raw is None and normalized_candles:
        current_volume_raw = normalized_candles[-1].get("volume")
    volume_ratio_value = safe_ratio(float(current_volume_raw) if current_volume_raw is not None else None, avg_volume_30d_raw)
    liquidity_score_value = liquidity_score(normalized_candles, current_price)

    trend_value = determine_trend(current_price, ma50, ma200, str(macd_data["signal"]))
    local_interpretation_technical = _technical_interpretation(
        trend=trend_value,
        price=current_price,
        ma20=ma20,
        ma50=ma50,
        ma200=ma200,
        macd_signal=str(macd_data["signal"]),
        rsi_value=rsi_value,
        bb_width_pct=to_float(bb_data["width_pct"]),
    )
    local_interpretation_volume = _volume_interpretation(
        avg_volume_30d=avg_volume_30d_raw,
        current_volume=float(current_volume_raw) if current_volume_raw is not None else None,
        volume_ratio=volume_ratio_value,
        obv_trend=obv_trend,
        liquidity_score_value=liquidity_score_value,
        anomalous_count=len(anomalous_sessions),
    )

    valuation_confidence = min_confidence(
        ai_payload.fundamentals.eps_ttm.confidence,
        ai_payload.fundamentals.fcf.confidence,
        ai_payload.fundamentals.revenue_ttm.confidence,
        ai_payload.fundamentals.ebitda_ttm.confidence,
        ai_payload.debt_balance.net_debt.confidence,
        ai_payload.debt_balance.equity.confidence,
        ai_payload.company.shares_outstanding.confidence,
    )
    float_shares_confidence = min_confidence(
        ai_payload.company.shares_outstanding.confidence,
        ai_payload.shareholders.free_float_pct.confidence,
    )
    bvps_confidence = min_confidence(
        ai_payload.debt_balance.equity.confidence,
        ai_payload.company.shares_outstanding.confidence,
    )

    ocf_metric = ai_payload.fundamentals.ocf
    if ocf_value is None and fcf_value is not None and capex_value is not None:
        ocf_metric = _metric(
            value=round(fcf_value + capex_value, 2),
            as_of=ai_payload.fundamentals.fcf.as_of or ai_payload.debt_balance.capex.as_of,
            source="local",
            confidence=min_confidence(
                ai_payload.fundamentals.fcf.confidence,
                ai_payload.debt_balance.capex.confidence,
            ),
            unit="PLN",
            note="Przyblizenie: OCF ~= FCF + CAPEX, gdy brak osobnej pozycji CFO.",
        )

    bvps_metric = ai_payload.fundamentals.bvps
    if bvps_value is not None:
        bvps_metric = _metric(
            value=round(bvps_value, 4),
            as_of=ai_payload.debt_balance.equity.as_of or ai_payload.company.shares_outstanding.as_of,
            source="local",
            confidence=bvps_confidence,
            unit="PLN",
            note="Wyliczone z kapitalu wlasnego i liczby akcji.",
        )

    company = CompanyInfo(
        name=_text_or_default(ai_payload.company.name, instrument_shortname or symbol),
        full_name=_text_or_default(
            ai_payload.company.full_name,
            instrument_name or instrument_shortname or symbol,
        ),
        description=_text_or_default(
            ai_payload.company.description,
            "Brak zweryfikowanego opisu spolki w payloadzie AI.",
        ),
        sector=_text_or_default(ai_payload.company.sector),
        industry=_text_or_default(ai_payload.company.industry),
        country=_text_or_default(ai_payload.company.country),
        exchange=_text_or_default(ai_payload.company.exchange, mic),
        founded=_text_or_default(ai_payload.company.founded),
        employees=ai_payload.company.employees,
        ceo=_text_or_default(ai_payload.company.ceo),
        ceo_since=_text_or_default(ai_payload.company.ceo_since),
        headquarters=_text_or_default(ai_payload.company.headquarters),
        is_leader_in=ai_payload.company.is_leader_in,
        main_products=ai_payload.company.main_products,
        key_competitors=ai_payload.company.key_competitors,
        market_position=_text_or_default(ai_payload.company.market_position),
        website=_text_or_default(ai_payload.company.website),
        isin=_text_or_default(ai_payload.company.isin, instrument_isin or ""),
        price=CompanyInfo.PriceInfo(
            current=round(current_price, 2),
            currency=currency,
            change_1d_pct=round(change_1d_pct, 2),
            change_ytd_pct=round(change_ytd_pct, 2),
            week_52_high=round(week_52_high, 2),
            week_52_low=round(week_52_low, 2),
            market_cap=round(market_cap, 2),
            as_of=_dt_iso(last_trade_at),
        ),
    )

    fundamentals = Fundamentals(
        ebitda_margin=ai_payload.fundamentals.ebitda_margin,
        roe=ai_payload.fundamentals.roe,
        roic=ai_payload.fundamentals.roic,
        ocf=ocf_metric,
        fcf=ai_payload.fundamentals.fcf,
        fcf_yield=_metric(
            value=round(fcf_yield_value, 2) if fcf_yield_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=valuation_confidence,
            unit="%",
        ),
        pe_ratio=_metric(
            value=round(pe_ratio_value, 2) if pe_ratio_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=min_confidence(ai_payload.fundamentals.eps_ttm.confidence, ai_payload.company.shares_outstanding.confidence),
            unit="x",
        ),
        ev_ebitda=_metric(
            value=round(ev_ebitda_value, 2) if ev_ebitda_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=valuation_confidence,
            unit="x",
        ),
        pb_ratio=_metric(
            value=round(pb_ratio_value, 2) if pb_ratio_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=min_confidence(ai_payload.debt_balance.equity.confidence, ai_payload.company.shares_outstanding.confidence),
            unit="x",
        ),
        ps_ratio=_metric(
            value=round(ps_ratio_value, 2) if ps_ratio_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=min_confidence(ai_payload.fundamentals.revenue_ttm.confidence, ai_payload.company.shares_outstanding.confidence),
            unit="x",
        ),
        discount_from_peak_pct=_metric(
            value=round(discount_from_peak_pct, 2),
            as_of=market_data_as_of,
            source="local",
            confidence="high",
            unit="%",
        ),
        bvps=bvps_metric,
        revenue_ttm=ai_payload.fundamentals.revenue_ttm,
        ebitda_ttm=ai_payload.fundamentals.ebitda_ttm,
        net_income_ttm=ai_payload.fundamentals.net_income_ttm,
        eps_ttm=ai_payload.fundamentals.eps_ttm,
        interpretation=ai_payload.fundamentals.interpretation,
    )

    debt_balance = DebtBalance.model_validate(ai_payload.debt_balance.model_dump())

    dividend = Dividend(
        dividend_yield=_metric(
            value=round(dividend_yield_value, 2) if dividend_yield_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence=min_confidence(ai_payload.dividend.payout_ratio.confidence, ai_payload.company.shares_outstanding.confidence),
            unit="%",
        ),
        payout_ratio=ai_payload.dividend.payout_ratio,
        dividend_growth_3y=_metric(
            value=round(dividend_growth_3y_value, 2) if dividend_growth_3y_value is not None else None,
            as_of=ai_payload.dividend.payout_ratio.as_of,
            source="local",
            confidence=ai_payload.dividend.payout_ratio.confidence,
            unit="%",
            note="CAGR 3-letni",
        ),
        last_dividend=(
            Dividend.LastDividend.model_validate(ai_payload.dividend.last_dividend.model_dump())
            if ai_payload.dividend.last_dividend is not None
            else None
        ),
        history=ai_payload.dividend.history,
        is_dividend_stock=ai_payload.dividend.is_dividend_stock,
        dividend_consistency=ai_payload.dividend.dividend_consistency,
        interpretation=ai_payload.dividend.interpretation,
    )

    technical = Technical(
        trend=trend_value,
        moving_averages=Technical.MovingAverages(
            ma_20=_metric(
                value=round(ma20, 2) if ma20 is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            ma_50=_metric(
                value=round(ma50, 2) if ma50 is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            ma_200=_metric(
                value=round(ma200, 2) if ma200 is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            price_vs_ma20=_price_vs_level(current_price, ma20),
            price_vs_ma50=_price_vs_level(current_price, ma50),
            price_vs_ma200=_price_vs_level(current_price, ma200),
        ),
        macd=Technical.Macd(
            macd_line=_metric(
                value=round(to_float(macd_data["macd_line"]), 4) if to_float(macd_data["macd_line"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
            ),
            signal_line=_metric(
                value=round(to_float(macd_data["signal_line"]), 4) if to_float(macd_data["signal_line"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
            ),
            histogram=_metric(
                value=round(to_float(macd_data["histogram"]), 4) if to_float(macd_data["histogram"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
            ),
            signal=str(macd_data["signal"]),
        ),
        bollinger_bands=Technical.BollingerBands(
            upper=_metric(
                value=round(to_float(bb_data["upper"]), 2) if to_float(bb_data["upper"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            middle=_metric(
                value=round(to_float(bb_data["middle"]), 2) if to_float(bb_data["middle"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            lower=_metric(
                value=round(to_float(bb_data["lower"]), 2) if to_float(bb_data["lower"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit=currency,
            ),
            width_pct=_metric(
                value=round(to_float(bb_data["width_pct"]), 2) if to_float(bb_data["width_pct"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
                unit="%",
            ),
            position=str(bb_data["position"]),
        ),
        rsi=_metric(
            value=round(rsi_value, 2) if rsi_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence="high",
        ),
        stoch_rsi=Technical.StochRsi(
            k=_metric(
                value=round(to_float(stoch_data["k"]), 2) if to_float(stoch_data["k"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
            ),
            d=_metric(
                value=round(to_float(stoch_data["d"]), 2) if to_float(stoch_data["d"]) is not None else None,
                as_of=market_data_as_of,
                source="local",
                confidence="high",
            ),
            signal=str(stoch_data["signal"]),
        ),
        support_resistance=Technical.SupportResistance(
            supports=[Technical.Level.model_validate(item) for item in support_resistance_data["supports"]],
            resistances=[Technical.Level.model_validate(item) for item in support_resistance_data["resistances"]],
        ),
        interpretation=local_interpretation_technical,
    )

    volume_liquidity = VolumeAndLiquidity(
        avg_volume_30d=_metric(
            value=int(round(avg_volume_30d_raw)) if avg_volume_30d_raw is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence="high",
            unit="akcji/sesja",
        ),
        current_volume=_metric(
            value=int(current_volume_raw) if current_volume_raw is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence="high",
            unit="akcji",
        ),
        volume_ratio=_metric(
            value=round(volume_ratio_value, 2) if volume_ratio_value is not None else None,
            as_of=market_data_as_of,
            source="local",
            confidence="high",
            unit="x",
        ),
        obv_trend=obv_trend,
        obv_signal=obv_signal,
        liquidity_score=liquidity_score_value,
        bid_ask_spread_pct=_metric(
            value=None,
            as_of=market_data_as_of,
            source="local",
            confidence="low",
            unit="%",
            note="Brak danych order-book w stock-service.",
        ),
        float_shares=_metric(
            value=round(float_shares_value) if float_shares_value is not None else None,
            as_of=ai_payload.shareholders.free_float_pct.as_of,
            source="local",
            confidence=float_shares_confidence,
            unit="akcji",
            note="Wyliczone z shares_outstanding i free float.",
        ),
        anomalous_sessions=anomalous_sessions,
        interpretation=local_interpretation_volume,
    )

    price_target_value = to_float(ai_payload.verdict.price_target.value)
    upside_pct_value = safe_percent(
        None if price_target_value is None else price_target_value - current_price,
        current_price,
    )
    upside_pct = upside_pct_value or 0.0

    scores = ai_payload.trend_condition.scores
    business_quality_score = _mean(
        [
            to_float(scores.profitability.score),
            to_float(scores.competitive_advantage.score),
            to_float(scores.industry_outlook.score),
        ]
    )
    trend_score = _mean([to_float(scores.revenue_growth.score)])
    balance_score = _mean([to_float(scores.balance_sheet.score)])
    cash_quality_score = _mean([to_float(scores.earnings_quality.score)])
    governance_score = _mean([to_float(scores.management_quality.score)])
    valuation_score = _valuation_score(
        pb_ratio=pb_ratio_value,
        ps_ratio=ps_ratio_value,
        pe_ratio=pe_ratio_value,
        ev_ebitda=ev_ebitda_value,
        fcf_yield=fcf_yield_value,
    )
    base_score = (
        0.25 * business_quality_score
        + 0.20 * trend_score
        + 0.20 * balance_score
        + 0.15 * cash_quality_score
        + 0.15 * valuation_score
        + 0.05 * governance_score
    )
    computed_overall_score = round(_clamp(base_score, 1.0, 10.0), 1)

    condition_score = _mean(
        [
            business_quality_score,
            trend_score,
            balance_score,
            cash_quality_score,
        ]
    )
    computed_valuation_quadrant = _quadrant_from_scores(
        valuation_score=valuation_score,
        condition_score=condition_score,
        upside_pct=upside_pct_value,
        has_price_target=price_target_value is not None,
        pb_ratio=pb_ratio_value,
        ps_ratio=ps_ratio_value,
    )
    computed_recommendation = _recommendation_from_context(
        overall_score=computed_overall_score,
        upside_pct=upside_pct,
        valuation_quadrant=computed_valuation_quadrant,
        trend=trend_value,
    )
    computed_momentum_signal, computed_momentum_label, computed_momentum_reasoning = _momentum_context(
        overall_score=computed_overall_score,
        upside_pct=upside_pct,
        trend=trend_value,
        macd_signal=str(macd_data["signal"]),
        current_quadrant=computed_valuation_quadrant,
    )
    computed_valuation_matrix = _default_valuation_matrix(
        current_quadrant=computed_valuation_quadrant,
        momentum_signal=computed_momentum_signal,
        momentum_label=computed_momentum_label,
        momentum_reasoning=computed_momentum_reasoning,
    )
    overall_score = round(_clamp(to_float(ai_payload.verdict.overall_score) or computed_overall_score, 1.0, 10.0), 1)
    recommendation = ai_payload.verdict.recommendation or computed_recommendation
    valuation_matrix = (
        ValuationMatrix.model_validate(ai_payload.verdict.valuation_matrix.model_dump())
        if ai_payload.verdict.valuation_matrix is not None
        else computed_valuation_matrix
    )
    ai_verdict_interpretation = (ai_payload.verdict.interpretation or "").strip()
    verdict_interpretation = ai_verdict_interpretation or _verdict_interpretation(
        valuation_quadrant=valuation_matrix.current_quadrant,
        recommendation=recommendation,
        overall_score=overall_score,
        upside_pct=upside_pct,
        pb_ratio=pb_ratio_value,
        ps_ratio=ps_ratio_value,
        net_debt_ebitda=to_float(ai_payload.debt_balance.net_debt_ebitda.value),
        trend=trend_value,
        base_case_description=ai_payload.verdict.base_case.description,
    )

    verdict = Verdict(
        overall_score=overall_score,
        recommendation=recommendation,
        time_horizon=ai_payload.verdict.time_horizon,
        price_target=ai_payload.verdict.price_target,
        upside_pct=round(upside_pct, 2),
        bull_case=ai_payload.verdict.bull_case,
        base_case=ai_payload.verdict.base_case,
        bear_case=ai_payload.verdict.bear_case,
        key_watchpoints=ai_payload.verdict.key_watchpoints,
        valuation_matrix=valuation_matrix,
        interpretation=verdict_interpretation,
    )

    meta = ReportMeta(
        symbol=symbol,
        mic=mic,
        period=period,
        generated_at=_dt_iso(final_generated_at),
        valid_until=valid_until.isoformat(),
        report_type="equity",
        source_versions=ReportMeta.SourceVersions(
            price_data_as_of=market_data_as_of.isoformat(),
            fundamentals_as_of=_latest_ai_as_of(ai_payload),
            model=model,
        ),
    )

    report = EquityReport(
        meta=meta,
        company=company,
        fundamentals=fundamentals,
        debt_balance=debt_balance,
        trend_condition=ai_payload.trend_condition,
        dividend=dividend,
        key_events=ai_payload.key_events,
        advantages_risks=ai_payload.advantages_risks,
        technical=technical,
        volume_liquidity=volume_liquidity,
        shareholders=ai_payload.shareholders,
        verdict=verdict,
    )
    return report, market_data_as_of
