#!/usr/bin/env python3
"""Live market data: CoinGecko full-market activity scan + Kraken OHLCV.

All calls are stdlib-only (urllib). Results are cached in-memory with TTLs.
"""
import json
import math
import time
import urllib.request

CG_API = "https://api.coingecko.com/api/v3/coins/markets"
KRAKEN_OHLC = "https://api.kraken.com/0/public/OHLC"
KRAKEN_PAIRS = "https://api.kraken.com/0/public/AssetPairs"

_cache = {}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-terminal/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cached(key, ttl, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def _zscores(vals):
    n = len(vals)
    if n < 2:
        return [0.0] * n
    mu = sum(vals) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / n) or 1.0
    return [(v - mu) / sd for v in vals]


# ---------------------------------------------------------------- activity
def activity_scan(top=30, min_mcap=10_000_000):
    """Rank the full market by activity (volume/mcap + volatility)."""
    def _fetch():
        coins = []
        for page in (1, 2):
            params = ("vs_currency=usd&order=market_cap_desc&per_page=250&page=%d"
                      "&sparkline=false&price_change_percentage=1h,24h" % page)
            try:
                coins.extend(_get(CG_API + "?" + params))
            except Exception:
                break
            time.sleep(4)
        rows = []
        for c in coins:
            try:
                mcap = float(c.get("market_cap") or 0)
                vol = float(c.get("total_volume") or 0)
                if mcap < min_mcap or vol <= 0:
                    continue
                rows.append({
                    "symbol": (c.get("symbol") or "").upper(),
                    "name": c.get("name"),
                    "price": c.get("current_price"),
                    "mcap": mcap,
                    "vol24h": vol,
                    "vol_mcap": vol / mcap,
                    "pct_1h": float(c.get("price_change_percentage_1h_in_currency") or 0),
                    "pct_24h": float(c.get("price_change_percentage_24h_in_currency") or 0),
                })
            except (TypeError, ValueError):
                continue
        zv = _zscores([r["vol_mcap"] for r in rows])
        z24 = _zscores([abs(r["pct_24h"]) for r in rows])
        z1 = _zscores([abs(r["pct_1h"]) for r in rows])
        for r, a, b, cc in zip(rows, zv, z24, z1):
            r["activity"] = round(a + b + 0.5 * cc, 2)
        rows.sort(key=lambda r: r["activity"], reverse=True)
        # de-dupe symbols, keep best
        seen, out = set(), []
        for r in rows:
            if r["symbol"] in seen:
                continue
            seen.add(r["symbol"])
            out.append(r)
        return {"scanned_at": time.time(), "universe": len(rows), "coins": out}
    return _cached("activity", 300, _fetch)


# ---------------------------------------------------------------- Kraken OHLC
_PAIRS = None

def _kraken_pairs():
    global _PAIRS
    if _PAIRS is None:
        d = _get(KRAKEN_PAIRS)
        _PAIRS = d.get("result", {})
    return _PAIRS


def resolve_pair(symbol):
    """Map 'BTC' -> Kraken pair key like 'XXBTZUSD'."""
    sym = symbol.upper()
    pairs = _kraken_pairs()
    # direct: <SYM>USD
    for key, meta in pairs.items():
        base = meta.get("base", "")
        quote = meta.get("quote", "")
        alt = meta.get("altname", "")
        if quote == "ZUSD" and (alt.upper() == sym + "USD" or base.upper().rstrip("XZ") == sym or alt.upper().rstrip("USD") == sym):
            return key
    # fallback: any USD quote containing the symbol
    for key, meta in pairs.items():
        if meta.get("quote") == "ZUSD" and sym in meta.get("altname", "").upper():
            return key
    return None


def ohlc(symbol, interval=60):
    """Hourly (or other interval) OHLCV from Kraken. Returns list of dicts."""
    def _fetch():
        pair = resolve_pair(symbol)
        if not pair:
            return {"error": "pair not on Kraken", "symbol": symbol}
        d = _get(f"{KRAKEN_OHLC}?pair={pair}&interval={interval}")
        if d.get("error"):
            return {"error": ";".join(d["error"]), "symbol": symbol}
        key = next(k for k in d["result"] if k != "last")
        rows = []
        for r in d["result"][key]:
            rows.append({
                "t": int(r[0]),
                "o": float(r[1]), "h": float(r[2]),
                "l": float(r[3]), "c": float(r[4]),
                "v": float(r[6]),
            })
        return {"symbol": symbol.upper(), "pair": pair, "interval": interval,
                "candles": rows}
    return _cached(f"ohlc:{symbol}:{interval}", 300, _fetch)
