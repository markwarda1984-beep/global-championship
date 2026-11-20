"""Championship 5.2: resilient, multi-source, read-only discovery radar.

Purpose: separate, expandable stock monitoring outside the fixed 200 ticker scan.
New ticker admission means research monitoring only, NEVER fair-value validation,
a trade recommendation, a buy signal, or broker execution.

Sources: SEC EDGAR current 8-K Atom feed + SEC listed ticker directory;
GDELT and Google News RSS headlines are secondary leads, never MONITOR-eligible without a primary disclosure.
Curated seed disclosures explicitly provided in discovery_seeds.csv can bootstrap
ASX and US research monitoring, if recent and liquid.

The system never claims complete global market coverage. Source failures are
recorded, cannot be turned into 'no news' claims, and do not erase history.
"""
from __future__ import annotations

import argparse
import csv
from email.utils import parsedate_to_datetime
import json
import logging
import os
import re
import statistics
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

BASE = Path(__file__).resolve().parent
SEC_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_FEED = "https://www.sec.gov/cgi-bin/browse-edgar"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BING_NEWS_RSS = "https://www.bing.com/news/search"
TRUSTED_SEED_HOSTS = {
    "dug.com", "www.dug.com", "announcements.asx.com.au",
    "investorhub.eos-aus.com", "eos-aus.com",
    "www.sec.gov", "sec.gov", "ir.bitdeer.com", "bitdeer.gcs-web.com",
    "ir.penguinsolutions.com",
}
THEME_TERMS = (
    "ai", "artificial intelligence", "data center", "datacenter", "gpu", "compute",
    "semiconductor", "high performance computing", "photonics", "quantum",
    "defense", "defence", "counter drone", "counter-drone", "space", "satellite",
    "launch", "rocket", "biotech", "phase 3", "fda", "rare earth", "uranium",
    "nuclear", "energy storage", "bitcoin", "crypto", "robotics",
)
EVENT_TERMS = (
    "contract", "order", "agreement", "award", "approval", "trial", "results",
    "revenue", "earnings", "backlog", "financing", "acquisition", "guidance",
)
QUERY_TERMS = (
    '("AI infrastructure" OR "data center" OR "GPU cluster") (contract OR earnings OR agreement)',
    '("counter drone" OR "satellite" OR "small modular reactor") (contract OR order OR approval)',
    '("phase 3" OR photonics OR "rare earth") (results OR contract OR award)',
)
GOOGLE_NEWS_TERMS = (
    '"AI infrastructure" contract OR "data center" deal OR "GPU cloud" agreement when:7d',
    '"counter drone" contract OR satellite order OR "nuclear" approval when:7d',
    '"phase 3" results OR photonics contract OR "rare earth" award when:7d',
)
MIN_PRICE = 0.50
MIN_MEDIAN_DOLLAR_VOLUME = 150_000.0
MAX_MARKET_CAP = 20_000_000_000.0
MAX_CANDIDATES_PER_RUN = 35
MAX_REGISTRY_SIZE = 1500
MAX_OPEN_RESEARCH = 160
MAX_NEWS_ONLY_PER_RUN = 8
SEC_CONTACT_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
TODAY = lambda: datetime.now(timezone.utc)
LOGGER = logging.getLogger("championship_discovery")


def iso_date(text: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if not d.tzinfo else d.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def is_recent(value: str, now: datetime, days: int = 45) -> bool:
    d = iso_date(value)
    return bool(d and now - timedelta(days=days) <= d <= now + timedelta(days=1))


def safe_ticker(s: str) -> str | None:
    value = str(s).strip().upper()
    return value if re.fullmatch(r"[A-Z0-9.\-]{1,12}", value) else None


def safe_primary(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme == "https" and p.hostname in TRUSTED_SEED_HOSTS and not p.username and not p.password
    except ValueError:
        return False


def load_original_200(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        data = list(csv.DictReader(f))
    result = [safe_ticker(x.get("ticker", "")) for x in data]
    if len(result) != 200 or len(set(result)) != 200 or None in result:
        raise ValueError("Original watchlist.csv must remain exactly 200 unique tickers")
    return set(result)


def read_seeds(path: Path, now: datetime) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        ticker = safe_ticker(row.get("ticker", ""))
        url = row.get("official_url", "").strip()
        if not ticker or not safe_primary(url):
            LOGGER.warning("Skipping untrusted/incomplete seed: %s", row.get("ticker"))
            continue
        if not is_recent(row.get("evidence_date", ""), now):
            LOGGER.warning("Skipping outdated/future seed: %s", ticker)
            continue
        out.append({
            "ticker": ticker,
            "company": row.get("company", "").strip()[:160],
            "theme": row.get("theme", "").strip()[:90],
            "evidence_date": row["evidence_date"].strip(),
            "evidence_url": url,
            "evidence_kind": "CURATED_OFFICIAL_DISCLOSURE_REFERENCE",
            "discovery_source": "seed file (human-curated public source)",
            "corroboration": "Not independently parsed/validated by this automation",
        })
    return out


def sec_cik_map(payload: Any) -> dict[str, dict]:
    """Convert documented SEC JSON table format; never guess a ticker."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unrecognised SEC ticker directory")
    fields = [str(c).strip().lower() for c in payload.get("fields", [])]
    for field in ("cik", "name", "ticker", "exchange"):
        if field not in fields:
            raise ValueError(f"SEC mapping lacks {field}")
    index = {name: fields.index(name) for name in ("cik", "name", "ticker", "exchange")}
    result = {}
    for line in payload["data"]:
        try:
            ticker = safe_ticker(line[index["ticker"]])
            exchange = str(line[index["exchange"]]).upper().strip()
            if ticker and exchange in {"NASDAQ", "NYSE", "NYSE AMERICAN", "NYSE ARCA"}:
                result[str(int(line[index["cik"]]))] = {
                    "ticker": ticker, "company": str(line[index["name"]])[:160], "exchange": exchange
                }
        except (TypeError, ValueError, IndexError):
            continue
    return result


def parse_sec_atom(xml: str, lookup: dict[str, dict], now: datetime) -> dict[str, dict]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    out = {}
    for entry in root.findall("a:entry", ns):
        title = entry.findtext("a:title", "", ns)
        summary = " ".join(entry.findtext("a:summary", "", ns).split())
        link = entry.find("a:link", ns)
        url = link.get("href", "") if link is not None else ""
        if not url.startswith("https://www.sec.gov/"):
            continue
        cik = re.search(r"/data/(\d+)/", url)
        if not cik:
            cik = re.search(r"\((\d{10})\)", title)
        if not cik:
            continue
        corp = lookup.get(str(int(cik.group(1))))
        if not corp:
            continue
        published = entry.findtext("a:updated", "", ns) or entry.findtext("a:published", "", ns)
        if not is_recent(published, now, 10):
            continue
        # RSS is a filing pointer, NOT verification that the event is positive.
        t = corp["ticker"]
        if t not in out or str(published) > str(out[t]["evidence_date"]):
            out[t] = {**corp, "evidence_date": published, "evidence_url": url,
                      "evidence_kind": "SEC_8K_FILING_REFERENCE", "filing_title": title[:250],
                      "filing_summary": summary[:1200]}
    return out


def normalize_company(s: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    text = re.sub(r"\b(incorporated|inc|corp|corporation|ltd|limited|holdings|group|class|co|plc)\b", " ", text)
    return " ".join(text.split())


def extract_news_matches(articles: list[dict], filings: dict[str, dict]) -> list[dict]:
    """News coverage is a lead, not a primary source. Only SEC 8-K matches qualify."""
    matches = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", ""))[:300]
        t_lower = title.lower()
        if not any(re.search(r"\b" + re.escape(w) + r"\b", t_lower) for w in THEME_TERMS):
            continue
        if not any(re.search(r"\b" + re.escape(w) + r"\b", t_lower) for w in EVENT_TERMS):
            continue
        for ticker, record in filings.items():
            name = normalize_company(record["company"])
            if len(name) < 10 or len(name.split()) < 2:
                continue
            # Exact normalized company phrase avoids ambiguous symbol-only matches.
            title_normalized = normalize_company(title)
            if re.search(r"\b" + re.escape(name) + r"\b", title_normalized):
                matches.append({**record, "ticker": ticker, "theme": "event-driven small-cap lead",
                                "discovery_source": ("Bing News RSS lead AND public SEC 8-K" if article.get("source") == "bing_news_rss" else "Google News RSS lead AND public SEC 8-K" if article.get("source") == "google_news_rss" else "GDELT news lead AND public SEC 8-K"),
                                "corroboration": "Independent news article matched named SEC filer; contents not verified",
                                "news_title": title, "news_url": str(article.get("url", ""))[:500]})
                break
    result = {}
    for x in matches:
        result.setdefault(x["ticker"], x)
    return list(result.values())


def gdelt_seen_date(article: dict, now: datetime) -> str | None:
    """Recognize GDELT's YYYYMMDDTHHMMSSZ timestamps; reject undated rumours."""
    raw = str(article.get("seendate", "") or article.get("date", "")).strip()
    date = iso_date(raw)
    if date is None:
        try:
            date = datetime.strptime(raw.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return date.isoformat() if is_recent(date.isoformat(), now, 10) else None


def extract_unverified_news_leads(articles: list[dict], now: datetime) -> list[dict]:
    """Extract explicit exchange:ticker references, NEVER a primary filing claim.

    A news article can be mislabelled or speculative. This function only adds a
    PENDING_EVIDENCE lead, even when liquidity and market cap pass the gate.
    """
    results: dict[str, dict] = {}
    pattern = re.compile(r"\b(NASDAQ|NYSE|ASX)\s*:\s*\$?([A-Z][A-Z0-9.\-]{0,10})\b", re.I)
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title", ""))[:350]
        lower = title.lower()
        if not any(re.search(r"\b" + re.escape(t) + r"\b", lower) for t in THEME_TERMS):
            continue
        if not any(re.search(r"\b" + re.escape(t) + r"\b", lower) for t in EVENT_TERMS):
            continue
        date = gdelt_seen_date(article, now)
        if date is None:
            continue
        url = str(article.get("url", ""))[:550]
        try:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        for match in pattern.finditer(title):
            exchange, raw = match.groups()
            ticker = safe_ticker(raw)
            if not ticker:
                continue
            ticker = ticker + ".AX" if exchange.upper() == "ASX" and not ticker.endswith(".AX") else ticker
            if ticker in results:
                continue
            results[ticker] = {
                "ticker": ticker, "company": title[:160],
                "theme": "unverified event-driven news ticker lead",
                "evidence_date": date, "evidence_url": url,
                "evidence_kind": "SECONDARY_NEWS_TICKER_LEAD_UNVERIFIED",
                "discovery_source": ("Bing News RSS (secondary, unverified)" if article.get("source") == "bing_news_rss" else "Google News RSS (secondary, unverified)" if article.get("source") == "google_news_rss" else "GDELT news (secondary, unverified)"),
                "corroboration": "Exchange ticker only appears in news headline; verify issuer identity and primary filing",
                "news_title": title,
            }
            if len(results) >= MAX_NEWS_ONLY_PER_RUN:
                return list(results.values())
    return list(results.values())


def parse_google_news_rss(xml_text: str, now: datetime, limit: int = 60,
                          source: str = "google_news_rss") -> list[dict]:
    """Parse only dated, HTTPS RSS news *links*, never claim they are primary filings.

    Google News RSS is an uncontracted public feed; results may be stale or
    incomplete. Its links can be opaque Google redirects rather than publisher URLs.
    """
    root = ET.fromstring(xml_text)
    if root.tag != "rss":
        raise ValueError("Not a Google News RSS document")
    articles: list[dict] = []
    seen: set[str] = set()
    for item in root.findall("./channel/item"):
        title = " ".join((item.findtext("title") or "").split())[:350]
        url = (item.findtext("link") or "").strip()[:550]
        pub_date = (item.findtext("pubDate") or "").strip()
        try:
            date = parsedate_to_datetime(pub_date).astimezone(timezone.utc)
            parsed_url = urlparse(url)
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if (not title or not url or url in seen or parsed_url.scheme != "https"
                or not parsed_url.hostname or parsed_url.username or parsed_url.password
                or not is_recent(date.isoformat(), now, 10)):
            continue
        seen.add(url)
        articles.append({"title": title, "url": url,
                         "seendate": date.isoformat(), "source": source})
        if len(articles) >= limit:
            break
    return articles


def valid_sec_contact(value: str) -> bool:
    """SEC asks automated clients to identify themselves with a working contact."""
    return bool(value and len(value) <= 250 and "\n" not in value and "\r" not in value
                and SEC_CONTACT_PATTERN.search(value))


def market_checks(quote: dict | None, *, capital_limit: float = MAX_MARKET_CAP) -> tuple[bool, list[str]]:
    """Liquidity/quote checks; a passing result is NOT valuation or business diligence."""
    if quote is None:
        return False, ["QUOTE_UNAVAILABLE"]
    problems = []
    price = quote.get("price")
    volume = quote.get("median_dollar_volume_20d")
    age = quote.get("stale_days")
    cap = quote.get("market_cap")
    if not isinstance(price, (int, float)) or not MIN_PRICE <= price < 100000:
        problems.append("PRICE_INELIGIBLE")
    if not isinstance(volume, (int, float)) or volume < MIN_MEDIAN_DOLLAR_VOLUME:
        problems.append("THIN_LIQUIDITY_OR_UNKNOWN")
    if not isinstance(age, (int, float)) or age > 7 or age < 0:
        problems.append("STALE_PRICE")
    if cap is not None and (not isinstance(cap, (int, float)) or cap > capital_limit or cap <= 0):
        problems.append("OUTSIDE_SMALL_MIDCAP_SCOPE")
    if cap is None:
        problems.append("MARKET_CAP_UNVERIFIED")
    return len(problems) == 0, problems


def evaluate(candidates: list[dict], quotes: dict, previous: dict, original: set[str], now: datetime) -> dict:
    """Incremental, deterministic: all historical tracked names kept; no silent deletion."""
    if any(not safe_ticker(s) for s in original):
        raise ValueError("Original stock list malformed")
    history = previous.get("candidates", {}) if isinstance(previous, dict) else {}
    if not isinstance(history, dict):
        history = {}
    result = {k: dict(v) for k, v in history.items() if safe_ticker(k) and isinstance(v, dict)}
    events = {"newly_monitored": [], "new_pending": [], "newly_archived": [], "revived": []}
    seen = set()
    for c in candidates[:MAX_CANDIDATES_PER_RUN]:
        ticker = safe_ticker(c.get("ticker", ""))
        if not ticker or ticker in original or ticker in seen:
            continue
        if not str(c.get("evidence_url", "")).startswith("https://") or not is_recent(c.get("evidence_date", ""), now):
            continue
        prior = result.get(ticker, {})
        primary = c.get("evidence_kind") in {"SEC_8K_FILING_REFERENCE", "CURATED_OFFICIAL_DISCLOSURE_REFERENCE"}
        if not primary and prior.get("evidence_kind") in {"SEC_8K_FILING_REFERENCE", "CURATED_OFFICIAL_DISCLOSURE_REFERENCE"}:
            # A later unverified headline must not overwrite an existing primary reference.
            continue
        seen.add(ticker)
        quote = quotes.get(ticker)
        eligible, concerns = market_checks(quote)
        if not primary:
            eligible = False
            concerns = ["PRIMARY_DISCLOSURE_NOT_VERIFIED"] + concerns
        if prior.get("status") == "MANUAL_EXCLUDE":
            continue
        is_new = ticker not in result
        status = "MONITOR" if eligible else "PENDING_EVIDENCE"
        merged = {**prior, "ticker": ticker, "company": c.get("company"), "theme": c.get("theme", "unspecified"),
                  "status": status, "last_researched_utc": now.isoformat(), "evidence_url": c["evidence_url"],
                  "evidence_date": c["evidence_date"], "evidence_kind": c.get("evidence_kind", "UNKNOWN"),
                  "discovery_source": c.get("discovery_source"), "corroboration": c.get("corroboration"), "primary_disclosure_reference": primary,
                  "last_quote": quote or None, "concerns": concerns,
                  "review_status": "RESEARCH ONLY — PRIMARY DISCLOSURE CONTENT/VALUATION NOT CONFIRMED",
                  "buy_readiness": None, "orders_enabled": False}
        merged.setdefault("first_seen_utc", now.isoformat())
        merged["failed_checks"] = 0 if eligible else (int(prior.get("failed_checks", 0)) + 1)
        result[ticker] = merged
        if is_new:
            events["newly_monitored" if eligible else "new_pending"].append(ticker)
        elif prior.get("status") == "ARCHIVED_MONITORING" and eligible:
            events["revived"].append(ticker)
    for ticker, prior in list(result.items()):
        if ticker in seen or ticker in original or prior.get("status") == "MANUAL_EXCLUDE":
            continue
        # Do not archive only because upstream feed is unavailable on a single run.
        quote = quotes.get(ticker)
        if quote is None:
            continue
        eligible, concerns = market_checks(quote)
        failures = 0 if eligible else int(prior.get("failed_checks", 0)) + 1
        prior["last_quote"] = quote
        prior["last_researched_utc"] = now.isoformat()
        prior["failed_checks"] = failures
        prior["concerns"] = concerns
        # Three consecutive objective price/liquidity failures -> archive monitoring,
        # NOT a claim that its investment thesis failed.
        if prior.get("status") == "MONITOR" and failures >= 3:
            prior["status"] = "ARCHIVED_MONITORING"
            prior["archive_reason"] = "3 consecutive failed liquidity/quote checks"
            events["newly_archived"].append(ticker)
        elif prior.get("status") == "ARCHIVED_MONITORING" and eligible:
            prior["status"] = "MONITOR"
            prior.pop("archive_reason", None)
            events["revived"].append(ticker)
    # Preserve old entries even if above cap; new discovery admission must not evict history.
    return {"schema_version": "5.2-discovery-radar-1", "updated_at_utc": now.isoformat(),
            "original_200_unchanged": True, "candidates": dict(sorted(result.items())),
            "events": events, "orders_enabled": False}


def make_snapshot(registry: dict, health: dict, now: datetime) -> dict:
    candidates = registry["candidates"]
    counts = {s: sum(c.get("status") == s for c in candidates.values()) for s in
              ("MONITOR", "PENDING_EVIDENCE", "ARCHIVED_MONITORING", "MANUAL_EXCLUDE")}
    active = [x for x in candidates.values() if x.get("status") == "MONITOR"]
    sec_ok = health.get("sec_8k", {}).get("status") == "ok"
    gdelt_ok = health.get("gdelt", {}).get("status") == "ok"
    fallback_ok = any(health.get(name, {}).get("status") == "ok" for name in ("google_news", "bing_news"))
    source_coverage = ("COMPLETE_FOR_CONFIGURED_SAMPLES" if sec_ok and gdelt_ok else
                       "CORE_SOURCES_AVAILABLE_WITH_FALLBACK" if sec_ok and fallback_ok else
                       "PARTIAL_OR_UNAVAILABLE")
    return {"schema_version": "5.2-discovery-radar-1", "published_at_utc": now.isoformat(),
            "source_coverage": source_coverage,
            "total_discovered_ever": len(candidates), "monitor_count": counts["MONITOR"],
            "pending_count": counts["PENDING_EVIDENCE"], "archived_count": counts["ARCHIVED_MONITORING"],
            "newly_monitored": registry["events"]["newly_monitored"],
            "new_pending": registry["events"]["new_pending"],
            "newly_archived": registry["events"]["newly_archived"],
            "revived": registry["events"]["revived"], "source_health": health,
            "active_watchlist": sorted(active, key=lambda x: x["ticker"]),
            "research_only": True, "orders_enabled": False,
            "limitations": ["US SEC 8-K feed is not exhaustive; GDELT, Google News RSS and Bing News RSS are sampling sources with no guaranteed availability",
                            "ASX general-market discovery not yet implemented; curated ASX seeds only",
                            "Cited filing/announcement is not automatically checked for investment merit",
                            "Liquidity, market cap, quote and valuation can be missing or delayed",
                            "No price level, readiness percent, trade or expected return is automatically validated",
                            "News-only ticker mentions remain PENDING_EVIDENCE even if liquidity tests pass"]}


class SourceFetchError(RuntimeError):
    def __init__(self, source: str, code: int | None, message: str,
                 retry_after_seconds: int | None = None):
        super().__init__(f"{source}: {message}")
        self.code = code
        self.retry_after_seconds = retry_after_seconds


def fetch_with_retry(session, url: str, *, params: dict | None = None, source: str = "source") -> Any:
    """Retry transient 5xx/timeouts only; do NOT hammer a 403 or 429 source."""
    import requests
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = session.get(url, params=params, timeout=18)
            code = int(getattr(response, "status_code", 200))
            if code in (401, 403, 429):
                detail = "access_denied_403" if code == 403 else ("rate_limited_429" if code == 429 else "unauthorized_401")
                retry_hint = None
                if code == 429:
                    retry_raw = getattr(response, "headers", {}).get("Retry-After", "")
                    try:
                        retry_hint = max(0, min(int(retry_raw), 7 * 24 * 3600))
                    except (TypeError, ValueError, OverflowError):
                        pass
                raise SourceFetchError(source, code, detail, retry_hint)
            response.raise_for_status()
            return response
        except SourceFetchError:
            raise
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            last = exc
            if status not in (500, 502, 503, 504) or attempt == 1:
                raise SourceFetchError(source, status, f"http_{status or 'unknown'}") from exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
            if attempt == 1:
                raise SourceFetchError(source, None, f"transient_network_{type(exc).__name__}") from exc
        if attempt == 0:
            time.sleep(2.0)
    raise SourceFetchError(source, None, f"upstream_unavailable_{type(last).__name__}")


def discover_external(session, now: datetime, *, sec_configured: bool = True,
                      source_state: dict | None = None) -> tuple[list[dict], dict]:
    """SEC corroboration + rate-limited GDELT with independent RSS fallback.

    A 429 opens a *persistent* cooldown, carried through the tracked registry.
    No attempt is made to sidestep rate limits or rotate request identity/IP.
    """
    health: dict[str, Any] = {}
    filings: dict[str, dict] = {}
    if not sec_configured:
        health["sec_8k"] = {
            "status": "configuration_required",
            "reason": "SEC_USER_AGENT must contain a genuine contact email in GitHub Actions secrets",
            "coverage": "SEC filings NOT checked (not equivalent to no new filings)"}
    else:
        try:
            directory = sec_cik_map(fetch_with_retry(session, SEC_TICKERS, source="sec_ticker_directory").json())
            response = fetch_with_retry(session, SEC_FEED, source="sec_latest_8k", params={
                "action": "getcurrent", "type": "8-K", "owner": "include", "count": "100", "output": "atom"})
            filings = parse_sec_atom(response.text, directory, now)
            health["sec_8k"] = {"status": "ok", "latest_feed_matched_listed_tickers": len(filings),
                                 "coverage": "at most latest 100 filings; not an exhaustive market screen"}
        except SourceFetchError as exc:
            status = "access_denied" if exc.code in (401, 403) else ("rate_limited" if exc.code == 429 else "unavailable")
            health["sec_8k"] = {"status": status, "http_status": exc.code, "reason": str(exc)[:180],
                                 "coverage": "SEC filings NOT checked (not equivalent to no new filings)"}
        except (ValueError, ET.ParseError) as exc:
            health["sec_8k"] = {"status": "unavailable", "reason": "invalid SEC response or ticker mapping", "error_type": type(exc).__name__}

    # Six scheduled runs/day cover three topics twice, without request bursts.
    slot = (2, 8, 10, 13, 16, 21).index(now.hour) if now.hour in (2, 8, 10, 13, 16, 21) else now.hour % 6
    theme_index = slot % len(QUERY_TERMS)
    articles: list[dict] = []
    last = source_state if isinstance(source_state, dict) else {}
    retry_at = iso_date(last.get("gdelt_retry_at_utc", ""))
    try:
        streak = max(0, min(int(last.get("gdelt_consecutive_429", 0)), 8))
    except (ValueError, TypeError):
        streak = 0

    if retry_at is not None and now < retry_at:
        health["gdelt"] = {"status": "cooldown", "checked_theme": theme_index + 1,
                           "next_attempt_at_utc": retry_at.isoformat(),
                           "reason": "Prior 429: respect provider limit across scheduled runs"}
    else:
        try:
            response = fetch_with_retry(session, GDELT, source="gdelt_doc", params={
                "query": QUERY_TERMS[theme_index], "mode": "artlist", "format": "json",
                "timespan": "1week", "maxrecords": "50", "sort": "datedesc"})
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("articles", []), list):
                raise ValueError("Invalid GDELT JSON article format")
            # Filter unsafe/undated articles before either SEC match or ticker mention.
            articles = [a for a in data.get("articles", []) if
                        isinstance(a, dict) and gdelt_seen_date(a, now)
                        and str(a.get("url", "")).startswith("https://")]
            health["gdelt"] = {"status": "ok", "checked_theme": theme_index + 1,
                                "themes_total": len(QUERY_TERMS), "article_count": len(articles),
                                "coverage": "One rotating topic per run; not exhaustive"}
            streak, retry_at = 0, None
        except SourceFetchError as exc:
            status = "rate_limited" if exc.code == 429 else ("access_denied" if exc.code in (401, 403) else "unavailable")
            # Never hammer a cloud-shared IP: exponential cross-run cooldown.
            if exc.code in (401, 403, 429):
                delay = min(72 * 3600, (12 * 3600) * 2 ** min(streak, 3))
                if exc.retry_after_seconds is not None:
                    delay = max(delay, exc.retry_after_seconds)
                retry_at = now + timedelta(seconds=delay)
                streak = min(streak + 1, 8)
            health["gdelt"] = {"status": status, "http_status": exc.code,
                               "checked_theme": theme_index + 1, "reason": str(exc)[:180],
                               "next_attempt_at_utc": retry_at.isoformat() if retry_at else None,
                               "next_action": "RSS fallback; retry only after persistent cooldown"}
        except (ValueError, TypeError) as exc:
            health["gdelt"] = {"status": "unavailable", "checked_theme": theme_index + 1,
                               "reason": "Invalid or incomplete GDELT response", "error_type": type(exc).__name__}
    health["gdelt_control"] = {"gdelt_retry_at_utc": retry_at.isoformat() if retry_at else None,
                               "gdelt_consecutive_429": streak}

    # Use a genuinely distinct provider. This is not a GDELT proxy or rate-limit bypass.
    # Google News RSS is a public, unguaranteed feed; failure is also reported.
    if health["gdelt"]["status"] != "ok":
        try:
            resp = fetch_with_retry(session, GOOGLE_NEWS_RSS, source="google_news_rss",
                                    params={"q": GOOGLE_NEWS_TERMS[theme_index],
                                            "hl": "en-AU", "gl": "AU", "ceid": "AU:en"})
            articles = parse_google_news_rss(resp.text, now)
            health["google_news"] = {"status": "ok", "checked_theme": theme_index + 1,
                                     "article_count": len(articles),
                                     "coverage": "RSS headline sample only; source articles not independently verified"}
        except SourceFetchError as exc:
            status = "rate_limited" if exc.code == 429 else ("access_denied" if exc.code in (401, 403) else "unavailable")
            health["google_news"] = {"status": status, "http_status": exc.code,
                                     "reason": str(exc)[:180], "checked_theme": theme_index + 1}
        except (ValueError, ET.ParseError, TypeError) as exc:
            health["google_news"] = {"status": "unavailable", "reason": "Invalid RSS format",
                                     "error_type": type(exc).__name__, "checked_theme": theme_index + 1}
    else:
        health["google_news"] = {"status": "not_needed", "reason": "GDELT returned a valid response"}

    # Separate tertiary source if Google News RSS is blocked or has no recent hits.
    if health["gdelt"]["status"] != "ok" and not articles:
        try:
            response = fetch_with_retry(session, BING_NEWS_RSS, source="bing_news_rss",
                                        params={"q": GOOGLE_NEWS_TERMS[theme_index].replace(" when:7d", ""),
                                                "format": "rss"})
            articles = parse_google_news_rss(response.text, now, source="bing_news_rss")
            health["bing_news"] = {"status": "ok", "checked_theme": theme_index + 1,
                                   "article_count": len(articles),
                                   "coverage": "Bing RSS headline sample only; links are not primary filings"}
        except SourceFetchError as exc:
            status = "rate_limited" if exc.code == 429 else ("access_denied" if exc.code in (401, 403) else "unavailable")
            health["bing_news"] = {"status": status, "http_status": exc.code,
                                   "reason": str(exc)[:180], "checked_theme": theme_index + 1}
        except (ValueError, ET.ParseError, TypeError) as exc:
            health["bing_news"] = {"status": "unavailable", "reason": "Invalid RSS format",
                                   "error_type": type(exc).__name__, "checked_theme": theme_index + 1}
    else:
        health["bing_news"] = {"status": "not_needed", "reason": "GDELT/Google news source was usable"}

    verified_leads = extract_news_matches(articles, filings)
    secondary_leads = extract_unverified_news_leads(articles, now)
    verified_tickers = {c["ticker"] for c in verified_leads}
    secondary_leads = [c for c in secondary_leads if c["ticker"] not in verified_tickers]
    health["new_lead_coverage"] = {"corroborated_sec_and_news": len(verified_leads),
                                   "secondary_only_pending": len(secondary_leads),
                                   "disclosure_validated": False}
    return verified_leads + secondary_leads, health


def rotate_price_queue(new_names: list[str], prior_names: list[str], now: datetime,
                       limit: int = MAX_CANDIDATES_PER_RUN) -> list[str]:
    """Price-check new leads first and rotate older monitored names fairly.

    Coverage is intentionally bounded per run, NOT a claim of continuous quotes.
    """
    recent = list(dict.fromkeys(new_names))[:limit]
    old = [x for x in dict.fromkeys(prior_names) if x not in recent]
    remaining = max(0, limit - len(recent))
    if not old or not remaining:
        return recent
    start = (now.date().toordinal() * 6 + now.hour) % len(old)
    return recent + [old[(start + k) % len(old)] for k in range(min(remaining, len(old)))]


def fetch_quotes(tickers: list[str], now: datetime, max_names: int = MAX_CANDIDATES_PER_RUN) -> tuple[dict, dict]:
    """Yahoo daily bars; price/capitalisation delayed or unofficial; not executable."""
    import yfinance as yf
    quotes = {}
    health = {"status": "ok", "attempted": min(len(tickers), max_names), "failed": 0}
    for ticker in tickers[:max_names]:
        try:
            asset = yf.Ticker(ticker)
            frame = asset.history(period="4mo", interval="1d", auto_adjust=False, actions=False)
            if frame.empty or len(frame) < 25:
                raise ValueError("fewer than 25 daily bars")
            pairs = [(float(x), float(v)) for x, v in zip(frame["Close"].tail(20), frame["Volume"].tail(20))
                     if x is not None and v is not None and float(x) > 0 and float(v) >= 0]
            if len(pairs) < 15:
                raise ValueError("incomplete price/volume history")
            px = float(frame["Close"].iloc[-1])
            qtime = frame.index[-1].to_pydatetime().date().isoformat()
            day = datetime.fromisoformat(qtime).replace(tzinfo=timezone.utc)
            if day > now + timedelta(days=1):
                raise ValueError("future quote date")
            median = statistics.median([p * v for p, v in pairs])
            try:
                cap = asset.fast_info.get("market_cap")
                cap = float(cap) if cap is not None else None
            except Exception:
                cap = None
            quotes[ticker] = {"price": round(px, 5), "quote_date": qtime,
                              "stale_days": max(0, (now.date() - day.date()).days),
                              "median_dollar_volume_20d": round(median, 2),
                              "market_cap": cap, "price_source": "unofficial yfinance daily bars — not executable"}
        except Exception as exc:
            health["failed"] += 1
            LOGGER.warning("Price check unavailable for %s: %s", ticker, str(exc)[:200])
    return quotes, health


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(*, root: Path = BASE, offline: bool = False) -> dict:
    now = TODAY()
    original = load_original_200(root / "watchlist.csv")
    registry_path = root / "reports" / "discovery_watchlist.json"
    report_path = root / "reports" / "discovery_latest.json"
    previous = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    seeds = read_seeds(root / "discovery_seeds.csv", now)
    health: dict[str, Any] = {"curated_seeds": {"status": "ok", "count": len(seeds)}}
    external: list[dict] = []
    if offline:
        health["external"] = {"status": "offline: no upstream checks"}
        quotes = {}
        health["quotes"] = {"status": "offline: no market data"}
    else:
        import requests
        ua = os.environ.get("SEC_USER_AGENT", "").strip()
        session = requests.Session()
        # Never invent a contact email. Unconfigured SEC discovery is explicitly skipped.
        if valid_sec_contact(ua):
            session.headers.update({"User-Agent": ua})
        else:
            session.headers.update({"User-Agent": "Championship-Discovery/5.2 research-only"})
        session.headers.update({"Accept": "application/json, application/atom+xml, */*"})
        external, remote_health = discover_external(session, now,
            sec_configured=valid_sec_contact(ua), source_state=previous.get("source_state"))
        health.update(remote_health)
        # New leads are checked first; existing research names rotate fairly as list grows.
        new_names = [c["ticker"] for c in seeds + external if c["ticker"] not in original]
        old_names = [t for t, v in previous.get("candidates", {}).items()
                     if t not in original and v.get("status") in
                     ("MONITOR", "PENDING_EVIDENCE", "ARCHIVED_MONITORING")]
        names = rotate_price_queue(new_names, old_names, now)
        quotes, quote_health = fetch_quotes(names, now)
        quote_health["coverage"] = "bounded research sample, rotating existing names; not every candidate is requoted every run"
        quote_health["available_candidates"] = len(set(new_names + old_names))
        health["quotes"] = quote_health
    # Limit discovery names without losing already monitored history.
    seen = set()
    candidates = []
    for c in seeds + external:
        s = c["ticker"]
        if s not in seen and s not in original:
            seen.add(s)
            candidates.append(c)
    registry = evaluate(candidates, quotes, previous, original, now)
    # Keep GDELT backoff across independent Actions runs via committed watchlist JSON.
    if offline:
        registry["source_state"] = previous.get("source_state", {})
    else:
        registry["source_state"] = health.get("gdelt_control", {})
    snapshot = make_snapshot(registry, health, now)
    write_json(registry_path, {k: v for k, v in registry.items() if k != "events"})
    write_json(report_path, snapshot)
    LOGGER.info("Discovery: %s monitoring, %s pending, %s archived, %s new",
                snapshot["monitor_count"], snapshot["pending_count"], snapshot["archived_count"],
                len(snapshot["newly_monitored"]))
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Generate non-live snapshot without data fetch")
    parser.add_argument("--root", type=Path, default=BASE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    outcome = run(root=args.root, offline=args.offline)
    print(json.dumps({k: outcome[k] for k in
                      ("monitor_count", "pending_count", "archived_count", "newly_monitored", "new_pending")}, indent=2))


if __name__ == "__main__":
    main()
