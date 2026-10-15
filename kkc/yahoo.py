"""Yahoo Finance 日線（美股、ETF、商品期貨）。只用於長期回測與日線分析。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://query{n}.finance.yahoo.com/v8/finance/chart/{sym}"
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 (KK Compass 2)"


def daily(sym, start="2005-01-01", cache_dir=None, max_age_h=12):
    """回傳日線 DataFrame（index＝收盤時間 UTC，欄位同加密貨幣），已排除今天未收盤那根。"""
    path = Path(cache_dir) / f"yf_{sym.replace('=', '_').replace('^', '_')}.csv" if cache_dir else None
    if path and path.exists() and (time.time() - path.stat().st_mtime) < max_age_h * 3600:
        df = pd.read_csv(path, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True)
        df["open_time"] = (df.index - pd.Timedelta(days=1)).as_unit("ms").asi8
        return df
    p1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    p2 = int(time.time())
    js = None
    for i in range(6):
        try:
            r = _s.get(URL.format(n=1 + i % 2, sym=sym),
                       params={"period1": p1, "period2": p2, "interval": "1d", "events": "split"}, timeout=30)
            if r.status_code == 429:
                time.sleep(3 + 3 * i)
                continue
            r.raise_for_status()
            js = r.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(2 + 2 * i)
    if not js or not js.get("chart", {}).get("result"):
        return None
    res = js["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    meta = res.get("meta", {})
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                       "volume": q["volume"]}, index=pd.to_datetime(ts, unit="s", utc=True))
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["high"] > 0) & (df["low"] > 0)]
    # 以交易日當天收盤時間（約 UTC 20:00～21:00）當 index；今天若尚未收盤則丟掉最後一根
    df.index = df.index.normalize() + pd.Timedelta(hours=21)
    df = df[~df.index.duplicated(keep="last")]
    if len(df) and df.index[-1] > pd.Timestamp.now(tz="UTC"):
        df = df.iloc[:-1]
    df["volume"] = df["volume"].fillna(0)
    df["quote_volume"] = df["volume"] * df["close"]
    df["open_time"] = (df.index - pd.Timedelta(days=1)).as_unit("ms").asi8  # 毫秒
    df = df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]]
    df.attrs["currency"] = meta.get("currency")
    if path:
        os.makedirs(path.parent, exist_ok=True)
        df.to_csv(path)
    return df
