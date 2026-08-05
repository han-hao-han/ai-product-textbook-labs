"""Replay the saved real Q06 report through the V2.2.2 candidate."""

from __future__ import annotations

import json
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_evidence_semantic_boundary_v2_2_2 import (  # noqa: E402
    ReportEvidenceSemanticBoundaryError,
    load_report_evidence_semantic_contract,
    replay_v2_2_1_real_report,
    validate_v2_2_2_contract,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _probe(mutator: Callable[[dict[str, Any]], None]) -> bool:
    changed = deepcopy(load_report_evidence_semantic_contract())
    mutator(changed)
    try:
        validate_v2_2_2_contract(changed)
    except ReportEvidenceSemanticBoundaryError:
        return True
    return False


def main() -> int:
    validate_v2_2_2_contract()
    replay = replay_v2_2_1_real_report()
    hard_counts = Counter(
        issue.code for issue in replay.deterministic_semantic_issues
    )
    manual_counts = Counter(
        issue.code for issue in replay.manual_review_flags
    )
    formal_issue_counts = Counter(
        issue.code for issue in replay.formal_validation_issues
    )
    formal_manual_counts = Counter(
        issue.code for issue in replay.formal_manual_review_flags
    )
    probes = {
        "cross_claim_fact_borrowing_rejected": _probe(
            lambda value: value["claim_evidence_candidate"].update(
                {"cross_claim_fact_borrowing_allowed": True}
            )
        ),
        "program_fact_injection_rejected": _probe(
            lambda value: value["claim_evidence_candidate"].update(
                {"program_may_add_missing_fact_reference": True}
            )
        ),
        "automatic_report_repair_rejected": _probe(
            lambda value: value["scope"].update(
                {"automatic_report_repair_allowed": True}
            )
        ),
        "real_model_authority_rejected": _probe(
            lambda value: value["scope"].update(
                {"real_model_calls_allowed": True}
            )
        ),
        "human_final_decision_removal_rejected": _probe(
            lambda value: value["manual_semantic_review_candidate"].update(
                {"human_remains_final_decision_maker": False}
            )
        ),
    }
    passed = (
        len(replay.current_numeric_issues) == 16
        and len(replay.canonical_numeric_issues) == 1
        and replay.canonical_numeric_issues[0].token_or_phrase == "3"
        and len(replay.deterministic_semantic_issues) == 7
        and hard_counts
        == {
            "unsupported_significance_claim": 1,
            "unsupported_quantity_superlative": 1,
            "unsupported_order_superlative": 1,
            "unsupported_average_value_claim": 2,
            "unsupported_product_classification": 2,
        }
        and len(replay.manual_review_flags) == 8
        and manual_counts
        == {
            "seasonality_interpretation": 3,
            "causal_or_effect_claim": 2,
            "inventory_action": 2,
            "pricing_or_logistics_action": 1,
        }
        and replay.formal_validation_status == "failed"
        and len(replay.formal_validation_issues) == 8
        and formal_issue_counts
        == {
            "untraceable_numeric_token": 1,
            "unsupported_significance_claim": 1,
            "unsupported_quantity_superlative": 1,
            "unsupported_order_superlative": 1,
            "unsupported_average_value_claim": 2,
            "unsupported_product_classification": 2,
        }
        and len(replay.formal_manual_review_flags) == 8
        and formal_manual_counts == manual_counts
        and replay.terminal_json_parse_passed
        and replay.control_schema_passed
        and replay.source_response_unchanged
        and all(probes.values())
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"report_evidence_semantic_v2_2_2_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-report-evidence-semantic-v2.2.2-offline-v1"
        ),
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "source_run_id": (
            "q06_v2_2_1_flash_real_revalidation_"
            "20260803T153719_794668+0800"
        ),
        "source_sha256": replay.source_sha256,
        "source_response_unchanged": replay.source_response_unchanged,
        "terminal_json_parse_passed": replay.terminal_json_parse_passed,
        "control_schema_passed": replay.control_schema_passed,
        "current_numeric_issue_count": len(replay.current_numeric_issues),
        "canonical_numeric_issue_count": len(
            replay.canonical_numeric_issues
        ),
        "canonical_numeric_issues": [
            asdict(issue) for issue in replay.canonical_numeric_issues
        ],
        "deterministic_semantic_issue_count": len(
            replay.deterministic_semantic_issues
        ),
        "deterministic_semantic_issue_counts": dict(hard_counts),
        "deterministic_semantic_issues": [
            asdict(issue) for issue in replay.deterministic_semantic_issues
        ],
        "manual_review_flag_count": len(replay.manual_review_flags),
        "manual_review_flag_counts": dict(manual_counts),
        "manual_review_flags": [
            asdict(issue) for issue in replay.manual_review_flags
        ],
        "formal_report_validation": {
            "status": replay.formal_validation_status,
            "issue_count": len(replay.formal_validation_issues),
            "issue_counts": dict(formal_issue_counts),
            "issues": [
                asdict(issue)
                for issue in replay.formal_validation_issues
            ],
            "manual_review_flag_count": len(
                replay.formal_manual_review_flags
            ),
            "manual_review_flag_counts": dict(formal_manual_counts),
            "manual_review_flags": [
                asdict(issue)
                for issue in replay.formal_manual_review_flags
            ],
            "report_rendered": False,
            "automatic_repair_performed": False,
        },
        "negative_probes": probes,
        "candidate_result": "failed_without_auto_repair",
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "real_model_calls_allowed": False,
        "privacy_audit": {
            "raw_provider_response_duplicated": False,
            "api_key_saved": False,
            "authorization_header_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
