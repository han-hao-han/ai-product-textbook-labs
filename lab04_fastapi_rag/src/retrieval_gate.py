from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .paths import RETRIEVAL_GATE_PATH


@dataclass(frozen=True)
class RetrievalGate:
    status: str
    threshold: float
    source_commit: str
    corpus_sha256: str
    index_sha256: str
    model_revision: str
    evaluation_set_sha256: str

    def passes(self, top1_score: float) -> bool:
        return float(top1_score) >= self.threshold


def load_retrieval_gate(
    path: Path = RETRIEVAL_GATE_PATH,
) -> RetrievalGate:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("检索门控配置必须是JSON对象")
    if payload.get("schema_version") != "retrieval_gate_frozen_v1":
        raise ValueError("不支持的检索门控配置版本")
    if payload.get("status") != "h3_frozen_user_confirmed":
        raise ValueError("检索门控阈值尚未由用户确认冻结")
    threshold = float(payload.get("threshold", -1))
    if threshold != 0.6831968426704407:
        raise ValueError("检索门控阈值偏离H3冻结值")
    if (
        payload.get("pass_rule") != "top1_score >= threshold"
        or payload.get("reject_rule") != "top1_score < threshold"
        or payload.get("retune_after_evaluation") is not False
    ):
        raise ValueError("检索门控判定规则偏离冻结方案")
    calibration = payload.get("calibration")
    if not isinstance(calibration, dict):
        raise ValueError("检索门控缺少校准来源")
    if (
        calibration.get("question_set_sha256")
        != "13ccbdd23ac50edeb1e106ea68d295f185cfea6e4d3789db3dd66a2429253d9b"
        or calibration.get("gate_policy_sha256")
        != "a457b31c53091fd3b16df2eeea1e6ba9e7fc36c1ed17687a87063920bb340769"
        or calibration.get("threshold_result_sha256")
        != "fb2473dd0f485d5579eccd98431cd598e44e6460378ccc1d5e069a4e926b1dd8"
    ):
        raise ValueError("检索门控校准来源哈希不一致")
    return RetrievalGate(
        status=str(payload["status"]),
        threshold=threshold,
        source_commit=str(payload["source_commit"]),
        corpus_sha256=str(payload["corpus_sha256"]),
        index_sha256=str(payload["index_sha256"]),
        model_revision=str(payload["model_revision"]),
        evaluation_set_sha256=str(payload["evaluation_set_sha256"]),
    )


def validate_gate_against_index(
    gate: RetrievalGate,
    index_manifest: dict[str, Any],
) -> None:
    if gate.corpus_sha256 != index_manifest.get("corpus_sha256"):
        raise ValueError("正式门控语料哈希与当前索引不一致")
    if gate.index_sha256 != index_manifest.get("embeddings_sha256"):
        raise ValueError("正式门控索引哈希与当前索引不一致")
    if gate.model_revision != index_manifest.get("revision"):
        raise ValueError("正式门控模型Revision与当前索引不一致")
