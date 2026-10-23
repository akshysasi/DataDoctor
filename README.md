# DataDoctor

DataDoctor is a Python and Flask app that checks CSV files for common data quality issues and lets you preview and download an optionally cleaned copy.

## Features

- Upload and preview a CSV file.
- See dataset size, data types, missing values, duplicates, constant columns, and potential numeric outliers.
- View summary statistics and correlations between numeric columns.
- Get suggestions about issues to review.
- Preview cleaning changes before downloading.
- Choose cleaning options for the downloaded copy:
  - Remove duplicate rows.
  - Fill missing numeric values with the column median.
  - Fill missing text values with the most common value in the column.
  - Drop rows that still contain missing values.

Cleaning options are optional. The uploaded file is not overwritten.

## Requirements

- Python 3.13
- Flask
- pandas
- NumPy

## Setup on Windows

Open a terminal in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install Flask pandas numpy