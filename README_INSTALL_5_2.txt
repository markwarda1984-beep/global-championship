CHAMPIONSHIP 5.2 - RELIABLE DISCOVERY NEWS FEEDS
Repository: markwarda1984-beep/global-championship
Status: patch prepared and fully tested offline; NOT YET INSTALLED IN GITHUB.

WHY THIS CHANGE
GDELT DOC API repeatedly responds HTTP 429 from GitHub-hosted shared IPs.
There is no way to guarantee GDELT itself will accept those requests.
5.2 therefore makes the whole discovery pipeline resilient:
 - On GDELT 429/403 it waits 12, 24, 48, up to 72 hours across scheduled runs.
 - Remembers cooldown state in reports/discovery_watchlist.json (published by GitHub Actions).
 - Tries independent Google News RSS; if unavailable or empty, tries Bing News RSS.
 - Keeps SEC 8-K filing verification working with your existing SEC_USER_AGENT secret.
 - News mentions are unverified research leads only. They CANNOT become 'MONITOR'
   merely because a news headline mentioned the ticker or quote/liquidity looked good.
 - Reports exactly which provider worked, failed or was skipped, without claiming
   exhaustive global-market coverage.
 - Does NOT change the original 200, the buy-price models, the trade safeguard
   or brokerage accounts. NO orders, trades, account credentials or broker access.

FILES IN THIS PATCH
 discovery_engine.py                    replaces existing 5.1 file
 .github/workflows/discovery.yml       replaces existing 5.1 file
 tests/test_discovery_engine.py        updates version/reliability regression tests
 tests/test_discovery_sources_52.py    NEW 5.2 fallback tests
 README_INSTALL_5_2.txt                installation notes (optional to keep)

INSTALL VIA ANDROID GITSYNC
1. Extract this ZIP into Documents/global-championship (REPLACE corresponding files).
2. Keep .git, existing watchlist.csv, valuation/scanner workflow files,
   reports/ and all other files untouched. Ensure that hidden .github was extracted.
3. In GitSync, three dots beside Sync Changes -> Upload Changes.
   Do NOT use Upload + Overwrite.
4. In GitHub Actions, run 'Championship 5.2 underfollowed discovery radar'
   or let its push trigger run automatically.
5. Confirm GitHub Actions run succeeds, then open
   reports/discovery_latest.json and inspect schema_version 5.2-discovery-radar-1.
   Also inspect source_health.sec_8k, source_health.gdelt,
   source_health.google_news, source_health.bing_news,
   and source_coverage (COMPLETE_FOR_CONFIGURED_SAMPLES,
   CORE_SOURCES_AVAILABLE_WITH_FALLBACK, or PARTIAL_OR_UNAVAILABLE).
6. Confirm reports/discovery_watchlist.json contains source_state and that
   original_200_unchanged=true and orders_enabled=false.

TESTED
 - On a copied repository: python -m unittest discover -s tests -v
 - 76 tests passed on November 21, 2026, including GDELT 429,
   Google RSS 429, Bing fallback, cooldown persistence, and no-trade gates.
 - Offline tests cannot guarantee public news endpoints allow access from
   a GitHub-hosted runner. Verify the live report after installation.

SEC SECRET
The existing SEC_USER_AGENT remains in GitHub Actions secrets. Do NOT put it
or your personal email address in ZIP files or watchlist/config JSON.

SOURCE ATTRIBUTION
Google News RSS and Bing News RSS are publicly accessible RSS services whose
formats can change without notice. They are secondary leads, not verified
company disclosures and not real-time market data.
