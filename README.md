# Global Investment Championship — 4.0 weekly valuation + 200-stock intensive scanner

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


---

# Championship 4.0 — weekly company-specific valuation research (new)

**Deployment note:** This ZIP is an overlay to the existing 3.0 repository, not a full replacement. Keep every 3.0 file and the `.git` folder. Copy only the included new `valuation_engine.py`, `tests/test_valuation_engine.py`, `.github/workflows/valuation.yml`, and the updated README. Do not replace your watchlist or daily scan.

## What runs and when

- The **3.0 daily price scanner is unchanged**: six runs every day at 02:20, 08:20, 10:20, 13:20, 16:20 and 21:20 Sydney time.
- A **separate 4.0 fundamentals job** is scheduled every **Sunday at 03:10 Australia/Sydney** (DST-aware). It also starts after your first GitSync push of the new valuation files and can be triggered through Actions → Run workflow. GitHub schedules are best effort; Yahoo Finance fundamentals can be rate-limited and incomplete.
- The new valuation workflow fetches the latest available daily bars for 200 names, then checks **all 200** for source-labelled fundamental fields with conservative model assumptions. It leaves blocked and specialist names unvalued rather than supplying fake prices.
- The job creates **`valuation_200.csv`**, **`valuation_200.html`**, **`valuation_200.json`**, and **`valuation_200_run_summary.json`**, uploaded as a 14-day-retained downloadable GitHub artifact. This is an independent weekly download; the daily 3.0 dashboard is not automatically joined to it.

## How models are selected

| Business | Preliminary approach | Important limitation |
|---|---|---|
| Ordinary cash-generative companies | Five-year equity free-cash-flow sensitivity model | Uses public snapshot data; no audited 3-year normalisation for noncyclicals; equity FCF may include one-off items |
| Banks/insurers | Illustrative justified price-to-book sensitivity using book value and ROE | Simplified model does not verify capital adequacy, provisioning, losses, regulation or underwriting cycle |
| Resources/energy/cyclicals | Requires at least 3 positive annual cash-flow observations before a scenario can be displayed | Even 3 years are not a commodity-cycle NAV or through-cycle owner earnings |
| Biotech, REITs and complex financial firms | Deliberately **unvalued** by generic model | Need probability-weighted pipeline/asset modelling, AFFO/NAV or specialist capital/custody/asset-management work |
| Negative FCF, insufficient statements, stale reports, ADR/currency mismatch | **No price estimate** | Requires further source verification or specialist model |

The model reports **bear/base/bull fair-value scenarios** and **indicative research watch/deep prices** where its input criteria pass. These values remain `INDICATIVE MODEL — NOT VERIFIED OR APPROVED`; they are **not "VALIDATED" buy prices**, investment recommendations or executable limit prices. No 3.0 watchlist fields are silently promoted to validated. User approval, audited information, realistic growth, leverage, scenario testing, dilution, taxes, fees, currency exposure and a documented investment thesis remain necessary.

## Data integrity and cost

The workflow uses `yfinance` (unofficial Yahoo Finance data, no paid subscription) for snapshot fundamentals and stock daily bars. Its completeness cannot be guaranteed. It checks publication-date proxies, quote/financial currency agreement, share-count and market-cap consistency, cash-flow sign and sector suitability. Fiscal date is source-reported and may not be the date a filing was published. **All 200 names appear**, including explicit errors if Yahoo is unavailable. Reports do not claim a 200/200 successful fundamentals refresh unless it occurs.

The most recent fetch time is not proof that underlying filings or fundamentals are current. These values are hypotheses for human research, not independently verified intrinsic values. Every successful run is a snapshot; historical reports are not durable beyond the 14-day artifact retention unless saved separately.

## View weekly valuation report

1. Open your repository → **Actions**.
2. Select **Championship 4.0 weekly valuation research** and the latest completed run.
3. Under **Artifacts**, download `championship-valuation-4-...`.
4. Unzip and open **`valuation_200.html`** on your phone, or view `valuation_200.csv` in a spreadsheet.
5. Check `valuation_200_run_summary.json` for how many names had sufficient inputs to produce indicative models. **Model coverage is not the same as fundamental validation.**

## Security

No broker integration, passwords, trading keys, order placement, buy/sell automation or write-access token is required. GitHub workflow uses `contents: read` only. Before making any investment decision, obtain a current executable quote and verify official company filings and brokerage/tax costs. This is a high-risk research system, not a profit guarantee.
