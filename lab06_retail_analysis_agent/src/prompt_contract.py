"""Load immutable, versioned prompts used by the H3 Agent layer."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
AGENT_SYSTEM_PROMPT_VERSION = "1.5.6-h3-agent-system-v1"
REPORT_PROMPT_VERSION = "1.5.6-h3-report-v1"
DECISION_GATE_PROMPT_V2_VERSION = "1.5.6-h3-decision-gate-v2"
REPORT_FINALIZER_PROMPT_V2_VERSION = (
    "1.5.6-h3-report-finalizer-v2"
)
TOOL_SELECTOR_PROMPT_V2_VERSION = "1.5.6-h3-tool-selector-v2"
DECISION_GATE_PROMPT_V2_1_VERSION = "1.5.6-h3-decision-gate-v2.1"
REPORT_SEMANTIC_PROMPT_V2_1_VERSION = (
    "1.5.6-h3-report-semantic-v2.1"
)
NATIVE_TOOL_AGENT_PROMPT_V2_1_REVISION_VERSION = (
    "1.5.6-h3-native-tool-agent-v2.1-revision"
)
NATIVE_TOOL_REPORT_PROMPT_V2_1_REVISION_VERSION = (
    "1.5.6-h3-native-tool-report-v2.1-revision"
)
NATIVE_TOOL_REPORT_EVIDENCE_GUARD_V1_VERSION = (
    "1.5.6-h3-native-tool-report-evidence-guard-v1"
)


@dataclass(frozen=True)
class VersionedPrompt:
    version: str
    relative_path: str
    content: str
    sha256: str


@dataclass(frozen=True)
class AgentPromptBundle:
    system: VersionedPrompt
    report: VersionedPrompt


@dataclass(frozen=True)
class ReportBoundaryPromptBundleV2:
    decision_gate: VersionedPrompt
    tool_selector: VersionedPrompt
    report_finalizer: VersionedPrompt


@dataclass(frozen=True)
class ReportBoundaryPromptBundleV2_1:
    decision_gate: VersionedPrompt
    report_semantic_planner: VersionedPrompt


def _load_prompt(filename: str, version: str) -> VersionedPrompt:
    path = PROMPT_ROOT / filename
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"提示词文件为空：{filename}")
    return VersionedPrompt(
        version=version,
        relative_path=f"prompts/{filename}",
        content=content,
        sha256=sha256(content.encode("utf-8")).hexdigest(),
    )


def load_agent_prompts() -> AgentPromptBundle:
    return AgentPromptBundle(
        system=_load_prompt(
            "agent_system_prompt_v1.md",
            AGENT_SYSTEM_PROMPT_VERSION,
        ),
        report=_load_prompt(
            "report_prompt_v1.md",
            REPORT_PROMPT_VERSION,
        ),
    )


def load_native_tool_agent_prompts_v2_1_revision() -> AgentPromptBundle:
    """Load the independent native-tool mainline prompts.

    These prompts intentionally do not reuse the historical V2.1 recipe
    prompts: tool selection and arguments remain model responsibilities.
    """
    return AgentPromptBundle(
        system=_load_prompt(
            "native_tool_agent_system_v2_1_revision.md",
            NATIVE_TOOL_AGENT_PROMPT_V2_1_REVISION_VERSION,
        ),
        report=_load_prompt(
            "native_tool_report_v2_1_revision.md",
            NATIVE_TOOL_REPORT_PROMPT_V2_1_REVISION_VERSION,
        ),
    )


def load_native_tool_agent_prompts_evidence_guard_v1() -> AgentPromptBundle:
    """Load the native-tool mainline with the evidence-guard report Prompt."""
    return AgentPromptBundle(
        system=_load_prompt(
            "native_tool_agent_system_v2_1_revision.md",
            NATIVE_TOOL_AGENT_PROMPT_V2_1_REVISION_VERSION,
        ),
        report=_load_prompt(
            "native_tool_report_evidence_guard_v1.md",
            NATIVE_TOOL_REPORT_EVIDENCE_GUARD_V1_VERSION,
        ),
    )


def load_report_boundary_prompts_v2() -> ReportBoundaryPromptBundleV2:
    return ReportBoundaryPromptBundleV2(
        decision_gate=_load_prompt(
            "decision_gate_prompt_v2.md",
            DECISION_GATE_PROMPT_V2_VERSION,
        ),
        tool_selector=_load_prompt(
            "tool_selector_prompt_v2.md",
            TOOL_SELECTOR_PROMPT_V2_VERSION,
        ),
        report_finalizer=_load_prompt(
            "report_finalizer_prompt_v2.md",
            REPORT_FINALIZER_PROMPT_V2_VERSION,
        ),
    )


def load_report_boundary_prompts_v2_1(
) -> ReportBoundaryPromptBundleV2_1:
    return ReportBoundaryPromptBundleV2_1(
        decision_gate=_load_prompt(
            "decision_gate_prompt_v2_1.md",
            DECISION_GATE_PROMPT_V2_1_VERSION,
        ),
        report_semantic_planner=_load_prompt(
            "report_semantic_prompt_v2_1.md",
            REPORT_SEMANTIC_PROMPT_V2_1_VERSION,
        ),
    )
