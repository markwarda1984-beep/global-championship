# Championship 5.4 — Evidence Gate (additive to 5.1 intelligence and 5.2 discovery)

This patch is **research-only** and has no brokerage API, order placement, buy recommendation, or trading side effects. It preserves the existing exactly 200 ticker `watchlist.csv`, the six daily scans (02:20, 08:20, 10:20, 13:20, 16:20, 21:20 Sydney), six daily discovery runs (five minutes after scanner at :35), Sunday 03:10 Sydney valuation and the existing six-attempt, no-force-push publishing logic. It does not modify the scanning, discovery, fundamental-model or bridge engine scripts.

## Primary disclosure checks (discovery)

`intelligence_layer_51.py --mode discovery` still builds the original queue, then `evidence_upgrade_54.enrich_queue` downloads official-source issuer PDF/HTML documents **with tight size/page/time bounds, HTTPS trusted-host checks and redirects disabled**. It extracts document text (via `pypdf` or a standard HTML parser), verifies that an issuer name is in the actual text, compares the claimed publication date against date strings in the actual document, and checks configured claim words within a *single 1,000-character passage*. Matches include the source URL, PDF page (where applicable), excerpt and content SHA-256. If issuer, document date or claim cannot be supported, `primary_claim_verified=false` with explicit flags.

**Meaning:** A `primary_claim_verified=true` result means only **“the issuer reports this specified statement in an identifiable, dated document”**. It does **not** establish that the company’s reported claim is true, audited, forward-looking, material, or profitable. No statement can be marked supported from an URL path, slug, feed title, 200 HTTP status alone or a news article. `settings/discovery_claims_54.json` defines statements to inspect and is not itself evidence. An issuer without an explicit claim rule can have its document/issuer checked, but its claim stays unverified.

The initial rules are deliberately narrow: DUG revenue / 49%; Penguin / Marvell collaboration; Bitdeer third-quarter results; EOS issuer identity only until a specific factual claim is entered. Expect **zero or few** matches if documents are inaccessible, text cannot be extracted, the declared date differs, or the actual statement is not found. Never fabricate a match.

## SEC economic verification (valuation)

The weekly valuation workflow calls `evidence_upgrade_54.py --mode financials` on up to **ten preselected preliminary valuation research candidates**, subject to configured `SEC_USER_AGENT` (already supplied as a repository Actions secret). It fetches the SEC ticker/CIK association and that issuer's official `companyfacts` XBRL JSON. The program checks:

- official filer CIK and ticker association;
- actual common shares outstanding (not weighted-average diluted EPS shares);
- reported operating cash flow and capex of the *same period and filing accession*;
- agreement between primary and unofficial shares (within 10%);
- period-identical primary free cash flow versus model's unofficial cash flow (within 25%);
- USD financial-currency consistency.

If any check fails, the issuer is **not evidence-qualified**. Financial institutions, cyclicals with mismatched annual-vs-quarterly data, ASX companies, ADRs with currency/split mismatches, inaccessible SEC API responses and all unexamined issuers stay unqualified until suitable specialist evidence is supplied. Companyfacts itself is **issuer-filed**, not an independent audit and not a full fully diluted capitalization review. The first pass reviews only ten preliminary candidates, not all 200. Any repeated rate limits are not circumvented.

`reports/primary_financials_latest.json` records SEC status and per-filer data. Daily scans use available financials if dated no more than 31 days earlier; otherwise they fail closed. This does not claim to fully verify 200 companies.

## Dilution-adjusted asymmetry (no trade rank)

`reports/asymmetry_latest.json` and `reports/asymmetry_weekly.json` contain:

- **Evidence-qualified top 10**: *only* model rows with official primary share and matched primary-period free cash flow, reconciled against their corresponding model. A missing-data result can legitimately be **empty**.
- **Unverified research queue**: model scenarios examined with explicit missing-evidence flags. These are **not** investment rankings or actionable targets.
- Illustrative future share issuance stresses: **bear +15%, base +5%, bull +0%**. These are user-configurable in `settings/dilution_stress_54.json` and are **not observed future dilution**. Values are per-share scenarios, scaled for documented vs unofficial current outstanding shares *only when source-verified*, then divided by `(1 + hypothetical new issuance)`. No proceeds value is assumed.
- A base-upside / worst-bear-loss **scenario ratio**, never a probability, predicted return, or buy-readiness score.

The existing `reports/valuation_top10_latest.json` remains available as a plainly-labelled **unverified model-research ranking**. It additionally carries new evidence/dilution flags. The evidence-qualified ranking is separate so an unverified valuation cannot silently become a “buy”.

## Offset, AUD, fees, FX and tax

Configure `settings/intelligence_51.json`:

- `illustrative_5_8`: **5.80%**, an editable working illustration, **not verified as a live home-loan rate**.
- `unconfirmed_6_01`: **6.01%**, an **unconfirmed alternative**, not the asserted current St George rate.
- `comparison_principal_aud` (default A$1,000), `comparison_months` (13), buy/sell brokerage and each-way FX spread, with existing AUD/USD quote freshness rules.
- two editable Australian marginal/Medicare stress scenarios (illustrative taxable incomes A$158k and A$110k). Outputs apply full marginal tax to positive hypothetical realised gains *without applying a CGT discount*, as a **conservative scenario only**. Actual CGT may differ materially, especially for assets held across the legislated 1 July 2027 reform; obtain current ATO/accountant guidance.

Both rate benchmarks are reported alongside each bear/base/bull after-tax hypothetical. Mortgage interest avoided through an eligible offset is not investment income. **Assumes interest on an owner-occupied NON-deductible mortgage**, an eligible offset balance and loan balance above offset; saving uses simple non-compounded interest. Stock values are not 13-month forecasts; dividends, CGT cost-base indexation, levies, loss carry-forwards and FX currency change are not modelled as actual tax results.

## Report files / permissions

New: `reports/primary_financials_latest.json`, `reports/asymmetry_latest.json`, `reports/asymmetry_weekly.json`.
Enhanced: `reports/research_queue_latest.json`, `reports/valuation_top10_latest.json`, `reports/valuation_top10_weekly.json`, `reports/offset_comparison_latest.json`, `reports/offset_comparison_weekly.json`, `reports/intelligence_latest.json`.

The scan, discovery and valuation jobs still publish with their **existing six-attempt fetch/rebase/push retries**, and GitHub Actions uploads artifacts. Research is read-only; all new outputs have `orders_enabled: false`. `pypdf` is installed via `requirements.txt`.

### Verification

After merging or GitSync-uploading the patch, check each of the three *new* workflow runs in GitHub Actions and inspect the above JSONs. In particular, check that the discovery claim count is **supported by actual text excerpts** and that a missing SEC filing produces a missing-evidence flag rather than a ranked recommendation. A green workflow by itself does not mean source claims were verified. The original `watchlist.csv` and the source engines are not included in this update.

Run offline unit tests: `python -m unittest discover -s tests -v`.
Run an offline (non-live) report smoke test: `python evidence_upgrade_54.py --mode financials --offline`, `python intelligence_layer_51.py --mode discovery --offline`, `python intelligence_layer_51.py --mode scan --offline`, `python intelligence_layer_51.py --mode valuation --offline` on a disposable copy of the repo.
