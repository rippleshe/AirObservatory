from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .features import PCA_FEATURES


@dataclass(frozen=True)
class PCAArtifact:
    features: tuple[str, ...]
    input_rows: int
    sample_count: int
    dropped_rows: int
    missing_fraction: float
    explained_variance: list[dict]
    loadings: list[dict]
    scores: list[dict]
    correlation: list[dict]


def fit_city_pca(frame: pd.DataFrame, max_components: int = 5) -> PCAArtifact:
    if frame.empty:
        raise ValueError("No aligned pollution/weather rows are available")

    values = frame[list(PCA_FEATURES)].apply(pd.to_numeric, errors="coerce")
    input_rows = len(values)
    missing_cells = int(values.isna().sum().sum())
    missing_fraction = missing_cells / max(1, values.size)
    usable = values.dropna(axis=0, how="any")
    if len(usable) < 168:
        raise ValueError(
            f"Only {len(usable)} complete hourly rows are available; "
            "at least 168 are required"
        )

    scaler = StandardScaler()
    standardized = scaler.fit_transform(usable)
    component_count = min(max_components, len(PCA_FEATURES), len(usable))
    model = PCA(n_components=component_count)
    scores = model.fit_transform(standardized)

    cumulative = np.cumsum(model.explained_variance_ratio_)
    explained = [
        {
            "component": f"PC{index + 1}",
            "variance_ratio": float(ratio),
            "cumulative_ratio": float(cumulative[index]),
        }
        for index, ratio in enumerate(model.explained_variance_ratio_)
    ]

    loadings = []
    for feature_index, feature in enumerate(PCA_FEATURES):
        row = {"feature": feature}
        for component_index in range(component_count):
            row[f"PC{component_index + 1}"] = float(
                model.components_[component_index, feature_index]
            )
        loadings.append(row)

    usable_times = frame.loc[usable.index, "time"].tolist()
    score_rows = []
    for row_index, value in enumerate(scores):
        row = {"time": usable_times[row_index]}
        for component_index in range(component_count):
            row[f"PC{component_index + 1}"] = float(value[component_index])
        score_rows.append(row)

    correlation_matrix = usable.corr()
    correlation = [
        {
            "feature": feature,
            "values": {
                other: float(correlation_matrix.loc[feature, other])
                for other in PCA_FEATURES
            },
        }
        for feature in PCA_FEATURES
    ]

    return PCAArtifact(
        features=PCA_FEATURES,
        input_rows=input_rows,
        sample_count=len(usable),
        dropped_rows=input_rows - len(usable),
        missing_fraction=missing_fraction,
        explained_variance=explained,
        loadings=loadings,
        scores=score_rows,
        correlation=correlation,
    )
