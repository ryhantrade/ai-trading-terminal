# AI Trading Terminal

Bloomberg-style crypto trading terminal powered by 3 open-source pillars
(from the reference AI-desk build):

| Pillar | Role in this terminal |
|---|---|
| **REA** (morluto/rea) | UI/UX analysis methodology — professional terminal layout: watchlist \| chart + forecast cone \| AI research panel |
| **Kronos** (shiyu-coder/Kronos) | Kronos-mini foundation model (4.1M params, MIT) forecasts 24h ahead from 512 hourly candles; 5 sampled paths → P(up), expected move, p10/p50/p90 cone on the chart |
| **TradingAgents** (TauricResearch/TradingAgents) | Analyst-debate pipeline (analysts → bull/bear → risk → portfolio manager). Analysts are **rule-based on the SMC Market-Mechanics playbook** (free, backtested) instead of paid LLM calls |

## Live data (all free, no keys)

- **Market activity scan** — CoinGecko `/coins/markets` (top 500), ranked by
  volume/market-cap + volatility → big-transaction / whale-activity coins
- **OHLCV** — Kraken public API (680 USD pairs, hourly)

## API

- `GET /` — terminal UI
- `GET /api/health`
- `GET /api/activity?top=30` — ranked market activity (5-min cache)
- `GET /api/candles?coin=BTC&tf=60` — Kraken OHLCV (5-min cache)
- `GET /api/forecast?coin=BTC` — Kronos forecast; `{status: running}` while
  computing in background, then `{status: ready, result: {paths, median, p10, p90, p_up, exp_move_pct}}` (1-h cache)
- `GET /api/debate?coin=BTC` — analyst debate → `{verdict: BUY|SELL|HOLD, confidence, analysts[]}`

## Run locally

```bash
pip install -r requirements.txt   # + torch CPU (see requirements.txt)
sh build.sh   # downloads Kronos-mini weights
python3 app.py  # -> http://127.0.0.1:8000
```

## Deploy (Render)

- Build command: `sh build.sh`
- Start command: `sh start.sh`
- Free tier sleeps after inactivity; first forecast after wake takes ~1 min.

## LLM upgrade path

`analysts.py` mirrors the TradingAgents agent graph. To swap the rule-based
analysts for real LLM debate, point the analysts at an OpenAI-compatible
endpoint (Ollama locally, or Groq's free tier) — no other changes needed.
