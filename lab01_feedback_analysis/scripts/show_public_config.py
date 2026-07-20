from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values


SCRIPT_PATH = Path(__file__).resolve()
REPOSITORY_ROOT = SCRIPT_PATH.parents[2]
ENV_PATH = REPOSITORY_ROOT / ".env"


def first_value(
    values: dict,
    *names: str,
    default: str = "未配置",
) -> str:
    """读取第一个存在且非空的环境变量。"""
    for name in names:
        value = values.get(name)

        if value is not None:
            text = str(value).strip()

            if text:
                return text

    return default


def configured_text(
    values: dict,
    *names: str,
) -> str:
    """只显示密钥是否配置，不显示任何密钥字符。"""
    for name in names:
        value = values.get(name)

        if value is not None and str(value).strip():
            return "已配置（敏感内容已隐藏）"

    return "未配置"


def main() -> None:
    if not ENV_PATH.exists():
        raise FileNotFoundError(
            "项目根目录没有找到 .env"
        )

    values = dict(
        dotenv_values(ENV_PATH)
    )

    default_model = first_value(
        values,
        "LLM_MODEL",
        "DEEPSEEK_MODEL",
    )

    default_base_url = first_value(
        values,
        "LLM_BASE_URL",
        "DEEPSEEK_BASE_URL",
    )

    default_temperature = first_value(
        values,
        "LLM_TEMPERATURE",
        "DEEPSEEK_TEMPERATURE",
        default="0",
    )

    print(
        "=== 实验 1.5.1 API 配置 ==="
    )
    print(
        "敏感信息状态：已隐藏"
    )
    print()
    print("默认平台：DeepSeek")
    print(f"默认模型：{default_model}")
    print(
        f"Base URL：{default_base_url}"
    )
    print(
        f"temperature："
        f"{default_temperature}"
    )
    print("思考模式：disabled")
    print(
        "API Key："
        + configured_text(
            values,
            "LLM_API_KEY",
            "DEEPSEEK_API_KEY",
        )
    )

    print()
    print("候选模型配置：")

    print(
        "- GLM："
        + configured_text(
            values,
            "GLM_API_KEY",
        )
    )

    print(
        "- Qwen："
        + configured_text(
            values,
            "QWEN_API_KEY",
        )
    )

    print()
    print(
        "Prompt 版本："
        "v3_billing_consistency"
    )


if __name__ == "__main__":
    main()