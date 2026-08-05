"""Offline preflight for the reopened V2.1 native-tool mainline."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.native_tool_mainline_revision import (  # noqa: E402
    REVISION_PATH,
    validate_native_tool_mainline_revision,
)


def main() -> int:
    result = validate_native_tool_mainline_revision()
    run_id = datetime.now().astimezone().strftime(
        "v2_1_mainline_revision_%Y%m%dT%H%M%S_%f%z"
    )
    output_root = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-v2.1-mainline-revision-preflight-v1",
        "run_id": run_id,
        "execution_mode": "offline_contract_preflight",
        "contract_path": str(
            REVISION_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "real_network_opened": False,
        "api_key_read": False,
        "real_model_called": False,
        "status": result.status,
        "tool_count": result.tool_count,
        "model_selects_tool": result.model_selects_tool,
        "model_generates_arguments": (
            result.model_generates_arguments
        ),
        "model_decides_continue": result.model_decides_continue,
        "model_organizes_report": result.model_organizes_report,
        "program_builds_charts": result.program_builds_charts,
        "program_preselects_next_tool": (
            result.program_preselects_next_tool
        ),
        "real_model_calls_allowed": (
            result.real_model_calls_allowed
        ),
        "provisional_representative_response_count": (
            result.provisional_representative_response_count
        ),
        "checks": list(result.checks),
        "next_stage": (
            "独立原生工具Mock编排器；"
            "模型同时看到七工具并自主选择，仍不调用真实模型"
        ),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
