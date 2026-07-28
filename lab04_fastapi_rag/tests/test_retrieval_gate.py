from __future__ import annotations

import pytest

from src.retrieval_gate import load_retrieval_gate


def test_h3_gate_uses_exact_confirmed_threshold() -> None:
    gate = load_retrieval_gate()

    assert gate.threshold == 0.6831968426704407
    assert gate.passes(gate.threshold)
    assert not gate.passes(gate.threshold - 1e-15)


def test_h3_gate_is_not_rounded_for_decision() -> None:
    gate = load_retrieval_gate()

    assert not gate.passes(0.6831968)
    assert gate.passes(0.6831969)
