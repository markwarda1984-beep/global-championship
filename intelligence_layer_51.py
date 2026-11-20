"""Championship 5.1 decision-intelligence layer on top of existing 5.2 discovery.

Read-only outputs. Never executes, creates, transmits, suggests, or approves orders.
Valuation Top 10 is a *source-labelled RESEARCH queue*, not a list of verified buys.
Source verification distinguishes primary filing METADATA, URL reachability,
and issuer-reported claims detected in source text (not independently audited).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
REPORTS = BASE / "reports"
CONFIG = BASE / "settings" / "intelligence_51.json"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        val = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def positive(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def number(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def date_age(value: Any, now: datetime) -> int | None:
    date = dt(value)
    if not date:
        return None
    age = (now.date() - date.date()).days
    return age if 0 <= age <= 3000 else None


def read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def assert_safety(scan: dict | None, registry: dict | None = None) -> None:
    if scan is not None:
        rows = scan.get("stocks")
        ticks = [str(x.get("ticker", "")).upper() for x in rows] if isinstance(rows, list) else []
        if len(ticks) != 200 or len(set(ticks)) != 200:
            raise ValueError("Main 200-stock scanner was missing, altered or duplicated")
        if scan.get("orders_enabled") is not False:
            raise ValueError("Main scanner must explicitly disable orders")
    if registry is not None and (registry.get("orders_enabled") is not False or
                                  registry.get("original_200_unchanged") is not True):
        raise ValueError("Discovery registry protection failed")


def pct_diff(current: float, prev: float) -> float:
    return round(100.0 * (current / prev - 1.0), 3)


def scan_changes(previous: dict | None, current: dict, now: datetime) -> dict:
    assert_safety(current)
    prior = {x["ticker"]: x for x in previous.get("stocks", [])} if previous and isinstance(previous.get("stocks"), list) else {}
    if prior and len(prior) != 200:
        raise ValueError("Previous scanner record incomplete: refuse misleading comparison")
    items = []
    changed_data = []
    for row in current["stocks"]:
        ticker = row["ticker"]
        old = prior.get(ticker)
        if not old:
            continue
        a, b = positive(old.get("last_daily_close")), positive(row.get("last_daily_close"))
        old_date, new_date = old.get("quote_date"), row.get("quote_date")
        category = "UNCHANGED_OR_UNCOMPARABLE"
        move = None
        if a and b and old_date and new_date and dt(old_date) and dt(new_date):
            if dt(new_date).date() > dt(old_date).date():
                category = "NEW_DAILY_BAR"
                move = pct_diff(b, a)
            elif dt(new_date).date() == dt(old_date).date() and abs(b - a) > 1e-8:
                category = "SAME_BAR_DATA_REVISION"
            elif dt(new_date).date() < dt(old_date).date():
                category = "QUOTE_DATE_REGRESSION"
        fields = [key for key in ("entry_basis", "provisional_entry", "model_status", "data_status")
                  if old.get(key) != row.get(key)]
        if category != "UNCHANGED_OR_UNCOMPARABLE" or fields:
            event = {"ticker": ticker, "category": category,
                     "old_quote_date": old_date, "new_quote_date": new_date,
                     "old_daily_close": a, "new_daily_close": b, "daily_bar_change_pct": move,
                     "research_field_changes": fields,
                     "current_provisional_entry": row.get("provisional_entry"),
                     "research_only": True, "buy_signal": False}
            changed_data.append(event)
            if category == "NEW_DAILY_BAR" or fields:
                items.append(event)
    ranked = sorted(items, key=lambda x: (abs(x["daily_bar_change_pct"] or 0), x["ticker"]), reverse=True)
    return {"schema_version": "5.1-scan-changes-1", "published_at_utc": now.isoformat(),
            "current_scan_utc": current.get("scan_utc"),
            "prior_scan_utc": previous.get("scan_utc") if previous else None,
            "comparison_status": "COMPARED" if prior else "BASELINE_ONLY_NO_PREVIOUS_SCAN",
            "universe_count": 200, "new_daily_bar_count": sum(v["category"] == "NEW_DAILY_BAR" for v in changed_data),
            "same_bar_revision_count": sum(v["category"] == "SAME_BAR_DATA_REVISION" for v in changed_data),
            "quote_date_regression_count": sum(v["category"] == "QUOTE_DATE_REGRESSION" for v in changed_data),
            "research_field_change_count": sum(bool(v["research_field_changes"]) for v in changed_data),
            "material_changes": ranked, "data_revisions_and_regressions": [v for v in changed_data if v["category"] in
                                                                         ("SAME_BAR_DATA_REVISION", "QUOTE_DATE_REGRESSION")],
            "meaning": "Daily-bar change is between different quote sessions, NOT intraday gain, executable return or trade signal",
            "orders_enabled": False}


def verify_url_metadata(record: dict, session: Any = None, allow_network: bool = False,
                        sec_ok: bool = False) -> dict:
    """Independent, bounded issuer URL reachability check; never claims PDF/filing substance checked."""
    try:
        from discovery_engine import TRUSTED_SEED_HOSTS
    except ImportError:
        TRUSTED_SEED_HOSTS = set()
    url = str(record.get("evidence_url", ""))
    try:
        parsed = urlparse(url)
        valid_host = (parsed.scheme == "https" and parsed.hostname in TRUSTED_SEED_HOSTS
                      and not parsed.username and not parsed.password)
    except ValueError:
        valid_host = False
    kind = record.get("evidence_kind")
    if not valid_host:
        return {"primary_source_verified": False, "primary_claim_verified": False,
                "verification_level": "UNTRUSTED_OR_NONPRIMARY_HOST"}
    if (kind == "SEC_8K_FILING_REFERENCE" and sec_ok and parsed.hostname in ("www.sec.gov", "sec.gov")
            and "/Archives/edgar/data/" in parsed.path):
        return {"primary_source_verified": True, "primary_claim_verified": False,
                "verification_level": "SEC_TICKER_AND_FILING_METADATA_MATCHED_OFFICIAL_FEED",
                "content_verification": "Filing metadata only; business event and investment implications not parsed"}
    if kind != "CURATED_OFFICIAL_DISCLOSURE_REFERENCE":
        return {"primary_source_verified": False, "primary_claim_verified": False,
                "verification_level": "SECONDARY_NEWS_ONLY_OR_UNMATCHED_FILING"}
    if not allow_network or session is None:
        return {"primary_source_verified": False, "primary_claim_verified": False,
                "verification_level": "OFFICIAL_LINK_NOT_FETCHED"}
    try:
        # No redirects: avoids treating a login page or third-party destination as verified.
        response = session.get(url, timeout=9, allow_redirects=False, stream=True)
        code = int(response.status_code)
        mime = str(response.headers.get("Content-Type", "")).lower().split(";")[0].strip()
        response.close()
        if code == 200 and mime in ("application/pdf", "text/html", "application/xhtml+xml", "application/octet-stream"):
            return {"primary_source_verified": True, "primary_claim_verified": False,
                    "verification_level": "OFFICIAL_PUBLISHER_URL_REACHABLE_ONLY",
                    "http_status": code, "content_type": mime,
                    "content_verification": "Issuer URL returned 200; contents, announcement date and company claims NOT verified"}
        return {"primary_source_verified": False, "primary_claim_verified": False,
                "verification_level": "PUBLISHER_URL_UNVERIFIED_HTTP_OR_TYPE", "http_status": code}
    except Exception as ex:
        return {"primary_source_verified": False, "primary_claim_verified": False,
                "verification_level": "PUBLISHER_URL_FETCH_ERROR", "error_type": type(ex).__name__}


def research_queue(registry: dict, discovery: dict, now: datetime, *, session: Any = None,
                   allow_network: bool = False) -> dict:
    assert_safety(None, registry)
    records = []
    sec_ok = discovery.get("source_health", {}).get("sec_8k", {}).get("status") == "ok"
    for ticker, row in sorted(registry.get("candidates", {}).items()):
        if row.get("status") == "MANUAL_EXCLUDE":
            continue
        url = str(row.get("evidence_url") or "")
        verify = verify_url_metadata(row, session, allow_network, sec_ok)
        quote = row.get("last_quote") or {}
        freshness = date_age(row.get("evidence_date"), now)
        concerns = list(row.get("concerns") or [])
        if not verify["primary_source_verified"]:
            concerns = ["OFFICIAL_EVIDENCE_NOT_VERIFIED"] + concerns
        if freshness is None or freshness > 45:
            concerns = ["EVIDENCE_STALE_OR_UNDATED"] + concerns
        if row.get("status") == "ARCHIVED_MONITORING":
            concerns = ["ARCHIVED_MONITORING"] + concerns
        # Source-verified = provenance only; never imply the announcement's assertions are true.
        verified_queue = bool(verify["primary_source_verified"] and freshness is not None and freshness <= 45
                              and row.get("status") != "ARCHIVED_MONITORING")
        try:
            source_host = urlparse(url).hostname if url else None
        except ValueError:
            source_host = None
        records.append({"ticker": ticker, "company": row.get("company"), "theme": row.get("theme"),
                        "status": row.get("status"), "source_url": url, "evidence_date": row.get("evidence_date"),
                        "evidence_kind": row.get("evidence_kind"), "discovery_source": row.get("discovery_source"),
                        "source_host": source_host,
                        "primary_source_verified": verify["primary_source_verified"],
                        "primary_claim_verified": False, "verification": verify,
                        "in_source_verified_research_queue": verified_queue,
                        "last_daily_close": positive(quote.get("price")),
                        "quote_date": quote.get("quote_date"), "median_dollar_volume_20d": quote.get("median_dollar_volume_20d"),
                        "market_cap_unverified": quote.get("market_cap"),
                        "gaps": list(dict.fromkeys(concerns + ["Read official filing and independently verify economics, dilution and valuation"])),
                        "decision": "SOURCE-TRIAGED RESEARCH ONLY — NOT BUY APPROVAL"})
    records.sort(key=lambda x: (not x["in_source_verified_research_queue"],
                                x["status"] != "MONITOR", x["ticker"]))
    return {"schema_version": "5.1-source-evidence-queue-1", "published_at_utc": now.isoformat(),
            "discovery_snapshot_utc": discovery.get("published_at_utc"),
            "original_200_unchanged": True,
            "source_verified_reference_count": sum(x["in_source_verified_research_queue"] for x in records),
            "not_yet_verified_count": sum(not x["in_source_verified_research_queue"] for x in records),
            "claim_verified_count": 0,
            "records": records,
            "warning": "Only official-source metadata/URL reachability verified. No PDF or disclosure claims, trading thesis or valuations have been independently validated.",
            "orders_enabled": False}


def valuation_top10(scan: dict, valuation: dict | None, now: datetime) -> dict:
    assert_safety(scan)
    val = valuation or {}
    models = {str(r.get("ticker", "")).upper(): r for r in val.get("stocks", []) if isinstance(r, dict)}
    results = []
    blockers = {"no_indicative_model": 0, "stale_or_incomplete": 0}
    valuation_ts = val.get("summary", {}).get("timestamp_utc")
    model_run_age = date_age(valuation_ts, now)
    for sr in scan["stocks"]:
        ticker = str(sr["ticker"]).upper()
        model = models.get(ticker)
        if not model or not str(model.get("model_status", "")).startswith("INDICATIVE"):
            blockers["no_indicative_model"] += 1
            continue
        px = positive(sr.get("last_daily_close"))
        bear, base, bull = (positive(model.get(x)) for x in ("bear_value", "base_value", "bull_value"))
        watch = positive(model.get("model_watch_entry"))
        fiscal_age = date_age(model.get("fiscal_as_of"), now)
        quote_age = date_age(sr.get("quote_date"), now)
        ccy = sr.get("currency")
        valid = (all(v is not None for v in (px, bear, base, bull, watch)) and bear <= base <= bull
                 and 0 <= fiscal_age <= 550 if fiscal_age is not None else False)
        if not valid or quote_age is None or quote_age > 7 or model_run_age is None or model_run_age > 14 or \
                str(model.get("price_currency", "")).upper() != str(ccy).upper() or \
                str(model.get("fundamental_currency", "")).upper() != str(ccy).upper() or \
                str(model.get("model_quality", "")).upper().startswith("VALIDATED"):
            blockers["stale_or_incomplete"] += 1
            continue
        base_upside = (base / px - 1) * 100
        bear_downside = (bear / px - 1) * 100
        margin = (watch / px - 1) * 100
        # Explanation-first prioritisation, not probability of profit or forecast return.
        score = round(min(45, max(0, base_upside) * 0.3) +
                      min(25, max(0, bear_downside) * 0.25) +
                      min(20, max(0, margin) * 0.20) +
                      max(0, 10 * (1 - fiscal_age / 550)), 2)
        results.append({"ticker": ticker, "company": sr.get("company"),
                        "currency": ccy, "quote_date": sr.get("quote_date"),
                        "last_daily_close": round(px, 5), "bear_value": bear, "base_value": base,
                        "bull_value": bull, "model_watch_entry": watch,
                        "pct_to_indicative_base": round(base_upside, 2),
                        "pct_to_indicative_bear": round(bear_downside, 2),
                        "pct_to_unverified_watch_entry": round(margin, 2),
                        "research_priority_score_not_probability": score,
                        "fundamental_as_of": model.get("fiscal_as_of"),
                        "valuation_snapshot_utc": valuation_ts,
                        "model_type": model.get("model_type"), "assumptions": model.get("model_assumptions"),
                        "source": model.get("source"), "source_verification": "UNOFFICIAL_DATA_NOT_INDEPENDENTLY_CHECKED",
                        "research_gaps": ["Confirm audited filings and normalised earnings",
                                          "Verify dilution, debt, upcoming catalyst and downside scenario",
                                          "Independently review valuation assumptions and FX"],
                        "verified_buy_signal": False, "buy_readiness_pct": None,
                        "decision": "VALUATION RESEARCH PRIORITY — NOT A BUY"})
    results.sort(key=lambda r: (-r["research_priority_score_not_probability"], r["ticker"]))
    top = [{"rank": i + 1, **v} for i, v in enumerate(results[:10])]
    return {"schema_version": "5.1-valuation-top10-1", "published_at_utc": now.isoformat(),
            "source_valuation_snapshot_utc": valuation_ts,
            "model_data_available_count": sum(str(x.get("model_status", "")).startswith("INDICATIVE") for x in val.get("stocks", [])),
            "eligible_for_research_count": len(results), "ranked_top_10": top, "exclusion_counts": blockers,
            "verified_buy_count": 0, "orders_enabled": False,
            "warning": "Ranked only among eligible unverified scenario models; not 10 best investments or predicted winners. No independent filing validation, time-horizon assumptions, or probability estimates."}


def evidence_qualified_top10(scan: dict, primary60: dict | None, now: datetime) -> dict:
    """Only current 6.0 issuer-primary scenarios may enter active Top 10 and tax simulations.

    Retains existing report schema for downstream consumers, but never projects an
    unofficial model watch-entry into another supposedly evidence-based report.
    Missing or stale 6.0 report gives empty ranking, never a fallback buy level.
    """
    assert_safety(scan)
    from report_bridge import checked_championship60, evidence_entry, numeric, VALID_STATUS
    base = {str(x['ticker']).upper():x for x in scan['stocks']}
    rows=checked_championship60(primary60, set(base))
    eligible=[]
    for ticker,stock in base.items():
        val=rows.get(ticker)
        px=numeric(stock.get('last_daily_close'))
        matched=evidence_entry(val,ticker,px,stock.get('currency'),stock.get('quote_date'))
        if not matched or date_age(matched.get('report_as_of_utc'),now) not in range(0,15):
            continue
        bear,mid,bull=(numeric(matched.get(k)) for k in ('bear','base','bull'))
        if not (bear and mid and bull and bear<=mid<=bull):
            continue
        entry=numeric(matched.get('selected_entry'))
        if not entry:
            continue
        risk_downside=max(5.0,(1-bear/px)*100)
        base_upside=(mid/px-1)*100
        eligible.append({'ticker':ticker,'company':stock.get('company'),
            'currency':stock.get('currency'),'quote_date':stock.get('quote_date'),
            'last_daily_close':px,'bear_value':bear,'base_value':mid,'bull_value':bull,
            'model_watch_entry':None, # RETIRED: former Yahoo heuristic
            'selected_6_0_entry':entry,
            'margin_of_safety_entries_60':matched.get('margin_of_safety_entries'),
            'pct_to_indicative_base':round(base_upside,2),
            'pct_to_indicative_bear':round((bear/px-1)*100,2),
            'pct_to_unverified_watch_entry':None,
            'research_priority_score_not_probability':round(max(0.0,base_upside)/risk_downside,3),
            'fundamental_as_of':None,
            'valuation_snapshot_utc':primary60.get('published_at_utc'),
            'model_type':matched.get('sector_method'),
            'assumptions':matched.get('assumptions'),
            'source':matched.get('primary_source_evidence',{}).get('url'),
            'source_verification':'PRIMARY_INPUTS_VALIDATED_FORECASTS_HYPOTHETICAL',
            'research_gaps':matched.get('risks',[]),
            'verified_buy_signal':False,'buy_readiness_pct':None,
            'decision':'6.0 EVIDENCE-QUALIFIED RESEARCH ONLY — NO TRADES'})
    eligible.sort(key=lambda x:(-x['research_priority_score_not_probability'],x['ticker']))
    return {'schema_version':'6.0-evidence-only-valuation-top10-1',
      'published_at_utc':now.isoformat(),
      'source_valuation_snapshot_utc':(primary60 or {}).get('published_at_utc'),
      'model_data_available_count':(primary60 or {}).get('validated_inputs_count',0),
      'eligible_for_research_count':len(eligible),
      'ranked_top_10':[{'rank':i+1,**row} for i,row in enumerate(eligible[:10])],
      'exclusion_counts':{'not_validated_or_missing':200-len(eligible)},
      'verified_buy_count':0,'orders_enabled':False,
      'warning':'Only CURRENT Championship 6.0 issuer-primary validated scenarios. '
                'All former provisional entries RETIRED, no fallback. No orders.'}


def fx_aud_rate(path: Path, now: datetime, *, allow_network: bool = False) -> dict:
    """Fetch a bounded, unofficial AUD/USD daily close; never invent FX on failure."""
    saved = read(path, {})
    if (saved.get("status") == "ok" and positive(saved.get("aud_per_usd"))
            and date_age(saved.get("quote_date"), now) is not None
            and date_age(saved.get("quote_date"), now) <= 4):
        return saved
    if allow_network:
        try:
            import yfinance as yf
            hist = yf.Ticker("AUDUSD=X").history(period="10d", interval="1d", auto_adjust=False, actions=False)
            px = positive(hist["Close"].iloc[-1]) if not hist.empty else None
            obs_date = hist.index[-1].to_pydatetime().date().isoformat() if not hist.empty else None
            age = date_age(obs_date, now)
            if not px or not 0.2 <= px <= 2.5 or age is None or age > 4:
                raise ValueError("FX quote is unavailable, implausible or stale")
            result = {"schema_version": "5.1-fx-1", "status": "ok", "quote_date": obs_date,
                      "aud_per_usd": round(1 / px, 8), "source": "unofficial Yahoo Finance AUDUSD=X daily bar",
                      "warning": "FX estimate only; no live broker exchange rate, spread or execution quote"}
            write(path, result)
            return result
        except Exception as exc:
            return {"status": "unavailable", "reason": type(exc).__name__,
                    "previous_quote_date": saved.get("quote_date")}
    return {"status": "unavailable", "reason": "No fresh verifiable FX observation supplied",
            "previous_quote_date": saved.get("quote_date")}


def after_tax_comparison(top10: dict, assumptions: dict, fx: dict, now: datetime) -> dict:
    amount = positive(assumptions.get("comparison_principal_aud"))
    rate = number(assumptions.get("owner_occupied_offset_rate_pct"))
    months = number(assumptions.get("comparison_months"))
    buy_fee, sell_fee = (number(assumptions.get(x)) for x in
                         ("illustrative_brokerage_aud_buy", "illustrative_brokerage_aud_sell"))
    fx_spread = number(assumptions.get("illustrative_fx_spread_pct_each_way"))
    people = assumptions.get("tax_scenarios", [])
    if not amount or rate is None or not 0 <= rate <= 30 or not months or months > 120 or \
            buy_fee is None or sell_fee is None or min(buy_fee, sell_fee) < 0 or \
            fx_spread is None or not 0 <= fx_spread <= 15 or \
            not isinstance(people, list) or not people:
        raise ValueError("Missing/invalid mortgage, tax, brokerage or horizon assumptions")
    for person in people:
        mr = number(person.get("marginal_plus_medicare_pct"))
        if mr is None or not 0 <= mr <= 60:
            raise ValueError("Invalid tax scenario")
    offset = amount * rate / 100 * months / 12
    rates = assumptions.get('offset_rate_scenarios', [])
    if not rates:
        rates = [{'id':'illustrative_5_8','annual_rate_pct':rate,
                  'confirmation':'ILLUSTRATIVE_NOT_LIVE','rate_source':'legacy configurable working assumption'}]
    benchmarks=[]
    for r in rates:
        named_rate=number(r.get('annual_rate_pct'))
        if not r.get('id') or named_rate is None or not 0 <= named_rate <= 30:
            raise ValueError('Invalid configurable offset scenario')
        benchmarks.append({'id':r['id'],'annual_rate_pct':named_rate,
             'confirmation':r.get('confirmation','UNCONFIRMED_NOT_LIVE'),
             'rate_source':r.get('rate_source','USER_CONFIGURED_NOT_LIVE'),
             'offset_savings_aud':round(amount*named_rate/100*months/12,2)})
    entries = []
    for c in top10.get("ranked_top_10", []):
        ccy = str(c.get("currency", "")).upper()
        spot = 1.0 if ccy == "AUD" else positive(fx.get("aud_per_usd")) if ccy == "USD" and fx.get("status") == "ok" else None
        row = {"rank": c["rank"], "ticker": c["ticker"], "price_currency": ccy,
               "source_model_utc": c.get("valuation_snapshot_utc"), "aud_per_currency": spot,
               "status": "SCENARIO_ONLY_NOT_A_PREDICTION" if spot else "BLOCKED_MISSING_FRESH_AUD_FX",
               "offset_savings_aud": round(offset, 2), "hypothetical_outcomes": {},
               "verified_buy_signal": False}
        px = positive(c.get("last_daily_close"))
        if spot and px and amount > buy_fee * 2 + sell_fee:
            costs = fx_spread / 100 if ccy != "AUD" else 0
            # Entry/exit FX handling is an explicit simple spread sensitivity. FX held constant otherwise.
            deployed = (amount - buy_fee) * (1 - costs)
            for scenario, key in (("bear", "bear_value"), ("base", "base_value"), ("bull", "bull_value")):
                target = positive(c.get(key))
                if not target:
                    continue
                proceeds = deployed * target / px * (1 - costs) - sell_fee
                capital_gain = proceeds - amount  # All-in simplistic capital basis; no dividends.
                people_scenarios = {}
                for p in people:
                    mr = p["marginal_plus_medicare_pct"] / 100
                    tax_stress = max(0.0, capital_gain) * mr
                    net_profit = capital_gain - tax_stress
                    people_scenarios[p["id"]] = {
                        "gross_profit_after_fees_aud": round(capital_gain, 2),
                        "conservative_tax_stress_aud": round(tax_stress, 2),
                        "illustrative_after_tax_profit_aud": round(net_profit, 2),
                        "less_offset_savings_aud": round(net_profit - offset, 2),
                        "beats_offset_in_this_hypothetical_scenario": net_profit > offset,
                        "offset_comparisons_by_rate": {z['id']:{
                            'net_profit_minus_offset_aud':round(net_profit-z['offset_savings_aud'],2),
                            'beats_this_offset_scenario':net_profit>z['offset_savings_aud']}
                            for z in benchmarks},
                    }
                row["hypothetical_outcomes"][scenario] = people_scenarios
        entries.append(row)
    return {"schema_version": "5.1-aftertax-offset-sensitivity-1", "published_at_utc": now.isoformat(),
            "principal_aud": amount, "horizon_months": months,
            "annual_owner_occupied_mortgage_rate_assumption_pct": rate,
            "offset_savings_aud_for_horizon": round(offset, 2), "offset_savings_tax_treatment": "Owner-occupied interest avoided (not taxable bank interest)",
            "offset_rate_scenarios":benchmarks,
            "rate_confirmation_policy":"5.8% IS EDITABLE ILLUSTRATION; 6.01% IS UNCONFIRMED. Neither is a live St George quote.",
            "fees_aud":{"buy":buy_fee,"sell":sell_fee},
            "fx_spread_pct_each_way":fx_spread,
            "tax_method": "NO_DISCOUNT_FULL_GAIN_MARGINAL_TAX_STRESS_ONLY",
            "assumed_fx_at_exit": "unchanged; FX returns not forecast", "fx_quote": fx,
            "tax_scenarios": people, "ranked_research_scenarios": entries,
            "tax_law_warning": assumptions.get("tax_law_warning"),
            "source_urls": assumptions.get("tax_sources", []),
            "warnings": ["Model fair values are NOT 13-month predictions; bear/base/bull scenarios only",
                         "13-month horizon may cross July 2027 CGT reform; actual tax treatment NOT computed",
                         "No automatic 50% CGT discount is applied; this is a conservative sensitivity not personalised tax advice",
                         "Capital losses not immediately deductible against salary; dividends and realised FX movements excluded",
                         "Brokerage and FX cost figures are EDITABLE ILLUSTRATIVE assumptions, not quotes",
                         "Mortgage offset comparison requires loan balance in excess of offset and owner-occupied non-deductible interest"],
            "orders_enabled": False}


def journal_events(changes: dict, queue: dict | None, top10: dict, now: datetime, manual: dict | None = None) -> list[dict]:
    events = []
    for c in changes.get("material_changes", []):
        change = c.get("daily_bar_change_pct")
        if c.get("category") == "NEW_DAILY_BAR" and change is not None and abs(change) >= 5:
            events.append({"ticker": c["ticker"], "event_type": "LARGE_DAILY_BAR_MOVE_RESEARCH_ALERT",
                           "evidence_date": c.get("new_quote_date"), "observed_change_pct": change,
                           "evidence_url": None,
                           "rationale": "Large dated daily-bar change, requires catalyst/news validation"})
        if c.get("research_field_changes"):
            events.append({"ticker": c["ticker"], "event_type": "RESEARCH_MODEL_OR_STATUS_CHANGED",
                           "evidence_date": c.get("new_quote_date"),
                           "changed_fields": c["research_field_changes"], "evidence_url": None,
                           "rationale": "Research fields changed; inspect filings and model inputs"})
    for q in (queue or {}).get("records", []):
        if q.get("in_source_verified_research_queue"):
            events.append({"ticker": q["ticker"], "event_type": "OFFICIAL_SOURCE_REFERENCE_TRIAGED",
                           "evidence_date": q.get("evidence_date"), "evidence_url": q.get("source_url"),
                           "rationale": "Official source provenance checked; contents and earnings impact unverified"})
    for r in top10.get("ranked_top_10", []):
        events.append({"ticker": r["ticker"], "event_type": "VALUATION_RESEARCH_TOP10",
                       "evidence_date": r.get("valuation_snapshot_utc"), "evidence_url": None,
                       "rationale": f"Rank {r['rank']} on model input snapshot; not a purchase recommendation"})
    for item in (manual or {}).get("entries", []):
        if not isinstance(item, dict) or item.get("decision") not in {"RESEARCH", "WATCH", "HOLD", "EXCLUDE"}:
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", ticker) or not dt(item.get("decision_date")):
            continue
        events.append({"ticker": ticker, "event_type": "HUMAN_RESEARCH_DECISION_LOG",
                       "evidence_date": item["decision_date"],
                       "evidence_url": item.get("official_source_url"),
                       "stated_research_decision": item["decision"],
                       "thesis": str(item.get("thesis", ""))[:800],
                       "risk": str(item.get("risk", ""))[:500],
                       "next_review_date": item.get("next_review_date"),
                       "rationale": "Human-authored research journal entry; not a broker instruction"})
    return events


def append_journal(previous: dict | None, incoming: list[dict], now: datetime) -> dict:
    history = list((previous or {}).get("entries", []))
    seen = {x.get("event_id") for x in history}
    for event in incoming:
        # Stable ID excludes volatile timestamps and rank so unchanged reasons do not spam per scan.
        fingerprint = {k: v for k, v in event.items() if k not in ("rationale",)}
        eid = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]
        if eid in seen:
            continue
        seen.add(eid)
        history.append({"event_id": eid, "recorded_at_utc": now.isoformat(), **event,
                        "review_decision": "RESEARCH_ONLY", "thesis_status": "UNVERIFIED",
                        "human_approval": False, "order_id": None, "orders_enabled": False})
    return {"schema_version": "5.1-decision-journal-1", "updated_at_utc": now.isoformat(),
            "entry_count": len(history), "entries": history, "human_review_required": True,
            "retention": "APPEND_ONLY_DEDUPLICATED; no automated deletion",
            "orders_enabled": False}


def run(root: Path = BASE, mode: str = "scan", offline: bool = False, *,
        now: datetime | None = None, session: Any = None) -> dict:
    now = now or now_utc()
    reports = root / "reports"
    if mode == "snapshot":
        previous = reports / "latest.json"
        target = root / "data" / "intel51_prior_report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if previous.is_file():
            shutil.copyfile(previous, target)
            return {"snapshot": True}
        target.unlink(missing_ok=True)
        return {"snapshot": False}
    if mode == "discovery":
        registry = read(reports / "discovery_watchlist.json")
        discovery = read(reports / "discovery_latest.json")
        if not isinstance(registry, dict) or not isinstance(discovery, dict):
            raise ValueError("Missing live discovery reports")
        if not offline and session is None:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Championship-Research/5.1 primary-source-provenance-only"})
        queue = research_queue(registry, discovery, now, session=session, allow_network=not offline)
        # Source-text extraction and exact configured-claim matching: no URL-only approval.
        from evidence_upgrade_54 import enrich_queue
        claims = read(root / "settings" / "discovery_claims_54.json", {})
        queue = enrich_queue(queue, claims, session, now, allow_network=not offline)
        write(reports / "research_queue_latest.json", queue)
        return queue
    if mode not in ("scan", "valuation"):
        raise ValueError("Unsupported intelligence mode")
    scan = read(reports / "latest.json")
    if not isinstance(scan, dict):
        raise ValueError("Missing reports/latest.json")
    assert_safety(scan)
    valuation = read(reports / "valuation_latest.json", {})
    primary_60 = read(reports / ('valuation_60_weekly.json' if mode == 'valuation' else 'valuation_60_latest.json'), {})
    top = evidence_qualified_top10(scan, primary_60, now)
    from evidence_upgrade_54 import asymmetry_report
    raw_evidence = read(reports / "primary_financials_latest.json", {})
    if not isinstance(raw_evidence,dict) or not raw_evidence:
        raw_evidence = {'schema_version':'5.4-sec-primary-financials-1',
            'status':'NO_PRIMARY_ECONOMIC_EVIDENCE_CHECKED_YET',
            'companies':{},'orders_enabled':False,'research_only':True}
        write(reports / "primary_financials_latest.json", raw_evidence)
    # Stale SEC reads cannot promote models into an evidence-qualified ranking.
    if date_age(raw_evidence.get("published_at_utc"), now) is None or \
            date_age(raw_evidence.get("published_at_utc"), now) > 31:
        raw_evidence = {}
    stress_cfg = read(root / "settings" / "dilution_stress_54.json", {})
    stresses = stress_cfg.get('hypothetical_future_issuance_pct', {})
    asymmetry = asymmetry_report(scan, valuation, raw_evidence, now,
        stress_bear=float(stresses.get('bear', 15))/100,
        stress_base=float(stresses.get('base', 5))/100,
        stress_bull=float(stresses.get('bull', 0))/100)
    scenario_by_ticker = {x['ticker']:x for x in
        [*asymmetry['evidence_qualified_top10'],*asymmetry['unverified_scenario_review_queue']]}
    for item in top['ranked_top_10']:
        check=scenario_by_ticker.get(item['ticker'])
        item['evidence_qualified_for_asymmetry']=bool(check and check['primary_model_economics_verified'])
        item['dilution_adjusted_scenarios']=check.get('dilution_adjusted_values') if check else None
        item['missing_primary_evidence_flags']=check.get('source_flags',[]) if check else ['PRIMARY_MODEL_NOT_CHECKED']
    top['evidence_qualified_top10_count']=asymmetry['evidence_qualified_count']
    top['warning'] += ' Supplemental 5.4 asymmetry scenarios are separate and not purchase targets.'
    cfg = read(root / "settings" / "intelligence_51.json")
    if not isinstance(cfg, dict):
        raise ValueError("Missing intelligence assumptions")
    fx = fx_aud_rate(reports / "fx_aud_latest.json", now, allow_network=(mode == "scan" and not offline))
    comparison = after_tax_comparison(top, cfg, fx, now)
    if mode == "valuation":
        write(reports / "valuation_top10_weekly.json", top)
        write(reports / "offset_comparison_weekly.json", comparison)
        write(reports / "asymmetry_weekly.json", asymmetry)
        return {"valuation_top10": top, "offset": comparison, "asymmetry":asymmetry}
    previous = read(root / "data" / "intel51_prior_report.json")
    changes = scan_changes(previous, scan, now)
    queue = read(reports / "research_queue_latest.json", {})
    journal_prev = read(reports / "decision_journal.json", {})
    manual = read(root / "decisions" / "manual_decisions.json", {"entries": []})
    journal = append_journal(journal_prev, journal_events(changes, queue, top, now, manual), now)
    write(reports / "changes_latest.json", changes)
    write(reports / "valuation_top10_latest.json", top)
    write(reports / "asymmetry_latest.json", asymmetry)
    write(reports / "offset_comparison_latest.json", comparison)
    write(reports / "decision_journal.json", journal)
    summary = {"schema_version": "5.1-intelligence-index-1", "published_at_utc": now.isoformat(),
               "base_scanner_count": 200, "discovery_pipeline_preserved": True,
               "change_summary": {k: changes[k] for k in ("comparison_status", "new_daily_bar_count", "same_bar_revision_count", "research_field_change_count")},
               "research_queue_source_verified_count": queue.get("source_verified_reference_count"),
               "valuation_top10_count": len(top["ranked_top_10"]),
               "evidence_qualified_asymmetric_count": asymmetry['evidence_qualified_count'],
               "journal_entries": journal["entry_count"],
               "offset_comparison_status": "SCENARIOS_WITH_LIMITATIONS",
               "reports": ["reports/changes_latest.json", "reports/research_queue_latest.json",
                           "reports/valuation_top10_latest.json", "reports/offset_comparison_latest.json",
                           "reports/decision_journal.json", "reports/asymmetry_latest.json",
                           "reports/primary_financials_latest.json"],
               "research_only": True, "orders_enabled": False}
    write(reports / "intelligence_latest.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("snapshot", "discovery", "scan", "valuation"), required=True)
    parser.add_argument("--root", type=Path, default=BASE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = run(root=args.root, mode=args.mode, offline=args.offline)
    print(json.dumps({"mode": args.mode, "schema_version": result.get("schema_version"),
                      "orders_enabled": result.get("orders_enabled", False), "status": "complete"}, indent=2))


if __name__ == "__main__":
    main()
