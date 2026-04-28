export type Source     = 'openai' | 'local' | 'manual'
export type Confidence = 'high' | 'medium' | 'low'
export type Direction  = 'up' | 'down' | 'flat'
export type Trend      = 'bullish' | 'bearish' | 'neutral'
export type Impact     = 'high' | 'medium' | 'low'
export type Recommendation = 'strong_buy' | 'buy' | 'hold' | 'reduce' | 'sell'

export type MV<T = number> = {
  value:      T | null
  as_of:      string        // ISO date "2024-12-31"
  source:     Source
  confidence: Confidence
  unit?:      string        // %, x, PLN, osoby …
  note?:      string        // optional clarifying comment
}

export type ReportMeta = {
  symbol:       string      // "PKBX"
  mic:          string      // "XWAR"
  period:       string      // "2025-Q1"
  generated_at: string      // ISO datetime
  valid_until:  string      // ISO date  (typically +90 days)
  report_type:  'equity'
  source_versions: {
    price_data_as_of:    string
    fundamentals_as_of:  string
    model:               string   // "gpt-4o"
  }
}

export type ReportPeriod = {
  period:       string
  generated_at: string
  is_current:   boolean
}


export type CompanyInfo = {
  name:            string
  full_name:       string
  description:     string    // 2–3 sentences: what the company does
  sector:          string
  industry:        string
  country:         string
  exchange:        string
  founded:         string
  employees:       MV<number>
  ceo:             string
  ceo_since:       string
  headquarters:    string
  is_leader_in:    string[]
  main_products:   string[]
  key_competitors: string[]
  market_position: string
  website:         string
  isin:            string
  price: {
    current:        number
    currency:       string
    change_1d_pct:  number
    change_ytd_pct: number
    week_52_high:   number
    week_52_low:    number
    market_cap:     number
    as_of:          string
  }
}

export type Fundamentals = {
  ebitda_margin:       MV     // % EBITDA / Revenue
  roe:                 MV     // %  Return on Equity
  roic:                MV     // %  Return on Invested Capital
  ocf:                 MV     // PLN Trailing 12m operating cash flow
  fcf:                 MV     // PLN  Free Cash Flow
  fcf_yield:           MV     // %  FCF / Market Cap
  pe_ratio:            MV     // x  Price / EPS
  ev_ebitda:           MV     // x  Enterprise Value / EBITDA
  pb_ratio:            MV     // x  Price / Book
  ps_ratio:            MV     // x  Price / Sales
  discount_from_peak_pct: MV  // %  discount from 52w high
  bvps:                MV     // PLN Book value per share
  revenue_ttm:         MV     // PLN Trailing 12m revenue
  ebitda_ttm:          MV     // PLN Trailing 12m EBITDA
  net_income_ttm:      MV     // PLN Trailing 12m net income
  eps_ttm:             MV     // PLN Trailing 12m EPS
  interpretation:      string
}

export type DebtBalance = {
  cash_and_equivalents:  MV   // PLN
  net_debt:              MV   // PLN  = total debt − cash
  net_debt_ebitda:       MV   // x
  current_ratio:         MV   // x   current assets / current liabilities
  quick_ratio:           MV   // x   (current assets − inventory) / current liabilities
  interest_coverage:     MV   // x   EBIT / interest expense
  de_ratio:              MV   // x   Debt / Equity
  capex:                 MV   // PLN
  capex_to_depreciation: MV   // x   CAPEX / D&A
  total_assets:          MV   // PLN
  equity:                MV   // PLN
  interpretation:        string
}

export type ScoreItem = {
  score:     number   // 1–10
  reasoning: string
}

export type HistoryYear = {
  year:               number
  revenue:            number | null   // PLN mln
  ebitda:             number | null   // PLN mln
  ebitda_margin_pct:  number | null   // %
  net_income:         number | null   // PLN mln
  eps:                number | null   // PLN
  roe_pct:            number | null   // %
  net_debt_ebitda:    number | null   // x
  dividend_per_share: number | null   // PLN
  direction:          Direction
}

export type TrendCondition = {
  scores: {
    profitability:         ScoreItem
    balance_sheet:         ScoreItem
    earnings_quality:      ScoreItem
    revenue_growth:        ScoreItem
    market_valuation:      ScoreItem
    management_quality:    ScoreItem
    competitive_advantage: ScoreItem
    industry_outlook:      ScoreItem
    overall:               number
  }
  history:          HistoryYear[]
  positive_signals: string[]
  negative_signals: string[]
  interpretation:   string
}

export type DividendHistory = {
  year:               number
  dividend_per_share: number | null
  yield_pct:          number | null
  payout_ratio_pct:   number | null
  paid:               boolean
}

export type Dividend = {
  dividend_yield:       MV
  payout_ratio:         MV
  dividend_growth_3y:   MV
  last_dividend: {
    amount:   number
    currency: string
    ex_date:  string
    pay_date: string
  } | null
  history:              DividendHistory[]
  is_dividend_stock:    boolean
  dividend_consistency: 'consistent' | 'irregular' | 'none'
  interpretation:       string
}

export type KeyEvent = {
  date:        string
  title:       string
  description: string
  impact:      Impact
  confidence:  Confidence
}

export type UpcomingDate = {
  date:  string
  event: string
  type:  'earnings' | 'dividend' | 'agm' | 'other'
}

export type KeyEvents = {
  positive:       KeyEvent[]
  negative:       KeyEvent[]
  upcoming_dates: UpcomingDate[]
  interpretation: string
}

export type Advantage = {
  title:       string
  description: string
  strength:    'strong' | 'moderate' | 'weak'
}

export type Risk = {
  title:       string
  description: string
  severity:    Impact
  probability: Impact
}

export type AdvantagesRisks = {
  moat_score:     number    // 1–10
  moat_type:      string
  advantages:     Advantage[]
  risks:          Risk[]
  interpretation: string
}

export type Technical = {
  trend: Trend
  moving_averages: {
    ma_20:          MV
    ma_50:          MV
    ma_200:         MV
    price_vs_ma20:  'above' | 'below'
    price_vs_ma50:  'above' | 'below'
    price_vs_ma200: 'above' | 'below'
  }
  macd: {
    macd_line:   MV
    signal_line: MV
    histogram:   MV
    signal:      Trend
  }
  bollinger_bands: {
    upper:    MV
    middle:   MV
    lower:    MV
    width_pct: MV
    position: 'upper' | 'middle' | 'lower'
  }
  rsi:       MV
  stoch_rsi: {
    k:      MV
    d:      MV
    signal: 'overbought' | 'oversold' | 'neutral'
  }
  support_resistance: {
    supports:    Array<{ level: number; strength: 'strong' | 'moderate' | 'weak' }>
    resistances: Array<{ level: number; strength: 'strong' | 'moderate' | 'weak' }>
  }
  interpretation: string
}

export type AnomalousSession = {
  date:             string
  volume:           number
  avg_volume:       number
  ratio:            number
  price_change_pct: number
  type:             'accumulation' | 'distribution' | 'neutral'
}

export type VolumeAndLiquidity = {
  avg_volume_30d:     MV
  current_volume:     MV
  volume_ratio:       MV   // current / 30d avg
  obv_trend:          'rising' | 'falling' | 'flat'
  obv_signal:         Trend
  liquidity_score:    number   // 1–10
  bid_ask_spread_pct: MV
  float_shares:       MV
  anomalous_sessions: AnomalousSession[]
  interpretation:     string
}

export type Shareholder = {
  name:             string
  stake_pct:        number
  type:             'institutional' | 'insider' | 'strategic' | 'state'
  change_direction: 'increased' | 'decreased' | 'unchanged' | 'new'
}

export type InsiderTransaction = {
  date:     string
  insider:  string
  role:     string
  type:     'buy' | 'sell'
  shares:   number
  price:    number
  value:    number
  currency: string
  source_url?: string | null
}

export type Shareholders = {
  free_float_pct:             MV
  institutional_ownership_pct: MV
  insider_ownership_pct:      MV
  major_shareholders:         Shareholder[]
  insider_transactions:       InsiderTransaction[]
  interpretation:             string
}

export type Case = {
  title:                  string
  description:            string
  probability:            Impact
  catalysts_or_risks:     string[]
}

export type MatrixQuadrant = 'A' | 'B' | 'C' | 'D'
export type MomentumSignal = 'buy_now' | 'accumulate' | 'wait' | 'too_expensive' | 'avoid'

export type ValuationMatrix = {
  current_quadrant: MatrixQuadrant
  quadrants: {
    A: { title: string; description: string }
    B: { title: string; description: string }
    C: { title: string; description: string }
    D: { title: string; description: string }
  }
  momentum: {
    signal:    MomentumSignal
    label:     string
    reasoning: string
  }
}

export type Verdict = {
  overall_score:    number          // 1–10
  recommendation:   Recommendation
  time_horizon:     'short' | 'medium' | 'long'
  price_target:     MV
  upside_pct:       number
  bull_case:        Case
  base_case:        Case
  bear_case:        Case
  key_watchpoints:  string[]        // What to monitor
  valuation_matrix: ValuationMatrix
  interpretation:   string
}

export type EquityReport = {
  meta:             ReportMeta
  company:          CompanyInfo
  fundamentals:     Fundamentals
  debt_balance:     DebtBalance
  trend_condition:  TrendCondition
  dividend:         Dividend
  key_events:       KeyEvents
  advantages_risks: AdvantagesRisks
  technical:        Technical
  volume_liquidity: VolumeAndLiquidity
  shareholders:     Shareholders
  verdict:          Verdict
}
