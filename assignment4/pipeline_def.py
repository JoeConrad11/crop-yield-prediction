"""Custom sklearn transformer for the county-yield-anomaly pipeline
(Assignment 4). Lives in its own file so both the build script and the
served pipeline's unpickling can import the exact same class.

The idea: two counties can have identical raw NDVI/weather/degree-day
values but very different yield potential (soil, management, climate
baseline) -- so what actually predicts a yield SWING is how far this year's
weather is from THAT county's own multi-year normal, not the raw value.
CountyAnomalyTransformer learns each county's per-feature mean at fit time
and expresses new rows as anomalies from it (plus a year-trend feature for
the slow genetics/practices-driven yield increase over time). This learned
state is exactly why the pipeline must be loaded from the fitted artifact,
not rebuilt from scratch at boot -- a freshly-constructed transformer has no
group means at all.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class CountyAnomalyTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, group_cols, value_cols, year_col="year", passthrough_cols=None):
        # __init__ only assigns -- no computation, no validation, so
        # sklearn's clone()/get_params()/set_params() machinery works.
        self.group_cols = group_cols
        self.value_cols = value_cols
        self.year_col = year_col
        self.passthrough_cols = passthrough_cols

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.group_means_ = X.groupby(list(self.group_cols))[list(self.value_cols)].mean()
        self.global_means_ = X[list(self.value_cols)].mean()
        self.min_year_ = int(X[self.year_col].min())
        return self

    def transform(self, X):
        X = pd.DataFrame(X)
        group_keys = list(X.set_index(list(self.group_cols)).index)
        looked_up = [
            self.group_means_.loc[key] if key in self.group_means_.index else self.global_means_
            for key in group_keys
        ]
        means_df = pd.DataFrame(looked_up, columns=list(self.value_cols), index=X.index)

        out = pd.DataFrame(index=X.index)
        for col in self.value_cols:
            out[f"anom_{col}"] = X[col].to_numpy() - means_df[col].to_numpy()
        out["year_trend"] = X[self.year_col].to_numpy() - self.min_year_
        for col in self.passthrough_cols or []:
            out[col] = X[col].to_numpy()
        return out.to_numpy(dtype=float)

    def get_feature_names_out(self, input_features=None):
        names = [f"anom_{c}" for c in self.value_cols] + ["year_trend"] + list(self.passthrough_cols or [])
        return np.array(names)

    def known_group(self, group_key) -> bool:
        """True if `group_key` (e.g. (state_fips, county_fips)) had its own
        fitted mean rather than falling back to the global mean."""
        return group_key in self.group_means_.index
