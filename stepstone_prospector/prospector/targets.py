"""Hirewright business config + classifiers.

Everything about *who Hirewright sells to* lives here so it can be tuned in one
place: the six service categories and their role keywords, the markers that
identify a competing staffing firm, and the urgency vocabulary.

Hirewright leases skilled/semi-skilled CEE workers by the hour to German
industrial employers. A useful lead is a DIRECT EMPLOYER with a blue-collar gap
in one of these categories — not another agency.
"""

from __future__ import annotations

import re
from typing import Optional

from .core import normalize_title


# ---------------------------------------------------------------------------
# Hirewright's six service categories. Edit keywords/rates to tune targeting.
# ---------------------------------------------------------------------------

CATEGORIES = {
    "Skilled trades": {
        "rate": "€29/hr",
        "keywords": [
            "Schweißer", "WIG-Schweißer", "MAG-Schweißer", "Elektriker",
            "Elektroniker", "Elektroinstallateur", "Anlagenmechaniker SHK",
            "Lüftungstechniker", "Industriemechaniker", "Schlosser", "Monteur",
            "Zerspanungsmechaniker", "CNC-Fräser", "CNC-Dreher",
        ],
    },
    "Industrial specialists": {
        "rate": "€29/hr",
        "keywords": [
            "Sprinklermonteur", "Brandschutzmonteur", "Kalibriertechniker",
            "Monteur Sicherheitstechnik", "Sicherheitstechnik",
        ],
    },
    "Construction & finishing": {
        "rate": "€25/hr",
        "keywords": [
            "Maler", "Maler und Lackierer", "Rohrleitungsbauer", "Rohrleger",
            "Bauhelfer", "Trockenbauer",
        ],
    },
    "Semi-skilled production": {
        "rate": "€20/hr",
        "keywords": [
            "Produktionshelfer", "Produktionsmitarbeiter", "Montagemitarbeiter",
            "Maschinenbediener", "Maschinen- und Anlagenführer", "Verpacker",
        ],
    },
    "Logistics & warehouse": {
        "rate": "€20/hr",
        "keywords": [
            "Lagermitarbeiter", "Lagerhelfer", "Kommissionierer", "Staplerfahrer",
            "Gabelstaplerfahrer", "Kraftfahrer", "LKW-Fahrer", "Berufskraftfahrer",
        ],
    },
    "Cleaning & maintenance": {
        "rate": "€19/hr",
        "keywords": [
            "Reinigungskraft", "Gebäudereiniger", "Industriereiniger",
            "Unterhaltsreinigung",
        ],
    },
}

# A posting company is a COMPETITOR (another staffing firm), not a prospect, if
# its name contains any of these (case-insensitive). Seed list — easy to extend.
AGENCY_MARKERS = [
    "zeitarbeit", "personaldienstleist", "personalservice", "personalvermittlung",
    "arbeitnehmerüberlassung", "überlassung", "randstad", "adecco", "manpower",
    "tempton", "piening", "persona service", "trenkwalder", "orizon",
    "i.k. hofmann", "gis personal", "zag", "dekra arbeit", "start people",
    "unique personal", "jobimpulse", "aktief",
]

URGENCY_TERMS = [
    "ab sofort", "sofort", "dringend", "schnellstmöglich", "kurzfristig",
    "umgehend", "sofortiger",
]


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------

def _match_norm(text: str) -> str:
    """Normalize for keyword matching: lowercase, hyphens/slashes -> spaces.

    Keeps German umlauts/ß as word characters so \\b boundaries work on them.
    """
    text = normalize_title(text)          # lowercase, strip gender tags, collapse
    text = re.sub(r"[-/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Pre-compile a word-boundary pattern per (category, keyword).
_CATEGORY_PATTERNS = []
for _cat, _cfg in CATEGORIES.items():
    for _kw in _cfg["keywords"]:
        _kwn = _match_norm(_kw)
        _CATEGORY_PATTERNS.append(
            (_cat, _kwn, re.compile(r"\b" + re.escape(_kwn) + r"\b"))
        )


def classify_category(title: str) -> Optional[str]:
    """Map a job title to a Hirewright category, or None if out of ICP.

    Prefers the most specific match (longest keyword) so "Sprinklermonteur"
    classifies as an Industrial specialist, not the generic "Monteur".
    """
    if not title:
        return None
    hay = _match_norm(title)
    best_cat = None
    best_len = -1
    for cat, kwn, pat in _CATEGORY_PATTERNS:
        if pat.search(hay) and len(kwn) > best_len:
            best_cat, best_len = cat, len(kwn)
    return best_cat


def is_staffing_agency(company: str) -> bool:
    """True if the company name looks like a competing staffing firm."""
    if not company:
        return False
    low = company.lower()
    return any(marker in low for marker in AGENCY_MARKERS)


def detect_urgency(title: str, description: str) -> bool:
    """True if the ad signals it needs people fast."""
    blob = " ".join(p for p in (title, description) if p).lower()
    return any(term in blob for term in URGENCY_TERMS)


def category_rate(category: Optional[str]) -> str:
    """Indicative Hirewright rate for a category (or empty)."""
    if category and category in CATEGORIES:
        return CATEGORIES[category]["rate"]
    return ""
