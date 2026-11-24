# Championship issuer evidence recovery

This upgrade addresses the unchanged supported-valuation count by recovering actual financial inputs. The frozen original-200 baseline is 41; local verification produces 83 supported research valuations (+42), with no baseline names lost. All 200 receive an explicit assessment; 117 still lack sufficient supported inputs. A downloaded filing is not counted as a valuation.

The collector resolves obsolete SEC tags period by period, native IFRS currencies, matching annual cash-flow/capex accessions and bank balance-sheet periods. Separate filing-cover reconciliation establishes receipt ratios and listed-share terms. Dated secondary FX is labelled separately from issuer financials. Missing inputs remain null.

Four Australian banks have manually reconciled issuer PDF tables with document hashes, PDF pages and disclosed share-count precision. Older PDF publication days that were not captured remain null. Other ASX annual-report links are source inventories, not verified financial tables.

`reports/coverage_recovery_91.md` and `.json` explain every original stock's result and outstanding fields. `reports/coverage_90_latest.json` compares with the frozen 41-name baseline. `reports/latest.json` retains its existing schema and adds an explicit primary-supported count and comparison. Vendor model availability is a separate metric. Forecast scenarios remain assumptions, not verified future outcomes.

Weekly research checks whether SEC evidence refresh is due (seven days). Configure the existing `SEC_USER_AGENT` Actions secret with a real contact email for future retrievals. Without it the collector preserves the dated evidence and reports the configuration gap; it never refreshes timestamps to disguise stale inputs. Existing model staleness gates continue to apply. FX refreshes independently.

Existing schedules, legacy report keys, HPE/SKS/DUG priority thresholds and zero-order guards are preserved. No trades are enabled.

Validation: `python -m unittest discover -s tests`; `python championship_90.py --mode scan`; `python verify_90.py`; `python coverage_recovery_audit_91.py`.
