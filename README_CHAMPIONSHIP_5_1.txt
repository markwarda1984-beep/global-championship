CHAMPIONSHIP 5.1 — DISCOVERY RELIABILITY PATCH
===========================================
STATUS: Prepared and tested OFFLINE; NOT installed into GitHub until GitSync upload.
NO TRADING. Do not place orders. No brokerage access.

PURPOSE
- Repair handling of the SEC.gov 403 and GDELT DOC 429 discovered in the first 5.0 run.
- Fix misleading interpretation of a GitHub Actions 'success' when upstream news/filing coverage is incomplete.
- Preserve original 200-stock scanner, price/report bridge, weekly valuation, schedules and previously published reports.

FILES IN THIS ZIP
  discovery_engine.py                     (replace existing 5.0)
  tests/test_discovery_engine.py          (replace existing 5.0 tests)
  .github/workflows/discovery.yml         (replace existing 5.0 discovery workflow)
  README_CHAMPIONSHIP_5_1.txt             (these instructions)

No watchlist.csv, discovery_seeds.csv, reports/*.json, scan.py, valuation_engine.py,
report_bridge.py, scan.yml or valuation.yml is included or changed.
Preserve the hidden .git directory in your existing repository.

INSTALL — Android GitSync
1. Extract this ZIP into Documents/global-championship. Confirm file replacement,
   retaining the directories including hidden .github/workflows/.
2. GitSync > three dots next to SYNC CHANGES > UPLOAD CHANGES.
   Do NOT use Upload + Overwrite.
3. The push of discovery_engine.py, test and workflow edits triggers the workflow
   'Championship 5.1 underfollowed discovery radar'.
4. In GitHub Actions, check the 5.1 run, full test suite and the published files:
     reports/discovery_latest.json
     reports/discovery_watchlist.json
5. Check reports/discovery_latest.json source_health and source_coverage:
     COMPLETE_FOR_CONFIGURED_SAMPLES = both SEC and the sampled GDELT theme worked.
     PARTIAL_OR_UNAVAILABLE = one or more feeds blocked/unconfigured/unavailable.
   Even 'COMPLETE' means narrow sampled sources, not all global investments.

IMPORTANT: SEC_USER_AGENT — OPTIONAL MANUAL CONFIGURATION TO ENABLE SEC REQUESTS
The SEC requires identifying your automated research client with a contact address.
5.0 used a GitHub URL in the default User-Agent and SEC returned HTTP 403.
5.1 will NOT send a misleading unidentified SEC request if your SEC_USER_AGENT
repository secret is missing or not email-shaped. Instead it explicitly reports
"configuration_required" under source_health.sec_8k.
To enable SEC attempts: GitHub repository > Settings > Secrets and variables >
Actions > New repository secret. Name SEC_USER_AGENT. Set the VALUE to a
short research-client description followed by an actual email address you control
(e.g., 'Research Monitor user-at-your-own-domain.example' — replace with an actual
working email address, including @; do not copy the placeholder).
Then run the discovery workflow again from GitHub Actions.
A valid User-Agent improves compliance but does NOT guarantee SEC access: their
security controls may still return 403 for cloud IPs. 5.1 handles this cleanly
without repeated blocked requests and cannot bypass SEC rules or GitHub permissions.

WHY GDELT WILL NOT BE HAMMERED
- Only 1 of 3 rotating news topics is queried in any scheduled run, versus 3 before.
- On 429, fail fast, record rate_limited in source_health, try again on the NEXT
  scheduled run rather than repeatedly requesting an already rate-limited source.
- Brief retries only for transient 5xx and connection/time-out errors.
- Some 429s may still happen due to shared IPs or GDELT's own traffic policy.

DISCOVERY QUALITY AND SAFETY
- A GDELT headline with an explicitly labelled exchange symbol may be added as
  PENDING_EVIDENCE if dated within 10 days, topic relevant and a valid https URL.
- Such news-only candidates NEVER become MONITOR solely from headline or market data.
  They need a primary SEC 8-K reference or a curated official issuer/exchange source.
- Existing first-party verified references are not overwritten by news-only items.
- News-only leads are unverified even if the ticker appears legitimate; always
  corroborate issuer identity, disclosure details and full financials.
- If an upstream feed fails, historical data is preserved. No successful trade
  readiness, entry level, automatic buy or sell is produced.
- Original 200 still tracks exactly 200; additional candidates live separately.
- All six daily Sydney scans and weekly 200-stock valuation remain as before.

LOCAL VALIDATION (COMPLETE)
  python -m unittest discover -s tests -v
  python discovery_engine.py --offline
Patch was tested alongside existing 200/valuation/bridge modules: 61 offline tests
passed. This does NOT confirm SEC or GDELT connectivity from GitHub Actions.

LIVE SUCCESS CRITERIA
- New 5.1 workflow completes and publishes both JSON reports.
- Source failures appear as GitHub Actions warnings and in machine-readable fields,
  rather than a deceptive "source check passed".
- Sec source_health is 'ok' only if both SEC directory AND filing sample work;
  'configuration_required', 'access_denied' or other status is an honest limit.
- New news-only tips remain PENDING_EVIDENCE until corroborated.
- Original 200 prices and provisional valuation bridge remain operational.

DIRECT CHATGPT GITHUB WRITE PERMISSION
The previously observed GitHub 403 for ChatGPT connector file-write actions is
separate from SEC.gov 403. This code patch does NOT change ChatGPT app permissions.
GitSync upload and the existing GitHub Actions contents:write publishing pathway
are the currently proven authorised deployment and reporting routes.
