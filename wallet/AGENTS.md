# Wallet Agent Guide

Follow the root `AGENTS.md` first. This file adds service-specific rules for `wallet`.

## Scope

`wallet` is a FastAPI service responsible for wallets, accounts, transactions, brokerage
flows, holdings, gains, alerts, recurring expenses, debts, goals, clients, CRUD modules,
validators, schemas, and financial state.

## Risk Profile

Treat `wallet` as the highest business-risk backend service. Changes can affect balances,
cash movement, holdings, gains, account ownership, and sensitive financial data.

Critical areas:

- money calculations
- wallet and account CRUD
- transaction lifecycle
- brokerage buy/sell flows
- holdings and gains
- debts, goals, alerts, and recurring expenses
- ownership and cross-user access
- migrations affecting financial data
- API response contracts used by `next-ui`

## Working Rules

- Do not change financial behavior without identifying the business rule being changed.
- Verify resulting financial state, not only HTTP status codes.
- Preserve API contracts unless the user explicitly requests a contract change.
- When endpoint behavior changes, update API/component tests and frontend usage where
  applicable.
- Use deterministic fixtures or factories for users, wallets, accounts, transactions,
  holdings, instruments, and auth headers.
- Keep unit tests isolated from real external services.
- Do not weaken coverage gates or exclusions without explaining the risk.

## Test Expectations

For money-related behavior, tests should show:

- currency
- opening balance
- transaction amount and type
- expected cash effect
- expected final balance
- expected holdings change
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

## Verification

Use the smallest relevant command:

```bash
make unit-test-wallet
make coverage-unit-wallet
```

For public API behavior or cross-service assumptions:

```bash
make component-test
make integration-test
```
