# Background evidence research

This is an executable scheduled GitHub Actions worker, separate from the existing price scan. It selects up to 20 due unresolved companies per run and saves a checkpoint after every company. Never-attempted cases are processed before repeats; HPE, SKS and DUG receive priority within that fair queue. Existing price/valuation schedules and entry thresholds are unchanged.

The worker runs at **00:45, 04:45, 08:45, 12:45, 16:45 and 20:45 Australia/Sydney** and can also be run manually. An initial pass through roughly 111 unresolved original companies plus priority names should fit into six full batches, approximately one day if source availability and run time permit. This is a source-research pass, not a promise that every company will receive a supported valuation.

Each SEC case retrieves issuer facts, submission metadata and up to two latest annual/quarterly filings. Existing reviewed parsers can recover cash-flow rows, comparable issued shares and receipt terms. The worker keeps source URLs, document hashes, filing dates and short review excerpts. Unreviewed custom tags are saved as candidates and never fed into valuations. ASX cases get refreshed filing inventories; issuer PDF tables and new specialist models remain explicitly in the human review queue until a reviewed adapter is implemented. No broker or trading actions exist.

A persistent queue records attempts, unresolved flags, backoff dates and provider cooldowns. HTTP 403/429 stops that SEC provider for 24 hours; the worker does not hammer it. Successful unchanged source data can be refreshed only by a genuine new retrieval. Financial dates are preserved. A configured SEC_USER_AGENT secret is used if present; otherwise requests identify this public research repository, without disclosing a personal email.

Research writes only dedicated `reports/background_*93*` files. Existing financial inputs and workflows are preserved. The 6.0/9.0 readers merge only intact issuer-evidence records with a valid hash and an observation time at least as recent as their existing record. No supported count is inferred from a download. The 9.0 engine must actually produce a supported scenario before a case is counted as resolved.

After successful research, GitHub's `workflow_run` event starts the existing scan and weekly valuation workflows, which publish and verify the usual compatible reports. Failed research does not trigger those downstream jobs. The worker's own commit uses `[skip ci]` to prevent push-trigger loops. The scheduled research worker is serialized and uses bounded non-force push/rebase retries.

Progress is published in:

- `reports/background_research_latest_93.md`: readable progress and outstanding cases.
- `reports/background_research_latest_93.json`: actual last batch, sources, coverage and workflow run URL.
- `reports/background_research_state_93.json`: persistent attempts and next eligible times.
- `reports/background_review_queue_93.json`: all currently unresolved cases and missing fields.
- `reports/background_source_notes_93.json`: source excerpts and unapproved extraction candidates.
- `reports/background_evidence_93.json`: evidence eligible for existing valuation checks.
- `reports/background_research_history_93.json`: the last 100 runs.

These reports describe completed research batches; the Actions page indicates whether a run is currently active. Raw documents are fetched only within bounded requests, not committed in bulk. The source notes and progress are also saved as per-run artifacts for 14 days.

Verification: `python -m unittest discover -s tests`; `python background_research_93.py --batch-size 2 --max-minutes 2`. Automated tests cover fair rotation, backoff, provider cooldowns, rejected redirects, untrusted/tampered/future evidence, atomic checkpoints, and the unchanged existing model suite. New models and unverified financial inputs still require review. No completion date or full 200-stock supported valuation coverage is guaranteed.
