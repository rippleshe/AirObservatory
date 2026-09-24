from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from backend.db import transaction
from backend.repository import location_row

from .features import load_city_feature_frame
from .fingerprint import fit_city_fingerprint
from .pca import fit_city_pca


def materialize_city_structure(
    location_id: int,
    hours: int = 24 * 90,
    max_components: int = 5,
) -> dict:
    location = location_row(location_id)
    if location is None:
        raise ValueError(f"Unknown location_id={location_id}")

    frame = load_city_feature_frame(location_id, hours=hours)
    artifact = fit_city_pca(frame, max_components=max_components)
    run_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()
    window_start = artifact.scores[0]["time"]
    window_end = artifact.scores[-1]["time"]

    payload = {
        "run_id": run_id,
        "location_id": location_id,
        "city": location["city"],
        "created_at": created_at,
        "window_start": window_start,
        "window_end": window_end,
        "sample_count": artifact.sample_count,
        "input_rows": artifact.input_rows,
        "dropped_rows": artifact.dropped_rows,
        "missing_fraction": artifact.missing_fraction,
        "standardization": "z-score",
        "missing_strategy": "complete_case_no_interpolation",
        "pollution_source": "CAMS model analysis",
        "weather_source": "Open-Meteo historical weather/reanalysis",
        "features": list(artifact.features),
        "explained_variance": artifact.explained_variance,
        "loadings": artifact.loadings,
        "scores": artifact.scores,
        "correlation": artifact.correlation,
    }

    with transaction() as con:
        con.execute(
            """
            INSERT INTO analysis_runs(
                run_id, analysis_type, version, window_start, window_end,
                created_at, config_json, metrics_json, artifact_path, status
            ) VALUES (?, ?, 'pca-zscore-hourly', ?, ?, ?, ?, ?, NULL, 'success')
            """,
            (
                run_id,
                f"city_structure:{location_id}",
                window_start,
                window_end,
                created_at,
                json.dumps(
                    {
                        "location_id": location_id,
                        "hours": hours,
                        "max_components": max_components,
                        "standardization": "z-score",
                        "missing_strategy": "complete_case_no_interpolation",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return payload

def materialize_city_fingerprint(
    hours: int = 24 * 90,
    max_components: int = 5,
    max_clusters: int = 6,
) -> dict:
    artifact = fit_city_fingerprint(
        hours=hours,
        max_components=max_components,
        max_clusters=max_clusters,
    )
    run_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()

    payload = {
        "run_id": run_id,
        "created_at": created_at,
        "window_start": artifact.window_start,
        "window_end": artifact.window_end,
        "city_count": artifact.city_count,
        "sample_hours_min": artifact.sample_hours_min,
        "sample_hours_max": artifact.sample_hours_max,
        "features": list(artifact.features),
        "standardization": "z-score across cities",
        "local_structure_warning": (
            "National fingerprint PCA is fit on common city-level summary features; "
            "city-local PCA axes are not compared across cities."
        ),
        "cluster_method": "KMeans; k selected by maximum silhouette over k=2..6",
        "cluster_count": artifact.cluster_count,
        "silhouette": artifact.silhouette,
        "explained_variance": artifact.explained_variance,
        "loadings": artifact.loadings,
        "points": artifact.points,
        "cluster_profiles": artifact.cluster_profiles,
    }

    with transaction() as con:
        con.execute(
            """
            INSERT INTO analysis_runs(
                run_id, analysis_type, version, window_start, window_end,
                created_at, config_json, metrics_json, artifact_path, status
            ) VALUES (
                ?, 'city_fingerprint', 'city-summary-pca-kmeans',
                ?, ?, ?, ?, ?, NULL, 'success'
            )
            """,
            (
                run_id,
                artifact.window_start,
                artifact.window_end,
                created_at,
                json.dumps(
                    {
                        "hours": hours,
                        "max_components": max_components,
                        "max_clusters": max_clusters,
                        "standardization": "z-score across cities",
                        "cluster_selection": "max silhouette for k=2..6",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return payload

