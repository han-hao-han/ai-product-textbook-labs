from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from src.validation_selector import DIFFICULTY_GROUPS, DIFFICULTY_LABELS, FEATURE_WEIGHTS


FEATURE_LABELS = {
    "reference_field_count": "参考字段数",
    "entity_count": "实体数",
    "longest_value_chars": "最长值字符数",
    "multiline_entity_count": "多行实体数",
    "mean_pair_distance": "键值平均距离",
    "duplicate_key_count": "重复键名数",
}


def write_validation_candidate_outputs(
    candidates: list[dict[str, Any]],
    *,
    output_dir: Path,
    project_root: Path,
    excluded_ids: set[str],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "validation_candidate_manifest.json"
    gallery_path = output_dir / "validation_candidate_gallery.html"
    manifest = {
        "status": "12张验证候选，等待用户每类选择2张",
        "selection_basis": "仅使用XFUND标注和布局特征，不使用模型表现",
        "excluded_main_observation_ids": sorted(excluded_ids),
        "feature_weights": FEATURE_WEIGHTS,
        "candidates": [_manifest_item(item, project_root) for item in candidates],
    }
    _write_json_atomic(manifest_path, manifest)
    _write_text_atomic(gallery_path, _render_gallery(candidates, gallery_path.parent))
    return manifest_path, gallery_path


def _manifest_item(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    return {
        "sample_id": item["sample_id"],
        "difficulty_group": item["difficulty_group"],
        "difficulty_label": item["difficulty_label"],
        "candidate_order_in_group": item["candidate_order_in_group"],
        "difficulty_score": item["difficulty_score"],
        "difficulty_details": item["difficulty_details"],
        "image_path": _relative_path(item["image_path"], project_root),
        "label_counts": item["label_counts"],
        "features": item["features"],
        "privacy_screen": item["privacy_screen"],
        "reference": item["reference"],
    }


def _relative_path(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def _render_gallery(candidates: list[dict[str, Any]], output_dir: Path) -> str:
    sections = []
    for group in DIFFICULTY_GROUPS:
        cards = "\n".join(
            _render_card(item, output_dir)
            for item in candidates
            if item["difficulty_group"] == group
        )
        sections.append(
            f'<section><h2>{DIFFICULTY_LABELS[group]}候选</h2>{cards}</section>'
        )
    weights = "、".join(
        f"{FEATURE_LABELS[name]} {weight:.0%}" for name, weight in FEATURE_WEIGHTS.items()
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XFUND固定验证候选</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", sans-serif; background: #f4f6f8; color: #17212b; }}
    main {{ max-width: 1220px; margin: auto; padding: 32px 20px 60px; }}
    .notice {{ background: #fff7d6; border-left: 4px solid #d99b00; padding: 12px 16px; }}
    .card {{ display: grid; grid-template-columns: minmax(320px, 1fr) minmax(380px, 1fr); gap: 20px; background: white; border: 1px solid #dce2e8; border-radius: 10px; padding: 18px; margin: 18px 0; }}
    img {{ width: 100%; max-height: 680px; object-fit: contain; background: #eef1f4; border: 1px solid #dce2e8; }}
    .score {{ display: inline-block; padding: 5px 9px; border-radius: 999px; background: #e7f0ff; color: #174ea6; }}
    .metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }}
    .metric {{ background: #f4f6f8; padding: 7px 9px; border-radius: 6px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 7px; border-bottom: 1px solid #e3e7eb; text-align: left; vertical-align: top; }}
    @media (max-width: 840px) {{ .card {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body><main>
  <h1>XFUND中文固定验证：12张候选</h1>
  <p class="notice">身份证号模式命中的图片已硬排除；姓名等其他隐私信号只记录，不参与难度或候选排序。请在三组中各选择2张，并人工确认原图不存在身份证号码。</p>
  <p>评分权重：{html.escape(weights)}</p>
  {''.join(sections)}
</main></body></html>
"""


def _render_card(item: dict[str, Any], output_dir: Path) -> str:
    image_source = html.escape(_relative_path(item["image_path"], output_dir), quote=True)
    features = item["features"]
    privacy = item["privacy_screen"]
    privacy_categories = "、".join(privacy["signal_categories"]) or "标注文本未检出"
    contributions = item["difficulty_details"]["score_contributions"]
    contribution_rows = "".join(
        f"<tr><td>{html.escape(FEATURE_LABELS[name])}</td>"
        f"<td>{html.escape(str(features[name]))}</td>"
        f"<td>{contributions[name]:.2f}</td></tr>"
        for name in FEATURE_WEIGHTS
    )
    field_rows = "".join(
        f"<tr><td>{html.escape(str(field['key']))}</td>"
        f"<td>{html.escape(str(field['value']))}</td></tr>"
        for field in item["reference"]["reference_fields"]
    )
    return f"""
    <article class="card">
      <div><img src="{image_source}" alt="XFUND样本{html.escape(item['sample_id'])}"></div>
      <div>
        <h3>{html.escape(item['difficulty_label'])}{item['candidate_order_in_group']}：{html.escape(item['sample_id'])}</h3>
        <p class="score">难度分数 {item['difficulty_score']:.2f}</p>
        <p><strong>隐私预筛记录：</strong>信号：{html.escape(privacy_categories)}。这些信号不参与难度或候选排序；仍须查看原图确认身份证号码不存在。</p>
        <div class="metrics">
          <div class="metric">参考字段：{features['reference_field_count']}</div>
          <div class="metric">实体：{features['entity_count']}</div>
          <div class="metric">最长值：{features['longest_value_chars']}字符</div>
          <div class="metric">多行实体：{features['multiline_entity_count']}</div>
          <div class="metric">键值距离：{features['mean_pair_distance']}</div>
          <div class="metric">重复键名：{features['duplicate_key_count']}</div>
        </div>
        <h4>难度贡献明细</h4>
        <table><thead><tr><th>特征</th><th>原始值</th><th>贡献分</th></tr></thead><tbody>{contribution_rows}</tbody></table>
        <details><summary>查看人工标注参考字段</summary>
          <table><thead><tr><th>字段名</th><th>字段值</th></tr></thead><tbody>{field_rows}</tbody></table>
        </details>
      </div>
    </article>
"""


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def _write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_suffix(".html.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        file.write(content)
    temporary.replace(path)
