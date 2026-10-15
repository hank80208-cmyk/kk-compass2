"""回測引擎（短線 4H 與波段日線共用）。

設計原則：
1. 訊號確認後，用更細一級的 K 棒逐根撮合（短線用 1H、波段用日線）。
   同一根同時碰到停損與目標，一律算停損（保守）。
2. 計入手續費、滑價、資金費率。
3. 樣本內（前 70% 時間）挑方案，樣本外（後 30%）驗證；報告以樣本外為準。
4. 隨機進場對照組：同幣種、同方向、同停損幅度、同出場方式，在同樣的 BTC 大盤條件下隨機時間進場。
"""
from __future__ import annotations

import itertools
import zlib

import numpy as np
import pandas as pd

COST = dict(taker=0.00055, maker=0.0002, slip=0.0002, funding_per_hour=0.0000125)

# 出場方式
EXITS = {
    "fixed2": dict(kind="fixed", r=2.0, name="固定 2R 止盈"),
    "fixed3": dict(kind="fixed", r=3.0, name="固定 3R 止盈"),
    "scale": dict(kind="scale", r1=2.0, r2=4.0, name="2R 先平一半、停損移到成本、剩下 4R"),
    "trail": dict(kind="trail", name="跟著 EMA20 移動出場（收盤跌破/站上 EMA20 出場）"),
    # 美股用
    "revert": dict(kind="revert", name="反彈收盤站上 5 日均線出場"),
    "trail50": dict(kind="trail", name="收盤跌破 EMA50 出場"),
}

TF = {
    "4h": dict(name="短線", exec_tf="1h", hours_per_bar=1, max_hold=168,
               stops=["pullback", "struct"], exits=["fixed2", "fixed3", "scale", "trail"]),
    "1d": dict(name="波段", exec_tf="1d", hours_per_bar=24, max_hold=60,
               stops=["pullback", "struct"], exits=["fixed2", "fixed3", "scale", "trail"]),
}


def variants(tf):
    return [dict(stop=s, exit=x) for s, x in itertools.product(TF[tf]["stops"], TF[tf]["exits"])]


def variant_name(v):
    s = {"struct": "停損放結構點", "pullback": "停損放回檔點"}[v["stop"]]
    return f"{s}／{EXITS[v['exit']]['name']}"


def simulate(om, o, h, l, c, start_ms, d, stop, exit_key, trail=None, max_hold=168,
             hours_per_bar=1, cost=COST):
    """從 start_ms 之後第一根 K 棒開盤市價進場。回傳 dict 或 None。"""
    i0 = int(np.searchsorted(om, start_ms, side="left"))
    n = len(o)
    if i0 >= n:
        return None
    entry = o[i0] * (1 + d * cost["slip"])
    risk = (entry - stop) * d
    if not np.isfinite(risk) or risk <= 0:
        return None
    ex = EXITS[exit_key]
    end = i0 + max_hold
    if end > n:  # 資料不夠走完持有期
        return None
    pos = 1.0
    pnl = 0.0          # 以進場價為分母的報酬（不含進場手續費）
    fees = cost["taker"]
    cur_stop = stop
    reason, j = None, i0
    t1_done = False
    for j in range(i0, end):
        hit_stop = (l[j] <= cur_stop) if d == 1 else (h[j] >= cur_stop)
        if hit_stop:
            gap = (o[j] < cur_stop) if d == 1 else (o[j] > cur_stop)
            px = (o[j] if (gap and j > i0) else cur_stop) * (1 - d * cost["slip"])
            pnl += pos * (px - entry) / entry * d
            fees += pos * cost["taker"]
            pos = 0
            reason = "保本出場" if t1_done else "停損"
            break
        if ex["kind"] == "fixed":
            tgt = entry + d * ex["r"] * risk
            if (h[j] >= tgt) if d == 1 else (l[j] <= tgt):
                pnl += pos * (tgt - entry) / entry * d
                fees += pos * cost["maker"]
                pos, reason = 0, "目標"
                break
        elif ex["kind"] == "scale":
            if not t1_done:
                t1 = entry + d * ex["r1"] * risk
                if (h[j] >= t1) if d == 1 else (l[j] <= t1):
                    pnl += 0.5 * (t1 - entry) / entry * d
                    fees += 0.5 * cost["maker"]
                    pos, t1_done, cur_stop = 0.5, True, entry
                    continue  # 同一根不再判斷第二目標（保守）
            else:
                t2 = entry + d * ex["r2"] * risk
                if (h[j] >= t2) if d == 1 else (l[j] <= t2):
                    pnl += pos * (t2 - entry) / entry * d
                    fees += pos * cost["maker"]
                    pos, reason = 0, "目標"
                    break
        elif ex["kind"] == "revert" and trail is not None:
            tv = trail[j]
            if np.isfinite(tv) and ((c[j] > tv) if d == 1 else (c[j] < tv)):
                px = c[j] * (1 - d * cost["slip"])
                pnl += pos * (px - entry) / entry * d
                fees += pos * cost["taker"]
                pos, reason = 0, "目標"
                break
        elif ex["kind"] == "trail" and trail is not None and j > i0:
            tv = trail[j]
            if np.isfinite(tv) and ((c[j] < tv) if d == 1 else (c[j] > tv)):
                px = c[j] * (1 - d * cost["slip"])
                pnl += pos * (px - entry) / entry * d
                fees += pos * cost["taker"]
                pos, reason = 0, "移動出場"
                break
    if pos > 0:  # 時間到，市價出場
        px = c[j] * (1 - d * cost["slip"])
        pnl += pos * (px - entry) / entry * d
        fees += pos * cost["taker"]
        reason = "時間出場"
    bars = j - i0 + 1
    fund = -d * cost["funding_per_hour"] * bars * hours_per_bar
    net = pnl - fees + fund
    risk_pct = risk / entry
    return dict(entry_px=entry, reason=reason, hours=bars * hours_per_bar, ret=net,
                r=net / risk_pct, risk_pct=risk_pct, entry_time=int(om[i0]), exit_time=int(om[j]))


FEATURES = ["score", "btc_score", "btc_bull", "stop_atr", "vol_ratio4", "close_pos4", "atr_pct4",
            "struct_risk_pct", "pull_risk_pct"]


def run_setups(coin, setups, ex_df, tf, cfg=None):
    """一個幣、一個週期的所有訊號 × 所有方案。同方向持倉期間不重複進場。"""
    spec = TF[tf]
    om = ex_df["open_time"].values.astype("int64")
    o, h, l, c = (ex_df[x].values for x in ("open", "high", "low", "close"))
    trail = ex_df["trail"].values if "trail" in ex_df else None
    rows = []
    for vi, v in enumerate(variants(tf)):
        busy = {1: -1, -1: -1}
        for s in setups:
            start_ms = int(s["time"].value // 1_000_000)
            if start_ms < om[0] or start_ms <= busy[s["dir"]]:
                continue
            stop = s["stop_struct"] if v["stop"] == "struct" else s["stop_pull"]
            res = simulate(om, o, h, l, c, start_ms, s["dir"], stop, v["exit"], trail,
                           spec["max_hold"], spec["hours_per_bar"])
            if res is None:
                continue
            busy[s["dir"]] = res["exit_time"]
            rows.append(dict(coin=coin, tf=tf, variant=vi, dir=s["dir"], grade=s["grade"],
                             grade_v1=s.get("grade_v1"), trend_rel=s["trend_rel"], signal_time=s["time"],
                             **{k: s.get(k) for k in FEATURES}, **res))
    return rows


def run_random_control(trades, ex_dfs, btc_score, tf, v, cutoff, n_rep=3):
    """同大盤條件的隨機對照：BTC 分數同方向且強度相近的日子裡，隨機挑時間進場。"""
    spec = TF[tf]
    rows = []
    for coin, g in trades.groupby("coin"):
        ex = ex_dfs.get(coin)
        if ex is None:
            continue
        om = ex["open_time"].values.astype("int64")
        o, h, l, c = (ex[x].values for x in ("open", "high", "low", "close"))
        trail = ex["trail"].values if "trail" in ex else None
        lo_t = pd.Timestamp(om[0], unit="ms", tz="UTC")
        hi_t = pd.Timestamp(om[-1] - (spec["max_hold"] + 2) * spec["hours_per_bar"] * 3_600_000, unit="ms", tz="UTC")
        for k in range(n_rep):
            rng = np.random.default_rng(zlib.crc32(f"{coin}{tf}".encode()) + 101 * k)
            for _, r in g.iterrows():
                lvl = r["btc_score"] if np.isfinite(r["btc_score"]) else 0
                if lvl == 0:
                    days = btc_score[btc_score.abs() <= 1]
                else:
                    days = btc_score[(np.sign(btc_score) == np.sign(lvl)) & (btc_score.abs() >= abs(lvl) - 1)
                                     & (btc_score.abs() <= abs(lvl) + 1)]
                days = days[(days.index > lo_t) & (days.index < hi_t)]
                days = days[days.index < cutoff] if r["signal_time"] < cutoff else days[days.index >= cutoff]
                if len(days) == 0:
                    continue
                day = days.index[rng.integers(len(days))]
                st = int(day.value // 1_000_000) + (int(rng.integers(6)) * 4 * 3_600_000 if tf == "4h" else 0)
                i0 = int(np.searchsorted(om, st))
                if i0 >= len(o):
                    continue
                px = o[i0]
                stop = px * (1 - r["dir"] * r["risk_pct"])
                res = simulate(om, o, h, l, c, st, r["dir"], stop, v["exit"], trail, spec["max_hold"],
                               spec["hours_per_bar"])
                if res:
                    rows.append(dict(coin=coin, dir=r["dir"], signal_time=day, **res))
    return pd.DataFrame(rows)


def stats(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return dict(n=0)
    df = df.sort_values("entry_time")
    r = df["r"].values
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    cum = np.cumsum(r)
    dd = (np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum).max()
    streak = mx = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    se = r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else np.nan
    return dict(n=int(len(r)), win=float((r > 0).mean() * 100), avg_r=float(r.mean()),
                med_r=float(np.median(r)), se=float(se) if np.isfinite(se) else None,
                t=float(r.mean() / se) if se and np.isfinite(se) and se > 0 else 0.0,
                pf=float(wins / losses) if losses > 0 else float("inf"),
                max_dd_r=float(dd), max_losing_streak=int(mx), total_r=float(r.sum()),
                avg_hours=float(df["hours"].mean()), med_hours=float(df["hours"].median()),
                pct_target=float((df["reason"] == "目標").mean() * 100),
                pct_stop=float((df["reason"] == "停損").mean() * 100))


def split_time(df, cutoff):
    return df[df["signal_time"] < cutoff], df[df["signal_time"] >= cutoff]


def by_year(df):
    out = {}
    if len(df) == 0:
        return out
    for y, g in df.groupby(pd.to_datetime(df["signal_time"]).dt.year):
        out[int(y)] = stats(g)
    return out


# ====================================================================== 日線規則：前瞻報酬
HORIZONS = [1, 3, 7, 14]


def forward_returns(daily: pd.DataFrame):
    c = daily["close"]
    return pd.DataFrame({f"f{h}": c.shift(-h) / c - 1 for h in HORIZONS}, index=daily.index)


def rule_stats(events: pd.DataFrame, base: pd.DataFrame, direction: int):
    out = {}
    for hz in HORIZONS:
        col = f"f{hz}"
        e = events[col].dropna() * direction
        b = base[col].dropna() * direction
        if len(e) == 0:
            out[hz] = dict(n=0)
            continue
        out[hz] = dict(n=int(len(e)), mean=float(e.mean() * 100), median=float(e.median() * 100),
                       win=float((e > 0).mean() * 100), base_mean=float(b.mean() * 100),
                       excess=float((e.mean() - b.mean()) * 100))
    return out
