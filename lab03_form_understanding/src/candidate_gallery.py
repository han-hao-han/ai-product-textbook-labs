from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any


def write_candidate_outputs(
    candidates: list[dict[str, Any]],
    *,
    output_dir: Path,
    project_root: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "candidate_manifest.json"
    gallery_path = output_dir / "candidate_gallery.html"

    manifest = {
        "status": "候选，尚未由用户选择",
        "selection_basis": "仅使用XFUND标注和布局特征，不使用模型表现",
        "candidate_count": len(candidates),
        "candidates": [_manifest_item(item, project_root) for item in candidates],
    }
    _write_json_atomic(manifest_path, manifest)
    _write_text_atomic(gallery_path, _render_gallery(candidates, gallery_path.parent))
    return manifest_path, gallery_path


def _manifest_item(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    return {
        "sample_id": item["sample_id"],
        "candidate_role": item["candidate_role"],
        "selection_reason": item["selection_reason"],
        "image_path": _relative_path(item["image_path"], project_root),
        "label_counts": item["label_counts"],
        "features": item["features"],
        "privacy_screen": item["privacy_screen"],
        "reference": item["reference"],
    }


def _relative_path(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def _render_gallery(candidates: list[dict[str, Any]], output_dir: Path) -> str:
    cards = "\n".join(_render_card(item, output_dir) for item in candidates)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>XFUND中文表单候选查看</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", sans-serif; background: #f4f6f8; color: #17212b; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ margin-bottom: 24px; }}
    .notice {{ background: #fff7d6; border-left: 4px solid #d99b00; padding: 12px 16px; }}
    .card {{ display: grid; grid-template-columns: minmax(320px, 1fr) minmax(360px, 1fr); gap: 20px; background: white; border: 1px solid #dce2e8; border-radius: 10px; padding: 18px; margin: 20px 0; }}
    img {{ width: 100%; max-height: 720px; object-fit: contain; background: #eef1f4; border: 1px solid #dce2e8; }}
    h1, h2, h3 {{ margin-top: 0; }}
    .meta {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .metric {{ background: #f4f6f8; padding: 8px 10px; border-radius: 6px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #e3e7eb; padding: 8px; text-align: left; vertical-align: top; }}
    .warning {{ color: #9b2c2c; }}
    .checklist {{ background: #eef7ff; border: 1px solid #b8d8f0; padding: 10px 12px; margin: 12px 0; }}
    @media (max-width: 820px) {{ .card {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>XFUND中文表单：5张教学候选</h1>
    <p class="notice">身份证号模式命中的图片已被程序硬排除；姓名等其他隐私信号只记录，不参与候选排序。自动预筛不能替代原图人工检查。</p>
    <p>来源：XFUND v1.0；许可：CC BY-NC-SA 4.0；当前页面只在本地生成。</p>
  </header>
  {cards}
</main>
</body>
</html>
"""


def _render_card(item: dict[str, Any], output_dir: Path) -> str:
    image_source = html.escape(_relative_path(item["image_path"], output_dir), quote=True)
    features = item["features"]
    label_counts = item["label_counts"]
    fields = item["reference"]["reference_fields"]
    warnings = item["reference"]["conversion_warnings"]
    privacy = item["privacy_screen"]
    privacy_categories = "、".join(privacy["signal_categories"]) or "标注文本未检出"
    rows = "\n".join(
        "<tr><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(field["key"])),
            html.escape(str(field["value"])),
        )
        for field in fields
    )
    warning_html = ""
    if warnings:
        warning_html = '<p class="warning">{}</p>'.format(
            html.escape("；".join(warnings))
        )

    return f"""
  <section class="card">
    <div>
      <img src="{image_source}" alt="XFUND样本{html.escape(item['sample_id'])}">
    </div>
    <div>
      <h2>{html.escape(item['candidate_role'])}</h2>
      <p><strong>样本ID：</strong>{html.escape(item['sample_id'])}</p>
      <p>{html.escape(item['selection_reason'])}</p>
      <p><strong>隐私预筛记录：</strong>信号：{html.escape(privacy_categories)}。这些信号不参与候选排序；仍须查看原图确认身份证号码不存在。</p>
      <div class="checklist">
        <strong>人工复核清单</strong>
        <p>□ 原图未发现完整、局部或遮挡的身份证号码；若发现或不确定，本样本必须排除。</p>
        <p>□ 已记录姓名、电话、地址、账号等其他信号；这些信号不自动排除。</p>
        <p>□ 已检查下方显式question-answer关系；发现的问题应记录，不能静默改写。</p>
      </div>
      <div class="meta">
        <div class="metric">参考字段：{features['reference_field_count']}</div>
        <div class="metric">实体总数：{features['entity_count']}</div>
        <div class="metric">最长值字符：{features['longest_value_chars']}</div>
        <div class="metric">多行实体：{features['multiline_entity_count']}</div>
        <div class="metric">键值平均距离：{features['mean_pair_distance']}</div>
        <div class="metric">布局复杂度：{features['layout_complexity']}</div>
      </div>
      <p>实体标签：header={label_counts.get('header', 0)}，question={label_counts.get('question', 0)}，answer={label_counts.get('answer', 0)}，other={label_counts.get('other', 0)}</p>
      {warning_html}
      <h3>转换后的人工标注参考字段</h3>
      <table>
        <thead><tr><th>字段名</th><th>字段值</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>
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
