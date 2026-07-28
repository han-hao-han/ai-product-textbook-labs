from __future__ import annotations

from collections import Counter
import html
import os
from pathlib import Path
from typing import Any

from .reference_converter import convert_reference_fields


_SPECIAL_SYMBOLS = frozenset(("☑", "□", "☒", "✓", "✔", "√", "■"))


def write_reference_review_page(
    *,
    sample_id: str,
    document: dict[str, Any],
    image_path: Path,
    review_record: dict[str, Any],
    output_dir: Path,
) -> Path:
    if str(document.get("id")) != sample_id:
        raise ValueError("复核页样本ID与XFUND文档不一致")
    if review_record.get("sample_id") != sample_id:
        raise ValueError("复核页样本ID与人工复核记录不一致")
    if not image_path.is_file():
        raise FileNotFoundError(f"找不到复核图片：{image_path}")

    reference = convert_reference_fields(document)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"reference_review_{sample_id}.html"
    content = _render_page(
        sample_id=sample_id,
        image_path=image_path,
        output_path=output_path,
        reference=reference,
        review_record=review_record,
    )
    temporary = output_path.with_suffix(".html.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        file.write(content)
    temporary.replace(output_path)
    return output_path


def _render_page(
    *,
    sample_id: str,
    image_path: Path,
    output_path: Path,
    reference: dict[str, Any],
    review_record: dict[str, Any],
) -> str:
    fields = reference["reference_fields"]
    key_counts = Counter(field["key"] for field in fields)
    correction_by_pair = _correction_by_entity_pair(review_record)
    structure_by_pair = _structure_by_entity_pair(review_record)
    rows = "\n".join(
        _render_row(
            index,
            field,
            key_counts[field["key"]],
            correction_by_pair,
            structure_by_pair,
        )
        for index, field in enumerate(fields, start=1)
    )
    image_source = html.escape(
        Path(os.path.relpath(image_path, output_path.parent)).as_posix(),
        quote=True,
    )
    annotation_status = html.escape(
        str(review_record["annotation_review"]["status"])
    )
    final_status = html.escape(str(review_record["final_reference_status"]))
    warning_html = ""
    if reference["conversion_warnings"]:
        warning_html = (
            '<div class="warning"><strong>转换警告：</strong>'
            + html.escape("；".join(reference["conversion_warnings"]))
            + "</div>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(sample_id)} 人工标注逐字段复核</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", sans-serif; color: #17212b; background: #f4f6f8; }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    .notice, .policy, .warning {{ padding: 12px 16px; margin: 12px 0; border-radius: 6px; }}
    .notice {{ background: #fff7d6; border-left: 4px solid #d99b00; }}
    .policy {{ background: #eef7ff; border-left: 4px solid #2673b8; }}
    .warning {{ background: #fee; border-left: 4px solid #b42318; }}
    .layout {{ display: grid; grid-template-columns: minmax(420px, 0.9fr) minmax(680px, 1.4fr); gap: 18px; align-items: start; }}
    .image-panel, .table-panel {{ background: white; border: 1px solid #dce2e8; border-radius: 8px; padding: 14px; }}
    .image-panel {{ position: sticky; top: 12px; }}
    img {{ width: 100%; max-height: 86vh; object-fit: contain; background: #eef1f4; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border: 1px solid #dce2e8; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #edf2f7; z-index: 1; }}
    .text {{ white-space: pre-wrap; word-break: break-word; }}
    .duplicate {{ background: #fff8e8; }}
    .recorded {{ box-shadow: inset 5px 0 #2f855a; }}
    .symbols {{ color: #9b2c2c; font-weight: 700; }}
    .decision {{ min-width: 160px; }}
    textarea, select {{ width: 100%; box-sizing: border-box; font: inherit; }}
    textarea {{ min-height: 58px; }}
    code {{ background: #edf2f7; padding: 2px 5px; }}
    @media (max-width: 980px) {{ .layout {{ grid-template-columns: 1fr; }} .image-panel {{ position: static; }} }}
  </style>
</head>
<body>
<main>
  <h1>XFUND样本 {html.escape(sample_id)}：人工标注逐字段复核</h1>
  <p>当前标注复核状态：<code>{annotation_status}</code>；
     最终参考结果状态：<code>{final_status}</code>。</p>
  <div class="notice">
    下表来自XFUND显式question-answer关系，不预设其100%正确。
    请逐项查看原图；页面中的选择和备注不会自动保存，也不会改写原始标注。
  </div>
  <div class="policy">
    <strong>复核规则：</strong>
    同名多行既可能是数据集按行标注，也可能应合并为一个字段；请根据原图和教学表示目的裁决。
    ☑、□等符号必须原样核对，不自动转换为“是/否”。
    若字段正确选“确认原标注”；若需要修改，记录校正后的键、值和原因；看不清时选“不确定”。
  </div>
  {warning_html}
  <div class="layout">
    <section class="image-panel">
      <h2>原图</h2>
      <img src="{image_source}" alt="XFUND样本{html.escape(sample_id)}">
    </section>
    <section class="table-panel">
      <h2>数据集原始标注字段（{len(fields)}项）</h2>
      <table>
        <thead>
          <tr>
            <th>序号</th><th>实体ID</th><th>字段名</th><th>字段值</th>
            <th>提示</th><th>人工决定（本页不保存）</th><th>校正/备注草稿</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
  </div>
  <div class="policy">
    <strong>提交复核结果时请提供：</strong>
    确认无误的序号；需校正的序号、校正后字段名与字段值、原因；
    需要合并的序号及合并后键值；无法确认的序号。
    程序随后把决定写入<code>data/local/sample_reviews/{html.escape(sample_id)}.json</code>，
    保留原标注和可追踪实体ID。
  </div>
</main>
</body>
</html>
"""


def _render_row(
    index: int,
    field: dict[str, Any],
    duplicate_count: int,
    correction_by_pair: dict[tuple[str, str], dict[str, Any]],
    structure_by_pair: dict[tuple[str, str], dict[str, Any]],
) -> str:
    key = str(field["key"])
    value = str(field["value"])
    symbols = sorted({char for char in key + value if char in _SPECIAL_SYMBOLS})
    hints: list[str] = []
    row_classes: list[str] = []
    if duplicate_count > 1:
        hints.append(f"同名字段共{duplicate_count}项，请检查是否为多行内容")
        row_classes.append("duplicate")
    if symbols:
        hints.append("特殊符号：" + " ".join(symbols))
    entity_pair = (
        str(field["question_entity_id"]),
        str(field["answer_entity_id"]),
    )
    correction = correction_by_pair.get(entity_pair)
    if correction is not None:
        hints.append(
            f"已记录校正：{correction['action']}（{correction['correction_id']}）"
        )
        row_classes.append("recorded")
    structure = structure_by_pair.get(entity_pair)
    if structure is not None:
        hints.append(
            f"已记录结构：{structure['review_id']} / "
            f"{structure['row_id']} / 第{structure['column_index']}列"
        )
        row_classes.append("recorded")
    hint_text = "；".join(hints) or "—"
    row_class = (
        f' class="{html.escape(" ".join(dict.fromkeys(row_classes)))}"'
        if row_classes
        else ""
    )
    return f"""
          <tr{row_class}>
            <td>{index}</td>
            <td>Q:{html.escape(str(field['question_entity_id']))}<br>
                A:{html.escape(str(field['answer_entity_id']))}</td>
            <td class="text">{html.escape(key)}</td>
            <td class="text">{html.escape(value)}</td>
            <td class="symbols">{html.escape(hint_text)}</td>
            <td class="decision">
              <select aria-label="字段{index}人工决定">
                <option>待复核</option>
                <option>确认原标注</option>
                <option>修改字段名</option>
                <option>修改字段值</option>
                <option>修改键值对</option>
                <option>与同名行合并</option>
                <option>删除错误关系</option>
                <option>不确定</option>
              </select>
            </td>
            <td><textarea aria-label="字段{index}校正备注"
                placeholder="校正后的键/值、原因；本页内容不会自动保存"></textarea></td>
          </tr>"""


def _correction_by_entity_pair(
    review_record: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    corrections = review_record.get("annotation_review", {}).get(
        "corrections", []
    )
    for correction in corrections:
        question_id = correction.get("source_question_entity_id")
        answer_id = correction.get("source_answer_entity_id")
        if question_id is not None and answer_id is not None:
            result[(str(question_id), str(answer_id))] = correction
    return result


def _structure_by_entity_pair(
    review_record: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    structure_reviews = review_record.get("annotation_review", {}).get(
        "structure_reviews", []
    )
    for structure_review in structure_reviews:
        for row in structure_review.get("rows", []):
            for cell in row.get("cells", []):
                question_id = cell.get("source_question_entity_id")
                answer_id = cell.get("source_answer_entity_id")
                if question_id is None or answer_id is None:
                    continue
                result[(str(question_id), str(answer_id))] = {
                    "review_id": structure_review["review_id"],
                    "row_id": row["row_id"],
                    "column_index": cell["column_index"],
                }
    return result
