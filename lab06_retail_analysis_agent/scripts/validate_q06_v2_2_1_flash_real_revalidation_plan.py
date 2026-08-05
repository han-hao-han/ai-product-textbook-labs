"""Create offline evidence for the V2.2.1 Q06 real-call plan."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q06_v2_2_1_flash_real_revalidation_plan import (  # noqa: E402
    Q06V2_2_1FlashRealPlanError,
    load_q06_v2_2_1_flash_real_plan,
    validate_q06_v2_2_1_flash_real_plan,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _probe(mutator: Callable[[dict[str, Any]], None]) -> bool:
    changed = deepcopy(load_q06_v2_2_1_flash_real_plan())
    mutator(changed)
    try:
        validate_q06_v2_2_1_flash_real_plan(changed)
    except Q06V2_2_1FlashRealPlanError:
        return True
    return False


def main() -> int:
    preflight = validate_q06_v2_2_1_flash_real_plan()
    probes = {
        "broader_question_scope_rejected": _probe(
            lambda plan: plan["scope"].update(
                {"question_ids": ["Q06", "Q09"]}
            )
        ),
        "fourth_response_rejected": _probe(
            lambda plan: plan["hard_limits"].update(
                {"response_attempt_upper_bound": 4}
            )
        ),
        "automatic_retry_rejected": _probe(
            lambda plan: plan["hard_limits"].update(
                {"automatic_retry_count": 1}
            )
        ),
        "missing_terminal_json_mode_rejected": _probe(
            lambda plan: plan["request_protocol"][
                "response_format_sequence"
            ].__setitem__(2, None)
        ),
        "dsml_repair_rejected": _probe(
            lambda plan: plan["response_gates"][2].update(
                {"dsml_or_markdown_repair_allowed": True}
            )
        ),
        "premature_real_authority_rejected": _probe(
            lambda plan: plan["authorization"].update(
                {
                    "status": "authorized_by_user",
                    "real_model_calls_allowed": True,
                }
            )
        ),
        "premature_runner_ready_claim_rejected": _probe(
            lambda plan: plan["implementation"].update(
                {
                    "guarded_runner": "scripts/run.py",
                    "guarded_runner_status": "ready",
                }
            )
        ),
    }
    passed = all(probes.values())
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q06_v2_2_1_flash_real_plan_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-q06-v2.2.1-flash-real-plan-offline-v1"
        ),
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "question_ids": list(preflight.question_ids),
        "model": preflight.model,
        "response_attempt_upper_bound": (
            preflight.response_attempt_upper_bound
        ),
        "automatic_retry_count": preflight.automatic_retry_count,
        "tool_choice_sequence": list(preflight.tool_choice_sequence),
        "response_format_sequence": list(
            preflight.response_format_sequence
        ),
        "real_model_calls_allowed": preflight.real_model_calls_allowed,
        "guarded_runner_ready": preflight.guarded_runner_ready,
        "checks": list(preflight.checks),
        "negative_probes": probes,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "privacy_audit": {
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
