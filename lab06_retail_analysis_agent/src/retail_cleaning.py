"""Apply the frozen H2 cleaning contract to the fixed retail dataset."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.data_audit import DataAuditError, validate_required_columns


@dataclass(frozen=True)
class RetailDataLayers:
    classified: pd.DataFrame
    sales_fact: pd.DataFrame
    customer_fact: pd.DataFrame
    exceptions: pd.DataFrame


def _normalized_string(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _normalized_description(series: pd.Series) -> pd.Series:
    return (
        _normalized_string(series)
        .str.replace(r"\s+", " ", regex=True)
        .replace("", pd.NA)
    )


def _integer_series(series: pd.Series, *, column: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise DataAuditError(f"{column}存在缺失或无法解析的数值。")
    rounded = numeric.round()
    if numeric.sub(rounded).abs().gt(1e-9).any():
        raise DataAuditError(f"{column}包含非整数值。")
    return rounded.astype("int64")


def _customer_id_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    known = numeric.dropna()
    if known.sub(known.round()).abs().gt(1e-9).any():
        raise DataAuditError("CustomerID包含非整数标识。")
    return numeric.round().astype("Int64").astype("string")


def _unit_price_milli_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise DataAuditError("UnitPrice存在缺失或无法解析的数值。")
    scaled = numeric.mul(1000)
    rounded = scaled.round()
    if scaled.sub(rounded).abs().gt(1e-7).any():
        raise DataAuditError("UnitPrice精度超过冻结的三位小数口径。")
    return rounded.astype("int64")


def _canonical_product_names(sales: pd.DataFrame) -> pd.Series:
    described = sales.loc[
        sales["description"].notna(),
        ["stock_code", "description"],
    ]
    if described.empty:
        return pd.Series(dtype="string", name="product_name")

    counts = (
        described.groupby(
            ["stock_code", "description"],
            dropna=False,
        )
        .size()
        .rename("rows")
        .reset_index()
        .sort_values(
            ["stock_code", "rows", "description"],
            ascending=[True, False, True],
            kind="stable",
        )
    )
    canonical = counts.drop_duplicates("stock_code", keep="first")
    return canonical.set_index("stock_code")["description"].rename(
        "product_name"
    )


def build_retail_data_layers(frame: pd.DataFrame) -> RetailDataLayers:
    """Return deterministic derived layers without modifying the raw frame."""

    validate_required_columns(frame)

    classified = pd.DataFrame(index=frame.index)
    classified["source_row_number"] = pd.Series(
        range(2, len(frame) + 2),
        index=frame.index,
        dtype="int64",
    )
    classified["is_exact_duplicate_after_first"] = frame.duplicated(
        keep="first"
    )
    classified["invoice_no"] = _normalized_string(frame["InvoiceNo"])
    classified["stock_code"] = _normalized_string(frame["StockCode"])
    classified["description"] = _normalized_description(
        frame["Description"]
    )
    classified["quantity"] = _integer_series(
        frame["Quantity"],
        column="Quantity",
    )
    classified["invoice_date"] = pd.to_datetime(
        frame["InvoiceDate"],
        errors="coerce",
    )
    if classified["invoice_date"].isna().any():
        raise DataAuditError("InvoiceDate存在缺失或无法解析的时间。")
    classified["unit_price_milli_gbp"] = _unit_price_milli_series(
        frame["UnitPrice"]
    )
    classified["customer_id"] = _customer_id_series(frame["CustomerID"])
    classified["country"] = _normalized_string(frame["Country"])
    classified["line_amount_milli_gbp"] = (
        classified["quantity"]
        * classified["unit_price_milli_gbp"]
    )

    starts_c = classified["invoice_no"].str.startswith(
        ("C", "c"),
        na=False,
    )
    record_class = pd.Series(
        "other_unclassified",
        index=classified.index,
        dtype="string",
    )
    record_class.loc[
        ~starts_c
        & classified["quantity"].gt(0)
        & classified["unit_price_milli_gbp"].gt(0)
    ] = "sale"
    record_class.loc[
        ~starts_c & classified["unit_price_milli_gbp"].eq(0)
    ] = "zero_price_non_sale"
    record_class.loc[
        ~starts_c & classified["quantity"].lt(0)
    ] = "inventory_adjustment"
    record_class.loc[
        ~starts_c & classified["unit_price_milli_gbp"].lt(0)
    ] = "financial_adjustment"
    record_class.loc[starts_c] = "cancelled"
    classified["record_class"] = record_class

    active = ~classified["is_exact_duplicate_after_first"]
    sales_fact = classified.loc[
        active & classified["record_class"].eq("sale")
    ].copy()
    canonical_names = _canonical_product_names(sales_fact)
    sales_fact["product_name"] = sales_fact["stock_code"].map(
        canonical_names
    )
    customer_fact = sales_fact.loc[
        sales_fact["customer_id"].notna()
    ].copy()
    exceptions = classified.loc[
        active & ~classified["record_class"].eq("sale")
    ].copy()

    return RetailDataLayers(
        classified=classified,
        sales_fact=sales_fact,
        customer_fact=customer_fact,
        exceptions=exceptions,
    )
