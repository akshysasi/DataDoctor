from io import BytesIO
import json
from secrets import token_hex
from datetime import datetime
from math import ceil, isfinite

from flask import Flask, jsonify, render_template, request, send_file, session
import pandas as pd

from analyzer import (
    analyze_dataset,
    convert_column_type,
    detect_anomalies,
    fill_missing_values,
    outlier_columns_by_row,
    outlier_row_mask,
    standardize_category_values,
)

from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
app.secret_key = token_hex(32)
_active_datasets = {}

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def _now_label():
    return datetime.now().astimezone().strftime("%b %d, %H:%M")


def _apply_cleaning(state, cleaned_df, operation, label):
    if cleaned_df.equals(state["current"]):
        return False
    state["undo"] = state["current"].copy()
    state["current"] = cleaned_df
    operation = {**operation, "applied_at": _now_label()}
    state.setdefault("operations", []).append(operation)
    state.setdefault("activity", []).append({"label": label, "time": operation["applied_at"]})
    state["activity"] = state["activity"][-20:]
    state["revision"] = state.get("revision", 0) + 1
    state["anomaly_cache"] = None
    return True


def _anomaly_result(state, contamination, run=False):
    contamination = float(contamination)
    cache = state.get("anomaly_cache")
    revision = state.get("revision", 0)
    if (
        cache
        and cache["revision"] == revision
        and cache["contamination"] == contamination
    ):
        return cache
    if not run:
        return None

    mask, scores, error = detect_anomalies(state["current"], contamination)
    cache = {
        "revision": revision,
        "contamination": contamination,
        "mask": mask.to_numpy(dtype=bool).tolist(),
        "scores": scores.tolist(),
        "error": error,
    }
    state["anomaly_cache"] = cache
    return cache


def _json_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not isfinite(value):
        return str(value)
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


@app.get("/api/explorer")
def explorer_data():
    dataset_id = session.get("dataset_id")
    state = _active_datasets.get(dataset_id)
    if state is None:
        return jsonify({"error": "Upload a CSV to explore its rows."}), 404

    frame = state["current"]
    query = request.args.get("q", "").strip()[:250]
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", 10))
    except ValueError:
        page_size = 10
    if page_size not in {10, 25, 50}:
        page_size = 10

    filtered = frame
    if query:
        matches = pd.Series(False, index=frame.index, dtype=bool)
        for column in frame.columns:
            matches |= frame[column].astype("string").str.contains(
                query, case=False, regex=False, na=False
            )
        filtered = frame.loc[matches]

    total_rows = len(filtered)
    pages = max(1, ceil(total_rows / page_size))
    page = min(page, pages)
    start = (page - 1) * page_size
    page_frame = filtered.iloc[start:start + page_size]
    columns = [
        {
            "name": str(column),
            "dtype": str(frame[column].dtype),
            "missing": int(frame[column].isna().sum()),
            "unique": int(frame[column].nunique(dropna=True)),
        }
        for column in frame.columns
    ]
    rows = [
        {
            "index": start + offset + 1,
            "cells": [
                {"value": _json_value(value), "missing": bool(pd.isna(value))}
                for value in row
            ],
        }
        for offset, row in enumerate(page_frame.itertuples(index=False, name=None))
    ]
    return jsonify({
        "columns": columns,
        "rows": rows,
        "page": page,
        "pages": pages,
        "page_size": page_size,
        "total_rows": total_rows,
        "dataset_rows": len(frame),
        "query": query,
    })


def build_cleaning_script(operations):
    """Build a standalone pandas script that replays the active clean history."""
    lines = [
        "#!/usr/bin/env python3",
        '"""Reproduce DataDoctor cleaning actions on a source CSV."""',
        "import argparse",
        "import numpy as np",
        "import pandas as pd",
        "from sklearn.ensemble import IsolationForest",
        "",
        "def remove_iqr_outliers(frame):",
        "    flagged = np.zeros(len(frame), dtype=bool)",
        "    for column in frame.select_dtypes(include=np.number).columns:",
        "        values = frame[column]",
        "        observed = values.dropna()",
        "        if len(observed) < 4:",
        "            continue",
        "        q1, q3 = observed.quantile(0.25), observed.quantile(0.75)",
        "        iqr = q3 - q1",
        "        if iqr == 0:",
        "            continue",
        "        flagged |= ((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).fillna(False).to_numpy(dtype=bool)",
        "    return frame.loc[~flagged].reset_index(drop=True)",
        "",
        "def remove_isolation_forest_anomalies(frame, contamination):",
        "    if len(frame) < 5:",
        "        return frame",
        "    numeric = frame.select_dtypes(include=np.number)",
        "    usable = [column for column in numeric.columns if numeric[column].notna().any() and numeric[column].nunique(dropna=True) > 1]",
        "    if not usable:",
        "        return frame",
        "    features = numeric[usable].fillna(numeric[usable].median())",
        "    model = IsolationForest(n_estimators=100, contamination=contamination, random_state=42)",
        "    labels = model.fit_predict(features)",
        "    return frame.loc[labels != -1].reset_index(drop=True)",
        "",
        "parser = argparse.ArgumentParser(description=__doc__)",
        "parser.add_argument('input_csv', help='Source CSV to clean')",
        "parser.add_argument('output_csv', help='Path for the cleaned CSV')",
        "args = parser.parse_args()",
        "df = pd.read_csv(args.input_csv)",
        "",
    ]

    for step, action in enumerate(operations, start=1):
        operation = action.get("operation")
        lines.append(f"# Cleaning step {step}: {operation}")
        if operation == "remove_duplicates":
            lines.append("df = df.drop_duplicates().reset_index(drop=True)")
        elif operation == "fill_missing":
            strategy = action.get("strategy", "median")
            if strategy not in {"mean", "median"}:
                continue
            lines.extend([
                "numeric_columns = df.select_dtypes(include=np.number).columns",
                "for column in numeric_columns:",
                f"    fill_value = df[column].{strategy}()",
                "    if pd.notna(fill_value):",
                "        df[column] = df[column].fillna(fill_value)",
                "for column in df.columns.difference(numeric_columns, sort=False):",
                "    mode = df[column].mode(dropna=True)",
                "    if not mode.empty:",
                "        df[column] = df[column].fillna(mode.iloc[0])",
            ])
        elif operation == "remove_outliers":
            lines.append("df = remove_iqr_outliers(df)")
        elif operation == "remove_anomalies":
            contamination = float(action.get("contamination", 0.05))
            lines.append(f"df = remove_isolation_forest_anomalies(df, {contamination!r})")
        elif operation == "convert_type":
            column = repr(action.get("column", ""))
            target_type = action.get("target_type")
            if target_type == "number":
                lines.append(f"df[{column}] = pd.to_numeric(df[{column}], errors='raise')")
            elif target_type == "date":
                lines.append(f"df[{column}] = pd.to_datetime(df[{column}], errors='raise')")
            elif target_type == "text":
                lines.append(f"df[{column}] = df[{column}].astype('string')")
        elif operation == "standardize_category":
            column = repr(action.get("column", ""))
            mode = action.get("mode", "trim")
            if mode not in {"trim", "lower", "title"}:
                continue
            lines.append(f"values = df[{column}].astype('string').str.strip()")
            if mode == "lower":
                lines.append("values = values.str.lower()")
            elif mode == "title":
                lines.append("values = values.str.title()")
            lines.append(f"df[{column}] = values")
        lines.append("")

    lines.extend([
        "df.to_csv(args.output_csv, index=False, encoding='utf-8-sig')",
        "print(f'Cleaned CSV saved to {args.output_csv}')",
    ])
    return BytesIO(("\n".join(lines) + "\n").encode("utf-8"))


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    return render_template(
        "index.html",
        report=None,
        error="That file is too large. Please choose a CSV smaller than 16 MB.",
    ), 413

@app.route("/", methods=["GET", "POST"])
def index():
    report = None
    error = None
    notice = None
    filename = None
    preview_columns = []
    preview_rows = []
    cleaning_preview = False
    rows_before = 0
    rows_after = 0
    missing_before = 0
    missing_after = 0
    cleaned_preview_columns = []
    cleaned_preview_rows = []
    duplicate_preview_columns = []
    duplicate_preview_rows = []
    active_df = None
    original_df = None
    duplicate_rows = 0
    can_undo = False
    missing_cells = 0
    missing_preview_columns = []
    missing_preview_rows = []
    missing_preview = False
    missing_cells_after = 0
    numeric_strategy = "median"
    outlier_rows_count = 0
    outlier_preview_columns = []
    outlier_preview_rows = []
    outlier_preview = False
    type_columns = []
    type_column = ""
    type_target = "number"
    type_preview = False
    type_preview_rows = []
    type_source_dtype = ""
    type_result_dtype = ""
    type_invalid_count = 0
    category_columns = []
    category_column = ""
    category_mode = "trim"
    category_preview = False
    category_preview_rows = []
    category_changed_count = 0
    anomaly_contamination = "0.05"
    anomaly_rows_count = 0
    anomaly_preview = False
    anomaly_preview_columns = []
    anomaly_preview_rows = []
    anomaly_detection_error = None
    anomaly_count_available = False
    anomaly_scores = []
    quality_distribution = []
    numeric_summary_rows = []
    column_profiles = []
    activity = []
    is_modified = False

    if request.method == "POST":
        uploaded_file = request.files.get("file")
        action = request.form.get("action", "analyze")
        numeric_strategy = request.form.get("numeric_strategy", "median")
        type_column = request.form.get("type_column", "")
        type_target = request.form.get("type_target", "number")
        category_column = request.form.get("category_column", "")
        category_mode = request.form.get("category_mode", "trim")
        anomaly_contamination = request.form.get("anomaly_contamination", "0.05")

        try:
            if uploaded_file is not None and uploaded_file.filename and action == "analyze":
                if not uploaded_file.filename.lower().endswith(".csv"):
                    raise ValueError("Please choose a file with a .csv extension.")
                filename = uploaded_file.filename
                df = pd.read_csv(uploaded_file)
                if len(df.columns) == 0:
                    raise ValueError("This CSV does not contain a header row.")
                dataset_id = session.get("dataset_id") or token_hex(16)
                session["dataset_id"] = dataset_id
                _active_datasets[dataset_id] = {
                    "original": df.copy(), "current": df.copy(),
                    "undo": None, "filename": filename, "operations": [],
                    "activity": [], "revision": 0, "anomaly_cache": None,
                }
            dataset_id = session.get("dataset_id")
            state = _active_datasets.get(dataset_id)
            if state is None:
                if not error:
                    error = "Upload and analyze a CSV before using the Cleaning Studio."
            else:
                filename = state["filename"]
                operations = state.setdefault("operations", [])
                if action == "apply_duplicates":
                    cleaned = state["current"].drop_duplicates().reset_index(drop=True)
                    removed = len(state["current"]) - len(cleaned)
                    if _apply_cleaning(state, cleaned, {"operation": "remove_duplicates"}, "Removed duplicate rows"):
                        notice = f"Removed {removed:,} duplicate row(s)."
                    else:
                        notice = "No duplicate rows needed removal."
                elif action == "apply_missing":
                    cleaned = fill_missing_values(
                        state["current"],
                        numeric_strategy=numeric_strategy,
                    )
                    filled = int(state["current"].isna().sum().sum() - cleaned.isna().sum().sum())
                    if _apply_cleaning(
                        state, cleaned,
                        {"operation": "fill_missing", "strategy": numeric_strategy},
                        f"Filled missing values using {numeric_strategy}",
                    ):
                        notice = f"Filled {filled:,} missing cell(s) using {numeric_strategy}."
                    else:
                        notice = "No missing values could be filled in this dataset."
                elif action == "apply_outliers":
                    outlier_mask = outlier_row_mask(state["current"])
                    removed = int(outlier_mask.sum())
                    cleaned = state["current"].loc[~outlier_mask].reset_index(drop=True)
                    if _apply_cleaning(state, cleaned, {"operation": "remove_outliers"}, "Removed IQR outlier rows"):
                        notice = f"Removed {removed:,} row(s) flagged by the IQR check."
                    else:
                        notice = "The IQR check did not flag any rows."
                elif action == "apply_anomalies":
                    anomaly_cache = _anomaly_result(state, anomaly_contamination, run=True)
                    anomaly_detection_error = anomaly_cache["error"]
                    if not anomaly_detection_error:
                        anomaly_mask = pd.Series(anomaly_cache["mask"], index=state["current"].index)
                        removed = int(anomaly_mask.sum())
                        cleaned = state["current"].loc[~anomaly_mask].reset_index(drop=True)
                        if _apply_cleaning(
                            state, cleaned,
                            {"operation": "remove_anomalies", "contamination": float(anomaly_contamination)},
                            "Removed Isolation Forest anomaly rows",
                        ):
                            notice = f"Removed {removed:,} row(s) flagged by Isolation Forest."
                        else:
                            notice = "Isolation Forest did not flag any rows with this setting."

                elif action == "apply_type":
                    if type_column not in state["current"].columns:
                        error = "Choose a column before applying a type conversion."
                    else:
                        proposed_df, invalid_count = convert_column_type(
                            state["current"], type_column, type_target
                        )
                        if invalid_count:
                            error = (
                                f"Conversion stopped: {invalid_count} non-empty value(s) "
                                "cannot be converted. Review the preview first."
                            )
                        elif _apply_cleaning(
                            state, proposed_df,
                            {"operation": "convert_type", "column": str(type_column), "target_type": type_target},
                            f"Converted {type_column} to {type_target}",
                        ):
                            notice = f"Converted {type_column} to {type_target}."
                        else:
                            notice = f"{type_column} already matches {type_target}."
                elif action == "apply_standardize":
                    try:
                        proposed_df, changed_count = standardize_category_values(
                            state["current"], category_column, category_mode
                        )
                    except ValueError as exc:
                        error = str(exc)
                    else:
                        if changed_count:
                            _apply_cleaning(
                                state, proposed_df,
                                {"operation": "standardize_category", "column": str(category_column), "mode": category_mode},
                                f"Standardized {category_column} ({category_mode})",
                            )
                            notice = f"Standardized {changed_count:,} value(s) in {category_column}."
                        else:
                            notice = "No values in this column needed standardization."
                elif action in {"undo_duplicates", "undo_operation"} and state["undo"] is not None:
                    state["current"] = state["undo"]
                    state["undo"] = None
                    if operations:
                        undone = operations.pop()
                    else:
                        undone = {"operation": "last cleaning action"}
                    state["revision"] = state.get("revision", 0) + 1
                    state["anomaly_cache"] = None
                    state.setdefault("activity", []).append({
                        "label": f"Undid {undone.get('operation', 'last cleaning action').replace('_', ' ')}",
                        "time": _now_label(),
                    })
                    state["activity"] = state["activity"][-20:]
                    notice = "Undid the last cleaning action."
                elif action == "reset_dataset":
                    state["current"] = state["original"].copy()
                    state["undo"] = None
                    operations.clear()
                    state["revision"] = state.get("revision", 0) + 1
                    state["anomaly_cache"] = None
                    state.setdefault("activity", []).append({"label": "Reset to uploaded data", "time": _now_label()})
                    state["activity"] = state["activity"][-20:]
                    notice = "Reset the active dataset to the uploaded data."

                active_df = state["current"]
                original_df = state["original"]
                activity = list(reversed(state.get("activity", [])[-6:]))
                is_modified = not active_df.equals(original_df)
                type_columns = active_df.columns.tolist()
                category_columns = [
                    column for column in active_df.columns
                    if pd.api.types.is_object_dtype(active_df[column].dtype)
                    or pd.api.types.is_string_dtype(active_df[column].dtype)
                    or isinstance(active_df[column].dtype, pd.CategoricalDtype)
                ]
                duplicate_rows = int(active_df.duplicated().sum())
                outlier_mask = outlier_row_mask(active_df)
                outlier_rows_count = int(outlier_mask.sum())
                anomaly_cache = _anomaly_result(
                    state, anomaly_contamination,
                    run=action in {"preview_anomalies", "apply_anomalies"},
                )
                if anomaly_cache:
                    anomaly_count_available = not anomaly_cache["error"]
                    anomaly_detection_error = anomaly_cache["error"]
                    anomaly_rows_count = sum(anomaly_cache["mask"])
                    anomaly_scores = anomaly_cache["scores"]
                    anomaly_mask = pd.Series(anomaly_cache["mask"], index=active_df.index)
                can_undo = state["undo"] is not None
                missing_cells = int(active_df.isna().sum().sum())
                report = analyze_dataset(active_df)
                quality_distribution = [
                    {"label": "Complete cells", "value": max(0, active_df.size - missing_cells), "color": "#2dd4bf"},
                    {"label": "Missing cells", "value": missing_cells, "color": "#f59e0b"},
                ]
                numeric_summary_rows = [
                    {"column": str(column), "mean": float(active_df[column].mean()), "median": float(active_df[column].median())}
                    for column in active_df.select_dtypes(include="number").columns[:6]
                    if active_df[column].notna().any()
                ]
                column_profiles = [
                    {"name": str(column), "dtype": str(active_df[column].dtype),
                     "missing": int(active_df[column].isna().sum()),
                     "unique": int(active_df[column].nunique(dropna=True))}
                    for column in active_df.columns
                ]
                preview_columns = active_df.columns.tolist()
                preview_rows = active_df.head(10).to_dict(orient="records")
                duplicate_preview = active_df.loc[active_df.duplicated(keep="first")]
                duplicate_preview_columns = duplicate_preview.columns.tolist()
                duplicate_preview_rows = duplicate_preview.head(10).to_dict(orient="records")
                cleaning_preview = action == "preview_duplicates"
                rows_before = len(active_df)
                rows_after = len(active_df) - duplicate_rows
                missing_before = int(active_df.isna().sum().sum())
                missing_after = missing_before
                missing_cells = missing_before
                missing_cells_after = missing_before
                missing_preview = action == "preview_missing"
                if missing_preview:
                    proposed_df = fill_missing_values(active_df, numeric_strategy=numeric_strategy)
                    affected = active_df.isna().any(axis=1)
                    missing_preview_columns = proposed_df.columns.tolist()
                    missing_preview_rows = proposed_df.loc[affected].head(10).to_dict(orient="records")
                    missing_cells_after = int(proposed_df.isna().sum().sum())
                outlier_preview = action == "preview_outliers"
                if outlier_preview:
                    original_mask = outlier_row_mask(active_df)
                    flagged_df = active_df.loc[original_mask]
                    outlier_preview_columns = active_df.columns.tolist()
                    outlier_preview_rows = flagged_df.head(10).to_dict(orient="records")
                    flagged_columns = outlier_columns_by_row(active_df)
                    flagged_positions = [i for i, flagged in enumerate(original_mask.to_numpy()) if flagged][:10]
                    for row, position in zip(outlier_preview_rows, flagged_positions):
                        row["__outlier_columns__"] = flagged_columns[position]
                anomaly_preview = action == "preview_anomalies"
                if anomaly_preview and not anomaly_detection_error:
                    flagged_positions = [i for i, flagged in enumerate(anomaly_mask.to_numpy()) if flagged][:10]
                    anomaly_preview_columns = active_df.columns.tolist()
                    anomaly_preview_rows = active_df.iloc[flagged_positions].to_dict(orient="records")
                    for row, position in zip(anomaly_preview_rows, flagged_positions):
                        row["__anomaly_score__"] = round(float(anomaly_scores.iloc[position]), 4)
                type_preview = action == "preview_type" or (action == "apply_type" and bool(error))
                if type_preview and type_column in active_df.columns:
                    proposed_df, type_invalid_count = convert_column_type(
                        active_df, type_column, type_target
                    )
                    type_source_dtype = str(active_df[type_column].dtype)
                    type_result_dtype = str(proposed_df[type_column].dtype)
                    for before, after in zip(
                        active_df[type_column].head(10).tolist(),
                        proposed_df[type_column].head(10).tolist(),
                    ):
                        before_is_missing = pd.isna(before)
                        after_is_missing = pd.isna(after)
                        type_preview_rows.append({
                            "before": "—" if before_is_missing else str(before),
                            "after": "—" if after_is_missing else str(after),
                            "invalid": bool(not before_is_missing and after_is_missing),
                        })
                elif action == "preview_type":
                    error = "Choose a column to preview a type conversion."
                category_preview = action == "preview_standardize" or (
                    action == "apply_standardize" and bool(error)
                )
                if category_preview:
                    try:
                        proposed_df, category_changed_count = standardize_category_values(
                            active_df, category_column, category_mode
                        )
                    except ValueError as exc:
                        error = str(exc)
                    else:
                        differences = (
                            active_df[category_column].astype("string")
                            != proposed_df[category_column].astype("string")
                        ).fillna(False)
                        before_values = active_df.loc[differences, category_column].head(10)
                        after_values = proposed_df.loc[differences, category_column].head(10)
                        category_preview_rows = [
                            {"before": str(before), "after": str(after)}
                            for before, after in zip(before_values.tolist(), after_values.tolist())
                        ]
                cleaned_preview_columns = active_df.columns.tolist()
                cleaned_preview_rows = active_df.loc[~active_df.duplicated(keep="first")].head(10).to_dict(orient="records")
                if action == "download":
                    output = BytesIO()
                    active_df.to_csv(output, index=False, encoding="utf-8-sig")
                    output.seek(0)
                    return send_file(output, mimetype="text/csv", as_attachment=True,
                                     download_name="datadoctor_cleaned.csv")
                if action == "download_report":
                    report_data = json.dumps(
                        report,
                        ensure_ascii=False,
                        indent=2,
                        default=lambda value: value.item() if hasattr(value, "item") else str(value),
                    ).encode("utf-8")
                    return send_file(
                        BytesIO(report_data),
                        mimetype="application/json",
                        as_attachment=True,
                        download_name="datadoctor_quality_report.json",
                    )
                if action == "download_script":
                    return send_file(
                        build_cleaning_script(operations),
                        mimetype="text/x-python",
                        as_attachment=True,
                        download_name="datadoctor_cleaning_script.py",
                    )
        except Exception as exc:
            error = f"Could not analyze that CSV: {exc}"

    elif session.get("dataset_id") in _active_datasets:
        state = _active_datasets[session["dataset_id"]]
        filename = state["filename"]
        active_df = state["current"]
        original_df = state["original"]
        type_columns = active_df.columns.tolist()
        category_columns = [
            column for column in active_df.columns
            if pd.api.types.is_object_dtype(active_df[column].dtype)
            or pd.api.types.is_string_dtype(active_df[column].dtype)
            or isinstance(active_df[column].dtype, pd.CategoricalDtype)
        ]
        duplicate_rows = int(active_df.duplicated().sum())
        outlier_rows_count = int(outlier_row_mask(active_df).sum())
        anomaly_cache = _anomaly_result(state, anomaly_contamination)
        if anomaly_cache:
            anomaly_count_available = not anomaly_cache["error"]
            anomaly_detection_error = anomaly_cache["error"]
            anomaly_rows_count = sum(anomaly_cache["mask"])
        can_undo = state["undo"] is not None
        report = analyze_dataset(active_df)
        activity = list(reversed(state.get("activity", [])[-6:]))
        is_modified = not active_df.equals(original_df)
        quality_distribution = [
            {"label": "Complete cells", "value": max(0, active_df.size - missing_cells), "color": "#2dd4bf"},
            {"label": "Missing cells", "value": missing_cells, "color": "#f59e0b"},
        ]
        numeric_summary_rows = [
            {"column": str(column), "mean": float(active_df[column].mean()), "median": float(active_df[column].median())}
            for column in active_df.select_dtypes(include="number").columns[:6]
            if active_df[column].notna().any()
        ]
        column_profiles = [
            {"name": str(column), "dtype": str(active_df[column].dtype),
             "missing": int(active_df[column].isna().sum()),
             "unique": int(active_df[column].nunique(dropna=True))}
            for column in active_df.columns
        ]
        preview_columns = active_df.columns.tolist()
        preview_rows = active_df.head(10).to_dict(orient="records")
        duplicate_preview = active_df.loc[active_df.duplicated(keep="first")]
        duplicate_preview_columns = duplicate_preview.columns.tolist()
        duplicate_preview_rows = duplicate_preview.head(10).to_dict(orient="records")
        missing_cells = int(active_df.isna().sum().sum())
        missing_cells_after = missing_cells

    return render_template(
        "index.html",
        report=report,
        error=error,
        filename=filename,
        preview_columns=preview_columns,
        preview_rows=preview_rows,
        cleaning_preview=cleaning_preview,
        rows_before=rows_before,
        rows_after=rows_after,
        cleaned_preview_columns=cleaned_preview_columns,
        cleaned_preview_rows=cleaned_preview_rows,
        missing_before=missing_before,
        missing_after=missing_after,
        duplicate_rows=duplicate_rows,
        duplicate_preview_columns=duplicate_preview_columns,
        duplicate_preview_rows=duplicate_preview_rows,
        can_undo=can_undo,
        active_rows=len(active_df) if active_df is not None else 0,
        original_rows=len(original_df) if original_df is not None else 0,
        missing_cells=missing_cells,
        missing_preview=missing_preview,
        missing_preview_columns=missing_preview_columns,
        missing_preview_rows=missing_preview_rows,
        missing_cells_after=missing_cells_after,
        numeric_strategy=numeric_strategy,
        outlier_rows_count=outlier_rows_count,
        outlier_preview=outlier_preview,
        outlier_preview_columns=outlier_preview_columns,
        outlier_preview_rows=outlier_preview_rows,
        type_columns=type_columns,
        type_column=type_column,
        type_target=type_target,
        type_preview=type_preview,
        type_preview_rows=type_preview_rows,
        type_source_dtype=type_source_dtype,
        type_result_dtype=type_result_dtype,
        type_invalid_count=type_invalid_count,
        category_columns=category_columns,
        category_column=category_column,
        category_mode=category_mode,
        category_preview=category_preview,
        category_preview_rows=category_preview_rows,
        category_changed_count=category_changed_count,
        anomaly_contamination=anomaly_contamination,
        anomaly_rows_count=anomaly_rows_count,
        anomaly_preview=anomaly_preview,
        anomaly_preview_columns=anomaly_preview_columns,
        anomaly_preview_rows=anomaly_preview_rows,
        anomaly_detection_error=anomaly_detection_error,
        notice=notice,
        anomaly_count_available=anomaly_count_available,
        quality_distribution=quality_distribution,
        numeric_summary_rows=numeric_summary_rows,
        column_profiles=column_profiles,
        activity=activity,
        is_modified=is_modified,
    )


if __name__ == "__main__":
    app.run(debug=False)

