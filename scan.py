"""Global Investment Championship | 200-stock, read-only research monitor.

No broker integration. Daily OHLCV histories are not executable live quotes.
Historical price zones are mechanically generated and not investment valuations.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
SYDNEY = ZoneInfo("Australia/Sydney")
REQUIRED_FIELDS = ("ticker", "name", "sector", "buy_price", "buy_validation", "status",
                   "fair_value", "fair_value_date", "valuation_method", "risk_note")
BATCH_SIZE = 25
EXPECTED_STOCKS = 200


def positive_float(value, *, label: str):
    if str(value).strip() == "":
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"Invalid {label}: {value}")
    return number


def load_watchlist(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not set(REQUIRED_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError(f"Watchlist missing required columns: {REQUIRED_FIELDS}")
        rows = [{column: (row.get(column) or "").strip() for column in REQUIRED_FIELDS}
                for row in reader]
    symbols = [r["ticker"].upper() for r in rows]
    if len(rows) != EXPECTED_STOCKS or len(set(symbols)) != EXPECTED_STOCKS or not all(symbols):
        raise ValueError(f"Watchlist must contain exactly {EXPECTED_STOCKS} unique, nonempty tickers")
    for row in rows:
        positive_float(row["buy_price"], label=f"buy_price of {row['ticker']}")
        positive_float(row["fair_value"], label=f"fair_value of {row['ticker']}")
        validation = row["buy_validation"].upper()
        if validation not in {"UNRESEARCHED", "PROVISIONAL", "VALIDATED"}:
            raise ValueError(f"Unsupported buy_validation on {row['ticker']}")
        if validation == "VALIDATED" and not (row["buy_price"] and row["fair_value"] and
                                              row["fair_value_date"] and row["valuation_method"]):
            raise ValueError(f"VALIDATED requires buy price, fair value, methodology and date: {row['ticker']}")
    return rows


def currency_for(ticker: str) -> str:
    suffix = ticker.upper().split(".")[-1] if "." in ticker else ""
    return {"AX": "AUD", "TO": "CAD", "V": "CAD", "L": "GBP", "HK": "HKD",
            "DE": "EUR", "PA": "EUR", "SW": "CHF", "T": "JPY", "SI": "SGD", "NS": "INR"}.get(suffix, "USD")


def percentage_change(current: float, prior: float | None):
    return round((current / prior - 1) * 100, 2) if prior and prior > 0 else None


def pct_distance(current: float | None, target: float | None):
    """Positive percentage = last daily price ABOVE level; negative = BELOW level."""
    return round((current / target - 1) * 100, 2) if current and target else None


def rsi14(closes: list[float]) -> float | None:
    if len(closes) < 15:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
    gain = statistics.mean(max(d, 0) for d in deltas)
    loss = statistics.mean(max(-d, 0) for d in deltas)
    if gain == 0 and loss == 0:
        return 50.0
    if loss == 0:
        return 100.0
    return round(100 - (100 / (1 + gain / loss)), 1)


def percentile_25(values: list[float]) -> float:
    # Linear interpolation at the nearest 25th-percentile point of sorted closes.
    ordered = sorted(values)
    position = (len(ordered) - 1) * .25
    i = math.floor(position)
    weight = position - i
    return ordered[i] * (1 - weight) + ordered[min(i + 1, len(ordered) - 1)] * weight


def compute_metrics(quote: dict, metadata: dict, now: datetime) -> dict:
    closes = [float(v) for v in quote.get("closes", [])]
    volumes = [float(v) for v in quote.get("volumes", [])]
    if len(closes) < 2 or not all(math.isfinite(v) and v > 0 for v in closes):
        raise ValueError("Insufficient valid daily closing prices")
    last = closes[-1]
    recent = closes[-252:]
    low52, high52 = min(recent), max(recent)
    sma50 = statistics.mean(closes[-50:]) if len(closes) >= 50 else None
    sma200 = statistics.mean(closes[-200:]) if len(closes) >= 200 else None
    # These are HISTORICAL SEARCH ZONES, NOT fair-value/buy recommendations.
    watch_zone = round(min(percentile_25(recent), sma200 or float("inf")), 5) if len(recent) >= 60 else None
    deep_zone = round(watch_zone * .85, 5) if watch_zone else None
    buy = positive_float(metadata["buy_price"], label="buy_price")
    fair = positive_float(metadata["fair_value"], label="fair_value")
    validation = metadata["buy_validation"]
    validated_buy = buy if validation == "VALIDATED" else None

    change_5d = percentage_change(last, closes[-6] if len(closes) >= 6 else None)
    change_20d = percentage_change(last, closes[-21] if len(closes) >= 21 else None)
    change_63d = percentage_change(last, closes[-64] if len(closes) >= 64 else None)
    return_vol = None
    if len(closes) >= 22:
        daily = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 20, len(closes))]
        return_vol = round(statistics.stdev(daily) * math.sqrt(252) * 100, 1)
    vol_ratio = None
    if len(volumes) >= 21 and all(math.isfinite(v) and v >= 0 for v in volumes[-21:]):
        baseline = statistics.mean(volumes[-21:-1])
        vol_ratio = round(volumes[-1] / baseline, 2) if baseline > 0 else None

    quote_date = str(quote.get("quote_date") or "")
    stale_days = None
    try:
        date = datetime.fromisoformat(quote_date)
        if date.tzinfo is not None:
            stale_days = max(0, (now - date.astimezone(timezone.utc)).days)
        else:
            stale_days = max(0, (now.date() - date.date()).days)
    except ValueError:
        pass
    signal = "HISTORICAL DATA SHORT" if watch_zone is None else "ABOVE HISTORICAL WATCH ZONE"
    if watch_zone is not None:
        diff = pct_distance(last, watch_zone)
        if diff <= 0:
            signal = "AT/BELOW HISTORICAL WATCH ZONE"
        elif diff <= 5:
            signal = "WITHIN 5% OF HISTORICAL WATCH ZONE"
    if validated_buy and last <= validated_buy:
        signal = "BELOW MANUALLY VALIDATED BUY LEVEL — VERIFY THESIS"
    if stale_days is not None and stale_days > 7:
        signal = "STALE DATA — REVIEW"

    from championship_90 import trading_lows
    levels = trading_lows(quote.get("lows", []), closes)
    levels["trading_low_52w"] = levels.pop("low_52w")
    return {
        **levels,
        "currency": quote.get("currency") or currency_for(metadata["ticker"]),
        "price": round(last, 5),
        "quote_date": quote_date,
        "stale_days": stale_days,
        "lookback_sessions": len(recent),
        "low_52w": round(low52, 5),
        "high_52w": round(high52, 5),
        "drawdown_from_high_pct": pct_distance(last, high52),
        "sma_50": round(sma50, 5) if sma50 else None,
        "sma_200": round(sma200, 5) if sma200 else None,
        "rsi_14": rsi14(closes),
        "change_5d_pct": change_5d,
        "change_20d_pct": change_20d,
        "change_63d_pct": change_63d,
        "volatility_20d_annual_pct": return_vol,
        "volume_ratio_20d": vol_ratio,
        "technical_watch_zone": watch_zone,
        "technical_deep_zone": deep_zone,
        "distance_to_watch_zone_pct": pct_distance(last, watch_zone),
        "distance_to_validated_buy_pct": pct_distance(last, validated_buy),
        "distance_to_manual_provisional_pct": pct_distance(last, buy) if validation == "PROVISIONAL" else None,
        "validated_buy_price": validated_buy,
        "manual_provisional_buy_price": buy if validation == "PROVISIONAL" else None,
        "fair_value_estimate": fair,
        "signal": signal,
        "history": [round(v, 5) for v in recent[-30:]],
        "data_status": "DAILY HISTORY — NOT LIVE" if stale_days is None or stale_days <= 7 else "STALE DAILY HISTORY",
    }


def fetch_batch(tickers: list[str]) -> dict[str, dict]:
    """Batch 25 Yahoo Finance daily OHLCV histories. Partial failures are represented as missing."""
    import yfinance as yf

    frame = yf.download(tickers, period="1y", interval="1d", group_by="ticker",
                        auto_adjust=False, actions=False, progress=False,
                        threads=4, timeout=12, multi_level_index=True)
    if frame is None or frame.empty:
        return {}
    out = {}
    for ticker in tickers:
        try:
            block = frame[ticker]  # top-level ticker index with group_by=ticker
            rows = block[["Close", "Low", "Volume"]].dropna(subset=["Close"])
            closes, volumes, valid_dates, lows = [], [], [], []
            for dt, row in rows.iterrows():
                close, vol = float(row["Close"]), float(row["Volume"])
                if math.isfinite(close) and close > 0:
                    closes.append(close)
                    low = float(row["Low"])
                    lows.append(low if math.isfinite(low) and low > 0 else None)
                    volumes.append(vol if math.isfinite(vol) and vol >= 0 else 0.0)
                    valid_dates.append(dt)
            if len(closes) < 2:
                continue
            # Use the timestamp of the last valid trading row, not current clock time.
            out[ticker] = {"closes": closes, "volumes": volumes, "lows": lows,
                           "quote_date": valid_dates[-1].isoformat()}
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def fetch_bitcoin(pair: str) -> dict:
    import requests

    reply = requests.get("https://api.kraken.com/0/public/Ticker", params={"pair": pair}, timeout=15)
    reply.raise_for_status()
    doc = reply.json()
    if doc.get("error"):
        raise ValueError(str(doc["error"]))
    result = doc.get("result") or {}
    if not result:
        raise ValueError("Kraken returned no ticker")
    tick = next(iter(result.values()))
    return {"last": float(tick["c"][0]), "bid": float(tick["b"][0]),
            "ask": float(tick["a"][0])}


def sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return "—"
    low, high = min(values), max(values)
    spread = max(high - low, 1e-8)
    coords = " ".join(f"{(i*104/(len(values)-1)):.1f},{(24-(v-low)*20/spread):.1f}"
                      for i, v in enumerate(values))
    return ('<svg width="104" height="28" viewBox="0 0 104 28" aria-label="Recent daily closes" '
            'role="img"><polyline fill="none" stroke="#38bdf8" stroke-width="1.7" points="' + coords + '"/></svg>')


def level_bar(row: dict) -> str:
    price, watch, deep, validated = (row.get(k) for k in
                                     ("price", "technical_watch_zone", "technical_deep_zone", "validated_buy_price"))
    levels = [float(x) for x in (price, watch, deep, validated) if isinstance(x, (float, int))]
    if len(levels) < 2:
        return "—"
    min_price, max_price = min(levels), max(levels)
    spread = max(max_price - min_price, max_price * .01)
    x = lambda v: 12 + 170 * (v - min_price) / spread
    marks = [(deep, "#64748b", "Deep historical zone"), (watch, "#f59e0b", "Historical watch zone"),
             (validated, "#10b981", "Manually validated buy price"), (price, "#38bdf8", "Latest daily close")]
    lines = ['<svg width="195" height="30" viewBox="0 0 195 30" role="img" aria-label="Price level comparison">',
             '<line x1="12" x2="182" y1="15" y2="15" stroke="#64748b" stroke-width="2"/>']
    for v, color, title in marks:
        if isinstance(v, (float, int)):
            lines.append(f'<circle cx="{x(v):.1f}" cy="15" r="5" fill="{color}"><title>{title}: {v:.3f}</title></circle>')
    lines.append('</svg>')
    return "".join(lines)


def format_cell(value, digits=2):
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return escape(str(value))


def render_html(data: dict) -> str:
    body = []
    for row in data["stocks"]:
        ticker = escape(row["ticker"])
        fields = ["ticker", "name", "sector", "currency", "price", "technical_watch_zone",
                  "technical_deep_zone", "validated_buy_price", "manual_provisional_buy_price",
                  "distance_to_watch_zone_pct", "distance_to_validated_buy_pct", "rsi_14",
                  "sma_50", "sma_200", "low_52w", "high_52w", "drawdown_from_high_pct",
                  "change_20d_pct", "volatility_20d_annual_pct", "volume_ratio_20d",
                  "quote_date", "signal", "buy_validation", "data_status"]
        vals = [format_cell(row.get(k)) for k in fields]
        # Use data state for the client-side filter; all 200 are included equally.
        text_data = escape(" ".join(str(row.get(k, "")) for k in ("ticker", "name", "sector", "signal")))
        body.append(f'<tr data-search="{text_data.lower()}" data-signal="{escape(str(row.get("signal", "")))}">' +
                    "".join(f"<td>{val}</td>" for val in vals) +
                    f"<td>{level_bar(row)}</td><td>{sparkline(row.get('history') or [])}</td></tr>")

    bitcoin = []
    for pair, quote in data["bitcoin"].items():
        label = "AUD" if pair == "XBTAUD" else "USD"
        bitcoin.append((f"<b>BTC/{label}:</b> " +
                        (f"{quote['last']:,.2f} last · bid {quote['bid']:,.2f} · ask {quote['ask']:,.2f}"
                         if "error" not in quote else f"Unavailable ({escape(str(quote['error']))})")))

    headers = ["Ticker", "Company", "Market group", "Currency", "Last daily close", "Historical watch",
               "Historical deep", "Validated buy", "Manual provisional buy", "% above watch",
               "% above validated", "RSI 14", "SMA 50", "SMA 200", "52w low", "52w high",
               "% from 52w high", "20-session return %", "20d vol annual %", "Relative volume",
               "Bar date", "Research alert", "Buy validation", "Quote status", "Price-level bar", "30-day sparkline"]
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>200-stock Global Investment Championship</title><style>
:root{color-scheme:dark}body{font:14px system-ui,sans-serif;background:#0b1220;color:#e2e8f0;margin:0;padding:14px}
h1{font-size:22px;margin:.4em 0}p{line-height:1.6}small{color:#cbd5e1}.summary{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.summary article{padding:10px 14px;background:#17243a;border:1px solid #2d3d52;border-radius:10px}
strong.big{font-size:22px;display:block}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
input,select{background:#17243a;border:1px solid #41536d;border-radius:7px;color:#fff;padding:10px;max-width:100%}
input{flex:1;min-width:190px}table{border-collapse:collapse;min-width:2500px;width:100%;font-size:12px}
th,td{border-bottom:1px solid #29394d;padding:7px;text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#1d2b42;cursor:pointer}tr:hover{background:#17243a}
.table-wrap{overflow:auto;max-height:75vh;border:1px solid #34445d;border-radius:8px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px}.dot{width:9px;height:9px;display:inline-block;border-radius:50%;margin-right:4px}
.notice{border-left:3px solid #cbd5e1;padding:8px 12px;background:#17243a;margin:12px 0}
a{color:#7dd3fc}
</style></head><body>'''
    page += (f'<h1>Global Investment Championship — all 200 stocks</h1><p>Scan (Sydney): {escape(data["scan_sydney"])}</p>'
             f'<div class="summary"><article>Universe<strong class="big">{len(data["stocks"])}</strong></article>'
             f'<article>Daily bars returned<strong class="big">{data["stock_quotes_available"]}</strong></article>'
             f'<article>Missing quotes<strong class="big">{len(data["stocks"])-data["stock_quotes_available"]}</strong></article>'
             f'<article>Manually validated buy levels<strong class="big">{data["validated_buy_count"]}</strong></article></div>'
             '<div class="notice"><b>Research-only.</b> Prices are historical daily bars, not live executable quotes. '
             'Orange/grey markers are purely statistical historical price zones (NOT good-value purchases); '
             'green markers appear only for manually validated valuation prices. Blank valuations are intentional. '
             'A price crossing a level is not a trade recommendation. No trades or broker connections.</div>'
             '<p>Separate Bitcoin tracker: ' + ' | '.join(bitcoin) + '</p>'
             '<p class="legend"><span><i class="dot" style="background:#38bdf8"></i>Latest daily price</span>'
             '<span><i class="dot" style="background:#f59e0b"></i>Historical watch</span>'
             '<span><i class="dot" style="background:#64748b"></i>Historical deep</span>'
             '<span><i class="dot" style="background:#10b981"></i>Validated buy</span></p>'
             '<div class="controls"><input id="search" placeholder="Search any of 200 stocks, sectors or alerts" autocomplete="off">'
             '<select id="filter"><option value="all">All 200</option><option value="near">At/near watch zone</option>'
             '<option value="missing">Missing/stale quote</option><option value="validated">Validated buy price</option></select>'
             '<span id="shown"></span></div>'
             '<div class="table-wrap"><table id="table"><thead><tr>' +
             ''.join('<th>'+escape(name)+'</th>' for name in headers) + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'
             '<p><small>All 200 stocks are assessed by the same quantitative rules at each scan. The history-based watch '
             'zone is the lower of the trailing one-year 25th percentile close and the 200-session average; the '
             'historical deep zone is 15% lower. These are fixed statistical heuristics, not intrinsic valuations. '
             'A genuine buy price requires recorded company-specific fair-value research, evidence and a margin of safety. '
             'News, earnings, credit risk, debt, dilution and business quality are NOT automatically verified by this version. '
             'Yahoo data may be delayed, blocked or stale; coverage is explicitly reported. No Australian tax treatment '
             'is assumed. Bitcoin is an independent indicative Kraken quote.</small></p>'
             '<script>const rows=[...document.querySelectorAll("#table tbody tr")];const q=document.querySelector("#search");'
             'const f=document.querySelector("#filter");const shown=document.querySelector("#shown");'
             'function update(){const needle=q.value.toLowerCase().trim(),mode=f.value;let count=0;'
             'for(const r of rows){let ok=r.dataset.search.includes(needle);const cells=r.cells;'
             'if(mode==="near")ok=ok && (/ZONE/.test(r.dataset.signal) && (/WITHIN 5%|AT/BELOW/.test(r.dataset.signal)));'
             'if(mode==="missing")ok=ok && (/UNAVAILABLE|STALE/.test(cells[23].textContent));'
             'if(mode==="validated")ok=ok && (cells[7].textContent!=="—");'
             'r.style.display=ok?"":"none";if(ok)count++;}shown.textContent=count+" / "+rows.length+" shown";}'
             'q.addEventListener("input",update);f.addEventListener("change",update);update();</script></body></html>')
    return page


def run_scan(watchlist: Path = BASE / "watchlist.csv", output: Path = BASE / "data",
             batch_fetcher=fetch_batch, btc_fetcher=fetch_bitcoin,
             now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Scan time must have a timezone")
    rows = load_watchlist(watchlist)
    for row in rows:
        row.update(currency=currency_for(row["ticker"]), price=None, quote_date=None,
                   validated_buy_price=None, manual_provisional_buy_price=None,
                   technical_watch_zone=None, technical_deep_zone=None,
                   distance_to_watch_zone_pct=None, distance_to_validated_buy_pct=None,
                   history=[], signal="DATA UNAVAILABLE", data_status="UNAVAILABLE")
    for start in range(0, len(rows), BATCH_SIZE):
        chunk = rows[start:start+BATCH_SIZE]
        symbols = [r["ticker"] for r in chunk]
        try:
            quotes = batch_fetcher(symbols)
        except Exception as exc:
            quotes = {}
            for row in chunk:
                row["data_status"] = f"UNAVAILABLE (batch): {str(exc)[:70]}"
        for row in chunk:
            quote = quotes.get(row["ticker"])
            if quote is None:
                continue
            try:
                row.update(compute_metrics(quote, row, now))
            except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
                row["data_status"] = f"UNAVAILABLE (invalid): {str(exc)[:70]}"
    bitcoin = {}
    for pair in ("XBTAUD", "XBTUSD"):
        try:
            bitcoin[pair] = btc_fetcher(pair)
        except Exception as exc:
            bitcoin[pair] = {"error": str(exc)[:150]}
    quote_count = sum(r["price"] is not None for r in rows)
    payload = {"scan_utc": now.astimezone(timezone.utc).isoformat(),
               "scan_sydney": now.astimezone(SYDNEY).isoformat(),
               "stock_quotes_available": quote_count,
               "validated_buy_count": sum(r["validated_buy_price"] is not None for r in rows),
               "stocks": rows, "bitcoin": bitcoin,
               "data_quality": "YAHOO HISTORICAL DAILY BARS; NOT REAL TIME",
               "planned_test_capital_aud": 1000, "funding_status": "NOT_YET_FUNDED",
               "confirmed_holdings": [], "trade_execution_enabled": False}
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    csv_fields = ("ticker", "name", "sector", "currency", "price", "technical_watch_zone",
                  "technical_deep_zone", "validated_buy_price", "manual_provisional_buy_price",
                  "distance_to_watch_zone_pct", "distance_to_validated_buy_pct", "rsi_14",
                  "sma_50", "sma_200", "low_52w", "high_52w", "drawdown_from_high_pct",
                  "change_5d_pct", "change_20d_pct", "change_63d_pct", "volatility_20d_annual_pct",
                  "volume_ratio_20d", "quote_date", "signal", "buy_validation", "fair_value",
                  "fair_value_date", "valuation_method", "risk_note", "status", "data_status")
    with (output / "latest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (output / "index.html").write_text(render_html(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run_scan()
    print(f"Global research scan: {result['stock_quotes_available']}/{len(result['stocks'])} stocks with daily bars; "
          f"Bitcoin: {', '.join(result['bitcoin'])}; no trades")
    if result["stock_quotes_available"] == 0 and all("error" in q for q in result["bitcoin"].values()):
        raise SystemExit("All market feeds unavailable")
