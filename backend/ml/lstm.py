"""Hand-written numpy LSTM for 24h PM2.5 forecasting.

No framework: the recurrent cell, its backpropagation-through-time, and the
Adam update are all implemented here, because the visualization contract is
the forward pass itself — every gate activation shown on the engine page is
read straight out of `forward_seq` below.

Model: FEATURES (8) -> LSTM(HIDDEN=16) over SEQ=24 hours -> dense -> HORIZON=24.
One global model trained on all 60 cities; each city's features are z-scored
with statistics estimated on its own training split only.

Evaluation is honest by construction: metrics are computed on the validation
windows against the CAMS analysis field (the only complete 96-day grid), with
Persistence / Rolling-Mean computed on the *same* windows for comparison.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

FEATURES: tuple[str, ...] = (
    "pm25",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_sin",
    "wind_direction_cos",
    "boundary_layer_height",
    "precipitation",
)
TARGET = "pm25"
SEQ = 24
HORIZON = 24
HIDDEN = 16

REPLAY_HOURS = 48


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Params:
    """Wx/b are fused across the four gates: rows [0:H)=f, [H:2H)=i,
    [2H:3H)=o, [3H:4H)=g̃."""

    Wx: np.ndarray  # (F, 4H)
    Wh: np.ndarray  # (H, 4H)
    b: np.ndarray  # (4H,)
    Wy: np.ndarray  # (H, horizon)
    by: np.ndarray  # (horizon,)

    @classmethod
    def init(cls, n_features: int, hidden: int, horizon: int, rng: np.random.Generator) -> "Params":
        std_x = 1.0 / math.sqrt(n_features)
        std_h = 1.0 / math.sqrt(hidden)
        # Forget-gate bias starts at 1: the cell remembers by default and has
        # to learn when to forget, not the other way around.
        bias = np.zeros(4 * hidden, dtype=np.float32)
        bias[:hidden] = 1.0
        return cls(
            Wx=(rng.normal(0, std_x, (n_features, 4 * hidden))).astype(np.float32),
            Wh=(rng.normal(0, std_h, (hidden, 4 * hidden))).astype(np.float32),
            b=bias,
            Wy=(rng.normal(0, std_h, (hidden, horizon))).astype(np.float32),
            by=np.zeros(horizon, dtype=np.float32),
        )

    def as_dict(self) -> dict:
        return {
            "Wx": self.Wx.tolist(),
            "Wh": self.Wh.tolist(),
            "b": self.b.tolist(),
            "Wy": self.Wy.tolist(),
            "by": self.by.tolist(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Params":
        return cls(
            Wx=np.asarray(data["Wx"], dtype=np.float32),
            Wh=np.asarray(data["Wh"], dtype=np.float32),
            b=np.asarray(data["b"], dtype=np.float32),
            Wy=np.asarray(data["Wy"], dtype=np.float32),
            by=np.asarray(data["by"], dtype=np.float32),
        )


@dataclass
class Tape:
    """Per-timestep activations from one forward pass — the visualization's
    ground truth. Gates are (T, H); cell/hidden (T, H); the pre-gate split is
    kept so the UI can show the raw affine mix if it ever wants to."""

    f: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    i: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    o: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    g: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    cell: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))
    hidden: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.float32))


def forward(x: np.ndarray, p: Params, tape: Tape | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Batched forward over a sequence.

    x: (B, T, F). Returns (pred (B, horizon), h_last (B, H), c_last (B, H)).
    With `tape`, also fills (T, H) activation arrays from the first sample —
    tapes are for single-series replay, so batch>1 simply overwrites with
    sample 0's trace.
    """
    B, T, F_ = x.shape
    H = p.Wh.shape[0]
    h = np.zeros((B, H), dtype=np.float32)
    c = np.zeros((B, H), dtype=np.float32)
    cache_f = np.empty((T, B, H), dtype=np.float32)
    cache_i = np.empty_like(cache_f)
    cache_o = np.empty_like(cache_f)
    cache_g = np.empty_like(cache_f)
    cache_tc = np.empty_like(cache_f)
    cache_c = np.empty_like(cache_f)
    cache_c_prev = np.empty_like(cache_f)
    cache_h_prev = np.empty_like(cache_f)

    for t in range(T):
        xt = x[:, t, :]
        cache_h_prev[t] = h
        cache_c_prev[t] = c
        a = xt @ p.Wx + h @ p.Wh + p.b
        af = a[:, :H]
        ai = a[:, H : 2 * H]
        ao = a[:, 2 * H : 3 * H]
        ag = a[:, 3 * H :]
        f = _sigmoid(af)
        i = _sigmoid(ai)
        o = _sigmoid(ao)
        g = np.tanh(ag)
        c = f * c + i * g
        tc = np.tanh(c)
        h = o * tc
        cache_f[t], cache_i[t], cache_o[t], cache_g[t], cache_tc[t] = f, i, o, g, tc
        cache_c[t] = c

    pred = h @ p.Wy + p.by
    if tape is not None:
        squeeze = lambda arr: np.transpose(arr, (1, 0, 2))[0]  # noqa: E731
        tape.f = squeeze(cache_f)
        tape.i = squeeze(cache_i)
        tape.o = squeeze(cache_o)
        tape.g = squeeze(cache_g)
        tape.cell = squeeze(cache_c)
        tape.hidden = squeeze(cache_tc * cache_o)
    return pred, h, c


def loss_and_grads(
    x: np.ndarray, y: np.ndarray, p: Params
) -> tuple[float, dict[str, np.ndarray]]:
    """MSE loss and BPTT gradients. y is (B, horizon) in the same normalized
    space as the targets."""
    B, T, _ = x.shape
    H = p.Wh.shape[0]
    pred, h_last, _ = forward(x, p)
    diff = pred - y
    loss = float(np.mean(diff * diff))

    d = (2.0 / diff.size) * diff  # (B, horizon)
    grads = {
        "Wy": h_last.T @ d,
        "by": d.sum(axis=0),
    }
    dh = d @ p.Wy.T  # (B, H)
    dc = np.zeros((B, H), dtype=np.float32)
    dWx = np.zeros_like(p.Wx)
    dWh = np.zeros_like(p.Wh)
    db = np.zeros_like(p.b)

    # Recompute the cache with a second sweep instead of storing it during
    # forward — a full cache doubles memory for BPTT; a re-run is cheap.
    h = np.zeros((B, H), dtype=np.float32)
    c = np.zeros((B, H), dtype=np.float32)
    steps: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for t in range(T):
        xt = x[:, t, :]
        h_prev = h
        c_prev = c
        a = xt @ p.Wx + h_prev @ p.Wh + p.b
        f = _sigmoid(a[:, :H])
        i = _sigmoid(a[:, H : 2 * H])
        o = _sigmoid(a[:, 2 * H : 3 * H])
        g = np.tanh(a[:, 3 * H :])
        c = f * c_prev + i * g
        tc = np.tanh(c)
        h = o * tc
        # h_prev/c_prev are the states ENTERING the step — dWh reads those,
        # not the outgoing ones.
        steps.append((xt, h_prev.copy(), c_prev.copy(), f, i, o, g))

    for t in range(T - 1, -1, -1):
        xt, h_prev, c_prev, f, i, o, g = steps[t]
        tc = np.tanh(c_prev * f + i * g)  # == tanh(c_t), consistent with c above
        # Each gate gets the derivative of its own activation: df/di carry
        # σ′, dg carries tanh′ — and do must carry σ′ too, or the output
        # gate's gradient comes out ~30× too large.
        do = dh * tc * o * (1.0 - o)
        dc = dc + dh * o * (1.0 - tc * tc)
        df = dc * c_prev * f * (1.0 - f)
        di = dc * g * i * (1.0 - i)
        dg = dc * i * (1.0 - g * g)
        dc_prev = dc * f
        da = np.concatenate([df, di, do, dg], axis=1)  # (B, 4H)
        dWx += xt.T @ da
        dWh += h_prev.T @ da
        db += da.sum(axis=0)
        dh = da @ p.Wh.T
        dc = dc_prev

    grads["Wx"] = dWx
    grads["Wh"] = dWh
    grads["b"] = db
    return loss, grads


class Adam:
    def __init__(self, params: Params, lr: float = 2e-3) -> None:
        self.lr = lr
        self.beta1, self.beta2, self.eps = 0.9, 0.999, 1e-8
        self.t = 0
        self.m = {
            name: np.zeros_like(getattr(params, name)) for name in ("Wx", "Wh", "b", "Wy", "by")
        }
        self.v = {name: np.zeros_like(getattr(params, name)) for name in ("Wx", "Wh", "b", "Wy", "by")}

    def step(self, params: Params, grads: dict[str, np.ndarray], clip_norm: float = 1.0) -> None:
        total = math.sqrt(sum(float(np.sum(g * g)) for g in grads.values()))
        scale = clip_norm / total if total > clip_norm else 1.0
        self.t += 1
        for name, grad in grads.items():
            g = grad * scale
            self.m[name] = self.beta1 * self.m[name] + (1 - self.beta1) * g
            self.v[name] = self.beta2 * self.v[name] + (1 - self.beta2) * (g * g)
            m_hat = self.m[name] / (1 - self.beta1**self.t)
            v_hat = self.v[name] / (1 - self.beta2**self.t)
            setattr(params, name, getattr(params, name) - self.lr * m_hat / (np.sqrt(v_hat) + self.eps))


@dataclass
class Dataset:
    """Windows pooled across cities. City stats travel with each window so
    predictions can be de-normalized to µg/m³ for metrics."""

    x_train: np.ndarray  # (N, SEQ, F) float32, normalized
    y_train: np.ndarray  # (N, HORIZON) float32, normalized pm25
    x_val: np.ndarray
    y_val: np.ndarray
    val_city: np.ndarray  # (N_val,) int index into city_mean/city_std
    city_mean: np.ndarray  # (C,) pm25 means (µg/m³)
    city_std: np.ndarray  # (C,) pm25 stds
    train_hours: tuple[str, str]
    val_hours: tuple[str, str]


def build_windows(
    frames: dict[int, np.ndarray],
    seq: int = SEQ,
    horizon: int = HORIZON,
    val_fraction: float = 0.2,
    stride: int = 2,
) -> Dataset:
    """frames: location_id -> (T_i, F) array already ordered oldest→newest.
    Per city: z-score with TRAIN-split statistics only, then cut windows.
    A window is validation iff its LAST target index sits in the city's
    trailing `val_fraction` of time."""
    xs_tr: list[np.ndarray] = []
    ys_tr: list[np.ndarray] = []
    xs_va: list[np.ndarray] = []
    ys_va: list[np.ndarray] = []
    va_city: list[int] = []
    means: list[float] = []
    stds: list[float] = []

    for city_id, (location_id, frame) in enumerate(sorted(frames.items())):
        total = frame.shape[0]
        if total < seq + horizon + 24:
            continue
        split = int(total * (1 - val_fraction))
        train_part = frame[:split]
        mean = train_part.mean(axis=0)
        std = train_part.std(axis=0)
        std[std < 1e-6] = 1.0
        means.append(float(mean[0]))
        stds.append(float(std[0]))
        norm = (frame - mean) / std
        last_val_start = split - seq  # first window index allowed in validation
        for start in range(0, total - seq - horizon + 1, stride):
            x = norm[start : start + seq]
            y = norm[start + seq : start + seq + horizon, 0]
            if start + seq + horizon <= split:
                xs_tr.append(x)
                ys_tr.append(y)
            elif start >= last_val_start:
                xs_va.append(x)
                ys_va.append(y)
                va_city.append(city_id)

    to_array = lambda parts: (  # noqa: E731
        np.stack(parts).astype(np.float32) if parts else np.zeros((0, seq, len(FEATURES)), np.float32)
    )
    return Dataset(
        x_train=to_array(xs_tr),
        y_train=np.stack(ys_tr).astype(np.float32) if ys_tr else np.zeros((0, horizon), np.float32),
        x_val=to_array(xs_va),
        y_val=np.stack(ys_va).astype(np.float32) if ys_va else np.zeros((0, horizon), np.float32),
        val_city=np.asarray(va_city, dtype=np.int64),
        city_mean=np.asarray(means, dtype=np.float32),
        city_std=np.asarray(stds, dtype=np.float32),
        train_hours=("", ""),
        val_hours=("", ""),
    )


def train(
    data: Dataset,
    epochs: int = 120,
    batch_size: int = 256,
    lr: float = 2e-3,
    seed: int = 7,
    progress: "callable | None" = None,
) -> tuple[Params, list[float]]:
    rng = np.random.default_rng(seed)
    params = Params.init(data.x_train.shape[2], HIDDEN, HORIZON, rng)
    opt = Adam(params, lr=lr)
    losses: list[float] = []
    n = data.x_train.shape[0]
    if n == 0:
        raise ValueError("no training windows")
    for epoch in range(epochs):
        order = rng.permutation(n)
        epoch_loss = 0.0
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            loss, grads = loss_and_grads(data.x_train[idx], data.y_train[idx], params)
            opt.step(params, grads)
            epoch_loss += loss * len(idx)
        losses.append(epoch_loss / n)
        if progress is not None:
            progress(epoch, losses[-1])
    return params, losses


def evaluate(params: Params, data: Dataset, batch_size: int = 512) -> dict:
    """Per-horizon MAE/RMSE in µg/m³ for the LSTM and, on the same validation
    windows, for the two baselines read off the input window itself."""
    x, y = data.x_val, data.y_val
    n = x.shape[0]
    if n == 0:
        return {}
    preds_norm = np.empty((n, HORIZON), dtype=np.float32)
    for start in range(0, n, batch_size):
        chunk = x[start : start + batch_size]
        pred, _, _ = forward(chunk, params)
        preds_norm[start : start + batch_size] = pred
    city = data.val_city
    mean = data.city_mean[city][:, None]
    std = data.city_std[city][:, None]
    pred = preds_norm * std + mean
    truth = y * std + mean
    last_pm = x[:, -1, 0:1] * std + mean  # persistence level
    roll = (x[:, -6:, 0] * std + mean).mean(axis=1, keepdims=True)

    def per_horizon(errors: np.ndarray) -> tuple[list[float], list[float]]:
        mae = np.abs(errors).mean(axis=0)
        rmse = np.sqrt((errors * errors).mean(axis=0))
        return [round(float(v), 3) for v in mae], [round(float(v), 3) for v in rmse]

    out: dict = {}
    for name, level in (("LSTM", pred), ("Persistence", np.repeat(last_pm, HORIZON, axis=1)), ("Rolling Mean", np.repeat(roll, HORIZON, axis=1))):
        mae, rmse = per_horizon(level - truth)
        out[name] = {
            "mae": mae,
            "rmse": rmse,
            "mae_overall": round(float(np.mean(mae)), 3),
            "rmse_overall": round(float(np.sqrt(np.mean(np.asarray(rmse) ** 2))), 3),
            "samples": int(n),
        }
    return out


def forecast_next(
    params: Params,
    window_norm: np.ndarray,  # (SEQ, F) newest last
    pm_mean: float,
    pm_std: float,
) -> np.ndarray:
    """De-normalized 24h forecast from the trained decode (training口径: SEQ
    window -> dense horizon)."""
    pred, _, _ = forward(window_norm[None, :, :].astype(np.float32), params)
    return (pred[0] * pm_std + pm_mean).astype(float)


def replay(
    params: Params,
    series_norm: np.ndarray,  # (REPLAY_HOURS, F)
) -> Tape:
    """One genuine recurrent pass over the replay window; every gate value the
    engine page draws comes from here."""
    tape = Tape()
    forward(series_norm[None, :, :].astype(np.float32), params, tape)
    return tape


def count_params(p: Params) -> int:
    return int(sum(arr.size for arr in (p.Wx, p.Wh, p.b, p.Wy, p.by)))


def save_artifact(path: str, params: Params, data: Dataset, metrics: dict, extra: dict) -> None:
    payload = {
        "features": list(FEATURES),
        "seq": SEQ,
        "horizon": HORIZON,
        "hidden": HIDDEN,
        "params": params.as_dict(),
        # Per-city target stats travel with the artifact so any caller can
        # de-normalize; feature stats too, so replay can normalize.
        "city_ids": _CITY_IDS,
        "city_target_mean": data.city_mean.tolist(),
        "city_target_std": data.city_std.tolist(),
        "city_feature_mean": _FEATURE_MEAN,
        "city_feature_std": _FEATURE_STD,
        "metrics": metrics,
        "train_hours": list(data.train_hours),
        "val_hours": list(data.val_hours),
        **extra,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


# --- per-city feature statistics stash (filled by the training pipeline) ----
_CITY_IDS: list[int] = []
_FEATURE_MEAN: list[list[float]] = []
_FEATURE_STD: list[list[float]] = []


def stash_city_stats(frames: dict[int, np.ndarray], val_fraction: float = 0.2) -> None:
    """Record each city's training-split feature statistics next to its target
    statistics. MUST stay index-aligned with build_windows: same sorted order,
    same minimum-length skip rule."""
    global _CITY_IDS, _FEATURE_MEAN, _FEATURE_STD
    _CITY_IDS = []
    _FEATURE_MEAN = []
    _FEATURE_STD = []
    for location_id in sorted(frames):
        frame = frames[location_id]
        if frame.shape[0] < SEQ + HORIZON + 24:
            continue
        split = int(frame.shape[0] * (1 - val_fraction))
        mean = frame[:split].mean(axis=0)
        std = frame[:split].std(axis=0)
        std[std < 1e-6] = 1.0
        _CITY_IDS.append(location_id)
        _FEATURE_MEAN.append([round(float(v), 6) for v in mean])
        _FEATURE_STD.append([round(float(v), 6) for v in std])
