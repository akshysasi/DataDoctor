
import pandas as pd
import numpy as np


def analyze_dataset(df):
    """Analyze a DataFrame and return a dataset health report."""

    rows, columns = df.shape

    # 1. Missing values
    missing = df.isnull().sum()
    missing_percent = (missing / max(rows, 1) * 100).round(2)

    # 2. Duplicate records
    duplicate_count = int(df.duplicated().sum())

    # 3. Data types
    data_types = df.dtypes.astype(str)

    # 4. Constant columns
    constant_columns = [
        col for col in df.columns
        if df[col].nunique(dropna=False) <= 1
    ]

    # 5. Potential numerical outliers using the IQR rule
    outliers = {}

    numeric_columns = df.select_dtypes(include=np.number).columns

    for col in numeric_columns:
        series = df[col].dropna()

        if len(series) < 4:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        if iqr == 0:
            continue

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        count = int(
            ((series < lower_bound) | (series > upper_bound)).sum()
        )

        if count > 0:
            outliers[col] = count

    
    # 6. Statistical summary and numeric correlations

    summary = df.describe(include="all").fillna("").to_dict()

    numeric_data = df.select_dtypes(include=np.number)
    correlations = numeric_data.corr().round(2).fillna("")

    # 7. Build the report
    report = {
        "rows": rows,
        "columns": columns,
        "missing_values": {
            col: {
                "count": int(missing[col]),
                "percentage": float(missing_percent[col]),
            }
            for col in df.columns
        },
        "duplicate_rows": duplicate_count,
        "data_types": data_types.to_dict(),
        "constant_columns": constant_columns,
        "potential_outliers": outliers,
        "summary": summary,
        "correlations": correlations.to_dict(),
    }

    return report


if __name__ == "__main__":
    # Temporary test dataset
    sample_data = {
        "Name": ["Alex", "Sam", "Alex", "Riya", "Sam"],
        "Age": [21, 22, np.nan, 250, 22],
        "Score": [80, 90, 80, 85, 90],
        "Department": ["AI", "DS", "AI", "AI", "DS"],
    }

    df = pd.DataFrame(sample_data)
    report = analyze_dataset(df)

    print("\n===== DATADOCTOR HEALTH REPORT =====")
    print(f"Rows: {report['rows']}")
    print(f"Columns: {report['columns']}")
    print(f"Duplicate rows: {report['duplicate_rows']}")

    print("\nMissing values:")
    for col, details in report["missing_values"].items():
        print(
            f"  {col}: {details['count']} missing "
            f"({details['percentage']}%)"
        )

    print("\nConstant columns:")
    print(report["constant_columns"])

    print("\nPotential outliers:")
    print(report["potential_outliers"])

    print("\nData types:")
    print(report["data_types"])

    print("\nStatistical summary:")
    print(df.describe(include="all"))
