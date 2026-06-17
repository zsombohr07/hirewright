"""Core domain logic: data model, normalization, headcount, scaling, dates.

This is the "own the brain" half of the tool — turning raw listings into signal.
It has no third-party dependencies and touches no network.

Scope guardrail: only company + job-ad fields live here. No personal data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# German gender / inclusivity tags that pad titles and company names.
# Matched with surrounding brackets optional, case-insensitive.
_GENDER_TAG_RE = re.compile(
    r"""
    \(?\s*                      # optional opening paren
    (?:
        # m/w/d, w/m/d, m/w/d/x, and the common "div"/"divers" final segment
        # (e.g. w/m/div., m/w/divers). At least one separator required so a bare
        # single letter is never stripped.
        [mwdfx](?:\s*[/|]\s*(?:div(?:ers)?|[mwdfx]))+
        |
        all\s+genders
        |
        divers
        |
        gn                      # "gn" = geschlechtsneutral
    )
    \s*\.?\s*\)?                 # optional trailing dot (div.) + closing paren
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Company-form suffixes. Longest forms first so "GmbH & Co. KG" strips before
# "GmbH". Each entry is matched as a trailing token (optionally comma-separated).
_COMPANY_SUFFIXES = [
    "gmbh & co. kg",
    "gmbh & co kg",
    "gmbh und co. kg",
    "ag & co. kg",
    "se & co. kg",
    "gmbh",
    "mbh",
    "ag",
    "se",
    "kgaa",
    "kg",
    "ohg",
    "ug (haftungsbeschränkt)",
    "ug",
    "ev",
    "e.v.",
    "ltd.",
    "ltd",
    "limited",
    "inc.",
    "inc",
    "llc",
    "plc",
    "co.",
    "co",
]

# Build one regex that anchors any suffix at the end of the string, allowing a
# leading separator (space / comma). Escaped + sorted longest-first.
_SUFFIX_RE = re.compile(
    r"(?:[\s,]+(?:" + "|".join(re.escape(s) for s in _COMPANY_SUFFIXES) + r"))+\s*$",
    re.IGNORECASE,
)

_PUNCT_RE = re.compile(r"[^\w\s&+/-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _collapse(text: str) -> str:
    """Lowercase, strip stray punctuation, collapse whitespace."""
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def normalize_company(company: str) -> str:
    """Normalize a company name so the same employer groups across listings.

    Strips gender tags and legal-form suffixes, then collapses noise.
    """
    if not company:
        return ""
    text = _GENDER_TAG_RE.sub(" ", company)
    # Strip suffixes repeatedly (handles e.g. trailing ", Inc" then "Ltd").
    prev = None
    while prev != text:
        prev = text
        text = _SUFFIX_RE.sub("", text)
    return _collapse(text)


def normalize_title(title: str) -> str:
    """Normalize a job title so the same role groups across listings."""
    if not title:
        return ""
    text = _GENDER_TAG_RE.sub(" ", title)
    return _collapse(text)


def company_matches(target: str, candidate: str) -> bool:
    """True if a job ad's company (candidate) is the watchlist company (target).

    Both names are run through normalize_company (legal suffixes + gender tags
    stripped, noise collapsed), then matched as a token-subset: every word of the
    target must appear in the candidate. So "BMW" matches "BMW AG" / "BMW Group",
    and "Stahlbau Becker" matches "Stahlbau Becker GmbH", while an unrelated firm
    is rejected. Deliberately lenient — StepStone free-text search is fuzzy and we
    would rather keep a near-match than silently drop a real one.
    """
    t = normalize_company(target)
    c = normalize_company(candidate)
    if not t or not c:
        return False
    if t == c:
        return True
    return set(t.split()).issubset(set(c.split()))


# ---------------------------------------------------------------------------
# Headcount — deliberately conservative
# ---------------------------------------------------------------------------

# Words that genuinely indicate a number of *openings*. "Mitarbeiter" and
# friends are intentionally absent: German ads use those for company size.
_OPENING_WORDS = [
    "stellenangebote",
    "stellen",
    "positionen",
    "vakanzen",
    "openings",
    "positions",
    "roles",
    "vacancies",
]

# A digit adjacent (within ~1-2 tokens, either order) to an opening word.
_OPENING_NUM_RE = re.compile(
    r"""
    (?:
        (\d{1,3})\s+(?:\w+\s+){0,1}(?:%(words)s)   # "3 offene Stellen"
        |
        (?:%(words)s)\s+(?:\w+\s+){0,1}(\d{1,3})   # "Stellen: 3" / "positions (3)"
    )
    """
    % {"words": "|".join(_OPENING_WORDS)},
    re.IGNORECASE | re.VERBOSE,
)

# "Multiple openings" language with no explicit number.
_MULTIPLE_RE = re.compile(
    r"\b(mehrere|multiple|diverse|verschiedene|zahlreiche)\b", re.IGNORECASE
)

HEADCOUNT_CAP = 200


def parse_headcount(title: str, description: str) -> Tuple[Optional[int], str]:
    """Best-effort openings count from ad text. CONSERVATIVE by design.

    Returns (count, basis):
      - ("explicit")        a number sat right next to an opening-word; capped
                            at HEADCOUNT_CAP (above that = company size, not jobs).
      - (None, "multiple")  language like "mehrere Stellen" but no number.
      - (1, "single_assumed") default: one ad = one opening.

    Never reads "X Mitarbeiter" as openings — that is company size.
    """
    blob = " ".join(p for p in (title, description) if p)

    best: Optional[int] = None
    for m in _OPENING_NUM_RE.finditer(blob):
        num = m.group(1) or m.group(2)
        if num is None:
            continue
        val = int(num)
        if val <= 0 or val > HEADCOUNT_CAP:
            continue  # implausible as an openings count
        if best is None or val > best:
            best = val
    if best is not None:
        return best, "explicit"

    if _MULTIPLE_RE.search(blob):
        return None, "multiple"

    return 1, "single_assumed"


# ---------------------------------------------------------------------------
# Posted-date parsing
# ---------------------------------------------------------------------------

_DDMMYYYY_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_REL_RE = re.compile(
    r"vor\s+(\d+|einem|einer|eine|ein)\s+(tag|tage|tagen|woche|wochen)",
    re.IGNORECASE,
)


def parse_posted_date(value, today: Optional[date] = None) -> Optional[date]:
    """Parse ISO, dd.mm.yyyy, or German relative phrases into a date.

    Handles: "2026-06-01", "2026-06-01T09:00:00Z", "01.06.2026", "heute",
    "gestern", "vor 3 Tagen", "vor 2 Wochen", "vor einer Woche".
    Returns None if unparseable.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None

    today = today or date.today()
    low = s.lower()

    if low == "heute":
        return today
    if low == "gestern":
        return today - timedelta(days=1)
    if low in ("vorgestern",):
        return today - timedelta(days=2)

    m = _REL_RE.search(low)
    if m:
        word = m.group(1)
        n = 1 if word in ("einem", "einer", "eine", "ein") else int(word)
        unit = m.group(2)
        days = n * 7 if unit.startswith("woche") else n
        return today - timedelta(days=days)

    m = _ISO_RE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    m = _DDMMYYYY_RE.match(s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None

    return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class JobPosting:
    """A single public job ad. Company + job-ad data only — no personal data."""

    company: str
    title: str
    source_url: str  # UNIQUE — the dedup key
    source: str = "stepstone"
    location: str = ""
    salary: str = ""
    posted_date: Optional[date] = None
    description: str = ""

    # Derived (filled by enrich()).
    company_norm: str = ""
    title_norm: str = ""
    title_en: str = ""          # English translation of the job title
    headcount: Optional[int] = None
    headcount_basis: str = ""

    # V2 lead-engine fields (set by classifiers / storage, not enrich()).
    category: str = ""          # Hirewright service category, or "" if out of ICP
    is_agency: bool = False     # True = a competing staffing firm, not a prospect
    urgency: bool = False       # ad uses "ab sofort"/"dringend"/etc.
    status: str = "new"         # lead workflow state; survives re-runs
    first_seen: Optional[date] = None  # when we first saw this ad (from storage)
    last_seen: Optional[date] = None   # most recent sighting (from storage)
    repost_count: int = 1       # times this company+role appears (set at report time)

    def enrich(self) -> "JobPosting":
        """Populate derived fields from the raw ones. Returns self."""
        from .translate import translate_title  # lazy: avoids import cycle

        self.company_norm = normalize_company(self.company)
        self.title_norm = normalize_title(self.title)
        self.title_en = translate_title(self.title)
        if isinstance(self.posted_date, str):
            self.posted_date = parse_posted_date(self.posted_date)
        self.headcount, self.headcount_basis = parse_headcount(
            self.title, self.description
        )
        return self
