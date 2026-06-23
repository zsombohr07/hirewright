"""Lead scoring + pitch-line generation.

Turns classified postings into ranked company leads for Hirewright's sales team.
The scoring is intentionally transparent and tunable — adjust the weights below.

For a crew-leasing business, VOLUME is the dominant signal: a company opening
many roles (or the same role repeatedly) has a labour gap worth supplying.
PERSISTENCE (an ad open for weeks) means they can't fill it themselves.
URGENCY ("ab sofort") means they need help now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from .core import JobPosting, normalize_company
from .targets import category_rate


# ---------------------------------------------------------------------------
# Per-posting score
# ---------------------------------------------------------------------------

def days_open(posting: JobPosting, today: Optional[date] = None) -> int:
    """How long we've known this ad to be open (today - first_seen)."""
    today = today or date.today()
    if posting.first_seen:
        return max(0, (today - posting.first_seen).days)
    return 0


def _volume_points(posting: JobPosting) -> int:
    hc = posting.headcount
    if hc is not None:
        if hc >= 10:
            return 10
        if hc >= 5:
            return 6
        if hc >= 2:
            return 3
        return 1  # exactly 1 known opening
    # Unknown count: "multiple" language is a stronger hint than a lone assumed ad.
    if posting.headcount_basis == "multiple":
        return 4
    return 1


def _persistence_points(posting: JobPosting, today: Optional[date]) -> int:
    d = days_open(posting, today)
    if d >= 60:
        base = 8
    elif d >= 30:
        base = 5
    elif d >= 14:
        base = 2
    else:
        base = 0
    repost_bonus = min((posting.repost_count - 1) * 2, 6)
    return base + repost_bonus


def score_posting(posting: JobPosting, today: Optional[date] = None) -> int:
    """Transparent lead score for one posting. Higher = hotter lead.

    lead_score = VOLUME + PERSISTENCE + URGENCY.
    Reads posting.first_seen (days_open), posting.repost_count, posting.urgency.
    """
    volume = _volume_points(posting)
    persistence = _persistence_points(posting, today)
    urgency = 3 if posting.urgency else 0
    return volume + persistence + urgency


# ---------------------------------------------------------------------------
# One-ad-per-firm selection ("latest among relevant")
# ---------------------------------------------------------------------------

def _posting_date(posting: JobPosting) -> date:
    """Best available date for recency: posted_date, else first_seen, else epoch."""
    for d in (posting.posted_date, posting.first_seen):
        if isinstance(d, date):
            return d
    return date.min


def select_latest_per_company(
    postings: List[JobPosting], today: Optional[date] = None
) -> List[JobPosting]:
    """Collapse to ONE ad per company: the latest among the *relevant* ones.

    "Relevant" = a direct employer (not a staffing agency) whose role is in the
    Hirewright ICP (has a category). Among those, keep the most recently posted
    ad per normalized company, tie-broken by lead score so a same-day tie keeps
    the stronger signal. Off-ICP and competitor ads are dropped entirely.
    """
    today = today or date.today()
    best: dict = {}
    for p in postings:
        if p.is_agency or not p.category:
            continue
        key = p.company_norm or normalize_company(p.company)
        rank = (_posting_date(p), score_posting(p, today))
        cur = best.get(key)
        if cur is None or rank > cur[0]:
            best[key] = (rank, p)
    return [v[1] for v in best.values()]


# ---------------------------------------------------------------------------
# Company roll-up
# ---------------------------------------------------------------------------

@dataclass
class RoleLead:
    role: str            # display title
    category: str
    rate: str
    headcount: Optional[int]
    count: int           # number of ad instances for this role at this company
    days_open: int
    repost_count: int
    urgency: bool
    locations: List[str]
    score: int


@dataclass
class CompanyLead:
    company: str
    score: int
    category: str        # primary (top role's) category
    rate: str
    total_headcount: int
    max_days_open: int
    repost_count: int
    urgency: bool
    locations: List[str]
    roles: List[RoleLead] = field(default_factory=list)

    @property
    def top_role(self) -> Optional[RoleLead]:
        return self.roles[0] if self.roles else None


def _headcount_int(posting: JobPosting) -> int:
    return posting.headcount if isinstance(posting.headcount, int) else 0


def rollup_company_leads(
    postings: List[JobPosting], today: Optional[date] = None
) -> List[CompanyLead]:
    """Rank DIRECT EMPLOYERS by summed lead score. Agencies & out-of-ICP dropped.

    repost_count for a role = how many times that company+normalized-role appears
    across the whole posting set (e.g. the same welder ad in four cities -> 4).
    """
    today = today or date.today()

    # repost_count across the entire set (before filtering), per company+role.
    repost_map: dict = {}
    for p in postings:
        repost_map[(p.company_norm, p.title_norm)] = (
            repost_map.get((p.company_norm, p.title_norm), 0) + 1
        )

    # Keep only direct employers with an in-ICP category.
    leads_in = [
        p for p in postings if not p.is_agency and p.category
    ]
    for p in leads_in:
        p.repost_count = repost_map.get((p.company_norm, p.title_norm), 1)

    # Group company -> role -> postings.
    companies: dict = {}
    for p in leads_in:
        c = companies.setdefault(
            p.company_norm, {"display": p.company, "roles": {}}
        )
        c["roles"].setdefault(p.title_norm, []).append(p)

    out: List[CompanyLead] = []
    for cnorm, c in companies.items():
        role_leads: List[RoleLead] = []
        for rnorm, ps in c["roles"].items():
            role_score = sum(score_posting(p, today) for p in ps)
            hc = sum(_headcount_int(p) for p in ps)
            d_open = max(days_open(p, today) for p in ps)
            reposts = max(p.repost_count for p in ps)
            urgent = any(p.urgency for p in ps)
            locs = sorted({p.location for p in ps if p.location})
            cat = ps[0].category
            role_leads.append(
                RoleLead(
                    role=ps[0].title,
                    category=cat,
                    rate=category_rate(cat),
                    headcount=hc if hc else None,
                    count=len(ps),
                    days_open=d_open,
                    repost_count=reposts,
                    urgency=urgent,
                    locations=locs,
                    score=role_score,
                )
            )
        role_leads.sort(key=lambda r: r.score, reverse=True)
        top = role_leads[0]
        out.append(
            CompanyLead(
                company=c["display"],
                score=sum(r.score for r in role_leads),
                category=top.category,
                rate=top.rate,
                total_headcount=sum(r.headcount or 0 for r in role_leads),
                max_days_open=max(r.days_open for r in role_leads),
                repost_count=max(r.repost_count for r in role_leads),
                urgency=any(r.urgency for r in role_leads),
                locations=sorted({l for r in role_leads for l in r.locations}),
                roles=role_leads,
            )
        )

    out.sort(key=lambda l: l.score, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Pitch line (German)
# ---------------------------------------------------------------------------

def pitch_line(lead: CompanyLead) -> str:
    """A German one-liner the sales team can paste into outreach."""
    role = lead.top_role
    if role is None:
        return ""
    headcount = role.headcount if role.headcount else "Mehrere"
    location = role.locations[0] if role.locations else "Deutschland"
    urgent = ", dringend ausgeschrieben" if lead.urgency else ""
    # Drop a leading count from the role name so we don't print "20× 20 ...".
    role_name = re.sub(r"^\s*\d+\s*[x×]?\s*", "", role.role).strip() or role.role
    return (
        f"{lead.company}: {headcount}× {role_name} in {location}, "
        f"seit {role.days_open} Tagen offen{urgent}. "
        f"→ Hirewright {lead.category}, ab {lead.rate}, CEE-Pipeline, "
        f"Abrechnung nur nach geleisteten Stunden."
    )


def category_summary(leads: List[CompanyLead]) -> List[Tuple[str, int, int]]:
    """Per-category (category, lead_count, total_headcount) for the summary."""
    agg: dict = {}
    for lead in leads:
        for role in lead.roles:
            cat = role.category
            entry = agg.setdefault(cat, [0, 0])
            entry[0] += 1
            entry[1] += role.headcount or 0
    rows = [(cat, n, hc) for cat, (n, hc) in agg.items()]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows
