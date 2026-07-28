from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding_config import load_embedding_config  # noqa: E402
from src.embedding_model import EmbeddingError  # noqa: E402
from src.index_builder import IndexBuildError, build_index  # noqa: E402
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用本地冻结Embedding模型构建NumPy精确索引。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点2/步骤2] 构建NumPy精确向量索引")
    try:
        source_config = load_source_config()
        embedding_config = load_embedding_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        run_manifest = require_compatible_run(run_dir, source_config)
        result = build_index(
            run_dir,
            embedding_config,
            str(run_manifest["frozen_device"]),
        )
    except (
        EmbeddingError,
        IndexBuildError,
        FileExistsError,
        FileNotFoundError,
        ImportError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"索引构建失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print("未进入Top 5演示；失败记录位于index/failures/。")
        return 1

    print(f"状态：{result['status']}")
    print(f"矩阵形状：{result['matrix_shape']}")
    print(f"dtype：{result['matrix_dtype']}")
    print(f"L2范数：{result['norm_diagnostics']}")
    print(f"Chunk顺序SHA-256：{result['chunk_order_sha256']}")
    print(f"索引SHA-256：{result['embeddings_sha256']}")
    print(f"最大实际输入Token：{result['embedding_diagnostics']['max_input_tokens']}")
    print(f"截断输入：{result['embedding_diagnostics']['truncated_input_count']}")
    print(f"构建耗时：{result['elapsed_seconds']:.3f}秒")
    print("生成目录：index/current/")
    print("下一步：")
    print(
        "python scripts/demo_retrieval.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
