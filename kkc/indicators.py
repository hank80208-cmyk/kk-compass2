"""技術指標。全部只用到當根與之前的資料（無未來函數），擺動高低點例外，見 pivots()。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(s, fast=12, slow=26, sig=9):
    dif = ema(s, fast) - ema(s, slow)
    dea = dif.ewm(span=sig, adjust=False, min_periods=sig).mean()
    return dif, dea, dif - dea


def kd(df, n=9, k=3, d=3):
    """台灣常用 KD(9,3,3)。"""
    ll = df["low"].rolling(n, min_periods=n).min()
    hh = df["high"].rolling(n, min_periods=n).max()
    rsv = ((df["close"] - ll) / (hh - ll).replace(0, np.nan) * 100).fillna(50)
    kk = rsv.ewm(alpha=1 / k, adjust=False).mean()
    dd = kk.ewm(alpha=1 / d, adjust=False).mean()
    kk[ll.isna()] = np.nan
    dd[ll.isna()] = np.nan
    return kk, dd


def bollinger(s, n=20, k=2.0):
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    width = (up - lo) / mid
    return mid, up, lo, width


def rolling_pct_rank(s, n):
    """當前值在近 n 根中的百分位（0~100）。"""
    def f(a):
        return (a[:-1] < a[-1]).mean() * 100 if len(a) > 1 else np.nan
    return s.rolling(n, min_periods=max(10, n // 2)).apply(f, raw=True)


def pivots(df, k=3):
    """擺動高低點（左右各 k 根）。

    擺動點要等右邊 k 根走完才「確認」，所以回傳兩組欄位：
      ph / pl         : 在第 i 根是擺動高 / 低（只能事後才知道，畫圖用）
      ph_known / pl_known : 第 t 根收盤時『已確認』的最新擺動高 / 低價位與位置
    訊號一律使用 *_known，確保回測沒有偷看未來。
    """
    h, l = df["high"].values, df["low"].values
    n = len(df)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for i in range(k, n - k):
        win_h = h[i - k:i + k + 1]
        win_l = l[i - k:i + k + 1]
        if h[i] == win_h.max() and (win_h[:k] < h[i]).all():
            ph[i] = True
        if l[i] == win_l.min() and (win_l[:k] > l[i]).all():
            pl[i] = True
    return ph, pl


def known_pivot_lists(ph, pl, k):
    """對每個 t，列出到 t 為止已確認的擺動點索引（擺動點 i 在 i+k 確認）。

    回傳 confirm_at：list of (confirm_index, pivot_index, kind)，依確認時間排序。
    """
    ev = []
    for i in np.where(ph)[0]:
        ev.append((i + k, i, "H"))
    for i in np.where(pl)[0]:
        ev.append((i + k, i, "L"))
    ev.sort()
    return ev
