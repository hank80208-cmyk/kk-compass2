"""Telegram 通知。沒填 token 就只印在畫面上。"""
from __future__ import annotations

import json
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"
TF_NAME = {"4h": "短線（4H）", "1d": "波段（日線）"}


def _fp(x):
    a = abs(x)
    nd = 2 if a >= 100 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.1 else 6 if a >= 0.01 else 8
    return f"{x:,.{nd}f}"


def format_plan(p, link=None):
    d = p["dir"]
    head = {"A": "🟢 A 級", "B": "🔵 B 級"}.get(p["grade"], p["grade"])
    side = "做多" if d == 1 else "做空"
    lo = "低" if d == 1 else "高"
    stop_name = f"回檔{lo}" if p["stop_key"] == "pullback" else f"結構{lo}"
    hold = p.get("hold_med")
    hold_txt = f"約 {hold / 24:.0f} 天" if hold and hold >= 48 else (f"約 {hold:.0f} 小時" if hold else "—")
    px = p.get("position_x")
    pos_txt = (f"本金的 {px * 100:.0f}%" if px and px < 1 else f"本金的 {px:.1f} 倍" if px else "—")
    lines = [
        f"{head}｜{side} {p['symbol'][:-4]}｜{TF_NAME[p['tf']]}",
        f"{'不破低再過高' if d == 1 else '不過高再破低'}・確認 {p['time']}（台北）",
        "",
        f"進場　{_fp(p['entry'])}（或掛 {_fp(p['trigger'])} 等回踩）",
        f"停損　{_fp(p['stop'])}（{stop_name}，{p['risk_pct']:.1f}%）",
        f"止盈　{p['tp_text']}",
        f"持有　{hold_txt}",
        f"倉位　{pos_txt}（停損時虧本金 {p.get('risk_per_trade', 1):g}%）",
        "",
        f"BTC 日線 {p['btc_score']:+.0f}｜本幣日線 {p['score']:+.0f}",
    ]
    f = p.get("funding") or {}
    if f.get("rate_8h") is not None:
        extra = f"（近 30 日第 {f['pct']:.0f} 百分位）" if f.get("pct") is not None else ""
        lines.append(f"資金費率 8h {f['rate_8h']:+.4f}%{extra}")
        if f.get("pct") is not None and ((d == 1 and f["pct"] >= 90) or (d == -1 and f["pct"] <= 10)):
            lines.append("⚠️ 同方向的人很擠，留意軋空／多殺多")
    h = p.get("hist") or {}
    if h.get("n"):
        lines.append(f"回測：同級同方向 {h['n']} 筆・勝率 {h['win']:.0f}%・平均 {h['avg_r']:+.2f}R・最長連虧 {p.get('streak', '—')}")
    if link:
        lines.append(link)
    return "\n".join(lines)


def send(cfg, text, log=print):
    token, chat = cfg.get("telegram_bot_token"), cfg.get("telegram_chat_id")
    if not token or not chat:
        log("—— Telegram 未設定，訊息內容 ——\n" + text + "\n——")
        return False
    r = requests.post(API.format(token=token, method="sendMessage"),
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=20)
    if not r.ok:
        log(f"  ! Telegram 傳送失敗：{r.status_code} {r.text[:200]}")
    return r.ok


def send_file(cfg, path, caption="", log=print):
    token, chat = cfg.get("telegram_bot_token"), cfg.get("telegram_chat_id")
    if not token or not chat:
        return False
    with open(path, "rb") as fh:
        r = requests.post(API.format(token=token, method="sendDocument"),
                          data={"chat_id": chat, "caption": caption[:1000]},
                          files={"document": (os.path.basename(path), fh, "text/html")}, timeout=60)
    if not r.ok:
        log(f"  ! Telegram 檔案傳送失敗：{r.status_code} {r.text[:200]}")
    return r.ok


def load_sent(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError):
        return set()


def save_sent(path, keys):
    keys = sorted(keys)[-3000:]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(keys, fh)
