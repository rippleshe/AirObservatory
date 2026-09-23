import sqlite3
from pathlib import Path

from backend.ml.baselines import persistence, rolling_mean

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")

def test_schema_separates_observation_model_and_forecast():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    tables = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "air_observations" in tables
    assert "air_model_analysis" in tables
    assert "forecasts" in tables

def test_backtest_view_exists():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    views = {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    }
    assert "forecast_backtest_pm25" in views

def test_baselines_are_deterministic():
    x = [10, 20, 30, 40, 50, 60]
    assert persistence(x, horizon=3) == [60.0, 60.0, 60.0]
    assert rolling_mean(x, horizon=2, window=3) == [50.0, 50.0]
