# Championship 5.1 Intelligence Layer — Additive to Existing 5.2 Discovery

This is a **read-only research upgrade**, NOT a downgrade or replacement for the live **Championship 5.2 discovery pipeline**, fixed 200-stock scanner, or 4.0 valuation job. It adds five capabilities without a broker integration or order placement. The schedules, original watchlist, scan.py, discovery_engine.py, valuation_engine.py and report_bridge.py remain unchanged.

## Files and ownership

| File | Publisher | Meaning |
|---|---|---|
| `reports/changes_latest.json` | Daily 200-stock scanner | Dated daily-bar differences, separately flagged same-bar corrections, quote-date regressions and changed research fields. First scan is a baseline, not fake market moves. |
| `reports/research_queue_latest.json` | Existing discovery 5.2 job | Underfollowed issuers with original official URL, source-host verification level, original disclosure date, quote/liquidity limitations and missing diligence. |
| `reports/valuation_top10_latest.json` | Daily scanner | Reproducible Top 10 **research priorities** drawn from *eligible* indicative models, original unmodified 200 list, dated quotes, currency checks and provisional scenarios. Never a buy list or probability of profit. |
| `reports/offset_comparison_latest.json` | Daily scanner | AUD $1,000 scenario versus hypothetical owner-occupied offset savings, tax stress, brokerage and FX assumptions; no guaranteed returns. |
| `reports/decision_journal.json` | Daily scanner | Append-only, stable-ID-deduplicated, **research-only** event history plus human-entered watch/hold/research/exclude decisions. |
| `reports/intelligence_latest.json` | Daily scanner | ChatGPT-readable index and coverage counters. |
| `reports/valuation_top10_weekly.json`, `reports/offset_comparison_weekly.json` | Weekly valuation job | Weekly standalone outputs for the refreshed fundamental model run, without racing daily-file writes. |
| `reports/fx_aud_latest.json` | Daily scanner only (if Yahoo FX refresh succeeds) | Unofficial USD→AUD conversion based on dated `AUDUSD=X` closes; missing/stale rates block foreign-stock AUD scenarios. |

**Concurrency:** Each workflow owns separate new JSON paths. Existing six-attempt safe fetch/rebase/push hotfix remains in all three. The discovery and valuation jobs never write the main decision journal. Discovery/valuation updates are picked up by the next daily scanner run, which can lag by a scan.

## Source verification, not verified returns

A genuine **SEC official filing metadata match** between a listed issuer and an 8-K filing is labelled `SEC_TICKER_AND_FILING_METADATA_MATCHED_OFFICIAL_FEED`. A curated company-disclosure URL is fetched once using a bounded 9-second call: a 200 response with an expected content type produces `OFFICIAL_PUBLISHER_URL_REACHABLE_ONLY`. Hostnames, HTTPS, redirect restrictions and recent evidence dates are enforced. Failed checks remain **pending**. **Neither classification asserts that a filing's content, financial claims, contract value or potential returns have been audited or verified**. The JSON clearly separates `primary_source_verified` (metadata/URL) from `primary_claim_verified` (always false). Do not equate source reachability with investment suitability. News-only leads remain pending.

The existing Discovery Radar 5.2 GDELT cooldown, Google News RSS, Bing News RSS and official SEC feed are all preserved.

## Top 10 methodology and limitations

A name must have a non-stale daily close (≤7 days old), a weekly valuation model snapshot (≤14 days), a fiscal statement proxy within the existing 550-day acceptance limit, confirmed quote/fundamental currency match, and a valid positive bear/base/bull order with an indicative watch entry. Scores combine capped indicative upside to base, bear-case downside protection, provisional entry margin and freshness. They rank **next research priority** only. All `verified_buy_signal=false`; `buy_readiness_pct=null`. No extrapolated positive scenario guarantees returns. The model inputs are unofficial Yahoo-derived and have not been independently verified.

## After-tax AUD versus owner-occupied mortgage offset

Edit `settings/intelligence_51.json` to change the $1,000 capital comparison, 5.8% **illustrative (not live)** mortgage rate, 13-month timeframe, brokerage and FX spread assumptions and owner tax sensitivities. The two scenarios use **assumed** marginal rates including 2% Medicare: 39% for an illustrative taxable income of A$158,000; 32% at A$110,000. Never input personal tax returns or account identifiers in a public GitHub repository.

**Critical tax caveat:** Australia's 2026 reforms change CGT for gains accruing from 1 July 2027. A 13-month comparison beginning November 2026 crosses that date, so the code uses **a conservative full-gain marginal-tax sensitivity with NO automatic CGT discount**, not a claim to compute the future statutory CGT liability. Indexation, minimum tax, partial-period gains, future law changes, tax losses, dividends, foreign withholding, taxable-income adjustments, and personal Medicare/levy consequences are not modelled. The valuation bear/base/bull price levels are **not dated 13-month forecasts**. USD examples block when fresh unofficial FX is missing; other currencies currently block instead of receiving invented exchange rates. Avoid interpreting positive `beats_offset_in_this_hypothetical_scenario` as an investment recommendation.

Primary sources: [ATO individual tax rates](https://www.ato.gov.au/tax-rates-and-codes/tax-rates-australian-residents), [ATO 2026–27 CGT reform](https://www.ato.gov.au/about-ato/new-legislation/in-detail/individuals/tax-reform-boosting-home-ownership-reforming-negative-gearing-and-capital-gains-tax), [ASIC Moneysmart offset accounts](https://moneysmart.gov.au/home-loans/mortgage-offset-accounts). Tax and lending inputs need independent current verification.

## Journal: optional manual research decisions

Edit `decisions/manual_decisions.json` (defaults to an empty `entries` array) and upload through GitSync. Example:

```json
{
  "schema_version": "5.1-human-research-notes-1",
  "entries": [
    {
      "ticker": "NVDA",
      "decision": "WATCH",
      "decision_date": "2026-11-21",
      "thesis": "Recheck official earnings release and valuation assumptions",
      "risk": "Multiple compression and volatility",
      "official_source_url": null,
      "next_review_date": "2026-12-01"
    }
  ]
}
```

Allowed journal decisions: `WATCH`, `HOLD`, `RESEARCH`, `EXCLUDE`. Invalid entries or `BUY`/`SELL` are ignored. Human decisions are stored as research notes and **cannot** execute or authorise any trade. The scanner adds dated large-price-change alerts (≥5% between **different** quote dates), major research-status changes, official-source research leads and eligible Top 10 model observations; unchanged evidence is deduplicated. Existing journal entries are preserved; do not delete or overwrite the journal manually.

## Install with GitSync / GitHub

1. Extract the ZIP, copy its **contents** into `Documents/global-championship` while preserving `.git`, `watchlist.csv`, and the existing source files.
2. Choose **three dots beside Sync Changes → Upload Changes**, *not* `Upload + Overwrite`.
3. In GitHub Actions, check the 5.2 Discovery Radar, 200-stock scan and weekly valuation workflows. The added `intelligence_layer_51.py` path triggers all three on first upload, so the existing schedules remain unchanged.
4. Reports are published in `reports/*.json` on `main`. ChatGPT can read them via the existing GitHub connection. If a job fails, inspect the individual job step; the workflow artifact remains available for 14 days.

## Developer tests and safety

`python -m unittest discover -s tests -v`

All offline unit tests test source categorisation, stale market/FX data rejection, tax-sensitivity arithmetic, same-bar corrections versus new trading sessions, Top 10 blocking rules, deduplicated research journals and no-trading controls. They do **not** prove a live data API will always respond. The repository contains no broker account credentials or endpoints, and the new layer only writes research JSON.
