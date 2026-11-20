"""Championship 4.0: source-labelled, research-only valuation triage for 200 stocks.

IMPORTANT: Outputs are model hypotheses, never independently validated intrinsic
values, executable quotes, or trading instructions. No broker, no order APIs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
REQUIRED_COUNT = 200
FIELDS = [
    "ticker", "company", "group", "price_currency", "last_daily_close", "quote_date",
    "data_status", "fundamental_currency", "fiscal_as_of", "snapshot_utc",
    "model_status", "model_type", "model_quality", "bear_value", "base_value",
    "bull_value", "model_watch_entry", "model_deep_entry", "pct_to_watch_entry",
    "upside_to_base_pct", "revenue_growth_input", "fcf_input", "fcf_basis",
    "shares_input", "roe_input", "book_value_input", "model_assumptions",
    "source", "caveats", "risk_note", "manual_validation", "review_flag",
]
DATA_SOURCE = "Yahoo Finance via unofficial yfinance; company filings NOT verified"


def number(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def positive(v: Any) -> float | None:
    x = number(v)
    return x if x is not None and x > 0 else None


def percentage(current: float | None, target: float | None) -> float | None:
    return round((current / target - 1) * 100, 2) if current and target and target > 0 else None


def date_from_unix(v: Any) -> datetime | None:
    n = number(v)
    if n is None or n <= 0:
        return None
    try:
        return datetime.fromtimestamp(n, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def as_of(info: dict[str, Any]) -> datetime | None:
    return date_from_unix(info.get("mostRecentQuarter")) or date_from_unix(info.get("lastFiscalYearEnd"))


def classified(info: dict[str, Any], meta: dict) -> str:
    sector = str(info.get("sector") or "").lower()
    industry = str(info.get("industry") or "").lower()
    group = str(meta.get("sector") or "").lower()
    ticker = str(meta.get("ticker") or "").upper()
    # Distinguish leveraged deposit-takers/insurers from financial technology and
    # asset managers: a justified-bank-P/B model must not price Visa or Coinbase.
    book_roe_names = {
        "JPM", "BAC", "GS", "MS", "C", "WFC", "PGR", "CBA.AX", "NAB.AX",
        "WBC.AX", "ANZ.AX", "MQG.AX", "QBE.AX", "SUN.AX", "IAG.AX",
        "HSBC", "UBS", "RY", "TD", "IBN"
    }
    cashflow_payments_and_exchanges = {"V", "MA", "PYPL", "XYZ", "ICE", "CME"}
    financial_specialist = {
        "COIN", "HOOD", "SOFI", "AFRM", "BRK-B", "BLK", "SCHW",
        "KKR", "BX", "APO", "NU"
    }
    resource_names = {"BHP.AX", "RIO.AX", "FMG.AX", "MIN.AX", "WDS.AX", "LYC.AX",
                      "LOT.AX", "GG8.AX", "SFR.AX", "PDN.AX", "BOE.AX", "PLS.AX",
                      "XOM", "CVX", "COP", "OXY", "SLB", "EOG", "MPC",
                      "VLO", "CCJ", "UEC", "UUUU", "LEU", "FCX", "NEM", "AEM", "PAAS"}
    if ticker in financial_specialist:
        return "SPECIALIST_RESEARCH_REQUIRED"
    if ticker in cashflow_payments_and_exchanges:
        return "FCF_TO_EQUITY"
    if ticker in book_roe_names or "insurance" in industry or "banks" in industry:
        return "FINANCIAL_BOOK_ROE"
    if "financial" in sector or "asset management" in industry or "credit services" in industry:
        return "SPECIALIST_RESEARCH_REQUIRED"
    if ticker in resource_names or any(k in sector for k in ("basic materials", "energy")) or "resources" in group:
        return "CYCLICAL_NEEDS_MULTIYEAR"
    if any(k in sector or k in industry for k in ("real estate", "reit", "biotechnology")):
        return "SPECIALIST_RESEARCH_REQUIRED"
    return "FCF_TO_EQUITY"


def equity_fcf_dcf(fcf_per_share: float, growth: float, discount: float, terminal_growth: float = .02) -> float:
    """Illustrative discounted equity free cash flow, not a validated investment valuation."""
    if fcf_per_share <= 0 or discount <= terminal_growth + .035 or not (-.3 <= growth <= .3):
        raise ValueError("Unsafe cash-flow model assumptions")
    cash = fcf_per_share
    pv = 0.0
    for year in range(1, 6):
        cash *= 1 + growth
        pv += cash / (1 + discount) ** year
    terminal = cash * (1 + terminal_growth) / (discount - terminal_growth)
    return pv + terminal / (1 + discount) ** 5


def model_fcf(base_fcf_per_share: float, revenue_growth: float | None,
              market_cap: float | None, vol: float | None) -> tuple[tuple[float, float, float], str, float]:
    # Conservative caps prevent unsupportable extrapolation of one year's growth.
    base_g = max(-.06, min(.10, (revenue_growth or 0.0) * .5))
    risk = .14
    if market_cap is None or market_cap < 2e9:
        risk += .025
    if vol is not None and vol >= 80:
        risk += .025
    if vol is not None and vol >= 130:
        risk += .02
    bear = equity_fcf_dcf(base_fcf_per_share * .8, max(-.12, base_g - .06), risk + .03, .01)
    base = equity_fcf_dcf(base_fcf_per_share, base_g, risk, .02)
    bull = equity_fcf_dcf(base_fcf_per_share * 1.10, min(.16, base_g + .05), max(.105, risk - .025), .025)
    assumptions = (f"equity FCF/share; 5-year cash-flow DCF; baseline growth={base_g:.1%}; "
                   f"baseline discount={risk:.1%}; terminal growth=2%; bear uses 20% "
                   "FCF haircut and higher discount rate; bull uses optimistic assumptions")
    return (bear, base, bull), assumptions, risk


def model_book_roe(book_per_share: float, roe: float) -> tuple[tuple[float, float, float], str]:
    if book_per_share <= 0 or not (.045 <= roe <= .35):
        raise ValueError("Book value/ROE insufficient for indicative financial model")
    growth = .02
    base_cost = .125
    bear = book_per_share * max(.0, (roe * .75 - growth) / (.155 - growth))
    base = book_per_share * max(.0, (roe - growth) / (base_cost - growth))
    bull = book_per_share * max(.0, (min(.35, roe * 1.15) - growth) / (.105 - growth))
    assumptions = ("illustrative justified P/B = (ROE - 2% long-run growth) / "
                   "(cost of equity - 2%); 12.5% base cost of equity; bear/bull ROE "
                   "and discount-rate sensitivity; regulatory capital unverified")
    return (bear, base, bull), assumptions


def get_fundamentals(ticker: str) -> dict:
    """Fetch limited public Yahoo financial fields. No financial statements verified."""
    import yfinance as yf

    item = yf.Ticker(ticker)
    info = item.get_info()
    if not isinstance(info, dict) or not info:
        raise ValueError("Yahoo fundamental metadata missing")
    # Separate optional historical check for cyclicals, to avoid using single-year peaks.
    historical_fcf = []
    if classified(info, {"ticker": ticker, "sector": ""}) == "CYCLICAL_NEEDS_MULTIYEAR":
        try:
            frame = item.get_cashflow(freq="yearly")
            for key in ("Free Cash Flow", "FreeCashFlow"):
                if frame is not None and not frame.empty and key in frame.index:
                    historical_fcf = [float(x) for x in frame.loc[key].tolist()
                                      if positive(x) is not None]
                    break
        except Exception:
            pass  # Missing financial statements produce an unvalued row, not fake numbers.
    return {"info": info, "annual_fcf": historical_fcf}


def evaluate(meta: dict, price_row: dict, feed: dict | None, now: datetime) -> dict:
    ticker = meta["ticker"]
    price = positive(price_row.get("price"))
    currency = price_row.get("currency") or ("AUD" if ticker.endswith(".AX") else "USD")
    out = {
        "ticker": ticker, "company": meta.get("name", ""), "group": meta.get("sector", ""),
        "price_currency": currency, "last_daily_close": price,
        "quote_date": price_row.get("quote_date", ""),
        "data_status": price_row.get("data_status", ""),
        "fundamental_currency": None, "fiscal_as_of": None, "snapshot_utc": now.isoformat(),
        "model_status": "NOT MODELLED", "model_type": "NONE", "model_quality": "UNVERIFIED",
        "bear_value": None, "base_value": None, "bull_value": None,
        "model_watch_entry": None, "model_deep_entry": None,
        "pct_to_watch_entry": None, "upside_to_base_pct": None,
        "revenue_growth_input": None, "fcf_input": None, "fcf_basis": "NONE",
        "shares_input": None, "roe_input": None, "book_value_input": None,
        "model_assumptions": "", "source": DATA_SOURCE, "caveats": "",
        "risk_note": meta.get("risk_note") or "NOT INDEPENDENTLY REVIEWED",
        "manual_validation": "NEVER AUTO VALIDATED", "review_flag": "RESEARCH REQUIRED",
    }
    failures = []
    if not price:
        failures.append("Missing stock price")
    stale = number(price_row.get("stale_days"))
    if stale is None or stale > 7:
        failures.append("Daily-price date missing or older than 7 days")
    if not feed or not isinstance(feed.get("info"), dict):
        failures.append("Fundamentals feed unavailable or rate-limited")
    if failures:
        out.update(model_status="BLOCKED: " + "; ".join(failures), caveats="; ".join(failures))
        return out

    info = feed["info"]
    model_type = classified(info, meta)
    out["model_type"] = model_type
    quote_currency = str(info.get("currency") or "").upper()
    fin_currency = str(info.get("financialCurrency") or "").upper()
    out["fundamental_currency"] = fin_currency or None
    if quote_currency != str(currency).upper():
        failures.append("Quote currency mismatch or missing")
    if not fin_currency or fin_currency != str(currency).upper():
        failures.append("Financial statement currency mismatch or missing (ADR/FX risk)")

    fiscal_date = as_of(info)
    out["fiscal_as_of"] = fiscal_date.date().isoformat() if fiscal_date else None
    if not fiscal_date:
        failures.append("No source-reported fiscal statement date")
    elif not (0 <= (now - fiscal_date).days <= 550):
        failures.append("Fiscal reporting date outside 550-day freshness check")
    kind = str(info.get("quoteType") or "").upper()
    if kind != "EQUITY":
        failures.append("Instrument is not confirmed common equity or ADR")
    shares = positive(info.get("sharesOutstanding"))
    cap = positive(info.get("marketCap"))
    out["shares_input"] = shares
    if shares and cap and price:
        mismatch = abs(cap / shares / price - 1)
        if mismatch > .40:
            failures.append("Market cap/share-count/price mismatch (split or ADR risk)")
    else:
        failures.append("Market cap or share-count missing")

    if model_type == "SPECIALIST_RESEARCH_REQUIRED":
        failures.append("Specialist valuation required (AFFO, pipeline, capital structure, regulatory or asset model)")
    if failures:
        out.update(model_status="BLOCKED: " + "; ".join(failures), caveats="; ".join(failures))
        return out

    vol = number(price_row.get("volatility_20d_annual_pct"))
    rg = number(info.get("revenueGrowth"))
    out["revenue_growth_input"] = rg
    out["roe_input"] = number(info.get("returnOnEquity"))
    out["book_value_input"] = number(info.get("bookValue"))
    out["fcf_input"] = number(info.get("freeCashflow"))
    fcf = positive(info.get("freeCashflow"))
    fcf_basis = "LATEST UNVERIFIED FREE CASH FLOW (SINGLE PERIOD)"
    
    try:
        if model_type == "FINANCIAL_BOOK_ROE":
            book = positive(info.get("bookValue"))
            roe = number(info.get("returnOnEquity"))
            if book is None or roe is None:
                raise ValueError("Financial institution book value or ROE missing")
            values, assumptions = model_book_roe(book, roe)
            out["fcf_basis"] = "NOT USED: FINANCIAL COMPANY"
        else:
            if model_type == "CYCLICAL_NEEDS_MULTIYEAR":
                hist = [x for x in (number(v) for v in feed.get("annual_fcf", [])) if x is not None]
                if len(hist) < 3 or any(x <= 0 for x in hist[:3]):
                    raise ValueError("Requires at least 3 positive annual free-cash-flow observations; assess cycle")
                # Median of three years dampens cycle peaks; still not a commodity-price NAV.
                fcf = statistics.median(hist[:3])
                fcf_basis = "MEDIAN OF 3 ANNUAL UNVERIFIED CASH FLOW OBSERVATIONS"
            if fcf is None:
                raise ValueError("Positive equity free cash flow missing; no speculative multiple substituted")
            if shares is None:
                raise ValueError("Shares missing")
            values, assumptions, _ = model_fcf(fcf / shares, rg, cap, vol)
            out["fcf_basis"] = fcf_basis
            out["fcf_input"] = fcf
    except ValueError as e:
        out.update(model_status="UNVALUED: " + str(e), caveats=str(e))
        return out

    bear, base, bull = values
    if not all(math.isfinite(x) and x > 0 for x in values) or not (bear <= base <= bull):
        out.update(model_status="UNVALUED: scenario calculations inconsistent",
                   caveats="Model range failed validation")
        return out

    # These levels are provisional model hypotheses, never validated purchase prices.
    haircut = .40 if vol is not None and vol >= 80 else .30
    entry = base * (1 - haircut)
    deep = min(entry * .75, bear * .90)
    out.update(
        model_status="INDICATIVE MODEL — NOT VERIFIED OR APPROVED",
        model_quality="LOW: UNOFFICIAL, LATEST SNAPSHOT, SENSITIVITY-BASED",
        bear_value=round(bear, 4), base_value=round(base, 4), bull_value=round(bull, 4),
        model_watch_entry=round(entry, 4), model_deep_entry=round(deep, 4),
        pct_to_watch_entry=percentage(price, entry), upside_to_base_pct=percentage(base, price),
        model_assumptions=assumptions,
        caveats="Yahoo-derived fields are unverified; scenarios use assumptions, not forecast certainty; "
                "cross-check filings, multiple and adverse event risk before valuation validation",
        review_flag=("POTENTIAL DISCOUNT — VERIFY FUNDAMENTALS" if price is not None and price <= entry
                     else "RESEARCH ONLY — ABOVE INDICATIVE ENTRY"),
    )
    return out


def blocked(meta: dict, pr: dict, error: str, now: datetime) -> dict:
    row = evaluate(meta, pr, None, now)
    row["model_status"] = f"FEED ERROR: {error[:180]}"
    row["caveats"] = error[:180]
    return row


def render_html(rows: list[dict], summary: dict) -> str:
    keys = ["ticker", "company", "price_currency", "last_daily_close", "quote_date",
            "model_type", "model_status", "bear_value", "base_value", "bull_value",
            "model_watch_entry", "model_deep_entry", "pct_to_watch_entry", "upside_to_base_pct",
            "fiscal_as_of", "model_quality", "review_flag", "caveats"]
    head = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Global Championship 4.0 — 200 company research valuations</title><style>
    :root{color-scheme:dark}body{background:#0d1423;color:#e4eaf3;font:14px system-ui,sans-serif;padding:15px}
    h1{font-size:23px}a{color:#83d3ff}.grid{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}
    .metric{border:1px solid #344764;border-radius:9px;padding:10px;min-width:140px}
    .metric b{display:block;font-size:25px}input{width:min(100%,420px);padding:11px;background:#1d2b42;color:white;border:1px solid #405373}
    table{border-collapse:collapse;min-width:2600px;font-size:12px}th,td{padding:8px;text-align:left;white-space:nowrap;border-bottom:1px solid #35435d}
    th{background:#19273c;position:sticky;top:0}.wrap{overflow:auto;max-height:75vh}
    .note{border-left:3px solid #8797ad;padding:12px;background:#18253a;line-height:1.55}
    </style></head><body>"""
    cards = "".join(f'<div class="metric">{escape(k)}<b>{v}</b></div>' for k, v in [
        ("Universe", summary["total_rows"]), ("Indicative models", summary["indicative_model_count"]),
        ("Unvalued / blocked", summary["blocked_or_unvalued_count"]),
        ("Validated buy prices", 0)])
    html = head + f"<h1>Championship 4.0 — {len(rows)}-company valuation research</h1>"
    html += f"<p>Research as of {escape(summary['timestamp_utc'])} UTC</p><div class='grid'>{cards}</div>"
    html += ("<div class='note'><b>Not investment advice or buy prices.</b> These are indicative, "
             "unverified scenarios based on unofficial financial snapshots and conservative heuristics. "
             "No valuation is fundamentally validated; missing data do not get artificial prices. "
             "The 200 companies are monitored, but only sufficiently sourced companies receive model values. "
             "Even these may be materially wrong (especially cyclicals and ADRs). No orders generated.</div><p></p>")
    html += "<input id='q' placeholder='Filter all 200 ticker names, models or errors...'>"
    html += "<div class='wrap'><table><thead><tr>" + "".join(f"<th>{escape(k.replace('_',' ').title())}</th>" for k in keys) + "</tr></thead><tbody>"
    for row in rows:
        vals = []
        for k in keys:
            v = row.get(k)
            vals.append("—" if v is None or v == "" else escape(f"{v:,.2f}" if isinstance(v, float) else str(v)))
        html += "<tr>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
    html += "</tbody></table></div>"
    html += """<script>document.getElementById('q').addEventListener('input',function(){
      const q=this.value.toLowerCase(); document.querySelectorAll('tbody tr').forEach(row=>{
       row.hidden=!row.textContent.toLowerCase().includes(q);});});</script></body></html>"""
    return html


def write_results(rows: list[dict], output: Path, now: datetime) -> dict:
    summary = {
        "timestamp_utc": now.isoformat(), "total_rows": len(rows),
        "indicative_model_count": sum(x["model_status"].startswith("INDICATIVE") for x in rows),
        "blocked_or_unvalued_count": sum(not x["model_status"].startswith("INDICATIVE") for x in rows),
        "validated_buy_count": 0,
        "order_execution_enabled": False, "orders_generated": 0,
        "source": DATA_SOURCE,
        "warning": "Research-only indicative scenarios, not verified intrinsic values or instructions to buy",
    }
    output.mkdir(parents=True, exist_ok=True)
    with (output / "valuation_200.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    (output / "valuation_200.json").write_text(json.dumps({"summary": summary, "stocks": rows}, indent=2,
                                                      ensure_ascii=False), encoding="utf-8")
    (output / "valuation_200.html").write_text(render_html(rows, summary), encoding="utf-8")
    return summary


def run_engine(watchlist: Path = BASE / "watchlist.csv", prices: Path = DATA / "latest.json",
               output: Path = DATA, fetcher: Callable[[str], dict] = get_fundamentals,
               workers: int = 3, max_minutes: float = 25.0,
               now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    with watchlist.open(encoding="utf-8-sig", newline="") as f:
        meta = list(csv.DictReader(f))
    if len(meta) != REQUIRED_COUNT or len({r["ticker"] for r in meta}) != REQUIRED_COUNT:
        raise ValueError("Expected exactly 200 unique watchlist rows")
    data = json.loads(prices.read_text(encoding="utf-8"))
    quotes = {r["ticker"]: r for r in data.get("stocks", [])}
    if len(quotes) != REQUIRED_COUNT:
        raise ValueError("Expected 200 stocks in current scanner output")
    rows = [blocked(m, quotes[m["ticker"]], "NOT YET FETCHED", now) for m in meta]
    # Create checkpoint immediately so a partial feed still yields 200 visible rows.
    write_results(rows, output, now)
    by_ticker = {m["ticker"]: i for i, m in enumerate(meta)}
    deadline = time.monotonic() + max(1.0, max_minutes) * 60
    pool = ThreadPoolExecutor(max_workers=max(1, min(6, workers)))
    pending = {pool.submit(fetcher, m["ticker"]): m["ticker"] for m in meta}
    completed = 0
    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            finished, _ = wait(pending, timeout=min(remaining, 30), return_when=FIRST_COMPLETED)
            if not finished:
                continue
            for future in finished:
                ticker = pending.pop(future)
                i = by_ticker[ticker]
                try:
                    rows[i] = evaluate(meta[i], quotes[ticker], future.result(), now)
                except Exception as exc:
                    rows[i] = blocked(meta[i], quotes[ticker], f"{type(exc).__name__}: {str(exc)}", now)
                completed += 1
            if completed % 20 == 0 or not pending:
                write_results(rows, output, now)
    finally:
        for future in pending:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
    if pending:
        for future, ticker in pending.items():
            i = by_ticker[ticker]
            rows[i] = blocked(meta[i], quotes[ticker], "TIME BUDGET EXCEEDED — RETRY MANUALLY", now)
    summary = write_results(rows, output, now)
    summary["fundamentals_fetch_completed"] = completed
    summary["unfetched_due_to_time_budget"] = len(pending)
    (output / "valuation_200_run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Non-trading weekly 200-stock valuation research")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-minutes", type=float, default=25.0)
    args = parser.parse_args()
    result = run_engine(workers=args.workers, max_minutes=args.max_minutes)
    print(json.dumps(result, indent=2))
