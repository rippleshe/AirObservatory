from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from backend.city_catalog import region_for
from backend.repository import active_location_rows

from .features import PCA_FEATURES, load_city_feature_frame

REPRESENTATIVE_RULE = (
    "One city per province: among the cities that clear the >=168 complete-hour guard "
    "in the common window, the province's highest window-mean PM2.5 (pm25_mean) is the "
    "province representative; ties fall to the lower location_id. Selection happens "
    "after the summary features and before PCA/KMeans, so every statistic below "
    "describes the provincial representatives only."
)

FINGERPRINT_FEATURES = (
    "pm25_mean",
    "pm25_p90",
    "pm25_std",
    "pm10_mean",
    "pm10_p90",
    "no2_mean",
    "no2_p90",
    "o3_mean",
    "o3_p90",
    "o3_std",
    "so2_mean",
    "co_mean",
    "temperature_mean",
    "humidity_mean",
    "wind_speed_mean",
    "boundary_layer_height_mean",
    "precipitation_hour_fraction",
    "pm25_diurnal_amplitude",
    "corr_pm25_wind",
    "corr_pm25_boundary_layer",
    "corr_o3_temperature",
)


@dataclass(frozen=True)
class CityFingerprintArtifact:
    features: tuple[str, ...]
    window_start: str
    window_end: str
    city_count: int
    eligible_city_count: int
    representative_rule: str
    sample_hours_min: int
    sample_hours_max: int
    explained_variance: list[dict]
    loadings: list[dict]
    points: list[dict]
    cluster_profiles: list[dict]
    cluster_count: int
    silhouette: float | None


def _numeric_complete(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame[list(PCA_FEATURES)].apply(pd.to_numeric, errors="coerce")
    complete = values.dropna(axis=0, how="any").copy()
    complete["time"] = pd.to_datetime(frame.loc[complete.index, "time"], utc=True)
    return complete


def _safe_corr(frame: pd.DataFrame, left: str, right: str) -> float:
    value = frame[left].corr(frame[right])
    return 0.0 if pd.isna(value) else float(value)


def _city_summary(frame: pd.DataFrame) -> dict[str, float]:
    complete = _numeric_complete(frame)
    if len(complete) < 168:
        raise ValueError(
            f"Only {len(complete)} complete hourly rows are available; at least 168 are required"
        )

    hour_cycle = complete.assign(hour=complete["time"].dt.hour).groupby("hour")["pm25"].mean()
    diurnal_amplitude = float(hour_cycle.max() - hour_cycle.min()) if not hour_cycle.empty else 0.0

    return {
        "pm25_mean": float(complete["pm25"].mean()),
        "pm25_p90": float(complete["pm25"].quantile(0.90)),
        "pm25_std": float(complete["pm25"].std(ddof=0)),
        "pm10_mean": float(complete["pm10"].mean()),
        "pm10_p90": float(complete["pm10"].quantile(0.90)),
        "no2_mean": float(complete["no2"].mean()),
        "no2_p90": float(complete["no2"].quantile(0.90)),
        "o3_mean": float(complete["o3"].mean()),
        "o3_p90": float(complete["o3"].quantile(0.90)),
        "o3_std": float(complete["o3"].std(ddof=0)),
        "so2_mean": float(complete["so2"].mean()),
        "co_mean": float(complete["co"].mean()),
        "temperature_mean": float(complete["temperature_2m"].mean()),
        "humidity_mean": float(complete["relative_humidity_2m"].mean()),
        "wind_speed_mean": float(complete["wind_speed_10m"].mean()),
        "boundary_layer_height_mean": float(complete["boundary_layer_height"].mean()),
        "precipitation_hour_fraction": float((complete["precipitation"] > 0.1).mean()),
        "pm25_diurnal_amplitude": diurnal_amplitude,
        "corr_pm25_wind": _safe_corr(complete, "pm25", "wind_speed_10m"),
        "corr_pm25_boundary_layer": _safe_corr(
            complete,
            "pm25",
            "boundary_layer_height",
        ),
        "corr_o3_temperature": _safe_corr(complete, "o3", "temperature_2m"),
    }


def _province_representatives(rows: list[dict]) -> list[dict]:
    """Highest window-mean PM2.5 per province, ties to the lower location_id."""
    best: dict[str, dict] = {}
    for row in sorted(rows, key=lambda item: (-item["pm25_mean"], item["location_id"])):
        best.setdefault(row["province"] or row["city"], row)
    return sorted(best.values(), key=lambda row: row["location_id"])


def fit_city_fingerprint(
    *,
    hours: int = 24 * 90,
    max_components: int = 5,
    max_clusters: int = 6,
) -> CityFingerprintArtifact:
    locations = active_location_rows()
    frames: dict[int, pd.DataFrame] = {}
    first_times: list[pd.Timestamp] = []
    last_times: list[pd.Timestamp] = []

    for location in locations:
        location_id = int(location["location_id"])
        frame = load_city_feature_frame(location_id, hours=hours)
        if frame.empty:
            continue
        times = pd.to_datetime(frame["time"], utc=True)
        frames[location_id] = frame.assign(time=times)
        first_times.append(times.min())
        last_times.append(times.max())

    if len(frames) < 3:
        raise ValueError("At least three cities with aligned history are required")

    common_start = max(first_times)
    common_end = min(last_times)
    if common_start >= common_end:
        raise ValueError("Cities do not share a common analysis window")

    rows: list[dict] = []
    location_by_id = {int(row["location_id"]): row for row in locations}

    for location_id, frame in frames.items():
        common = frame[(frame["time"] >= common_start) & (frame["time"] <= common_end)].copy()
        complete_count = len(_numeric_complete(common))
        if complete_count < 168:
            continue
        summary = _city_summary(common)
        location = location_by_id[location_id]
        rows.append(
            {
                "location_id": location_id,
                "city": location["city"],
                "province": location["province"],
                "region": region_for(location["city"]) or "其他",
                "sample_hours": complete_count,
                **summary,
            }
        )

    if len(rows) < 3:
        raise ValueError("Fewer than three cities have enough complete rows in the common window")

    eligible_city_count = len(rows)
    representatives = _province_representatives(rows)
    if len(representatives) < 3:
        raise ValueError("Fewer than three provinces have an eligible representative city")

    city_frame = pd.DataFrame(representatives)
    matrix = city_frame[list(FINGERPRINT_FEATURES)].astype(float)
    scaler = StandardScaler()
    standardized = scaler.fit_transform(matrix)

    component_count = min(max_components, len(FINGERPRINT_FEATURES), len(city_frame))
    pca = PCA(n_components=component_count)
    scores = pca.fit_transform(standardized)
    cumulative = np.cumsum(pca.explained_variance_ratio_)

    explained_variance = [
        {
            "component": f"PC{index + 1}",
            "variance_ratio": float(ratio),
            "cumulative_ratio": float(cumulative[index]),
        }
        for index, ratio in enumerate(pca.explained_variance_ratio_)
    ]
    loadings = []
    for feature_index, feature in enumerate(FINGERPRINT_FEATURES):
        row = {"feature": feature}
        for component_index in range(component_count):
            row[f"PC{component_index + 1}"] = float(
                pca.components_[component_index, feature_index]
            )
        loadings.append(row)

    cluster_count = 1
    silhouette: float | None = None
    labels = np.zeros(len(city_frame), dtype=int)
    if len(city_frame) >= 4:
        max_k = min(max_clusters, len(city_frame) - 1)
        best_score = -1.0
        for k in range(2, max_k + 1):
            model = KMeans(n_clusters=k, random_state=42, n_init=20)
            candidate = model.fit_predict(standardized)
            if len(set(candidate.tolist())) < 2:
                continue
            score = float(silhouette_score(standardized, candidate))
            if score > best_score:
                best_score = score
                labels = candidate
                cluster_count = k
                silhouette = score

    points = []
    for index, row in city_frame.iterrows():
        point = {
            "location_id": int(row["location_id"]),
            "city": row["city"],
            "province": row["province"],
            "region": row["region"],
            "sample_hours": int(row["sample_hours"]),
            "cluster": int(labels[index]) + 1,
            "features": {
                feature: float(row[feature])
                for feature in FINGERPRINT_FEATURES
            },
        }
        for component_index in range(component_count):
            point[f"PC{component_index + 1}"] = float(scores[index, component_index])
        points.append(point)

    cluster_profiles = []
    for cluster_index in range(cluster_count):
        mask = labels == cluster_index
        centroid = standardized[mask].mean(axis=0)
        top_indices = np.argsort(np.abs(centroid))[::-1][:4]
        cluster_profiles.append(
            {
                "cluster": cluster_index + 1,
                "city_count": int(mask.sum()),
                "top_features": [
                    {
                        "feature": FINGERPRINT_FEATURES[index],
                        "zscore": float(centroid[index]),
                    }
                    for index in top_indices
                ],
            }
        )

    return CityFingerprintArtifact(
        features=FINGERPRINT_FEATURES,
        window_start=common_start.isoformat(),
        window_end=common_end.isoformat(),
        city_count=len(points),
        eligible_city_count=eligible_city_count,
        representative_rule=REPRESENTATIVE_RULE,
        sample_hours_min=int(city_frame["sample_hours"].min()),
        sample_hours_max=int(city_frame["sample_hours"].max()),
        explained_variance=explained_variance,
        loadings=loadings,
        points=points,
        cluster_profiles=cluster_profiles,
        cluster_count=cluster_count,
        silhouette=silhouette,
    )
