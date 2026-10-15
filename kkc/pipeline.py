"""把數據、訊號、回測串起來（短線 4H ＋ 波段日線）。"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data
from . import signals as sg


def load_coin(sym, cfg, cache, now_ms):
    d = data.klines(sym, "1d", cfg["days_daily"], f"{cache}/klines", now_ms)
    h4 = data.klines(sym, "4h", cfg["days_4h"], f"{cache}/klines", now_ms)
    h1 = data.klines(sym, "1h", cfg["days_1h"], f"{cache}/klines", now_ms)
    return d, h4, h1


def _exec_frames(daily, h4f, h1):
    """撮合用的 K 棒：短線用 1H（移動出場線＝已收盤 4H 的 EMA20），波段用日線（EMA20）。"""
    ex4 = h1.copy()
    t4 = pd.DataFrame({"t": h4f.index, "trail": h4f["ema20"].values})
    t1 = pd.DataFrame({"t": ex4.index})
    m = pd.merge_asof(t1, t4, on="t", direction="backward")
    ex4["trail"] = m["trail"].values
    exd = daily[["open_time", "open", "high", "low", "close"]].copy()
    exd["trail"] = daily["ema20"].values
    return ex4, exd


def analyze_coin(sym, d, h4, h1, cfg):
    daily = sg.daily_features(d)
    h4f = sg.h4_features(h4)
    k = cfg["pivot_k"]
    raw, ph, pl = sg.h4_setups(h4f, k)
    setups = [sg.enrich_setup(s, h4f, ph, pl, daily, cfg) for s in raw]
    setups = [s for s in setups if not np.isnan(s["score"])]
    rawd, phd, pld = sg.h4_setups(daily, k)
    dsetups = [sg.enrich_setup(s, daily, phd, pld, daily, cfg) for s in rawd]
    dsetups = [s for s in dsetups if not np.isnan(s["score"])]
    for s in dsetups:
        s["tf"] = "1d"
    for s in setups:
        s["tf"] = "4h"
    ex4, exd = _exec_frames(daily, h4f, h1)
    return dict(symbol=sym, daily=daily, h4=h4f, h1=h1, setups=setups, ph=ph, pl=pl,
                dsetups=dsetups, phd=phd, pld=pld, ex4=ex4, exd=exd)


def load_universe(cfg, cache, log=print, now_ms=None, symbols=None, workers=6):
    now_ms = now_ms or int(time.time() * 1000)
    if symbols:
        uni = [{"symbol": s, "base": s[:-4], "quote_volume": np.nan, "last": np.nan, "chg24h": np.nan}
               for s in symbols]
    else:
        uni = data.universe(cfg["top_n"] * 3)
        uni = [u for u in uni if u["quote_volume"] >= cfg["min_quote_volume_usd"]]
        try:  # 只留有永續合約的幣（同時排除代幣化股票、冷門幣）
            snap = data.hl_snapshot()
            uni = [u for u in uni if data.hl_name(u["base"], snap)]
        except Exception as e:  # noqa
            log(f"  ! Hyperliquid 清單取得失敗，略過合約過濾：{e}")
    coins, skipped = {}, []

    def job(u):
        d, h4, h1 = load_coin(u["symbol"], cfg, cache, now_ms)
        return u, d, h4, h1

    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(job, u) for u in uni]
        for k, f in enumerate(as_completed(futs), 1):
            try:
                u, d, h4, h1 = f.result()
            except Exception as e:  # noqa
                log(f"  ! 抓取失敗：{e}")
                continue
            if len(d) and (now_ms - d["open_time"].iloc[-1]) > 3 * 86_400_000:
                skipped.append((u["symbol"], "超過 3 天沒有新 K 線（可能已下架或改名）"))
                continue
            need_h1 = min(500, int(cfg["days_1h"] * 24 * 0.8))
            need_h4 = min(300, int(cfg["days_4h"] * 6 * 0.8))
            if len(d) < cfg["min_daily_bars"] or len(h4) < need_h4 or len(h1) < need_h1:
                skipped.append((u["symbol"], f"資料不足（日線 {len(d)} 根）"))
                continue
            coins[u["symbol"]] = dict(meta=u, d=d, h4=h4, h1=h1)
            if k % 20 == 0:
                log(f"  已載入 {k}/{len(uni)}")
    order = [u["symbol"] for u in uni if u["symbol"] in coins][: cfg["top_n"]]
    coins = {s: coins[s] for s in order}
    return coins, skipped, uni


def attach_btc(analyses, cfg):
    """每個訊號附上當時 BTC 的日線方向分數與牛熊（收盤是否在 EMA200 上），再分級。"""
    btc = analyses.get("BTCUSDT")
    if not btc:
        return
    bd = btc["daily"]
    bs, bull = bd["score"], (bd["close"] > bd["ema200"])
    for a in analyses.values():
        for key, tf in (("setups", "4h"), ("dsetups", "1d")):
            for s in a[key]:
                i = bs.index.searchsorted(s["time"], side="right") - 1
                s["btc_score"] = float(bs.iloc[i]) if i >= 0 else np.nan
                s["btc_bull"] = bool(bull.iloc[i]) if i >= 0 else None
                s["grade_v1"] = s.get("grade_v1", s["grade"])
                s["grade"] = sg.grade_btc(s, cfg, tf)


def backtest_all(analyses, cfg, log=print):
    rows, rule_rows, base_rows = [], [], []
    for sym, a in analyses.items():
        rows.extend(bt.run_setups(sym, a["setups"], a["ex4"], "4h", cfg))
        rows.extend(bt.run_setups(sym, a["dsetups"], a["exd"], "1d", cfg))
        fr = bt.forward_returns(a["daily"])
        hits = sg.daily_rule_hits(a["daily"])
        valid = a["daily"]["score"].notna()
        base = fr[valid].copy()
        base["coin"] = sym
        base_rows.append(base)
        for r in sg.RULES:
            h = hits[r["id"]] & valid
            keep, last = [], None
            for t in h[h].index:
                if last is None or (t - last).days > 5:
                    keep.append(t)
                    last = t
            if keep:
                e = fr.loc[keep].copy()
                e["coin"], e["rule"] = sym, r["id"]
                rule_rows.append(e)
    trades = pd.DataFrame(rows)
    base = pd.concat(base_rows) if base_rows else pd.DataFrame()
    rule_ev = pd.concat(rule_rows) if rule_rows else pd.DataFrame()
    return trades, base, rule_ev


def choose_variant(trades, tf, cutoff, min_n):
    """只用『樣本內』挑出期望值最高的方案（不看樣本外答案）。"""
    best, best_v = None, -1e9
    table = []
    for vi, v in enumerate(bt.variants(tf)):
        t = trades[trades["variant"] == vi]
        ins, oos = bt.split_time(t, cutoff)
        si, so, sa = bt.stats(ins), bt.stats(oos), bt.stats(t)
        table.append(dict(vi=vi, name=bt.variant_name(v), exit=v["exit"], stop=v["stop"], ins=si, oos=so, all=sa))
        if si.get("n", 0) >= min_n and si["avg_r"] > best_v:
            best, best_v = vi, si["avg_r"]
    return (best if best is not None else 0), table
