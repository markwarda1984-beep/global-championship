# Global Investment Championship — research-only cloud scanner

This 30-stock starter monitors prices from **Yahoo Finance historical daily bars** and separately monitors **Bitcoin BTC/AUD and BTC/USD** on Kraken's public ticker endpoint. It does **not** place trades, log into brokerage accounts, use secrets, or connect to a broker.

## What you'll get

Every successful scan uploads a seven-day-retained GitHub Actions ZIP artifact containing:

- `index.html` — phone-friendly research dashboard with recent daily-close sparklines
- `latest.csv` — 30-stock comparison table, including local currency, research level, and data quality status
- `latest.json` — machine-readable stock history, Bitcoin bid/ask/last, timestamps, and monitoring-only metadata

`watchlist.csv` has 30 unique securities across Australia and international markets. **BABA $75 is a provisional, unvalidated research level, not a recommendation.** The remaining levels are intentionally blank. NVDA is currently tagged `NO BUY` for research purposes, not as a trading instruction. Prices are shown in each stock's quoted currency; there is no automatic FX conversion.

## Schedule (Sydney time, including DST)

Runs daily at **02:20, 08:20, 10:20, 13:20, 16:20 and 21:20** using GitHub Actions' `timezone: Australia/Sydney` schedule option. The workflow supports **Run workflow** manually and performs one integration run when the source is pushed to `main`. GitHub may delay or drop scheduled jobs; at daylight-saving spring transition, a nonexistent 02:20 time advances to the next valid time.

## To view a report

1. Open your repository's **Actions → Championship price scan**.
2. Select the latest successful workflow run, or use **Run workflow** to request a new run.
3. Under **Artifacts**, download `championship-dashboard-...`.
4. Extract the artifact and open `index.html`. `latest.csv` can be opened in a spreadsheet.

This is a *downloadable report*, not a hosted dashboard. Each workflow run creates a new separate artifact; it does not update a single live web page.

## Test locally (Python 3.11+)

```bash
python -m unittest discover -s tests -v
python -m pip install -r requirements.txt
python scan.py
```

The unit tests are **offline**, using injected fake data; a successful unit test does not establish that external market-data feeds or GitHub Actions have succeeded. The scanner flags unavailable external quotes instead of inserting simulated prices into reports.

## Security and scope

- No trading integrations, exchange keys, secrets, order APIs, or executable recommendations.
- Planned A$1,000 testing capital is **not yet funded**; confirmed holdings are an empty list.
- Stock quotes are last available **daily bars, not live**; Bitcoin public bid/ask/last prices are informational.
- This starter monitors only the 30 named stocks, **not** every global security. It does not provide validated intrinsic values, buy readiness scores, taxes, forecasts, or performance attribution.
- **Do not commit passwords, personal financial details or API keys.** Your GitHub repository was public when this package was prepared. You can make it private via repository Settings → General → Danger Zone → Change repository visibility.

## Windows one-command deployment option

If a connected app cannot write to GitHub: extract this ZIP on Windows with **Git for Windows** installed and your GitHub authentication configured. In PowerShell opened in the extracted folder, run:

```powershell
./publish-to-github.ps1
```

This script clones the repository, copies the scanner and workflow, commits and pushes to `main` **without force-pushing**. You may need to allow execution for this session (`Set-ExecutionPolicy -Scope Process RemoteSigned`) and enter your own GitHub credentials through Git Credential Manager. Check GitHub **Actions** for the first run after pushing.
