# Reviewed share and cash-flow recovery

This repair adds historical models for CME, COP, LEU, MA, NKE and REGN. The fixed universe remains 200. Local verified coverage is 98/200 versus the immediately preceding 92/200 and original 89/200. Existing supported tickers are frozen in `settings/recovery_baseline_94.json`; a downloaded statement or provisional EPS sensitivity never counts as a supported model.

Five issuer-specific share policies reconcile dated cover counts only after primary security descriptions establish equal economic rights. Regeneron's common/Class A and CME's five common classes require different member maps. All classes must be present, positive, dated consistently and free from conflicts. Unexpected classes, changed rights documents, issuer mismatches and ambiguous note tables are rejected. Source URLs, document hashes, accession numbers, component counts and rights excerpts remain inspectable in `reports/reviewed_share_counts_94.json`. These are outstanding counts, not weighted-average EPS denominators.

ConocoPhillips' 2025 annual cash-flow statement supplies 2023–25 capital expenditures and investments. The 2025 reconciliation is USD19.796bn operating cash flow less USD12.553bn capital expenditures and investments = USD7.243bn conservative cash flow. This broad spending deduction includes investments and is not represented as fully reconciled distributable owner cash flow. Acquisition spending remains separately identified by the dynamic engine. No absent PPE amount is filled with zero.

The bounded 9.3 worker applies the same reviewed parsers and retains these issuers in its refresh rotation after recovery. The worker's existing provider cooldowns and time/request bounds remain active. Changed security descriptions require review; unknown issuers do not inherit an economic-rights policy.

`python recovery_94.py --mode scan` and `--mode weekly` independently inspect the existing published valuation outputs, check that the previous 92 are preserved, verify the new denominators and COP source figures, and publish distinct scan/weekly comparison files. They do not regenerate valuation outputs. Both workflows run these checks before publication.

102 historical models remain unsupported after this repair; 31 still lack normalized current primary statement series. Other blockers include specialist asset/pipeline inputs, foreign listed-share basis, incomplete cycle histories and loss-making companies requiring an appropriate model. This release does not claim those cases are repaired or that any new buy opportunity has been validated. Their financial inputs remain missing explicitly.

Historical and forward scenarios stay separate. HPE, SKS and DUG thresholds, Webull/Kraken preferences, the AUD1,000 trial budget, six daily reviews and emergency alerts remain intact. No trades or orders are generated.
