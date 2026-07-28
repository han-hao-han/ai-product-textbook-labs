from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.generation_client import prepare_generation_client  # noqa: E402
from src.generation_config import load_generation_config  # noqa: E402
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="准备并真实核验冻结的百炼结构化生成客户端。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点3/步骤1] 准备结构化生成客户端")
    try:
        source_config = load_source_config()
        generation_config = load_generation_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        require_compatible_run(run_dir, source_config)
        result = prepare_generation_client(run_dir, generation_config)
    except (
        FileExistsError,
        FileNotFoundError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"生成客户端准备失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"状态：{result['status']}")
    print(f"提供商：{result['provider']} ({result['region']})")
    print(f"模型：{result['model']}")
    print(f"JSON Mode：{result['structured_output']}")
    print(f"在线模型调用：{result['online_model_called']}")
    print(f"API Key已保存：{result['api_key_saved']}")
    print(f"凭据来源：{result['credential_source']}")
    print(f"已检查lab04/.env：{result['project_dotenv_checked']}")
    print(f"输出Token上限已发送：{result['output_token_cap_sent']}")
    print(f"运行记录：generation/attempts/{result['attempt']}/")
    if result["status"] == "retrieval_only":
        print(
            "未在当前环境或lab04_fastapi_rag/.env中发现DASHSCOPE_API_KEY，"
            "或发生临时调用失败；"
            "当前可体验检索和门控，但不会在线生成。"
        )
        print(
            "配置凭据后重新运行本命令，将创建新的attempt，不覆盖本次记录。"
        )
    elif result["status"] == "blocked":
        print("客户端被阻断；请查看脱敏错误，修复后显式重新运行准备命令。")
    else:
        print("分类与回答JSON Mode均通过真实账号测试。")
        print("下一步：streamlit run app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
