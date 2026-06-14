export type Currency = 'PLN' | 'USD' | 'EUR'

export type AccountType = 'CURRENT' | 'SAVINGS' | 'BROKERAGE' | 'CREDIT'

export type Transaction = {
  id: string
  amount: string
  description: string
  balance_before: string
  balance_after: string
  date_transaction: string
  account_id: string
  category: string | null
  status: string | null
}

export type AccountListItem = {
  id: string
  name: string
  bank_id: string
  account_type: string
  currency: Currency
  available: string | null
  blocked: string | null
  last_transactions: Transaction[]
}

export type BrokerageAccountListItem = {
  id: string
  name: string
  totals_by_currency: Record<string, string>  // { PLN: "1234.56", USD: "500.00" }
}

export type DebtItem = {
  id: string
  name: string
  lander: string
  amount: string
  currency: Currency
  interest_rate_pct: string
  monthly_payment: string
  end_date: string
}

export type RealEstateItem = {
  id: string
  wallet_id: string
  name: string
  country: string | null
  city: string | null
  type: string | null
  area_m2: string | null
  purchase_price: string
  purchase_currency: Currency | null
  price: string | null
}

export type MetalHoldingItem = {
  id: string
  wallet_id: string
  metal: string
  grams: string
  cost_basis: string
  cost_currency: Currency | null
  price: string | null
  price_currency: Currency | null
}

export type PositionPerformance = {
  symbol: string
  quantity: string
  avg_cost: string
  price: string
  currency: Currency
  value: string
  cost: string
  pnl_amount: string
  pnl_pct: string   // decimal fraction, e.g. "0.0423" = 4.23%
}

export type BrokerageEventItem = {
  date: string        
  sym: string
  type: string         // BrokerageEventKind: BUY | SELL | DIV | FEE | SPLIT | ADJUSTMENT …
  qty: string
  price: string
  value: string | null // total value; if null compute as qty × price
  ccy: string
  account: string
}

export type RecurringExpenseItem = {
  id: string
  name: string
  category: string | null
  amount: string
  currency: Currency
  due_day: number
  account: string | null
  note: string | null
}

export type RecurringExpenseOut = RecurringExpenseItem & {
  wallet_id: string
}

export type DashFlowMonthItem = {
  month: string
  income_by_currency: Record<string, string>
  expense_by_currency: Record<string, string>
  tax_by_currency?: Record<string, string>
  capital_by_currency: Record<string, string>
}

export type WalletListItem = {
  id: string
  name: string
  accounts: AccountListItem[]
  brokerage_accounts: BrokerageAccountListItem[]
  debts: DebtItem[]
  real_estates: RealEstateItem[]
  metal_holdings: MetalHoldingItem[]
  capital_gains_deposit_ytd: Record<string, string>
  capital_gains_broker_ytd: Record<string, string>
  capital_gains_real_estate_ytd: Record<string, string>
  capital_gains_metal_ytd: Record<string, string>
  expense_ytd_by_currency: Record<string, string>
  income_ytd_by_currency: Record<string, string>
  top_gainers: PositionPerformance[]
  top_losers: PositionPerformance[]
  last_brokerage_events: BrokerageEventItem[]
  recurring_expenses_top: RecurringExpenseItem[]
  dash_flow_8m: DashFlowMonthItem[]
}

export type YearGoalOut = {
  id: string
  wallet_id: string
  year: number
  rev_target_year: string
  exp_budget_year: string
  capital_gain_target_year: string
  currency: Currency
}

export type FavoriteItem = {
  sym: string
  pl_pct: string   // percentage points from quote change_pct, e.g. "4.23" = 4.23%
  pl_abs: string   // absolute P/L in item currency
  currency: string
}

export type PriceAlert = {
  id: string
  sym: string
  enabled: boolean
  one_shot: boolean
  below_price: string | null
  above_price: string | null
  current_price: string | null
  currency: string | null
  created_at: string | null
  last_triggered: string | null
  expires_at: string | null
}

export type UserNote = {
  id: string
  user_id: string
  text: string
  created_at: string
  updated_at: string
}

export type WalletCreationResponse = WalletListItem

export type WalletSyncResponse = {
  user_id: string
  first_name: string
  wallets: WalletListItem[]
  banks: { id: string; name: string; shortname: string }[]
  last_favorite_items: FavoriteItem[]
  last_price_alerts: PriceAlert[]
  assets_8m_total: { months: string[]; values: number[] } | null
  cpi_8m: { index_by_month: Record<string, number> } | null
}

export type AccountCreationResponse = {
  id: string
  name: string
  account_type: string
  currency: Currency
}
