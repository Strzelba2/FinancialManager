from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


Source = Literal["openai", "local", "manual"]
Confidence = Literal["high", "medium", "low"]
Direction = Literal["up", "down", "flat"]
Trend = Literal["bullish", "bearish", "neutral"]
Impact = Literal["high", "medium", "low"]
Recommendation = Literal["strong_buy", "buy", "hold", "reduce", "sell"]
MatrixQuadrant = Literal["A", "B", "C", "D"]
MomentumSignal = Literal["buy_now", "accumulate", "wait", "too_expensive", "avoid"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


MetricScalar = str | float | int | bool


class MetricValue(StrictModel):
    value: MetricScalar | None
    as_of: str
    source: Source
    confidence: Confidence
    unit: str | None = None
    note: str | None = None


class ReportMeta(StrictModel):
    symbol: str
    mic: str
    period: str
    generated_at: str
    valid_until: str
    report_type: Literal["equity"]

    class SourceVersions(StrictModel):
        price_data_as_of: str
        fundamentals_as_of: str
        model: str

    source_versions: SourceVersions


class ReportPeriod(StrictModel):
    period: str
    generated_at: str
    is_current: bool


class CompanyInfo(StrictModel):
    class PriceInfo(StrictModel):
        current: float
        currency: str
        change_1d_pct: float
        change_ytd_pct: float
        week_52_high: float
        week_52_low: float
        market_cap: float
        as_of: str

    name: str
    full_name: str
    description: str
    sector: str
    industry: str
    country: str
    exchange: str
    founded: str
    employees: MetricValue
    ceo: str
    ceo_since: str
    headquarters: str
    is_leader_in: list[str]
    main_products: list[str]
    key_competitors: list[str]
    market_position: str
    website: str
    isin: str
    price: PriceInfo


class Fundamentals(StrictModel):
    ebitda_margin: MetricValue
    roe: MetricValue
    roic: MetricValue
    ocf: MetricValue
    fcf: MetricValue
    fcf_yield: MetricValue
    pe_ratio: MetricValue
    ev_ebitda: MetricValue
    pb_ratio: MetricValue
    ps_ratio: MetricValue
    discount_from_peak_pct: MetricValue
    bvps: MetricValue
    revenue_ttm: MetricValue
    ebitda_ttm: MetricValue
    net_income_ttm: MetricValue
    eps_ttm: MetricValue
    interpretation: str


class DebtBalance(StrictModel):
    cash_and_equivalents: MetricValue
    net_debt: MetricValue
    net_debt_ebitda: MetricValue
    current_ratio: MetricValue
    quick_ratio: MetricValue
    interest_coverage: MetricValue
    de_ratio: MetricValue
    capex: MetricValue
    capex_to_depreciation: MetricValue
    total_assets: MetricValue
    equity: MetricValue
    interpretation: str


class ScoreItem(StrictModel):
    score: float
    reasoning: str


class HistoryYear(StrictModel):
    year: int
    revenue: float | None
    ebitda: float | None
    ebitda_margin_pct: float | None
    net_income: float | None
    eps: float | None
    roe_pct: float | None
    net_debt_ebitda: float | None
    dividend_per_share: float | None
    direction: Direction


class TrendCondition(StrictModel):
    class Scores(StrictModel):
        profitability: ScoreItem
        balance_sheet: ScoreItem
        earnings_quality: ScoreItem
        revenue_growth: ScoreItem
        market_valuation: ScoreItem
        management_quality: ScoreItem
        competitive_advantage: ScoreItem
        industry_outlook: ScoreItem
        overall: float

    scores: Scores
    history: list[HistoryYear]
    positive_signals: list[str]
    negative_signals: list[str]
    interpretation: str


class DividendHistory(StrictModel):
    year: int
    dividend_per_share: float | None
    yield_pct: float | None
    payout_ratio_pct: float | None
    paid: bool


class Dividend(StrictModel):
    class LastDividend(StrictModel):
        amount: float
        currency: str
        ex_date: str
        pay_date: str

    dividend_yield: MetricValue
    payout_ratio: MetricValue
    dividend_growth_3y: MetricValue
    last_dividend: LastDividend | None
    history: list[DividendHistory]
    is_dividend_stock: bool
    dividend_consistency: Literal["consistent", "irregular", "none"]
    interpretation: str


class KeyEvent(StrictModel):
    date: str
    title: str
    description: str
    impact: Impact
    confidence: Confidence


class UpcomingDate(StrictModel):
    date: str
    event: str
    type: Literal["earnings", "dividend", "agm", "other"]


class KeyEvents(StrictModel):
    positive: list[KeyEvent]
    negative: list[KeyEvent]
    upcoming_dates: list[UpcomingDate]
    interpretation: str


class Advantage(StrictModel):
    title: str
    description: str
    strength: Literal["strong", "moderate", "weak"]


class Risk(StrictModel):
    title: str
    description: str
    severity: Impact
    probability: Impact


class AdvantagesRisks(StrictModel):
    moat_score: float
    moat_type: str
    advantages: list[Advantage]
    risks: list[Risk]
    interpretation: str


class Technical(StrictModel):
    class MovingAverages(StrictModel):
        ma_20: MetricValue
        ma_50: MetricValue
        ma_200: MetricValue
        price_vs_ma20: Literal["above", "below"]
        price_vs_ma50: Literal["above", "below"]
        price_vs_ma200: Literal["above", "below"]

    class Macd(StrictModel):
        macd_line: MetricValue
        signal_line: MetricValue
        histogram: MetricValue
        signal: Trend

    class BollingerBands(StrictModel):
        upper: MetricValue
        middle: MetricValue
        lower: MetricValue
        width_pct: MetricValue
        position: Literal["upper", "middle", "lower"]

    class StochRsi(StrictModel):
        k: MetricValue
        d: MetricValue
        signal: Literal["overbought", "oversold", "neutral"]

    class Level(StrictModel):
        level: float
        strength: Literal["strong", "moderate", "weak"]

    class SupportResistance(StrictModel):
        supports: list["Technical.Level"]
        resistances: list["Technical.Level"]

    trend: Trend
    moving_averages: MovingAverages
    macd: Macd
    bollinger_bands: BollingerBands
    rsi: MetricValue
    stoch_rsi: StochRsi
    support_resistance: SupportResistance
    interpretation: str


class AnomalousSession(StrictModel):
    date: str
    volume: int
    avg_volume: int
    ratio: float
    price_change_pct: float
    type: Literal["accumulation", "distribution", "neutral"]


class VolumeAndLiquidity(StrictModel):
    avg_volume_30d: MetricValue
    current_volume: MetricValue
    volume_ratio: MetricValue
    obv_trend: Literal["rising", "falling", "flat"]
    obv_signal: Trend
    liquidity_score: float
    bid_ask_spread_pct: MetricValue
    float_shares: MetricValue
    anomalous_sessions: list[AnomalousSession]
    interpretation: str


class Shareholder(StrictModel):
    name: str
    stake_pct: float
    type: Literal["institutional", "insider", "strategic", "state"]
    change_direction: Literal["increased", "decreased", "unchanged", "new"]


class InsiderTransaction(StrictModel):
    date: str
    insider: str
    role: str
    type: Literal["buy", "sell"]
    shares: int
    price: float
    value: float
    currency: str
    source_url: str | None = None


class Shareholders(StrictModel):
    free_float_pct: MetricValue
    institutional_ownership_pct: MetricValue
    insider_ownership_pct: MetricValue
    major_shareholders: list[Shareholder]
    insider_transactions: list[InsiderTransaction]
    interpretation: str


class Case(StrictModel):
    title: str
    description: str
    probability: Impact
    catalysts_or_risks: list[str]


class ValuationMatrix(StrictModel):
    class Quadrant(StrictModel):
        title: str
        description: str

    class Quadrants(StrictModel):
        A: "ValuationMatrix.Quadrant"
        B: "ValuationMatrix.Quadrant"
        C: "ValuationMatrix.Quadrant"
        D: "ValuationMatrix.Quadrant"

    class Momentum(StrictModel):
        signal: MomentumSignal
        label: str
        reasoning: str

    current_quadrant: MatrixQuadrant
    quadrants: Quadrants
    momentum: Momentum


class Verdict(StrictModel):
    overall_score: float
    recommendation: Recommendation
    time_horizon: Literal["short", "medium", "long"]
    price_target: MetricValue
    upside_pct: float
    bull_case: Case
    base_case: Case
    bear_case: Case
    key_watchpoints: list[str]
    valuation_matrix: ValuationMatrix
    interpretation: str


class EquityReport(StrictModel):
    meta: ReportMeta
    company: CompanyInfo
    fundamentals: Fundamentals
    debt_balance: DebtBalance
    trend_condition: TrendCondition
    dividend: Dividend
    key_events: KeyEvents
    advantages_risks: AdvantagesRisks
    technical: Technical
    volume_liquidity: VolumeAndLiquidity
    shareholders: Shareholders
    verdict: Verdict


class EquityReportResponse(StrictModel):
    asset_class: Literal["equity"]
    report: EquityReport
    available_periods: list[ReportPeriod]


Technical.model_rebuild()
ValuationMatrix.model_rebuild()
EquityReport.model_rebuild()
EquityReportResponse.model_rebuild()
