"""數據層：Binance 公開行情（K 線）＋ Hyperliquid（資金費率、持倉量）。

- 所有 K 線都只保留「已收盤」的 K 棒，避免把還在跑的那根拿來算訊號。
- 本地 CSV 快取，第二次之後只補最新的部分。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

BINANCE = "https://data-api.binance.vision/api/v3"
HL = "https://api.hyperliquid.xyz/info"

INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

# 穩定幣、法幣、黃金代幣等不是「幣種行情」的標的
EXCLUDE_BASES = {
    "USDC", "USD1", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "EURI", "AEUR",
    "XUSD", "USDE", "PYUSD", "RLUSD", "UST", "USTC", "PAXG", "XAUT", "BFUSD", "U",
    "GBP", "TRY", "BRL", "ARS", "JPY", "WBTC", "WBETH", "BNSOL",
}

_session = requests.Session()
_session.headers["User-Agent"] = "kk-compass2/1.0"


def _get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _post(payload, tries=4):
    for i in range(tries):
        try:
            r = _session.post(HL, json=payload, timeout=20)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(3 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


# ---------------------------------------------------------------- 幣種清單
def universe(top_n=100, min_price=0.0):
    """Binance USDT 現貨成交額前 N 名（扣除穩定幣、槓桿代幣）。"""
    rows = _get(f"{BINANCE}/ticker/24hr")
    out = []
    for x in rows:
        s = x["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in EXCLUDE_BASES or base.endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        qv = float(x["quoteVolume"])
        px = float(x["lastPrice"])
        if qv <= 0 or px <= min_price:
            continue
        out.append({"symbol": s, "base": base, "quote_volume": qv,
                    "last": px, "chg24h": float(x["priceChangePercent"])})
    out.sort(key=lambda r: -r["quote_volume"])
    return out[:top_n]


# ---------------------------------------------------------------- K 線
def _fetch_klines(symbol, interval, start_ms, end_ms=None):
    step = INTERVAL_MS[interval]
    rows = []
    cur = start_ms
    while True:
        params = {"symbol": symbol, "interval": interval, "startTime": cur, "limit": 1000}
        if end_ms:
            params["endTime"] = end_ms
        d = _get(f"{BINANCE}/klines", params)
        if not d:
            break
        rows.extend(d)
        last_open = d[-1][0]
        if len(d) < 1000:
            break
        cur = last_open + step
    if not rows:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "quote_volume"])
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "tb_base", "tb_quote", "ignore"])
    df = df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    return df


def klines(symbol, interval, days, cache_dir, now_ms=None):
    """回傳只含『已收盤』K 棒的 DataFrame，index = 收盤時間（UTC）。"""
    now_ms = now_ms or int(time.time() * 1000)
    step = INTERVAL_MS[interval]
    path = Path(cache_dir) / f"{symbol}_{interval}.csv"
    start_needed = now_ms - days * 86_400_000
    old = None
    if path.exists():
        try:
            old = pd.read_csv(path)
        except Exception:
            old = None
    if old is not None and len(old) and old["open_time"].iloc[0] <= start_needed + step:
        start = int(old["open_time"].iloc[-1])  # 重抓最後一根（可能當時未收盤）
        new = _fetch_klines(symbol, interval, start)
        df = pd.concat([old[old["open_time"] < start], new], ignore_index=True)
    else:
        df = _fetch_klines(symbol, interval, start_needed)
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(path, index=False)
    return finalize(df, interval, now_ms)


def finalize(df, interval, now_ms):
    step = INTERVAL_MS[interval]
    df = df[df["open_time"] + step <= now_ms].copy()  # 只留已收盤
    df["time"] = pd.to_datetime(df["open_time"] + step, unit="ms", utc=True)  # 收盤時間
    df = df.set_index("time")
    return df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]]


# ---------------------------------------------------------------- Hyperliquid
def hl_snapshot():
    """回傳 {幣名: {funding, oi_usd, mark, premium, day_volume}}；funding 為每小時費率。"""
    meta, ctx = _post({"type": "metaAndAssetCtxs"})
    out = {}
    for a, c in zip(meta["universe"], ctx):
        try:
            mark = float(c.get("markPx") or 0)
            out[a["name"]] = {
                "funding": float(c.get("funding") or 0),
                "oi_usd": float(c.get("openInterest") or 0) * mark,
                "mark": mark,
                "premium": float(c.get("premium") or 0),
                "day_volume": float(c.get("dayNtlVlm") or 0),
            }
        except (TypeError, ValueError):
            continue
    return out


def hl_name(base, snapshot):
    """Binance 幣名對到 Hyperliquid 幣名（例如 PEPE→kPEPE）。"""
    if base in snapshot:
        return base
    if "k" + base in snapshot:
        return "k" + base
    if base.startswith("1000") and "k" + base[4:] in snapshot:
        return "k" + base[4:]
    return None


def hl_funding_history(coin, days, cache_dir, now_ms=None):
    """每小時資金費率歷史（本地快取、增量更新）。"""
    now_ms = now_ms or int(time.time() * 1000)
    path = Path(cache_dir) / f"funding_{coin}.csv"
    start_needed = now_ms - days * 86_400_000
    old = None
    if path.exists():
        try:
            old = pd.read_csv(path)
        except Exception:
            old = None
    start = start_needed
    if old is not None and len(old) and old["time"].iloc[0] <= start_needed + 3_600_000:
        start = int(old["time"].iloc[-1]) + 1
    rows = []
    cur = start
    for _ in range(60):
        d = _post({"type": "fundingHistory", "coin": coin, "startTime": int(cur)})
        if not d:
            break
        rows.extend({"time": int(x["time"]), "rate": float(x["fundingRate"])} for x in d)
        if len(d) < 500:
            break
        cur = d[-1]["time"] + 1
        time.sleep(0.25)
    new = pd.DataFrame(rows, columns=["time", "rate"])
    df = new if old is None or start == start_needed else pd.concat([old, new])
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(path, index=False)
    s = pd.Series(df["rate"].values, index=pd.to_datetime(df["time"], unit="ms", utc=True))
    return s


def save_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
