#!/usr/bin/env python3
"""Kronos-mini forecasting engine.

Lazy-loads the model once, then forecasts 24 steps ahead from 512 hourly
candles. Forecasts run in a background thread and are cached (1h TTL) so the
web API stays snappy: /api/forecast returns {status: pending} while computing.
"""
import os
import sys
import threading
import time

import numpy as np
import pandas as pd

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BASE, "kronos"))

MODEL_DIR = os.path.join(_BASE, "models", "mini")
TOK_DIR = os.path.join(_BASE, "models", "mini-tok")

_predictor = None
_lock = threading.Lock()
_jobs = {}   # key -> {status, result, started}


def _get_predictor():
    global _predictor
    if _predictor is None:
        import torch
        # Constrained containers (e.g. Render Free 0.1 CPU): torch defaults to
        # host core count and thrashes. Pin threads for predictable speed.
        try:
            torch.set_num_threads(2)
            torch.set_num_interop_threads(2)
        except Exception:
            pass
        from model import Kronos, KronosTokenizer, KronosPredictor
        tok = KronosTokenizer.from_pretrained(TOK_DIR)
        mdl = Kronos.from_pretrained(MODEL_DIR)
        mdl.eval()
        _predictor = KronosPredictor(mdl, tok, max_context=512)
    return _predictor


def _run_forecast(key, closes, n_paths=5, pred_len=24):
    """Blocking forecast; stores result in _jobs[key]."""
    try:
        from model.kronos import calc_time_stamps
        predictor = _get_predictor()
        n = len(closes)
        lookback = min(512, n)
        seg = closes[n - lookback:]
        now = pd.Timestamp.utcnow().floor("h")
        x_ts = pd.Series(pd.date_range(now - pd.Timedelta(hours=lookback - 1),
                                      periods=lookback, freq="h"))
        y_ts = pd.Series(pd.date_range(now + pd.Timedelta(hours=1),
                                      periods=pred_len, freq="h"))

        o = np.asarray(seg, dtype=np.float32)
        # synthesize HLC around close (Kronos needs OHLC; tight band is fine)
        rng = np.maximum(np.abs(np.diff(o, prepend=o[0])), o * 0.0005)
        df = pd.DataFrame({
            "open": o, "high": o + rng * 0.6, "low": o - rng * 0.6,
            "close": o, "volume": np.zeros_like(o), "amount": np.zeros_like(o),
        })
        x = df[["open", "high", "low", "close", "volume", "amount"]].values.astype(np.float32)
        mu, sd = x.mean(0), x.std(0)
        xn = np.clip((x - mu) / (sd + 1e-5), -5, 5)[np.newaxis, :]
        x_stamp = calc_time_stamps(x_ts).values.astype(np.float32)[np.newaxis, :]
        y_stamp = calc_time_stamps(y_ts).values.astype(np.float32)[np.newaxis, :]

        paths = []
        for _ in range(n_paths):
            p = predictor.generate(xn, x_stamp, y_stamp, pred_len,
                                   T=1.0, top_k=0, top_p=0.9,
                                   sample_count=1, verbose=False)
            p = p.squeeze(0) * (sd + 1e-5) + mu
            paths.append([float(v) for v in p[:, 3]])
        paths = np.array(paths)
        last = float(o[-1])
        ends = paths[:, -1]
        p_up = float((ends > last).mean())
        median = [float(v) for v in np.median(paths, axis=0)]
        p10 = [float(v) for v in np.percentile(paths, 10, axis=0)]
        p90 = [float(v) for v in np.percentile(paths, 90, axis=0)]
        exp_move = float((ends.mean() - last) / last * 100)
        _jobs[key] = {"status": "ready", "result": {
            "paths": [[float(v) for v in row] for row in paths],
            "median": median, "p10": p10, "p90": p90,
            "p_up": round(p_up, 2),
            "exp_move_pct": round(exp_move, 2),
            "last_close": last,
            "forecast_at": time.time(),
            "timestamps": [int(t.timestamp()) for t in y_ts],
        }}
    except Exception as e:
        _jobs[key] = {"status": "error", "error": str(e)[:300]}


def forecast_async(symbol, closes, n_paths=5, pred_len=24, ttl=3600):
    """Kick off a forecast if none cached/running. Returns job dict."""
    key = f"{symbol}:{n_paths}:{pred_len}"
    with _lock:
        job = _jobs.get(key)
        now = time.time()
        if job and job.get("status") == "ready":
            res = job.get("result", {})
            if now - res.get("forecast_at", 0) < ttl:
                return job
        if job and job.get("status") == "running":
            return job
        closes = [float(c) for c in closes]
        _jobs[key] = {"status": "running", "started": now}
        t = threading.Thread(target=_run_forecast,
                             args=(key, closes, n_paths, pred_len),
                             daemon=True)
        t.start()
        return _jobs[key]
