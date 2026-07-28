from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.checkpoint2_report import write_checkpoint2_report  # noqa: E402
from src.embedding_config import load_embedding_config  # noqa: E402
from src.embedding_model import EmbeddingError  # noqa: E402
from src.index_builder import IndexBuildError  # noqa: E402
from src.retriever import RetrievalError, retrieve_top_k  # noqa: E402
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行冻结问题的NumPy精确Top 5检索并生成检查点2报告。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点2/步骤3] 运行固定问题的Top 5检索")
    try:
        source_config = load_source_config()
        embedding_config = load_embedding_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        run_manifest = require_compatible_run(run_dir, source_config)
        result = retrieve_top_k(
            run_dir,
            embedding_config,
            str(run_manifest["frozen_device"]),
            embedding_config.demo_query,
        )
        report_md, report_json, demo_json = write_checkpoint2_report(
            run_dir,
            embedding_config,
            result,
        )
    except (
        EmbeddingError,
        IndexBuildError,
        RetrievalError,
        FileExistsError,
        FileNotFoundError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"Top 5检索失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print("未到达检查点2；请保留错误信息并检查前置产物。")
        return 1

    print(f"状态：{result['status']}")
    print(f"问题：{result['query']}")
    print(f"相似度：{result['similarity']}")
    print(f"在线生成模型调用：{result['generation_model_called']}")
    print("")
    for hit in result["hits"]:
        section = " > ".join(hit["section_path"])
        print(
            f"Top {hit['rank']} | score={hit['score']:.6f} | "
            f"{hit['page_title']}"
        )
        print(f"  来源：{hit['source_path']}")
        print(f"  章节：{section}")
        print(f"  Chunk：{hit['chunk_id']}")
    print("")
    print(
        "生成文件："
        f"{demo_json.relative_to(run_dir).as_posix()}、"
        f"{report_md.relative_to(run_dir).as_posix()}、"
        f"{report_json.relative_to(run_dir).as_posix()}"
    )
    print("已到达检查点2，请查看Top 5全文和报告后再决定是否继续检查点3。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
