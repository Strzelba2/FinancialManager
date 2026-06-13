# Brokerage Holding Events

## Purpose

Brokerage holdings are derived from auditable brokerage events. The wallet service must
support market trades, splits, manual corrections, and corporate instrument conversions
without silently editing holdings.

## Scope

This design covers wallet brokerage events used by Next UI holdings and brokerage event
pages:

- `BUY` and `SELL`
- `SPLIT`
- `ADJUSTMENT`
- `CONVERSION`

CSV import remains partial for brokerage trade rows. Manual holding actions are created
from `/brokerage/holdings`.

BoSSA full-history CSV import supports brokerage events and cash ledger rows in PLN,
USD, and EUR. Missing `Saldo po operacji` values are calculated when the file contains a
full history ordered with the oldest rows at the bottom and newest rows at the top.

Stock is the source of truth for instruments. Wallet stores only a local instrument
mirror needed for holdings and events. The mirror is created or updated after stock
successfully resolves `symbol + mic`; wallet does not create instruments from raw import
text.

## Business Rules

`SPLIT` changes the same instrument only:

- `quantity *= split_ratio`
- `avg_cost /= split_ratio`
- no cash transaction is created
- no capital gain is created

`ADJUSTMENT` sets a holding baseline:

- target quantity is stored in `quantity`
- target average cost is stored in `price`
- a note is required
- no cash transaction is created
- no capital gain is created

`CONVERSION` represents a corporate action such as rebranding, merger conversion,
split-with-symbol-change, or reverse-split-with-symbol-change:

- source instrument is stored in `instrument_id`
- target instrument is stored in `target_instrument_id`
- source quantity is stored in `quantity`
- target quantity is `quantity * split_ratio`
- cost basis is carried from the source holding to the target holding
- target average cost is recalculated from carried cost and target quantity
- a note is required, for example `WORKSERV -> GIGROUP, scalenie 1:5`
- no cash transaction is created
- no capital gain is created

The service rejects a conversion when:

- the target instrument is missing
- target instrument equals the source instrument
- source quantity is not positive
- ratio is not positive
- the source holding does not have enough quantity

BoSSA cash balances are calculated before import when `Saldo po operacji` is absent or
empty:

- rows are processed from oldest to newest, using the source file bottom-to-top order
- running balances are tracked separately for PLN, USD, and EUR
- if a row already has `Saldo po operacji`, that provided value is used as the currency
  balance checkpoint
- the wallet import still validates `previous balance + amount == amount_after` per
  linked cash subaccount before writing transactions
- USD and EUR rows require linked brokerage cash subaccounts before any row is written

Brokerage BUY and SELL events always need a cash-settlement path. If the instrument is
quoted outside the base cash currencies, for example CHF or GBP, the event must include
`settlement_currency` in `PLN`, `USD`, or `EUR` and an `fx_rate` from instrument currency
to settlement currency. The service rejects such events before updating holdings when the
settlement currency or FX rate is missing. Holding-only changes should use `SPLIT`,
`ADJUSTMENT`, or `CONVERSION`, not a cash trade with omitted settlement data.

BoSSA missing instruments are blocking:

- parser rows with unresolved instruments are marked `NEEDS_REVIEW`
- `NEEDS_REVIEW` rows remain visible in the Next UI preview
- the Next UI disables import while any `NEEDS_REVIEW` row is present
- wallet preflight rejects payloads containing `NEEDS_REVIEW` or trade rows without
  `instrument_symbol` and `instrument_mic`
- wallet also resolves every trade instrument in stock before writing any events or cash
  transactions

Manual instruments are added in stock with an optional full quote source URL:

```text
quote_source = https://quotes.example.com/q/?s=lnga.uk
```

The stock manual refresh reads all instruments with non-empty `quote_source`, parses the
quote source page, and upserts `quote_latest`. This is intended for occasional foreign
instruments that are not covered by the standard market table ingestors.

## API Contract

Manual brokerage events are created through:

```text
POST /wallet/brokerage/event
```

`CONVERSION` payload extends the standard brokerage event payload with:

```json
{
  "kind": "CONVERSION",
  "target_instrument_symbol": "GIG",
  "target_instrument_mic": "XWAR",
  "target_instrument_name": "GIGROUP SA"
}
```

The response includes `target_instrument_id` for conversion auditability.

BoSSA full-history import is created through:

```text
POST /wallet/brokerage/history/import
```

Blocking preflight errors return `422` and no rows are written.

Manual stock administration is exposed through:

```text
POST /stock/markets
POST /stock/instruments
GET /stock/instruments/resolve?mic=XLON&symbol=LNGA.UK
```

`POST /stock/instruments` accepts `quote_source` as an optional full quote source URL.

## Data Model Impact

`brokerage_events` has a nullable `target_instrument_id` foreign key to `instruments`.
It is used only for corporate conversion events. Older event kinds keep this field null.

`stock.instrument` has nullable `quote_source` for manually managed quote source pages.
`wallet.instruments.symbol` supports symbols up to 12 characters so wallet mirrors can
store symbols such as `LNGA.UK`.

## Security Considerations

Ownership remains enforced at the brokerage account boundary. The route verifies that the
authenticated user owns the target brokerage account before the event is applied.

Instrument trust is enforced across services: stock must know the instrument before
wallet records brokerage events or creates a local mirror. This avoids silently creating
holdings from unverified import text.

## Test Expectations

Evidence expected from the testing process:

- wallet unit tests for split, adjustment, conversion, migration structure, and
  oversell diagnostics
- component/API tests for BoSSA generated cash balances in PLN, USD, and EUR and
  persisted import into linked cash subaccounts
- unit and component/API tests for BoSSA all-or-nothing missing instrument preflight
- stock unit tests for quote source page parsing and quote_source refresh without live
  network calls
- component/API tests for manual stock market and instrument creation with quote_source
- Next UI unit tests for route validation and `/brokerage/holdings` payloads
- Next UI unit tests for BoSSA import blocking and manual instrument creation payloads
- component/API test for persisted conversion state and preserved cost basis
