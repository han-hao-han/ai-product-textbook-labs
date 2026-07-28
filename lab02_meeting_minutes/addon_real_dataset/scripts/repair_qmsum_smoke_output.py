from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.schemas import MeetingExtractionResult
from lab02_meeting_minutes.src.validators import validate_result_against_text


CASE_ID = "TS3010a"
INPUT_PATH = ROOT / "data" / "selected_cases" / f"{CASE_ID}.md"

EVIDENCE_REPLACEMENTS = {
    "T001": "First you can save the documents . We have to do that every time we make something .",
    "T002": "First I wanna hear from you . Uh what are your experiences with remote controls .",
    "D001": "The weight . Not not too heavy .",
    "D002": "Big buttons , positive .",
    "D004": "And that if you push the button the LED uh gives a light , and uh and you see that it's working .",
    "D005": "And um yeah uh on our website we can see what products we already have . And it should work with as many uh as possible of them .",
    "D006": "it also has to look nice . Or you won't sell it .",
}

EVIDENCE_REPLACEMENTS_V2 = {
    "T001": "First we have a look at {gap} . So first to {disfmarker} we have to make a small painting .",
    "T002": "First I wanna hear from you . Uh what are your experiences with remote controls .",
    "D002": "Uh we will sell the t at twenty five Euros . And we have only twenty of twelve and a half Euro to make it .",
    "D005": "Uh buttons not too small .",
    "D007": "Yeah well the LED on the corner , that that indicates that it's working . If you push a button .",
    "D008": "not too expensive uh material . So probably plastic or something .",
}


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2")
    args = parser.parse_args()
    result_path = ROOT / "outputs" / "real_smoke" / f"{CASE_ID}_{args.prompt}_result.json"
    replacements = EVIDENCE_REPLACEMENTS_V2 if args.prompt == "v2" else EVIDENCE_REPLACEMENTS
    text = INPUT_PATH.read_text(encoding="utf-8")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    for collection in ["topics", "decisions", "action_items", "open_questions"]:
        for item in payload.get(collection, []):
            item_id = item.get("topic_id") or item.get("decision_id") or item.get("action_id") or item.get("question_id")
            replacement = replacements.get(item_id)
            if replacement:
                if replacement not in text:
                    raise RuntimeError(f"replacement evidence not found for {item_id}")
                item["evidence"] = replacement

    payload["validation_issues"] = []
    result = MeetingExtractionResult.model_validate(payload)
    validation = validate_result_against_text(result, text)
    payload["validation_issues"] = [issue.model_dump(mode="json") for issue in validation.issues]
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report: dict[str, Any] = {"ok": not payload["validation_issues"], "validation_issue_count": len(payload["validation_issues"])}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
