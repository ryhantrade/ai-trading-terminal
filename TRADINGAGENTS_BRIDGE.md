# TradingAgents Bridge — upgrading the debate to real LLMs

The terminal's `/api/debate` endpoint currently runs TradingAgents-STRUCTURE with
rule-based SMC analysts (Trend / Liquidity / Kronos / Risk). This document
describes how to swap the rule-based analysts for real LLM analysts, matching
the TradingAgents architecture from the @ludoonchart video (REA + Kronos +
TradingAgents).

## Option A — Ollama (local, free)

Requires a machine with enough RAM (8GB+). The VM this project was built on
only had ~264MB free, so Ollama was not run there.

1. Install Ollama and pull a model: `ollama pull qwen2.5:7b` (or llama3.1:8b).
2. TradingAgents supports Ollama natively: in its `default_config` set
   `llm_provider: "ollama"` and `backend_url: "http://localhost:11434/v1"`.
3. Replace each rule-based analyst in `analysts.py` with a TradingAgents
   agent of the same role:
   - Trend Analyst -> `create_trend_analyst`
   - Liquidity Analyst -> `create_liquidity_analyst` (SMC: sweeps + displacement)
   - Kronos Analyst -> feed Kronos `p_up` / `exp_move` as the quantitative input
   - Risk Manager -> `create_risk_manager` (1% risk, SL/TP from ATR)
4. Keep the JSON contract unchanged (`signal`, `confidence`, `analysts`, `reasoning`)
   so `static/index.html` works without changes.

## Option B — Groq (cloud, free tier available)

1. Get a free API key from https://console.groq.com and set `GROQ_API_KEY`.
2. TradingAgents supports Groq via `llm_provider: "groq"` in `default_config`.
3. Same analyst mapping as Option A; calls go to Groq's hosted models
   (e.g. `llama-3.3-70b-versatile`).

## Notes

- Kronos (mini, 4.1M params) stays the quantitative engine either way —
  it runs on CPU in ~13s for 5 paths x 24 steps and is already integrated
  in `forecast_engine.py`.
- REA (the MCP-based research agent) was used as the UI/analysis methodology
  for this build; it is not a runtime dependency.
