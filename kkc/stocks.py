"""美股與商品觀察清單（Hyperliquid 股票／商品永續合約報價）。

重要：這些市場 2025 年底才上線，歷史不到一年，加密貨幣那套回測證據不適用，
所以這裡只做「狀態描述」：日線方向分數、長期趨勢（200 日均線）、結構觸發價位。
不給進場建議，信件與報告都會標示「未經回測驗證」。
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

from . import signals as sg

HL = "https://api.hyperliquid.xyz/info"

DEFAULT_WATCH = [
    ["QQQ（那斯達克 100）", "xyz:XYZ100"],
    ["MSTR", "xyz:MSTR"],
    ["閃迪 SNDK", "xyz:SNDK"],
    ["美光 MU", "xyz:MU"],
    ["台積電 TSM", "xyz:TSM"],
    ["輝達 NVDA", "xyz:NVDA"],
    ["PLTR", "xyz:PLTR"],
    ["黃金", "xyz:GOLD"],
    ["白銀", "xyz:SILVER"],
    ["原油 WTI", "xyz:CL"],
]
STEP = {"1d": 86_400_000, "4h": 14_400_000}


def candles(coin, interval, days, tries=5):
    now = int(time.time() * 1000)
    d = None
    for i in range(tries):
        try:
            r = requests.post(HL, json={"type": "candleSnapshot", "req": {
                "coin": coin, "interval": interval, "startTime": now - days * 86_400_000, "endTime": now}}, timeout=30)
            d = r.json() if r.ok else None
        except (requests.RequestException, ValueError):
            d = None
        if d:
            break
        time.sleep(2 + 2 * i)  # 被限速時等一下再試
    if not d:
        return None
    df = pd.DataFrame(d)
    out = pd.DataFrame({"open_time": df["t"].astype("int64"), "open": df["o"].astype(float),
                        "high": df["h"].astype(float), "low": df["l"].astype(float),
                        "close": df["c"].astype(float), "volume": df["v"].astype(float)})
    out["quote_volume"] = out["volume"] * out["close"]
    out = out[out["open_time"] + STEP[interval] <= now]  # 只留已收盤
    out.index = pd.to_datetime(out["open_time"] + STEP[interval], unit="ms", utc=True)
    return out


def _levels(df, ph, pl, k=3):
    from .build import current_levels
    return current_levels(df, ph, pl, k, "%m-%d")


def analyze_one(name, coin):
    d = candles(coin, "1d", 900)
    time.sleep(1.2)
    h4 = candles(coin, "4h", 120)
    time.sleep(1.2)
    if d is None or len(d) < 60:
        return dict(name=name, coin=coin, error="抓不到資料")
    D = sg.daily_features(d)
    last = D.iloc[-1]
    px = float(h4["close"].iloc[-1]) if h4 is not None and len(h4) else float(d["close"].iloc[-1])
    rawd, phd, pld = sg.h4_setups(D, 3)
    lvd = _levels(D, phd, pld)
    recent = None
    if rawd and rawd[-1]["t"] >= len(D) - 3:
        s = rawd[-1]
        recent = dict(dir=s["dir"], date=D.index[s["t"]].tz_convert("Asia/Taipei").strftime("%m-%d"),
                      close=float(D["close"].iloc[s["t"]]), hold=float(s["swing"]),
                      risk_pct=abs(float(D["close"].iloc[s["t"]]) - float(s["swing"])) / float(D["close"].iloc[s["t"]]) * 100)
    lv4 = {}
    if h4 is not None and len(h4) > 60:
        H = sg.h4_features(h4)
        _, ph, pl = sg.h4_setups(H, 3)
        lv4 = _levels(H, ph, pl)
    score = float(last["score"]) if np.isfinite(last["score"]) else None
    ema200 = float(last["ema200"]) if np.isfinite(last["ema200"]) else None
    c = d["close"]
    return dict(
        name=name, coin=coin, price=px, bars=len(d), score=score, label=sg.score_label(score) if score is not None else "資料不足",
        above200=(px > ema200) if ema200 else None, ema200=ema200,
        chg1=(px / float(c.iloc[-2]) - 1) * 100 if len(c) > 2 else None,
        chg7=(px / float(c.iloc[-8]) - 1) * 100 if len(c) > 8 else None,
        chg30=(px / float(c.iloc[-31]) - 1) * 100 if len(c) > 31 else None,
        from_high=(px / float(d["high"].max()) - 1) * 100, atr_pct=float(last["atr_pct"]), rsi=float(last["rsi"]),
        recent=recent, levels_d=lvd, levels_4h=lv4)


def describe(x):
    """一句話狀態描述（不是建議）。"""
    if x.get("error"):
        return x["error"]
    parts = []
    if x["score"] is not None:
        parts.append(f"日線{x['label']}（{x['score']:+.0f}）")
    if x["above200"] is not None:
        parts.append("在 200 日均線之上" if x["above200"] else "在 200 日均線之下")
    if x["recent"]:
        r = x["recent"]
        parts.append(f"{r['date']} 日線確認{'做多' if r['dir'] == 1 else '做空'}結構，"
                     f"{'不可破' if r['dir'] == 1 else '不可過'} {r['hold']:,.2f}（距 {r['risk_pct']:.1f}%）")
    else:
        w = []
        for side, d in (("long", 1), ("short", -1)):
            lv = x["levels_d"].get(side)
            if lv and not lv["already"]:
                dist = (lv["trigger"] / x["price"] - 1) * 100
                w.append(f"收盤{'站上' if d == 1 else '跌破'} {lv['trigger']:,.2f} 轉{'多' if d == 1 else '空'}（{dist:+.1f}%）")
        parts.append("等待：" + "；".join(w) if w else "日線沒有成形的結構")
    return "，".join(parts)


def analyze_all(watch=None, log=print):
    out = []
    for name, coin in (watch or DEFAULT_WATCH):
        try:
            x = analyze_one(name, coin)
        except Exception as e:  # noqa — 單一標的失敗不影響其他
            x = dict(name=name, coin=coin, error=f"分析失敗：{e}")
        x["desc"] = describe(x)
        out.append(x)
    return out
