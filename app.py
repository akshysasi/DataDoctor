from io import BytesIO
from secrets import token_hex

from flask import Flask, render_template, request, send_file, session
import pandas as pd

from analyzer import analyze_dataset

from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
app.secret_key = token_hex(32)
_active_datasets = {}

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


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

    if request.method == "POST":
        uploaded_file = request.files.get("file")
        action = request.form.get("action", "analyze")

        try:
            if uploaded_file is not None and uploaded_file.filename and action == "analyze":
                if not uploaded_file.filename.lower().endswith(".csv"):
                    raise ValueError("Please choose a file with a .csv extension.")
                filename = uploaded_file.filename
                df = pd.read_csv(uploaded_file)
                dataset_id = session.get("dataset_id") or token_hex(16)
                session["dataset_id"] = dataset_id
                _active_datasets[dataset_id] = {
                    "original": df.copy(), "current": df.copy(),
                    "undo": None, "filename": filename,
                }
            dataset_id = session.get("dataset_id")
            state = _active_datasets.get(dataset_id)
            if state is None:
                if not error:
                    error = "Upload and analyze a CSV before using the Cleaning Studio."
            else:
                filename = state["filename"]
                if action == "apply_duplicates":
                    state["undo"] = state["current"].copy()
                    state["current"] = state["current"].drop_duplicates().reset_index(drop=True)
                elif action == "undo_duplicates" and state["undo"] is not None:
                    state["current"] = state["undo"]
                    state["undo"] = None
                elif action == "reset_dataset":
                    state["current"] = state["original"].copy()
                    state["undo"] = None

                active_df = state["current"]
                original_df = state["original"]
                duplicate_rows = int(active_df.duplicated().sum())
                can_undo = state["undo"] is not None
                report = analyze_dataset(active_df)
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
                cleaned_preview_columns = active_df.columns.tolist()
                cleaned_preview_rows = active_df.loc[~active_df.duplicated(keep="first")].head(10).to_dict(orient="records")
                if action == "download":
                    output = BytesIO()
                    active_df.to_csv(output, index=False, encoding="utf-8-sig")
                    output.seek(0)
                    return send_file(output, mimetype="text/csv", as_attachment=True,
                                     download_name="datadoctor_cleaned.csv")
        except Exception as exc:
            error = f"Could not analyze that CSV: {exc}"

    elif session.get("dataset_id") in _active_datasets:
        state = _active_datasets[session["dataset_id"]]
        filename = state["filename"]
        active_df = state["current"]
        original_df = state["original"]
        duplicate_rows = int(active_df.duplicated().sum())
        can_undo = state["undo"] is not None
        report = analyze_dataset(active_df)
        preview_columns = active_df.columns.tolist()
        preview_rows = active_df.head(10).to_dict(orient="records")
        duplicate_preview = active_df.loc[active_df.duplicated(keep="first")]
        duplicate_preview_columns = duplicate_preview.columns.tolist()
        duplicate_preview_rows = duplicate_preview.head(10).to_dict(orient="records")

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
    )


if __name__ == "__main__":
    app.run(debug=True)

