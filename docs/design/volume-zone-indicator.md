# Volume Zone Indicator

## Purpose

The volume zone indicator is a deterministic stock-analysis feature for daily OHLCV
history. It estimates price areas where meaningful volume activity occurred, labels the
observable price-volume behavior in those areas, and exposes confirmation and
invalidation levels for the current scenario.

The indicator does not call AI, OpenAI, prompts, or external classification models. It is
separate from equity report generation. When an equity report snapshot already exists,
the indicator may read its stored free-float metrics as deterministic context; it never
triggers report generation to obtain those values.

## Data And Limits

The MVP uses daily candles from the `stock` service:

- `date_quote`
- `open`
- `high`
- `low`
- `close`
- `volume`

Daily OHLCV is only a proxy. The algorithm cannot know real order flow, aggressive buy or
sell volume, institutional inventory, or the real number of accumulated shares.

The `stock` candle and instrument models do not store a historical free-float time
series. The API therefore returns `historical_free_float_available=false`. If a stored
equity report AI snapshot contains `shareholders.free_float_pct` and
`company.shares_outstanding`, the response sets `current_free_float_used=true` and uses
that point-in-time snapshot only for current free-float turnover context.

## Algorithm

The backend validates candles before calculation. It sorts rows chronologically, excludes
duplicates and invalid OHLC rows, keeps `high == low` sessions with a diagnostic warning,
and treats missing volume as zero with a warning.

The profile divides the historical price range into configurable bins. The default is
`logarithmic_bins` with `target_bin_count=80`, which is safer for instruments whose price
changes by large multiples. Other supported strategies are `percentage_bins`,
`atr_based_bins`, and `fixed_target_bin_count`.

Volume allocation is proportional to the intersection between a candle range and each
price bin. Body, close, and typical-price bonuses can increase a bin weight, but each
candle is renormalized so allocated volume never exceeds that candle's daily volume.

Weighted activity applies optional half-life decay:

```text
0.5 ** (age_in_sessions / half_life_sessions)
```

Raw volume remains unchanged. Old zones therefore become less prominent but are not
deleted from history.

## Zones, Episodes, And Evidence

The profile detector finds contiguous high-activity bins and converts them into price
zones. Each zone can contain multiple activity episodes. A new episode begins after a
configured period without contact with the zone, after a material ATR-based departure
from the zone, or when a maximum episode span is exceeded. Top-level zone activity fields
describe the latest episode, not all historical contacts summed together.

Directional labels are gated by quality:

- minimum effective sessions
- minimum active weeks
- minimum activity-equivalent sessions
- maximum dominant session share
- minimum consistency

Weak zones stay gray as `NEUTRAL_LIQUIDITY` or
`INSUFFICIENT_DIRECTIONAL_EVIDENCE`.

Directional labels also require a minimum evidence score. A low score cannot become
`ACCUMULATION_CANDIDATE` or `DISTRIBUTION_CANDIDATE` only because the balance is slightly
positive or negative.

Evidence is deterministic and grouped into four families:

- activity score
- effort-versus-result proxy
- rejection score
- market structure score

The response exposes evidence codes such as `HIGH_RELATIVE_VOLUME`,
`FAILED_BREAKDOWNS`, and `VOLATILITY_COMPRESSION`. Next UI maps these codes to fixed
Polish labels.

## Causality

Calculations for a day can only use candles available through that day. The API can return
a walk-forward timeline; each point is calculated from a prefix of the history ending at
that date. This protects against repainting historical states with future candles.

The response distinguishes:

- `estimated_start_date`
- `first_detected_at`
- `direction_assigned_at`
- `confirmed_at`
- `invalidated_at`
- `last_active_at`

Confirmation and invalidation levels are state transitions, not display-only lines. For
example, once a demand-side zone is confirmed below its invalidation level for the
configured number of closes, it cannot remain `ACCUMULATION_CANDIDATE` or
`ACCUMULATION_ACTIVE`.

`active_zone` means the zone currently interacting with price. A zone is active only
when the current close is inside the zone, close enough by ATR, or had recent contact.
A strong historical zone far away from price may still be returned in `zones`, but it is
not the active market state.

## Identity, Lifecycle, And Current Role

Three separate concerns are exposed as distinct fields, never collapsed into one:

- the historical behavior signature of the episode (`detected_signature` at first
  detection and `episode_signature` from the full episode, which becomes immutable once
  the episode closes) - this is never downgraded by a later invalidation;
- the episode `lifecycle_status` (`CANDIDATE`, `ACTIVE`, `CONFIRMED`, `INVALIDATED`,
  `CLOSED`);
- the response-time `current_market_role` (for example `FORMER_DEMAND_NOW_SUPPLY`,
  `HISTORICAL_SUPPORT`) which depends on today's price and lives on `current_state`, not
  on the historical episode.

The lifecycle is a monotonic per-episode state machine: `CANDIDATE -> ACTIVE -> CONFIRMED`
or `CANDIDATE/ACTIVE -> INVALIDATED -> CLOSED`. A closed episode is never resurrected back
to `CONFIRMED`; a fresh signal starts a new episode. A candidate becomes `ACTIVE` only
after the candidate conditions hold for `active_hold_sessions`. Confirmation is counted
only from `entered_active_at` forward, candidate invalidation from `first_detected_at`
forward; candles before detection never drive a transition.

The raw directional score is kept as-is and never zeroed. A zone exposes
`raw_directional_score`, a `quality_gate` (`PASSED`/`FAILED`), and `quality_fail_reasons`
explaining why a strong raw score may still not earn a directional label (for example
`MINIMUM_EFFECTIVE_SESSIONS_NOT_MET`).

## Detection Quality

Threshold runs of high-activity bins are split at clear low-volume nodes (a valley at
least `min_local_minimum_drop` below the weaker neighbouring peak, with minimum child
size), then to a hard width cap of `min(max_zone_width_atr * ATR,
center_price * max_zone_width_pct)`. A cluster that still cannot be split into a clean zone
is kept as `BROAD_NEUTRAL_LIQUIDITY` with `directional_classification_allowed=false` rather
than deleted; only clusters spanning almost the whole price range are dropped.

## Two Profiles And Zone Detection

The response returns two profiles with metadata (`structural_profile_metadata`,
`active_profile_metadata`):

- a structural profile (full history, no decay, activity normalized by the contemporaneous
  median volume) which anchors long-term dwell zones;
- an active profile (time decay over a recent lookback window) which surfaces
  historical/high-price zones that activity normalization alone cannot see.

Decay is off by default (`structural_half_life_sessions=None`); the active profile keeps
decay.

The UI exposes three profile display modes (default `Estymowany wolumen`):

- `raw` — bar length from `raw_volume` (full-history shares allocated per price level,
  conserved: `Σ raw_volume ≈ Σ candle volume`); comparable with the lower volume panel;
- `active` — the decayed recent-window profile (current relevance);
- `structural` — bar length from `activity_score` (normalized `weighted_volume`), i.e.
  price acceptance / sustained above-average activity, **not** share count.

These differ only in which field drives bar length over the same bins; `activity_score`
deliberately does not track `raw_volume` (a few high-volume sessions score low on
activity). Each bin also carries `contributing_sessions`; the profile tooltip shows
`raw_volume`, `activity_score`, session count, and the profile's date range. Volume-by-price
is an estimate: a daily candle's volume is spread across its low–high range proportionally,
so it is labeled accordingly and is not exact order flow.

**Detection draws candidate bands from BOTH profiles and merges overlaps.** A band found in
either profile is kept; bands whose price ranges overlap by at least
`zone_merge_overlap_fraction` of the narrower band are merged. Each zone records its
`source_profile` (`STRUCTURAL` / `ACTIVE` / `BOTH`), `structural_strength`,
`active_strength`, and `current_relevance`. Episodes and evidence are always built from
full-history (structural) contributions, so even an active-discovered band stays causal. A
new active zone is not erased because it is not yet significant over ten years, and an old
structural zone is not erased because it had no recent activity.

## Zone Set, Highlighting, And Visibility

`mode=full` (used by the full-page chart) returns every detected zone in `zones`;
`mode=summary` limits `zones` to the highlighted set. `highlighted_zone_ids` always lists
up to three zones (active + nearest demand + nearest supply, or nearest support/resistance
+ strongest structural when no zone is active). The UI exposes visibility modes
`Wszystkie` / `Istotne` / `Aktywne` (default `Istotne`): all detected zones, the
highlighted set, or only zones with an open lifecycle. Historical and invalidated zones are
never dropped from the API response just because they are not highlighted, but the default
chart view favors readability over rendering every historical diagnostic item.

## Evidence Balance Timeline

The lower panel is a **causal, per-day** evidence balance independent of zone selection: a
trailing `evidence_balance_window` of demand-vs-supply pressure (the same effort-vs-result
and rejection primitives used for zones), normalized to `[-1, +1]` with the sign preserved
(`> 0` accumulation, `< 0` distribution, `0` computed-neutral, `null` during warm-up). It
covers the full requested range, not a recent slice; the panel label shows the actual date
range. The per-prefix lifecycle `state` walk is O(n^2) and is computed only in `backtest`
mode; chart modes ship the cheap balance series.

## Active Zone And Nearest Levels

`active_zone` is the zone currently interacting with price; when no zone is recent or close
it is `null` (no fallback to a distant historical zone). The response then exposes
`nearest_zone_above` and `nearest_zone_below` for context. The active zone carries
selection transparency (`selection_reason`, `distance_to_zone_percent`,
`distance_to_zone_atr`, `sessions_since_last_contact`) and a `price_relation`
(`INSIDE_ZONE`, `RETESTING_FROM_ABOVE`, `BROKEN_DOWN`, ...). Visible zones are ordered by
`display_priority` with an explicit `display_role`.

## Directional Phases (Accumulation / Distribution)

`directional_episodes` are raw accumulation/distribution candidates detected from the
daily `market_evidence_balance` series, **independent of profile zones** — a phase can
exist where no liquidity zone formed (and a neutral zone can contain a directional
phase). Detection is a hysteresis state machine: enter a phase when
`|balance| > phase_enter_threshold`, leave it only when balance falls back through
`phase_exit_threshold`, so the regime does not flip every session. A contiguous regime
run of at least `phase_candidate_min` sessions becomes an internal candidate.

Each phase separates the **estimated base** from the **detected signal**. `candidate_at`
is the causal day when the balance regime becomes visible. The box starts at
`estimated_start_at`, found by looking back for a compact base/consolidation with bounded
ATR range, low internal trend, compression, and repeated boundary contacts. `price_low` and
`price_high` are calculated only from that base window, not from later breakout candles.
If a pressure burst has no qualifying base, it stays visible only in the lower evidence
panel and does not become a full `A`/`D` phase box.

The lifecycle status remains monotonic: a phase may become `CONFIRMED` or `INVALIDATED`,
but a confirmed phase is not later rewritten to invalidated because price eventually breaks
the old zone. Later breaks change the current market role of the historical level. The API
therefore exposes `confirmed_at` and `invalidated_at` separately from `estimated_start_at`,
`candidate_at`, and `ended_at`. `linked_zone_ids` lists overlapping liquidity zones (empty
when the phase overlaps none).

The backend also returns `resolved_directional_episodes`, a technical phase set after
same-direction merge, setup-strength filtering, opposite-direction conflict resolution,
and cooldown. This layer is useful for diagnostics and current setup context, but it is
not the final historical annotation layer.

Historical importance is intentionally separated from setup quality. Each phase exposes
`setup_score` (causal, based on evidence balance, duration, and zone linkage) and
`historical_outcome_score` (after-the-fact, based on sign-aware `ret20`, `ret60`,
MFE/MAE, breakout direction, follow-through, and opposite-move penalty). The API returns
`major_directional_phases` for phases that actually explain meaningful follow-through in
the expected direction. These fields use future candles, so they are historical
annotations and must not be used as live trading signals.

The UI draws phases as an optional overlay layer with modes `Off`, `Historical`,
`Current`, and `Debug`. `Historical` uses `major_directional_phases`; `Current` uses the
technical resolved layer for active/candidate setups; `Debug` uses raw
`directional_episodes`. Phase boxes are intentionally unlabeled on the price pane. If the
visible set is small, the outcome marker (`A✓`, `D✓`, `A×`, `D×`) is placed at the
confirmation or invalidation date. This avoids painting the whole historical base as if
the final outcome had been known from the start and prevents the diagnostic A/D layer
from obscuring candles.

## API And Cache

Endpoint:

```text
GET /stock/analysis/{mic}/{symbol}/volume-zones
```

Query parameters:

- `mode=summary|full|backtest`
- `date_from`
- `date_to`
- `include_timeline`
- `max_zones`

The endpoint resolves the instrument by MIC and symbol, reads daily candles, and returns a
typed Pydantic response. Missing instruments return `404`. Too-short histories return
`422`.

Results are cached in stock Redis storage for 15 minutes. The cache key includes MIC,
symbol, mode, date range, timeline flag, maximum zone count, last candle date, stored
free-float snapshot version, calculation version, and configuration version.

For ordinary UI requests, `include_timeline=true` returns a recent causal timeline window
instead of recalculating the entire multi-year history. `mode=backtest` keeps the full
walk-forward timeline.

## UI

Next UI extends the existing ECharts stock chart. For a single candlestick chart it can
show:

- up to three zones
- the active zone
- confirmation and invalidation lines
- a right-side price-axis activity profile built from profile bins
- one lower evidence-balance panel
- a deterministic details panel

Zone rectangles cover the candles that built or resolved the visible zone episode:
from episode start through confirmation, invalidation, or the latest active contact.
Remembered support/resistance levels may still be drawn as dashed lines after that
rectangle, but the hover target is the episode box itself.

Colors show behavior proxies:

- gray: meaningful activity without enough directional evidence
- green: behavior consistent with demand-side absorption proxy
- red: behavior consistent with supply-side absorption proxy

The UI says "Siła dowodów" and does not display probability language.

## Backtest

`mode=backtest` returns MVP walk-forward counts:

- evaluated sessions
- detected zones
- directional and neutral zones
- candidate states
- confirmed and invalidated states
- state changes

Benchmark comparisons against simple breakout, relative-volume breakout,
support/resistance, moving averages, and randomized same-frequency signals are documented
as validation extensions. The MVP does not optimize parameters on the full history.
