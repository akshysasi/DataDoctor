from flask import Flask, render_template, request
import pandas as pd
from analyzer import analyze_dataset

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    report = None
    error = None
    preview_columns = []
    preview_rows = []

    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if uploaded_file is None or uploaded_file.filename == "":
            error = "Choose a CSV file first."
        else:
            try:
                df = pd.read_csv(uploaded_file)
                report = analyze_dataset(df)
                preview_columns = df.columns.tolist()
                preview_rows = df.head(10).to_dict(orient="records")
            except Exception as exc:
                error = f"Could not analyze that CSV: {exc}"

    return render_template(
    "index.html",
    report=report,
    error=error,
    preview_columns=preview_columns,
    preview_rows=preview_rows,
)


if __name__ == "__main__":
    app.run(debug=True)