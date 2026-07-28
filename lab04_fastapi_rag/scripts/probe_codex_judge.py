from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.judge_client import BlindJudgeInput, run_judge_attempt  # noqa: E402
from src.judge_config import load_judge_config  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用非正式人工样本真实核验H3 Codex Judge候选配置。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def _next_attempt(probe_dir: Path) -> Path:
    existing = sorted(
        path
        for path in probe_dir.glob("attempt_*")
        if path.is_dir() and path.name.removeprefix("attempt_").isdigit()
    )
    if len(existing) >= 3:
        raise RuntimeError("H3 Judge同一探针已失败或执行三次，停止继续尝试")
    return probe_dir / f"attempt_{len(existing) + 1:03d}"


def main() -> int:
    args = parse_args()
    print("[检查点4/H3] 真实核验Codex Judge候选配置")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        if not (run_dir / "manifest.json").is_file():
            raise FileNotFoundError("缺少实验运行manifest")
        config = load_judge_config(require_frozen=False)
        probe = BlindJudgeInput(
            question_id="H3_JUDGE_PROBE",
            question="FastAPI的response_model如何帮助约束输出并保护敏感字段？",
            required_points=(
                "response_model定义输出结构",
                "FastAPI按输出模型校验和过滤返回数据",
                "只输出模型声明字段可避免暴露敏感字段",
            ),
            optional_points=("可用于生成OpenAPI Schema",),
            critical_errors=("声称response_model只影响编辑器提示",),
            final_answer=(
                "response_model定义接口输出结构，FastAPI会据此校验并过滤"
                "返回数据。只返回模型声明的字段，可以避免把密码等敏感字段"
                "暴露给客户端。"
            ),
            cited_chunks=(
                {
                    "chunk_id": "h3_probe_chunk_001",
                    "source_path": "h3_probe/not_formal_evaluation.md",
                    "section_path": "H3人工探针",
                    "content": (
                        "response_model用于定义输出数据结构。FastAPI会按照"
                        "输出模型校验并过滤返回数据，只保留模型声明的字段，"
                        "从而避免返回输入对象中的敏感信息。"
                    ),
                },
            ),
        )
        attempt_dir = _next_attempt(
            run_dir / "judge" / config.probe_series
        )
        result = run_judge_attempt(
            probe,
            attempt_dir=attempt_dir,
            config=config,
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"Codex Judge探针失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"状态：{result['status']}")
    print(f"模型：{result['model']}")
    print(f"推理强度：{result['reasoning_effort']}")
    print(f"CLI：{result['cli_version']}")
    print(f"只读Sandbox：{result['sandbox'] == 'read-only'}")
    print(f"禁止工具事件：{result['forbidden_events']}")
    print(f"耗时：{result['elapsed_seconds']:.3f}秒")
    print(
        "运行记录："
        f"judge/{config.probe_series}/{result['attempt']}/"
    )
    if result["status"] != "judged":
        print("探针未通过；不得冻结Judge配置或运行正式Judge。")
        return 1
    output = result["output"]
    print(f"回答等级：{output['answer_grade']}")
    print("JSON Schema与必答点精确划分均通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
