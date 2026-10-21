"""訊號層：日線方向計分、4H『不破低，再過高』、分級、日線篩選規則。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ti


# ====================================================================== 日線
def daily_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    c = d["close"]
    for n in (20, 50, 200):
        d[f"ema{n}"] = ti.ema(c, n)
    d["atr"] = ti.atr(d)
    d["atr_pct"] = d["atr"] / c * 100
    d["dif"], d["dea"], d["hist"] = ti.macd(c)
    d["k"], d["d"] = ti.kd(d)
    d["rsi"] = ti.rsi(c)
    d["bb_mid"], d["bb_up"], d["bb_lo"], d["bb_w"] = ti.bollinger(c)
    d["bb_w_pct"] = ti.rolling_pct_rank(d["bb_w"], 120)
    d["vma20"] = ti.sma(d["quote_volume"], 20)
    d["vol_ratio"] = d["quote_volume"] / d["vma20"]
    d["hi365"] = d["high"].rolling(365, min_periods=200).max()
    d["lo365"] = d["low"].rolling(365, min_periods=200).min()
    d["lo90"] = d["low"].rolling(90, min_periods=60).min()
    d["hi90c"] = c.rolling(90, min_periods=60).max()
    d["lo90c"] = c.rolling(90, min_periods=60).min()
    d["dc_mid"] = (d["high"].rolling(20).max() + d["low"].rolling(20).min()) / 2
    d["close_pos"] = (c - d["low"]) / (d["high"] - d["low"]).replace(0, np.nan)

    # --- 方向計分（-7 ~ +7），每項都存下來給報告解釋
    e20, e50, e200 = d["ema20"], d["ema50"], d["ema200"]
    align = np.select(
        [(c > e20) & (e20 > e50) & (e50 > e200), (c < e20) & (e20 < e50) & (e50 < e200),
         (c > e200) & (e50 > e200), (c < e200) & (e50 < e200)],
        [2, -2, 1, -1], 0)
    slope = e50.pct_change(5) * 100
    s_slope = np.select([slope > 1, slope < -1], [1, -1], 0)
    s_macd = np.sign(d["hist"]).fillna(0)
    s_dc = np.where(c > d["dc_mid"], 1, -1)

    # 日線結構：最近兩個已確認擺動高 / 低
    ph, pl = ti.pivots(d, 3)
    struct = np.zeros(len(d))
    highs, lows = [], []
    ev = ti.known_pivot_lists(ph, pl, 3)
    j = 0
    hv, lv = d["high"].values, d["low"].values
    for t in range(len(d)):
        while j < len(ev) and ev[j][0] <= t:
            _, i, kind = ev[j]
            (highs if kind == "H" else lows).append(hv[i] if kind == "H" else lv[i])
            j += 1
        if len(highs) >= 2 and len(lows) >= 2:
            hh, hl = highs[-1] > highs[-2], lows[-1] > lows[-2]
            lh, ll = highs[-1] < highs[-2], lows[-1] < lows[-2]
            struct[t] = 2 if (hh and hl) else (-2 if (lh and ll) else 0)
    d["s_align"], d["s_slope"], d["s_macd"] = align, s_slope, s_macd
    d["s_struct"], d["s_dc"] = struct, s_dc
    d["ema50_slope"] = slope
    valid = e200.notna()
    d["score"] = (d[["s_align", "s_slope", "s_macd", "s_struct", "s_dc"]].sum(axis=1)).where(valid)
    d["bias_dir"] = np.select([d["score"] >= 3, d["score"] <= -3], [1, -1], 0)
    d["pivot_h"], d["pivot_l"] = ph, pl
    return d


def score_label(s):
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return "資料不足"
    s = int(s)
    if s >= 4:
        return "多頭"
    if s >= 2:
        return "偏多"
    if s <= -4:
        return "空頭"
    if s <= -2:
        return "偏空"
    return "震盪"


SCORE_ITEMS = [
    ("s_align", "均線排列", 2, "收盤/EMA20/50/200 完全多頭 +2、完全空頭 -2；站上/跌破 EMA200 且 EMA50 同側 ±1"),
    ("s_struct", "日線結構", 2, "最近兩個擺動高低點：高點墊高且低點墊高 +2；高點降低且低點降低 -2"),
    ("s_slope", "EMA50 斜率", 1, "近 5 日 > +1% 得 +1，< -1% 得 -1"),
    ("s_macd", "MACD 柱狀", 1, "柱狀在零軸上 +1、下 -1"),
    ("s_dc", "20 日區間位置", 1, "收盤高於近 20 日高低中點 +1，否則 -1"),
]


# ====================================================================== 4H 結構
def h4_features(h4: pd.DataFrame) -> pd.DataFrame:
    h4 = h4.copy()
    h4["atr"] = ti.atr(h4)
    h4["ema20"] = ti.ema(h4["close"], 20)
    h4["ema50"] = ti.ema(h4["close"], 50)
    h4["k"], h4["d"] = ti.kd(h4)
    h4["vol_ratio"] = h4["quote_volume"] / ti.sma(h4["quote_volume"], 20)
    rng = (h4["high"] - h4["low"]).replace(0, np.nan)
    h4["close_pos"] = (h4["close"] - h4["low"]) / rng
    return h4


def h4_setups(h4: pd.DataFrame, k: int = 3):
    """找出所有『不破低，再過高』(多) 與『不過高，再破低』(空) 的確認點。

    多：已確認擺動低 L → 其後已確認擺動高 H → L 之後沒有任何 4H 收盤跌破 L
        → 4H 收盤由下往上越過 H（以收盤為準）＝ 確認。
        回檔低 HL ＝ H 之後到確認前的最低點（更緊的停損選項）。
    空：完全鏡像。
    擺動點要等右側 k 根走完才算確認，因此只會用到當下已知的資訊。
    """
    ph, pl = ti.pivots(h4, k)
    ev = ti.known_pivot_lists(ph, pl, k)
    hi, lo, cl = h4["high"].values, h4["low"].values, h4["close"].values
    n = len(h4)
    out = []
    known_H, known_L = [], []  # (idx, price)
    j = 0
    used_long, used_short = set(), set()
    for t in range(1, n):
        while j < len(ev) and ev[j][0] <= t:
            _, i, kind = ev[j]
            if kind == "H":
                known_H.append((i, hi[i]))
            else:
                known_L.append((i, lo[i]))
            j += 1
        # ---- 多
        if known_L and known_H:
            iL, pL = known_L[-1]
            cand = [x for x in known_H if x[0] > iL]
            if cand:
                iH, pH = cand[-1]
                key = (iL, iH)
                if key not in used_long and cl[t] > pH and cl[t - 1] <= pH:
                    if cl[iL + 1:t + 1].min() >= pL:  # 不破低（收盤為準）
                        hl = lo[iH:t + 1].min()
                        out.append(dict(t=t, dir=1, swing=pL, swing_i=iL, trigger=pH,
                                        trigger_i=iH, pullback=hl))
                        used_long.add(key)
        # ---- 空
        if known_H and known_L:
            iH, pH = known_H[-1]
            cand = [x for x in known_L if x[0] > iH]
            if cand:
                iL, pL = cand[-1]
                key = (iH, iL)
                if key not in used_short and cl[t] < pL and cl[t - 1] >= pL:
                    if cl[iH + 1:t + 1].max() <= pH:  # 不過高
                        lh = hi[iL:t + 1].max()
                        out.append(dict(t=t, dir=-1, swing=pH, swing_i=iH, trigger=pL,
                                        trigger_i=iL, pullback=lh))
                        used_short.add(key)
    return out, ph, pl


def nearest_opposing_level(h4, ph, pl, t, entry, direction, k=3, lookback=180):
    """進場價上方（做多）/下方（做空）最近的已確認 4H 擺動點，當作第一道壓力/支撐。"""
    lo_i = max(0, t - lookback)
    idx = np.arange(lo_i, max(lo_i, t - k + 1))
    if direction == 1:
        lv = [h4["high"].values[i] for i in idx if ph[i] and h4["high"].values[i] > entry]
        return min(lv) if lv else None
    lv = [h4["low"].values[i] for i in idx if pl[i] and h4["low"].values[i] < entry]
    return max(lv) if lv else None


def daily_opposing_level(dd, entry, direction, k=3, lookback=365):
    """日線上，進場價上方（做多）/下方（做空）最近、且已確認的擺動高/低點。

    dd 只含 4H 訊號當下以前已收盤的日 K，擺動點需右側 k 根走完才算數。
    """
    if len(dd) <= k:
        return None
    sub = dd.iloc[max(0, len(dd) - lookback): len(dd) - k]
    if direction == 1:
        lv = sub.loc[sub["pivot_h"].astype(bool), "high"]
        lv = lv[lv > entry]
        return float(lv.min()) if len(lv) else None
    lv = sub.loc[sub["pivot_l"].astype(bool), "low"]
    lv = lv[lv < entry]
    return float(lv.max()) if len(lv) else None


GRADE_TEXT = {
    "A": "BTC 趨勢明確且同方向，停損 ≤ 上限",
    "B": "BTC 趨勢明確且同方向，但停損偏寬",
    "C": "BTC 在震盪區，結構訊號歷史上約打平",
    "D": "逆著 BTC 的明確趨勢，歷史上樣本外為負",
}


def grade_btc(s, cfg, tf="4h"):
    """依回測證據的分級（v2）：決定性因素是 BTC 日線趨勢，不是幣種自己的趨勢。

    停損上限依週期不同：短線 max_risk_pct、波段 max_risk_pct_d（事先設定，不是回測挑出來的）。
    """
    cap = cfg["max_risk_pct"] if tf == "4h" else cfg["max_risk_pct_d"]
    b = s.get("btc_score")
    if b is None or np.isnan(b):
        return "C"
    strong = abs(b) >= cfg["btc_strong_score"]
    aligned = strong and np.sign(b) == s["dir"]
    if strong and not aligned:
        return "D"
    if aligned:
        # 老師「突破要放量」：短線 4H 量比 < 1 降為 C（6 年回測樣本外 +0.03R vs +0.44R）
           if tf == "4h" and s.get("vol_ratio4", np.inf) < cfg.get("min_vol_ratio_4h", 1.0):
               return "C"
           return "A" if s["pull_risk_pct"] <= cap else "B"
    return "C"


def grade(trend_rel, stop_fit_ok, room_ok):
    """A：順勢＋停損距離合適＋空間 ≥ 2R；B：差一項或是震盪盤；C：其餘（含逆勢）。"""
    if trend_rel == "逆勢":
        return "C"
    misses = (not stop_fit_ok) + (not room_ok)
    if trend_rel == "順勢":
        return "A" if misses == 0 else ("B" if misses == 1 else "C")
    return "B" if misses == 0 else "C"  # 震盪


def enrich_setup(s, h4, ph, pl, daily, cfg):
    """把一個 4H 確認點補上：日線方向、停損、空間、停損距離檢查、等級。"""
    t, direction = s["t"], s["dir"]
    row = h4.iloc[t]
    ts = h4.index[t]
    dd = daily[daily.index <= ts]
    score = dd["score"].iloc[-1] if len(dd) else np.nan
    bias = int(dd["bias_dir"].iloc[-1]) if len(dd) else 0
    trend_rel = "震盪" if bias == 0 else ("順勢" if bias == direction else "逆勢")
    atr4 = row["atr"]
    entry = row["close"]
    buf = cfg["stop_buffer_atr"] * atr4
    stop_struct = s["swing"] - direction * buf
    stop_pull = s["pullback"] - direction * buf
    stop = stop_pull if cfg["stop_mode"] == "pullback" else stop_struct
    risk = abs(entry - stop)
    stop_atr = risk / atr4 if atr4 and atr4 > 0 else np.nan
    lo_ok, hi_ok = cfg["stop_atr_min"], cfg["stop_atr_max"]
    stop_fit_ok = bool(lo_ok <= stop_atr <= hi_ok) if not np.isnan(stop_atr) else False
    opp = daily_opposing_level(dd, entry, direction)
    room_r = (abs(opp - entry) / risk) if (opp is not None and risk > 0) else np.inf
    room_ok = room_r >= cfg["min_room_r"]
    g = grade(trend_rel, stop_fit_ok, room_ok)
    cp = row["close_pos"]
    s.update(vol_ratio4=row["vol_ratio"],
             close_pos4=(cp if direction == 1 else 1 - cp),          # 收在 K 棒的強勢端 = 1
             ext_atr4=(entry - row["ema20"]) * direction / atr4 if atr4 else np.nan,  # 離 EMA20 多遠
             ema_side4=float(np.sign((row["ema20"] - row["ema50"]) * direction)),
             rsi_d=dd["rsi"].iloc[-1] if len(dd) else np.nan,
             atr_pct4=atr4 / entry * 100,
             struct_risk_pct=abs(entry - stop_struct) / entry * 100,
             pull_risk_pct=abs(entry - stop_pull) / entry * 100)
    s.update(time=ts, entry=entry, stop=stop, stop_struct=stop_struct, stop_pull=stop_pull,
             risk_pct=risk / entry * 100, atr4=atr4, stop_atr=stop_atr, stop_fit_ok=stop_fit_ok,
             opp_level=opp, room_r=room_r, room_ok=room_ok, score=score, bias=bias,
             trend_rel=trend_rel, grade=g)
    return s


# ====================================================================== 日線篩選規則
RULES = [
    dict(id="squeeze_up", name="壓縮後向上突破", dir=1,
         desc="布林帶寬處於近 120 日最窄兩成，收盤突破上緣且放量。低波動後的表態，真假突破需後續確認。",
         cond="前一日帶寬百分位 ≤ 20 ／ 收盤 > 布林上緣 ／ 量比（成交額÷20 日均）≥ 1.5"),
    dict(id="squeeze_dn", name="壓縮後向下跌破", dir=-1,
         desc="布林帶寬處於近 120 日最窄兩成，收盤跌破下緣且放量。",
         cond="前一日帶寬百分位 ≤ 20 ／ 收盤 < 布林下緣 ／ 量比 ≥ 1.5"),
    dict(id="cross_up", name="EMA20 上穿 50 初期帶量", dir=1,
         desc="EMA20 上穿 EMA50 三日內、放量、位於 EMA200 之上。",
         cond="交叉距今 ≤ 3 日 ／ 量比 ≥ 1.3 ／ 收盤 > EMA200"),
    dict(id="cross_dn", name="EMA20 下穿 50 初期帶量", dir=-1,
         desc="EMA20 下穿 EMA50 三日內、放量、位於 EMA200 之下。",
         cond="交叉距今 ≤ 3 日 ／ 量比 ≥ 1.3 ／ 收盤 < EMA200"),
    dict(id="deep_reclaim", name="深跌後站回 EMA20", dir=1,
         desc="距一年高點跌超過一半，首次放量站回 EMA20。抓長期下跌後的第一次收復，不代表跌勢結束。",
         cond="收盤 ≤ 365 日高點 × 0.5 ／ 收盤由下往上穿越 EMA20 ／ 量比 ≥ 1.5"),
    dict(id="pump_lose", name="暴漲後跌破 EMA20", dir=-1,
         desc="自 90 日低點漲超過一倍後，首次放量跌破 EMA20。抓急漲後的第一次失守。",
         cond="收盤 ≥ 90 日低點 × 2 ／ 收盤由上往下穿越 EMA20 ／ 量比 ≥ 1.5"),
    dict(id="breakout_high", name="強勢創 90 日收盤新高", dir=1,
         desc="收盤創 90 日新高且日線方向為多頭（≥ +4）。動能延續型。",
         cond="收盤 = 近 90 日最高收盤 ／ 方向分數 ≥ 4"),
    dict(id="breakdown_low", name="弱勢創 90 日收盤新低", dir=-1,
         desc="收盤創 90 日新低且日線方向為空頭（≤ -4）。",
         cond="收盤 = 近 90 日最低收盤 ／ 方向分數 ≤ -4"),
    dict(id="kd_low_turn", name="低檔 KD 轉折（逆勢）", dir=1,
         desc="K 自超賣區回升穿過 D，且距一年高點 40% 以上。逆勢抄底型，風險高。",
         cond="K 上穿 D ／ K ≤ 30 ／ 近 10 日最低 K ≤ 20 ／ 收盤 ≤ 365 日高點 × 0.6"),
    dict(id="kd_high_turn", name="高檔 KD 轉折（逆勢）", dir=-1,
         desc="K 自超買區回落穿過 D，且距 90 日低點漲超過 50%。逆勢摸頭型，風險高。",
         cond="K 下穿 D ／ K ≥ 70 ／ 近 10 日最高 K ≥ 80 ／ 收盤 ≥ 90 日低點 × 1.5"),
]
RULE_BY_ID = {r["id"]: r for r in RULES}


def daily_rule_hits(d: pd.DataFrame) -> pd.DataFrame:
    """每一天每條規則是否成立（布林欄位）。"""
    c = d["close"]
    vr = d["vol_ratio"]
    out = pd.DataFrame(index=d.index)
    w_prev = d["bb_w_pct"].shift(1)
    out["squeeze_up"] = (w_prev <= 20) & (c > d["bb_up"]) & (vr >= 1.5)
    out["squeeze_dn"] = (w_prev <= 20) & (c < d["bb_lo"]) & (vr >= 1.5)
    up = (d["ema20"] > d["ema50"]) & (d["ema20"].shift(1) <= d["ema50"].shift(1))
    dn = (d["ema20"] < d["ema50"]) & (d["ema20"].shift(1) >= d["ema50"].shift(1))
    up3 = up.rolling(4, min_periods=1).max().astype(bool) & (d["ema20"] > d["ema50"])
    dn3 = dn.rolling(4, min_periods=1).max().astype(bool) & (d["ema20"] < d["ema50"])
    out["cross_up"] = up3 & (vr >= 1.3) & (c > d["ema200"])
    out["cross_dn"] = dn3 & (vr >= 1.3) & (c < d["ema200"])
    x_up = (c > d["ema20"]) & (c.shift(1) <= d["ema20"].shift(1))
    x_dn = (c < d["ema20"]) & (c.shift(1) >= d["ema20"].shift(1))
    out["deep_reclaim"] = (c <= d["hi365"] * 0.5) & x_up & (vr >= 1.5)
    out["pump_lose"] = (c >= d["lo90"] * 2) & x_dn & (vr >= 1.5)
    out["breakout_high"] = (c >= d["hi90c"]) & (d["score"] >= 4)
    out["breakdown_low"] = (c <= d["lo90c"]) & (d["score"] <= -4)
    kx_up = (d["k"] > d["d"]) & (d["k"].shift(1) <= d["d"].shift(1))
    kx_dn = (d["k"] < d["d"]) & (d["k"].shift(1) >= d["d"].shift(1))
    out["kd_low_turn"] = kx_up & (d["k"] <= 30) & (d["k"].rolling(10).min() <= 20) & (c <= d["hi365"] * 0.6)
    out["kd_high_turn"] = kx_dn & (d["k"] >= 70) & (d["k"].rolling(10).max() >= 80) & (c >= d["lo90"] * 1.5)
    return out.fillna(False).astype(bool)
