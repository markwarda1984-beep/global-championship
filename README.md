# Global Investment Championship — 200-stock intensive scanner

**Monitoring only.** No broker access, no orders, no automatic purchases, no credentials.

This **upgrades** your existing 30-stock scanner to an equally detailed **200-stock** global watchlist. All original 30 names are preserved, including the **BABA $75 USD PROVISIONAL** watch price; the other 170 include US technology/AI, energy/materials, healthcare, finance, industrials, consumer, Australian ASX and international ADRs. We deliberately do **not** treat the top 20–30 as the only names needing research.

## Every stock, every run

For **each of the 200**, the dashboard and CSV show:

| Field | Meaning |
|---|---|
| Last daily close and bar date | Last accessible daily price from Yahoo Finance. **Not live or executable.** |
| Technical watch and deep zones | Automatically computed historical screening levels; **NOT verified purchase prices** |
| Manually validated buy price | Populated **only when** a documented fair-value analysis, source date and rationale are supplied |
| Manual provisional buy price | Existing research hypothesis (BABA), distinct from validated price |
| Distance to watch / validated buy | % last close above or below the respective level |
| Technical profile | 50-/200-day averages, 14-day RSI, 52-week low/high, % below high |
| Movement / risk | 5/20/63-session returns, annualised 20d historical volatility, volume ratio vs last 20 sessions |
| Data quality | Flagged unavailable, stale or incomplete daily-bar data |
| Equal monitoring | All 200 rows use the same calculation and reporting rules |

The HTML report is searchable and filterable on Android, and contains a **mini price-level graph and sparkline for every stock**. The machine-readable output is downloadable as `latest.csv` and `latest.json`.

Bitcoin independently displays AUD/USD ticker prices from Kraken's public spot ticker endpoint.

## About "really good" buy prices

A low historical price **does not establish genuine value**. The historical watch zone is the lower of (1) the 25th-percentile daily close from the past year or (2) the 200-session average, where available. A **deep historical zone** is 15% lower. Both are deliberately labelled *statistical research zones*, not a company valuation, prediction, good purchase price, or a buy recommendation.

A validated buy level must come from **company-specific** analysis of earnings, free cash flow, debt/capital structure, industry outlook, dilution, valuation multiples and scenarios. The editable `watchlist.csv` provides `fair_value`, `fair_value_date`, `valuation_method`, `risk_note`, `buy_price`, and `buy_validation` to record this analysis **for every company**. No empty cell is secretly filled with a fabricated valuation. The system rejects rows marked `VALIDATED` without supporting fair-value metadata.

This version **automates detailed quantitative monitoring of all 200**, but does **not** automatically complete expert company-level fair-value research, independently verify news or earnings, or produce personal tax advice. For full verified valuation coverage, a separate source-checked fundamentals/news research pipeline is required. Do not confuse a green chart indicator with approval to trade.

## Automatic schedule

GitHub Actions schedules all 200 at **02:20, 08:20, 10:20, 13:20, 16:20, 21:20 Australia/Sydney** daily, including daylight saving. Runs can be delayed or occasionally omitted by GitHub. Yahoo Finance is unofficial and can rate limit or return missing results. A batch size of 25 reduces requests versus one-by-one downloads, but does **not** guarantee 200/200 coverage. The output always states the count and missing data.

## Get report on your phone

1. Open [the repository Actions tab](https://github.com/markwarda1984-beep/global-championship/actions).
2. Select the newest **Championship intensive 200-stock scan** successful run.
3. Under **Artifacts**, download `championship-200-dashboard-*`.
4. Extract and open `index.html`; `latest.csv` contains all 200 rows. Artifacts expire after 14 days.

## Upgrade from Android using GitSync

1. **Do not erase your existing `.git` directory** in `Documents/global-championship`.
2. Extract the 200-stock upgrade ZIP somewhere outside the GitSync folder.
3. Enable **Show hidden system files** in Samsung My Files so `.github` is visible.
4. Copy the *contents* of the extracted upgrade (not the outer directory) into `Documents/global-championship`, choosing **Replace existing files** for `scan.py`, `watchlist.csv`, `README.md`, `requirements.txt`, `tests/` and `.github/workflows/scan.yml`. Do not copy a `.git` directory; this package contains none.
5. In GitSync, select **three dots next to Sync Changes → Upload Changes**. **Do not use Upload + Overwrite**.
6. Confirm the push on GitHub and open the **Actions** tab to verify the online run succeeds.

## Local testing

With Python 3.11+ and dependencies installed:

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scan.py
```

Offline unit tests simulate data and do **not** prove online quotes work. A live GitHub workflow run must be checked to confirm actual coverage. No brokerage integrations are present.

## Championship 3.0: research triage and evidence gates

A **separate read-only research layer** runs after each 200-stock price scan:

- `opportunity_engine.py` processes **all 200**, no exceptions.
- `opportunity_triage_200.html` is a searchable technical-research priority list.
- `opportunity_triage_200.csv` includes the latest available daily price, unvalidated historical zones, manual price research, missing fundamental/catalyst evidence, and data quality.
- `research_summary.json` explicitly reports valuation coverage and `orders_generated: 0`.

The heuristic priority score is **not** a probability of profit, investment-quality score, predicted return or authorisation to trade. It has not been independently backtested. It never fabricates valuation or earnings data. Source-confirmed business valuations and event-driven intelligence require separate data collection and independent source review; no claim of that automation is made here.

**Cory-style methodology used as an inspiration, not a verified replication:** evaluate business cycles, normalised earnings, company-specific valuation, and disciplined sizing. Growth and speculative firms require different models; historical price discounts alone do not make a bargain.

**Future execution policy:** This repository contains no broker keys, live execution, trading endpoints, order templates or unattended buy/sell tasks. Any future integration would require a supported regulated brokerage connection and an explicit, individually approved order in the live account; a research score cannot execute an order. Until then, paper-trade proposals are for discussion only.

Important caveats: 200 stocks share the same *technical* monitoring, but they do not yet have 200 independently source-checked fundamental valuations, earnings-event calendars or news monitoring. No out-of-sample performance track record exists for the ranking method. Rates, FX, slippage, tax, sector concentration, bankruptcy risk and survivorship bias can substantially alter results.
