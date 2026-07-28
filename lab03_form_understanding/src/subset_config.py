from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SubsetConfigError(ValueError):
    """Raised when the fixed teaching subset configuration is inconsistent."""


def load_teaching_subset(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    validate_teaching_subset(config)
    return config


def validate_teaching_subset(config: dict[str, Any]) -> None:
    if config.get("dataset") != "XFUND" or config.get("language") != "zh":
        raise SubsetConfigError("固定样本配置必须使用XFUND中文数据")
    main = config.get("main")
    observations = config.get("observations")
    validation = config.get("validation")
    if not isinstance(main, dict) or not isinstance(main.get("sample_id"), str):
        raise SubsetConfigError("固定样本配置缺少教材主样本")
    if not isinstance(observations, list) or len(observations) != 3:
        raise SubsetConfigError("固定样本配置必须包含3张观察样本")
    if not isinstance(validation, dict) or not isinstance(validation.get("samples"), list):
        raise SubsetConfigError("固定样本配置缺少validation对象")

    main_observation_ids = [main["sample_id"]] + [
        item.get("sample_id") for item in observations if isinstance(item, dict)
    ]
    if len(main_observation_ids) != 4 or not all(
        isinstance(sample_id, str) and sample_id for sample_id in main_observation_ids
    ):
        raise SubsetConfigError("主样本或观察样本ID无效")
    if len(set(main_observation_ids)) != 4:
        raise SubsetConfigError("主样本和观察样本存在重复")

    validation_samples = validation["samples"]
    validation_ids = [
        item.get("sample_id") for item in validation_samples if isinstance(item, dict)
    ]
    if len(validation_ids) != len(validation_samples) or not all(
        isinstance(sample_id, str) and sample_id for sample_id in validation_ids
    ):
        raise SubsetConfigError("验证样本ID无效")
    if len(validation_ids) != len(set(validation_ids)):
        raise SubsetConfigError("验证样本存在重复")
    overlap = set(main_observation_ids) & set(validation_ids)
    if overlap:
        raise SubsetConfigError(f"样本集合存在重叠：{sorted(overlap)}")

    status = validation.get("status")
    if status == "frozen_user_confirmed":
        if len(validation_samples) != 6:
            raise SubsetConfigError("冻结验证集必须包含6张样本")
        expected_groups = ["simple", "simple", "medium", "medium", "complex", "complex"]
        actual_groups = [item.get("difficulty_group") for item in validation_samples]
        if actual_groups != expected_groups:
            raise SubsetConfigError("验证样本难度顺序不符合2+2+2契约")
        actual_orders = [item.get("validation_order") for item in validation_samples]
        if actual_orders != [1, 2, 3, 4, 5, 6]:
            raise SubsetConfigError("验证样本顺序必须固定为1到6")
    elif status != "pending_user_selection":
        raise SubsetConfigError(f"未知的验证集状态：{status}")


def main_observation_ids(config: dict[str, Any]) -> set[str]:
    return {config["main"]["sample_id"]} | {
        item["sample_id"] for item in config["observations"]
    }
