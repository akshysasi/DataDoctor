# DataDoctor

**A local-first CSV quality workspace for exploring, cleaning, and exporting trustworthy datasets.**

DataDoctor helps analysts and developers find common data-quality problems before they move a CSV into a report, model, or production workflow. It pairs an explainable health score with reviewable cleaning actions and keeps the uploaded source file unchanged.

## Problem

CSV files often contain missing values, repeated records, inconsistent categories, invalid types, and unusual numeric rows. Finding these issues manually is slow, and cleaning without a preview can silently damage useful data. DataDoctor brings those checks and reversible actions into one lightweight local application.

## Features

- Upload and analyze CSV files up to 16 MB.
- Calculate a 0–100 health score from available completeness, duplicate, IQR outlier, and constant-column checks.
- Review dataset dimensions, column types, missing values, duplicates, outliers, summary statistics, correlations, and suggested checks.
- Search and paginate through active data, inspect per-column types and missing counts, and see missing cells highlighted.
- Preview and apply duplicate removal, missing-value filling, IQR outlier removal, and Isolation Forest anomaly removal.
- Safely convert columns to numbers, dates, or text, and standardize category values.
- Undo the latest cleaning action or reset the active dataset to its uploaded state.
- Export the active CSV, a detailed JSON quality report, or a reproducible Python cleaning script.
- Review cleaning activity for the current session.

The active copy and history are held in memory by the Flask process. The original upload is never overwritten; restarting the app clears active sessions.

## Screenshots

The dashboard includes an overview, data explorer, quality report, Cleaning Studio, and Export Center. Add current application screenshots here when preparing a public release.

## Technology

- Python 3.13
- Flask
- pandas and NumPy
- scikit-learn (Isolation Forest)
- HTML, CSS, and JavaScript
- Plotly.js for interactive quality charts

## Architecture

```text
Browser
  └── Flask routes (app.py)
       ├── In-memory active dataset and operation history
       ├── JSON explorer endpoint (/api/explorer)
       └── Analysis and cleaning helpers (analyzer.py)
            └── pandas / NumPy / scikit-learn

templates/index.html  Dashboard and Cleaning Studio
static/css/           Responsive visual system
static/js/            Search, pagination, confirmations, and activity view
tests/                Analyzer and Flask workflow tests
```

The dashboard and all metrics use the active uploaded dataset. Isolation Forest runs only when an anomaly preview or removal is requested; until then, its dashboard count is shown as unavailable.

## Install on Windows

Open PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run locally

```powershell
.\.venv\Scripts\python.exe app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), upload a `.csv` file, and select **Analyze dataset**.

## Example workflow

1. Upload a CSV and review its health score, quality findings, and summary.
2. Search and page through the active dataset in Data Explorer.
3. Preview a Cleaning Studio operation, then apply it if the affected rows or values look right.
4. Use Undo or Reset if you want to reverse changes.
5. Export the cleaned CSV, JSON quality report, or replayable Python script.

The generated script accepts a source path and output path:

```powershell
python datadoctor_cleaning_script.py input.csv cleaned.csv
```

Install the requirements in the Python environment used to run the generated script.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project structure

```text
DataDoctor/
├── analyzer.py
├── app.py
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── portfolio.css
│   └── js/
│       └── portfolio.js
└── tests/
```

## Future improvements

- Add automated accessibility checks and keyboard-driven table navigation.
- Offer configurable upload limits and background analysis for larger datasets.
- Add persistent project storage and multi-dataset session management.
- Capture and publish application screenshots and a short workflow demo.
- Add deployment configuration after choosing a hosting environment and data-handling policy.

## License

DataDoctor is released under the MIT License. See [LICENSE](LICENSE).
