from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE_DIR = Path(__file__).parent
HISTORICAL_PATH = BASE_DIR / "data" / "ernow_historical.csv"
TEMPLATE_PATH = BASE_DIR / "data" / "ernow_historical_template.csv"
TARGET = "observed_wait_min"
TIME_COL = "timestamp"
MIN_ROWS = 60

REQUIRED_COLUMNS = [
    "timestamp",
    "hospital",
    "observed_wait_min",
]

OPTIONAL_NUMERIC_FEATURES = [
    "typical_ed_minutes",
    "recent_ed_visits",
    "recent_occupancy_pct",
    "left_before_seen_pct",
    "temperature_c",
    "wind_kmh",
    "severe_weather",
    "major_event",
    "holiday",
]

CATEGORICAL_FEATURES = ["hospital", "ari_level"]


def load_historical_data(path: Path = HISTORICAL_PATH) -> Tuple[pd.DataFrame, List[str]]:
    if not path.exists():
        return pd.DataFrame(), [f"Missing {path.name}"]

    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return df, ["Missing required columns: " + ", ".join(missing)]

    df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce", utc=True)
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    df = df.dropna(subset=[TIME_COL, TARGET, "hospital"]).copy()
    df = df.sort_values(TIME_COL).reset_index(drop=True)

    warnings = []
    if len(df) < MIN_ROWS:
        warnings.append(f"Need at least {MIN_ROWS} labeled rows; found {len(df)}.")
    if df[TIME_COL].nunique() < 10:
        warnings.append("Need observations across more timestamps for a meaningful time-based test split.")
    if df["hospital"].nunique() < 2:
        warnings.append("Need data from at least two hospitals.")

    return df, warnings


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out[TIME_COL], errors="coerce", utc=True)
    out["hour"] = ts.dt.hour
    out["day_of_week"] = ts.dt.dayofweek
    out["month"] = ts.dt.month
    out["weekend"] = (ts.dt.dayofweek >= 5).astype(int)

    for col in OPTIONAL_NUMERIC_FEATURES:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if "ari_level" not in out.columns:
        out["ari_level"] = "Unavailable"
    out["ari_level"] = out["ari_level"].fillna("Unavailable").astype(str)
    out["hospital"] = out["hospital"].astype(str)
    return out


def _feature_columns(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    numeric = [
        "hour",
        "day_of_week",
        "month",
        "weekend",
        *OPTIONAL_NUMERIC_FEATURES,
    ]
    numeric = [c for c in numeric if c in df.columns and df[c].notna().any()]
    categorical = [c for c in CATEGORICAL_FEATURES if c in df.columns and df[c].notna().any()]
    return numeric, categorical


def time_based_split(df: pd.DataFrame, test_fraction: float = 0.20) -> Tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values(TIME_COL).reset_index(drop=True)
    split_idx = max(1, min(len(ordered) - 1, int(len(ordered) * (1 - test_fraction))))
    return ordered.iloc[:split_idx].copy(), ordered.iloc[split_idx:].copy()


def _preprocessor(numeric: List[str], categorical: List[str], scale_numeric: bool) -> ColumnTransformer:
    numeric_steps = [("impute", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scale", StandardScaler()))

    numeric_pipe = Pipeline(numeric_steps)
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer([
        ("num", numeric_pipe, numeric),
        ("cat", categorical_pipe, categorical),
    ])


def _metrics(y_true, y_pred) -> Dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "R2": float(r2_score(y_true, y_pred)) if len(y_true) >= 2 else float("nan"),
    }


def train_and_compare(df: pd.DataFrame) -> Dict:
    prepared = engineer_features(df)
    numeric, categorical = _feature_columns(prepared)
    train_df, test_df = time_based_split(prepared)

    feature_cols = numeric + categorical
    X_train = train_df[feature_cols]
    y_train = train_df[TARGET]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET]

    models = {
        "Median baseline": Pipeline([
            ("prep", _preprocessor(numeric, categorical, scale_numeric=False)),
            ("model", DummyRegressor(strategy="median")),
        ]),
        "Linear regression": Pipeline([
            ("prep", _preprocessor(numeric, categorical, scale_numeric=True)),
            ("model", LinearRegression()),
        ]),
        "Ridge regression": Pipeline([
            ("prep", _preprocessor(numeric, categorical, scale_numeric=True)),
            ("model", Ridge(alpha=1.0)),
        ]),
        "Random forest": Pipeline([
            ("prep", _preprocessor(numeric, categorical, scale_numeric=False)),
            ("model", RandomForestRegressor(
                n_estimators=300,
                max_depth=8,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1,
            )),
        ]),
    }

    fitted = {}
    metric_rows = []
    for name, pipeline in models.items():
        pipeline.fit(X_train, y_train)
        preds = pipeline.predict(X_test)
        metric_rows.append({"Model": name, **_metrics(y_test, preds)})
        fitted[name] = pipeline

    metrics = pd.DataFrame(metric_rows).sort_values(["MAE", "RMSE"]).reset_index(drop=True)
    best_name = metrics.iloc[0]["Model"]
    best_model = fitted[best_name]
    non_baseline = metrics[metrics["Model"] != "Median baseline"]
    interpret_name = non_baseline.iloc[0]["Model"] if not non_baseline.empty else best_name
    interpret_model = fitted[interpret_name]

    return {
        "metrics": metrics,
        "best_model_name": best_name,
        "best_model": best_model,
        "interpret_model_name": interpret_name,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "train_start": train_df[TIME_COL].min(),
        "train_end": train_df[TIME_COL].max(),
        "test_start": test_df[TIME_COL].min(),
        "test_end": test_df[TIME_COL].max(),
        "numeric_features": numeric,
        "categorical_features": categorical,
        "feature_importance": feature_importance(interpret_model),
    }


def feature_importance(pipeline: Pipeline, top_n: int = 12) -> pd.DataFrame:
    prep = pipeline.named_steps["prep"]
    model = pipeline.named_steps["model"]
    try:
        names = prep.get_feature_names_out()
    except Exception:
        return pd.DataFrame(columns=["Feature", "Importance"])

    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        values = np.abs(np.asarray(model.coef_, dtype=float).ravel())
    else:
        return pd.DataFrame(columns=["Feature", "Importance"])

    if len(names) != len(values):
        return pd.DataFrame(columns=["Feature", "Importance"])

    cleaned = [str(n).replace("num__", "").replace("cat__", "") for n in names]
    out = pd.DataFrame({"Feature": cleaned, "Importance": values})
    return out.sort_values("Importance", ascending=False).head(top_n).reset_index(drop=True)


def training_status(path: Path = HISTORICAL_PATH) -> Dict:
    df, warnings = load_historical_data(path)
    ready = not warnings and len(df) >= MIN_ROWS
    return {
        "ready": ready,
        "rows": len(df),
        "warnings": warnings,
        "path": str(path),
        "data": df,
    }
