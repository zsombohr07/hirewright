"""Fetchers: the "rent the fetch" half of the tool.

SampleFetcher gives a zero-setup offline demo. ApifyStepStoneFetcher delegates
the hard part — getting past StepStone's bot protection — to a managed Apify
actor, running one targeted search per WATCHLIST COMPANY (account-based motion):
you supply the company names, it finds those companies' current ads. We
deliberately implement NO bot-evasion here (no proxies, no CAPTCHA solving, no
stealth browser).

Adding Indeed.de later is just one more Fetcher subclass.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from .core import JobPosting, company_matches
from .targets import (
    classify_category,
    is_staffing_agency,
    detect_urgency,
)


class Fetcher:
    """Base fetcher. Subclasses return a list of classified JobPosting objects."""

    def fetch(self, query: Optional[str] = None, limit: int = 100) -> List[JobPosting]:
        raise NotImplementedError


def _classify(posting: JobPosting, fallback_category: Optional[str] = None) -> JobPosting:
    """Run enrich + Hirewright classifiers on a posting. Returns it."""
    posting.enrich()
    posting.category = classify_category(posting.title) or (fallback_category or "")
    posting.is_agency = is_staffing_agency(posting.company)
    posting.urgency = detect_urgency(posting.title, posting.description)
    return posting


# ---------------------------------------------------------------------------
# Offline sample data — proves the whole pipeline with zero setup.
# ---------------------------------------------------------------------------

def _days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


# Each row: company, title, url, location, salary, posted, description, first_seen_days
_SAMPLE_ROWS = [
    # (a) Direct employer, big volume, weeks open, urgent -> should TOP the list.
    (
        "Autowerk Niedersachsen GmbH",
        "20 Produktionshelfer (m/w/d)",
        "https://www.stepstone.de/job/autowerk-produktionshelfer-hannover-1",
        "Hannover",
        "13,50 - 15,00 EUR/Std.",
        "vor 6 Wochen",
        "Für unsere Fahrzeugmontage in Hannover suchen wir ab sofort "
        "Produktionshelfer. Insgesamt 20 offene Stellen im Zwei-Schicht-Betrieb "
        "zu besetzen.",
        45,
    ),
    # (b) Direct employer, same skilled role reposted across 4 cities, long open.
    (
        "Stahlbau Becker GmbH",
        "Schweißer WIG (m/w/d)",
        "https://www.stepstone.de/job/becker-schweisser-wig-bremen-10",
        "Bremen",
        "",
        "vor 9 Wochen",
        "Erfahrene WIG-Schweißer für unseren Stahlbau gesucht.",
        70,
    ),
    (
        "Stahlbau Becker GmbH",
        "Schweißer WIG (w/m/d)",
        "https://www.stepstone.de/job/becker-schweisser-wig-hamburg-11",
        "Hamburg",
        "",
        "vor 8 Wochen",
        "WIG-Schweißer für Baustahl- und Anlagenbauprojekte.",
        62,
    ),
    (
        "Stahlbau Becker GmbH",
        "Schweißer WIG (m/w/d)",
        "https://www.stepstone.de/job/becker-schweisser-wig-kiel-12",
        "Kiel",
        "",
        "vor 7 Wochen",
        "Wir erweitern unser Schweißteam am Standort Kiel.",
        55,
    ),
    (
        "Stahlbau Becker GmbH",
        "Schweißer WIG (all genders)",
        "https://www.stepstone.de/job/becker-schweisser-wig-rostock-13",
        "Rostock",
        "",
        "vor 6 Wochen",
        "WIG-Schweißer für den Schiffs- und Anlagenbau.",
        48,
    ),
    # (c) Staffing COMPETITOR -> must go to COMPETITOR WATCH, not leads.
    (
        "RegioPersonal Zeitarbeit GmbH",
        "Staplerfahrer (m/w/d)",
        "https://www.stepstone.de/job/regiopersonal-staplerfahrer-koeln-20",
        "Köln",
        "",
        "vor 3 Tagen",
        "Für unseren Kunden in Köln suchen wir Staplerfahrer in Arbeitnehmer"
        "überlassung.",
        5,
    ),
    # (d) Out-of-ICP role -> must be dropped entirely.
    (
        "Webagentur Pixelwerk GmbH",
        "Marketing Manager (m/w/d)",
        "https://www.stepstone.de/job/pixelwerk-marketing-manager-berlin-30",
        "Berlin",
        "55.000 - 65.000 EUR",
        "vor 1 Woche",
        "Du verantwortest unsere Online-Marketing-Kampagnen.",
        8,
    ),
    # (e) DECOY: "über 500 Mitarbeitern" must NOT be read as headcount.
    (
        "Maschinenbau Weber GmbH & Co. KG",
        "Industriemechaniker (m/w/d)",
        "https://www.stepstone.de/job/weber-industriemechaniker-stuttgart-40",
        "Stuttgart",
        "",
        "vor 10 Tagen",
        "Als ein Unternehmen mit über 500 Mitarbeitern bieten wir Ihnen einen "
        "sicheren Arbeitsplatz in der Instandhaltung.",
        10,
    ),
    # Filler direct employers for a realistic spread.
    (
        "Rheinhafen Logistik GmbH",
        "Kommissionierer (m/w/d)",
        "https://www.stepstone.de/job/rheinhafen-kommissionierer-duisburg-50",
        "Duisburg",
        "",
        "vor 3 Wochen",
        "Zur Verstärkung unseres Lagers besetzen wir mehrere Stellen in der "
        "Kommissionierung.",
        20,
    ),
    (
        "Elektro Sauer GmbH",
        "Elektroinstallateur (m/w/d)",
        "https://www.stepstone.de/job/sauer-elektroinstallateur-dortmund-60",
        "Dortmund",
        "",
        "vor 5 Wochen",
        "Installation und Wartung elektrotechnischer Anlagen im Industrieumfeld.",
        35,
    ),
    (
        "Schiffswerft Nord GmbH",
        "Rohrleitungsbauer (m/w/d)",
        "https://www.stepstone.de/job/werftnord-rohrleitungsbauer-rostock-70",
        "Rostock",
        "",
        "vor 7 Wochen",
        "Dringend gesucht: Rohrleitungsbauer für den Schiffbau, "
        "schnellstmöglicher Einstieg.",
        50,
    ),
    (
        "CleanTec Service GmbH",
        "Industriereiniger (m/w/d)",
        "https://www.stepstone.de/job/cleantec-industriereiniger-frankfurt-80",
        "Frankfurt",
        "",
        "vor 5 Tagen",
        "Unterhalts- und Industriereinigung von Produktionshallen.",
        5,
    ),
    # Second staffing competitor (different marker) for the watch list.
    (
        "Tempton Personal GmbH",
        "Lagerhelfer (m/w/d)",
        "https://www.stepstone.de/job/tempton-lagerhelfer-leipzig-90",
        "Leipzig",
        "",
        "vor 4 Tagen",
        "Für unseren Kunden suchen wir Lagerhelfer ab sofort.",
        6,
    ),
]


class SampleFetcher(Fetcher):
    """Realistic offline StepStone-style postings. No network, zero setup.

    With a `companies` watchlist it returns only matching rows (the same
    account-based motion as the live fetcher); with none it returns all rows so
    `python3 run.py` is still a full end-to-end demo.
    """

    def __init__(
        self, companies: Optional[List[str]] = None, source: str = "stepstone"
    ):
        self.companies = companies or []
        self.source = source

    def fetch(self, query: Optional[str] = None, limit: int = 100) -> List[JobPosting]:
        out: List[JobPosting] = []
        for row in _SAMPLE_ROWS[:limit]:
            company, title, url, location, salary, posted, desc, fs_days = row
            if self.companies and not any(
                company_matches(c, company) for c in self.companies
            ):
                continue
            p = JobPosting(
                company=company,
                title=title,
                source_url=url,
                source=self.source,
                location=location,
                salary=salary,
                posted_date=posted,
                description=desc,
            )
            p.first_seen = _days_ago(fs_days)
            out.append(_classify(p))
        return out


# ---------------------------------------------------------------------------
# Apify — managed StepStone actor. We rent the fetch.
# ---------------------------------------------------------------------------

_APIFY_URL = (
    "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
)

# Per-request read timeout (seconds). run-sync waits for the scrape to finish, so
# this needs headroom for a slow company; a failure here just skips that company.
_REQUEST_TIMEOUT = 300


def _first(item: dict, *keys):
    """Tolerant field lookup: return the first present, non-empty alias."""
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return ""


def _post_actor(actor: str, token: str, body: dict) -> list:
    """POST a run-sync request to an Apify actor and return its dataset items.

    Shared by every Apify fetcher — only the request body differs per actor.
    """
    data = json.dumps(body).encode("utf-8")
    url = _APIFY_URL.format(actor=actor, token=token)
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            f"Apify request failed ({e.code}). Check the actor id and your "
            f"token/plan. Response: {detail}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Apify: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise RuntimeError(f"Apify request timed out after {_REQUEST_TIMEOUT}s") from e

    items = json.loads(payload)
    if isinstance(items, dict):  # some actors wrap results
        items = items.get("items", items.get("data", []))
    return items


# Default actor — easyapi's StepStone scraper (well-documented, ~$3/1k results).
# Override with APIFY_ACTOR if you pick a different one; you may then need to
# adjust _company_search_url / _map_items to match its URL + output shape.
_DEFAULT_ACTOR = "easyapi~stepstone-jobs-scraper"


def _company_search_url(company: str) -> str:
    """Build a StepStone DE keyword-search URL for one watchlist company.

    The `?searchOrigin=` param is REQUIRED: without it StepStone redirects a bare
    `/jobs/<name>` to the company *profile* page and the actor returns nothing.
    Tuned for the easyapi actor; a different actor may want another URL shape.
    """
    what = urllib.parse.quote_plus(company)
    return f"https://www.stepstone.de/jobs/{what}?searchOrigin=Homepage_top-search"


class ApifyStepStoneFetcher(Fetcher):
    """Fetch StepStone listings via a managed Apify actor.

    Set APIFY_TOKEN and APIFY_ACTOR in the environment (or pass them in). It runs
    ONE targeted search per watchlist company, then verifies each returned ad
    really belongs to that company (free-text search is fuzzy). The actor handles
    bot protection; we just map its JSON to JobPosting and classify it — only
    staffable blue-collar roles survive the downstream rollup.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        actor: Optional[str] = None,
        companies: Optional[List[str]] = None,
    ):
        self.token = token or os.environ.get("APIFY_TOKEN")
        self.actor = actor or os.environ.get("APIFY_ACTOR") or _DEFAULT_ACTOR
        self.companies = companies or []
        if not self.token:
            raise RuntimeError(
                "Apify fetcher needs APIFY_TOKEN. Set it as an environment "
                "variable (or pass token=), or use --fetcher sample for the "
                "offline demo.\n"
                "  export APIFY_TOKEN=apify_api_xxx\n"
                f"  export APIFY_ACTOR=<actor-id>   # optional, defaults to {_DEFAULT_ACTOR}"
            )

    def _run_actor(self, search_url: str, limit: int) -> list:
        # easyapi shape: searchUrls (list of plain URLs), maxItems (min 30), and
        # an Apify proxy — without the proxy StepStone blocks the actor (empty
        # results). maxItems is the per-search cap and what you're billed on.
        return _post_actor(
            self.actor,
            self.token,
            {
                "searchUrls": [search_url],
                "maxItems": max(limit, 30),
                "proxyConfiguration": {"useApifyProxy": True},
            },
        )

    def _map_items(self, items, fallback_category) -> List[JobPosting]:
        out: List[JobPosting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            company = _first(item, "company", "companyName", "employer")
            title = _first(item, "title", "jobTitle", "positionName")
            source_url = _first(item, "url", "jobUrl", "link")
            if not company or not title or not source_url:
                continue  # skip incomplete items
            source_url = str(source_url)
            if source_url.startswith("/"):  # easyapi returns relative job URLs
                source_url = "https://www.stepstone.de" + source_url
            p = JobPosting(
                company=str(company),
                title=str(title),
                source_url=source_url,
                source="stepstone",
                location=str(_first(item, "location", "city")),
                salary=str(_first(item, "salary", "salaryText")),
                posted_date=_first(item, "postedAt", "datePosted", "publishedAt", "date"),
                description=str(
                    _first(
                        item, "description", "jobDescription", "descriptionText",
                        "textSnippet",
                    )
                ),
            )
            out.append(_classify(p, fallback_category=fallback_category))
        return out

    def fetch(self, query: Optional[str] = None, limit: int = 100) -> List[JobPosting]:
        # One explicit search if a query is given (advanced escape hatch);
        # otherwise one search per watchlist company.
        if query:
            return self._map_items(self._run_actor(query, limit), None)

        if not self.companies:
            raise RuntimeError(
                "Company-watchlist mode needs a company list. Pass "
                "--companies <file> (one company name per line), or --query "
                "<StepStone search URL> for a single explicit search."
            )

        seen_urls = set()
        out: List[JobPosting] = []
        total = len(self.companies)
        for i, company in enumerate(self.companies, 1):
            # Live progress so a multi-minute run never looks frozen.
            print(f"  [{i}/{total}] searching {company}…", file=sys.stderr, flush=True)
            url = _company_search_url(company)
            try:
                items = self._run_actor(url, limit)
            except RuntimeError as e:
                # One company failing (timeout, actor hiccup) must not sink the
                # whole batch — skip it and keep going.
                print(f"      ↳ skipped: {e}", file=sys.stderr, flush=True)
                continue
            kept = 0
            for p in self._map_items(items, fallback_category=None):
                # Verify the ad really is this company (free-text search noise).
                if not company_matches(company, p.company):
                    continue
                if p.source_url in seen_urls:
                    continue
                seen_urls.add(p.source_url)
                out.append(p)
                kept += 1
            print(
                f"      ↳ {len(items)} ad(s) found, {kept} matched {company}",
                file=sys.stderr,
                flush=True,
            )
        return out


# ---------------------------------------------------------------------------
# Apify — managed Indeed.de actor. Same "rent the fetch" pattern as StepStone.
# ---------------------------------------------------------------------------

# Default actor — easyapi's Indeed scraper (same vendor as the StepStone one,
# ~$3/1k results). Override with APIFY_INDEED_ACTOR so it can coexist with the
# StepStone APIFY_ACTOR. A different actor may need another body / output shape.
_DEFAULT_INDEED_ACTOR = "easyapi~indeed-jobs-scraper"


def _ts_to_date(value) -> Optional[date]:
    """Unix timestamp (seconds or milliseconds) -> date. None if unparseable."""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts > 1e12:  # value is in milliseconds
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def _indeed_search_url(company: str) -> str:
    """Indeed.de keyword search for one watchlist company.

    `sort=date` returns newest-first and `fromage=14` caps results to the last
    14 days, so each company's pull is small and we get the freshest ads.
    """
    what = urllib.parse.quote_plus(company)
    return f"https://de.indeed.com/jobs?q={what}&sort=date&fromage=14"


class ApifyIndeedFetcher(Fetcher):
    """Fetch Indeed.de listings via a managed Apify actor.

    Mirrors ApifyStepStoneFetcher: one targeted search per watchlist company,
    then verifies each returned ad really belongs to that company (free-text
    search is fuzzy). Set APIFY_TOKEN (and optionally APIFY_INDEED_ACTOR).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        actor: Optional[str] = None,
        companies: Optional[List[str]] = None,
    ):
        self.token = token or os.environ.get("APIFY_TOKEN")
        self.actor = (
            actor or os.environ.get("APIFY_INDEED_ACTOR") or _DEFAULT_INDEED_ACTOR
        )
        self.companies = companies or []
        if not self.token:
            raise RuntimeError(
                "Apify fetcher needs APIFY_TOKEN. Set it as an environment "
                "variable (or pass token=), or use --fetcher sample-indeed for "
                "the offline demo.\n"
                "  export APIFY_TOKEN=apify_api_xxx\n"
                f"  export APIFY_INDEED_ACTOR=<actor-id>   # optional, defaults "
                f"to {_DEFAULT_INDEED_ACTOR}"
            )

    def _run_actor(self, search_url: str, limit: int) -> list:
        # easyapi Indeed shape: searchUrl (singular, unlike StepStone's
        # searchUrls), maxItems (per-search cap / billing). sort=date means even
        # a small cap surfaces the newest ad. Proxy is included defensively.
        return _post_actor(
            self.actor,
            self.token,
            {
                "searchUrl": search_url,
                "maxItems": max(limit, 20),
                "proxyConfiguration": {"useApifyProxy": True},
            },
        )

    def _map_items(self, items, fallback_category) -> List[JobPosting]:
        out: List[JobPosting] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            company = _first(item, "company", "companyName", "employer")
            title = _first(item, "title", "jobTitle", "positionName")
            source_url = _first(item, "jobUrl", "url", "link")
            if not company or not title or not source_url:
                continue  # skip incomplete items
            source_url = str(source_url)
            if source_url.startswith("/"):
                source_url = "https://de.indeed.com" + source_url
            # salary is a nested object {min,max,type,text} on the easyapi actor.
            sal = item.get("salary")
            salary = str(sal.get("text") or "") if isinstance(sal, dict) else str(sal or "")
            # Prefer a real timestamp for the date; fall back to the textual one.
            pub = _ts_to_date(_first(item, "publishTimestamp", "createTimestamp"))
            posted = (
                pub.isoformat()
                if pub
                else str(_first(item, "postDate", "datePosted", "date"))
            )
            p = JobPosting(
                company=str(company),
                title=str(title),
                source_url=source_url,
                source="indeed",
                location=str(_first(item, "location", "city")),
                salary=salary,
                posted_date=posted,
                description=str(
                    _first(item, "snippet", "description", "jobDescription")
                ),
            )
            _classify(p, fallback_category=fallback_category)
            # Indeed bypasses the SQLite store, so seed first_seen from the ad's
            # publish date — scoring's days_open()/persistence read first_seen.
            if isinstance(p.posted_date, date):
                p.first_seen = p.posted_date
            elif pub:
                p.first_seen = pub
            out.append(p)
        return out

    def fetch(self, query: Optional[str] = None, limit: int = 100) -> List[JobPosting]:
        # One explicit search if a query is given (advanced escape hatch);
        # otherwise one search per watchlist company.
        if query:
            return self._map_items(self._run_actor(query, limit), None)

        if not self.companies:
            raise RuntimeError(
                "Company-watchlist mode needs a company list. Pass "
                "--companies <file> (one company name per line), or --query "
                "<Indeed search URL> for a single explicit search."
            )

        seen_urls = set()
        out: List[JobPosting] = []
        total = len(self.companies)
        for i, company in enumerate(self.companies, 1):
            print(f"  [{i}/{total}] searching {company}…", file=sys.stderr, flush=True)
            url = _indeed_search_url(company)
            try:
                items = self._run_actor(url, limit)
            except RuntimeError as e:
                print(f"      ↳ skipped: {e}", file=sys.stderr, flush=True)
                continue
            kept = 0
            for p in self._map_items(items, fallback_category=None):
                if not company_matches(company, p.company):
                    continue
                if p.source_url in seen_urls:
                    continue
                seen_urls.add(p.source_url)
                out.append(p)
                kept += 1
            print(
                f"      ↳ {len(items)} ad(s) found, {kept} matched {company}",
                file=sys.stderr,
                flush=True,
            )
        return out
