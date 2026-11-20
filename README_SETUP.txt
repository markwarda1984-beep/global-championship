CHAMPIONSHIP 5.0 — UNDERFOLLOWED DISCOVERY WATCHLIST
=================================================
STATUS: Prepared, offline-tested; NOT installed on GitHub until you upload these files.
NO orders, no brokerage APIs, no automated purchases/sales.

GOAL
- Preserve the fixed original watchlist.csv and BOTH existing scan and valuation workflows.
- Add a separate growing research register for new stocks that pass objective public-evidence,
  price, liquidity, share-size and freshness checks. A company admitted to MONITOR is NOT
  'buy ready', and a candidate may remain PENDING_EVIDENCE until data is adequate.
- Archive monitored names after 3 consecutive objective data/liquidity failures; never
  silently delete history or claim that the investment thesis is disproved by this alone.

QUICK INSTALL — your GitSync / Android workflow
1. Extract the ZIP into Documents/global-championship, preserving folder structure.
   It contains discovery_engine.py, discovery_seeds.csv, tests/test_discovery_engine.py,
   and the hidden .github/workflows/discovery.yml. Do NOT delete your .git folder.
2. Preserve watchlist.csv, scan.py, valuation_engine.py, opportunity_engine.py,
   report_bridge.py, and existing scan.yml and valuation.yml UNCHANGED.
3. In GitSync, select the three dots next to 'SYNC CHANGES' > 'UPLOAD CHANGES'.
   Do NOT use 'Upload + Overwrite'.
4. The push of these files should start GitHub Actions workflow
   'Championship 5.0 underfollowed discovery radar'. You may also start it manually
   from Actions > the workflow > Run workflow.
5. Confirm run conclusion success and that these two JSON files appear on main:
     reports/discovery_latest.json
     reports/discovery_watchlist.json
6. Add the optional SEC_USER_AGENT Actions secret for improved SEC reliability:
   GitHub repository > Settings > Secrets and variables > Actions > New repository secret.
   Name: SEC_USER_AGENT; value: 'Global Championship Research <valid-contact-email>'.
   Use only an email address that you control. Without it the source may be blocked.
7. Once online, check source_health fields in reports/discovery_latest.json.
   'unavailable' means the feed was NOT checked; do not interpret as no new opportunities.

HOW IT WORKS
- Runs 6x per Sydney day at 02:35, 08:35, 10:35, 13:35, 16:35, 21:35.
  Existing 200-stock scans remain at :20 and weekly valuation on Sunday.
- Curated bootstrap names: DUG.AX, EOS.AX, PENG, BTDR, each with a dated public
  company/stock-exchange disclosure link. Sources are references, NOT automatically
  verified underlying fundamentals. A seed must pass freshness and market-data checks.
- New US leads: sample the latest SEC 8-K filings, map filing CIK to an SEC-listed
  US ticker, match the full issuer name to a topic-specific third-party news lead,
  then check historical price, liquidity and market cap. News alone NEVER admits a stock.
- No fabricated sources, buying percentages, expected returns or entry limits.
- Price data from unofficial Yahoo Finance via yfinance can be delayed or missing.
  Only 'MONITOR' status means automatic RESEARCH tracking, not a BUY decision.
- A record remains in the discovery register; it is never automatically inserted into
  the fixed 200 original stocks, which retain their existing equal-coverage scanner.
- Reports are published automatically by GitHub Actions with [skip ci] commits.

LIMITATIONS / NEXT ENHANCEMENTS
- US SEC feed only exposes a finite latest set of filings and may miss events. SEC can
  refuse automated requests without an accurate, identifiable user agent.
- GDELT article matching is intentionally conservative; it may miss obscure firms.
- To limit source-rate load, up to 35 candidates are price-checked per run, prioritising
  new leads and rotating existing names; the report shows this coverage limitation.
- No general ASX exchange-wide scanning or non-US/crypto token auto-enumeration yet;
  ASX lead discovery currently requires curated primary-source seed entries. These are
  honest coverage limitations; we will extend data providers and specialist models.
- A new primary filing is not necessarily good news, and a decline in liquidity does
  not prove the investment thesis has failed.
- An unattended GitHub workflow does not perform source-document fundamental analysis.
  It creates research leads for the scheduled ChatGPT reviews to investigate.
- This project has no connected broker and may not place trades.

SAFETY / VALIDATION
  python -m unittest discover -s tests -v
  python discovery_engine.py --offline
The offline mode only creates explicitly unverified PENDING_EVIDENCE entries and is NOT a
live research pass. When doing offline tests against this repository be careful not to
commit the synthetic output as proof of a successful live run.

If an Actions run fails, inspect failing step and do NOT reset or overwrite watchlist.csv.
