#!/usr/bin/env python3
"""CLI entry point for the Hirewright sales-lead engine.

Scans public StepStone (DE) job ads and surfaces German employers with a
blue-collar labour gap Hirewright could supply. Run `python3 run.py` with no
arguments for a zero-setup offline demo.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from prospector.core import company_matches
from prospector.fetchers import (
    SampleFetcher,
    ApifyStepStoneFetcher,
    ApifyIndeedFetcher,
)
from prospector.scoring import (
    rollup_company_leads,
    select_latest_per_company,
    pitch_line,
    category_summary,
)
from prospector.storage import Store
from prospector.translate import translate_title
from prospector.unified import export_unified

# Default unified-list path: the "Unified list" folder next to this tool, resolved
# from the script location so it works regardless of the current directory.
_DEFAULT_UNIFIED = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "Unified list",
        "unified_list.csv",
    )
)


def load_companies(path):
    """Read a watchlist file: one company name per line, '#' lines ignored."""
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        out = []
        for line in fh:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def build_fetcher(args, companies):
    if args.fetcher == "sample":
        return SampleFetcher(companies=companies)
    if args.fetcher == "sample-indeed":
        return SampleFetcher(companies=companies, source="indeed")
    if args.fetcher == "apify":
        return ApifyStepStoneFetcher(companies=companies)
    if args.fetcher == "indeed":
        return ApifyIndeedFetcher(companies=companies)
    raise ValueError(f"unknown fetcher: {args.fetcher}")


def _flag(value: bool, yes: str = "yes", no: str = "no") -> str:
    return yes if value else no


def print_report(
    postings, upsert_result, today=None, companies=None, source_label="StepStone (DE)"
):
    today = today or date.today()
    leads = rollup_company_leads(postings, today)
    agencies = [p for p in postings if p.is_agency]
    companies = companies or []

    line = "=" * 72
    print()
    print(line)
    print(f"  HIREWRIGHT SALES-LEAD ENGINE — {source_label}")
    print(line)
    print(f"  Postings analysed : {len(postings)}")
    print(f"  Qualified leads   : {len(leads)} direct employers")
    print(f"  Competitor ads    : {len(agencies)} (staffing rivals)")
    print(
        f"  This run          : {upsert_result['new']} new, "
        f"{upsert_result['seen_again']} seen again"
    )

    # --- Priority leads ---------------------------------------------------
    print()
    print("  OPEN STAFFABLE ROLES  (your target companies — pay only for hours worked)")
    print("  " + "-" * 68)
    if not leads:
        print("  (no qualifying employers found)")
    for i, lead in enumerate(leads, 1):
        role = lead.top_role
        hc = lead.total_headcount or "?"
        locs = ", ".join(lead.locations) or "—"
        print()
        print(
            f"  {i}. {lead.company}   [score {lead.score}]  "
            f"{lead.category} · {lead.rate}"
        )
        print(
            f"     {hc} worker(s) needed · top role: {role.role} "
            f"(x{role.count})"
        )
        print(f"        ↳ EN: {translate_title(role.role)}")
        print(
            f"     open {lead.max_days_open}d · reposts {lead.repost_count} · "
            f"urgent {_flag(lead.urgency)} · {locs}"
        )
        print(f"     ↳ {pitch_line(lead)}")

    # --- Competitor watch -------------------------------------------------
    print()
    print("  COMPETITOR WATCH  (staffing rivals — not leads)")
    print("  " + "-" * 68)
    if not agencies:
        print("  (no staffing-agency ads seen)")
    else:
        seen = {}
        for p in agencies:
            seen.setdefault(p.company, set())
            if p.location:
                seen[p.company].add(p.location)
        for company, locs in sorted(seen.items()):
            where = ", ".join(sorted(locs)) or "—"
            print(f"  • {company}  →  hiring in {where}")

    # --- By-category summary ----------------------------------------------
    print()
    print("  BY CATEGORY  (lead count · total headcount demanded)")
    print("  " + "-" * 68)
    summary = category_summary(leads)
    if not summary:
        print("  (nothing to summarise)")
    for cat, n, hc in summary:
        print(f"  {hc:>3} workers · {n} lead(s) · {cat}")

    # --- Watchlist coverage -----------------------------------------------
    if companies:
        # "Covered" = the company surfaced an actual staffable lead, not merely
        # any ad (a watched firm posting only office roles still counts as a gap).
        found = {
            c for c in companies for lead in leads if company_matches(c, lead.company)
        }
        missing = [c for c in companies if c not in found]
        print()
        print(f"  WATCHED — no staffable {source_label} ads found")
        print("  " + "-" * 68)
        if not missing:
            print("  (every watched company had at least one matching ad)")
        else:
            for c in missing:
                print(f"  • {c}")
            print(
                "  Note: no result ≠ not hiring — they may post elsewhere "
                "(other boards, own site)."
            )

    print()
    print(line)
    print("  Note: public company + job-ad data only. No personal data collected.")
    print(line)
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Scan StepStone (DE) and surface German employers with a blue-collar "
            "labour gap Hirewright could supply."
        )
    )
    parser.add_argument(
        "--fetcher",
        choices=["sample", "apify", "indeed", "sample-indeed"],
        default="sample",
        help="data source: 'apify' = StepStone (DE), 'indeed' = Indeed (DE), "
        "'sample'/'sample-indeed' = offline demos (default: sample)",
    )
    parser.add_argument(
        "--companies",
        default=None,
        help="watchlist file: one company name per line ('#' lines ignored). "
        "Defaults to ./companies.txt if present.",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="explicit StepStone search URL (apify mode; advanced escape hatch, "
        "bypasses the company watchlist)",
    )
    parser.add_argument("--limit", type=int, default=100, help="max postings per search")
    parser.add_argument("--db", default="leads.db", help="SQLite database path")
    parser.add_argument("--csv", default="leads.csv", help="CSV export path")
    parser.add_argument(
        "--unified",
        default=_DEFAULT_UNIFIED,
        help="unified company+contact list (merge-preserving). "
        "Defaults to the 'Unified list' folder next to the tool.",
    )
    args = parser.parse_args(argv)

    # Resolve the watchlist: explicit --companies, else ./companies.txt if present.
    companies_path = args.companies
    if companies_path is None and os.path.exists("companies.txt"):
        companies_path = "companies.txt"
    if args.companies and not os.path.exists(args.companies):
        print(f"error: companies file not found: {args.companies}", file=sys.stderr)
        return 2
    companies = load_companies(companies_path)

    try:
        fetcher = build_fetcher(args, companies)
        fetched = fetcher.fetch(query=args.query, limit=args.limit)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(f"Fetched {len(fetched)} postings via '{args.fetcher}' fetcher.")

    if args.fetcher in ("indeed", "sample-indeed"):
        # Indeed motion: keep ONE ad per firm (latest among the relevant), then
        # merge into the single combined sheet tagged source=indeed. No SQLite /
        # leads.csv — the unified list is the sole deliverable and ad-age comes
        # from each posting's publish date (first_seen).
        collapsed = select_latest_per_company(fetched)
        leads = rollup_company_leads(collapsed)
        unified_rows = export_unified(
            leads, collapsed, args.unified, source="indeed"
        )
        result = {"new": len(collapsed), "seen_again": 0}
        print(
            f"Collapsed to {len(collapsed)} firm(s) (one latest ad each). "
            f"Unified list: {unified_rows} companies merged -> {args.unified}"
        )
        print_report(
            collapsed, result, companies=companies, source_label="Indeed (DE)"
        )
        return 0

    with Store(args.db) as store:
        result = store.upsert_many(fetched)
        rows = store.export_csv(args.csv)
        all_postings = store.all_postings()

    leads = rollup_company_leads(all_postings)
    unified_rows = export_unified(leads, all_postings, args.unified)

    print(
        f"Stored to {args.db} ({result['new']} new). "
        f"Exported {rows} rows to {args.csv}."
    )
    print(f"Unified list: {unified_rows} companies merged -> {args.unified}")
    print_report(all_postings, result, companies=companies)
    return 0


if __name__ == "__main__":
    sys.exit(main())
