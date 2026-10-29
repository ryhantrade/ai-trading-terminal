#!/usr/bin/env python3
"""AI Trading Terminal — Bloomberg-style crypto desk.

Pillars (from the reference build):
  REA            -> UI/UX analysis methodology: professional terminal layout
                    (watchlist | chart+forecast | research panel)
  Kronos         -> Kronos-mini foundation model forecasts on every chart
  TradingAgents  -> analyst debate pipeline (analysts -> risk -> portfolio),
                    rule-based on the SMC playbook (free); LLM pluggable.

Run:  python3 app.py   ->  http://127.0.0.1:8000
"""
import os
import time

from flask import Flask, jsonify, request, send_from_directory

import market_data
import analysts

app = Flask(__name__, static_folder="static", static_url_path="/static")

_forecast = None
try:
    import forecast_engine
    _forecast = forecast_engine
except Exception as e:  # torch missing etc. -> forecasts disabled, rest works
    print("forecast engine unavailable:", e)


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "kronos": _forecast is not None,
                    "time": time.time()})


@app.get("/api/activity")
def api_activity():
    top = min(int(request.args.get("top", 30)), 100)
    return jsonify(market_data.activity_scan(top=top))


@app.get("/api/candles")
def api_candles():
    symbol = request.args.get("coin", "BTC").upper()
    tf = int(request.args.get("tf", 60))
    return jsonify(market_data.ohlc(symbol, interval=tf))


@app.get("/api/forecast")
def api_forecast():
    symbol = request.args.get("coin", "BTC").upper()
    if _forecast is None:
        return jsonify({"status": "unavailable",
                        "error": "Kronos engine not loaded"}), 503
    data = market_data.ohlc(symbol, interval=60)
    if data.get("error") or len(data.get("candles", [])) < 120:
        return jsonify({"status": "error",
                        "error": data.get("error", "not enough candles")}), 502
    closes = [c["c"] for c in data["candles"]]
    job = _forecast.forecast_async(symbol, closes, n_paths=5, pred_len=24)
    return jsonify(job)


@app.get("/api/debate")
def api_debate():
    symbol = request.args.get("coin", "BTC").upper()
    data = market_data.ohlc(symbol, interval=60)
    if data.get("error") or len(data.get("candles", [])) < 60:
        return jsonify({"error": data.get("error", "not enough candles")}), 502
    fc = None
    if _forecast is not None:
        closes = [c["c"] for c in data["candles"]]
        fc = _forecast.forecast_async(symbol, closes, n_paths=5, pred_len=24)
    return jsonify(analysts.debate(symbol, data["candles"], fc))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
