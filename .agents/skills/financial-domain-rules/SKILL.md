---
name: financial-domain-rules
description: Use when reviewing or changing FinancialManager financial logic, including wallet, accounts, transactions, brokerage flows, holdings, gains, balances, debts, goals, alerts, reports, or money calculations.
---

# Financial Domain Rules

Use this skill when a change affects financial correctness.

Always identify the financial rule being changed or verified.

For money-related behavior, tests should make the business scenario visible:

- currency
- opening balance
- transaction amount
- transaction type
- expected cash effect
- expected final balance
- expected holdings change where applicable
- expected realized or unrealized gain where applicable
- expected rounding behavior

Important edge cases:

- zero amount
- negative amount
- decimal precision
- rounding boundaries
- same-day transactions
- empty account
- insufficient cash
- partial sale of holdings
- duplicate import rows
- missing or malformed input
- multiple currencies in the same scenario
- brokerage average price after multiple purchases at different prices

Rules:

- Do not verify financial behavior only by HTTP status code.
- Verify the resulting financial state.
- For critical financial behavior, include negative paths where practical.
- For ownership-sensitive financial behavior, check that another user cannot access or modify the resource.
- Do not change financial calculations without adding or updating related tests.

Coverage priority:

- `wallet` has the lowest test coverage (≈2%) and the highest financial risk. Treat any untested wallet financial logic as the highest-priority coverage target.