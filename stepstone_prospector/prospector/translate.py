"""German -> English job-title translation, offline and dependency-free.

This stays true to the tool's "zero setup, standard-library only" design: rather
than calling a translation API (network + key + cost, and it would break offline
use), it leans on the fact that Hirewright's job-title vocabulary is *bounded* —
it's the same blue-collar role set the targeting already enumerates in
targets.py. A curated glossary covers that vocabulary plus the usual modifiers;
anything outside it is left untouched rather than guessed at.

Translation is deterministic, free, and runs on the existing normalization
machinery (gender tags like "(m/w/d)" are stripped first, as elsewhere).
"""

from __future__ import annotations

import re

from .core import _GENDER_TAG_RE


# ---------------------------------------------------------------------------
# Glossary. Keys are German source terms (case-insensitive), values English.
# Multi-word and compound forms are matched longest-first, so "Maler und
# Lackierer" wins over "Maler" and "WIG-Schweißer" wins over "Schweißer".
# Mirrors the role keywords in targets.py — keep the two in sync when tuning.
# ---------------------------------------------------------------------------

GLOSSARY = {
    # Skilled trades
    "WIG-Schweißer": "TIG Welder",
    "MAG-Schweißer": "MAG Welder",
    "MIG-Schweißer": "MIG Welder",
    "Schweißer": "Welder",
    "Elektroinstallateur": "Electrical Installer",
    "Elektroniker": "Electronics Technician",
    "Elektriker": "Electrician",
    "Anlagenmechaniker SHK": "HVAC & Plumbing Systems Mechanic",
    "Anlagenmechaniker": "Plant Mechanic",
    "Lüftungstechniker": "Ventilation Technician",
    "Industriemechaniker": "Industrial Mechanic",
    "Schlosser": "Metal Fitter",
    "Zerspanungsmechaniker": "CNC Machinist",
    "CNC-Fräser": "CNC Milling Machinist",
    "CNC-Dreher": "CNC Lathe Operator",
    "Fräser": "Milling Machinist",
    "Dreher": "Lathe Operator",
    "Monteur": "Fitter",
    # Industrial specialists
    "Sprinklermonteur": "Sprinkler Fitter",
    "Brandschutzmonteur": "Fire Protection Fitter",
    "Kalibriertechniker": "Calibration Technician",
    "Monteur Sicherheitstechnik": "Security Systems Fitter",
    "Sicherheitstechnik": "Security Systems",
    # Construction & finishing
    "Maler und Lackierer": "Painter & Varnisher",
    "Maler": "Painter",
    "Lackierer": "Varnisher",
    "Rohrleitungsbauer": "Pipeline Constructor",
    "Rohrleger": "Pipe Layer",
    "Bauhelfer": "Construction Helper",
    "Trockenbauer": "Drywall Installer",
    # Semi-skilled production
    "Produktionshelfer": "Production Helper",
    "Produktionsmitarbeiter": "Production Worker",
    "Montagemitarbeiter": "Assembly Worker",
    "Maschinen- und Anlagenführer": "Machine & Plant Operator",
    "Maschinenbediener": "Machine Operator",
    "Verpacker": "Packer",
    # Logistics & warehouse
    "Lagermitarbeiter": "Warehouse Worker",
    "Lagerhelfer": "Warehouse Helper",
    "Kommissionierer": "Order Picker",
    "Gabelstaplerfahrer": "Forklift Driver",
    "Staplerfahrer": "Forklift Driver",
    "Berufskraftfahrer": "Professional Driver",
    "LKW-Fahrer": "Truck Driver",
    "Kraftfahrer": "Driver",
    # Cleaning & maintenance
    "Reinigungskraft": "Cleaner",
    "Gebäudereiniger": "Building Cleaner",
    "Industriereiniger": "Industrial Cleaner",
    "Unterhaltsreinigung": "Maintenance Cleaning",
    # Welding-process abbreviations when they appear standalone
    # (e.g. "Schweißer WIG" -> "Welder TIG").
    "WIG": "TIG",
    "MAG": "MAG",
    "MIG": "MIG",
    # Common modifiers / connectors (lowest priority, shortest)
    "und": "and",
    "für": "for",
}

# Compile one (pattern, replacement) per term, longest source first so the most
# specific compound matches before its parts. \b boundaries respect umlauts/ß
# because those are word characters under Python's default Unicode regex.
_RULES = [
    (re.compile(r"\b" + re.escape(de) + r"\b", re.IGNORECASE), en)
    for de, en in sorted(GLOSSARY.items(), key=lambda kv: -len(kv[0]))
]

_WS_RE = re.compile(r"\s+")
# Tidy leftover separators after gender tags are stripped (" - ", " / ", ", ").
_STRAY_SEP_RE = re.compile(r"\s*[/]\s*|\s+-\s+")


def translate_title(title: str) -> str:
    """Translate a German job title to English using the glossary.

    Untranslated tokens (a number, a city, an unknown specialism) are preserved
    verbatim, so "20 Produktionshelfer" -> "20 Production Helper". Returns "" for
    empty input.
    """
    if not title:
        return ""
    text = _GENDER_TAG_RE.sub(" ", title)   # drop "(m/w/d)" etc., as elsewhere
    text = _STRAY_SEP_RE.sub(" ", text)
    for pat, repl in _RULES:
        text = pat.sub(repl, text)
    return _WS_RE.sub(" ", text).strip()
