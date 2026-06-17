"""Hirewright sales-lead engine — StepStone (DE) prospecting.

Scans public German job ads and surfaces direct employers with a blue-collar
labour gap that Hirewright could supply (skilled/semi-skilled CEE crews, leased
by the hour).

Public company + job-ad data only. No personal data is collected, stored, or
inferred (no contact names, emails, or phone numbers).
"""

from .core import (
    JobPosting,
    normalize_company,
    normalize_title,
    parse_headcount,
    parse_posted_date,
)
from .targets import (
    CATEGORIES,
    AGENCY_MARKERS,
    URGENCY_TERMS,
    classify_category,
    is_staffing_agency,
    detect_urgency,
    category_rate,
)
from .scoring import (
    score_posting,
    rollup_company_leads,
    pitch_line,
    category_summary,
    CompanyLead,
    RoleLead,
)
from .storage import Store
from .fetchers import Fetcher, SampleFetcher, ApifyStepStoneFetcher

__all__ = [
    "JobPosting",
    "normalize_company",
    "normalize_title",
    "parse_headcount",
    "parse_posted_date",
    "CATEGORIES",
    "AGENCY_MARKERS",
    "URGENCY_TERMS",
    "classify_category",
    "is_staffing_agency",
    "detect_urgency",
    "category_rate",
    "score_posting",
    "rollup_company_leads",
    "pitch_line",
    "category_summary",
    "CompanyLead",
    "RoleLead",
    "Store",
    "Fetcher",
    "SampleFetcher",
    "ApifyStepStoneFetcher",
]
