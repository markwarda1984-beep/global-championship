# Championship 9.2 Dynamic Earnings Intelligence

The 9.2 report keeps historical, management-guidance-backed forward, and provisional research views separate. Historical model policies are retained for comparison. Forward issuer guidance is not clipped by historical growth caps. Fixed earnings multiples and tax persistence are explicit assumptions, not issuer facts or guaranteed intrinsic values.

## Verified improvement

Frozen baseline: **89 supported historical valuations / 200**, source commit `6bb8da7`.
The reviewed additions are **MQG.AX, PME.AX and RMD.AX**: **92/200**, with no prior name lost. SKS and DUG remain priority discovery names outside the original 200. An updated forward view of HPE does not count as a new historical valuation.

All 111 originally outstanding cases have recovery records in `reports/dynamic_source_recovery_92.json`. A downloaded report or detected table is explicitly NOT a supported model. Unreconciled inputs, unprofitable histories, short commodity histories, financial capital structures and pipeline/NAV cases remain visible with their actual blockers. **The 111 financial models are not all recovered.** Missing financial numbers remain null.

The original Greenvale entry is an identity exception: the issuer source identifies GRV, while the existing watchlist key is GG8.AX. No GRV statements are applied to a GG8 price. The 200 keys are preserved pending explicit identity correction.

## Financial validation cases

| Case | Evidence and treatment |
|---|---|
| HPE | SEC FY26 Q4 release; GAAP diluted FY27 EPS 3.68–3.98, separately retained adjusted EPS 5.05–5.35 and after-tax exclusions 1.37. Policy multiples 10/14/18 imply USD 36.80 / 53.62 / 71.64. Direct diluted EPS is not divided by basic issued shares. Acquisition, preferred conversion and cash-flow definition effects remain explicit. |
| SKS | Audited FY26 owner earnings and cash flows; 23 October primary issuer reaffirmation of AUD 500m revenue and AUD 60m PBT. Forward EPS is a MODEL conversion using actual effective tax and owner allocation plus explicit issuance stress, never management-guided EPS. |
| DUG | FY26 USD financial statements and 19 November AGM four-month trading update. Group profit differs from owner earnings; EPS cents are normalized to USD. Owner cash after PPE, intangibles, lease principal and financing interest is negative USD 5.749m. Revenue/EBITDA growth does not manufacture a forward EPS valuation. |
| Macquarie | Consolidated ordinary-holder profit/equity, not parent-company-only columns or NCI. Issued shares are reconciled to treasury shares; neither share capital dollars nor weighted-average EPS shares are substituted for outstanding common shares. |
| ResMed ASX | Primary 10-K confirms ten CDIs represent one NYSE common share. Financial USD, quote AUD and 0.1 ordinary share per CDI are reconciled separately. |
| Pro Medicus | Four matched annual income/cash-flow periods. PPE, capitalized development and lease principal are deducted in the conservative owner-cash calculation. The large fair-value gain is flagged separately from recurring operating earnings. |

## Rankings

- `provisional_research_rankings`: primary-referenced sensitivities and guidance views with missing-input and risk flags. Unguided EPS sensitivities assume zero growth explicitly; they do not increase supported coverage.
- `validated_forward_rankings`: guidance-backed models passing current quote, cash/debt, dilution and other financial gates.
- `validated_pre_recovery_rankings`: those passing the financial gates, with at least 25% modeled base upside and evidence of early timing. Prefer 25–50% upside, but do not exclude higher upside solely because it exceeds 50%.
- Timing uses a new five-day low or distance from the low measured against actual daily volatility. No universal 3% recovery cut-off. Recovering companies remain visible in research rankings; missing timing history stays unknown.

An empty validated ranking is a valid result. The engine does not manufacture candidates to fill a Top 10.

## Background integration and compatibility

The existing 9.3 worker extracts quarterly and annual observations from the same retrieved SEC JSON. It also follows explicit public earnings-exhibit links from earnings 8-K filings. Reviewed HPE guidance rules can refresh the forward engine; unknown text stays a review candidate. A bounded oldest-first quarterly refresh also covers supported companies. The registered issuer-document collector rotates through cases with source hashes, timestamps, provider cooldowns and a review queue. Changed documents never inherit prior approval.

Successful background runs continue to trigger the existing scan and weekly workflows. Both now build and independently verify the dynamic report. Existing workflow names, six Sydney daily scan times, background schedules, 6.0 bridge schema and historical report paths are retained. The bridge gains additive 9.2 links and fields. Emergency alert automations are unchanged.

Preferences: **Webull stocks, Kraken crypto, AUD 1,000 trial budget**. Instrument availability/account funding are not assumed. Existing HPE `< USD 40`, SKS `<= AUD 5`, DUG `<= AUD 1.50` entry-review thresholds are retained. Thresholds are not automatic orders or valuation approval. No broker API, credentials, order routing or trades are introduced.

If a quote refresh fails, the last successful snapshot retains its ORIGINAL quote timestamp and explicit fallback label. Staleness gates still apply; a cached quote is never relabelled live.

## Reproduce and verify

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python championship_90.py --mode scan
python collect_documents_dynamic_92.py --max-documents 0
python dynamic_earnings_92.py --mode scan
python verify_financial_outputs_92.py --mode scan
```

Use `--mode weekly` for the weekly report. Quarterly fact history is in a gzip JSON file to keep repeated issuer observations small in git. Source inventory, financial-model coverage and provisional ranking counts are deliberately reported separately.
