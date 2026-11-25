# Native financial statement recovery (9.6)

This continues the merged 9.5 implementation. It does not rebuild the application.

Local verified historical coverage is 106/200 versus the resumed 98/200 checkpoint and the original 89/200 baseline. The preceding published 103 are retained. The three additional models are TSMC, PDD and ICICI Bank. Forward coverage remains four original watchlist companies; historical recoveries are not counted as forward forecasts. The remaining 94 historical models still need financial evidence or specialist modelling.

* TSMC: native TWD inline annual statements; parent-owner income; cash outflows include PPE, intangibles, lease principal and financing interest. Convenience USD translations are excluded. Five ordinary shares per ADS.
* PDD: native CNY parent-owner income and the combined equipment/software/intangibles cash acquisition line. Four ordinary shares per ADS.
* ICICI: issuer-filed U.S. GAAP reconciliations in INR millions, rather than mixed Indian GAAP statement values in INR thousands. Five owner-income years and four owner-equity years support the existing bank model. Two ordinary shares per ADS. Exact dated ordinary shares and independently dated INR/USD conversion are required.

`reviewed_native_96.py` is integrated into the existing SEC background collector. `reviewed_bank_96.py` follows ICICI's actual annual filings through SEC submissions, bypassing its unavailable company-facts endpoint without inventing API observations. Missing fields or changed table layout fail closed. Source hashes, table rows or exact cover excerpts identify observations. The worker publishes its dedicated bank evidence file; the scan and weekly workflows publish separate output files.

Dynamic cash flow now checks the required lease, intangible and financing-interest components for the TSMC cash definition. Missing quarterly costs stay unknown. Guidance selection uses the latest valid publication across reviewed seeds and worker evidence. The output verifier permits guidance to expire and checks revised guidance against its current source, rather than enforcing an obsolete EPS indefinitely.

`verify_outputs_96.py` inspects actual generated/published values, including native cash deductions, receipt denominators, FX direction/dates and bank owner income/equity. It does not treat workflow success as proof of accuracy. `verify_outputs_95.py` and the prior 9.2/9.4 checks remain in place.

HPE < USD40, SKS <= AUD5 and DUG <= AUD1.50 remain unchanged. Six daily reviews, emergency alerts, discovery, Webull, Kraken and the AUD1,000 research trial remain intact. No orders are enabled or generated.
