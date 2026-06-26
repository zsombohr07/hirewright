#!/usr/bin/env python3
"""Enrich a people list with the job-ad signal, keyed on company name.

You have a contact list (name, email, phone, company); this attaches what each
contact's company is currently hiring for, so you know who to call and what to
pitch. It keeps YOUR list as the source of truth — one row per person, your
original columns untouched — and appends the engine's job columns. Because the
join is per-person, a company appearing more than once is fine: every person at
BMW gets BMW's job signal.

Offline by default (built-in sample ads, no Apify token, no cost):

    cd stepstone_prospector
    python3 enrich_contacts.py

Live (real boards) once you've proven it works:

    export APIFY_TOKEN=apify_api_xxx
    python3 enrich_contacts.py --fetcher apify --limit 30
    python3 enrich_contacts.py --fetcher indeed --limit 20

Reuses the existing engine (prospector/*) — no changes to it.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date

from prospector.core import normalize_company, company_matches
from prospector.fetchers import (
    SampleFetcher,
    ApifyStepStoneFetcher,
    ApifyIndeedFetcher,
)
from prospector.scoring import (
    rollup_company_leads,
    select_latest_per_company,
)
from prospector.translate import translate_title

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_IN = os.path.normpath(os.path.join(_HERE, "..", "Input lists", "contacts.csv"))
_DEFAULT_OUT = os.path.normpath(
    os.path.join(_HERE, "..", "Input lists", "enriched_contacts.csv")
)

# Job-signal columns appended to each person (company is already in their row).
JOB_COLUMNS = [
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
]


def _detect_company_column(fieldnames):
    """Find the column that holds the company name (case-insensitive substring)."""
    for needle in ("company", "firm", "organi", "employer", "account"):
        for col in fieldnames:
            if needle in col.lower():
                return col
    return None


def _job_dict(lead, urls):
    """Build the appended job columns for one company lead."""
    top = lead.top_role
    return {
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
    }


def _read_contacts(path):
    if not os.path.exists(path):
        print(f"error: contact file not found: {path}", file=sys.stderr)
        print(
            "  Drop your CSV there (any headers — must include a company column).",
            file=sys.stderr,
        )
        return None, None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return reader.fieldnames or [], rows


def _report_repeats(rows, company_col):
    """Print how many companies repeat — answers 'do they repeat?' directly."""
    counts = {}
    order = []
    for r in rows:
        name = (r.get(company_col) or "").strip()
        if not name:
            continue
        key = normalize_company(name)
        if key not in counts:
            counts[key] = {"display": name, "n": 0}
            order.append(key)
        counts[key]["n"] += 1
    repeats = [(counts[k]["display"], counts[k]["n"]) for k in order if counts[k]["n"] > 1]
    repeats.sort(key=lambda x: x[1], reverse=True)
    n_contacts = sum(1 for r in rows if (r.get(company_col) or "").strip())
    print(
        f"  {n_contacts} contacts across {len(order)} companies; "
        f"{len(repeats)} have multiple contacts"
        + (" (all get the same company's job signal)." if repeats else ".")
    )
    if repeats:
        preview = ", ".join(f"{name} ({n})" for name, n in repeats[:8])
        more = "" if len(repeats) <= 8 else f", … (+{len(repeats) - 8} more)"
        print(f"    {preview}{more}")
    return [counts[k]["display"] for k in order]


def _fetch_leads(fetcher_name, companies, limit):
    """Run the chosen fetcher + roll up to per-company leads. Returns (leads, postings)."""
    if fetcher_name == "apify":
        postings = ApifyStepStoneFetcher(companies=companies).fetch(limit=limit)
        return rollup_company_leads(postings), postings
    if fetcher_name == "indeed":
        postings = ApifyIndeedFetcher(companies=companies).fetch(limit=limit)
        collapsed = select_latest_per_company(postings)
        return rollup_company_leads(collapsed), collapsed
    # sample (offline demo)
    postings = SampleFetcher(companies=companies).fetch(limit=limit)
    return rollup_company_leads(postings), postings


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Enrich a people list with per-company job-ad signal."
    )
    parser.add_argument(
        "--fetcher",
        choices=["sample", "apify", "indeed"],
        default="sample",
        help="data source: 'apify' = StepStone (DE), 'indeed' = Indeed (DE), "
        "'sample' = offline demo (default: sample)",
    )
    parser.add_argument("--in", dest="infile", default=_DEFAULT_IN,
                        help="input contact CSV (default: ../Input lists/contacts.csv)")
    parser.add_argument("--out", dest="outfile", default=_DEFAULT_OUT,
                        help="output CSV (default: ../Input lists/enriched_contacts.csv)")
    parser.add_argument("--limit", type=int, default=100, help="max postings per search")
    args = parser.parse_args(argv)

    fieldnames, rows = _read_contacts(args.infile)
    if rows is None:
        return 2
    if not rows:
        print("error: contact file has no rows.", file=sys.stderr)
        return 2

    company_col = _detect_company_column(fieldnames)
    if not company_col:
        print(
            "error: could not find a company column in: "
            f"{', '.join(fieldnames)}",
            file=sys.stderr,
        )
        print("  Rename one column to include 'company'.", file=sys.stderr)
        return 2
    print(f"Company column detected: '{company_col}'")

    companies = _report_repeats(rows, company_col)

    # Write the derived watchlist to a SEPARATE file so a hand-curated
    # companies.txt is never clobbered (this script doesn't need it — it searches
    # the contact list's companies directly — but it's handy for run.py reports).
    watchlist_path = os.path.join(_HERE, "contacts_companies.txt")
    with open(watchlist_path, "w", encoding="utf-8") as fh:
        fh.write("# Auto-generated from the contact list by enrich_contacts.py\n")
        for c in companies:
            fh.write(c + "\n")
    print(f"Wrote {len(companies)} companies -> contacts_companies.txt")

    leads, postings = _fetch_leads(args.fetcher, companies, args.limit)
    print(f"Fetched job signal for {len(leads)} company(ies) via '{args.fetcher}'.")

    # Job URLs per company (staffable postings only).
    urls_by_key = {}
    for p in postings:
        if p.is_agency or not p.category:
            continue
        urls_by_key.setdefault(normalize_company(p.company), []).append(p.source_url)

    # Per-person left join: match each contact's company to a lead (fuzzy, either
    # direction, so "BMW" <-> "BMW AG" and "VW Group" <-> "VW" both connect).
    blank_job = {c: "" for c in JOB_COLUMNS}
    matched = 0
    for r in rows:
        person_company = (r.get(company_col) or "").strip()
        hit = None
        for lead in leads:
            if person_company and (
                company_matches(person_company, lead.company)
                or company_matches(lead.company, person_company)
            ):
                hit = lead
                break
        if hit:
            r.update(_job_dict(hit, urls_by_key.get(normalize_company(hit.company), [])))
            matched += 1
        else:
            r.update(blank_job)

    # Sort hottest-first by lead_score (blank -> 0); keep input order within ties.
    def _score(r):
        try:
            return int(r.get("lead_score") or 0)
        except (ValueError, TypeError):
            return 0

    rows.sort(key=_score, reverse=True)

    out_fields = list(fieldnames) + [c for c in JOB_COLUMNS if c not in fieldnames]
    os.makedirs(os.path.dirname(args.outfile) or ".", exist_ok=True)
    with open(args.outfile, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Enriched {matched}/{len(rows)} contacts with a job match "
        f"-> {args.outfile}"
    )
    print("  (blank job columns = no staffable ad found — no result != not hiring.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
