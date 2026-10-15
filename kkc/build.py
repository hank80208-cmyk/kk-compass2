"""完整流程：抓資料 → 分析 → 回測 → 策略建議 → 組成報告需要的資料（context）。"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import backtest as bt
from . import data
from . import pipeline as pp
from . import signals as sg

TW = "Asia/Taipei"
TF_KEYS = {"4h": ("setups", "ph", "pl", "h4"), "1d": ("dsetups", "phd", "pld", "daily")}


def _f(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if np.isfinite(x) else None


def tw(ts, fmt="%m-%d %H:%M"):
    return pd.Timestamp(ts).tz_convert(TW).strftime(fmt)


def load_and_analyze(cfg, cache, log=print, now_ms=None):
    coins, skipped, uni = pp.load_universe(cfg, cache, log=log, now_ms=now_ms)
    an = {s: pp.analyze_coin(s, c["d"], c["h4"], c["h1"], cfg) for s, c in coins.items()}
    pp.attach_btc(an, cfg)
    for s in an:
        an[s]["meta"] = coins[s]["meta"]
    return an, skipped, uni


# ---------------------------------------------------------------- 結構等待點
def current_levels(df, ph, pl, k, fmt="%m-%d %H:%M"):
    """目前『等待中』的結構：做多要收盤站上哪裡、做空要收盤跌破哪裡。"""
    n = len(df)
    known = n - 1 - k
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    Hs = [(i, hi[i]) for i in range(max(0, known - 400), known + 1) if ph[i]]
    Ls = [(i, lo[i]) for i in range(max(0, known - 400), known + 1) if pl[i]]
    out = {}
    if Ls:
        iL, pL = Ls[-1]
        after = [x for x in Hs if x[0] > iL]
        broken = cl[iL + 1:].min() < pL if iL + 1 < n else False
        if after and not broken:
            iH, pH = after[-1]
            done = bool((cl[iH + 1:] > pH).any()) if iH + 1 < n else False
            out["long"] = dict(hold=float(pL), trigger=float(pH), hold_time=tw(df.index[iL], fmt),
                               trigger_time=tw(df.index[iH], fmt), already=done)
    if Hs:
        iH, pH = Hs[-1]
        after = [x for x in Ls if x[0] > iH]
        broken = cl[iH + 1:].max() > pH if iH + 1 < n else False
        if after and not broken:
            iL, pL = after[-1]
            done = bool((cl[iL + 1:] < pL).any()) if iL + 1 < n else False
            out["short"] = dict(hold=float(pH), trigger=float(pL), hold_time=tw(df.index[iH], fmt),
                                trigger_time=tw(df.index[iL], fmt), already=done)
    return out


# ---------------------------------------------------------------- 單筆計畫
def setup_plan(s, cfg, strat=None):
    """把一個結構確認點轉成可執行的計畫；strat 為該週期的回測主要方案。"""
    d, e = s["dir"], s["entry"]
    tf = s.get("tf", "4h")
    stop_key = (strat or {}).get("stop", "pullback")
    exit_key = (strat or {}).get("exit", "fixed3")
    stop = s["stop_pull"] if stop_key == "pullback" else s["stop_struct"]
    risk = abs(e - stop)
    risk_pct = risk / e * 100
    plan = dict(dir=d, tf=tf, time=tw(s["time"], "%m-%d %H:%M" if tf == "4h" else "%Y-%m-%d"),
                grade=s["grade"], entry=e, trigger=s["trigger"], stop=stop, stop_key=stop_key,
                risk_pct=risk_pct, stop_pull=s["stop_pull"], stop_struct=s["stop_struct"],
                risk_pull=s["pull_risk_pct"], risk_struct=s["struct_risk_pct"],
                btc_score=s.get("btc_score"), score=s["score"], exit_key=exit_key,
                t2=e + d * 2 * risk, t3=e + d * 3 * risk, t4=e + d * 4 * risk)
    ex = bt.EXITS[exit_key]
    if ex["kind"] == "fixed":
        plan["tp_text"] = f"{ex['r']:.0f}R 全部出場：{fmt_px(e + d * ex['r'] * risk)}"
    elif ex["kind"] == "scale":
        plan["tp_text"] = (f"2R 先平一半：{fmt_px(plan['t2'])}，停損移到成本；剩下 4R：{fmt_px(plan['t4'])}")
    else:
        when = "1H 收盤" if tf == "4h" else "日線收盤"
        line = "4H EMA20" if tf == "4h" else "EMA20"
        plan["tp_text"] = (f"不設固定止盈，{when}{'跌破' if d == 1 else '站上'} {line} 就出場"
                           f"（參考：2R {fmt_px(plan['t2'])}、3R {fmt_px(plan['t3'])}）")
    # 部位：每筆虧損 = 本金的 risk_per_trade%
    rpt = (strat or {}).get("risk_suggest", cfg.get("risk_per_trade_pct", 1.0))
    plan["risk_per_trade"] = rpt
    plan["position_x"] = rpt / risk_pct if risk_pct > 0 else None  # 倉位 / 本金
    return plan


def fmt_px(x):
    a = abs(x)
    nd = 2 if a >= 100 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.1 else 6 if a >= 0.01 else 8
    return f"{x:,.{nd}f}"


# ---------------------------------------------------------------- 資金費率
def funding_info(an, cfg, cache, log=print):
    try:
        snap = data.hl_snapshot()
    except Exception as e:  # noqa
        log(f"  ! 資金費率取得失敗：{e}")
        return {}
    out = {}
    for sym, a in an.items():
        name = data.hl_name(a["meta"]["base"], snap)
        if not name:
            continue
        cur = snap[name]
        info = dict(hl=name, rate_h=cur["funding"], rate_8h=cur["funding"] * 8 * 100,
                    oi_usd=cur["oi_usd"], pct=None)
        try:
            hist = data.hl_funding_history(name, cfg["funding_days"], f"{cache}/funding")
            if len(hist) > 48:
                info["pct"] = float((hist.values < cur["funding"]).mean() * 100)
        except Exception as e:  # noqa
            log(f"  ! {name} 資金費率歷史失敗：{e}")
        out[sym] = info
        time.sleep(0.12)
    return out


# ---------------------------------------------------------------- 回測彙整
def run_backtest(an, cfg, log=print):
    trades, base, rule_ev = pp.backtest_all(an, cfg, log)
    btc_score = an["BTCUSDT"]["daily"]["score"].dropna()
    strategies = {}
    for tf in ("4h", "1d"):
        t_all = trades[trades["tf"] == tf]
        cutoff = t_all["signal_time"].quantile(1 - cfg["oos_fraction"])
        _, vtable = pp.choose_variant(t_all, tf, cutoff, cfg["min_trades_for_stats"])
        best, _ = pp.choose_variant(t_all[t_all["grade"] == "A"], tf, cutoff, 20)  # 只看樣本內 A 級
        v = bt.variants(tf)[best]
        t = t_all[t_all["variant"] == best]
        grades = {}
        for g in "ABCD":
            sub = t[t["grade"] == g]
            ins, oos = bt.split_time(sub, cutoff)
            grades[g] = dict(all=bt.stats(sub), ins=bt.stats(ins), oos=bt.stats(oos),
                             all_long=bt.stats(sub[sub["dir"] == 1]), all_short=bt.stats(sub[sub["dir"] == -1]),
                             oos_long=bt.stats(oos[oos["dir"] == 1]), oos_short=bt.stats(oos[oos["dir"] == -1]))
        a_tr = t[t["grade"] == "A"]
        log(f"  {bt.TF[tf]['name']}隨機對照組…")
        rc = bt.run_random_control(a_tr, {s: a["ex4" if tf == "4h" else "exd"] for s, a in an.items()},
                                   btc_score, tf, v, cutoff)
        rins, roos = bt.split_time(rc, cutoff) if len(rc) else (rc, rc)
        regime = {}
        for bull in (True, False):
            for d in (1, -1):
                regime[(bull, d)] = bt.stats(a_tr[(a_tr["btc_bull"] == bull) & (a_tr["dir"] == d)])
        v1 = {}
        for g in "ABC":
            sub = t[t["grade_v1"] == g]
            v1[g] = dict(all=bt.stats(sub), oos=bt.stats(bt.split_time(sub, cutoff)[1]))
        per_coin = {}
        for sym, g in t.groupby("coin"):
            per_coin[sym] = dict(all=bt.stats(g), A=bt.stats(g[g["grade"] == "A"]),
                                 recent=g.sort_values("entry_time").tail(10)[
                                     ["signal_time", "dir", "grade", "r", "reason", "hours"]].to_dict("records"))
        # 建議每筆風險：讓 A 級歷史最大回撤約等於本金的 target_max_dd_pct（上下限 0.25%～1%）
        mdd = grades["A"]["all"].get("max_dd_r") or 0
        risk_suggest = float(np.clip(cfg.get("target_max_dd_pct", 20) / mdd, 0.25, 1.0)) if mdd > 0 else 0.5
        risk_suggest = round(risk_suggest * 4) / 4 if risk_suggest >= 0.5 else round(risk_suggest, 2)
        strategies[tf] = dict(tf=tf, name=bt.TF[tf]["name"], cutoff=cutoff, variants=vtable, best=best,
                              risk_suggest=risk_suggest,
                              stop=v["stop"], exit=v["exit"], best_name=bt.variant_name(v), grades=grades,
                              years_A=bt.by_year(a_tr), years_all=bt.by_year(t), regime=regime,
                              random=dict(all=bt.stats(rc), ins=bt.stats(rins), oos=bt.stats(roos)),
                              grades_v1=v1, per_coin=per_coin, n_trades=int(len(t)),
                              period=(t_all["signal_time"].min(), t_all["signal_time"].max()),
                              n_coins=int(t_all["coin"].nunique()))
    # 日線篩選規則（用短線的切點）
    cutoff = strategies["4h"]["cutoff"]
    rules = []
    for r in sg.RULES:
        e = rule_ev[rule_ev["rule"] == r["id"]] if len(rule_ev) else rule_ev
        ins = bt.rule_stats(e[e.index < cutoff], base[base.index < cutoff], r["dir"])
        oos = bt.rule_stats(e[e.index >= cutoff], base[base.index >= cutoff], r["dir"])
        ok_i = ins[7].get("n", 0) >= 30 and ins[7].get("excess", -1) > 0
        ok_o = oos[7].get("n", 0) >= 15 and oos[7].get("excess", -1) > 0
        verdict = ("兩段都贏基準" if ok_i and ok_o else
                   "樣本太少" if oos[7].get("n", 0) < 15 or ins[7].get("n", 0) < 30 else
                   "不穩定" if ok_i or ok_o else "沒有優勢")
        rules.append(dict(**r, ins=ins, oos=oos, verdict=verdict))
    return dict(strategies=strategies, rules=rules)


def strat_ok(strat, grade, d):
    """這個等級＋方向，回測是否支持（全期與樣本外都 > 0，且樣本足夠）。"""
    g = strat["grades"].get(grade, {})
    a = g.get("all_long" if d == 1 else "all_short", {})
    o = g.get("oos_long" if d == 1 else "oos_short", {})
    return (a.get("n", 0) >= 30 and a.get("avg_r", -1) > 0 and o.get("n", 0) >= 10 and o.get("avg_r", -1) > 0), a, o


# ---------------------------------------------------------------- 每幣策略建議
def recommend(sym, a, row, ctx_btc, cfg, strategies):
    """回傳一張策略卡：做多／做空／觀望，以及週期、進場、停損、止盈、持有時間、倉位。"""
    price = row["price"]
    picks = []
    for tf in ("1d", "4h"):
        key, phk, plk, dfk = TF_KEYS[tf]
        df = a[dfk]
        fresh_n = cfg["signal_fresh_days"] if tf == "1d" else cfg["signal_fresh_bars"]
        fresh = [s for s in a[key] if s["t"] >= len(df) - fresh_n]
        strat = strategies.get(tf) if strategies else None
        for s in fresh[-2:]:
            if s["grade"] not in ("A", "B"):
                continue
            plan = setup_plan(s, cfg, strat)
            ok, st_all, st_oos = strat_ok(strat, s["grade"], s["dir"]) if strat else (False, {}, {})
            moved_r = (price - plan["entry"]) * s["dir"] / abs(plan["entry"] - plan["stop"])
            stopped = (price - plan["stop"]) * s["dir"] <= 0
            if stopped:
                continue
            plan.update(symbol=sym, ok=ok, hist=st_all, hist_oos=st_oos, moved_r=moved_r,
                        hold_med=(strat["grades"][s["grade"]]["all"].get("med_hours") if strat else None),
                        streak=(strat["grades"][s["grade"]]["all"].get("max_losing_streak") if strat else None),
                        strat_name=strat["best_name"] if strat else "")
            picks.append(plan)
    picks.sort(key=lambda p: ({"A": 0, "B": 1}[p["grade"]], not p["ok"], p["tf"] != "1d"))
    rec = dict(symbol=sym, action="觀望", picks=picks, waits=[])
    good = [p for p in picks if p["ok"]]
    if good:
        p = good[0]
        rec["action"] = "做多" if p["dir"] == 1 else "做空"
        rec["main"] = p
        if p["moved_r"] > 1.0:
            rec["chase"] = f"價格已離確認價 {p['moved_r']:.1f}R，追價的盈虧比會變差，等回踩或放棄。"
    # 沒有建議時：列出等待條件
    strong = cfg["btc_strong_score"]
    for tf, lv in (("1d", row["levels_d"]), ("4h", row["levels"])):
        for side, d in (("long", 1), ("short", -1)):
            x = lv.get(side)
            if not x or x["already"]:
                continue
            g = "A/B" if ctx_btc * d >= strong else ("D" if ctx_btc * d <= -strong else "C")
            rec["waits"].append(dict(tf=tf, dir=d, trigger=x["trigger"], hold=x["hold"],
                                     dist=(x["trigger"] / price - 1) * 100, grade_if=g))
    return rec


# ---------------------------------------------------------------- 市場表
def market_rows(an, funding, cfg):
    btc_d = an["BTCUSDT"]["daily"] if "BTCUSDT" in an else None
    rows = []
    k = cfg["pivot_k"]
    for sym, a in an.items():
        d, h1 = a["daily"], a["h1"]
        last = d.iloc[-1]
        px = float(h1["close"].iloc[-1])
        c24 = px / float(h1["close"].iloc[-25]) - 1 if len(h1) > 25 else np.nan
        c7 = px / float(h1["close"].iloc[-169]) - 1 if len(h1) > 169 else np.nan
        c30 = px / float(d["close"].iloc[-31]) - 1 if len(d) > 31 else np.nan
        rs = np.nan
        if btc_d is not None and len(btc_d) > 31 and sym != "BTCUSDT":
            rs = c30 - (btc_d["close"].iloc[-1] / btc_d["close"].iloc[-31] - 1)
        hits = sg.daily_rule_hits(d).iloc[-1]
        rows.append(dict(
            symbol=sym, base=sym[:-4], price=px, chg24=_f(c24 * 100, 2), chg7=_f(c7 * 100, 2),
            chg30=_f(c30 * 100, 2), rs30=_f(rs * 100, 2), score=_f(last["score"], 0),
            label=sg.score_label(last["score"]), rsi=_f(last["rsi"], 1),
            from_high=_f((last["close"] / last["hi365"] - 1) * 100, 1),
            from_low=_f((last["close"] / last["lo365"] - 1) * 100, 1),
            vol_ratio=_f(last["vol_ratio"], 2), atr_pct=_f(last["atr_pct"], 2),
            quote_volume=a["meta"].get("quote_volume"),
            rules=[r for r in hits.index if hits[r]],
            funding=funding.get(sym),
            levels=current_levels(a["h4"], a["ph"], a["pl"], k),
            levels_d=current_levels(a["daily"], a["phd"], a["pld"], k, "%Y-%m-%d"),
        ))
    return rows


def build_context(an, cfg, cache, skipped, uni, log=print, with_backtest=True):
    now = datetime.now(timezone.utc)
    log("  資金費率…")
    funding = funding_info(an, cfg, cache, log)
    rows = market_rows(an, funding, cfg)
    btc = an["BTCUSDT"]["daily"].iloc[-1]
    btc_score = float(btc["score"])
    btb = run_backtest(an, cfg, log) if with_backtest else None
    strategies = btb["strategies"] if btb else {}
    recs = {}
    for r in rows:
        rec = recommend(r["symbol"], an[r["symbol"]], r, btc_score, cfg, strategies)
        for p in rec["picks"]:
            p["funding"] = r["funding"]
        recs[r["symbol"]] = rec
        r["action"] = rec["action"]
    return dict(now=now, now_tw=pd.Timestamp(now).tz_convert(TW).strftime("%Y-%m-%d %H:%M"),
                btc_score=btc_score, btc_label=sg.score_label(btc_score),
                btc_items={k: float(btc[k]) for k, *_ in sg.SCORE_ITEMS},
                btc_bull=bool(btc["close"] > btc["ema200"]), btc_ema200=float(btc["ema200"]),
                btc_price=float(an["BTCUSDT"]["h1"]["close"].iloc[-1]),
                rows=rows, recs=recs, backtest=btb, cfg=cfg,
                skipped=skipped, universe_n=len(uni), n=len(an))
