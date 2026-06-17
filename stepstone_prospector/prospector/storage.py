"""Local persistence: SQLite upsert (dedup + freshness) and CSV export.

The table is keyed on source_url so re-running the tool deduplicates listings
and builds a first_seen / last_seen freshness history.

V2: rows also carry category, is_agency, urgency, and a status field. On re-run,
last_seen is refreshed but status is NEVER overwritten — so a lead you've marked
'contacted' stays 'contacted'. days_open and lead_score are computed at report
time (not stored), so every run re-scores against fresh dates.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, date
from typing import Dict, List, Optional

from .core import JobPosting, parse_posted_date
from .translate import translate_title


_SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    source_url      TEXT PRIMARY KEY,
    company         TEXT NOT NULL,
    title           TEXT NOT NULL,
    source          TEXT,
    location        TEXT,
    salary          TEXT,
    posted_date     TEXT,
    description     TEXT,
    company_norm    TEXT,
    title_norm      TEXT,
    title_en        TEXT,
    headcount       INTEGER,
    headcount_basis TEXT,
    category        TEXT,
    is_agency       INTEGER DEFAULT 0,
    urgency         INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'new',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL
);
"""

_CSV_COLUMNS = [
    "company",
    "title",
    "title_en",
    "category",
    "headcount",
    "headcount_basis",
    "is_agency",
    "urgency",
    "status",
    "location",
    "salary",
    "posted_date",
    "source",
    "source_url",
    "first_seen",
    "last_seen",
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _date_to_str(d) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return d or ""


def _parse_stored_date(value) -> Optional[date]:
    """Parse a stored ISO timestamp/date (first 10 chars) into a date."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class Store:
    """SQLite-backed store of job postings, keyed on source_url."""

    def __init__(self, path: str = "leads.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Bring a pre-existing DB up to the current schema in place.

        CREATE TABLE IF NOT EXISTS won't add columns to a table that already
        exists, so add title_en if missing and backfill it from each stored
        title via the same translator used on fresh ingests.
        """
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(postings)")}
        if "title_en" not in cols:
            self.conn.execute("ALTER TABLE postings ADD COLUMN title_en TEXT")
            rows = self.conn.execute(
                "SELECT source_url, title FROM postings"
            ).fetchall()
            self.conn.executemany(
                "UPDATE postings SET title_en = ? WHERE source_url = ?",
                [(translate_title(r["title"]), r["source_url"]) for r in rows],
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def upsert_many(self, postings: List[JobPosting]) -> Dict[str, int]:
        """Insert new postings; for already-seen URLs just refresh last_seen.

        Existing rows keep their first_seen AND their status. Returns
        {"new": n, "seen_again": m}.
        """
        now = _now()
        new = 0
        seen_again = 0
        cur = self.conn.cursor()
        for p in postings:
            if not p.source_url:
                continue
            row = cur.execute(
                "SELECT source_url FROM postings WHERE source_url = ?",
                (p.source_url,),
            ).fetchone()
            if row is None:
                # Honour a seeded first_seen (used by the offline sample to
                # simulate ads that have been open for weeks); else now.
                first_seen = _date_to_str(p.first_seen) or now
                cur.execute(
                    """
                    INSERT INTO postings (
                        source_url, company, title, source, location, salary,
                        posted_date, description, company_norm, title_norm,
                        title_en, headcount, headcount_basis, category,
                        is_agency, urgency, status, first_seen, last_seen
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        p.source_url,
                        p.company,
                        p.title,
                        p.source,
                        p.location,
                        p.salary,
                        _date_to_str(p.posted_date),
                        p.description,
                        p.company_norm,
                        p.title_norm,
                        p.title_en,
                        p.headcount,
                        p.headcount_basis,
                        p.category,
                        1 if p.is_agency else 0,
                        1 if p.urgency else 0,
                        p.status or "new",
                        first_seen,
                        now,
                    ),
                )
                new += 1
            else:
                # Refresh freshness only. Never touch status.
                cur.execute(
                    "UPDATE postings SET last_seen = ? WHERE source_url = ?",
                    (now, p.source_url),
                )
                seen_again += 1
        self.conn.commit()
        return {"new": new, "seen_again": seen_again}

    def all_postings(self) -> List[JobPosting]:
        """Read every stored row back as a JobPosting (with freshness fields)."""
        rows = self.conn.execute("SELECT * FROM postings").fetchall()
        out: List[JobPosting] = []
        for r in rows:
            p = JobPosting(
                company=r["company"],
                title=r["title"],
                source_url=r["source_url"],
                source=r["source"] or "stepstone",
                location=r["location"] or "",
                salary=r["salary"] or "",
                posted_date=parse_posted_date(r["posted_date"]),
                description=r["description"] or "",
                company_norm=r["company_norm"] or "",
                title_norm=r["title_norm"] or "",
                title_en=r["title_en"] or "",
                headcount=r["headcount"],
                headcount_basis=r["headcount_basis"] or "",
                category=r["category"] or "",
                is_agency=bool(r["is_agency"]),
                urgency=bool(r["urgency"]),
                status=r["status"] or "new",
                first_seen=_parse_stored_date(r["first_seen"]),
                last_seen=_parse_stored_date(r["last_seen"]),
            )
            if not p.company_norm or not p.headcount_basis:
                p.enrich()
            out.append(p)
        return out

    def export_csv(self, path: str = "leads.csv") -> int:
        """Flat dump of all stored rows. Returns row count written."""
        rows = self.conn.execute(
            f"SELECT {', '.join(_CSV_COLUMNS)} FROM postings "
            "ORDER BY is_agency, company_norm"
        ).fetchall()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_CSV_COLUMNS)
            for r in rows:
                writer.writerow([r[c] for c in _CSV_COLUMNS])
        return len(rows)
