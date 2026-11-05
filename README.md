# DataDoctor

DataDoctor is a local CSV quality workspace built with Flask and pandas. It analyzes a dataset, explains common quality issues, and lets you review cleaning changes before exporting a cleaned copy.

## Features

### Dataset analysis

- Dataset dimensions, column types, and preview of the active data.
- Missing-value counts, exact duplicate rows, constant columns, and numeric outliers using the IQR rule.
- Dataset health score with a visible breakdown of the measured components.
- Summary statistics, numeric correlations, and suggested checks.

### Cleaning Studio

- Preview and remove exact duplicate rows.
- Fill numeric missing values with the mean or median and text/category gaps with the mode.
- Review and remove rows outside numeric IQR bounds.
- Run Isolation Forest anomaly detection across usable numeric columns, review flagged rows and scores, and remove flagged rows.
- Convert a selected column to number, date, or text. The app blocks conversions when non-empty values cannot be parsed.
- Standardize a selected text column by trimming spaces, lowercasing, or title-casing values.
- Undo the latest cleaning action or reset the active dataset to the upload.

### Export Center

- Download the active dataset as CSV.
- Download a detailed JSON quality report.
- Download a Python script that replays the cleaning actions applied during the session.

The uploaded source file is never overwritten. The active dataset and its operation history are held in memory by the running app and are cleared when the app restarts.

## Requirements

- Python 3.13
- Flask
- pandas
- NumPy
- scikit-learn

## Setup on Windows

Open PowerShell in the project folder and create the virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start DataDoctor:

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Use the app

1. Upload a `.csv` file and select **Analyze dataset**.
2. Review the health score, quality findings, and data preview.
3. In **Cleaning Studio**, preview an operation before applying it. Use **Undo last cleaning action** or **Reset to uploaded data** if needed.
4. In **Export Center**, download the active CSV, quality report, or cleaning script.

The cleaning script takes the original CSV path and a destination path:

```powershell
python datadoctor_cleaning_script.py input.csv cleaned.csv
```

Install the project requirements in the environment where you run the script so pandas, NumPy, and scikit-learn are available.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project layout

```text
DataDoctor/
├── analyzer.py        # Analysis and cleaning helpers
├── app.py             # Flask routes and active dataset workflow
├── requirements.txt   # Python dependencies
├── sample.csv         # Example CSV dataset
├── templates/
│   └── index.html     # Dashboard and Cleaning Studio
└── tests/             # Unit and route-level tests
```

## Notes

- Isolation Forest only uses numeric columns with varying values. Missing numeric inputs are filled with their median for the model; the original active dataset is unchanged during preview.
- The expected anomaly rate controls how many rows the model treats as unusual. An anomaly is a review signal, not proof that a row is incorrect.
- The app is designed for local development and does not require an external database.
