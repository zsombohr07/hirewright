# Hirewright Sales-Lead Engine

A command-line **sales-lead engine** for **Hirewright**, an industrial
labour-leasing company. Hirewright sources skilled and semi-skilled workers from
Central Europe (Hungary, Romania, Poland, Slovakia) and leases them **by the hour**
to industrial employers in **Germany** (automotive, manufacturing, logistics,
construction, shipbuilding). The pitch: full operational support — housing,
transport, paperwork, sick-leave cover — **no retainer, pay only for hours worked.**

This tool is **account-based**: you give it a **watchlist of companies** (e.g. names
you sourced on LinkedIn), and it checks **StepStone (DE)** for those companies' current
job ads, keeping the **staffable blue-collar roles** that fall into one of Hirewright's
six service categories — i.e. the gaps Hirewright could fill *at the accounts you care
about*. Finding the right contact person is a separate, downstream step — by design this
tool stays at the company level and collects no personal data.

The design is **"rent the fetch, own the brain"**: the hard part (getting past
StepStone's bot protection) is delegated to a managed [Apify](https://apify.com)
actor, running one search per watchlist company, while the valuable part — verifying the
match and turning raw ads into ranked, pitch-ready leads — is our own code.

> **Scope:** public company + job-ad data only. The tool does **not** collect, store,
> or infer any personal data — no contact names, emails, or phone numbers. This is
> prospecting about *companies*, which keeps it clear of GDPR's personal-data rules.

---

## Quick start (zero setup)

No accounts, no API keys, no `pip install`. Standard-library Python 3.9+ only.

```bash
cd stepstone_prospector
cp companies.example.txt companies.txt        # your watchlist, one name per line
python3 run.py --companies companies.txt
```

This runs built-in **sample** ads through the whole pipeline so you can see it work
end-to-end, filtered to the companies in your watchlist. (Running `python3 run.py` with
no watchlist replays *all* the sample ads, a fuller demo.) It writes `leads.db` (SQLite)
and `leads.csv`, and prints a report with:

- **OPEN STAFFABLE ROLES** — your watchlist companies with a current staffable gap,
  ranked by lead score, each with a ready-to-send German pitch line.
- **COMPETITOR WATCH** — staffing rivals (other agencies) and where they're hiring.
- **BY CATEGORY** — lead count and total headcount demanded per service category.
- **WATCHED — no staffable StepStone ads found** — watchlist companies that surfaced no
  fillable role (they may post nothing on StepStone, or only office roles). *No result ≠
  not hiring.*

Run it again and you'll see `0 new, N seen again` — postings are deduplicated on URL,
with `first_seen` / `last_seen` freshness tracking. A lead's `status` (e.g. once you
mark it `contacted` in the DB) is **never** overwritten on re-runs.

---

## What the engine looks for

Targeting happens in two layers:

1. **Which companies** — your **watchlist** in `companies.txt` (one name per line). This
   is the primary targeting input; the engine only looks at these companies. Matching is
   loose (legal suffixes and `(m/w/d)` noise are stripped via `normalize_company`), so
   `BMW` matches `BMW AG` and `Stahlbau Becker` matches `Stahlbau Becker GmbH`.
2. **Which of their roles count** — a role is kept only if it's a **staffable blue-collar
   role** in one of Hirewright's six categories (and the poster isn't a staffing agency).
   That filter lives in one editable file, **`prospector/targets.py`**:

| Category | Rate | Example roles |
|---|---|---|
| Skilled trades | €29/hr | Schweißer, Elektriker, Industriemechaniker, CNC-Fräser |
| Industrial specialists | €29/hr | Sprinklermonteur, Brandschutzmonteur, Sicherheitstechnik |
| Construction & finishing | €25/hr | Maler, Rohrleitungsbauer, Bauhelfer, Trockenbauer |
| Semi-skilled production | €20/hr | Produktionshelfer, Maschinenbediener, Verpacker |
| Logistics & warehouse | €20/hr | Lagerhelfer, Kommissionierer, Staplerfahrer, LKW-Fahrer |
| Cleaning & maintenance | €19/hr | Reinigungskraft, Gebäudereiniger, Industriereiniger |

`targets.py` also holds:
- **`AGENCY_MARKERS`** — name fragments (`zeitarbeit`, `randstad`, `adecco`, …) that
  identify a competing staffing firm. Those ads go to **Competitor Watch**, never to
  leads.
- **`URGENCY_TERMS`** — `ab sofort`, `dringend`, `kurzfristig`, … which bump a lead's
  score.

Edit any of these lists to tune the targeting; the rest of the tool picks it up
automatically.

---

## What the lead score means

The score is **transparent and tunable** (see `prospector/scoring.py`). For a crew-
leasing business, **volume** is the dominant signal:

- **VOLUME** — headcount `1` → 1 pt, `2–4` → 3, `5–9` → 6, `10+` → 10; "mehrere
  Stellen" (multiple, no number) → 4; otherwise 1.
- **PERSISTENCE** — how long the ad has stayed open (`days_open` = today − `first_seen`):
  `<14d` → 0, `14–29` → 2, `30–59` → 5, `60+` → 8; **plus** `(repost_count − 1) × 2`
  capped at 6, where `repost_count` is how many times that company+role appears (e.g.
  the same welder ad in four cities → 4).
- **URGENCY** — `+3` if the ad signals it needs people fast.

`lead_score = VOLUME + PERSISTENCE + URGENCY`, summed per role and then per company.
A long-open, repeatedly-posted, or high-volume role is exactly the gap Hirewright
fills. `days_open` and the score are recomputed **every run** against fresh dates —
they are not frozen in the database.

## The headcount caveat (conservative on purpose)

`headcount` is a **best-effort** read of how many openings an ad represents, and it is
deliberately cautious:

- It only reports an explicit number when that number sits right next to an
  opening-word — *Stellen, Positionen, Vakanzen, Stellenangebote, openings,
  positions, roles, vacancies* (e.g. "**20 offene Stellen**" → `20`).
- It **never** treats "**X Mitarbeiter**" as openings — in German ads that describes
  *company size*, not jobs on offer (e.g. "über 500 Mitarbeitern" is ignored).
- "**mehrere**"/"multiple" with no number → counted as the `multiple` signal.
- Otherwise it assumes **1** opening per ad. Anything above 200 is treated as company
  size, not openings.

So headcount undercounts rather than overcounts. Trust the **persistence/repost
signal** as much as any single ad's stated number.

---

## Going live with real data (Apify)

1. **Create an Apify account** at <https://apify.com> and copy your API token from
   *Settings → Integrations* (`apify_api_xxx`).
2. **Pick a StepStone actor** from the [Apify Store](https://apify.com/store) — search
   for "StepStone". Note its actor ID (e.g. `someuser~stepstone-scraper`). Actors vary;
   this tool maps their output tolerantly, but you may need to adjust the input shape in
   `prospector/fetchers.py` for a specific actor.
3. **Set the environment variables:**
   ```bash
   export APIFY_TOKEN=apify_api_xxx
   export APIFY_ACTOR=someuser~stepstone-scraper
   ```
4. **Run with your watchlist.** The engine runs **one targeted StepStone search per
   company** in `companies.txt`, verifies each returned ad really belongs to that company,
   and keeps the staffable roles:
   ```bash
   python3 run.py --fetcher apify --companies companies.txt --limit 100
   ```
   Or bypass the watchlist with one explicit StepStone search URL (advanced):
   ```bash
   python3 run.py --fetcher apify \
     --query "https://www.stepstone.de/jobs/bmw/in-deutschland"
   ```

If the token or actor is missing — or you forget `--companies` — the tool tells you
exactly what to set (or to fall back to `--fetcher sample`).

> **Note on persistence with live data:** `first_seen` is set the first time *this tool*
> sees an ad, so `days_open` starts at 0 on a fresh database and grows as you re-run the
> engine over days/weeks. The repost and volume signals work from the first run.

---

## CLI options

| Flag | Default | Meaning |
|------|---------|---------|
| `--fetcher {sample,apify}` | `sample` | Data source. `sample` is the offline demo. |
| `--companies` | `./companies.txt` if present | Watchlist file: one company name per line (`#` lines ignored). The primary targeting input. |
| `--query` | — | Explicit StepStone search URL (apify mode). Advanced escape hatch — bypasses the watchlist. |
| `--limit` | `100` | Max postings per search. |
| `--db` | `leads.db` | SQLite database path. |
| `--csv` | `leads.csv` | CSV export path. |

---

## Project layout

```
stepstone_prospector/
  prospector/
    __init__.py
    core.py      # JobPosting model, normalization, company matching, headcount, dates
    targets.py   # Hirewright config: categories, rivals, urgency + classifiers
    scoring.py   # lead scoring, company roll-up, German pitch lines
    storage.py   # SQLite upsert (dedup + freshness + status) + CSV export
    translate.py # German -> English job-title glossary (title_en column)
    fetchers.py  # SampleFetcher + ApifyStepStoneFetcher (per-company search)
  run.py                 # CLI entry point
  companies.example.txt  # watchlist template -> copy to companies.txt
  README.md
```

Adding another source later (e.g. **Indeed.de**) is just one new `Fetcher` subclass in
`fetchers.py` that returns classified `JobPosting` objects — the targeting, scoring, and
reporting code is source-agnostic. A second source is also the natural fix for the
StepStone-only blind spot below.

---

## Notes & limitations

- **StepStone-only visibility:** the engine only sees what's on StepStone. A watchlist
  company that advertises on LinkedIn Jobs, Indeed, or its own careers page (or simply
  isn't hiring right now) shows up under *"no staffable ads found"* — that is **not**
  evidence they aren't hiring. Widen coverage by adding another `Fetcher`.
- **Fuzzy name matching:** StepStone free-text company search can return a similarly-named
  firm; `company_matches()` (token-subset over `normalize_company`) removes most of that
  noise but isn't perfect. For bulletproof targeting, search by each company's StepStone
  profile URL instead of its name (you'd look each one up).
- **Terms of service:** reading StepStone ads programmatically is against StepStone's
  ToS, so keep volume **low** — this is targeted prospecting, not mass harvesting.
  Going through a managed Apify actor keeps the fetching at arm's length; use it
  responsibly.
- **LinkedIn was deliberately left out** — its anti-scraping posture and ToS make it a
  poor fit for this approach. (Use it to *source* the company names; this tool checks
  StepStone for their ads.)
- No bot-evasion is implemented here (no proxy rotation, CAPTCHA solving, or stealth
  browser). All fetching that touches the network goes through Apify.
