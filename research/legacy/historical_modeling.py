from functools import lru_cache
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
PROMOTION_MARGIN = 0.02


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
    return (
        df[df["timestamp"].isin(train_periods)].copy(),
        df[df["timestamp"].isin(test_periods)].copy(),
    )


def metrics(y, pred):
    return {
        "MAE": float(mean_absolute_error(y, pred)),
        "RMSE": float(mean_squared_error(y, pred) ** 0.5),
        "R2": float(r2_score(y, pred)) if len(y) > 1 else np.nan,
    }


def _preprocessor(numeric, categorical):
    num_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", num_pipe, numeric),
        ("cat", cat_pipe, categorical),
    ])


def train_historical_models():
    """Cached: retrains only when the history CSV changes, not on every page load."""
    mtime = HISTORY_PATH.stat().st_mtime if HISTORY_PATH.exists() else 0.0
    return _train_historical_models_cached(mtime)


@lru_cache(maxsize=2)
def _train_historical_models_cached(_history_mtime):
    status = history_status()
    if not status["ready"]:
        return None

    df = engineer(status["data"])
    train, test = chronological_split(df)

    numeric = ["year", "month", "quarter", "lag_1", "lag_2", "rolling_3"]
    categorical = ["hospital"]
    features = numeric + categorical

    X_train = train[features]
    y_train = train["observed_wait_min"]
    X_test = test[features]
    y_test = test["observed_wait_min"]

    predictions = {}
    rows = []

    persistence = test["lag_1"].to_numpy()
    predictions["Persistence baseline"] = persistence
    rows.append({"Model": "Persistence baseline", **metrics(y_test, persistence)})

    models = {
        "Ridge regression": Pipeline([
            ("prep", _preprocessor(numeric, categorical)),
            ("model", Ridge(alpha=1.0)),
        ]),
        "Random forest": Pipeline([
            ("prep", _preprocessor(numeric, categorical)),
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
        predictions[name] = pred
        rows.append({"Model": name, **metrics(y_test, pred)})
        fitted[name] = model

    metric_df = pd.DataFrame(rows).sort_values(["MAE", "RMSE"]).reset_index(drop=True)

    baseline_mae = float(metric_df.loc[metric_df["Model"] == "Persistence baseline", "MAE"].iloc[0])
    learned = metric_df[metric_df["Model"] != "Persistence baseline"].sort_values(["MAE", "RMSE"])
    best_ml_name = learned.iloc[0]["Model"]
    best_ml_mae = float(learned.iloc[0]["MAE"])

    learned_model_promoted = best_ml_mae < baseline_mae * (1 - PROMOTION_MARGIN)
    selected_model = best_ml_name if learned_model_promoted else "Persistence baseline"

    selected_pred = predictions[selected_model]
    error_frame = test[["timestamp", "hospital", "observed_wait_min"]].copy()
    error_frame["prediction"] = selected_pred
    error_frame["abs_error"] = (error_frame["observed_wait_min"] - error_frame["prediction"]).abs()

    hospital_error = (
        error_frame.groupby("hospital", as_index=False)
        .agg(MAE=("abs_error", "mean"), Observations=("abs_error", "size"))
        .sort_values("MAE")
    )

    return {
        "metrics": metric_df,
        "selected_model": selected_model,
        "best_model": metric_df.iloc[0]["Model"],
        "best_ml_model": best_ml_name,
        "learned_model_promoted": learned_model_promoted,
        "promotion_margin": PROMOTION_MARGIN,
        "baseline_mae": baseline_mae,
        "best_ml_mae": best_ml_mae,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_start": train["timestamp"].min(),
        "train_end": train["timestamp"].max(),
        "test_start": test["timestamp"].min(),
        "test_end": test["timestamp"].max(),
        "hospital_error": hospital_error,
        "error_frame": error_frame,
        "fitted_models": fitted,
        "numeric_features": numeric,
        "categorical_features": categorical,
    }


def current_throughput_forecast():
    status = history_status()
    result = train_historical_models()
    if not status["ready"] or result is None:
        return {
            "ready": False,
            "selected_model": None,
            "learned_model_promoted": False,
            "predictions": {},
        }

    history = status["data"].sort_values(["hospital", "timestamp"]).copy()
    # Step forward by the typical gap between reporting periods (about a year in this data),
    # not a fixed quarter, so the calendar features match how the data actually arrives.
    periods = pd.Series(sorted(history["timestamp"].dropna().unique()))
    gap = periods.diff().dropna().median() if len(periods) > 1 else pd.Timedelta(days=365)
    next_time = history["timestamp"].max() + gap
    rows = []

    for hospital, group in history.groupby("hospital"):
        values = group.sort_values("timestamp")["observed_wait_min"].astype(float).tolist()
        if not values:
            continue
        rows.append({
            "hospital": hospital,
            "year": next_time.year,
            "month": next_time.month,
            "quarter": next_time.quarter,
            "lag_1": values[-1],
            "lag_2": values[-2] if len(values) >= 2 else values[-1],
            "rolling_3": float(np.mean(values[-3:])),
            "last_observed_throughput_min": values[-1],
        })

    future = pd.DataFrame(rows)
    selected = result["selected_model"]

    if selected == "Persistence baseline":
        future["predicted_throughput_min"] = future["lag_1"]
    else:
        features = result["numeric_features"] + result["categorical_features"]
        future["predicted_throughput_min"] = result["fitted_models"][selected].predict(future[features])

    med = float(future["predicted_throughput_min"].median()) if not future.empty else 1.0
    med = med or 1.0
    future["relative_throughput_pressure"] = future["predicted_throughput_min"] / med

    return {
        "ready": True,
        "selected_model": selected,
        "best_ml_model": result["best_ml_model"],
        "learned_model_promoted": result["learned_model_promoted"],
        "baseline_mae": result["baseline_mae"],
        "best_ml_mae": result["best_ml_mae"],
        "predictions": future.set_index("hospital").to_dict("index"),
    }
