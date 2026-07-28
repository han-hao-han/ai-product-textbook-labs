from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding_config import load_embedding_config  # noqa: E402
from src.embedding_model import (  # noqa: E402
    EmbeddingError,
    prepare_embedding_model,
)
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载并核验固定Revision的本地Embedding模型。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点2/步骤1] 准备固定Revision的Embedding模型")
    try:
        source_config = load_source_config()
        embedding_config = load_embedding_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        run_manifest = require_compatible_run(run_dir, source_config)
        result = prepare_embedding_model(
            run_dir,
            embedding_config,
            str(run_manifest["frozen_device"]),
        )
    except (
        EmbeddingError,
        FileExistsError,
        FileNotFoundError,
        ImportError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"Embedding模型准备失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print("未进入索引构建；失败记录位于model/failures/。")
        return 1

    print(f"状态：{result['status']}")
    print(f"模型：{result['model_id']}")
    print(f"Revision：{result['revision']}")
    print(f"License：{result['license']}")
    print(f"设备：{result['device']}")
    print(f"批大小：{result['batch_size']}")
    print(f"维度：{result['dimension']}")
    print(
        "文档Embedding范数："
        f"{result['document_embedding_test']['min_l2_norm']:.8f}"
    )
    print(
        "查询Embedding范数："
        f"{result['query_embedding_test']['min_l2_norm']:.8f}"
    )
    print(f"必要文件：{len(result['required_files'])}")
    print(f"下载尝试次数：{result['download_attempts']}")
    print(f"准备耗时：{result['elapsed_seconds']:.3f}秒")
    print("生成文件：model/embedding_model.json")
    print("下一步：")
    print(
        "python scripts/build_index.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
