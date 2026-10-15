"""核心測試：python tests/test_core.py

1. 撮合：停損與目標同一根 → 算停損；跳空越過停損 → 用開盤價；分批止盈；移動出場。
2. 無未來函數：截斷資料後，截斷前的短線與波段訊號必須和完整資料算出來的一模一樣。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from kkc import backtest as bt, pipeline as pp  # noqa: E402
from kkc.data import finalize  # noqa: E402

N = 12
OM = np.arange(N, dtype="int64") * 3_600_000


def bars():
    return np.full(N, 100.0), np.full(N, 101.0), np.full(N, 99.0), np.full(N, 100.0)


def test_simulate():
    slip = bt.COST["slip"]
    # 1) 同一根同時碰到停損與目標 → 停損
    o, h, l, c = bars()
    h[2], l[2] = 115, 94
    r = bt.simulate(OM, o, h, l, c, 0, 1, 95, "fixed2", max_hold=10)
    assert r["reason"] == "停損" and r["r"] < -1, r
    # 2) 跳空越過停損 → 用開盤價出場（約 -10%）
    o, h, l, c = bars()
    o[3], h[3], l[3] = 90, 91, 89
    r = bt.simulate(OM, o, h, l, c, 0, 1, 95, "fixed2", max_hold=10)
    assert r["reason"] == "停損" and -0.105 < r["ret"] < -0.099, r
    # 3) 做空，目標先到
    o, h, l, c = bars()
    l[4] = 89
    r = bt.simulate(OM, o, h, l, c, 0, -1, 105, "fixed2", max_hold=10)
    assert r["reason"] == "目標" and 1.8 < r["r"] < 2.0, r
    # 4) 分批：2R 平一半後回到成本 → 保本出場，結果約 +1R
    o, h, l, c = bars()
    entry = 100 * (1 + slip)
    risk = entry - 95
    h[2] = entry + 2 * risk + 0.01
    l[5] = entry - 0.5
    r = bt.simulate(OM, o, h, l, c, 0, 1, 95, "scale", max_hold=10)
    assert r["reason"] == "保本出場" and 0.85 < r["r"] < 1.0, r
    # 5) 分批：2R 平一半、之後到 4R → 約 +3R（之後低點都在成本之上）
    o, h, l, c = bars()
    l[:] = entry + 0.3
    h[2] = entry + 2 * risk + 0.01
    h[6] = entry + 4 * risk + 0.01
    r = bt.simulate(OM, o, h, l, c, 0, 1, 95, "scale", max_hold=10)
    assert r["reason"] == "目標" and 2.8 < r["r"] < 3.0, r
    # 6) 移動出場：收盤跌破移動線就出場
    o, h, l, c = bars()
    trail = np.full(N, 98.0)
    c[4], l[4] = 97.5, 97
    r = bt.simulate(OM, o, h, l, c, 0, 1, 90, "trail", trail=trail, max_hold=10)
    assert r["reason"] == "移動出場" and r["exit_time"] == OM[4], r
    # 7) 資料不夠走完持有期 → None
    o, h, l, c = bars()
    assert bt.simulate(OM, o, h, l, c, 0, 1, 95, "fixed2", max_hold=50) is None
    print("✓ 撮合測試通過（停損優先、跳空、做空、分批保本、分批到 4R、移動出場、資料不足）")


def test_no_lookahead(symbols=("BTCUSDT", "SOLUSDT", "DOGEUSDT")):
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    for sym in symbols:
        raw = {tf: pd.read_csv(os.path.join(ROOT, "cache/klines", f"{sym}_{tf}.csv")) for tf in ("1d", "4h", "1h")}
        end = int(raw["4h"]["open_time"].iloc[-1]) + 14_400_000
        full = pp.analyze_coin(sym, *(finalize(raw[tf], tf, end) for tf in ("1d", "4h", "1h")), cfg)
        for frac in (0.6, 0.85):
            cut = int(raw["4h"]["open_time"].iloc[int(len(raw["4h"]) * frac)])
            part = pp.analyze_coin(sym, *(finalize(raw[tf], tf, cut) for tf in ("1d", "4h", "1h")), cfg)
            cut_ts = pd.Timestamp(cut, unit="ms", tz="UTC")
            for key in ("setups", "dsetups"):
                a = [(s["time"], s["dir"], round(s["entry"], 8), round(s["stop_pull"], 8), s["score"])
                     for s in full[key] if s["time"] <= cut_ts]
                b = [(s["time"], s["dir"], round(s["entry"], 8), round(s["stop_pull"], 8), s["score"])
                     for s in part[key]]
                assert a == b, f"{sym} {key} {frac}: 截斷前後訊號不同（可能偷看未來）\n{set(a) ^ set(b)}"
            fs, ps = full["daily"]["score"], part["daily"]["score"]
            assert np.allclose(fs.loc[ps.index].fillna(99), ps.fillna(99)), f"{sym} 日線分數不一致"
        print(f"✓ {sym} 無未來函數（短線 {len(full['setups'])}、波段 {len(full['dsetups'])} 個訊號，截斷 60%／85% 結果一致）")


if __name__ == "__main__":
    test_simulate()
    test_no_lookahead()
