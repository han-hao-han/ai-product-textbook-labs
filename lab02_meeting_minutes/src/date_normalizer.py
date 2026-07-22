from __future__ import annotations

import calendar
import re
from datetime import date, timedelta


DATE_NORMALIZER_VERSION = "date_normalizer_v1_h3_draft"

WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
TRANSCRIPT_NOISE_RE = re.compile(r"\{(?:vocalsound|gap|disfmarker|comment|pause|nonvocalsound)\}", re.IGNORECASE)
MONTH_NAME_RE = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", re.IGNORECASE)


def normalize_due_date(raw: str | None, meeting_date: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    explicit = _normalize_explicit_date(value, meeting_date)
    if explicit is not None:
        return explicit
    if meeting_date is None:
        return None
    base = date.fromisoformat(meeting_date)
    if value.startswith("今天"):
        return base.isoformat()
    if value.startswith("明天"):
        return (base + timedelta(days=1)).isoformat()
    if value.startswith("后天"):
        return (base + timedelta(days=2)).isoformat()
    week_match = re.search(r"(本周|下周)([一二三四五六日天])", value)
    if week_match:
        return _normalize_weekday(base, week_match.group(1), week_match.group(2)).isoformat()
    if "月底" in value:
        return date(base.year, base.month, calendar.monthrange(base.year, base.month)[1]).isoformat()
    return None


def repair_due_date_raw(raw: str | None, evidence: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    evidence_text = evidence or ""
    if _contains_noise_tolerant(evidence_text, value):
        return value
    month_match = MONTH_NAME_RE.search(value)
    if month_match and _contains_noise_tolerant(evidence_text, month_match.group(0)):
        return month_match.group(0)
    return value


def _contains_noise_tolerant(text: str, fragment: str) -> bool:
    def normalize(value: str) -> str:
        return "".join(TRANSCRIPT_NOISE_RE.sub("", value).split()).lower()

    return normalize(fragment) in normalize(text)


def _normalize_explicit_date(value: str, meeting_date: str | None) -> str | None:
    iso_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if iso_match:
        return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))).isoformat()
    month_day_match = re.search(r"(\d{1,2})月(\d{1,2})日", value)
    if month_day_match and meeting_date is not None:
        base = date.fromisoformat(meeting_date)
        return date(base.year, int(month_day_match.group(1)), int(month_day_match.group(2))).isoformat()
    return None


def _normalize_weekday(base: date, prefix: str, weekday_text: str) -> date:
    target = WEEKDAY_MAP[weekday_text]
    start_of_week = base - timedelta(days=base.weekday())
    return start_of_week + timedelta(days=target if prefix == "本周" else 7 + target)
