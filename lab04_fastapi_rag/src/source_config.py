from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .paths import CONFIG_PATH


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str
    token_count_method: str
    target_min_tokens: int
    target_max_tokens: int
    overlap_target_tokens: int
    overlap_min_tokens: int
    overlap_max_tokens: int


@dataclass(frozen=True)
class CodeDependencyException:
    source_path: str
    dependency_path: str
    line_start: int
    line_end: int
    expected_occurrences: int
    reason: str

    @property
    def line_selection(self) -> tuple[int, int]:
        return self.line_start, self.line_end


@dataclass(frozen=True)
class SourceConfig:
    schema_version: str
    repository: str
    release_tag: str
    commit: str
    archive_url: str
    source_url_template: str
    license_path: str
    license_git_blob_sha1: str
    chinese_docs_root: str
    code_source_root: str
    code_dependency_exceptions: tuple[CodeDependencyException, ...]
    included_groups: dict[str, int]
    excluded_pages: tuple[dict[str, str], ...]
    chunking: ChunkingConfig

    @property
    def expected_included_pages(self) -> int:
        return sum(self.included_groups.values())

    @property
    def excluded_path_map(self) -> dict[str, str]:
        return {
            item["source_path"]: item["excluded_reason"]
            for item in self.excluded_pages
        }

    def source_url(self, source_path: str) -> str:
        return self.source_url_template.format(
            commit=self.commit,
            source_path=source_path,
        )

    def dependency_exception(
        self,
        source_path: str,
        dependency_path: str,
        line_selection: tuple[int, int] | None,
    ) -> CodeDependencyException | None:
        for exception in self.code_dependency_exceptions:
            if (
                exception.source_path == source_path
                and exception.dependency_path == dependency_path
                and exception.line_selection == line_selection
            ):
                return exception
        return None


def _require_dict(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name}必须是JSON对象")
    return payload


def load_source_config(path: Path = CONFIG_PATH) -> SourceConfig:
    payload = _require_dict(read_json(path), "source_config")
    required = {
        "schema_version",
        "repository",
        "release_tag",
        "commit",
        "archive_url",
        "source_url_template",
        "license_path",
        "license_git_blob_sha1",
        "chinese_docs_root",
        "code_source_root",
        "code_dependency_exceptions",
        "included_groups",
        "excluded_pages",
        "chunking",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"source_config缺少字段：{', '.join(missing)}")

    commit = str(payload["commit"])
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("commit必须是40位小写十六进制SHA")
    if commit not in str(payload["archive_url"]):
        raise ValueError("archive_url必须固定到配置中的commit")
    if "{commit}" not in str(payload["source_url_template"]):
        raise ValueError("source_url_template必须包含{commit}")
    if "{source_path}" not in str(payload["source_url_template"]):
        raise ValueError("source_url_template必须包含{source_path}")

    groups = _require_dict(payload["included_groups"], "included_groups")
    expected_groups = {"tutorial", "advanced", "deployment", "how-to"}
    if set(groups) != expected_groups:
        raise ValueError("included_groups必须严格包含tutorial、advanced、deployment、how-to")
    normalized_groups = {str(key): int(value) for key, value in groups.items()}
    if any(value <= 0 for value in normalized_groups.values()):
        raise ValueError("included_groups中的文件数必须为正整数")

    dependency_exceptions = payload["code_dependency_exceptions"]
    if not isinstance(dependency_exceptions, list):
        raise ValueError("code_dependency_exceptions必须是数组")
    normalized_dependency_exceptions: list[CodeDependencyException] = []
    seen_dependency_exceptions: set[tuple[str, str, int, int]] = set()
    for item in dependency_exceptions:
        entry = _require_dict(item, "code_dependency_exceptions条目")
        source_path = str(entry.get("source_path", ""))
        dependency_path = str(entry.get("dependency_path", ""))
        line_start = int(entry.get("line_start", 0))
        line_end = int(entry.get("line_end", 0))
        expected_occurrences = int(entry.get("expected_occurrences", 0))
        reason = str(entry.get("reason", ""))
        if not source_path or not dependency_path or not reason:
            raise ValueError(
                "代码依赖例外必须包含source_path、dependency_path和reason"
            )
        if line_start <= 0 or line_end < line_start:
            raise ValueError("代码依赖例外的行范围无效")
        if expected_occurrences != 1:
            raise ValueError("精确代码依赖例外的expected_occurrences必须为1")
        key = (source_path, dependency_path, line_start, line_end)
        if key in seen_dependency_exceptions:
            raise ValueError(f"重复代码依赖例外：{source_path} -> {dependency_path}")
        seen_dependency_exceptions.add(key)
        normalized_dependency_exceptions.append(
            CodeDependencyException(
                source_path=source_path,
                dependency_path=dependency_path,
                line_start=line_start,
                line_end=line_end,
                expected_occurrences=expected_occurrences,
                reason=reason,
            )
        )

    exclusions = payload["excluded_pages"]
    if not isinstance(exclusions, list):
        raise ValueError("excluded_pages必须是数组")
    normalized_exclusions: list[dict[str, str]] = []
    seen_exclusions: set[str] = set()
    for item in exclusions:
        entry = _require_dict(item, "excluded_pages条目")
        source_path = str(entry.get("source_path", ""))
        reason = str(entry.get("excluded_reason", ""))
        if not source_path or not reason:
            raise ValueError("排除条目必须包含source_path和excluded_reason")
        if source_path in seen_exclusions:
            raise ValueError(f"重复排除路径：{source_path}")
        seen_exclusions.add(source_path)
        normalized_exclusions.append(
            {"source_path": source_path, "excluded_reason": reason}
        )

    chunking_payload = _require_dict(payload["chunking"], "chunking")
    chunking = ChunkingConfig(
        strategy=str(chunking_payload["strategy"]),
        token_count_method=str(chunking_payload["token_count_method"]),
        target_min_tokens=int(chunking_payload["target_min_tokens"]),
        target_max_tokens=int(chunking_payload["target_max_tokens"]),
        overlap_target_tokens=int(chunking_payload["overlap_target_tokens"]),
        overlap_min_tokens=int(chunking_payload["overlap_min_tokens"]),
        overlap_max_tokens=int(chunking_payload["overlap_max_tokens"]),
    )
    if not (
        0
        < chunking.target_min_tokens
        <= chunking.target_max_tokens
        and 0
        < chunking.overlap_min_tokens
        <= chunking.overlap_target_tokens
        <= chunking.overlap_max_tokens
    ):
        raise ValueError("Chunk长度或重叠配置无效")
    if chunking.strategy != "heading_aware_adjacent_merge_v1":
        raise ValueError("不支持的Chunk策略")

    return SourceConfig(
        schema_version=str(payload["schema_version"]),
        repository=str(payload["repository"]),
        release_tag=str(payload["release_tag"]),
        commit=commit,
        archive_url=str(payload["archive_url"]),
        source_url_template=str(payload["source_url_template"]),
        license_path=str(payload["license_path"]),
        license_git_blob_sha1=str(payload["license_git_blob_sha1"]),
        chinese_docs_root=str(payload["chinese_docs_root"]),
        code_source_root=str(payload["code_source_root"]),
        code_dependency_exceptions=tuple(normalized_dependency_exceptions),
        included_groups=normalized_groups,
        excluded_pages=tuple(normalized_exclusions),
        chunking=chunking,
    )
