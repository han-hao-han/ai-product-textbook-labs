"""Recover question-scoped provider responses from preserved case JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.q01_q10_batch_a_safe_runner import _write_json


def recover(run_dir: Path) -> dict[str, Any]:
    target = run_dir / "responses" / "by_question"
    manifest_path = target / "recovery_manifest.json"
    if manifest_path.exists():
        raise ValueError("recovery manifest already exists; refusing to overwrite")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    recovered: dict[str, int] = {}
    for question_id in summary["question_ids_executed"]:
        case_path = run_dir / f"{question_id}.json"
        case = json.loads(case_path.read_text(encoding="utf-8"))
        responses = case.get("outcome", {}).get("raw_responses", [])
        for index, response in enumerate(responses, start=1):
            _write_json(
                target / question_id / f"response_{index:03d}.json",
                {
                    "schema_version": (
                        "1.5.6-h3-question-scoped-recovered-response-v1"
                    ),
                    "question_id": question_id,
                    "question_response_index": index,
                    "source_case_file": f"{question_id}.json",
                    "provider_response": response,
                },
                secret="",
            )
        recovered[question_id] = len(responses)
    manifest = {
        "schema_version": "1.5.6-h3-response-evidence-recovery-v1",
        "run_id": summary["run_id"],
        "reason": (
            "per-question response indices collided in the shared crash-safe "
            "response directory"
        ),
        "source_case_json_preserved": True,
        "original_files_deleted": False,
        "recovered_response_counts": recovered,
        "api_key_saved": False,
        "request_headers_saved": False,
        "request_body_saved": False,
    }
    _write_json(manifest_path, manifest, secret="")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(recover(args.run_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
