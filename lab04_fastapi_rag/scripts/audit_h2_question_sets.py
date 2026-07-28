from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.h2_questions import (  # noqa: E402
    audit_h2_question_sets,
    load_gate_policy,
    load_h2_question_set,
)
from src.io_utils import read_json, write_json_atomic  # noqa: E402
from src.paths import (  # noqa: E402
    CALIBRATION_QUESTIONS_PATH,
    EVALUATION_QUESTIONS_PATH,
    RETRIEVAL_GATE_POLICY_PATH,
)
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计H2校准题、正式题和门控算法候选，不运行Embedding。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[H2/候选审计] 检查题集配额、来源和数据隔离")
    try:
        source_config = load_source_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        require_compatible_run(run_dir, source_config)
        checkpoint2 = (
            run_dir / "checkpoints" / "checkpoint_2" / "report.json"
        )
        if not checkpoint2.is_file():
            raise FileNotFoundError("缺少检查点2报告")
        source_manifest = read_json(
            run_dir / "source" / "document_manifest.json"
        )
        corpus_manifest = read_json(
            run_dir / "corpus" / "corpus_manifest.json"
        )
        calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
        evaluation = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
        gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)
        included_paths = {
            item["source_path"]
            for item in source_manifest["documents"]
            if item["included_or_excluded"] == "included"
        }
        audit = audit_h2_question_sets(
            calibration,
            evaluation,
            gate_policy,
            included_paths=included_paths,
            source_commit=source_config.commit,
            corpus_sha256=corpus_manifest["corpus_sha256"],
        )
        audit["experiment_run_id"] = run_dir.name
        audit["audited_at"] = datetime.now().astimezone().isoformat()
        output = run_dir / "calibration" / "h2_candidate_audit.json"
        if output.exists():
            raise FileExistsError("H2候选审计结果已存在，拒绝覆盖")
        write_json_atomic(output, audit)
    except (
        FileExistsError,
        FileNotFoundError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"H2候选审计失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"状态：{audit['status']}")
    print(f"候选状态：{audit['review_status']}")
    print(f"校准集：{audit['calibration']['scope_counts']}")
    print(f"正式集：{audit['evaluation']['scope_counts']}")
    print(
        "正式集文档组："
        f"{audit['evaluation']['document_group_counts']}"
    )
    print(
        "正式集题型："
        f"{audit['evaluation']['question_type_counts']}"
    )
    print(
        "含短Python代码题："
        f"{audit['evaluation']['questions_with_short_python_code']}"
    )
    print(f"校准集SHA-256：{audit['calibration']['sha256']}")
    print(f"正式集SHA-256：{audit['evaluation']['sha256']}")
    print("Embedding调用：False")
    print("在线模型调用：False")
    print("生成文件：calibration/h2_candidate_audit.json")
    print("已到达H2人工门；确认题集前不得计算门控阈值。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
