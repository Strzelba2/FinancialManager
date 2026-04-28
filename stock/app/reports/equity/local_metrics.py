from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Sequence, Any


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def iso_date(value: date | datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def confidence_rank(value: str | None) -> int:
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(str(value or "").lower(), 0)


def min_confidence(*values: str | None) -> str:
    filtered = [v for v in values if v]
    if not filtered:
        return "low"
    return min(filtered, key=confidence_rank)


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def safe_percent(numerator: float | None, denominator: float | None) -> float | None:
    ratio = safe_ratio(numerator, denominator)
    return None if ratio is None else ratio * 100.0


def sort_candles(candles: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in candles:
        if isinstance(item, dict):
            raw = item
        else:
            raw = {
                "date_quote": getattr(item, "date_quote", None),
                "open": getattr(item, "open", None),
                "high": getattr(item, "high", None),
                "low": getattr(item, "low", None),
                "close": getattr(item, "close", None),
                "volume": getattr(item, "volume", None),
            }
        if raw.get("date_quote") is None:
            continue
        rows.append(
            {
                "date_quote": raw["date_quote"],
                "open": to_float(raw.get("open")),
                "high": to_float(raw.get("high")),
                "low": to_float(raw.get("low")),
                "close": to_float(raw.get("close")),
                "volume": to_int(raw.get("volume")),
            }
        )
    rows.sort(key=lambda item: item["date_quote"])
    return rows


def closes(candles: Sequence[dict[str, Any]]) -> list[float]:
    return [row["close"] for row in candles if row.get("close") is not None]


def aggregate_candles_weekly(candles: Sequence[dict[str, Any]] | Iterable[Any]) -> list[dict[str, Any]]:
    rows = sort_candles(candles)
    if not rows:
        return []

    weekly_rows: list[dict[str, Any]] = []
    current_key: tuple[int, int] | None = None
    current_week: dict[str, Any] | None = None

    for row in rows:
        row_date = row["date_quote"]
        week_key = row_date.isocalendar()[:2]
        if current_key != week_key or current_week is None:
            if current_week is not None:
                weekly_rows.append(current_week)
            current_key = week_key
            current_week = {
                "date_quote": row_date,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
            }
            continue

        current_week["date_quote"] = row_date
        if current_week.get("open") is None and row.get("open") is not None:
            current_week["open"] = row.get("open")
        high = row.get("high")
        if high is not None:
            current_high = current_week.get("high")
            current_week["high"] = high if current_high is None else max(current_high, high)
        low = row.get("low")
        if low is not None:
            current_low = current_week.get("low")
            current_week["low"] = low if current_low is None else min(current_low, low)
        if row.get("close") is not None:
            current_week["close"] = row.get("close")
        row_volume = row.get("volume")
        current_volume = current_week.get("volume")
        if row_volume is not None:
            current_week["volume"] = (current_volume or 0) + row_volume

    if current_week is not None:
        weekly_rows.append(current_week)

    return weekly_rows


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / float(period)


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2.0 / (period + 1.0)
    series: list[float] = [values[0]]
    for value in values[1:]:
        series.append((value - series[-1]) * multiplier + series[-1])
    return series


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float | str | None]:
    if len(values) < slow:
        return {
            "macd_line": None,
            "signal_line": None,
            "histogram": None,
            "signal": "neutral",
        }

    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    macd_series = [f - s for f, s in zip(fast_series, slow_series)]
    signal_series = ema_series(macd_series, signal)
    macd_line = macd_series[-1]
    signal_line = signal_series[-1]
    histogram = macd_line - signal_line
    if macd_line > signal_line and histogram > 0:
        state = "bullish"
    elif macd_line < signal_line and histogram < 0:
        state = "bearish"
    else:
        state = "neutral"
    return {
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
        "signal": state,
    }


def rsi_series(values: Sequence[float], period: int = 14) -> list[float]:
    if len(values) <= period:
        return []

    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(values)):
        change = values[idx] - values[idx - 1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    series: list[float] = []
    if avg_loss == 0:
        series.append(100.0)
    else:
        rs = avg_gain / avg_loss
        series.append(100.0 - (100.0 / (1.0 + rs)))

    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
        if avg_loss == 0:
            series.append(100.0)
        else:
            rs = avg_gain / avg_loss
            series.append(100.0 - (100.0 / (1.0 + rs)))

    return series


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    series = rsi_series(values, period=period)
    return series[-1] if series else None


def stoch_rsi(values: Sequence[float], rsi_period: int = 14, stoch_period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> dict[str, float | str | None]:
    rsis = rsi_series(values, period=rsi_period)
    if len(rsis) < stoch_period:
        return {"k": None, "d": None, "signal": "neutral"}

    stoch_values: list[float] = []
    for idx in range(stoch_period - 1, len(rsis)):
        window = rsis[idx - stoch_period + 1: idx + 1]
        low = min(window)
        high = max(window)
        current = rsis[idx]
        if high == low:
            stoch_values.append(50.0)
        else:
            stoch_values.append(((current - low) / (high - low)) * 100.0)

    if len(stoch_values) < smooth_k:
        return {"k": None, "d": None, "signal": "neutral"}

    k_values: list[float] = []
    for idx in range(smooth_k - 1, len(stoch_values)):
        window = stoch_values[idx - smooth_k + 1: idx + 1]
        k_values.append(sum(window) / len(window))

    if len(k_values) < smooth_d:
        return {"k": None, "d": None, "signal": "neutral"}

    d_values: list[float] = []
    for idx in range(smooth_d - 1, len(k_values)):
        window = k_values[idx - smooth_d + 1: idx + 1]
        d_values.append(sum(window) / len(window))

    k_last = k_values[-1]
    d_last = d_values[-1]
    if max(k_last, d_last) >= 80:
        signal = "overbought"
    elif min(k_last, d_last) <= 20:
        signal = "oversold"
    else:
        signal = "neutral"
    return {"k": k_last, "d": d_last, "signal": signal}


def bollinger(values: Sequence[float], period: int = 20, std_dev: float = 2.0) -> dict[str, float | str | None]:
    if len(values) < period:
        return {
            "upper": None,
            "middle": None,
            "lower": None,
            "width_pct": None,
            "position": "middle",
        }
    window = values[-period:]
    middle = sum(window) / period
    variance = sum((value - middle) ** 2 for value in window) / period
    deviation = variance ** 0.5
    upper = middle + (std_dev * deviation)
    lower = middle - (std_dev * deviation)
    width_pct = safe_percent(upper - lower, middle)
    current = values[-1]
    band = upper - lower
    if band <= 0:
        position = "middle"
    else:
        normalized = (current - lower) / band
        if normalized >= 0.67:
            position = "upper"
        elif normalized <= 0.33:
            position = "lower"
        else:
            position = "middle"
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "width_pct": width_pct,
        "position": position,
    }


def obv(candles: Sequence[dict[str, Any]]) -> list[float]:
    if not candles:
        return []
    series: list[float] = [0.0]
    for idx in range(1, len(candles)):
        prev_close = candles[idx - 1]["close"]
        current_close = candles[idx]["close"]
        volume = float(candles[idx].get("volume") or 0)
        if prev_close is None or current_close is None:
            series.append(series[-1])
            continue
        if current_close > prev_close:
            series.append(series[-1] + volume)
        elif current_close < prev_close:
            series.append(series[-1] - volume)
        else:
            series.append(series[-1])
    return series


def obv_state(candles: Sequence[dict[str, Any]]) -> tuple[str, str]:
    series = obv(candles)
    if len(series) < 10:
        return "flat", "neutral"
    latest = series[-1]
    reference = series[-10]
    if latest > reference * 1.02:
        return "rising", "bullish"
    if latest < reference * 0.98:
        return "falling", "bearish"
    return "flat", "neutral"


def compute_52w_range(candles: Sequence[dict[str, Any]]) -> tuple[float | None, float | None]:
    window = list(candles[-252:])
    highs = [row["high"] for row in window if row.get("high") is not None]
    lows = [row["low"] for row in window if row.get("low") is not None]
    return (max(highs) if highs else None, min(lows) if lows else None)


def ytd_change_pct(candles: Sequence[dict[str, Any]], current_price: float | None, as_of: date) -> float | None:
    if current_price is None:
        return None
    anchor: float | None = None
    for row in candles:
        row_date = row["date_quote"]
        if row_date.year < as_of.year and row.get("close") is not None:
            anchor = row["close"]
        elif row_date.year == as_of.year:
            break
    if anchor is None:
        for row in candles:
            if row["date_quote"].year == as_of.year and row.get("close") is not None:
                anchor = row["close"]
                break
    return safe_percent(current_price - anchor, anchor)


def dividend_growth_cagr(history: Sequence[dict[str, Any]] | Sequence[Any], years: int = 3) -> float | None:
    normalized: list[tuple[int, float]] = []
    for item in history:
        year = getattr(item, "year", None) if not isinstance(item, dict) else item.get("year")
        dps = getattr(item, "dividend_per_share", None) if not isinstance(item, dict) else item.get("dividend_per_share")
        dps_value = to_float(dps)
        if year is None or dps_value is None or dps_value <= 0:
            continue
        normalized.append((int(year), dps_value))

    if not normalized:
        return None

    normalized.sort(key=lambda item: item[0])
    latest_year, latest_value = normalized[-1]
    target_year = latest_year - years
    anchor_value: float | None = None
    for year, value in normalized:
        if year == target_year:
            anchor_value = value
            break
    if anchor_value is None or anchor_value <= 0:
        return None
    return ((latest_value / anchor_value) ** (1.0 / years) - 1.0) * 100.0


def latest_positive_dividend_amount(history: Sequence[dict[str, Any]] | Sequence[Any]) -> float | None:
    latest_value: float | None = None
    latest_year: int | None = None
    for item in history:
        year = getattr(item, "year", None) if not isinstance(item, dict) else item.get("year")
        dps = getattr(item, "dividend_per_share", None) if not isinstance(item, dict) else item.get("dividend_per_share")
        dps_value = to_float(dps)
        if year is None or dps_value is None or dps_value <= 0:
            continue
        if latest_year is None or int(year) > latest_year:
            latest_year = int(year)
            latest_value = dps_value
    return latest_value


def detect_anomalous_sessions(candles: Sequence[dict[str, Any]], lookback: int = 90, avg_window: int = 30, threshold: float = 2.0, limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if len(candles) < avg_window + 2:
        return items

    start_idx = max(avg_window, len(candles) - lookback)
    for idx in range(start_idx, len(candles)):
        row = candles[idx]
        volume = row.get("volume")
        if volume is None:
            continue
        history = [c.get("volume") for c in candles[idx - avg_window: idx] if c.get("volume") is not None]
        if len(history) < avg_window or not history:
            continue
        avg_volume = int(round(sum(history) / len(history)))
        if avg_volume <= 0:
            continue
        ratio = volume / avg_volume
        if ratio < threshold:
            continue
        open_price = row.get("open")
        close_price = row.get("close")
        price_change_pct = safe_percent(
            None if close_price is None or open_price is None else close_price - open_price,
            open_price,
        )
        if price_change_pct is None:
            price_change_pct = 0.0
        if price_change_pct > 1.0:
            session_type = "accumulation"
        elif price_change_pct < -1.0:
            session_type = "distribution"
        else:
            session_type = "neutral"
        items.append(
            {
                "date": iso_date(row["date_quote"]),
                "volume": int(volume),
                "avg_volume": int(avg_volume),
                "ratio": round(ratio, 2),
                "price_change_pct": round(price_change_pct, 2),
                "type": session_type,
            }
        )
    items.sort(key=lambda item: (item["ratio"], item["date"]), reverse=True)
    return items[:limit]


def _cluster_levels(levels: Sequence[float], band_pct: float = 0.015) -> list[tuple[float, int]]:
    if not levels:
        return []
    sorted_levels = sorted(levels)
    clusters: list[list[float]] = [[sorted_levels[0]]]
    for level in sorted_levels[1:]:
        current_cluster = clusters[-1]
        avg = sum(current_cluster) / len(current_cluster)
        if avg > 0 and abs(level - avg) / avg <= band_pct:
            current_cluster.append(level)
        else:
            clusters.append([level])
    return [(sum(cluster) / len(cluster), len(cluster)) for cluster in clusters]


def support_resistance(candles: Sequence[dict[str, Any]], current_price: float | None, lookback: int = 180) -> dict[str, list[dict[str, Any]]]:
    window = list(candles[-lookback:])
    if len(window) < 3 or current_price is None:
        return {"supports": [], "resistances": []}

    swing_lows: list[float] = []
    swing_highs: list[float] = []
    for idx in range(1, len(window) - 1):
        prev_row = window[idx - 1]
        row = window[idx]
        next_row = window[idx + 1]
        low = row.get("low")
        high = row.get("high")
        if low is not None and prev_row.get("low") is not None and next_row.get("low") is not None:
            if low <= prev_row["low"] and low <= next_row["low"]:
                swing_lows.append(low)
        if high is not None and prev_row.get("high") is not None and next_row.get("high") is not None:
            if high >= prev_row["high"] and high >= next_row["high"]:
                swing_highs.append(high)

    supports = []
    for level, touches in _cluster_levels([lvl for lvl in swing_lows if lvl <= current_price * 1.015]):
        if touches >= 3:
            strength = "strong"
        elif touches == 2:
            strength = "moderate"
        else:
            strength = "weak"
        supports.append({"level": round(level, 2), "strength": strength, "touches": touches})
    supports.sort(key=lambda item: (item["level"], item["touches"]), reverse=True)

    resistances = []
    for level, touches in _cluster_levels([lvl for lvl in swing_highs if lvl >= current_price * 0.985]):
        if touches >= 3:
            strength = "strong"
        elif touches == 2:
            strength = "moderate"
        else:
            strength = "weak"
        resistances.append({"level": round(level, 2), "strength": strength, "touches": touches})
    resistances.sort(key=lambda item: (item["level"], item["touches"]))

    return {
        "supports": [{"level": item["level"], "strength": item["strength"]} for item in supports[:3]],
        "resistances": [{"level": item["level"], "strength": item["strength"]} for item in resistances[:3]],
    }


def liquidity_score(candles: Sequence[dict[str, Any]], current_price: float | None) -> float:
    window = list(candles[-30:])
    volumes = [row.get("volume") or 0 for row in window if row.get("volume") is not None]
    if not volumes or current_price is None:
        return 1.0

    avg_volume = sum(volumes) / len(volumes)
    avg_turnover = 0.0
    turnover_points = 0
    for row in window:
        close_price = row.get("close")
        volume = row.get("volume")
        if close_price is None or volume is None:
            continue
        avg_turnover += close_price * volume
        turnover_points += 1
    avg_turnover = avg_turnover / turnover_points if turnover_points else avg_volume * current_price

    volume_thresholds = [5_000, 20_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 5_000_000]
    turnover_thresholds = [50_000, 200_000, 500_000, 1_000_000, 3_000_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000]

    volume_score = 1
    turnover_score = 1
    for threshold in volume_thresholds:
        if avg_volume >= threshold:
            volume_score += 1
    for threshold in turnover_thresholds:
        if avg_turnover >= threshold:
            turnover_score += 1
    score = (volume_score + turnover_score) / 2.0
    return float(max(1.0, min(10.0, round(score, 1))))


def determine_trend(current_price: float | None, ma_50: float | None, ma_200: float | None, macd_signal: str) -> str:
    if current_price is None or ma_50 is None or ma_200 is None:
        return "neutral"
    if current_price > ma_50 and current_price > ma_200 and macd_signal == "bullish":
        return "bullish"
    if current_price < ma_50 and current_price < ma_200 and macd_signal == "bearish":
        return "bearish"
    return "neutral"
