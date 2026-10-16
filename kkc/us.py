"""美股策略（日線）。規則事先定好，回測與每日掃描共用同一份程式。

S1 多頭回檔：收盤 > SMA200 且 RSI(2) < 10 → 隔日開盤買；收盤站上 SMA5 出場；停損 2.5×ATR；最長 10 天。
S2 新高突破：收盤創 252 日新高（前一日不是）、量比 ≥ 1.5、收盤 > SMA200 → 隔日開盤買；
            收盤跌破 EMA20 出場；停損 2×ATR；最長 60 天。
S3 趨勢持有：日線方向分數由 < 4 轉為 ≥ 4 且收盤 > EMA50 → 隔日開盤買；收盤跌破 EMA50 出場；
            停損 3×ATR；最長 120 天。
全部只做多（20 年回測顯示美股做空長期虧損）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest as bt
from . import indicators as ti
from . import signals as sg

STRATS = {
    "S1": dict(name="多頭回檔", exit="revert", line="sma5", stop_atr=2.5, max_hold=10,
               desc="長期多頭（站上 200 日均線）裡的短線急跌，賭反彈"),
    "S2": dict(name="新高突破", exit="trail", line="ema20", stop_atr=2.0, max_hold=60,
               desc="收盤創一年新高且放量，跟著 EMA20 抱"),
    "S3": dict(name="趨勢持有", exit="trail50", line="ema50", stop_atr=3.0, max_hold=120,
               desc="日線方向轉強（≥ +4），抱到跌破 EMA50"),
}


def features(d: pd.DataFrame) -> pd.DataFrame:
    D = sg.daily_features(d)
    c = D["close"]
    D["sma5"] = ti.sma(c, 5)
    D["sma200"] = ti.sma(c, 200)
    D["rsi2"] = ti.rsi(c, 2)
    D["hi252c"] = c.rolling(252, min_periods=200).max()
    D["s1"] = (c > D["sma200"]) & (D["rsi2"] < 10)
    newhi = (c >= D["hi252c"]) & (c.shift(1) < D["hi252c"].shift(1))
    D["s2"] = newhi & (D["vol_ratio"] >= 1.5) & (c > D["sma200"])
    D["s3"] = (D["score"] >= 4) & (D["score"].shift(1) < 4) & (c > D["ema50"])
    return D


def signals(D, key):
    """回傳訊號列表（i, time, close, stop）。"""
    st = STRATS[key]
    col = {"S1": "s1", "S2": "s2", "S3": "s3"}[key]
    out = []
    idx = np.where(D[col].fillna(False).values)[0]
    for i in idx:
        atr = D["atr"].iloc[i]
        if not np.isfinite(atr):
            continue
        cl = float(D["close"].iloc[i])
        out.append(dict(i=int(i), time=D.index[i], close=cl, stop=cl - st["stop_atr"] * float(atr), atr=float(atr)))
    return out


def run(sym, D, key):
    """一檔股票一個策略的回測交易（同策略持倉中不重複進場）。"""
    st = STRATS[key]
    om = D["open_time"].values.astype("int64")
    o, h, l, c = (D[x].values for x in ("open", "high", "low", "close"))
    line = D[st["line"]].values
    rows, busy = [], -1
    for s in signals(D, key):
        start = int(s["time"].value // 1_000_000)
        if start <= busy:
            continue
        res = bt.simulate(om, o, h, l, c, start, 1, s["stop"], st["exit"], line, st["max_hold"], 24, next_open=True)
        if res is None:
            continue
        busy = res["exit_time"]
        rows.append(dict(coin=sym, strat=key, signal_time=s["time"], dir=1, i=s["i"],
                         score=float(D["score"].iloc[s["i"]]) if np.isfinite(D["score"].iloc[s["i"]]) else np.nan,
                         stop_atr=st["stop_atr"], **res))
    return rows


def plan(sym, D, s, key, risk_per_trade):
    st = STRATS[key]
    e = s["close"]
    risk_pct = (e - s["stop"]) / e * 100
    tp = {"revert": "哪天收盤站上 5 日均線，隔天開盤賣（信會提醒）；最長 10 個交易日",
          "trail": "哪天收盤跌破 20 日 EMA，隔天開盤賣（信會提醒）；最長 60 個交易日",
          "trail50": "哪天收盤跌破 50 日 EMA，隔天開盤賣（信會提醒）；最長 120 個交易日"}[st["exit"]]
    return dict(symbol=sym, strat=key, strat_name=st["name"], date=s["time"].tz_convert("America/New_York").strftime("%m-%d"),
                entry=e, stop=s["stop"], risk_pct=risk_pct, tp_text=tp,
                position_x=(risk_per_trade / risk_pct) if risk_pct > 0 else None, risk_per_trade=risk_per_trade,
                ext=float(D["close"].iloc[s["i"]] / D["sma200"].iloc[s["i"]] - 1))


def _walk(D, key, x):
    """假設訊號隔天開盤買進，走到最新收盤。回傳 (出場判定的 K 棒 j 或 None, 原因)。"""
    st = STRATS[key]
    low, c, line = D["low"].values, D["close"].values, D[st["line"]].values
    for j in range(x["i"] + 1, len(D)):
        if low[j] <= x["stop"]:
            return j, "stopped"
        if ((c[j] > line[j]) if st["exit"] == "revert" else (c[j] < line[j])):
            return j, "sell"
        if j - x["i"] >= st["max_hold"]:
            return j, "time"
    return None, "hold"


def picks(D_by_sym, key, since):
    """從 since（UTC 時間）起，照策略規則會進場的訊號：同一檔持倉中不重複進場；
    同一天觸發太多時依「離 200 日均線最遠」挑前 PICK_N 檔。回傳 [(sym, x, 出場 j, 原因)]。"""
    cand = []
    for sym, D in D_by_sym.items():
        busy = -1
        for x in signals(D, key):
            if D.index[x["i"]] < since or x["i"] <= busy:
                continue
            j, why = _walk(D, key, x)
            busy = j if j is not None else len(D)
            cand.append((D.index[x["i"]], -float(D["close"].iloc[x["i"]] / D["sma200"].iloc[x["i"]]), sym, x, j, why))
    cand.sort(key=lambda r: (r[0], r[1]))
    out, cnt = [], {}
    for day, _, sym, x, j, why in cand:
        cnt[day] = cnt.get(day, 0) + 1
        if cnt[day] <= PICK_N[key]:
            out.append((sym, x, j, why))
    return out


# ====================================================================== 每日掃描
UNIVERSE = ["QQQ", "SPY", "MSTR", "MU", "TSM", "NVDA", "PLTR", "SNDK", "AAPL", "MSFT", "AMZN", "GOOGL", "META",
            "TSLA", "AMD", "AVGO", "NFLX", "ADBE", "CRM", "ORCL", "INTC", "QCOM", "TXN", "AMAT", "LRCX", "KLAC",
            "ASML", "COIN", "SHOP", "UBER", "NOW", "PANW", "MRVL", "WDC", "SMCI", "ARM"]
LIVE = ["S2", "S1"]          # 通過驗證、會給進場計畫的策略（S3 與隨機一樣，不給）
RISK = {"S2": 0.5, "S1": 0.25}  # 每筆虧損占本金 %，依回測最大回撤換算（目標約 20%）
RANDOM_REF = {"S2": dict(all=0.106, oos=0.238), "S1": dict(all=-0.013, oos=0.014)}  # 隨機對照（同條件、隔日開盤出場）
PICK_N = {"S1": 3, "S2": 5}  # 同一天觸發太多時只挑前幾檔：依「離 200 日均線最遠」（長期趨勢最強）排序，回測較佳


def scan(cfg=None, log=print, universe=None):
    """美股區：QQQ 大盤、通過驗證策略的最新訊號（上一個美股交易日收盤）、回測統計。"""
    from . import yahoo
    cfg = cfg or {}
    feats, fail = {}, []
    for sym in (universe or UNIVERSE):
        try:
            d = yahoo.daily(sym)
            if d is None or len(d) < 260:
                fail.append(sym)
                continue
            feats[sym] = features(d)
        except Exception:  # noqa
            fail.append(sym)
    if "QQQ" not in feats:
        return dict(error="抓不到 QQQ 數據（Yahoo Finance）", fail=fail)
    q = feats["QQQ"].iloc[-1]
    last_day = feats["QQQ"].index[-1]
    # 回測統計（全部股票、20 年，前 70% 樣本內、後 30% 樣本外）
    rows = []
    for sym, D in feats.items():
        for key in LIVE:
            rows += run(sym, D, key)
    T = pd.DataFrame(rows)
    stats = {}
    if len(T):
        cut = T["signal_time"].quantile(0.7)
        for key in LIVE:
            t = T[T["strat"] == key]
            ins, oos = bt.split_time(t, cut)
            stats[key] = dict(all=bt.stats(t), oos=bt.stats(oos), random=RANDOM_REF[key])
    sigs, holds = [], []
    live = {s: D for s, D in feats.items() if D.index[-1] == last_day}  # 排除停牌或資料落後
    since = pd.Timestamp((cfg or {}).get("us_track_from", "2026-10-14"), tz="UTC")
    line_name = {"sma5": "5 日均線", "ema20": "20 日 EMA", "ema50": "50 日 EMA"}
    for key in LIVE:
        chosen = set()
        for sym, x, j, why in picks(live, key, since):
            D = live[sym]
            last = len(D) - 1
            if x["i"] == last:   # 昨天收盤的新訊號：今晚買
                p = plan(sym, D, x, key, RISK[key])
                p.update(hist=stats.get(key, {}).get("all"), hist_oos=stats.get(key, {}).get("oos"), pick=True,
                         score=float(D["score"].iloc[-1]) if np.isfinite(D["score"].iloc[-1]) else None)
                sigs.append(p)
                chosen.add(sym)
                continue
            if j is not None and j < last:
                continue   # 之前就出場了
            h = dict(symbol=sym, strat=key, strat_name=STRATS[key]["name"], stop=x["stop"], close=float(D["close"].iloc[-1]),
                     date=x["time"].tz_convert("America/New_York").strftime("%m-%d"), held=last - x["i"],
                     line=float(D[STRATS[key]["line"]].iloc[-1]), line_name=line_name[STRATS[key]["line"]])
            h["state"] = {"stopped": "stopped", "sell": "sell", "time": "sell", "hold": "hold"}[why]
            h["why"] = {"sell": f"收盤{'站上' if key == 'S1' else '跌破'}{h['line_name']}", "time": "持有天數到上限"}.get(why, "")
            holds.append(h)
        chosen |= {h['symbol'] for h in holds if h['strat'] == key}   # 已持有的不再列入「不建議再買」
        for sym, D in live.items():   # 有觸發但沒被挑中的，列出但不建議
            if sym not in chosen and bool(D[{"S1": "s1", "S2": "s2"}[key]].iloc[-1]):
                s = [x for x in signals(D, key) if x["i"] == len(D) - 1]
                if s:
                    p = plan(sym, D, s[0], key, RISK[key])
                    p["pick"] = False
                    sigs.append(p)
    sigs.sort(key=lambda p: (LIVE.index(p["strat"]), not p["pick"], -p["ext"]))
    holds.sort(key=lambda h: ({"sell": 0, "stopped": 1, "hold": 2}[h["state"]], h["symbol"]))
    return dict(date=last_day.tz_convert("America/New_York").strftime("%Y-%m-%d"),
                qqq=dict(price=float(q["close"]), sma200=float(q["sma200"]), score=float(q["score"]),
                         label=sg.score_label(q["score"]), up=bool(q["close"] > q["sma200"])),
                signals=sigs, holds=holds, stats=stats, n=len(feats), fail=fail)
