# Championship 6.0 — Primary-Evidence Full-Cycle Valuation Layer

This is **original research software**, informed by Cory Cramer's publicly discussed emphasis on stock-specific, full-cycle historical analysis and disciplined entry prices. It is **not** Cory Cramer's proprietary model, a reproduction of his paid signals, or an endorsement from him.

**Research only: no trades, brokers, orders, purchase approvals or expected win probabilities.** The original 200-stock scanner, Yahoo price history, 5.2 discovery, 5.4 document verification, scan-to-scan change engine, journal, AUD tax/offset comparison and existing report outputs remain intact. This package **does not replace** `watchlist.csv`, `scan.py`, `discovery_engine.py`, `valuation_engine.py`, `evidence_upgrade_54.py`, `intelligence_layer_51.py`, `report_bridge.py`, or `requirements.txt`.

## What it does

* Creates **exactly 200 original stock rows**, plus one row for each independently monitored discovery candidate, in `reports/valuation_60_latest.json`. The separate discovery list can grow; the original watchlist never changes.
* Publishes each stock's **date and currency of the last non-executable closing price**, daily-bar price momentum, filed annual net-income momentum, relevant valuation method, source confidence, risks, and precise missing-evidence flags.
* When its *primary financial inputs* are validated, publishes a **scenario-derived intrinsic value estimate** (not a verifiable fact), bear/base/bull, 10%, 15% and 20% base-value discounts, current-price distance to each proposed entry, and a margin-of-safety choice informed by earnings/price momentum. It never turns momentum into a validated filing or an automatic order.
* When a company lacks suitable issuer financials, a comparable share/ADR basis, several historical years, a recent price or a specialist asset or clinical appraisal, its status is **`NOT VALIDATED`** and **all fair values, entries and distances are JSON `null`**. It does not reuse the old unofficial Yahoo scenario numbers as verified intrinsic values.
* Produces a strictly **research-only** asymmetry-sorted shortlist among those with acceptable primary economic inputs. The ratio is base-case upside divided by the larger of 5% or bear-case loss, **not an expected return, probability, or buy signal**.

## Industry methodology and evidence gates

| Sector/method | Minimum source evidence | Illustrated valuation, conditional on all checks |
|---|---|---|
| Mature profitable businesses — `NORMALIZED_EARNINGS_AND_DCF` | At least four contiguous, recent, matching SEC-filed annual cash-flow and net-income periods, reconciled annual CFO and capex from the same filing, recent multiple official share counts, correct USD quote basis | 60% five-year FCFE-style FCF DCF + 40% historical median earnings capitalisation; capped historical cash-flow growth is a **forecast assumption**, not management guidance |
| Commodity/resource and cyclical industrial — `FULL_CYCLE_NORMALIZED_EARNINGS` | At least seven comparable, contiguous fiscal years of filed income and FCF; adequate cycle coverage must still be judged by a human | Capitalised median-through-cycle earnings and FCF, with bear/base/bull yields and hypothetical dilution |
| Depository banks and insurers — `BANK_INSURER_JUSTIFIED_BOOK` | Four-year filed net-income history, recent comparative stockholder equity and multiple issuer share counts | Book/share × (normalised ROE minus long-run growth)/(cost of equity minus growth), subject to regulatory-capital caveat |
| Property/REIT or asset-holding businesses — `PROPERTY_ASSET_NAV_OR_AFFO` / `HOLDING_COMPANY_ASSET_NAV` | Asset appraisals or AFFO/asset-level valuation, liabilities, debt, contingent liabilities, and reconciliation of shares | The mathematical NAV method exists, but ordinary accounting book assets alone are **informational only, not verified market NAV**. No targets until sufficient appraised-asset evidence exists |
| Preprofit biotech, highly unusual capital structures, unverified ADRs | Clinical/project probability, reserves, dilution and cash runway, or a verifiable ADR/ordinary-share conversion as appropriate | **NOT VALIDATED** until a specialist primary-evidence model is supported |

SEC [companyfacts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) is first-party *issuer-reported* financial evidence, not independently re-audited economics. Individual numeric facts have fiscal period, filing accession, filed date and tag, and the per-company source hash is recorded. Cash flow requires same fiscal start/end **and the same accession** for CFO and capital spending. Current share count must have a second dated primary-filing comparison; a >15% basis change requires separate reconciliation. Known foreign ADR/share-ratio ambiguity blocks valuation.

### Explicit forecast defaults (editable)

Edit `settings/championship_60.json` to change any assumptions, and allow GitHub to rerun the reporting code. Defaults: four years for stable companies, seven for cyclicals, five DCF forecast years, 14% base discount, 18% bear discount, 12% bull discount, 2% terminal growth, 40% normalized earnings weighting, 15/5/0% hypothetical bear/base/bull future dilution. These percentages are **scenario assumptions**, not observed returns or published guidance. Use only as a transparent starting point; model validation is not investment suitability.

### Incremental research rather than invented global coverage

The existing discovery workflow **owns** `reports/primary_series_cache_60.json` and requests up to **12** new or stale US SEC issuer records per run. SEC request limits, blockages, differences in filing tag conventions and foreign issuers may prevent immediate full coverage. The collector never bypasses 403/429 restrictions; a rate-limit cooldown and per-company failure history persist in the JSON cache. ASX and many foreign issuers require separate, future primary-financials adapters: they receive `NOT VALIDATED` rather than guessed USD values. Verified filings for 200 businesses cannot be responsibly delivered in one request.

The scanner is the sole publisher of `reports/valuation_60_latest.json` and `reports/valuation_60_summary.json`; the weekly valuation workflow owns `reports/valuation_60_weekly.json` and its summary; discovery owns the SEC cache. This partition preserves the existing bounded six-attempt Git publishing conflict retries. All reports retain `orders_enabled:false`.

## Outputs, for ChatGPT or your own review

| GitHub file | Contents | Writer |
|---|---|---|
| `reports/primary_series_cache_60.json` | Dated SEC source records, XBRL facts, source SHA256, access health and cooldown | Discovery runs |
| `reports/valuation_60_latest.json` | Complete all-200 + discovery stock-by-stock research rows | Six daily price scanner runs |
| `reports/valuation_60_summary.json` | Counts, missing flags, top ten research shortlist (all with evidence gates) | Scanner |
| `reports/valuation_60_weekly.json` | Weekly companion report | Existing Sunday valuation workflow |
| `reports/valuation_60_weekly_summary.json` | Weekly summary | Existing Sunday valuation workflow |

Historic `reports/latest.json`, `reports/discovery_latest.json`, `reports/valuation_latest.json`, `reports/changes_latest.json`, `reports/research_queue_latest.json`, `reports/offset_comparison_latest.json`, and `reports/decision_journal.json` are unaffected.

**Important**: The old 4.0/5.1 `model_watch_entry` values and 5.4 Top Ten may still exist as *preliminary vendor-based research scenarios*. For true 6.0 evidence-gated status, consult **only** the new `reports/valuation_60_latest.json` validation and missing-evidence fields, never carry over an old number silently.

## Installation (Android GitSync)

1. Extract ZIP **contents** into your current `Documents/global-championship`, preserving `.git` and `.github` and allowing only the three explicitly included workflow YAML files to be replaced.
2. GitSync → three dots next to Sync Changes → **Upload Changes**; not `Upload + Overwrite`.
3. Push automatically starts the scanner, discovery and weekly valuation workflows. GitHub Actions run all offline tests before producing and publishing reports. The collector requires the existing private `SEC_USER_AGENT` GitHub Action secret with a real email address.
4. On the **first** run, scan and valuation may execute **before** discovery has published the new SEC cache. A full report with all targets `null` in that case is a safe initial state. Subsequent discovery and scanning runs progressively add genuine evidence; remote source errors remain visible in the cache.
5. Review **Actions** and these files: `reports/primary_series_cache_60.json`, `reports/valuation_60_latest.json`, `reports/valuation_60_weekly.json`. Never interpret a workflow's successful exit alone as proof that SEC was accessible or intrinsic targets qualified.

## Offline development check

```bash
python -m unittest discover -s tests -v
python championship_60.py --mode scan
python championship_60.py --mode weekly
python championship_60.py --mode evidence-update --offline
```

The smoke run against an evidence-free sandbox must report **200 original plus discovered rows and zero validated values**. To verify code logic without inventing company financials, tests use explicitly synthetic mock issuer data.
