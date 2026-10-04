"""Training pipeline and serving layer around the hand-written numpy LSTM.

lstm.py is the pure mathematics; this module owns the database: it pulls the
aligned CAMS×weather feature grid, trains one global model, evaluates it
against the baselines on the same validation windows, registers the run in
`model_runs` (first writer that table has ever had), writes the 24h forecasts
into `forecasts` so every existing consumer (TraceDeck, the engine fan, the
metrics endpoint) picks the LSTM up automatically, and serves per-city gate
activations for the engine page's computation replay.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from backend.analytics.features import load_city_feature_frame
from backend.config import get_settings
from backend.db import connect, get_source, transaction
from backend.ml import lstm

logger = logging.getLogger("air_observatory.lstm")

MODEL_NAME = "LSTM"
TRAIN_EPOCHS = 90
WINDOW_STRIDE = 2
SNAPSHOTS_TO_KEEP = 3
# The engine page replays this many hours through the cell; the forecast
# itself stays at the training口径 (last SEQ hours -> dense HORIZON).
REPLAY_HOURS = lstm.REPLAY_HOURS


def collect_feature_frames(
    min_hours: int = 240,
) -> tuple[dict[int, np.ndarray], dict[int, list[str]]]:
    """Per city: (T, 8) float32 feature matrix in lstm.FEATURES order, plus
    the aligned hourly timestamps. Rows with any missing feature are dropped —
    the grid is dense in practice, this is a guarantee, not a patch."""
    with connect() as con:
        locations = con.execute(
            """
            SELECT location_id, city
            FROM locations
            WHERE active=1 AND station_type='city_reference'
            ORDER BY location_id
            """
        ).fetchall()

    frames: dict[int, np.ndarray] = {}
    times: dict[int, list[str]] = {}
    for location in locations:
        frame = load_city_feature_frame(location["location_id"], hours=24 * 110)
        if frame.empty:
            continue
        frame = frame.dropna()
        if frame.shape[0] < min_hours:
            continue
        matrix = frame[list(lstm.FEATURES)].to_numpy(dtype=np.float32)
        frames[location["location_id"]] = matrix
        times[location["location_id"]] = [str(v) for v in frame["time"].tolist()]
    return frames, times


def train_and_register(epochs: int = TRAIN_EPOCHS) -> dict:
    """Full nightly job: collect → train → evaluate → register → publish."""
    started = datetime.now(UTC)
    frames, times = collect_feature_frames()
    if len(frames) < 10:
        return {"status": "error", "message": f"only {len(frames)} cities have usable grids"}
    lstm.stash_city_stats(frames)
    data = lstm.build_windows(frames, stride=WINDOW_STRIDE)
    logger.info(
        "LSTM dataset: %d train / %d val windows across %d cities",
        data.x_train.shape[0],
        data.x_val.shape[0],
        len(frames),
    )

    # Honest spans for the registry: training covers each city up to its own
    # 80% mark, so the global claim is the intersection across cities.
    splits = {
        location_id: int(len(stamps) * 0.8)
        for location_id, stamps in times.items()
        if location_id in frames
    }
    data.train_hours = (
        min(stamps[0] for stamps in times.values()),
        min(times[location_id][split - 1] for location_id, split in splits.items()),
    )
    data.val_hours = (
        max(times[location_id][split] for location_id, split in splits.items()),
        max(stamps[-1] for stamps in times.values()),
    )

    def progress(epoch: int, loss: float) -> None:
        if epoch % 10 == 0 or epoch == epochs - 1:
            logger.info("LSTM epoch %d/%d loss %.5f", epoch + 1, epochs, loss)

    params, losses = lstm.train(data, epochs=epochs, progress=progress)
    metrics = lstm.evaluate(params, data)

    version = f"numpy-h{lstm.HIDDEN}-w{lstm.SEQ}-f{lstm.HORIZON}-{started.strftime('%Y%m%d%H%M')}"
    settings = get_settings()
    artifact_dir = settings.resolved_database_path.parent / "models"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"lstm_pm25_{version}.json"

    created_at = started.isoformat()
    lstm.save_artifact(
        str(artifact_path),
        params,
        data,
        metrics,
        extra={
            "version": version,
            "trained_at": created_at,
            "epochs": epochs,
            "losses": [round(v, 6) for v in losses[:: max(1, len(losses) // 50)]],
            "final_loss": losses[-1] if losses else None,
            "eval_basis": "cams_analysis",
        },
    )

    val_end = data.val_hours[1]
    horizons = list(range(1, lstm.HORIZON + 1))
    with transaction() as con:
        con.execute(
            "UPDATE model_runs SET is_active=0 WHERE model_name=? AND target_variable=?",
            (MODEL_NAME, "pm25"),
        )
        con.execute(
            """
            INSERT INTO model_runs(
                run_id, model_name, model_version, location_scope, target_variable,
                horizons_json, train_start, train_end, validation_start, validation_end,
                features_json, metrics_json, artifact_path, created_at, is_active
            ) VALUES (?, ?, ?, 'global', 'pm25', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                str(uuid.uuid4()),
                MODEL_NAME,
                version,
                json.dumps(horizons),
                data.train_hours[0],
                data.train_hours[1],
                data.val_hours[0],
                val_end,
                json.dumps(list(lstm.FEATURES)),
                json.dumps(metrics, ensure_ascii=False),
                str(artifact_path),
                created_at,
            ),
        )

    published = publish_lstm_forecasts(params, data, frames, times, created_at, version)
    pruned = _prune_lstm_snapshots()
    summary = {
        "status": "ok",
        "version": version,
        "cities": len(frames),
        "windows": [int(data.x_train.shape[0]), int(data.x_val.shape[0])],
        "epochs": epochs,
        "final_loss": losses[-1] if losses else None,
        "metrics": {
            name: {"mae": value["mae_overall"], "rmse": value["rmse_overall"]}
            for name, value in metrics.items()
        },
        "forecasts_written": published,
        "snapshots_pruned": pruned,
        "artifact": str(artifact_path),
    }
    logger.info("LSTM training registered: %s", json.dumps(summary, ensure_ascii=False))
    return summary


def publish_lstm_forecasts(
    params: lstm.Params,
    data: lstm.Dataset,
    frames: dict[int, np.ndarray],
    times: dict[int, list[str]],
    issued_at: str,
    version: str,
) -> int:
    """Write each city's next 24h into `forecasts` under model_name='LSTM'
    (same upsert contract as the baselines)."""
    source = get_source("air_observatory_baseline")
    if source is None:
        raise RuntimeError("Database is not initialized with the baseline forecast source")
    ids = list(lstm._CITY_IDS)
    written = 0
    with transaction() as con:
        for city_index, location_id in enumerate(ids):
            frame = frames.get(location_id)
            stamps = times.get(location_id)
            if frame is None or stamps is None or frame.shape[0] < lstm.SEQ:
                continue
            f_mean = np.asarray(lstm._FEATURE_MEAN[city_index], dtype=np.float32)
            f_std = np.asarray(lstm._FEATURE_STD[city_index], dtype=np.float32)
            window = (frame[-lstm.SEQ :] - f_mean) / f_std
            values = lstm.forecast_next(
                params,
                window,
                float(data.city_mean[city_index]),
                float(data.city_std[city_index]),
            )
            last_time = datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
            for horizon, value in enumerate(values, start=1):
                target_at = last_time + timedelta(hours=horizon)
                con.execute(
                    """
                    INSERT INTO forecasts(
                        location_id, source_id, model_name, model_version,
                        issued_at, target_at, horizon_hours, variable,
                        predicted_value, unit, fetched_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pm25', ?, 'µg/m³', ?, ?)
                    ON CONFLICT(
                        location_id, model_name, model_version,
                        issued_at, target_at, variable
                    ) DO UPDATE SET
                        predicted_value=excluded.predicted_value,
                        fetched_at=excluded.fetched_at
                    """,
                    (
                        location_id,
                        source["source_id"],
                        MODEL_NAME,
                        version,
                        issued_at,
                        target_at.isoformat(),
                        horizon,
                        round(float(value), 3),
                        datetime.now(UTC).isoformat(),
                        json.dumps({"eval_basis": "cams_analysis"}, ensure_ascii=False),
                    ),
                )
                written += 1
    return written


def _prune_lstm_snapshots(keep: int = SNAPSHOTS_TO_KEEP) -> int:
    with transaction() as con:
        cursor = con.execute(
            """
            DELETE FROM forecasts
            WHERE model_name=? AND variable='pm25'
              AND issued_at NOT IN (
                SELECT DISTINCT issued_at FROM forecasts
                WHERE model_name=? AND variable='pm25'
                ORDER BY issued_at DESC LIMIT ?
              )
            """,
            (MODEL_NAME, MODEL_NAME, keep),
        )
        return cursor.rowcount


# --- serving -----------------------------------------------------------------


def load_active_artifact() -> dict | None:
    """The trained model, cached by file mtime so retraining hot-swaps."""
    with connect() as con:
        row = con.execute(
            """
            SELECT artifact_path FROM model_runs
            WHERE model_name=? AND target_variable='pm25' AND is_active=1
            ORDER BY created_at DESC LIMIT 1
            """,
            (MODEL_NAME,),
        ).fetchone()
    if row is None or not row["artifact_path"]:
        return None
    path = Path(row["artifact_path"])
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    cache = _artifact_cache
    if cache.get("path") != str(path) or cache.get("mtime") != mtime:
        cache["path"] = str(path)
        cache["mtime"] = mtime
        cache["data"] = json.loads(path.read_text(encoding="utf-8"))
    return cache["data"]


_artifact_cache: dict = {}


def city_lstm_run(location_id: int) -> dict | None:
    """Everything the engine page needs for one city: the 48h replay tape of
    genuine gate activations plus the 24h forecast and the run's metrics."""
    artifact = load_active_artifact()
    if artifact is None:
        return None
    ids: list[int] = artifact.get("city_ids", [])
    if location_id not in ids:
        return None
    city_index = ids.index(location_id)

    frame = load_city_feature_frame(location_id, hours=24 * 6).dropna()
    if frame.shape[0] < REPLAY_HOURS:
        return None
    times = [str(v) for v in frame["time"].tolist()]
    matrix = frame[list(lstm.FEATURES)].to_numpy(dtype=np.float32)

    f_mean = np.asarray(artifact["city_feature_mean"][city_index], dtype=np.float32)
    f_std = np.asarray(artifact["city_feature_std"][city_index], dtype=np.float32)
    params = lstm.Params.from_dict(artifact["params"])

    replay_series = (matrix[-REPLAY_HOURS:] - f_mean) / f_std
    tape = lstm.replay(params, replay_series)

    window = (matrix[-lstm.SEQ :] - f_mean) / f_std
    values = lstm.forecast_next(
        params,
        window,
        artifact["city_target_mean"][city_index],
        artifact["city_target_std"][city_index],
    )
    last_time = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))

    steps = []
    for t in range(REPLAY_HOURS):
        steps.append(
            {
                "target_at": times[t],
                # The real feature vector this timestep fed the cell, kept in
                # physical units so the input band and the gates share one
                # honest time axis.
                "x": [round(float(v), 2) for v in matrix[t]],
                "f": [round(float(v), 3) for v in tape.f[t]],
                "i": [round(float(v), 3) for v in tape.i[t]],
                "o": [round(float(v), 3) for v in tape.o[t]],
                "g": [round(float(v), 3) for v in tape.g[t]],
                "cell": [round(float(v), 3) for v in tape.cell[t]],
                "hidden": [round(float(v), 3) for v in tape.hidden[t]],
            }
        )
    forecast = []
    for horizon, value in enumerate(values, start=1):
        forecast.append(
            {
                "target_at": (last_time + timedelta(hours=horizon)).isoformat(),
                "horizon_hours": horizon,
                "value": round(float(value), 3),
            }
        )

    metrics = artifact.get("metrics", {})
    metric_rows = []
    for model_name in ("LSTM", "Persistence", "Rolling Mean"):
        payload = metrics.get(model_name)
        if not payload:
            continue
        for horizon in range(lstm.HORIZON):
            metric_rows.append(
                {
                    "model_name": model_name,
                    "model_revision": artifact.get("version", "lstm"),
                    "horizon_hours": horizon + 1,
                    "samples": payload.get("samples", 0),
                    "mae": payload["mae"][horizon],
                    "rmse": payload["rmse"][horizon],
                }
            )

    return {
        "location_id": location_id,
        "city": _city_name(location_id),
        "unit": "µg/m³",
        "hidden": lstm.HIDDEN,
        "window_hours": lstm.SEQ,
        "replay_hours": REPLAY_HOURS,
        "feature_names": list(lstm.FEATURES),
        "steps": steps,
        "forecast": forecast,
        "metrics": metric_rows,
        "meta": {
            "version": artifact.get("version"),
            "trained_at": artifact.get("trained_at"),
            "eval_basis": artifact.get("eval_basis", "cams_analysis"),
            "params": lstm.count_params(params),
            "epochs": artifact.get("epochs"),
        },
    }


def artifact_ready(max_age_hours: float = 20.0) -> bool:
    artifact = load_active_artifact()
    if artifact is None:
        return False
    trained_at = artifact.get("trained_at")
    if not trained_at:
        return False
    try:
        at = datetime.fromisoformat(trained_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age = datetime.now(UTC) - at.astimezone(UTC)
    return age <= timedelta(hours=max_age_hours)


def _city_name(location_id: int) -> str:
    with connect() as con:
        row = con.execute(
            "SELECT city FROM locations WHERE location_id=?", (location_id,)
        ).fetchone()
    return row["city"] if row else ""
