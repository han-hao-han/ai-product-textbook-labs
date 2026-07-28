from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.checkpoint_report import write_checkpoint1_report  # noqa: E402
from src.corpus_builder import CorpusBuildError, build_corpus  # noqa: E402
from src.io_utils import read_json  # noqa: E402
from src.run_state import require_compatible_run, resolve_run_dir  # noqa: E402
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="清洗冻结中文文档、展开代码依赖并生成可追溯Chunk。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点1/步骤3] 清洗Markdown并构建Chunk")
    config = load_source_config()
    run_dir = resolve_run_dir(args.experiment_run_id)
    source_manifest = None
    try:
        require_compatible_run(run_dir, config)
        manifest_path = run_dir / "source" / "document_manifest.json"
        if manifest_path.is_file():
            source_manifest = read_json(manifest_path)
        corpus_manifest = build_corpus(run_dir, config)
    except (
        CorpusBuildError,
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
    ) as error:
        report_md, _ = write_checkpoint1_report(
            run_dir=run_dir,
            config=config,
            status="blocked",
            source_manifest=source_manifest,
            errors=[f"{type(error).__name__}: {error}"],
        )
        print(f"语料构建失败：{type(error).__name__}: {error}", file=sys.stderr)
        print(
            "检查点报告："
            f"{report_md.relative_to(run_dir).as_posix()}",
            file=sys.stderr,
        )
        return 1

    status = corpus_manifest["status"]
    report_md, report_json = write_checkpoint1_report(
        run_dir=run_dir,
        config=config,
        status=status,
        source_manifest=source_manifest,
        corpus_manifest=corpus_manifest,
    )
    print(f"状态：{status}")
    print(f"清洗文档：{corpus_manifest['document_count']}")
    print(f"Chunk：{corpus_manifest['chunk_count']}")
    print(f"Chunk策略：{corpus_manifest['chunking_strategy']}")
    print(f"含代码Chunk：{corpus_manifest['chunks_with_code']}")
    print(f"含表格Chunk：{corpus_manifest['chunks_with_table']}")
    print(
        "合并多个相关小节："
        f"{corpus_manifest['chunks_with_multiple_sections']}"
    )
    print(f"含Overlap：{corpus_manifest['chunks_with_overlap']}")
    print(
        "位于500～800："
        f"{corpus_manifest['chunks_in_target_range']} "
        f"（{corpus_manifest['target_range_ratio']:.1%}）"
    )
    print(f"低于目标下限：{corpus_manifest['chunks_under_target_min']}")
    print(f"低于下限原因：{corpus_manifest['under_min_reason_counts']}")
    print(f"超过目标上限：{corpus_manifest['chunks_over_target_max']}")
    print(f"超过上限原因：{corpus_manifest['over_max_reason_counts']}")
    print(f"长度分位数：{corpus_manifest['token_count_percentiles']}")
    print(f"Token计数方法：{corpus_manifest['token_count_method']}")
    print(f"语料SHA-256：{corpus_manifest['corpus_sha256']}")
    print(
        "报告："
        f"{report_md.relative_to(run_dir).as_posix()} "
        f"和 {report_json.relative_to(run_dir).as_posix()}"
    )
    print("已到达检查点1，请查看报告和代表Chunk后再决定是否继续检查点2。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
