"""The hand-written LSTM must be mathematically trustworthy before anything
draws its gates: analytic BPTT gradients are checked against central
differences, and a tiny training run must actually drive the loss down."""

from __future__ import annotations

import numpy as np
import pytest

from backend.ml import lstm


def _tiny_params(seed: int = 3) -> lstm.Params:
    rng = np.random.default_rng(seed)
    return lstm.Params.init(n_features=3, hidden=4, horizon=2, rng=rng)


def _loss_only(params: lstm.Params, x: np.ndarray, y: np.ndarray) -> float:
    pred, _, _ = lstm.forward(x, params)
    diff = pred - y
    return float(np.mean(diff * diff))


def test_bptt_gradients_match_numerical() -> None:
    rng = np.random.default_rng(0)
    # Central differences need float64: in float32 the loss delta underflows
    # into cancellation noise and the check measures rounding, not math.
    x = rng.normal(0, 1, (2, 5, 3)).astype(np.float64)
    y = rng.normal(0, 1, (2, 2)).astype(np.float64)
    params = _tiny_params()
    params.Wx = params.Wx.astype(np.float64)
    params.Wh = params.Wh.astype(np.float64)
    params.b = params.b.astype(np.float64)
    params.Wy = params.Wy.astype(np.float64)
    params.by = params.by.astype(np.float64)
    _, analytic = lstm.loss_and_grads(x, y, params)

    eps = 1e-5
    for name in ("Wx", "Wh", "b", "Wy", "by"):
        base = getattr(params, name)
        numeric = np.zeros_like(base)
        flat = base.reshape(-1)
        num_flat = numeric.reshape(-1)
        for k in range(flat.size):
            original = flat[k]
            flat[k] = original + eps
            up = _loss_only(params, x, y)
            flat[k] = original - eps
            down = _loss_only(params, x, y)
            flat[k] = original
            num_flat[k] = (up - down) / (2 * eps)
        ana = analytic[name].reshape(-1).astype(np.float64)
        denom = np.maximum(1.0, np.abs(ana) + np.abs(num_flat))
        rel = np.abs(ana - num_flat) / denom
        assert float(rel.max()) < 1e-5, f"{name} gradient mismatch: {rel.max()}"


def test_training_reduces_loss() -> None:
    rng = np.random.default_rng(1)
    # Learnable structure that persistence CANNOT express: the target doubles
    # the last input (persistence would predict it unscaled).
    n, t, f = 64, lstm.SEQ, 3
    x = rng.normal(0, 1, (n, t, f)).astype(np.float32)
    y = np.repeat(x[:, -1, 0:1] * 2.0, lstm.HORIZON, axis=1)
    data = lstm.Dataset(
        x_train=x,
        y_train=y,
        x_val=x[:8],
        y_val=y[:8],
        val_city=np.zeros(8, dtype=np.int64),
        city_mean=np.zeros(1, dtype=np.float32),
        city_std=np.ones(1, dtype=np.float32),
        train_hours=("", ""),
        val_hours=("", ""),
    )
    params, losses = lstm.train(data, epochs=60, batch_size=16, lr=5e-3)
    assert losses[-1] < losses[0] * 0.2
    # The trained cell must beat the persistence baseline on the synthetic task
    # it was given — if it can't win here, the cell itself is broken.
    metrics = lstm.evaluate(params, data)
    assert metrics["LSTM"]["mae_overall"] < metrics["Persistence"]["mae_overall"]


def test_forward_tape_records_consistent_gates() -> None:
    rng = np.random.default_rng(2)
    params = _tiny_params()
    x = rng.normal(0, 1, (1, 6, 3)).astype(np.float32)
    tape = lstm.Tape()
    pred, h_last, c_last = lstm.forward(x, params, tape)
    assert tape.f.shape == (6, 4)
    assert np.all(tape.f >= 0) and np.all(tape.f <= 1)
    assert np.all(tape.i >= 0) and np.all(tape.i <= 1)
    assert np.all(tape.o >= 0) and np.all(tape.o <= 1)
    assert np.all(np.abs(tape.g) <= 1)
    # Recomputing the recurrence from the tape must reproduce the final state:
    c_rebuilt = np.zeros(4, dtype=np.float32)
    for t in range(6):
        c_rebuilt = tape.f[t] * c_rebuilt + tape.i[t] * tape.g[t]
        assert np.allclose(c_rebuilt, tape.cell[t], atol=1e-5)
        assert np.allclose(tape.o[t] * np.tanh(c_rebuilt), tape.hidden[t], atol=1e-5)
    assert np.allclose(tape.cell[-1], c_last[0], atol=1e-6)
    assert np.allclose(tape.hidden[-1], h_last[0], atol=1e-6)
    assert pred.shape == (1, 2)


def test_build_windows_temporal_split() -> None:
    frames = {1: np.random.default_rng(4).normal(10, 3, (400, 3)).astype(np.float32)}
    data = lstm.build_windows(frames, seq=24, horizon=24, val_fraction=0.2, stride=1)
    train_n = data.x_train.shape[0]
    val_n = data.x_val.shape[0]
    assert train_n > 0 and val_n > 0
    # 400 hours: split at 320; training windows need target end <= 320
    # (start <= 272 -> 273 windows); validation starts at start >= 296
    # (296..352 = 57). The 23 ambiguous windows whose targets straddle the
    # split are dropped by construction.
    assert train_n == 273 and val_n == 57


def test_evaluate_denormalizes_to_real_units() -> None:
    rng = np.random.default_rng(5)
    frames = {1: (rng.normal(40, 10, (400, 3))).astype(np.float32)}
    data = lstm.build_windows(frames, val_fraction=0.2, stride=4)
    params, _ = lstm.train(data, epochs=2, batch_size=32)
    metrics = lstm.evaluate(params, data)
    for model in ("LSTM", "Persistence", "Rolling Mean"):
        assert model in metrics
        # µg/m³ scale: a well-formed error on ~N(40,10) data is O(10), not O(1)
        # or O(1000).
        assert 0.5 < metrics[model]["mae_overall"] < 100
        assert len(metrics[model]["mae"]) == lstm.HORIZON


def test_tape_empty_default() -> None:
    tape = lstm.Tape()
    assert tape.f.shape == (0, 0)
    assert tape.cell.shape == (0, 0)
