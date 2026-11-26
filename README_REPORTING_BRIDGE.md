# Compact reporting connection

Start at `reports/bridge/manifest.json`. Keep `reports/latest.json` and all detailed reports unchanged. The compact bridge is additive; existing clients continue to work.

Resolve main to a commit SHA, then request the manifest and every indexed file at that SHA with GitHub's standard Contents API. Decode `content` from base64. The manifest records each file's byte count and SHA-256 so clients can detect incomplete or mixed snapshots. Every JSON file must be strictly below 100,000 UTF-8 bytes. Stable index names point to numbered chunks; never assume one chunk or reuse an old manifest with a new main revision.

The dashboard contains exactly 200 original stocks; discovery companies are separate. Coverage distinguishes historical models from management-guidance-backed forward scenarios, including unresolved blockers. Weekly summary and indexed weekly valuation rows retain their own source timestamp. Priority quote rows preserve existing entry operators and thresholds. Session quotes carry observation timestamps, source URLs, freshness labels and missing flags; they are dated samples, not live executable quotes.

`closest_top30.json` and `closest_top10.json` use absolute percentage distance from the existing validated 6.0 research entry, with ticker tie breaks. They do not turn 9.2 scenarios into new entry limits. Validated forward and pre-recovery ranking indices preserve the upstream ranking order separately. Unsupported entries remain null. Ranking eligibility does not authorize a purchase.

April 2026 comparisons explicitly report `MISSING_VERIFIED_COMPARABLE_BASELINE`. No verified April valuation snapshot is present in the current inputs; historical filing dates and April market prices are not substitutes for an April valuation. No comparison is fabricated.

Both scan and weekly workflows build the bridge after financial validation, publish all chunks, and verify every published file through the standard GitHub Contents API. Their shared concurrency group prevents conflicting bridge snapshots without changing either schedule. Local checks: `python reporting_bridge.py --mode scan`, `python reporting_bridge.py --mode weekly`, `python reporting_bridge.py --verify`. Remote check: `python verify_reporting_bridge_api.py --ref COMMIT_SHA` (optional `GH_TOKEN`). Webull, Kraken, the AUD 1,000 research trial, alert automations, recovery workflows and all trading guards retain their existing settings.
