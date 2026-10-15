"""KK Compass 2

用法：
  python run.py daily          每日完整版：抓資料、6 年回測、策略建議、產生報告（reports/），傳 Telegram
  python run.py scan           每 4 小時：看最新 4H／日線是否出現回測支持的進場，有就傳 Telegram
  python run.py test-telegram  傳一則測試訊息
"""
from __future__ import annotations

import json
import os
import sys
import time

if sys.version_info < (3, 12):
    sys.exit("需要 Python 3.12 以上，請到 https://www.python.org/downloads/ 安裝新版。")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from kkc import build, emailer, notify, report  # noqa: E402

CACHE = os.path.join(ROOT, "cache")
OUT = os.path.join(ROOT, "reports")
STATE = os.path.join(ROOT, "state")


def load_cfg():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["telegram_bot_token"] = os.environ.get("KKC_TG_TOKEN", cfg.get("telegram_bot_token", ""))
    cfg["telegram_chat_id"] = os.environ.get("KKC_TG_CHAT", cfg.get("telegram_chat_id", ""))
    return cfg


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slim_strategies(strategies):
    """存給 scan 用的精簡版回測結果。"""
    out = {}
    for tf, st in strategies.items():
        out[tf] = dict(stop=st["stop"], exit=st["exit"], best_name=st["best_name"], risk_suggest=st["risk_suggest"],
                       grades={g: {k: st["grades"][g][k] for k in ("all", "all_long", "all_short", "oos_long", "oos_short")}
                               for g in "ABCD"})
    return out


def cmd_daily(artifact=False, notify_on=True):
    cfg = load_cfg()
    t0 = time.time()
    log("載入資料與分析…")
    an, skipped, uni = build.load_and_analyze(cfg, CACHE, log=log)
    log(f"  {len(an)} 個幣；回測中…")
    ctx = build.build_context(an, cfg, CACHE, skipped, uni, log=log)
    log("產生報告…")
    report.write_all(ctx, an, OUT, artifact=artifact)
    os.makedirs(STATE, exist_ok=True)
    with open(os.path.join(STATE, "strategies.json"), "w", encoding="utf-8") as f:
        json.dump(dict(generated=ctx["now_tw"], strategies=slim_strategies(ctx["backtest"]["strategies"])),
                  f, ensure_ascii=False, default=str)
    subject, html_body, text_body = emailer.build_email(ctx, cfg.get("report_url") if cfg.get("email_include_link") else None)
    with open(os.path.join(STATE, "email.json"), "w", encoding="utf-8") as f:
        json.dump(dict(subject=subject, html=html_body, text=text_body), f, ensure_ascii=False)
    log(f"完成，用時 {time.time() - t0:.0f} 秒 → {OUT}/index.html；email 內容 → state/email.json")
    if notify_on:
        acts = [r for r in ctx["recs"].values() if r["action"] != "觀望"]
        lines = [f"📊 KK Compass 每日報告 {ctx['now_tw']}",
                 f"BTC 日線 {ctx['btc_score']:+.0f}（{ctx['btc_label']}）・{'牛' if ctx['btc_bull'] else '熊'}市結構",
                 f"今日策略建議：{len(acts)} 檔" + ("" if acts else "（觀望）")]
        for r in acts[:8]:
            p = r["main"]
            lines.append(f"・{r['symbol'][:-4]} {r['action']} {p['grade']} {'波段' if p['tf'] == '1d' else '短線'}"
                         f"｜停損 {p['risk_pct']:.1f}%")
        if cfg.get("report_url"):
            lines.append(cfg["report_url"])
        notify.send(cfg, "\n".join(lines), log)
        for r in acts[:8]:
            notify.send(cfg, notify.format_plan(r["main"], cfg.get("report_url")), log)
        if not cfg.get("report_url"):
            notify.send_file(cfg, os.path.join(OUT, "index.html"), "每日總覽（用瀏覽器開啟）", log)
    return ctx, an


def load_strategies():
    """回測結果：優先用今天 daily 算的；雲端新環境沒有時，用程式庫內的快照。"""
    for path in (os.path.join(STATE, "strategies.json"), os.path.join(ROOT, "strategies_snapshot.json")):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)["strategies"]
        except (OSError, ValueError, KeyError):
            continue
    return None


def cmd_scan():
    """輕量掃描：只看最近兩根已收盤的 4H，有回測支持的 A/B 級新訊號才產生通知信。

    結果寫到 state/scan_email.json：{"send": true/false, "subject", "html", "text"}。
    """
    cfg = load_cfg()
    cfg.update(days_daily=600, days_4h=120, days_1h=10)
    os.makedirs(STATE, exist_ok=True)
    out_path = os.path.join(STATE, "scan_email.json")
    strategies = load_strategies()
    if not strategies:
        log("找不到回測結果（strategies.json / strategies_snapshot.json）")
        return
    an, _, _ = build.load_and_analyze(cfg, CACHE, log=lambda *a: None)
    funding = build.funding_info(an, {**cfg, "funding_days": 7}, CACHE, log=lambda *a: None)
    st = strategies["4h"]
    plans = []
    for sym, a in an.items():
        n = len(a["h4"])
        price = float(a["h1"]["close"].iloc[-1])
        for s in a["setups"]:
            if s["t"] < n - 2 or s["grade"] not in cfg["notify_grades"]:
                continue
            ok, h_all, h_oos = build.strat_ok(st, s["grade"], s["dir"])
            if not ok:
                continue
            p = build.setup_plan(s, cfg, st)
            if (price - p["stop"]) * s["dir"] <= 0:  # 已經打到停損就不通知
                continue
            p.update(symbol=sym, funding=funding.get(sym), hist=h_all, hist_oos=h_oos, ok=True,
                     hold_med=st["grades"][s["grade"]]["all"].get("med_hours"),
                     streak=st["grades"][s["grade"]]["all"].get("max_losing_streak"),
                     strat_name=st["best_name"], price_now=price,
                     moved_r=(price - p["entry"]) * s["dir"] / abs(p["entry"] - p["stop"]))
            plans.append(p)
    btc = an["BTCUSDT"]["daily"]["score"].iloc[-1]
    plans.sort(key=lambda p: (p["grade"], p["symbol"]))
    if plans:
        subject, html_body, text_body = emailer.build_scan_email(plans, float(btc), cfg)
        result = dict(send=True, subject=subject, html=html_body, text=text_body)
        if cfg.get("telegram_bot_token"):
            for p in plans:
                notify.send(cfg, notify.format_plan(p), log)
    else:
        result = dict(send=False)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    log(f"掃描完成：BTC {btc:+.0f}，新訊號 {len(plans)} 筆 → {out_path}")


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if c == "daily":
        cmd_daily(artifact="--artifact" in sys.argv, notify_on="--no-notify" not in sys.argv)
    elif c == "scan":
        cmd_scan()
    elif c == "test-telegram":
        ok = notify.send(load_cfg(), "✅ KK Compass 2 連線測試成功")
        print("成功" if ok else "失敗或未設定")
    else:
        print(__doc__)
