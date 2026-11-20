# Championship 5.2 — concurrent GitHub report publishing hotfix

**Problem diagnosed from live GitHub Actions run 44818711796:** both the 200-stock scanner and the discovery workflow succeeded at generating their reports, but their near-simultaneous pushes to `main` caused GitHub to reject the discovery push: `cannot lock ref refs/heads/main ... expected ...`.

**Fix:** each report workflow (200-stock scan, valuation, and discovery) now fetches the newest `main`, rebases its own generated report commit, and retries a non-force push up to 6 times with gradual pauses. No source code, report generation, trading guards, schedule, `watchlist.csv`, or user secrets are changed. If publishing cannot be completed after 6 attempts, the job fails with an explicit error and uploaded artifacts are retained.

## Install on Android with GitSync
1. Extract this ZIP **into** your existing `Documents/global-championship` repository folder and replace the three `.github/workflows/*.yml` files. Ensure your unzip app keeps the hidden `.github` folder.
2. Preserve the `.git` folder and all other files. Do not overwrite or delete your repository directory.
3. Open GitSync → three dots beside Sync Changes → Upload Changes (NOT Upload + Overwrite).
4. A `push` should start both scan and discovery workflows. Confirm both complete with a green check and `reports/latest.json` and `reports/discovery_latest.json` have fresh timestamps.
5. If needed, manually select **Run workflow** from GitHub Actions → Championship 5.2 discovery radar.

**Verification before deployment:** checked shell syntax for all three modified publication steps. Live conflict resolution still needs a real GitHub Actions run. No trades are enabled.
