from __future__ import annotations

import re
import unicodedata
from typing import Any


_NATIONAL_ID_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"
    r"|\d{15}"
    r")(?!\d)"
)
_LONG_DIGIT_PATTERN = re.compile(r"(?<!\d)\d{15,18}[Xx]?(?!\d)")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8})(?!\d)"
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
)

_LABEL_RULES = (
    (
        "person_identity",
        re.compile(
            r"姓名|姓\s*名|名字|申请人|负责人|联系人|经办人|"
            r"法定代表人|法人|授权领取人|项目经理|工程师|检查员|"
            r"施工员|班组长|存款人名称|人员分工|签署人|面试官|"
            r"应聘者|申报人|填表人|审核人|审批人|批准人|监理|"
            r"考生|教师|员工|参加确认人"
        ),
        20,
        "high",
    ),
    ("birth_date", re.compile(r"出生|生日"), 6, "medium"),
    ("address", re.compile(r"地址|住址|户籍|籍贯"), 8, "medium"),
    (
        "financial_or_account",
        re.compile(
            r"银行账号|银行卡号|账户|帐号|账号|开户银行|开户许可证|"
            r"存款人|许可证编号|许可证核准号"
        ),
        24,
        "high",
    ),
    ("signature", re.compile(r"签名|签字|手印"), 18, "high"),
    (
        "confidential_business_information",
        re.compile(r"保密文件|秘密文件|密封|商业秘密"),
        18,
        "high",
    ),
    ("face_photo", re.compile(r"照片|相片|头像"), 15, "high"),
    (
        "health_information",
        re.compile(r"健康|疾病|病史|医疗|诊断|体检"),
        14,
        "high",
    ),
)


def screen_document_privacy(document: dict[str, Any]) -> dict[str, Any]:
    """Return annotation-only privacy signals without retaining matched literals."""
    signals: list[dict[str, Any]] = []
    hard_exclusion_reasons: list[str] = []

    for entity in document["document"]:
        entity_id = entity["id"]
        text = _normalize_text(str(entity.get("text", "")))
        if not text:
            continue

        if _contains_national_id(text):
            _append_signal(
                signals,
                category="national_id",
                entity_id=entity_id,
                severity="critical",
                score=100,
                matched_by="value_pattern",
            )
            hard_exclusion_reasons.append("national_id_value")

        if _PHONE_PATTERN.search(text):
            _append_signal(
                signals,
                category="phone",
                entity_id=entity_id,
                severity="high",
                score=22,
                matched_by="value_pattern",
            )
        if _EMAIL_PATTERN.search(text):
            _append_signal(
                signals,
                category="email",
                entity_id=entity_id,
                severity="high",
                score=22,
                matched_by="value_pattern",
            )

        if "身份证" in text or "公民身份号码" in text or "证件号码" in text:
            _append_signal(
                signals,
                category="national_id_field",
                entity_id=entity_id,
                severity="medium",
                score=8,
                matched_by="field_label",
            )

        for category, pattern, score, severity in _LABEL_RULES:
            if pattern.search(text):
                _append_signal(
                    signals,
                    category=category,
                    entity_id=entity_id,
                    severity=severity,
                    score=score,
                    matched_by="field_label",
                )

    deduplicated = _deduplicate_signals(signals)
    total_score = sum(signal["score"] for signal in deduplicated)
    return {
        "screen_version": "annotation-privacy-v2",
        "method": "local_annotation_text_only",
        "hard_excluded": bool(hard_exclusion_reasons),
        "hard_exclusion_reasons": sorted(set(hard_exclusion_reasons)),
        "risk_score": total_score,
        "risk_tier": _risk_tier(total_score),
        "signal_categories": sorted(
            {signal["category"] for signal in deduplicated}
        ),
        "signals": deduplicated,
        "matched_literals_stored": False,
        "human_image_review_required": True,
    }


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def _contains_national_id(text: str) -> bool:
    if _NATIONAL_ID_PATTERN.search(text) or _LONG_DIGIT_PATTERN.search(text):
        return True
    compact = re.sub(r"[^0-9Xx*＊]", "", text).replace("＊", "*")
    if "*" in compact:
        digit_count = sum(character.isdigit() for character in compact)
        if 15 <= len(compact) <= 19 and digit_count >= 6:
            return True
    compact = compact.replace("*", "")
    if not 15 <= len(compact) <= 19:
        return False
    return bool(
        _NATIONAL_ID_PATTERN.fullmatch(compact)
        or _LONG_DIGIT_PATTERN.fullmatch(compact)
    )


def _append_signal(
    signals: list[dict[str, Any]],
    *,
    category: str,
    entity_id: Any,
    severity: str,
    score: int,
    matched_by: str,
) -> None:
    signals.append(
        {
            "category": category,
            "severity": severity,
            "score": score,
            "matched_by": matched_by,
            "entity_ids": [entity_id],
        }
    )


def _deduplicate_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for signal in signals:
        key = signal["category"], signal["matched_by"]
        if key not in grouped:
            grouped[key] = dict(signal)
            grouped[key]["entity_ids"] = list(signal["entity_ids"])
            continue
        grouped[key]["entity_ids"].extend(signal["entity_ids"])

    result = []
    for signal in grouped.values():
        signal["entity_ids"] = sorted(
            set(signal["entity_ids"]), key=lambda value: str(value)
        )
        result.append(signal)
    return sorted(result, key=lambda item: (item["category"], item["matched_by"]))


def _risk_tier(score: int) -> str:
    if score == 0:
        return "none_detected"
    if score < 15:
        return "low"
    if score < 35:
        return "medium"
    return "high"
