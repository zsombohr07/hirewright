"""Unified lead + contact list export (merge-preserving).

Writes ONE row per company: blank **contact** columns up front (you fill these in
from LinkedIn / your CRM) followed by the **job-signal** columns from the engine.
This is the sheet where you "unify" job posts with the people you'll call.

Re-runs MERGE on company name, so nothing you've typed is ever lost:
  - contact cells you've filled are preserved (never overwritten),
  - job columns are refreshed from the latest run,
  - new companies are appended,
  - companies that drop out of the latest run are kept (you keep the contact),
  - any extra columns you add to the file by hand are preserved too.
"""

from __future__ import annotations

import csv
import os
from datetime import date
from typing import List, Optional

from .core import normalize_company
from .translate import translate_title

# Contact columns first (blank, for you to fill), then the job-signal columns.
CONTACT_COLUMNS = [
    "contact_first_name",
    "contact_last_name",
    "email",
    "phone",
    "phone_secondary",
]
JOB_COLUMNS = [
    "company",
    "lead_score",
    "category",
    "rate",
    "open_roles",
    "total_headcount",
    "top_role",
    "top_role_en",
    "all_roles",
    "locations",
    "max_days_open",
    "urgent",
    "job_urls",
    "last_seen",
]
UNIFIED_COLUMNS = CONTACT_COLUMNS + JOB_COLUMNS


def _job_row(lead, urls, today) -> dict:
    top = lead.top_role
    return {
        "company": lead.company,
        "lead_score": lead.score,
        "category": lead.category,
        "rate": lead.rate,
        "open_roles": len(lead.roles),
        "total_headcount": lead.total_headcount,
        "top_role": top.role if top else "",
        "top_role_en": translate_title(top.role) if top else "",
        "all_roles": "; ".join(f"{r.role} (x{r.count})" for r in lead.roles),
        "locations": "; ".join(lead.locations),
        "max_days_open": lead.max_days_open,
        "urgent": "yes" if lead.urgency else "no",
        "job_urls": "; ".join(dict.fromkeys(urls)),  # dedup, keep order
        "last_seen": today.isoformat(),
    }


def export_unified(leads, postings, path: str, today: Optional[date] = None) -> int:
    """Write/merge the unified company+contact list. Returns row count written."""
    today = today or date.today()

    # StepStone job URLs per company (staffable postings only).
    urls_by_key: dict = {}
    for p in postings:
        if p.is_agency or not p.category:
            continue
        urls_by_key.setdefault(normalize_company(p.company), []).append(p.source_url)

    # Read any existing file to preserve contacts, drop-outs, and user columns.
    existing: dict = {}
    extra_cols: List[str] = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for col in reader.fieldnames or []:
                if col not in UNIFIED_COLUMNS and col not in extra_cols:
                    extra_cols.append(col)  # a column the user added by hand
            for row in reader:
                key = normalize_company(row.get("company", ""))
                if key:
                    existing[key] = row

    fieldnames = UNIFIED_COLUMNS + extra_cols
    out_rows: dict = {}

    # Current leads: fresh job columns + preserved contacts/extras.
    for lead in leads:
        key = normalize_company(lead.company)
        row = {c: "" for c in fieldnames}
        row.update(_job_row(lead, urls_by_key.get(key, []), today))
        prev = existing.get(key)
        if prev:
            for c in CONTACT_COLUMNS + extra_cols:
                row[c] = prev.get(c, "") or ""
        out_rows[key] = row

    # Companies seen before but not in this run — keep their row untouched.
    for key, prev in existing.items():
        if key not in out_rows:
            out_rows[key] = {c: prev.get(c, "") or "" for c in fieldnames}

    def _score(r) -> int:
        try:
            return int(r.get("lead_score") or 0)
        except (ValueError, TypeError):
            return 0

    rows = sorted(out_rows.values(), key=_score, reverse=True)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
