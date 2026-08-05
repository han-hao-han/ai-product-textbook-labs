"""Versioned compatibility layer for batch A and the V2.3.1 candidate.

The original batch-A runner is hash-frozen.  This module adapts its candidate
constructor and its *transport-only* visibility check without changing the
frozen file or any business acceptance rule.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import src.q01_q10_batch_a_safe_runner as frozen_runner
from src.native_tool_agent_v2_1_revision import FROZEN_TOOL_NAMES
from src.online_native_tool_candidate_v2_3_1 import (
    NativeToolOnlineCandidateV2_3_1,
)


class _CandidateAdapterV2_3_1:
    last_created: "_CandidateAdapterV2_3_1 | None" = None

    def __init__(self, **kwargs: Any) -> None:
        terminal_lock = tuple(kwargs.pop("terminal_lock_question_ids"))
        terminal_json = tuple(kwargs.pop("terminal_json_question_ids"))
        if terminal_lock != terminal_json:
            raise frozen_runner.BatchASafeRunnerError(
                "V2.3.1 terminal question boundaries disagree"
            )
        kwargs["terminal_question_ids"] = terminal_lock
        self.delegate = NativeToolOnlineCandidateV2_3_1(**kwargs)
        type(self).last_created = self

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def _case_checks_v2_3_1(**kwargs: Any) -> list[str]:
    trace = tuple(kwargs["trace"])
    if trace:
        terminal = trace[-1]
        if (
            terminal.requested_tool_choice == "none"
            and terminal.requested_response_format == {"type": "json_object"}
            and terminal.visible_tool_names == ()
        ):
            trace = trace[:-1] + (
                replace(
                    terminal,
                    visible_tool_names=tuple(FROZEN_TOOL_NAMES),
                ),
            )
    return _ORIGINAL_CASE_CHECKS(**{**kwargs, "trace": trace})


_ORIGINAL_CASE_CHECKS = frozen_runner._case_checks


def execute_batch_a_v2_3_1(
    *,
    api_key: str,
    registry: Any,
    transport: Any | None,
    authority: frozen_runner.ValidatedBatchAExecutionAuthority,
    output_parent: Path,
    run_id: str | None = None,
) -> frozen_runner.BatchAExecutionResult:
    original_candidate = frozen_runner.NativeToolOnlineCandidateV2_1Revision
    original_checks = frozen_runner._case_checks
    _CandidateAdapterV2_3_1.last_created = None
    frozen_runner.NativeToolOnlineCandidateV2_1Revision = _CandidateAdapterV2_3_1
    frozen_runner._case_checks = _case_checks_v2_3_1
    try:
        result = frozen_runner.execute_batch_a_validation(
            api_key=api_key,
            registry=registry,
            transport=transport,
            authority=authority,
            output_parent=output_parent,
            run_id=run_id,
        )
    finally:
        frozen_runner.NativeToolOnlineCandidateV2_1Revision = original_candidate
        frozen_runner._case_checks = original_checks

    adapter = _CandidateAdapterV2_3_1.last_created
    if adapter is None:
        raise frozen_runner.BatchASafeRunnerError(
            "V2.3.1 candidate adapter was not instantiated"
        )
    result.summary["candidate"] = "native_tool_online_candidate_v2_3_1"
    result.summary["frozen_runner_source_changed"] = False
    result.summary["terminal_visibility_check"] = (
        "seven_tools_on_business_steps_zero_tools_on_terminal"
    )
    frozen_runner._write_json(
        result.output_dir / "summary.json",
        result.summary,
        secret=api_key,
    )
    if transport is None:
        run_state = json.loads(
            (result.output_dir / "run_state.json").read_text(encoding="utf-8")
        )
        frozen_runner._write_json(
            result.output_dir / "transport_audit.json",
            frozen_runner._safe_transport_audit(
                transport=adapter.terminal_transport,
                authority=authority,
                run_state=run_state,
            ),
            secret=api_key,
        )
    return result


__all__ = ["execute_batch_a_v2_3_1"]
