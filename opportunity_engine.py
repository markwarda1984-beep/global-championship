"""Transparent, no-trade opportunity screen for all 200 monitored securities.

Intentionally ranks *technical research priority*, NOT expected returns,
probability of profit, verified fair value, or authorisation to trade.

Input: data/latest.json from scan.py. Output: all-200 comparison reports.
No internet, broker APIs, credentials, executable orders or orders in output.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from html import escape
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "data"


def finite_number(v):
    try:
        n = float(v)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def band(v, low, high):
    return max(low, min(high, v))


def technical_priority(row: dict) -> tuple[float | None, str, list[str]]:
    """Purely heuristic triage score on 0-100 scale, not an investment score.

    Price history anomalies/incomplete bars are never rewarded. Scores are
    comparable only within this day's sample and subject to data limitations.
    No backtested predictive performance is claimed.
    """
    px = finite_number(row.get("price"))
    stale = finite_number(row.get("stale_days"))
    required = ["sma_50", "sma_200", "change_20d_pct", "change_63d_pct",
                "rsi_14", "volatility_20d_annual_pct", "volume_ratio_20d"]
    m = {k: finite_number(row.get(k)) for k in required}
    if px is None or px <= 0:
        return None, "DATA BLOCKED", ["No valid stock close available"]
    if stale is not None and stale > 7:
        return None, "DATA BLOCKED", ["Price history stale over 7 days"]
    if any(m[k] is None for k in required):
        return None, "DATA INCOMPLETE", ["Insufficient comparable price history"]
    if m["volatility_20d_annual_pct"] < 0 or m["volume_ratio_20d"] < 0:
        return None, "DATA BLOCKED", ["Invalid volatility/volume metric"]

    trend = 25 if px > m["sma_200"] else 5
    trend += 15 if px > m["sma_50"] else 5
    momentum = band((m["change_20d_pct"] + 15) / 30 * 20, 0, 20)
    momentum += band((m["change_63d_pct"] + 25) / 60 * 10, 0, 10)
    volume = band((m["volume_ratio_20d"] - 0.5) / 2.5 * 10, 0, 10)
    rsi = m["rsi_14"]
    rsi_score = 10 if 40 <= rsi <= 68 else (5 if 30 <= rsi < 80 else 0)
    risk_penalty = band((m["volatility_20d_annual_pct"] - 50) * 0.12, 0, 15)
    score = round(band(trend + momentum + volume + rsi_score - risk_penalty, 0, 100), 1)
    notes = []
    if m["volume_ratio_20d"] >= 2:
        notes.append("Relative volume above 2×; check for news and liquidity")
    if m["volatility_20d_annual_pct"] >= 100:
        notes.append("Extreme recent volatility; increased loss risk")
    if m["rsi_14"] > 75:
        notes.append("Extended RSI; do not assume breakout will continue")
    if px < m["sma_200"]:
        notes.append("Below 200-session average")
    return score, ("HIGH TECHNICAL PRIORITY" if score >= 75 else
                   "TECHNICAL REVIEW" if score >= 55 else "TECHNICAL WATCH"), notes


def assess(row: dict) -> dict:
    score, label, notes = technical_priority(row)
    price = finite_number(row.get("price"))
    validated = finite_number(row.get("validated_buy_price"))
    fv = finite_number(row.get("fair_value_estimate"))
    research_date = row.get("fair_value_date") or ""
    method = row.get("valuation_method") or ""
    buy_validation = str(row.get("buy_validation", "UNRESEARCHED"))
    # Parsed CSV metadata does not verify financial source integrity.
    evidence_complete = bool(validated and fv and research_date and method and buy_validation == "VALIDATED")
    gaps = []
    if not evidence_complete:
        gaps.append("Source-check fair value and buy price")
    if not row.get("risk_note"):
        gaps.append("Assess debt, dilution, liquidity and downside")
    gaps.append("Verify next catalyst, earnings date and latest filing externally")
    notes.extend(gaps)

    if score is None:
        decision = "NO PROPOSAL: INSUFFICIENT DATA"
    elif not evidence_complete:
        decision = "RESEARCH ONLY — NO VALIDATED BUY"
    elif price is None or price > validated:
        decision = "WATCH — ABOVE VALIDATED BUY LEVEL"
    else:
        decision = "REVIEW ENTRY — NOT AN ORDER"
    return {
        "ticker": row["ticker"], "name": row.get("name", ""),
        "market_group": row.get("sector", ""), "currency": row.get("currency", ""),
        "last_daily_close": price, "quote_date": row.get("quote_date"),
        "technical_priority_score": score, "technical_priority_label": label,
        "historical_watch_price": row.get("technical_watch_zone"),
        "historical_deep_price": row.get("technical_deep_zone"),
        "validated_buy_price": validated if evidence_complete else None,
        "provisional_research_buy": row.get("manual_provisional_buy_price"),
        "distance_above_historical_watch_pct": row.get("distance_to_watch_zone_pct"),
        "distance_above_validated_buy_pct": row.get("distance_to_validated_buy_pct") if evidence_complete else None,
        "fair_value_estimate": fv if evidence_complete else None,
        "valuation_evidence_status": "DOCUMENTED (NOT EXTERNALLY VERIFIED)" if evidence_complete else "MISSING",
        "data_status": row.get("data_status", ""),
        "research_decision": decision,
        "missing_research": "; ".join(gaps),
        "risk_notes": "; ".join(notes),
    }


def html_report(rows, payload):
    columns = ["ticker", "name", "currency", "last_daily_close", "quote_date",
               "technical_priority_score", "technical_priority_label", "historical_watch_price",
               "historical_deep_price", "validated_buy_price", "provisional_research_buy",
               "distance_above_historical_watch_pct", "distance_above_validated_buy_pct",
               "valuation_evidence_status", "research_decision", "missing_research", "risk_notes"]
    entries = []
    for r in rows:
        vals = []
        for key in columns:
            v = r[key]
            vals.append("—" if v is None or v == "" else escape(f"{v:.2f}" if isinstance(v,float) else str(v)))
        entries.append("<tr>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>")
    head = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Global Championship | 200-name research triage</title>
    <style>body{font:14px system-ui,sans-serif;background:#101b2a;color:#e6edf5;padding:16px}
    section{overflow:auto;border:1px solid #34445b;max-height:75vh}table{border-collapse:collapse;min-width:2700px}
    td,th{border-bottom:1px solid #34445b;padding:8px;text-align:left;white-space:nowrap}
    th{position:sticky;top:0;background:#203149}input{padding:10px;background:#203149;color:white;border:1px solid #63738e}
    p{line-height:1.6;max-width:900px}small{color:#aebfd3}</style>"""
    body = (f"<h1>Global Investment Championship — Research triage for {len(rows)} stocks</h1>"
            f"<p>Latest scan: {escape(str(payload.get('scan_sydney','Unknown')))} | "
            "<b>Every stock assessed under the same technical rules.</b></p>"
            "<p>This is an explicitly UNVALIDATED technical-research ranking, not expected return, "
            "investment conviction, fair value, win probability or an instruction to buy. "
            "Company fundamentals and upcoming catalysts have not been independently verified. "
            "The original technical watch/deep zones are historical heuristics, never fair-value conclusions. "
            "All transaction execution is disabled. Obtain fresh quotes before any investment decision.</p>"
            "<input id='q' aria-label='Filter' placeholder='Filter 200 companies...'>"
            "<section><table><thead><tr>" + "".join(f"<th>{escape(c.replace('_',' ').title())}</th>" for c in columns)
            + "</tr></thead><tbody>" + "".join(entries) + "</tbody></table></section>"
            "<script>document.getElementById('q').addEventListener('input',function(){let s=this.value.toLowerCase();"
            "document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(s));});</script>"
            "<p><small>Sorting is only a research workflow convenience. Results require further independent "
            "validation, fee/FX/tax modelling and out-of-sample testing. No orders can be generated.</small></p></html>")
    return head + body


def run_engine(source: Path = OUT / "latest.json", output: Path = OUT) -> dict:
    raw = json.loads(source.read_text(encoding="utf-8"))
    items = raw.get("stocks", [])
    if len(items) != 200 or len({v.get("ticker") for v in items}) != 200:
        raise ValueError("200 unique stock rows required; refuse partial/mismatched input")
    rows = [assess(r) for r in items]
    rows.sort(key=lambda r: (r["technical_priority_score"] is not None,
                             r["technical_priority_score"] or 0), reverse=True)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "opportunity_triage_200.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    (output / "opportunity_triage_200.html").write_text(html_report(rows, raw), encoding="utf-8")
    summary = {"scan_sydney": raw.get("scan_sydney"), "universe": len(rows),
               "technical_scores_available": sum(r["technical_priority_score"] is not None for r in rows),
               "fundamentally_validated_buy_count": sum(r["validated_buy_price"] is not None for r in rows),
               "trade_execution_enabled": False,
               "orders_generated": 0,
               "disclaimer": "Technical research triage only. No trade instructions, live quotes, verified intrinsic values or profit guarantees."}
    (output / "research_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_engine(), indent=2))
