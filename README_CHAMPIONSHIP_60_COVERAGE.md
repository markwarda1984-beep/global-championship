# Championship 6.0 — Primary-Source Coverage and Forward-Research Completion Layer

Research-only, no brokerage connection or orders. The fixed 200-stock universe, 5.2 discovery, three pre-existing schedules, publishing retries, AUD tax/offset analysis, journal, and *retired legacy provisional entries* remain unchanged.

## What is genuinely implemented

1. **Prioritised official SEC financial series:** `championship_60.py --mode evidence-update` now collects NVIDIA first, then a configurable research-priority list, then new discovery issuers and the rest of the 200. The original alphabetical ordering had delayed NVIDIA. Uses the existing `SEC_USER_AGENT` secret, one bounded batch per discovery run, persistent provider cooldowns, and per-issuer dates/accessions/hash. Priority **is not a recommendation**. Companies without reconciled filing history still show `NOT VALIDATED`; no fair value, bear/base/bull, margin-of-safety entry or readiness score is created.
2. **Issuer-reported guidance:** `forward_research_60.py --mode update` checks the BODY of NVIDIA's official 17 Nov 2026 SEC Form 8-K earnings-release exhibit, requiring the issuer, date, FY2027 Q4 period and revenue forecast to appear together. When it actually fetches and verifies the text, it can report management's expected quarter revenue of US$130.0bn ±3%. A blocked/changed source returns an explicit failure, **not** a presumed value. This is MANAGEMENT REVENUE GUIDANCE, not forward EPS consensus, independent audit or a validated intrinsic forecast.
3. **Bounded analyst estimate research:** One 8-ticker batch per discovery run of Yahoo Finance analyst EPS estimates (via the already installed `yfinance` dependency), each with collection date, estimates, optional analyst count, source link and **UNOFFICIAL SECONDARY** label. Missing data is blank; source errors get per-ticker cooldowns, and HTTP 429 gets global cooldown. EPS currency/share class and fiscal end are not assumed. The revision series returns `NOT VALIDATED` unless two actual dated observations for the **same explicitly identified fiscal period** exist.
4. **Complete 204-row coverage ledger:** `forward_research_60.py --mode coverage` publishes `reports/coverage_60.json` for every fixed stock plus discovery candidate, listing filing/forward/guidance source status, missing-evidence flags, price date and the *research-only* priority queue. It does not use unverified upside to make a purchase recommendation.
5. **Non-interference:** Both current and weekly `reports/valuation_60_*.json` acquire additional `external_forward_earnings`, `earnings_revisions` and `issuer_forward_guidance` fields. The 6.0 valuation engine's verification gates, intrinsic values, margin of safety, and rank remain **unchanged by secondary analyst estimates or management guidance**. New data alone can never approve a trade.

## Scope and important limitations

- The first official filing batch is **not complete coverage of all 200 financial statements**. The queue gradually covers SEC-indexed US issuers, observing fair-use limits (SEC recommends no more than 10 requests/s). Original code already retains SEC financial histories, normalizes earnings for cyclicals, and gates assets/ADR/share basis; this patch accelerates and exposes coverage, it does not bypass those gates.
- The **ASX-listed and foreign non-SEC names still need issuer-specific official annual-report extraction and share/FX reconciliation**, while REITs, some banks, holding companies and biotech/project companies require specialist models. They stay `NOT VALIDATED` and receive no target without suitable evidence.
- There is **no free comprehensive primary-source analyst-consensus database**. The secondary Yahoo estimate snapshots are not primary verified and *never supply a validated intrinsic-value input*. Broker/issuer estimate claims cannot be independently confirmed or guaranteed by these sources.
- The SEC 8-K guidance source is intentionally *NVIDIA-specific* and tied to a dated source. Further issuers need purpose-built extraction rules and original documents. Issuer statements remain unverified as to truth.
- Existing modeled bear/base/bull outputs represent transparent forecasts and assumptions, **not objectively certified intrinsic values**. Do not interpret a percentage margin of safety as a probability of profit.
- The 5.8% mortgage offset remains **illustrative**, 6.01% remains **unconfirmed**. Australian taxes, fees, FX and journal calculations are unchanged.

## Live files after GitHub Actions publish

- `reports/primary_series_cache_60.json` — issuer XBRL facts, provenance, coverage/priority queue.
- `reports/forward_estimates_60.json` — secondary, dated EPS estimates and explicitly qualified revisions.
- `reports/issuer_guidance_60.json` — optional official NVIDIA Q4 FY27 management guidance, after live document fetch.
- `reports/coverage_60.json` — one evidence-status row per company.
- `reports/valuation_60_latest.json` and `reports/valuation_60_weekly.json` — 6.0 valuations, plus separate forward-evidence attributes.
- `reports/latest.json`, `reports/offset_comparison_latest.json`, `reports/decision_journal.json` — existing reports, unchanged schema and no-trading guards.

## Tests and installation

Local: `python -m unittest discover -s tests -v` (202 passing as of build). Optional no-network replay: `python forward_research_60.py --mode update --offline && python championship_60.py --mode scan && python forward_research_60.py --mode coverage && python championship_60.py --mode weekly`. Nothing sends orders. To publish the code on GitHub, extract the patch ZIP at repository root, preserving `.git`, then **GitSync → three dots beside Sync Changes → Upload Changes**, not Upload + Overwrite. GitHub push triggers existing jobs (scanner, discovery, weekly), and subsequent scheduled runs extend source coverage incrementally.

## Further verification in the 206-test release

The 6.0 `coverage_60.json` now exposes TWO deliberately distinct *research-only* lists:

- `evidence_qualified_below_base_research`: underlying price below a modelled base value, with verifiable source URL + source hash. This does not mean the stock meets the margin of safety.
- `evidence_qualified_at_selected_margin_of_safety`: a stricter subset trading at or below its momentum-selected 10%, 15%, or 20% entry. These levels are estimates tied to documented primary inputs, not assurances of a return, buy instructions, or a substitute for human diligence.

Both are empty when evidence is absent. The published `reports/coverage_60.json` contains 204 research records when the four discovery leads remain active, retaining 200 fixed-list records. Every `NOT VALIDATED` row has a **null** qualifying entry. The scanner's workflow now checks count, provenance, no-orders and list consistency before publishing. All legacy provisional price entries remain retired in the live 6.0 report builder. The 206 passing offline tests include four new regression tests for source-hash gating, no false undervaluation, and separation of base-value and margin-of-safety conditions.

### Current public NVIDIA statement, not a stock target

SEC Form 8-K filed 17 November 2026 includes exhibit `q3fy27pr.htm` (accession 0001045810-26-000088). NVIDIA reported US$115.8bn third-quarter FY27 revenue and issued US$130bn ±3% next-quarter revenue *management guidance*. These statements can be read/checked by the issuer-guidance adaptor at runtime. They do not supply a verified five-year earnings consensus, cash-flow discount rate, intrinsic value or entry target. An inaccessible source stays unverified. No number is preloaded into a buy target.

### Verify after GitSync upload

1. Verify three GitHub Actions runs complete successfully from the new commit (scanner, discovery, weekly valuation).
2. Verify `reports/primary_series_cache_60.json` includes NVDA or a transparent SEC-source error. The collector must never manufacture evidence.
3. Check `reports/forward_estimates_60.json`, `reports/issuer_guidance_60.json`, and `reports/coverage_60.json` are valid JSON with `orders_enabled:false`.
4. Confirm there are 200 original stocks, with any discoveries listed separately; verify `NVDA`'s legacy `provisional_entry` remains null in `reports/latest.json`.
5. Check that unverified companies have null `verified_intrinsic_value`, `bear`, `base`, `bull`, and 10%, 15%, 20% entries, and are absent from both evidence-qualified research lists.
6. Forward analyst EPS estimates may be missing or unofficial. Do **not** label them as primary-verified. ASX and many specialist sectors require additional issuer adapters and may remain NOT VALIDATED.
