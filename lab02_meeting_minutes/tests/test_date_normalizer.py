from lab02_meeting_minutes.src.date_normalizer import normalize_due_date, repair_due_date_raw


def test_normalizes_relative_dates_with_meeting_date() -> None:
    assert normalize_due_date("本周五前", "2026-07-20") == "2026-07-24"
    assert normalize_due_date("下周三前", "2026-07-20") == "2026-07-29"
    assert normalize_due_date("明天下午", "2026-07-20") == "2026-07-21"


def test_does_not_normalize_relative_date_without_meeting_date() -> None:
    assert normalize_due_date("下周三前", None) is None


def test_keeps_fuzzy_dates_unresolved() -> None:
    assert normalize_due_date("灰度上线前", "2026-07-20") is None


def test_repairs_qmsum_due_date_raw_to_evidence_month() -> None:
    evidence = "- Grad A: those experiments done by {disfmarker} by the time quals come {disfmarker} come around in July ."
    raw = "by the time quals come around in July"
    assert repair_due_date_raw(raw, evidence) == "July"
