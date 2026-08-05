"""Deterministic audit helpers for the UCI Online Retail workbook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = (
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
)

SCHEMA_VERSION = "1.5.6-data-audit-v1"


class DataAuditError(ValueError):
    """Raised when the workbook cannot satisfy the minimum audit contract."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a local file."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_online_retail_workbook(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Read the first worksheet while preserving identifier columns as text."""

    if not path.is_file():
        raise DataAuditError(f"找不到原始数据文件：{path}")

    try:
        excel_file = pd.ExcelFile(path, engine="openpyxl")
        sheet_names = list(excel_file.sheet_names)
        if not sheet_names:
            raise DataAuditError("工作簿不包含任何工作表。")
        frame = excel_file.parse(
            sheet_name=sheet_names[0],
            dtype={
                "InvoiceNo": "string",
                "StockCode": "string",
                "Description": "string",
                "CustomerID": "string",
                "Country": "string",
            },
        )
    except DataAuditError:
        raise
    except Exception as exc:
        raise DataAuditError(f"无法读取工作簿：{exc}") from exc

    validate_required_columns(frame)
    return frame, sheet_names


def validate_required_columns(frame: pd.DataFrame) -> None:
    """Ensure all official UCI fields are present before computing statistics."""

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        joined = "、".join(missing_columns)
        raise DataAuditError(f"缺少必需字段：{joined}")


def _sign_counts(series: pd.Series) -> dict[str, int]:
    numeric = pd.to_numeric(series, errors="coerce")
    return {
        "positive_rows": int((numeric > 0).sum()),
        "zero_rows": int((numeric == 0).sum()),
        "negative_rows": int((numeric < 0).sum()),
        "missing_or_non_numeric_rows": int(numeric.isna().sum()),
    }


def _iso_or_none(value: Any) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def build_audit_report(
    frame: pd.DataFrame,
    *,
    workbook_path: Path | None = None,
    sheet_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe audit report without exporting customer identifiers."""

    validate_required_columns(frame)

    invoice_text = frame["InvoiceNo"].astype("string").str.strip()
    first_character = invoice_text.str.slice(0, 1)
    starts_upper_c = invoice_text.str.startswith("C", na=False)
    starts_lower_c = invoice_text.str.startswith("c", na=False)
    starts_c = starts_upper_c | starts_lower_c
    non_digit_prefix = first_character.str.fullmatch(r"\D", na=False)

    quantity = pd.to_numeric(frame["Quantity"], errors="coerce")
    unit_price = pd.to_numeric(frame["UnitPrice"], errors="coerce")
    invoice_dates = pd.to_datetime(frame["InvoiceDate"], errors="coerce")

    non_digit_prefix_counts = (
        first_character[non_digit_prefix]
        .value_counts(dropna=False)
        .head(20)
        .to_dict()
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "dataset_name": "Online Retail",
            "uci_dataset_id": 352,
            "doi": "10.24432/C5BW33",
            "official_page": "https://archive.ics.uci.edu/dataset/352/online+retail",
            "license": "CC BY 4.0",
        },
        "file": {
            "name": workbook_path.name if workbook_path else None,
            "size_bytes": workbook_path.stat().st_size
            if workbook_path and workbook_path.is_file()
            else None,
            "sha256": sha256_file(workbook_path)
            if workbook_path and workbook_path.is_file()
            else None,
            "sheet_names": sheet_names or [],
        },
        "structure": {
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "columns": [str(column) for column in frame.columns],
            "dtypes": {
                str(column): str(dtype)
                for column, dtype in frame.dtypes.items()
            },
            "duplicate_rows": int(frame.duplicated().sum()),
        },
        "missing_rows_by_column": {
            str(column): int(count)
            for column, count in frame.isna().sum().items()
        },
        "date": {
            "parsed_rows": int(invoice_dates.notna().sum()),
            "missing_or_unparseable_rows": int(invoice_dates.isna().sum()),
            "minimum": _iso_or_none(invoice_dates.min()),
            "maximum": _iso_or_none(invoice_dates.max()),
        },
        "unique_non_missing_values": {
            "invoices": int(invoice_text.nunique(dropna=True)),
            "products": int(frame["StockCode"].nunique(dropna=True)),
            "customers": int(frame["CustomerID"].nunique(dropna=True)),
            "countries": int(frame["Country"].nunique(dropna=True)),
        },
        "quantity": _sign_counts(quantity),
        "unit_price": _sign_counts(unit_price),
        "cancellation_signals": {
            "uppercase_c_rows": int(starts_upper_c.sum()),
            "lowercase_c_rows": int(starts_lower_c.sum()),
            "case_insensitive_c_rows": int(starts_c.sum()),
            "case_insensitive_c_unique_invoices": int(
                invoice_text[starts_c].nunique(dropna=True)
            ),
            "other_non_digit_prefix_rows": int(
                (non_digit_prefix & ~starts_c).sum()
            ),
            "non_digit_prefix_counts": {
                str(key): int(value)
                for key, value in non_digit_prefix_counts.items()
            },
        },
        "signal_overlap": {
            "c_prefix_and_negative_quantity_rows": int(
                (starts_c & (quantity < 0)).sum()
            ),
            "c_prefix_and_zero_quantity_rows": int(
                (starts_c & (quantity == 0)).sum()
            ),
            "c_prefix_and_positive_quantity_rows": int(
                (starts_c & (quantity > 0)).sum()
            ),
            "no_c_prefix_and_negative_quantity_rows": int(
                (~starts_c & (quantity < 0)).sum()
            ),
        },
        "privacy": {
            "customer_id_values_exported": False,
            "customer_id_missing_rows": int(frame["CustomerID"].isna().sum()),
            "public_output_rule": "aggregate_only",
        },
        "interpretation_status": {
            "c_prefix": "official_metadata_rule_only",
            "negative_quantity": "pending_h2_interpretation",
            "returns": "pending_h2_interpretation",
            "sales_amount": "not_computed_before_h2",
        },
    }
    return report


def masked_preview(frame: pd.DataFrame, row_count: int = 5) -> list[dict[str, Any]]:
    """Return a local preview with CustomerID values removed."""

    validate_required_columns(frame)
    preview = frame.head(max(row_count, 0)).copy()
    preview["CustomerID"] = preview["CustomerID"].map(
        lambda value: "<missing>" if pd.isna(value) else "<present>"
    )
    preview["InvoiceDate"] = pd.to_datetime(
        preview["InvoiceDate"], errors="coerce"
    ).map(_iso_or_none)
    preview = preview.astype(object).where(pd.notna(preview), None)
    return preview.to_dict(orient="records")


def save_audit_report(report: dict[str, Any], output_path: Path) -> None:
    """Save the report atomically as UTF-8 JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
