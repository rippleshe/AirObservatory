PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    province TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    station_type TEXT NOT NULL DEFAULT 'city_reference',
    external_id TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    UNIQUE(name, station_type, external_id)
);

CREATE TABLE IF NOT EXISTS sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN (
        'ground_observation',
        'low_cost_sensor',
        'model_analysis',
        'external_forecast',
        'self_forecast',
        'weather_observation',
        'weather_forecast'
    )),
    cadence_minutes INTEGER,
    is_authoritative INTEGER NOT NULL DEFAULT 0 CHECK(is_authoritative IN (0,1)),
    description TEXT
);

CREATE TABLE IF NOT EXISTS provider_bindings (
    binding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    external_location_id TEXT NOT NULL,
    external_name TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    sensors_json TEXT NOT NULL,
    first_at TEXT,
    last_at TEXT,
    last_checked_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    UNIQUE(location_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_bindings_source
ON provider_bindings(source_id, active);

CREATE TABLE IF NOT EXISTS air_observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    pm25 REAL,
    pm10 REAL,
    no2 REAL,
    o3 REAL,
    so2 REAL,
    co REAL,
    aqi REAL,
    aqi_standard TEXT,
    quality_flag TEXT NOT NULL DEFAULT 'ok',
    raw_ref TEXT,
    UNIQUE(location_id, source_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_air_obs_loc_time
ON air_observations(location_id, observed_at);

CREATE TABLE IF NOT EXISTS air_model_analysis (
    analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    valid_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    model_run_at TEXT,
    pm25 REAL,
    pm10 REAL,
    no2 REAL,
    o3 REAL,
    so2 REAL,
    co REAL,
    reference_aqi REAL,
    quality_flag TEXT NOT NULL DEFAULT 'ok',
    UNIQUE(location_id, source_id, valid_at)
);

CREATE INDEX IF NOT EXISTS idx_model_analysis_loc_time
ON air_model_analysis(location_id, valid_at);

CREATE TABLE IF NOT EXISTS weather_observations (
    weather_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    observed_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    temperature_2m REAL,
    relative_humidity_2m REAL,
    pressure_msl REAL,
    precipitation REAL,
    wind_speed_10m REAL,
    wind_direction_10m REAL,
    boundary_layer_height REAL,
    quality_flag TEXT NOT NULL DEFAULT 'ok',
    UNIQUE(location_id, source_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_weather_obs_loc_time
ON weather_observations(location_id, observed_at);

CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(location_id),
    source_id INTEGER REFERENCES sources(source_id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    target_at TEXT NOT NULL,
    horizon_hours INTEGER NOT NULL,
    variable TEXT NOT NULL,
    predicted_value REAL,
    lower_bound REAL,
    upper_bound REAL,
    unit TEXT,
    fetched_at TEXT NOT NULL,
    metadata_json TEXT,
    UNIQUE(location_id, model_name, model_version, issued_at, target_at, variable)
);

CREATE INDEX IF NOT EXISTS idx_forecasts_target
ON forecasts(location_id, variable, target_at);

CREATE INDEX IF NOT EXISTS idx_forecasts_issue
ON forecasts(location_id, model_name, issued_at);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    analysis_type TEXT NOT NULL,
    version TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    metrics_json TEXT,
    artifact_path TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runs (
    run_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    location_scope TEXT NOT NULL,
    target_variable TEXT NOT NULL,
    horizons_json TEXT NOT NULL,
    train_start TEXT NOT NULL,
    train_end TEXT NOT NULL,
    validation_start TEXT,
    validation_end TEXT,
    test_start TEXT,
    test_end TEXT,
    features_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    artifact_path TEXT,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_model_active
ON model_runs(target_variable, is_active);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    dataset TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_start TEXT,
    requested_end TEXT,
    latest_source_time TEXT,
    inserted_rows INTEGER NOT NULL DEFAULT 0,
    updated_rows INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    latency_seconds REAL,
    status TEXT NOT NULL,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_provider_time
ON ingestion_runs(provider, started_at);

DROP VIEW IF EXISTS forecast_backtest_pm25;
CREATE VIEW forecast_backtest_pm25 AS
SELECT
    f.forecast_id,
    f.location_id,
    l.city,
    f.model_name,
    f.model_version,
    f.issued_at,
    f.target_at,
    f.horizon_hours,
    f.predicted_value,
    o.pm25 AS observed_value,
    (o.pm25 - f.predicted_value) AS error,
    ABS(o.pm25 - f.predicted_value) AS absolute_error,
    o.source_id AS observation_source_id,
    o.quality_flag
FROM forecasts f
JOIN locations l ON l.location_id=f.location_id
JOIN air_observations o
  ON o.location_id=f.location_id
 AND o.observed_at=f.target_at
WHERE f.variable='pm25'
  AND o.pm25 IS NOT NULL
  AND f.predicted_value IS NOT NULL;
