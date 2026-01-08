from __future__ import annotations

import uuid
from typing import Any, Optional, List
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel.ext.asyncio.session import AsyncSession

from app.crud.wallet_crud import list_wallets
from app.crud.snapshots_crude import (
    list_fx_rows_for_months, list_deposit_monthly_snapshots, list_brokerage_monthly_snapshots,
    list_metal_monthly_snapshots, list_real_estate_monthly_snapshots, upsert_fx_monthly_snapshot_uow,
    upsert_broacc_monthly_snapshot_uow, upsert_depacc_monthly_snapshot_uow, upsert_metal_monthly_snapshot,
    upsert_real_estate_monthly_snapshot
    )
from app.crud.deposit_account_crud import list_deposit_accounts_for_wallets
from app.crud.transaction_crud import count_transactions_since
from app.crud.brokerage_account_crud import list_brokerage_accounts
from app.crud.broker_event_crud import count_brokerage_events_since
from app.crud.holding_crud import list_holdings
from app.crud.brokerage_deposit_link_crud import list_brokerage_deposit_links
from app.crud.metal_holding_crud import list_metal_holdings_by_wallet
from app.crud.real_estate_crud import list_real_estates
from app.api.services.real_estate import get_latest_price_with_fallback

from app.models.models import DepositAccount, BrokerageAccount
from app.models.enums import Currency

from app.utils.money import dec, fx_convert, safe_ccy
from app.utils.date import month_key, last_n_month_keys
from app.utils.utils import TROY_OUNCE_G, metal_grams

import logging

logger = logging.getLogger(__name__)


async def get_wallet_manager_tree_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    months: int,
    stock_client,
    currency_rate: dict[str, Decimal],
) -> list[dict]:
    """
    Build the wallet-manager "tree" structure for the UI.

    This service aggregates:
      - wallets (base currency per wallet)
      - deposit accounts with balances, health, tx counts and monthly snapshots
      - brokerage accounts with linked cash accounts, holdings valuation, event counts and monthly snapshots
      - metals holdings with quote valuation (fallback to cost basis) and monthly snapshots
      - real estate holdings with price-per-m2 valuation (fallback to purchase price) and monthly snapshots
      - FX tables per month (for snapshot conversion) + "current FX" (for live conversion)

    Args:
        session: SQLAlchemy async database session.
        user_id: Internal user UUID.
        months: How many last months (keys) to include for snapshots.
        stock_client: Client used to fetch latest quotes (must expose `get_latest_quotes_for_symbols`).
        currency_rate: Current FX map used for live conversions (e.g. from NBP).

    Returns:
        A list of wallet dictionaries ready to be returned by the API and consumed by the UI.
    """
    keys = last_n_month_keys(months)
    since = datetime.now(timezone.utc) - timedelta(days=30)

    wallets = await list_wallets(session, user_id=user_id)
    if not wallets:
        return []

    wallet_ids = [w.id for w in wallets]
    base_by_wallet: dict[uuid.UUID, str] = {
        w.id: (safe_ccy(getattr(w, "currency", None), "PLN")) for w in wallets
    }

    fx_rows = await list_fx_rows_for_months(session, month_keys=keys)
    fx_by_month: dict[str, dict[str, Decimal]] = {
        r.month_key: {k: Decimal(str(v)) for k, v in (r.rates_json or {}).items()}
        for r in fx_rows
    }
    
    fx_now = currency_rate or {} 

    cur_mk = month_key()
    fx_cur = fx_by_month.get(cur_mk) or (fx_by_month.get(keys[0]) if keys else None) or {}

    dep_rows: List[DepositAccount] = await list_deposit_accounts_for_wallets(session, wallet_ids=wallet_ids)
    dep_ids = [a.id for a in dep_rows]

    tx_counts = await count_transactions_since(session, dep_account_ids=dep_ids, since=since)

    dep_snaps = await list_deposit_monthly_snapshots(session, wallet_ids=wallet_ids, month_keys=keys)
    dep_snaps_by_acc: dict[uuid.UUID, dict[str, dict]] = {}
    for s in dep_snaps:
        dep_snaps_by_acc.setdefault(s.account_id, {})[s.month_key] = {
            "ccy": s.currency.value,
            "available": s.available,
        }

    bro_accounts: List[BrokerageAccount] = await list_brokerage_accounts(session, wallet_ids=wallet_ids)
    bro_ids = [b.id for b in bro_accounts]

    ev_counts = await count_brokerage_events_since(session, brokerage_ids=bro_ids, since=since)

    bro_snaps = await list_brokerage_monthly_snapshots(session, wallet_ids=wallet_ids, month_keys=keys)
    bro_snaps_by_acc: dict[uuid.UUID, dict[str, dict]] = {}
    for s in bro_snaps:
        bro_snaps_by_acc.setdefault(s.brokerage_account_id, {})[s.month_key] = {
            "ccy": s.currency.value,
            "cash": s.cash,
            "stocks": s.stocks,
        }

    links = await list_brokerage_deposit_links(session, brokerage_account_ids=bro_ids)
    links_by_bro: dict[uuid.UUID, uuid.UUID] = {}
    for ln in links:
        links_by_bro.setdefault(ln.brokerage_account_id, ln.deposit_account_id)

    dep_map: dict[uuid.UUID, tuple[Any, Decimal]] = {}
    for acc in dep_rows:
        dep_map[acc.id] = (acc, dec(getattr(acc.balance, "available", 0)))

    holding_rows = await list_holdings(session, account_ids=bro_ids, with_relations=True)
    holdings_by_bro: dict[uuid.UUID, list[tuple[Any, Any]]] = {}
    all_symbols: list[str] = []
    for h in holding_rows:
        holdings_by_bro.setdefault(h.account_id, []).append((h, h.instrument))
        if getattr(h.instrument, "symbol", None):
            all_symbols.append(h.instrument.symbol)

    uniq_symbols = list(dict.fromkeys(all_symbols))
    quotes_map = await stock_client.get_latest_quotes_for_symbols(symbols=uniq_symbols) if uniq_symbols else {}

    metal_rows = await list_metal_holdings_by_wallet(session, wallet_ids=wallet_ids)
    re_rows = await list_real_estates(session, wallet_ids=wallet_ids)

    metal_snaps_by_wallet_month: dict[tuple[uuid.UUID, str], list[tuple[Decimal, str]]] = {}
    met_snaps = await list_metal_monthly_snapshots(session, wallet_ids=wallet_ids, month_keys=keys)
    for s in met_snaps:
        metal_snaps_by_wallet_month.setdefault((s.wallet_id, s.month_key), []).append((dec(s.value), s.currency.value))

    re_snaps_by_wallet_month: dict[tuple[uuid.UUID, str], list[tuple[Decimal, str]]] = {}
    re_snaps = await list_real_estate_monthly_snapshots(session, wallet_ids=wallet_ids, month_keys=keys)
    for s in re_snaps:
        re_snaps_by_wallet_month.setdefault((s.wallet_id, s.month_key), []).append((dec(s.value), s.currency.value))

    dep_by_wallet: dict[uuid.UUID, list[dict]] = {wid: [] for wid in wallet_ids}
    for acc in dep_rows:
        if acc.account_type == "BROKERAGE":
            continue
        dep_by_wallet[acc.wallet_id].append(
            {
                "id": str(acc.id),
                "name": acc.name,
                "ccy": acc.currency.value,
                "available": dec(getattr(acc.balance, "available", 0)),
                "tx_per_month": tx_counts.get(acc.id, 0),
                "health": {},
                "snapshots": dep_snaps_by_acc.get(acc.id, {}),
            }
        )

    bro_by_wallet: dict[uuid.UUID, list[dict]] = {wid: [] for wid in wallet_ids}
    
    for b in bro_accounts:
        defoult_ccy = base_by_wallet[b.wallet_id]
        items = holdings_by_bro.get(b.id, [])
        logger.info(f"items: {items}")
        positions: list[dict] = []
        missing_quotes = 0
        positions_value = Decimal("0")

        for h, inst in items:
            sym = getattr(inst, "symbol", None)
            q = quotes_map.get(sym) if sym else None
            if not q:
                missing_quotes += 1
                continue

            qty = dec(getattr(h, "quantity", 0))
            price = dec(getattr(q, "price", 0))
            value = qty * price
            cost = qty * dec(getattr(h, "avg_cost", 0))

            pnl_pct = Decimal("0")
            if cost > 0:
                pnl_pct = (value - cost) / cost

            q_ccy = safe_ccy(getattr(q, "currency", None), safe_ccy(getattr(inst, "currency", None), defoult_ccy))
            cv = fx_convert(value, q_ccy, defoult_ccy, fx_now)
            value_out = cv if cv is not None else value

            positions.append(
                {
                    "symbol": sym,
                    "mic": getattr(inst, "mic", None),
                    "value": value,
                    "value_default_ccy": value_out,
                    "pnl_pct": pnl_pct,
                    "currency": q_ccy,
                }
            )
            positions_value += value_out

        positions.sort(key=lambda p: p["value_default_ccy"], reverse=True)

        dep_id = links_by_bro.get(b.id)
        cash_accounts: list[dict] = []
        sum_cash_default_ccy = Decimal("0")
        if dep_id and dep_id in dep_map:
            dep_acc, dep_av = dep_map[dep_id]
            src_ccy = dep_acc.currency.value
            cash_accounts.append(
                {
                    "deposit_account_id": str(dep_acc.id),
                    "name": dep_acc.name,
                    "ccy": src_ccy,
                    "available": dep_av,
                }
            )
            
        cv = fx_convert(dec(dep_av), src_ccy, defoult_ccy, fx_now)
        if cv is not None:
            sum_cash_default_ccy += cv
            
        bro_by_wallet[b.wallet_id].append(
            {
                "id": str(b.id),
                "name": b.name,
                "ccy": defoult_ccy,
                "cash_accounts": cash_accounts,
                "sum_cash_accounts": sum_cash_default_ccy,
                "positions": positions,
                "positions_count": len(positions),
                "positions_value": positions_value,
                "events_per_month": ev_counts.get(b.id, 0),
                "health": {
                    "missing_quotes": missing_quotes,
                    "stale_quotes": False,
                    "projection_mismatch": False,
                },
                "snapshots": bro_snaps_by_acc.get(b.id, {}),
            }
        )

    metal_by_wallet: dict[uuid.UUID, dict] = {
        wid: {"count": 0, 
              "value": Decimal("0"), 
              "ccy": base_by_wallet[wid], 
              "health": {"missing_quotes": 0},
              "items": [],
              }
        for wid in wallet_ids
    }

    metal_symbols = [getattr(mh, "quote_symbol", None) for mh in metal_rows if getattr(mh, "quote_symbol", None)]
    uniq_metal_symbols = list(dict.fromkeys(metal_symbols))
    metal_quotes_map = await stock_client.get_latest_quotes_for_symbols(symbols=uniq_metal_symbols) if uniq_metal_symbols else {}

    for mh in metal_rows:
        wid = mh.wallet_id
        base = base_by_wallet[wid]

        grams = metal_grams(mh)
        sym = getattr(mh, "quote_symbol", None)
        quote = metal_quotes_map.get(sym) if sym else None

        if quote and grams > 0:
            last_price = dec(getattr(quote, "price", 0))
            base_value = (grams / TROY_OUNCE_G) * last_price
            base_ccy = safe_ccy(getattr(quote, "currency", None), "USD")
        else:
            base_value = dec(getattr(mh, "cost_basis", 0))
            base_ccy = safe_ccy(getattr(mh, "cost_currency", None), base)
            if sym:
                metal_by_wallet[wid]["health"]["missing_quotes"] += 1

        v_in_base = base_value if base_ccy == base else (fx_convert(base_value, base_ccy, base, fx_now) or Decimal("0"))

        metal_by_wallet[wid]["count"] += 1
        metal_by_wallet[wid]["value"] += v_in_base
        metal_by_wallet[wid]["ccy"] = base  
        
        metal_by_wallet[wid]["items"].append(
            {
                "name": str(getattr(mh, "metal", None)),
                "quantity": grams,       
                "qty_unit": "g",
                "value": v_in_base,    
                "ccy": base,            
            }
        )

    re_by_wallet: dict[uuid.UUID, dict] = {
        wid: {"count": 0, 
              "value": Decimal("0"), 
              "ccy": base_by_wallet[wid], 
              "health": {"missing_price": 0},
              "items": [],
              }
        for wid in wallet_ids
    }

    price_cache: dict[tuple[str, Optional[str], Optional[str], str], Optional[Any]] = {}

    for r in re_rows:
        wid = r.wallet_id
        base = base_by_wallet[wid]

        re_ccy = safe_ccy(getattr(r, "purchase_currency", None), base)

        key = (str(getattr(r, "type", "")), getattr(r, "country", None), getattr(r, "city", None), re_ccy)
        if key not in price_cache:
            price_cache[key] = await get_latest_price_with_fallback(
                session,
                type=getattr(r, "type", None),
                country=getattr(r, "country", None),
                city=getattr(r, "city", None),
                currency=getattr(r, "purchase_currency", None) or re_ccy,
            )

        price_obj = price_cache[key]
        area = dec(getattr(r, "area_m2", 0))

        if price_obj and area > 0:
            ppm2 = dec(getattr(price_obj, "avg_price_per_m2", 0))
            base_value = area * ppm2
        else:
            re_by_wallet[wid]["health"]["missing_price"] += 1
            base_value = dec(getattr(r, "purchase_price", 0))

        v_in_base = base_value if re_ccy == base else (fx_convert(base_value, re_ccy, base, fx_now) or Decimal("0"))

        re_by_wallet[wid]["count"] += 1
        re_by_wallet[wid]["value"] += v_in_base
        re_by_wallet[wid]["ccy"] = base
        
        re_by_wallet[wid]["items"].append(
            {
                "name": str(getattr(r, "name", "")),
                "city": str(getattr(r, "city", "")),
                "value": v_in_base,    
                "ccy": base,            
            }
        )

    out: list[dict] = []

    for w in wallets:
        base = base_by_wallet[w.id]

        wallet_dict: dict[str, Any] = {
            "id": str(w.id),
            "name": w.name,
            "base_ccy": base,
            "health": {"needs_review": False},
            "deposit_accounts": dep_by_wallet.get(w.id, []),
            "brokerage_accounts": bro_by_wallet.get(w.id, []),
            "metals": metal_by_wallet.get(w.id, {"count": 0, "value": Decimal("0"), "ccy": base, "health": {}}),
            "real_estate": re_by_wallet.get(w.id, {"count": 0, "value": Decimal("0"), "ccy": base, "health": {}}),
            "snapshots": {},
            "fx_by_month": {k: fx_by_month.get(k, {}) for k in keys},  
        }

        for mk in keys:
            fx = fx_by_month.get(mk) or {}
            if not fx:
                continue

            cash_deposit = Decimal("0")
            cash_broker = Decimal("0")
            stocks = Decimal("0")

            for a in wallet_dict["deposit_accounts"]:
                s = (a.get("snapshots") or {}).get(mk)
                if not s:
                    continue
                v = fx_convert(dec(s.get("available", 0)), s.get("ccy", base), base, fx)
                if v is not None:
                    cash_deposit += v

            for b in wallet_dict["brokerage_accounts"]:
                s = (b.get("snapshots") or {}).get(mk)
                if not s:
                    continue
                src = s.get("ccy", base)
                vc = fx_convert(dec(s.get("cash", 0)), src, base, fx)
                vs = fx_convert(dec(s.get("stocks", 0)), src, base, fx)
                if vc is not None:
                    cash_broker += vc
                if vs is not None:
                    stocks += vs

            metals = Decimal("0")
            for val, src_ccy in metal_snaps_by_wallet_month.get((w.id, mk), []):
                v = fx_convert(dec(val), src_ccy, base, fx)
                if v is not None:
                    metals += v

            real_estate = Decimal("0")
            for val, src_ccy in re_snaps_by_wallet_month.get((w.id, mk), []):
                v = fx_convert(dec(val), src_ccy, base, fx)
                if v is not None:
                    real_estate += v

            wallet_dict["snapshots"][mk] = {
                "ccy": base,
                "cash_deposit": cash_deposit,
                "cash_broker": cash_broker,
                "stocks": stocks,
                "metals": metals,
                "real_estate": real_estate,
            }
        out.append(wallet_dict)

    return out


async def create_monthly_snapshot_for_user_service(
    session: AsyncSession,
    user_id: uuid.UUID,
    month_key_snap: str | None,
    currency_rate: dict[str, Decimal],  
    stock_client,
) -> dict:
    """
    Create a monthly snapshot for the user.

    Orchestration-only service:
      - reads current wallet tree inputs (accounts, holdings, metals, real-estate)
      - fetches latest quotes where needed (outside DB transaction)
      - upserts:
          * FX monthly snapshot
          * deposit account monthly snapshots
          * brokerage monthly snapshots (cash + stocks)
          * metal monthly snapshots
          * real-estate monthly snapshots

    Notes:
      - External calls (quotes/CPI sync) are executed BEFORE the DB transaction
        to avoid holding locks while awaiting network I/O.

    Args:
        session: SQLAlchemy async session.
        user_id: User UUID.
        month_key_snap: Optional month key "YYYY-MM"; if None, uses current month_key().
        currency_rate: FX rates used for conversion (e.g. from NBP). Values are Decimal.
        stock_client: Client that can fetch quotes and trigger candle sync.

    Returns:
        (month_key, fx_saved, dep_count, bro_count, metal_count, re_count)
    """
    mk = month_key_snap or month_key()

    async with session.begin():
        await upsert_fx_monthly_snapshot_uow(session, month_key=mk, rates_json=currency_rate)

        wallets = await list_wallets(session, user_id=user_id)
        if not wallets:
            return {"month_key": mk, "ok": True, "counts": {"deposit": 0, "brokerage": 0, "metal": 0, "real_estate": 0}}

        wallet_ids = [w.id for w in wallets]
        base_by_wallet = {w.id: safe_ccy(getattr(w, "currency", None), "PLN") for w in wallets}

        dep_accounts = await list_deposit_accounts_for_wallets(session, wallet_ids=wallet_ids)

        dep_map: dict[uuid.UUID, tuple[str, Decimal]] = {}
        dep_count = 0
        for a in dep_accounts:
            bal = getattr(a, "balance", None)
            available = dec(getattr(bal, "available", 0))
            dep_map[a.id] = (a.currency.value, available)

            await upsert_depacc_monthly_snapshot_uow(
                session,
                wallet_id=a.wallet_id,
                account_id=a.id,
                month_key=mk,
                currency=a.currency,
                available=available,
            )
            dep_count += 1

        bro_accounts = await list_brokerage_accounts(session, wallet_ids=wallet_ids)
        bro_ids = [b.id for b in bro_accounts]

        links = await list_brokerage_deposit_links(session, brokerage_account_ids=bro_ids)
        links_by_bro: dict[uuid.UUID, list] = {}
        for ln in links:
            links_by_bro.setdefault(ln.brokerage_account_id, []).append(ln)

        holding_rows = await list_holdings(session, account_ids=bro_ids, with_relations=True)  
        holdings_by_bro: dict[uuid.UUID, list[tuple[Any, Any]]] = {}
        symbols: list[str] = []
        for h in holding_rows:
            holdings_by_bro.setdefault(h.account_id, []).append((h, h.instrument))
            sym = getattr(h.instrument, "symbol", None)
            if sym:
                symbols.append(sym)

        uniq_symbols = list(dict.fromkeys(symbols))
        quotes_map = await stock_client.get_latest_quotes_for_symbols(symbols=uniq_symbols) if uniq_symbols else {}

        bro_count = 0
        for b in bro_accounts:
            wid = b.wallet_id
            base_ccy = base_by_wallet.get(wid, "PLN")

            cash_base = Decimal("0")
            for ln in links_by_bro.get(b.id, []):
                dep_id = getattr(ln, "deposit_account_id", None)
                if not dep_id:
                    continue

                src = dep_map.get(dep_id)
                if not src:
                    continue

                src_ccy, av = src 
                if src_ccy == base_ccy:
                    cash_base += av
                else:
                    cv = fx_convert(av, src_ccy, base_ccy, currency_rate)
                    if cv is not None:
                        cash_base += cv

            stocks_base = Decimal("0")
            for h, inst in holdings_by_bro.get(b.id, []):
                sym = getattr(inst, "symbol", None)
                q = quotes_map.get(sym) if sym else None
                if not q:
                    continue
                qty = dec(getattr(h, "quantity", 0))
                price = dec(getattr(q, "price", 0))
                val = qty * price

                q_ccy = safe_ccy(getattr(q, "currency", None),
                                 safe_ccy(getattr(inst, "currency", None), base_ccy))

                if q_ccy == base_ccy:
                    stocks_base += val
                else:
                    cv = fx_convert(val, q_ccy, base_ccy, currency_rate)
                    if cv is not None:
                        stocks_base += cv
                        
            await stock_client.sync_daily_candles("CPIYPL.M")

            await upsert_broacc_monthly_snapshot_uow(
                session,
                wallet_id=b.wallet_id,
                brokerage_account_id=b.id,
                month_key=mk,
                currency=base_ccy,
                cash=cash_base,
                stocks=stocks_base,
            )
            bro_count += 1

        metal_rows = await list_metal_holdings_by_wallet(session, wallet_ids=wallet_ids)
        metal_symbols = list(dict.fromkeys([getattr(m, "quote_symbol", None) for m in metal_rows if getattr(m, "quote_symbol", None)]))
        metal_quotes = await stock_client.get_latest_quotes_for_symbols(symbols=metal_symbols) if metal_symbols else {}

        metal_count = 0
        for mh in metal_rows:
            grams = metal_grams(mh)
            sym = getattr(mh, "quote_symbol", None)
            q = metal_quotes.get(sym) if sym else None

            if q and grams > 0:
                last_price = dec(getattr(q, "price", 0))
                value = (grams / TROY_OUNCE_G) * last_price
                ccy_str = safe_ccy(getattr(q, "currency", None), "USD")  
            else:
                value = dec(getattr(mh, "cost_basis", 0))
                ccy_str = safe_ccy(getattr(mh, "cost_currency", None), base_by_wallet.get(mh.wallet_id, "PLN"))

            await upsert_metal_monthly_snapshot(
                session,
                wallet_id=mh.wallet_id,
                metal_holding_id=mh.id,
                month_key=mk,
                currency=Currency(ccy_str),
                value=value,
            )
            metal_count += 1

        re_rows = await list_real_estates(session, wallet_ids=wallet_ids)

        price_cache: dict[tuple[str, Optional[str], Optional[str], str], Any] = {}
        re_count = 0

        for p in re_rows:
            wid = p.wallet_id
            base = base_by_wallet.get(wid, "PLN")
            ccy_str = safe_ccy(getattr(p, "purchase_currency", None), base)
            ccy = Currency(ccy_str)

            key = (str(getattr(p, "type", "")), getattr(p, "country", None), getattr(p, "city", None), ccy_str)
            if key not in price_cache:
                price_cache[key] = await get_latest_price_with_fallback(
                    session,
                    type=getattr(p, "type", None),
                    country=getattr(p, "country", None),
                    city=getattr(p, "city", None),
                    currency=ccy,
                )

            price_obj = price_cache[key]
            area = dec(getattr(p, "area_m2", 0))

            if price_obj and area > 0:
                ppm2 = dec(getattr(price_obj, "avg_price_per_m2", 0))
                value = area * ppm2
            else:
                value = dec(getattr(p, "purchase_price", 0))

            await upsert_real_estate_monthly_snapshot(
                session,
                wallet_id=wid,
                real_estate_id=p.id,
                month_key=mk,
                currency=ccy,
                value=value,
            )
            re_count += 1

        return mk, True, dep_count, bro_count, metal_count, re_count
   