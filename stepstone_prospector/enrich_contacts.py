#!/usr/bin/env python3
"""Enrich a people list with the job-ad signal, keyed on company name.

You have a contact list (name, email, phone, company); this attaches what each
contact's company is currently hiring for, so you know who to call and what to
pitch. It keeps YOUR list as the source of truth — one row per person, your
original columns untouched — and appends the engine's job columns. Because the
join is per-person, a company appearing more than once is fine: every person at
BMW gets BMW's job signal.

It auto-discovers the CSV in ../Input lists/ and writes <name>.enriched.csv next
to it (your original file is never touched). Offline by default (built-in sample
ads, no Apify token, no cost):

    cd stepstone_prospector
    python3 enrich_contacts.py                       # offline test, all rows
    python3 enrich_contacts.py --max-contacts 100    # offline test, first 100

Preview the cost of a live run without spending anything:

    export APIFY_TOKEN=apify_api_xxx
    python3 enrich_contacts.py --fetcher auto --max-contacts 100 --dry-run

Live via Claude (recommended). Researches each company's OWN careers page +
the web, recognises the company despite name variants, and judges role fit —
no board-coverage gap, no brittle name/keyword matching. Needs ANTHROPIC_API_KEY
and also writes <name>.diagnostic.csv explaining every empty company:

    export ANTHROPIC_API_KEY=sk-ant-xxx
    python3 enrich_contacts.py --fetcher claude --max-contacts 100 --dry-run  # $0 preview
    python3 enrich_contacts.py --fetcher claude --max-contacts 100            # paid test

Live via job boards (Apify). 'auto' tries Indeed first and falls back to
StepStone only for the companies Indeed found nothing for:

    python3 enrich_contacts.py --fetcher auto --max-contacts 100   # paid test
    python3 enrich_contacts.py --fetcher indeed   # Indeed only, all rows
    python3 enrich_contacts.py --fetcher apify    # StepStone only, all rows

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
    ClaudeResearchFetcher,
)
from prospector.scoring import (
    rollup_company_leads,
    select_latest_per_company,
)
from prospector.translate import translate_title

_HERE = os.path.dirname(os.path.abspath(__file__))
_INPUT_DIR = os.path.normpath(os.path.join(_HERE, "..", "Input lists"))
_ENRICHED_SUFFIX = ".enriched.csv"  # our outputs — excluded from auto-discovery


def _discover_input():
    """Find the contact CSV to read when --in is not given.

    Prefers 'contacts.csv'; otherwise the single non-output *.csv in Input lists/.
    Returns (path, error_message) — exactly one is None.
    """
    preferred = os.path.join(_INPUT_DIR, "contacts.csv")
    if os.path.exists(preferred):
        return preferred, None
    if not os.path.isdir(_INPUT_DIR):
        return None, f"input folder not found: {_INPUT_DIR}"
    candidates = sorted(
        f for f in os.listdir(_INPUT_DIR)
        if f.lower().endswith(".csv") and not f.lower().endswith(_ENRICHED_SUFFIX)
    )
    if not candidates:
        return None, f"no input .csv found in {_INPUT_DIR}"
    if len(candidates) > 1:
        listing = ", ".join(candidates)
        return None, (
            f"multiple CSVs in {_INPUT_DIR} ({listing}); "
            "pick one with --in <file>"
        )
    return os.path.join(_INPUT_DIR, candidates[0]), None


def _default_output_for(in_path):
    """Derive '<stem>.enriched.csv' next to the input so the original is untouched."""
    folder = os.path.dirname(in_path) or "."
    stem = os.path.splitext(os.path.basename(in_path))[0]
    return os.path.join(folder, stem + _ENRICHED_SUFFIX)

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
    """Find the column holding the company name.

    Prefer an exact header ('company name' / 'company') so we never grab a
    look-alike like 'Company Name for Emails' or 'Company Address'; fall back to
    a substring match only if no exact header exists.
    """
    lowered = {col.lower().strip(): col for col in fieldnames}
    for exact in ("company name", "company", "company_name", "employer"):
        if exact in lowered:
            return lowered[exact]
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


def _company_found(company, leads):
    """True if any lead matches this company (fuzzy, either direction)."""
    return any(
        company_matches(company, l.company) or company_matches(l.company, company)
        for l in leads
    )


def _fetch_single(board, companies, limit):
    """Fetch ONE board + roll up to per-company leads.

    Returns (leads, postings, diagnostics) — diagnostics is a per-company list
    (Claude research only; empty for the board scrapers).
    """
    if not companies:
        return [], [], []
    if board == "stepstone":
        postings = ApifyStepStoneFetcher(companies=companies).fetch(limit=limit)
        return rollup_company_leads(postings), postings, []
    if board == "indeed":
        postings = ApifyIndeedFetcher(companies=companies).fetch(limit=limit)
        collapsed = select_latest_per_company(postings)
        return rollup_company_leads(collapsed), collapsed, []
    if board == "claude":
        fetcher = ClaudeResearchFetcher(companies=companies)
        postings = fetcher.fetch(limit=limit)
        return rollup_company_leads(postings), postings, fetcher.diagnostics
    # sample (offline demo)
    postings = SampleFetcher(companies=companies).fetch(limit=limit)
    return rollup_company_leads(postings), postings, []


def _fetch_leads(fetcher_name, companies, limit):
    """Run the chosen fetcher + roll up to per-company leads.

    Returns (leads, postings, diagnostics).

    'auto' = try Indeed for every company first, then fall back to StepStone ONLY
    for the companies Indeed found nothing staffable for.
    """
    if fetcher_name == "apify":
        return _fetch_single("stepstone", companies, limit)
    if fetcher_name == "indeed":
        return _fetch_single("indeed", companies, limit)
    if fetcher_name == "claude":
        return _fetch_single("claude", companies, limit)
    if fetcher_name == "auto":
        print("  [pass 1/2] Indeed (DE)…", file=sys.stderr)
        leads, postings, diag = _fetch_single("indeed", companies, limit)
        missing = [c for c in companies if not _company_found(c, leads)]
        if missing:
            print(
                f"  [pass 2/2] StepStone (DE) fallback for {len(missing)} "
                f"company(ies) Indeed missed…",
                file=sys.stderr,
            )
            leads2, postings2, _ = _fetch_single("stepstone", missing, limit)
            leads = leads + leads2
            postings = postings + postings2
        else:
            print("  [pass 2/2] skipped — Indeed covered every company.", file=sys.stderr)
        return leads, postings, diag
    # sample (offline demo)
    return _fetch_single("sample", companies, limit)


# easyapi actor pricing: per-result billing at each search's maxItems floor.
_INDEED_MIN, _INDEED_RATE = 20, 2.99 / 1000
_STEP_MIN, _STEP_RATE = 30, 3.00 / 1000
# Claude research: one Messages call per company. Web search is billed per search
# (~$10/1k) and a call makes a handful; tokens add a little on top. Rough rule of
# thumb of ~$0.05–0.10 per company, used only for the upfront estimate.
_CLAUDE_PER_COMPANY = 0.08


def _estimate_cost(fetcher_name, n_companies):
    """Human-readable cost estimate string for a live run, or None for offline."""
    if fetcher_name == "sample" or n_companies == 0:
        return None
    if fetcher_name == "claude":
        c = n_companies * _CLAUDE_PER_COMPANY
        return (
            f"~${c:.2f} ({n_companies} Claude web-research calls, "
            "~$0.05–0.10 each)"
        )
    if fetcher_name == "indeed":
        c = n_companies * _INDEED_MIN * _INDEED_RATE
        return f"~${c:.2f} ({n_companies} Indeed searches)"
    if fetcher_name == "apify":
        c = n_companies * _STEP_MIN * _STEP_RATE
        return f"~${c:.2f} ({n_companies} StepStone searches)"
    # auto: Indeed for all, StepStone fallback for the misses (unknown until run)
    indeed = n_companies * _INDEED_MIN * _INDEED_RATE
    step_worst = n_companies * _STEP_MIN * _STEP_RATE
    low = indeed + step_worst * 0.5   # ~half fall back
    high = indeed + step_worst        # every company falls back
    return (
        f"~${low:.2f}–${high:.2f} ({n_companies} Indeed searches"
        f" + StepStone fallback for the misses)"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Enrich a people list with per-company job-ad signal."
    )
    parser.add_argument(
        "--fetcher",
        choices=["sample", "claude", "auto", "indeed", "apify"],
        default="sample",
        help="data source: 'claude' = Claude researches each company's live "
        "openings via web search (needs ANTHROPIC_API_KEY); "
        "'auto' = Indeed first, StepStone fallback for misses; "
        "'indeed' = Indeed (DE) only; 'apify' = StepStone (DE) only; "
        "'sample' = offline demo (default: sample). 'auto'/'indeed'/'apify' need "
        "APIFY_TOKEN.",
    )
    parser.add_argument("--in", dest="infile", default=None,
                        help="input contact CSV (default: auto-discover the CSV in "
                        "../Input lists/)")
    parser.add_argument("--out", dest="outfile", default=None,
                        help="output CSV (default: <input>.enriched.csv next to the "
                        "input, leaving the original untouched)")
    parser.add_argument("--limit", type=int, default=100, help="max postings per search")
    parser.add_argument("--max-contacts", dest="max_contacts", type=int, default=None,
                        help="only process the FIRST N contacts (hard cap on how "
                        "many companies get searched — e.g. 100 for a test run)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="show what would be searched + a cost estimate, then "
                        "exit WITHOUT calling Apify ($0)")
    args = parser.parse_args(argv)

    # Resolve input: explicit --in, else auto-discover in ../Input lists/.
    infile = args.infile
    if infile is None:
        infile, err = _discover_input()
        if err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        print(f"Using input: {infile}")
    outfile = args.outfile or _default_output_for(infile)

    fieldnames, rows = _read_contacts(infile)
    if rows is None:
        return 2
    if not rows:
        print("error: contact file has no rows.", file=sys.stderr)
        return 2

    # Hard cap BEFORE anything else, so a live run can only ever touch these rows.
    if args.max_contacts is not None and args.max_contacts >= 0:
        if len(rows) > args.max_contacts:
            print(
                f"Capping to the first {args.max_contacts} of {len(rows)} contacts "
                f"(--max-contacts)."
            )
            rows = rows[: args.max_contacts]

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

    estimate = _estimate_cost(args.fetcher, len(companies))
    if estimate:
        print(f"Live run via '{args.fetcher}': estimated cost {estimate}.")

    if args.dry_run:
        print(
            f"\nDry run — would search {len(companies)} company(ies) via "
            f"'{args.fetcher}' and write {outfile}."
        )
        print("No calls made, $0 spent. Drop --dry-run to run for real.")
        return 0

    try:
        leads, postings, diagnostics = _fetch_leads(
            args.fetcher, companies, args.limit
        )
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Fetched job signal for {len(leads)} company(ies) via '{args.fetcher}'.")

    # Per-company diagnostic (Claude research): why each company is empty vs a hit,
    # so "no result" is never ambiguous. Written next to the enriched file.
    if diagnostics:
        diag_path = os.path.splitext(outfile)[0] + ".diagnostic.csv"
        if diag_path.endswith(".enriched.diagnostic.csv"):
            diag_path = diag_path.replace(".enriched.diagnostic.csv", ".diagnostic.csv")
        diag_fields = [
            "company", "careers_url", "roles_seen", "staffable_roles",
            "categories", "empty_reason", "error",
        ]
        with open(diag_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=diag_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(diagnostics)
        n_empty = sum(1 for d in diagnostics if not d.get("staffable_roles"))
        print(
            f"Wrote per-company diagnostic for {len(diagnostics)} companies "
            f"({n_empty} with no staffable role) -> {diag_path}"
        )

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
    os.makedirs(os.path.dirname(outfile) or ".", exist_ok=True)
    with open(outfile, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Enriched {matched}/{len(rows)} contacts with a job match "
        f"-> {outfile}"
    )
    print("  (blank job columns = no staffable ad found — no result != not hiring.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
