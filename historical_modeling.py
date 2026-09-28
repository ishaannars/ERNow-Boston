from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE = Path(__file__).parent
HISTORY_PATH = BASE / "data" / "cms_op18b_history.csv"

def history_status():
    if not HISTORY_PATH.exists():
        return {"ready": False, "reason": "Run cms_history_pipeline.py first.", "rows": 0}

    df = pd.read_csv(HISTORY_PATH)
    required = {"timestamp", "hospital", "observed_wait_min"}
    missing = required - set(df.columns)
    if missing:
        return {"ready": False, "reason": "Missing columns: " + ", ".join(sorted(missing)), "rows": len(df)}

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["observed_wait_min"] = pd.to_numeric(df["observed_wait_min"], errors="coerce")
    df = df.dropna(subset=["timestamp", "hospital", "observed_wait_min"]).copy()

    # Longitudinal OP-18b history is small by ML standards, so 36 is a practical floor.
    ready = len(df) >= 36 and df["timestamp"].nunique() >= 6 and df["hospital"].nunique() >= 3
    return {
        "ready": ready,
        "reason": None if ready else "Need at least 36 usable rows across 6+ reporting periods and 3+ hospitals.",
        "rows": len(df),
        "data": df,
    }

def engineer(df):
    out = df.sort_values(["hospital", "timestamp"]).copy()
    out["year"] = out["timestamp"].dt.year
    out["month"] = out["timestamp"].dt.month
    out["quarter"] = out["timestamp"].dt.quarter

    # Leakage-safe features: only prior outcomes are used.
    out["lag_1"] = out.groupby("hospital")["observed_wait_min"].shift(1)
    out["lag_2"] = out.groupby("hospital")["observed_wait_min"].shift(2)
    out["rolling_3"] = (
        out.groupby("hospital")["observed_wait_min"]
           .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    )
    return out.dropna(subset=["lag_1"]).copy()

def chronological_split(df, test_fraction=0.25):
    periods = sorted(df["timestamp"].dropna().unique())
    cut = max(1, int(len(periods) * (1 - test_fraction)))
    train_periods = set(periods[:cut])
    test_periods = set(periods[cut:])
    train = df[df["timestamp"].isin(train_periods)].copy()
    test = df[df["timestamp"].isin(test_periods)].copy()
    return train, test

def metrics(y, pred):
    return {
        "MAE": float(mean_absolute_error(y, pred)),
        "RMSE": float(mean_squared_error(y, pred) ** 0.5),
        "R2": float(r2_score(y, pred)) if len(y) > 1 else np.nan,
    }

def train_historical_models():
    status = history_status()
    if not status["ready"]:
        return None

    df = engineer(status["data"])
    train, test = chronological_split(df)

    numeric = ["year", "month", "quarter", "lag_1", "lag_2", "rolling_3"]
    categorical = ["hospital"]

    num_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    prep = ColumnTransformer([
        ("num", num_pipe, numeric),
        ("cat", cat_pipe, categorical),
    ])

    X_train = train[numeric + categorical]
    y_train = train["observed_wait_min"]
    X_test = test[numeric + categorical]
    y_test = test["observed_wait_min"]

    result_rows = []

    # Persistence is a meaningful time-series baseline.
    persistence = test["lag_1"].to_numpy()
    result_rows.append({"Model": "Persistence baseline", **metrics(y_test, persistence)})

    models = {
        "Ridge regression": Pipeline([
            ("prep", prep),
            ("model", Ridge(alpha=1.0)),
        ]),
        "Random forest": Pipeline([
            ("prep", prep),
            ("model", RandomForestRegressor(
                n_estimators=300,
                max_depth=7,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )),
        ]),
    }

    fitted = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        result_rows.append({"Model": name, **metrics(y_test, pred)})
        fitted[name] = model

    metric_df = pd.DataFrame(result_rows).sort_values(["MAE", "RMSE"]).reset_index(drop=True)

    by_hospital = []
    best_ml_name = metric_df[metric_df["Model"] != "Persistence baseline"].iloc[0]["Model"]
    best_ml = fitted[best_ml_name]
    best_pred = best_ml.predict(X_test)

    error_frame = test[["timestamp", "hospital", "observed_wait_min"]].copy()
    error_frame["prediction"] = best_pred
    error_frame["abs_error"] = (error_frame["observed_wait_min"] - error_frame["prediction"]).abs()

    hospital_error = (
        error_frame.groupby("hospital", as_index=False)
        .agg(
            MAE=("abs_error", "mean"),
            Observations=("abs_error", "size"),
        )
        .sort_values("MAE")
    )

    return {
        "metrics": metric_df,
        "best_model": metric_df.iloc[0]["Model"],
        "best_ml_model": best_ml_name,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_start": train["timestamp"].min(),
        "train_end": train["timestamp"].max(),
        "test_start": test["timestamp"].min(),
        "test_end": test["timestamp"].max(),
        "hospital_error": hospital_error,
        "error_frame": error_frame,
    }
