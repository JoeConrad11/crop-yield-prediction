"""Shared model definitions and evaluation helpers, used by both
train_models.py and the exploration notebook."""
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import mean_absolute_error, r2_score

from config import crop_checkpoints

ID_COLS = ["year", "state_fips", "state_alpha", "county_fips", "county_name"]
TARGET = "yield_bu_acre"

MODELS = {
    "LinearRegression": lambda: make_pipeline(StandardScaler(), LinearRegression()),
    "RandomForest": lambda: RandomForestRegressor(n_estimators=300, random_state=42),
    "GradientBoosting": lambda: GradientBoostingRegressor(n_estimators=300, max_depth=3, random_state=42),
    "MLP (small NN)": lambda: make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=3000, early_stopping=True,
                      random_state=42, alpha=0.01),
    ),
}


def load_checkpoint_table(checkpoint_name: str, crop: str = "corn") -> pd.DataFrame:
    return pd.read_csv(f"data/processed/model_table_{crop}_{checkpoint_name}.csv")


def numeric_feature_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in ID_COLS + [TARGET]]


def prep_features(df: pd.DataFrame) -> tuple:
    """One-hot encode state, return (df, feature_columns)."""
    numeric = numeric_feature_cols(df)
    df = df.dropna(subset=numeric + [TARGET]).copy()
    df = pd.get_dummies(df, columns=["state_alpha"], prefix="state")
    state_cols = [c for c in df.columns if c.startswith("state_")]
    return df, numeric + state_cols


def leave_one_year_out_eval(df: pd.DataFrame, features: list, model_factory) -> pd.DataFrame:
    results = []
    for test_year in sorted(df["year"].unique()):
        train = df[df["year"] != test_year]
        test = df[df["year"] == test_year]
        model = model_factory()
        model.fit(train[features], train[TARGET])
        preds = model.predict(test[features])
        mae = mean_absolute_error(test[TARGET], preds)
        r2 = r2_score(test[TARGET], preds)
        results.append({"held_out_year": test_year, "mae": mae, "r2": r2, "n_test": len(test)})
    return pd.DataFrame(results)


def run_all_checkpoints(crop: str = "corn") -> pd.DataFrame:
    """Full model x checkpoint comparison grid, used by train_models.py and the notebook."""
    summary_rows = []
    for checkpoint_name in crop_checkpoints(crop):
        raw = load_checkpoint_table(checkpoint_name, crop)
        df, features = prep_features(raw)
        for model_name, factory in MODELS.items():
            results = leave_one_year_out_eval(df, features, factory)
            summary_rows.append({
                "crop": crop,
                "checkpoint": checkpoint_name,
                "model": model_name,
                "mean_mae": results["mae"].mean(),
                "median_r2": results["r2"].median(),
            })
    return pd.DataFrame(summary_rows)
