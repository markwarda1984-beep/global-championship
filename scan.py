"""Public-data, research-only price monitor. Does not connect to brokers or place trades."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
SYDNEY = ZoneInfo("Australia/Sydney")
FIELDS = ("ticker", "name", "buy_price", "status")


def load_watchlist(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not set(FIELDS).issubset(reader.fieldnames or ()):
            raise ValueError(f"watchlist must contain {', '.join(FIELDS)}")
        stocks = [{k: (row.get(k) or "").strip() for k in FIELDS} for row in reader]
    tickers = [r["ticker"] for r in stocks]
    if len(stocks) != 30 or len(set(tickers)) != 30 or not all(tickers):
        raise ValueError("Starter watchlist must have exactly 30 unique, nonempty tickers")
    for row in stocks:
        if row["buy_price"]:
            buy = float(row["buy_price"])
            if not math.isfinite(buy) or buy <= 0:
                raise ValueError(f"Invalid buy_price for {row['ticker']}")
    return stocks


def distance_above_target(price: float | None, buy_price: str) -> float | None:
    """Positive means current close is ABOVE the unvalidated research level."""
    if price is None or not buy_price:
        return None
    return round((price / float(buy_price) - 1.0) * 100, 2)


def currency_for(ticker: str) -> str:
    return "AUD" if ticker.upper().endswith(".AX") else "USD"


def fetch_stock(ticker: str) -> dict:
    """Last daily bars from unofficial Yahoo Finance; never treated as live quotes."""
    import yfinance as yf

    frame = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=False)
    if frame is None or frame.empty:
        raise ValueError("No historical daily bars returned")
    points = [(date, float(close)) for date, close in zip(frame.index, frame["Close"])
              if math.isfinite(float(close)) and float(close) > 0]
    if not points:
        raise ValueError("No valid closing prices")
    date, last = points[-1]
    quote_date = date.isoformat()
    # The bar date is an exchange trading date, not a live timestamp.
    return {"price": round(last, 5), "quote_date": quote_date,
            "history": [round(v, 5) for _, v in points[-30:]]}


def fetch_bitcoin(pair: str) -> dict:
    """Public Kraken spot ticker; prices reflect an exchange and are not tradable guarantees."""
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
    coords = " ".join(f"{(i * 120 / (len(values)-1)):.1f},{(29-(v-low)*26/spread):.1f}"
                      for i, v in enumerate(values))
    return ('<svg width="120" height="32" viewBox="0 0 120 32" role="img" '
            'aria-label="Recent daily closing prices"><polyline fill="none" '
            'stroke="currentColor" stroke-width="1.8" points="' + coords + '"/></svg>')


def render_html(data: dict) -> str:
    body = []
    for row in data["stocks"]:
        fmt = lambda k: escape(str(row.get(k) if row.get(k) is not None else "—"))
        distance = row.get("distance_above_target_pct")
        dist_text = "—" if distance is None else f"{distance:+.2f}%"
        body.append("<tr>" + "".join(f"<td>{v}</td>" for v in (
            fmt("ticker"), fmt("currency"), fmt("price"),
            fmt("buy_price") if row["buy_price"] else "Unresearched",
            escape(dist_text), fmt("status"), fmt("quote_date"), fmt("data_status"),
            sparkline(row.get("history") or []))) + "</tr>")
    btc = []
    for pair, item in data["bitcoin"].items():
        label = "AUD" if pair == "XBTAUD" else "USD"
        if "error" in item:
            btc.append(f"<p><b>BTC/{label}</b>: unavailable ({escape(item['error'])})</p>")
        else:
            btc.append(f"<p><b>BTC/{label}</b>: last {item['last']:,.2f}, "
                       f"bid {item['bid']:,.2f}, ask {item['ask']:,.2f}</p>")
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Global Investment Championship</title>
<style>body{font:15px system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:14px}
h1{font-size:22px}small{color:#cbd5e1}section{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #334155;padding:8px;text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#1e293b}svg{color:#7dd3fc}</style></head><body>""" + (
        f"<h1>Global Investment Championship</h1><p>Scan: {escape(data['scan_sydney'])}</p>"
        f"<p><b>Watchlist:</b> {len(data['stocks'])} stocks; "
        f"{data['stock_quotes_available']} with daily-price data. "
        "<b>Research only, not live quotes or trade signals.</b></p>"
        "<p>Planned A$1,000 test capital — not yet funded. No confirmed holdings. No trades.</p>"
        "<h2>Separate Bitcoin monitor</h2>" + "".join(btc) +
        f"<small>Bitcoin quotes retrieved at {escape(data['scan_utc'])}; exchange prices may differ.</small>"
        "<h2>30-stock watchlist</h2><section><table><thead><tr>"
        "<th>Ticker</th><th>Currency</th><th>Last daily close</th>"
        "<th>Research buy level</th><th>Close above level</th><th>Research status</th>"
        "<th>Bar date</th><th>Data status</th><th>Recent closes</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></section>"
        "<p><small>Unresearched levels are deliberately blank. BABA's level is PROVISIONAL; "
        "a price reaching a level is not a recommendation. USD and AUD share prices are not directly "
        "comparable. Yahoo Finance history can be delayed, incomplete or inaccessible. "
        "Sparkline displays available daily closes, not an intraday price chart. "
        "This starter does not scan every listed stock or calculate validated readiness scores.</small></p>"
        "</body></html>"
    )


def run_scan(watchlist: Path = BASE / "watchlist.csv", output: Path = BASE / "data",
             stock_fetcher=fetch_stock, btc_fetcher=fetch_bitcoin,
             now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Scan timestamp must be timezone-aware")
    stocks = load_watchlist(watchlist)
    for row in stocks:
        row.update(currency=currency_for(row["ticker"]), price=None,
                   quote_date=None, history=[], distance_above_target_pct=None,
                   data_status="UNAVAILABLE")
        try:
            quote = stock_fetcher(row["ticker"])
            price = float(quote["price"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("Invalid price")
            row.update(price=price, quote_date=quote["quote_date"],
                       history=quote.get("history", []),
                       distance_above_target_pct=distance_above_target(price, row["buy_price"]),
                       data_status="LAST DAILY BAR — NOT LIVE")
        except Exception as exc:
            row["data_status"] = f"UNAVAILABLE: {str(exc)[:90]}"
    bitcoin = {}
    for pair in ("XBTAUD", "XBTUSD"):
        try:
            bitcoin[pair] = btc_fetcher(pair)
        except Exception as exc:
            bitcoin[pair] = {"error": str(exc)[:150]}
    quote_count = sum(row["price"] is not None for row in stocks)
    payload = {"scan_utc": now.astimezone(timezone.utc).isoformat(),
               "scan_sydney": now.astimezone(SYDNEY).isoformat(),
               "stock_quotes_available": quote_count,
               "stocks": stocks, "bitcoin": bitcoin,
               "planned_test_capital_aud": 1000,
               "funding_status": "NOT_YET_FUNDED",
               "confirmed_holdings": [], "trade_execution_enabled": False}
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = ("ticker", "name", "currency", "price", "quote_date", "buy_price", "distance_above_target_pct", "status", "data_status")
    with (output / "latest.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(stocks)
    (output / "index.html").write_text(render_html(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    summary = run_scan()
    print(f"Research scan complete: {summary['stock_quotes_available']}/30 daily stock bars, "
          f"Bitcoin pairs checked: {', '.join(summary['bitcoin'])}")
    if summary["stock_quotes_available"] == 0 and all("error" in q for q in summary["bitcoin"].values()):
        raise SystemExit("All external market feeds failed; inspect uploaded data artifact")
