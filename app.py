from io import BytesIO

from flask import Flask, render_template, request, send_file
import pandas as pd

from analyzer import analyze_dataset, clean_dataset

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    report = None
    error = None
    preview_columns = []
    preview_rows = []
    cleaning_preview = False
    rows_before = 0
    rows_after = 0
    missing_before = 0
    missing_after = 0
    cleaned_preview_columns = []
    cleaned_preview_rows = []

    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if uploaded_file is None or uploaded_file.filename == "":
            error = "Choose a CSV file first."
        else:
            try:
                df = pd.read_csv(uploaded_file)

                remove_duplicates = (
                    request.form.get("remove_duplicates") == "yes"
                )
                drop_missing = request.form.get("drop_missing") == "yes"
                fill_numeric_missing = (
                    request.form.get("fill_numeric_missing") == "yes"
                )
                fill_text_missing = (
                    request.form.get("fill_text_missing") == "yes"
                )

                cleaned_df = clean_dataset(
                    df,
                    remove_duplicates=remove_duplicates,
                    drop_missing=drop_missing,
                    fill_numeric_missing=fill_numeric_missing,
                    fill_text_missing=fill_text_missing,
                )

                if request.form.get("action") == "download":
                    output = BytesIO()
                    cleaned_df.to_csv(
                        output,
                        index=False,
                        encoding="utf-8-sig",
                    )
                    output.seek(0)

                    return send_file(
                        output,
                        mimetype="text/csv",
                        as_attachment=True,
                        download_name="datadoctor_cleaned.csv",
                    )

                report = analyze_dataset(df)
                preview_columns = df.columns.tolist()
                preview_rows = df.head(10).to_dict(orient="records")

                if request.form.get("action") == "preview":
                    cleaning_preview = True
                    rows_before = len(df)
                    rows_after = len(cleaned_df)
                    missing_before = int(df.isna().sum().sum())
                    missing_after = int(cleaned_df.isna().sum().sum())
                    cleaned_preview_columns = cleaned_df.columns.tolist()
                    cleaned_preview_rows = cleaned_df.head(10).to_dict(
                        orient="records"
                    )

            except Exception as exc:
                error = f"Could not analyze that CSV: {exc}"

    return render_template(
        "index.html",
        report=report,
        error=error,
        preview_columns=preview_columns,
        preview_rows=preview_rows,
        cleaning_preview=cleaning_preview,
        rows_before=rows_before,
        rows_after=rows_after,
        cleaned_preview_columns=cleaned_preview_columns,
        cleaned_preview_rows=cleaned_preview_rows,
        missing_before=missing_before,
        missing_after=missing_after,
    )


if __name__ == "__main__":
    app.run(debug=True)