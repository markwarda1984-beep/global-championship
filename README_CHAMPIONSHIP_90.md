# Championship 9.0

9.0 is an additive research report. Existing 6.0 JSON schemas, file names,
validation flags, workflows, schedules and entries remain compatible. No broker
integration, order generation or automatic trade approval exists.

## Reports and operation

- `python championship_90.py --mode quotes`: fetch dated priority daily bars.
- `python championship_90.py --mode scan`: assess the fixed 200 plus discovery and
  the three priority names; publish `reports/valuation_90_latest.json`,
  `reports/coverage_90_latest.json`; add `championship_90` to legacy stock rows.
- `python championship_90.py --mode weekly`: weekly sidecar equivalents.
- `python verify_90.py --mode scan` (or `weekly`): verify published invariants.
- `python -m unittest discover -s tests -v`: entire offline suite.

The scan, discovery and weekly workflows retain all existing stages. Scan owns
priority quote publication; discovery expands geographical leads and carries
session lows in its existing candidate registry. Weekly reads the latest priority
quotes and rejects stale ones. Sidecar reports are committed and uploaded.

## Reconciliation

Statement currency is checked across every aggregate monetary series. Conversion
is explicit: aggregate cashflows × dated quote-currency-per-statement-currency FX
÷ ordinary share count × ordinary-shares-per-ADR. Share-count discrepancies above
5% against a separately documented count block the model. Explicitly documented
splits normalize earlier share observations; splits are never inferred from price.
The existing 15% unexplained share-change guard remains active.

`settings/primary_adapters_90.json` is a reviewed document boundary, initially
empty. Missing adapters are reported, never populated with guessed inputs.
Each ticker may contain `share_basis`, `fx` and `sector` entries.

A share_basis or sector document must contain:
`issuer`, HTTPS `source_url`, `accession_or_document_id`, dated `as_of` and
`published_at`, `review_status: PRIMARY_DOCUMENT_FIELDS_RECONCILED`, a `facts`
object, and `facts_sha256` (SHA256 of Python `json.dumps(facts, sort_keys=True)`).
The digest detects field changes; it is not independent issuer authentication.
A human must reconcile those fields with the linked primary document before use.
No invented issuer numbers are shipped with this release.

Share-basis facts: `ticker`, `quote_currency`, `ordinary_shares_per_receipt`,
`ordinary_shares_outstanding`, optional `splits` containing `effective_date` and
`new_per_old`. The ratio is ordinary shares PER receipt. FX records specify
`from`, `to`, positive `rate`, `as_of` within seven days and HTTPS `source_url`.

## Sector methods

Existing stable-business normalized earnings/DCF, seven-year cyclical normalization,
and bank justified-book methods are retained. New specialist models require all
relevant sourced inputs, including explicit zero debt or cash where applicable.

| Sector | Formula / required economics | Explicit scenario assumptions |
|---|---|---|
| REIT/property | Recurring AFFO attributable to common equity / listed shares / yield | 10%, 8%, 6.5% equity yields |
| Holding company | Appraised assets minus all liabilities, per listed share | 30%, 15%, 0% asset haircuts |
| Specialist financial | Tangible common equity/share × (normalized ROE − g)/(cost of equity − g) | 18%, 14%, 11% cost; 2% growth |
| Project/biotech | Risk-adjusted project NPV + cash − debt − remaining funding, per share | 0.5×, 1×, 1.25× project NPV |

All sector facts also require `ticker`, `currency` matching the quote and
`share_basis: LISTED_SHARES`. `shares` is mandatory. Required financial fields are
listed in `specialist()`; a missing field returns null. Forecast yields, haircuts
and discount rates are hypotheses, not reported financial facts. A holding's book
value is not silently treated as an appraisal. Biotech success probabilities are
not guessed. Generic models are never substituted for missing sector evidence.

## Entry and discovery ranking

Preserved user rules: HPE strictly below US$40; SKS.AX at/below A$5;
DUG.AX at/below A$1.50. These are priority research thresholds, separate from
valuation-derived entries. Each reports threshold status and whether the latest
close broke the previous five-session intraday low. Unknown prices, currencies,
stale dates and missing lows produce unknown status. No recovery confirmation is
required before research review.

New 5-session, 30-session and 252-session lows use unadjusted intraday Low bars,
including the latest session. Previous five-session low excludes the latest.
Close-only minima are separately named. Short or missing histories return null;
legacy scanner `low_52w` remains its original close minimum and the actual trading
low is `trading_low_52w`. Corporate actions can distort unadjusted historical lows;
review documented splits and do not interpret these levels as total-return lows.

Ranking requires reconciled economic inputs, a quote no older than seven days,
at least 25% modeled base upside and a close within 3% of the five-session low.
25–50% scenarios are preferred before larger modeled gains; then smaller recovery
ranks first. These numerical filters are explicit research heuristics, not proof
of a catalyst, liquidity, business quality or a guaranteed return. An empty queue
is valid. The system never forces ten names into an unsupported opportunity list.

Discovery rotates six regional/theme searches and parses explicit NASDAQ, NYSE,
ASX, TSX/TSXV, LSE, HKEX, TSE, SGX, XETRA and NSE ticker references. News-only
leads remain unverified; existing primary-source/liquidity admission gates remain.
The bounded per-run quote budget rises from 35 to 60; this is not exhaustive
coverage of global exchanges. Market-specific quote currencies/units and issuer
identity must be reconciled before any financial valuation.

## Coverage comparison

`settings/coverage_baseline_90.json` freezes the pre-install fixed-200 baseline:
200 assessed, 41 with validated primary model inputs. Each 9.0 sidecar compares
same-run legacy coverage with its reconciled coverage, lists gains/losses and
retains missing-input reasons for every company. Assessment count is never
presented as successful valuation count. Missing foreign filings and specialist
adapters remain visible; this code does not manufacture 200 valuations.
