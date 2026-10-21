
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

    # 7. Suggested actions
    suggestions = []

    if duplicate_count > 0:
        suggestions.append(
            f"Review the {duplicate_count} duplicate row(s)."
        )

    for col in df.columns:
        missing_count = int(missing[col])
        if missing_count > 0:
            suggestions.append(
                f"Review the {missing_count} missing value(s) in '{col}'."
            )

    for col, count in outliers.items():
        suggestions.append(
            f"Review the {count} potential outlier(s) in '{col}'."
        )

    # 8. Build the report
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
        "suggestions": suggestions,
    }

    return report

def clean_dataset(
    df,
    remove_duplicates=False,
    drop_missing=False,
    fill_numeric_missing=False,
    fill_text_missing=False,
):
    """Return a cleaned copy of a DataFrame."""
    cleaned_df = df.copy()

    if remove_duplicates:
        cleaned_df = cleaned_df.drop_duplicates()

    if fill_numeric_missing:
        numeric_columns = cleaned_df.select_dtypes(include=np.number).columns

        for column in numeric_columns:
            median_value = cleaned_df[column].median()
            if pd.notna(median_value):
                cleaned_df[column] = cleaned_df[column].fillna(median_value)

    if fill_text_missing:
        text_columns = cleaned_df.select_dtypes(exclude=np.number).columns

        for column in text_columns:
            most_common = cleaned_df[column].mode(dropna=True)
            if not most_common.empty:
                cleaned_df[column] = cleaned_df[column].fillna(
                    most_common.iloc[0]
                )

    if drop_missing:
        cleaned_df = cleaned_df.dropna()

    return cleaned_df

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
