"""大盤雷達：美股期貨、三大指數、費半、VIX、10 年期殖利率、美元指數、台股加權（Yahoo Finance）。

只是資訊，不是訊號；但其中兩項有回測支持、會影響我們的美股策略：
- 費半在 200 日均線之下時，新高突破（S2）20 年前後兩段都為負 → 不做 S2。
- VIX 越高，多頭回檔（S1）越好（VIX ≥ 25 約 +0.11～0.14R；< 15 約 +0.01～0.03R）。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import numpy as np
import requests

TW = timezone(timedelta(hours=8))
ITEMS = [  # (代號, 名稱, 類別)
    ("NQ=F", "Nasdaq 100 期貨", "fut"), ("ES=F", "S&P 500 期貨", "fut"), ("YM=F", "道瓊期貨", "fut"),
    ("^IXIC", "Nasdaq 綜合", "idx"), ("^GSPC", "S&P 500", "idx"), ("^DJI", "道瓊", "idx"),
    ("^SOX", "費城半導體", "sox"), ("^VIX", "VIX 恐慌指數", "vix"), ("^TNX", "美 10 年期殖利率", "tnx"),
    ("DX-Y.NYB", "美元指數 DXY", "dxy"), ("CL=F", "WTI 原油", "cmd"), ("BZ=F", "布蘭特原油", "cmd"),
    ("GC=F", "黃金", "cmd"), ("^TWII", "台股加權", "idx"),
]
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 (KK Compass 2)"


def _get(sym):
    for i in range(3):
        try:
            r = _s.get(f"https://query{1 + i % 2}.finance.yahoo.com/v8/finance/chart/{sym}",
                       params={"interval": "1d", "range": "1y"}, timeout=20)
            if r.ok:
                return r.json()["chart"]["result"][0]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            pass
    return None


def _streak(c):
    d = np.sign(np.diff(c))
    n = 0
    for x in d[::-1]:
        if x == 0 or (n and np.sign(n) != x):
            break
        n += int(x)
    return n


def radar(log=print):
    out = []
    for sym, name, kind in ITEMS:
        res = _get(sym)
        if not res:
            out.append(dict(sym=sym, name=name, kind=kind, error=True))
            continue
        m = res["meta"]
        ts = res.get("timestamp") or []
        cl = res["indicators"]["quote"][0]["close"]
        pairs = [(t, c) for t, c in zip(ts, cl) if c is not None]
        if len(pairs) < 3:
            out.append(dict(sym=sym, name=name, kind=kind, error=True))
            continue
        price = float(m.get("regularMarketPrice") or pairs[-1][1])
        rt = m.get("regularMarketTime") or pairs[-1][0]
        tz = timezone(timedelta(seconds=m.get("gmtoffset", 0)))
        same_day = datetime.fromtimestamp(pairs[-1][0], tz).date() == datetime.fromtimestamp(rt, tz).date()
        closes = np.array([c for _, c in pairs], float)
        prev = closes[-2] if same_day else closes[-1]
        done = closes if same_day else np.append(closes, price)  # 含最新價
        x = dict(sym=sym, name=name, kind=kind, price=price, chg=(price / prev - 1) * 100,
                 time=datetime.fromtimestamp(rt, TW).strftime("%m-%d %H:%M"))
        if kind == "tnx":
            x["chg_bp"] = (price - prev) * 100
            x["chg20_bp"] = (price - done[-21]) * 100 if len(done) > 21 else None
        if kind == "sox":
            x["streak"] = _streak(done)
            sma200 = done[-200:].mean() if len(done) >= 200 else None
            x["vs200"] = (price / sma200 - 1) * 100 if sma200 else None
        out.append(x)
    return out


def get(items, sym):
    return next((x for x in items if x["sym"] == sym and not x.get("error")), None)


def strategy_notes(items):
    """大盤狀態對我們策略的影響（只用有回測支持的兩項）。"""
    notes = []
    sox, vix = get(items, "^SOX"), get(items, "^VIX")
    if sox and sox.get("vs200") is not None:
        if sox["vs200"] < 0:
            notes.append(f"費半在 200 日均線之下（{sox['vs200']:+.1f}%）：新高突破訊號暫停（回測這時平均虧損）。")
        else:
            notes.append(f"費半在 200 日均線之上（{sox['vs200']:+.1f}%）：新高突破訊號照常。")
    if vix:
        v = vix["price"]
        lvl = ("恐慌偏高，歷史上多頭回檔訊號最好（約 +0.11～0.14R）" if v >= 25 else
               "中等，多頭回檔訊號約 +0.05R" if v >= 20 else
               "偏低，多頭回檔訊號優勢很小（約 0～0.07R）" if v >= 15 else
               "很低，多頭回檔訊號幾乎沒有優勢（約 +0.01～0.03R）")
        notes.append(f"VIX {v:.1f}：{lvl}。")
    return notes
