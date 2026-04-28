from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from .schemas import (
    StrictModel,
    MetricValue,
    DebtBalance,
    TrendCondition,
    DividendHistory,
    KeyEvents,
    AdvantagesRisks,
    Shareholders,
    Case,
    ValuationMatrix,
    Recommendation,
)


class CompanyProfile(StrictModel):
    name: str | None = None
    full_name: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None
    founded: str | None = None
    employees: MetricValue
    ceo: str | None = None
    ceo_since: str | None = None
    headquarters: str | None = None
    is_leader_in: list[str] = Field(default_factory=list)
    main_products: list[str] = Field(default_factory=list)
    key_competitors: list[str] = Field(default_factory=list)
    market_position: str | None = None
    website: str | None = None
    isin: str | None = None
    shares_outstanding: MetricValue


class AiFundamentals(StrictModel):
    ebitda_margin: MetricValue
    roe: MetricValue
    roic: MetricValue
    ocf: MetricValue
    fcf: MetricValue
    bvps: MetricValue
    revenue_ttm: MetricValue
    ebitda_ttm: MetricValue
    net_income_ttm: MetricValue
    eps_ttm: MetricValue
    interpretation: str


class AiDividend(StrictModel):
    class LastDividend(StrictModel):
        amount: float
        currency: str
        ex_date: str
        pay_date: str

    payout_ratio: MetricValue
    last_dividend: LastDividend | None
    history: list[DividendHistory]
    is_dividend_stock: bool
    dividend_consistency: Literal["consistent", "irregular", "none"]
    interpretation: str


class AiVerdict(StrictModel):
    overall_score: float
    recommendation: Recommendation
    time_horizon: Literal["short", "medium", "long"]
    price_target: MetricValue
    bull_case: Case
    base_case: Case
    bear_case: Case
    key_watchpoints: list[str]
    valuation_matrix: ValuationMatrix
    interpretation: str


class EquityAiPayload(StrictModel):
    model_config = ConfigDict(extra="forbid")

    company: CompanyProfile
    fundamentals: AiFundamentals
    debt_balance: DebtBalance
    trend_condition: TrendCondition
    dividend: AiDividend
    key_events: KeyEvents
    advantages_risks: AdvantagesRisks
    shareholders: Shareholders
    verdict: AiVerdict
