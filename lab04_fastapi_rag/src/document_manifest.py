from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .io_utils import sha256_file, write_json_atomic
from .source_config import SourceConfig


CODE_INCLUDE_PATTERN = re.compile(
    r"\{\*\s+(?P<target>[^\s}]+)(?P<options>[^}]*)\*\}"
)
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
HEADING_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


class DocumentAuditError(RuntimeError):
    """Raised when the frozen document contract cannot be satisfied."""


def _to_repo_relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _resolve_relative_repo_path(source_path: str, target: str) -> str:
    source_parent = PurePosixPath(source_path).parent
    parts: list[str] = []
    for part in (source_parent / target).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise DocumentAuditError(
                    f"相对路径越出仓库根目录：{source_path} -> {target}"
                )
            parts.pop()
        else:
            parts.append(part)
    return PurePosixPath(*parts).as_posix()


def resolve_code_include_path(
    source_path: str,
    target: str,
    config: SourceConfig,
) -> str:
    """Resolve an include from FastAPI's fixed language build directory.

    FastAPI's Chinese Markdown pages live below ``docs/zh/docs/``, but their
    code-include directives are resolved from ``docs/zh`` regardless of the
    current page's nesting depth. Therefore ``../../docs_src/...`` always
    points to the repository-level ``docs_src/`` tree.
    """

    language_root = PurePosixPath(config.chinese_docs_root).parent
    try:
        PurePosixPath(source_path).relative_to(language_root)
    except ValueError as error:
        raise DocumentAuditError(
            f"页面不在冻结语言目录内：{source_path}"
        ) from error
    include_base = (language_root / "__include_base__.md").as_posix()
    return _resolve_relative_repo_path(include_base, target)


def extract_page_title(markdown: str, fallback: str) -> str:
    match = HEADING_PATTERN.search(markdown)
    if not match:
        return fallback
    return re.sub(r"\s+\{.*\}\s*$", "", match.group(1)).strip()


def parse_line_selection(options: str) -> tuple[int, int] | None:
    match = re.search(r"\bln\[(\d+)(?::(\d+))?\]", options)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start <= 0 or end < start:
        raise DocumentAuditError(f"无效的代码行范围：ln[{start}:{end}]")
    return start, end


def _parse_markdown_target(target: str) -> str:
    stripped = target.strip()
    if " " in stripped and not stripped.startswith("<"):
        stripped = stripped.split(" ", maxsplit=1)[0]
    return stripped.strip("<>")


def _audit_links(
    markdown: str,
    source_path: str,
    repo_root: Path,
    included_paths: set[str],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(markdown):
        raw_target = _parse_markdown_target(match.group("target"))
        split = urlsplit(raw_target)
        if split.scheme in {"http", "https", "mailto"}:
            status = "external"
            resolved = None
        elif raw_target.startswith("#"):
            status = "same_page_anchor"
            resolved = source_path
        elif raw_target.startswith("/"):
            status = "site_absolute"
            resolved = None
        else:
            relative_target = split.path
            if not relative_target:
                status = "same_page_anchor"
                resolved = source_path
            else:
                resolved = _resolve_relative_repo_path(source_path, relative_target)
                target_path = repo_root / resolved
                if target_path.is_dir():
                    candidate = target_path / "index.md"
                    if candidate.is_file():
                        resolved = _to_repo_relative(candidate, repo_root)
                        target_path = candidate
                if target_path.is_file():
                    status = (
                        "internal_in_corpus"
                        if resolved in included_paths
                        else "internal_out_of_scope"
                    )
                else:
                    status = "internal_missing"
        links.append(
            {
                "raw_target": raw_target,
                "resolved_source_path": resolved,
                "status": status,
            }
        )
    return links


def _audit_code_dependencies(
    markdown: str,
    source_path: str,
    repo_root: Path,
    config: SourceConfig,
) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    for match in CODE_INCLUDE_PATTERN.finditer(markdown):
        raw_target = match.group("target")
        options = match.group("options").strip()
        resolved = resolve_code_include_path(source_path, raw_target, config)
        line_selection = parse_line_selection(options)
        in_default_root = (
            resolved == config.code_source_root
            or resolved.startswith(f"{config.code_source_root}/")
        )
        exception = config.dependency_exception(
            source_path,
            resolved,
            line_selection,
        )
        if not in_default_root and exception is None:
            raise DocumentAuditError(
                "代码引用不在冻结依赖范围内："
                f"{source_path} -> {raw_target}（解析为{resolved}）"
            )
        target_path = repo_root / resolved
        exists = target_path.is_file()
        if exists and line_selection is not None:
            line_count = len(target_path.read_text(encoding="utf-8").splitlines())
            if line_selection[1] > line_count:
                raise DocumentAuditError(
                    "代码引用行范围越界："
                    f"{source_path} -> {resolved}，"
                    f"ln[{line_selection[0]}:{line_selection[1]}]，"
                    f"文件共{line_count}行"
                )
        dependency: dict[str, Any] = {
            "raw_target": raw_target,
            "source_path": resolved,
            "options": options,
            "line_selection": line_selection,
            "dependency_scope": (
                "code_source_root" if in_default_root else "approved_exception"
            ),
            "exception_reason": exception.reason if exception else None,
            "exists": exists,
            "content_sha256": sha256_file(target_path) if exists else None,
        }
        dependencies.append(dependency)
    return dependencies


def build_document_manifest(
    run_dir: Path,
    config: SourceConfig,
) -> dict[str, Any]:
    repo_root = run_dir / "source" / "repository"
    if not repo_root.is_dir():
        raise FileNotFoundError("缺少已下载仓库，请先运行download_fastapi_docs.py")

    chinese_root = repo_root / config.chinese_docs_root
    exclusion_map = config.excluded_path_map
    candidate_paths: list[str] = []
    for group in config.included_groups:
        group_dir = chinese_root / group
        candidate_paths.extend(
            _to_repo_relative(path, repo_root)
            for path in sorted(group_dir.rglob("*.md"))
            if path.is_file()
        )

    included_paths = {
        path for path in candidate_paths if path not in exclusion_map
    }
    expected_total = config.expected_included_pages
    if len(included_paths) != expected_total:
        raise DocumentAuditError(
            "冻结中文页面数量不匹配："
            f"expected={expected_total}, actual={len(included_paths)}"
        )

    actual_group_counts = Counter(
        PurePosixPath(path).relative_to(config.chinese_docs_root).parts[0]
        for path in included_paths
    )
    if dict(actual_group_counts) != config.included_groups:
        raise DocumentAuditError(
            "冻结分组数量不匹配："
            f"expected={config.included_groups}, "
            f"actual={dict(sorted(actual_group_counts.items()))}"
        )

    documents: list[dict[str, Any]] = []
    all_candidate_paths = set(candidate_paths)
    for source_path in sorted(all_candidate_paths):
        file_path = repo_root / source_path
        markdown = file_path.read_text(encoding="utf-8")
        included = source_path in included_paths
        code_dependencies = (
            _audit_code_dependencies(
                markdown,
                source_path,
                repo_root,
                config,
            )
            if included
            else []
        )
        links = (
            _audit_links(
                markdown,
                source_path,
                repo_root,
                included_paths,
            )
            if included
            else []
        )
        relative = PurePosixPath(source_path).relative_to(config.chinese_docs_root)
        documents.append(
            {
                "repo": config.repository,
                "commit": config.commit,
                "source_path": source_path,
                "document_group": relative.parts[0],
                "page_title": extract_page_title(markdown, file_path.stem),
                "source_url": config.source_url(source_path),
                "content_sha256": sha256_file(file_path),
                "size_bytes": file_path.stat().st_size,
                "included_or_excluded": "included" if included else "excluded",
                "excluded_reason": None if included else exclusion_map[source_path],
                "code_dependencies": code_dependencies,
                "links": links,
            }
        )

    missing_code = [
        {
            "document": document["source_path"],
            "dependency": dependency["source_path"],
        }
        for document in documents
        if document["included_or_excluded"] == "included"
        for dependency in document["code_dependencies"]
        if not dependency["exists"]
    ]
    missing_links = [
        {
            "document": document["source_path"],
            "target": link["raw_target"],
            "resolved_source_path": link["resolved_source_path"],
        }
        for document in documents
        if document["included_or_excluded"] == "included"
        for link in document["links"]
        if link["status"] == "internal_missing"
    ]
    exception_audit: list[dict[str, Any]] = []
    for exception in config.code_dependency_exceptions:
        actual_occurrences = sum(
            1
            for document in documents
            for dependency in document["code_dependencies"]
            if document["source_path"] == exception.source_path
            and dependency["source_path"] == exception.dependency_path
            and dependency["line_selection"] == exception.line_selection
            and dependency["dependency_scope"] == "approved_exception"
        )
        if actual_occurrences != exception.expected_occurrences:
            raise DocumentAuditError(
                "代码依赖例外出现次数与冻结配置不一致："
                f"{exception.source_path} -> {exception.dependency_path}，"
                f"expected={exception.expected_occurrences}, "
                f"actual={actual_occurrences}"
            )
        exception_audit.append(
            {
                "source_path": exception.source_path,
                "dependency_path": exception.dependency_path,
                "line_selection": exception.line_selection,
                "expected_occurrences": exception.expected_occurrences,
                "actual_occurrences": actual_occurrences,
                "reason": exception.reason,
            }
        )
    status = "blocked" if missing_code else ("warning" if missing_links else "passed")
    summary = {
        "schema_version": "fastapi_document_manifest_v2",
        "experiment_run_id": run_dir.name,
        "repository": config.repository,
        "release_tag": config.release_tag,
        "commit": config.commit,
        "status": status,
        "candidate_markdown_files": len(candidate_paths),
        "included_markdown_files": len(included_paths),
        "excluded_markdown_files": len(candidate_paths) - len(included_paths),
        "included_group_counts": dict(sorted(actual_group_counts.items())),
        "code_include_references": sum(
            len(item["code_dependencies"]) for item in documents
        ),
        "unique_code_dependencies": len(
            {
                dependency["source_path"]
                for item in documents
                for dependency in item["code_dependencies"]
            }
        ),
        "code_dependency_scope_counts": dict(
            sorted(
                Counter(
                    dependency["dependency_scope"]
                    for item in documents
                    for dependency in item["code_dependencies"]
                ).items()
            )
        ),
        "approved_dependency_exceptions": exception_audit,
        "missing_code_dependencies": missing_code,
        "link_status_counts": dict(
            sorted(
                Counter(
                    link["status"]
                    for item in documents
                    for link in item["links"]
                ).items()
            )
        ),
        "missing_internal_links": missing_links,
        "documents": documents,
    }
    write_json_atomic(run_dir / "source" / "document_manifest.json", summary)
    return summary
