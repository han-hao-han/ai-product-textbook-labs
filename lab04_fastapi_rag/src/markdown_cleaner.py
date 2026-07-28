from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .document_manifest import (
    CODE_INCLUDE_PATTERN,
    MARKDOWN_LINK_PATTERN,
    _parse_markdown_target,
    _resolve_relative_repo_path,
    parse_line_selection,
    resolve_code_include_path,
)
from .source_config import SourceConfig


IMAGE_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
IMAGE_ALT_PATTERN = re.compile(
    r"\balt\s*=\s*[\"'](?P<alt>[^\"']*)[\"']",
    re.IGNORECASE,
)
UNSAFE_BLOCK_PATTERN = re.compile(
    r"<(?P<tag>script|iframe)\b[^>]*>.*?</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")
DIRECTIVE_PATTERN = re.compile(
    r"^(?P<indent>\s*)///\s*(?P<kind>[A-Za-z0-9_-]+)"
    r"(?:\s*\|\s*(?P<title>.*))?\s*$"
)
DIRECTIVE_CLOSE_PATTERN = re.compile(r"^\s*///\s*$")
TAB_PATTERN = re.compile(r'^(?P<indent>\s*)===\s+"(?P<title>.+)"\s*$')


def _language_for_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return {
        ".py": "python",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".html": "html",
        ".js": "javascript",
        ".css": "css",
        ".sh": "bash",
    }.get(suffix, "text")


def _selected_code(content: str, selection: tuple[int, int] | None) -> str:
    if selection is None:
        return content.rstrip()
    lines = content.splitlines()
    start, end = selection
    if start > len(lines) or end > len(lines):
        raise ValueError(
            f"代码引用行范围越界：ln[{start}:{end}]，文件共{len(lines)}行"
        )
    return "\n".join(lines[start - 1 : end]).rstrip()


def expand_code_includes(
    markdown: str,
    source_path: str,
    repo_root: Path,
    config: SourceConfig,
) -> str:
    def replace(match: re.Match[str]) -> str:
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
            raise ValueError(
                "代码引用不在冻结依赖范围内："
                f"{source_path} -> {raw_target}（解析为{resolved}）"
            )
        code_path = repo_root / resolved
        if not code_path.is_file():
            raise FileNotFoundError(f"缺少代码依赖：{resolved}")
        content = code_path.read_text(encoding="utf-8")
        selected = _selected_code(content, line_selection)
        language = _language_for_path(resolved)
        return f"````{language}\n{selected}\n````"

    return CODE_INCLUDE_PATTERN.sub(replace, markdown)


def _convert_directives(markdown: str) -> str:
    output: list[str] = []
    directive_depth = 0
    for line in markdown.splitlines():
        if DIRECTIVE_CLOSE_PATTERN.match(line):
            if directive_depth:
                directive_depth -= 1
            continue
        match = DIRECTIVE_PATTERN.match(line)
        if match:
            directive_depth += 1
            title = (match.group("title") or match.group("kind")).strip()
            output.append(f"> **{title}**")
            continue
        tab = TAB_PATTERN.match(line)
        if tab:
            output.append(f"### {tab.group('title').strip()}")
            continue
        # Remove the presentation-only wrapper but leave inner Markdown unchanged.
        # In particular, fenced code and tables must remain detectable as blocks.
        output.append(line.rstrip())
    return "\n".join(output)


def _convert_links(
    markdown: str,
    source_path: str,
    repo_root: Path,
    config: SourceConfig,
) -> str:
    source_url = config.source_url(source_path)

    def replace(match: re.Match[str]) -> str:
        full = match.group(0)
        label_match = re.match(r"\[(?P<label>[^\]]+)\]", full)
        label = label_match.group("label") if label_match else full
        raw_target = _parse_markdown_target(match.group("target"))
        split = urlsplit(raw_target)
        if split.scheme in {"http", "https", "mailto"}:
            return label
        if raw_target.startswith("#"):
            return f"[{label}]({source_url}{raw_target})"
        if raw_target.startswith("/"):
            return label
        if not split.path:
            suffix = f"#{split.fragment}" if split.fragment else ""
            return f"[{label}]({source_url}{suffix})"
        resolved = _resolve_relative_repo_path(source_path, split.path)
        target_path = repo_root / resolved
        if target_path.is_dir() and (target_path / "index.md").is_file():
            resolved = (PurePosixPath(resolved) / "index.md").as_posix()
            target_path = repo_root / resolved
        if not target_path.is_file():
            return label
        target_url = config.source_url(resolved)
        if split.fragment:
            target_url = f"{target_url}#{split.fragment}"
        return f"[{label}]({target_url})"

    return MARKDOWN_LINK_PATTERN.sub(replace, markdown)


def clean_markdown(
    markdown: str,
    source_path: str,
    repo_root: Path,
    config: SourceConfig,
) -> tuple[str, dict[str, Any]]:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    code_include_count = len(CODE_INCLUDE_PATTERN.findall(normalized))
    normalized = expand_code_includes(
        normalized,
        source_path,
        repo_root,
        config,
    )

    image_alts: list[str] = []

    def replace_image(match: re.Match[str]) -> str:
        alt_match = IMAGE_ALT_PATTERN.search(match.group(0))
        alt = (alt_match.group("alt") if alt_match else "").strip()
        image_alts.append(alt)
        return f"[图片：{alt}]" if alt else "[图片]"

    normalized = IMAGE_PATTERN.sub(replace_image, normalized)
    unsafe_block_count = len(UNSAFE_BLOCK_PATTERN.findall(normalized))
    normalized = UNSAFE_BLOCK_PATTERN.sub("", normalized)
    normalized = _convert_directives(normalized)
    normalized = _convert_links(normalized, source_path, repo_root, config)
    normalized = HTML_TAG_PATTERN.sub("", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip() + "\n"

    metadata = {
        "code_include_count": code_include_count,
        "image_count": len(image_alts),
        "image_alts": image_alts,
        "unsafe_block_count": unsafe_block_count,
    }
    return normalized, metadata
