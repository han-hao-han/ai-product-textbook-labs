"""Deterministic H2 evidence for cleaning and metric-scope decisions."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pandas as pd

from src.data_audit import validate_required_columns


PROFILE_SCHEMA_VERSION = "1.5.6-cleaning-profile-v1"


def _rounded_sum(series: pd.Series, digits: int = 6) -> float:
    return round(float(series.sum()), digits)


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(
        frame.to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
    )


def _candidate_metrics(
    *,
    mask: pd.Series,
    invoice_no: pd.Series,
    customer_id: pd.Series,
    quantity: pd.Series,
    line_value: pd.Series,
) -> dict[str, Any]:
    selected_invoices = invoice_no[mask]
    selected_customers = customer_id[mask]
    known_customer_mask = mask & customer_id.notna()
    selected_rows = int(mask.sum())
    known_customer_rows = int(known_customer_mask.sum())
    selected_value = _rounded_sum(line_value[mask])
    known_customer_value = _rounded_sum(line_value[known_customer_mask])
    return {
        "rows": selected_rows,
        "unique_invoices": int(selected_invoices.nunique(dropna=True)),
        "quantity_sum": _rounded_sum(quantity[mask]),
        "mechanical_quantity_times_price_gbp": selected_value,
        "known_customer_rows": known_customer_rows,
        "unique_known_customers": int(
            selected_customers.nunique(dropna=True)
        ),
        "known_customer_mechanical_value_gbp": known_customer_value,
        "known_customer_row_ratio": round(
            known_customer_rows / max(selected_rows, 1),
            6,
        ),
        "known_customer_value_ratio": round(
            known_customer_value / max(selected_value, 1.0),
            6,
        ),
    }


def _top_grouped_records(
    frame: pd.DataFrame,
    *,
    mask: pd.Series,
    group_columns: list[str],
    quantity: pd.Series,
    unit_price: pd.Series,
    top_n: int,
) -> list[dict[str, Any]]:
    subset = frame.loc[mask, group_columns].copy()
    if subset.empty:
        return []

    subset["quantity_for_profile"] = quantity[mask].to_numpy()
    subset["unit_price_for_profile"] = unit_price[mask].to_numpy()
    grouped = (
        subset.groupby(group_columns, dropna=False)
        .agg(
            rows=("quantity_for_profile", "size"),
            quantity_sum=("quantity_for_profile", "sum"),
            minimum_unit_price=("unit_price_for_profile", "min"),
            maximum_unit_price=("unit_price_for_profile", "max"),
        )
        .reset_index()
        .sort_values(["rows", "quantity_sum"], ascending=[False, True])
        .head(top_n)
    )
    return _json_records(grouped)


def _decimal_places(value: float) -> int:
    decimal_value = Decimal(str(value)).normalize()
    return max(0, -decimal_value.as_tuple().exponent)


def build_cleaning_profile(
    frame: pd.DataFrame,
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    """Build read-only evidence without freezing or applying cleaning rules."""

    validate_required_columns(frame)
    if top_n <= 0:
        raise ValueError("top_n必须为正整数。")

    invoice_no = frame["InvoiceNo"].astype("string").str.strip()
    stock_code = frame["StockCode"].astype("string").str.strip()
    description = (
        frame["Description"]
        .astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )
    customer_id = frame["CustomerID"].astype("string").str.strip()
    country_raw = frame["Country"].astype("string")
    country_trimmed = country_raw.str.strip()
    quantity = pd.to_numeric(frame["Quantity"], errors="coerce")
    unit_price = pd.to_numeric(frame["UnitPrice"], errors="coerce")
    line_value = quantity * unit_price

    starts_c = invoice_no.str.startswith(("C", "c"), na=False)
    negative_quantity_no_c = ~starts_c & quantity.lt(0)
    zero_unit_price = unit_price.eq(0)
    negative_unit_price = unit_price.lt(0)
    normal_sales_candidate = (
        ~starts_c & quantity.gt(0) & unit_price.gt(0)
    )

    record_class = pd.Series(
        "other_unclassified",
        index=frame.index,
        dtype="string",
    )
    record_class.loc[normal_sales_candidate] = "normal_sales_candidate"
    record_class.loc[zero_unit_price & ~starts_c] = "zero_unit_price_no_c"
    record_class.loc[negative_quantity_no_c] = "negative_quantity_no_c"
    record_class.loc[negative_unit_price & ~starts_c] = (
        "negative_unit_price_no_c"
    )
    record_class.loc[starts_c] = "cancelled_c_prefix"

    profile_frame = pd.DataFrame(
        {
            "record_class": record_class,
            "invoice_no": invoice_no,
            "quantity": quantity,
            "line_value": line_value,
        }
    )
    classification = (
        profile_frame.groupby("record_class", dropna=False)
        .agg(
            rows=("record_class", "size"),
            unique_invoices=("invoice_no", "nunique"),
            quantity_sum=("quantity", "sum"),
            mechanical_quantity_times_price_gbp=("line_value", "sum"),
        )
        .reset_index()
        .sort_values("record_class")
    )

    duplicate_after_first = frame.duplicated()
    duplicate_all_occurrences = frame.duplicated(keep=False)
    classification_after_keep_first = (
        profile_frame.loc[~duplicate_after_first]
        .groupby("record_class", dropna=False)
        .agg(
            rows=("record_class", "size"),
            unique_invoices=("invoice_no", "nunique"),
            quantity_sum=("quantity", "sum"),
            mechanical_quantity_times_price_gbp=("line_value", "sum"),
        )
        .reset_index()
        .sort_values("record_class")
    )
    normal_after_dedup = normal_sales_candidate & ~duplicate_after_first
    normal_before_metrics = _candidate_metrics(
        mask=normal_sales_candidate,
        invoice_no=invoice_no,
        customer_id=customer_id,
        quantity=quantity,
        line_value=line_value,
    )
    normal_after_metrics = _candidate_metrics(
        mask=normal_after_dedup,
        invoice_no=invoice_no,
        customer_id=customer_id,
        quantity=quantity,
        line_value=line_value,
    )

    missing_description = description.isna()
    missing_customer = customer_id.isna()
    normal_missing_customer = normal_sales_candidate & missing_customer

    normal_invoice_customer = pd.DataFrame(
        {
            "invoice_no": invoice_no[normal_sales_candidate],
            "customer_known": customer_id[normal_sales_candidate].notna(),
        }
    )
    invoice_customer_flags = normal_invoice_customer.groupby(
        "invoice_no", dropna=False
    )["customer_known"].agg(["any", "all"])

    known_customer_sales_value = _rounded_sum(
        line_value[normal_sales_candidate & ~missing_customer]
    )
    normal_sales_value = _rounded_sum(line_value[normal_sales_candidate])

    description_pairs = pd.DataFrame(
        {
            "stock_code": stock_code,
            "description_key": description.str.casefold(),
        }
    ).dropna()
    distinct_descriptions = (
        description_pairs.groupby("stock_code", dropna=False)[
            "description_key"
        ]
        .nunique()
        .sort_values(ascending=False)
    )
    conflicting_descriptions = distinct_descriptions[
        distinct_descriptions > 1
    ]
    conflict_rows = (
        conflicting_descriptions.head(top_n)
        .rename("distinct_normalized_descriptions")
        .reset_index()
    )

    invoice_customer_counts = (
        pd.DataFrame(
            {
                "invoice_no": invoice_no,
                "customer_id": customer_id,
            }
        )
        .groupby("invoice_no", dropna=False)["customer_id"]
        .nunique(dropna=True)
    )
    invoice_country_counts = (
        pd.DataFrame(
            {
                "invoice_no": invoice_no,
                "country": country_trimmed,
            }
        )
        .groupby("invoice_no", dropna=False)["country"]
        .nunique(dropna=True)
    )

    unique_prices = pd.Series(unit_price.dropna().unique())
    price_to_places = {
        float(value): _decimal_places(float(value))
        for value in unique_prices
    }
    decimal_place_counts = (
        unit_price.dropna()
        .map(price_to_places)
        .value_counts()
        .sort_index()
    )

    report: dict[str, Any] = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "purpose": (
            "H2 cleaning and metric-scope evidence; no cleaning applied"
        ),
        "classification_is_provisional": True,
        "classification_precedence": [
            "cancelled_c_prefix",
            "negative_unit_price_no_c",
            "negative_quantity_no_c",
            "zero_unit_price_no_c",
            "normal_sales_candidate",
            "other_unclassified",
        ],
        "record_classification": _json_records(classification),
        "record_classification_after_keep_first": _json_records(
            classification_after_keep_first
        ),
        "signal_counts": {
            "normal_sales_candidate_rows": int(
                normal_sales_candidate.sum()
            ),
            "c_prefix_rows": int(starts_c.sum()),
            "negative_quantity_no_c_rows": int(
                negative_quantity_no_c.sum()
            ),
            "zero_unit_price_rows": int(zero_unit_price.sum()),
            "negative_unit_price_rows": int(negative_unit_price.sum()),
        },
        "negative_quantity_no_c_top_groups": _top_grouped_records(
            frame.assign(
                StockCode=stock_code,
                Description=description,
            ),
            mask=negative_quantity_no_c,
            group_columns=["StockCode", "Description"],
            quantity=quantity,
            unit_price=unit_price,
            top_n=top_n,
        ),
        "zero_unit_price_top_groups": _top_grouped_records(
            frame.assign(
                StockCode=stock_code,
                Description=description,
            ),
            mask=zero_unit_price,
            group_columns=["StockCode", "Description"],
            quantity=quantity,
            unit_price=unit_price,
            top_n=top_n,
        ),
        "negative_unit_price_groups": _top_grouped_records(
            frame.assign(
                InvoiceNo=invoice_no,
                StockCode=stock_code,
                Description=description,
                Country=country_trimmed,
            ),
            mask=negative_unit_price,
            group_columns=[
                "InvoiceNo",
                "StockCode",
                "Description",
                "Country",
            ],
            quantity=quantity,
            unit_price=unit_price,
            top_n=top_n,
        ),
        "missing_description_cross_checks": {
            "rows": int(missing_description.sum()),
            "customer_missing_rows": int(
                (missing_description & missing_customer).sum()
            ),
            "c_prefix_rows": int(
                (missing_description & starts_c).sum()
            ),
            "negative_quantity_no_c_rows": int(
                (missing_description & negative_quantity_no_c).sum()
            ),
            "zero_unit_price_rows": int(
                (missing_description & zero_unit_price).sum()
            ),
            "positive_quantity_positive_price_no_c_rows": int(
                (missing_description & normal_sales_candidate).sum()
            ),
        },
        "customer_coverage_for_normal_sales_candidate": {
            "total_rows": int(normal_sales_candidate.sum()),
            "known_customer_rows": int(
                (normal_sales_candidate & ~missing_customer).sum()
            ),
            "missing_customer_rows": int(normal_missing_customer.sum()),
            "known_customer_row_ratio": round(
                float(
                    (
                        normal_sales_candidate & ~missing_customer
                    ).sum()
                    / max(int(normal_sales_candidate.sum()), 1)
                ),
                6,
            ),
            "total_invoices": int(
                invoice_no[normal_sales_candidate].nunique(dropna=True)
            ),
            "invoices_with_any_known_customer": int(
                invoice_customer_flags["any"].sum()
            ),
            "invoices_with_only_missing_customer": int(
                (~invoice_customer_flags["any"]).sum()
            ),
            "invoices_mixing_known_and_missing_customer_rows": int(
                (
                    invoice_customer_flags["any"]
                    & ~invoice_customer_flags["all"]
                ).sum()
            ),
            "normal_candidate_mechanical_value_gbp": normal_sales_value,
            "known_customer_mechanical_value_gbp": (
                known_customer_sales_value
            ),
            "known_customer_value_ratio": round(
                known_customer_sales_value
                / max(normal_sales_value, 1.0),
                6,
            ),
            "customer_id_values_exported": False,
        },
        "exact_duplicate_sensitivity": {
            "all_duplicate_occurrence_rows": int(
                duplicate_all_occurrences.sum()
            ),
            "rows_removed_if_keep_first": int(
                duplicate_after_first.sum()
            ),
            "duplicate_group_count": int(
                frame.loc[duplicate_all_occurrences]
                .groupby(list(frame.columns), dropna=False)
                .ngroups
            ),
            "normal_candidate_before_dedup": normal_before_metrics,
            "normal_candidate_after_keep_first": normal_after_metrics,
            "difference_if_keep_first": {
                key: round(
                    float(normal_before_metrics[key])
                    - float(normal_after_metrics[key]),
                    6,
                )
                for key in (
                    "rows",
                    "unique_invoices",
                    "quantity_sum",
                    "mechanical_quantity_times_price_gbp",
                    "known_customer_rows",
                    "unique_known_customers",
                    "known_customer_mechanical_value_gbp",
                )
            },
            "recommendation_status": "pending_h2_freeze",
        },
        "product_description_consistency": {
            "stock_codes_with_description": int(
                distinct_descriptions.size
            ),
            "stock_codes_with_multiple_normalized_descriptions": int(
                conflicting_descriptions.size
            ),
            "maximum_descriptions_for_one_stock_code": int(
                distinct_descriptions.max()
                if not distinct_descriptions.empty
                else 0
            ),
            "top_conflicts": _json_records(conflict_rows),
        },
        "invoice_consistency": {
            "invoices_with_multiple_known_customers": int(
                (invoice_customer_counts > 1).sum()
            ),
            "invoices_with_multiple_countries": int(
                (invoice_country_counts > 1).sum()
            ),
        },
        "country_normalization": {
            "raw_unique_non_missing": int(
                country_raw.nunique(dropna=True)
            ),
            "trimmed_unique_non_missing": int(
                country_trimmed.nunique(dropna=True)
            ),
            "rows_changed_by_trim": int(
                (
                    country_raw.notna()
                    & country_trimmed.notna()
                    & country_raw.ne(country_trimmed)
                ).sum()
            ),
        },
        "unit_price_precision": {
            "maximum_decimal_places_observed": int(
                max(price_to_places.values(), default=0)
            ),
            "row_counts_by_decimal_places": {
                str(int(places)): int(count)
                for places, count in decimal_place_counts.items()
            },
        },
        "interpretation_status": {
            "normal_sales_candidate": "pending_h2_freeze",
            "negative_quantity_no_c": "not_assumed_to_be_return",
            "zero_unit_price": "not_assumed_to_be_gift",
            "negative_unit_price": "not_assumed_to_be_refund",
            "exact_duplicates": "sensitivity_only_not_removed",
            "mechanical_quantity_times_price_gbp": (
                "diagnostic_only_not_frozen_sales_metric"
            ),
        },
    }
    return report
