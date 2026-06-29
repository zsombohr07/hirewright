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
    CATEGORIES,
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


# ---------------------------------------------------------------------------
# Claude research — let the model find each company's live openings.
#
# Same account-based motion as the Apify fetchers (one search per watchlist
# company), but instead of renting a board scraper we ask Claude to research the
# company directly: its OWN careers page / ATS first, then the open web. This
# fixes the three ways the board scrapers silently lose companies:
#   * coverage — most of these industrial firms post on their own site, not a
#     board, and only the last 14 days are visible on Indeed;
#   * name matching — the model recognises "Panasonic Automotive Systems Europe
#     GmbH" on its careers page even when an ad just says "Panasonic";
#   * classification — the model judges role fit against Hirewright's six
#     categories instead of a ~60-word keyword whitelist.
# Downstream (rollup → scoring → CSV) is untouched: we hand back JobPostings
# whose .category is already one of the six (or "" = out of scope), exactly what
# rollup_company_leads expects.
# ---------------------------------------------------------------------------

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
# Web research + reading a few pages can be slow; give it headroom. A timeout
# just skips that one company (recorded in the diagnostic), never the batch.
_CLAUDE_TIMEOUT = 240
# Sonnet is the cost/quality sweet spot for this fan-out; override per run.
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def _extract_json_obj(text: str):
    """Return the LAST balanced top-level JSON object in `text`, or None.

    The model is told to end with one JSON object, but web-search runs can leave
    prose around it. Scans brace depth (string-aware) and json.loads the last
    complete {...}.
    """
    candidates = []
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start : i + 1])
                    start = None
    for cand in reversed(candidates):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


def _category_guidance() -> str:
    """Bullet list of the six categories + sample German titles, for the prompt."""
    lines = []
    for cat, cfg in CATEGORIES.items():
        sample = ", ".join(cfg["keywords"][:8])
        lines.append(f'  - "{cat}" (~{cfg["rate"]}): e.g. {sample}')
    return "\n".join(lines)


def _classify_claude(posting: JobPosting, category: str) -> JobPosting:
    """Like _classify, but trust the model's category instead of the keyword list.

    The keyword whitelist is exactly what we're replacing, so we set the category
    from the model (already validated to one of the six, or "" for out-of-scope)
    and still reuse the cheap deterministic enrichers for everything else.
    """
    posting.enrich()
    posting.category = category
    posting.is_agency = is_staffing_agency(posting.company)
    posting.urgency = posting.urgency or detect_urgency(
        posting.title, posting.description
    )
    # Indeed/StepStone seed first_seen from storage; Claude has no store, so seed
    # it from the ad's own posted date (scoring's days_open reads first_seen).
    if isinstance(posting.posted_date, date):
        posting.first_seen = posting.posted_date
    return posting


class ClaudeResearchFetcher(Fetcher):
    """Research each watchlist company's live openings via Claude + web search.

    One Anthropic Messages call per company, with the server-side web_search
    tool. The model returns a JSON object of current German openings, each tagged
    to a Hirewright category and backed by a source URL; we turn the staffable
    ones into JobPostings. Per-company diagnostics (careers page found, roles
    seen, why-empty) are collected on `self.diagnostics` for the caller to dump.

    Needs ANTHROPIC_API_KEY (metered API billing, separate from a Claude Code
    subscription). Override the model with CLAUDE_RESEARCH_MODEL.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        companies: Optional[List[str]] = None,
    ):
        self.token = token or os.environ.get("ANTHROPIC_API_KEY")
        self.model = (
            model or os.environ.get("CLAUDE_RESEARCH_MODEL") or _DEFAULT_CLAUDE_MODEL
        )
        self.companies = companies or []
        self.diagnostics: List[dict] = []
        if not self.token:
            raise RuntimeError(
                "Claude research fetcher needs ANTHROPIC_API_KEY. Set it as an "
                "environment variable (metered API billing, separate from your "
                "Claude Code subscription).\n"
                "  export ANTHROPIC_API_KEY=sk-ant-…\n"
                f"  export CLAUDE_RESEARCH_MODEL=<model-id>   # optional, defaults "
                f"to {_DEFAULT_CLAUDE_MODEL}"
            )

    _SYSTEM = (
        "You are a sourcing researcher for Hirewright, an industrial "
        "labour-leasing firm that leases blue-collar crews to employers in "
        "GERMANY. For one named company you find its CURRENT open job postings "
        "and report only the blue-collar roles Hirewright could staff.\n\n"
        "Method, in order:\n"
        "1. Find the company's official careers/jobs page (also check its ATS: "
        "softgarden, Personio, Workday, SuccessFactors, Greenhouse, etc.).\n"
        "2. Read its currently open positions located in Germany.\n"
        "3. Cross-check the open web (Google Jobs, Indeed, StepStone, LinkedIn) "
        "for the same company to catch roles the site hides behind JavaScript.\n\n"
        "Classify every blue-collar opening into exactly one Hirewright category "
        "(use the German title to judge — synonyms count, you are NOT limited to "
        "the example words):\n"
        "%(cats)s\n"
        "Anything office/white-collar/engineering/management, or any role you "
        'cannot tie to a live posting URL, is "out_of_scope".\n\n'
        "Hard rules:\n"
        "- Only report a role if you have a real, current source URL for it. If "
        "you cannot verify it, leave it out. Never invent postings or URLs.\n"
        "- Germany-based roles only.\n"
        "- Output ONE JSON object as the LAST thing in your reply, no prose "
        "after it, matching exactly:\n"
        "{\n"
        '  "company": str,\n'
        '  "careers_url": str|null,\n'
        '  "roles": [\n'
        '    {"title": str, "category": "<one of the six names above>|out_of_scope", '
        '"location": str, "url": str, "count": int, '
        '"posted_date": "YYYY-MM-DD"|null, "urgent": bool}\n'
        "  ],\n"
        '  "empty_reason": str|null   // if no staffable roles: why — e.g. '
        '"no careers page found", "hiring only office roles", "not hiring", '
        '"could not verify"\n'
        "}"
    )

    def _system_prompt(self) -> str:
        return self._SYSTEM % {"cats": _category_guidance()}

    def _post(self, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            _ANTHROPIC_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.token,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_CLAUDE_TIMEOUT) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(
                f"Anthropic request failed ({e.code}). Check ANTHROPIC_API_KEY "
                f"and your plan. Response: {detail}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach Anthropic: {e.reason}") from e
        except (TimeoutError, socket.timeout) as e:
            raise RuntimeError(
                f"Anthropic request timed out after {_CLAUDE_TIMEOUT}s"
            ) from e
        return json.loads(payload)

    def _research(self, company: str) -> dict:
        """Call Claude for one company; return the parsed JSON dict (raises on error)."""
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": self._system_prompt(),
            "tools": [
                {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Company: {company}\n"
                        "Research this company's current open positions in Germany "
                        "and report the staffable blue-collar roles as specified."
                    ),
                }
            ],
        }
        resp = self._post(body)
        text = "".join(
            b.get("text", "")
            for b in resp.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        )
        obj = _extract_json_obj(text)
        if obj is None:
            raise RuntimeError("model returned no parseable JSON")
        return obj

    def _postings_from(self, company: str, obj: dict) -> List[JobPosting]:
        """Turn one company's research JSON into staffable JobPostings (+diagnostic)."""
        valid = set(CATEGORIES.keys())
        roles = obj.get("roles") or []
        out: List[JobPosting] = []
        n_staffable = 0
        cats_seen = set()
        for role in roles:
            if not isinstance(role, dict):
                continue
            cat = role.get("category") or ""
            cat = cat if cat in valid else ""  # out_of_scope / unknown -> dropped
            url = (role.get("url") or "").strip()
            title = (role.get("title") or "").strip()
            if not cat or not url or not title:
                continue  # not staffable, or unverifiable (no URL) -> skip
            cats_seen.add(cat)
            n_staffable += 1
            count = role.get("count")
            p = JobPosting(
                company=company,
                title=title,
                source_url=url,
                source="claude",
                location=str(role.get("location") or ""),
                posted_date=role.get("posted_date") or None,
                description="",
            )
            p.urgency = bool(role.get("urgent"))
            _classify_claude(p, cat)
            if isinstance(count, int) and count > 0:
                p.headcount = count  # model's stated openings -> total_headcount
            out.append(p)
        self.diagnostics.append(
            {
                "company": company,
                "careers_url": obj.get("careers_url") or "",
                "roles_seen": len(roles),
                "staffable_roles": n_staffable,
                "categories": "; ".join(sorted(cats_seen)),
                "empty_reason": "" if n_staffable else (obj.get("empty_reason") or ""),
                "error": "",
            }
        )
        return out

    def fetch(self, query: Optional[str] = None, limit: int = 100) -> List[JobPosting]:
        if not self.companies:
            raise RuntimeError(
                "Claude research needs a company list (one company per row in the "
                "contact CSV)."
            )
        out: List[JobPosting] = []
        total = len(self.companies)
        for i, company in enumerate(self.companies, 1):
            print(f"  [{i}/{total}] researching {company}…", file=sys.stderr, flush=True)
            try:
                obj = self._research(company)
            except RuntimeError as e:
                # One company failing must not sink the batch — log + record it.
                print(f"      ↳ skipped: {e}", file=sys.stderr, flush=True)
                self.diagnostics.append(
                    {
                        "company": company,
                        "careers_url": "",
                        "roles_seen": 0,
                        "staffable_roles": 0,
                        "categories": "",
                        "empty_reason": "",
                        "error": str(e)[:200],
                    }
                )
                continue
            postings = self._postings_from(company, obj)
            out.extend(postings)
            print(
                f"      ↳ {len(obj.get('roles') or [])} role(s) seen, "
                f"{len(postings)} staffable",
                file=sys.stderr,
                flush=True,
            )
        return out
