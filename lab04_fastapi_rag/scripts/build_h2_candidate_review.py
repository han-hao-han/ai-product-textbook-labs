from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.h2_questions import (  # noqa: E402
    load_gate_policy,
    load_h2_question_set,
)
from src.h2_review import render_h2_candidate_review  # noqa: E402
from src.io_utils import read_json, write_text_atomic  # noqa: E402
from src.paths import (  # noqa: E402
    CALIBRATION_QUESTIONS_PATH,
    EVALUATION_QUESTIONS_PATH,
    RETRIEVAL_GATE_POLICY_PATH,
)
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成不含检索分数的H2人工审阅文档。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[H2/候选审阅] 生成人工检查文档")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        audit_path = run_dir / "calibration" / "h2_candidate_audit.json"
        if not audit_path.is_file():
            raise FileNotFoundError("缺少h2_candidate_audit.json")
        output = run_dir / "calibration" / "h2_candidate_review.md"
        if output.exists():
            raise FileExistsError("H2候选审阅文档已存在，拒绝覆盖")
        calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
        evaluation = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
        gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)
        audit = read_json(audit_path)
        if (
            audit["calibration"]["sha256"] != calibration.sha256
            or audit["evaluation"]["sha256"] != evaluation.sha256
        ):
            raise ValueError("H2候选文件已在审计后变化，请创建新运行重新审计")
        markdown = render_h2_candidate_review(
            calibration,
            evaluation,
            gate_policy,
            audit,
        )
        write_text_atomic(output, markdown)
    except (
        FileExistsError,
        FileNotFoundError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"H2审阅文档生成失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print("状态：passed")
    print("检索分数：未读取")
    print("生成文件：calibration/h2_candidate_review.md")
    print("请人工检查全部80题后确认或提出修改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
