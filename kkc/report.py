"""產生 HTML 報告：總覽、單幣、回測。"""
from __future__ import annotations

import html
import json
import math
import os

import numpy as np
import pandas as pd

from . import backtest as bt
from . import signals as sg

ECHARTS = "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.1/echarts.min.js"
FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
         "&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+TC:wght@400;500;700&display=swap")

CSS = """
/* 版面：交易台儀表板。上方大盤儀表 → 今日訊號 → 篩選 → 全市場表。 */
:root{
  --bg:#eef0ec; --panel:#f9faf7; --ink:#182024; --muted:#5d686c; --line:#d5d9d2;
  --accent:#b9770e; --accent-soft:#f3e3c3;
  --long:#18865a; --long-soft:#d7efe3; --short:#c43d35; --short-soft:#f6dcd9;
  --gA:#b9770e; --gB:#4f6f8f; --gC:#7d8689; --gD:#8f4a6a;
  --f-display:"Barlow Condensed","Noto Sans TC",system-ui,sans-serif;
  --f-body:"Noto Sans TC",system-ui,-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;
  --f-mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0f1517; --panel:#161e21; --ink:#e3e8e6; --muted:#8e9a9c; --line:#28343a;
  --accent:#e5a43a; --accent-soft:#3a2d16;
  --long:#3cc28a; --long-soft:#123326; --short:#f0675d; --short-soft:#3a1a18;
  --gA:#e5a43a; --gB:#7fa3c7; --gC:#8e9a9c; --gD:#c47fa0; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0f1517; --panel:#161e21; --ink:#e3e8e6; --muted:#8e9a9c; --line:#28343a;
  --accent:#e5a43a; --accent-soft:#3a2d16;
  --long:#3cc28a; --long-soft:#123326; --short:#f0675d; --short-soft:#3a1a18;
  --gA:#e5a43a; --gB:#7fa3c7; --gC:#8e9a9c; --gD:#c47fa0; color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 var(--f-body);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0 48px}
.wrap{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:28px}
a{color:inherit}
header.top{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 20px;padding-block:18px 10px;
  border-bottom:1px solid var(--line)}
.brand{font:700 26px/1 var(--f-display);letter-spacing:.02em}
.brand b{color:var(--accent)}
.stamp{color:var(--muted);font:12px var(--f-mono)}
nav.links{margin-left:auto;display:flex;gap:14px;flex-wrap:wrap}
nav.links a{text-decoration:none;color:var(--muted);font-weight:500}
nav.links a[aria-current]{color:var(--ink);border-bottom:2px solid var(--accent)}
h1,h2,h3{text-wrap:balance;margin:0}
h2{font:600 22px/1.2 var(--f-display);letter-spacing:.02em;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h2 small{font:400 13px var(--f-body);color:var(--muted);letter-spacing:0}
h3{font:600 17px/1.3 var(--f-display);letter-spacing:.02em}
section{display:flex;flex-direction:column;gap:12px;min-width:0}
.note{color:var(--muted);font-size:13px;max-width:72ch}
.mono,td.num,.num{font-family:var(--f-mono);font-variant-numeric:tabular-nums}
.up{color:var(--long)} .dn{color:var(--short)} .mut{color:var(--muted)}
.chip{display:inline-flex;align-items:center;gap:4px;padding:1px 8px;border-radius:3px;font-size:12px;
  font-weight:600;white-space:nowrap;border:1px solid transparent}
.chip.long{background:var(--long-soft);color:var(--long)}
.chip.short{background:var(--short-soft);color:var(--short)}
.chip.g{color:var(--panel);font-family:var(--f-mono)}
.chip.gA{background:var(--gA)} .chip.gB{background:var(--gB)} .chip.gC{background:var(--gC)} .chip.gD{background:var(--gD)}
.chip.ghost{border-color:var(--line);color:var(--muted);font-weight:500}
.chip.ok{border-color:var(--long);color:var(--long);font-weight:500}
.chip.warn{border-color:var(--accent);color:var(--accent);font-weight:500}
.chip.bad{border-color:var(--line);color:var(--muted);font-weight:500;text-decoration:line-through}
/* 大盤儀表 */
.regime{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:20px;background:var(--panel);
  border:1px solid var(--line);padding:20px;border-radius:6px}
@media (max-width:760px){.regime{grid-template-columns:1fr}}
.regime .big{font:700 56px/1 var(--f-display);font-variant-numeric:tabular-nums}
.regime .lbl{font:600 15px var(--f-body);color:var(--muted);text-transform:none}
.gauge{position:relative;height:30px;margin-top:14px}
.gauge .track{position:absolute;inset:12px 0;background:var(--line);border-radius:2px}
.gauge .zone{position:absolute;top:8px;height:14px;opacity:.28}
.gauge .mark{position:absolute;top:2px;width:4px;height:26px;background:var(--ink);border-radius:1px;transform:translateX(-2px)}
.gticks{display:flex;justify-content:space-between;font:11px var(--f-mono);color:var(--muted)}
.guide{border-left:3px solid var(--accent);padding:4px 0 4px 14px;display:flex;flex-direction:column;gap:6px}
.guide strong{font-size:16px}
.items{display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;font-size:13px;align-items:center}
.bar{height:8px;background:var(--line);position:relative;border-radius:2px}
.bar i{position:absolute;top:0;bottom:0;border-radius:2px}
/* 訊號卡 */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;min-width:0}
.card.long{border-top:3px solid var(--long)} .card.short{border-top:3px solid var(--short)}
.card .head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.card .sym{font:700 22px/1 var(--f-display);text-decoration:none}
.kv{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:13px}
.kv dt{color:var(--muted)} .kv dd{margin:0;font-family:var(--f-mono);font-variant-numeric:tabular-nums;text-align:right}
.empty{background:var(--panel);border:1px dashed var(--line);border-radius:6px;padding:18px;color:var(--muted)}
/* 表格 */
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{font:600 12px var(--f-body);color:var(--muted);background:var(--panel);position:sticky;top:0;cursor:default}
th.sort{cursor:pointer} th.sort:hover{color:var(--ink)}
td.num,th.num{text-align:right}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--accent-soft)}
details{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px 14px}
details summary{cursor:pointer;font-weight:600}
details[open] summary{margin-bottom:10px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.stat{display:flex;flex-direction:column;gap:2px}
.stat .v{font:600 26px/1.1 var(--f-display);font-variant-numeric:tabular-nums}
.stat .k{color:var(--muted);font-size:12px}
.stats{display:flex;flex-wrap:wrap;gap:16px 28px}
.verdict{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:6px;padding:16px 18px;display:flex;flex-direction:column;gap:8px}
.verdict p{margin:0;max-width:80ch}
#chart{width:100%;height:520px;background:var(--panel);border:1px solid var(--line);border-radius:6px}
@media (max-width:600px){#chart{height:420px}}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tabs button{font:600 13px var(--f-body);background:var(--panel);color:var(--muted);border:1px solid var(--line);
  border-radius:4px;padding:4px 12px;cursor:pointer}
.tabs button[aria-pressed="true"]{color:var(--ink);border-color:var(--accent);background:var(--accent-soft)}
button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input#q{font:14px var(--f-body);padding:6px 10px;border:1px solid var(--line);border-radius:4px;background:var(--panel);color:var(--ink);width:min(260px,100%)}
footer{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:14px;display:flex;flex-direction:column;gap:6px}
"""

SORT_JS = """
document.querySelectorAll('table[data-sortable]').forEach(t=>{
  t.querySelectorAll('th.sort').forEach((th,i)=>{th.addEventListener('click',()=>{
    const idx=[...th.parentNode.children].indexOf(th), tb=t.tBodies[0];
    const dir=th.dataset.dir==='asc'?'desc':'asc'; th.dataset.dir=dir;
    const rows=[...tb.rows]; rows.sort((a,b)=>{
      const x=a.cells[idx].dataset.v, y=b.cells[idx].dataset.v;
      const nx=parseFloat(x), ny=parseFloat(y);
      let c=(isNaN(nx)||isNaN(ny))?String(x).localeCompare(String(y)):nx-ny;
      if(isNaN(nx)&&!isNaN(ny))c=1; if(!isNaN(nx)&&isNaN(ny))c=-1;
      return dir==='asc'?c:-c}); rows.forEach(r=>tb.appendChild(r));});});});
const q=document.getElementById('q'); if(q){q.addEventListener('input',()=>{
  const v=q.value.trim().toUpperCase(); document.querySelectorAll('#mkt tbody tr').forEach(r=>{
    r.hidden = v && !r.dataset.sym.includes(v);});});}
"""


# ---------------------------------------------------------------- 小工具
def e(x):
    return html.escape(str(x))


def fp(x, nd=None):
    """依價格大小決定小數位。"""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    x = float(x)
    if nd is None:
        a = abs(x)
        nd = 2 if a >= 100 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.1 else 6 if a >= 0.01 else 8
    return f"{x:,.{nd}f}"


def pct(x, nd=2, sign=True, cls=True):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return '<span class="mut">—</span>'
    s = f"{x:+.{nd}f}%" if sign else f"{x:.{nd}f}%"
    if not cls:
        return s
    c = "up" if x > 0 else "dn" if x < 0 else "mut"
    return f'<span class="{c}">{s}</span>'


def r_(x, nd=2):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    c = "up" if x > 0 else "dn" if x < 0 else "mut"
    return f'<span class="{c}">{x:+.{nd}f}R</span>'


def dir_chip(d):
    return '<span class="chip long">做多</span>' if d == 1 else '<span class="chip short">做空</span>'


def grade_chip(g):
    return f'<span class="chip g g{g}" title="{e(sg.GRADE_TEXT.get(g, ""))}">{g}</span>'


def v(x):
    """排序用的 data-v。"""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return ""
    return str(x)


def page(title, body, nav, ctx, extra_head="", artifact=False):
    nav_html = "".join(f'<a href="{href}"{" aria-current=page" if cur else ""}>{e(lbl)}</a>'
                       for lbl, href, cur in nav)
    head = (f'<title>{e(title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="stylesheet" href="{FONTS}">\n<style>{CSS}{CSS2}</style>\n{extra_head}')
    content = (f'<div class="wrap"><header class="top"><span class="brand">KK <b>Compass</b> 2</span>'
               f'<span class="stamp">更新 {e(ctx["now_tw"])}（台北）</span><nav class="links">{nav_html}</nav></header>'
               f'{body}<footer><span>資料：Binance 公開現貨行情（K 線）、Hyperliquid（資金費率）。'
               f'所有訊號只用已收盤 K 棒計算。</span><span>這是規則式分析工具的輸出，不是投資建議；'
               f'回測結果代表過去，不保證未來。</span></footer></div><script>{SORT_JS}</script>')
    if artifact:
        return head + content
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            + head + '</head><body>' + content + '</body></html>')


def nav_for(level, cur):
    pre = "../" if level else ""
    return [("總覽", f"{pre}index.html", cur == "index"), ("回測驗證", f"{pre}backtest.html", cur == "bt")]


# ---------------------------------------------------------------- 大盤

CSS2 = """
.rec{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:18px 20px;display:flex;flex-direction:column;gap:14px;min-width:0}
.rec.long{border-left:5px solid var(--long)} .rec.short{border-left:5px solid var(--short)} .rec.wait{border-left:5px solid var(--gC)}
.rec .act{font:700 34px/1 var(--f-display);letter-spacing:.02em}
.rec .act.long{color:var(--long)} .rec .act.short{color:var(--short)} .rec .act.wait{color:var(--muted)}
.rec .row{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline}
.plan{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.plan .cell{border:1px solid var(--line);border-radius:4px;padding:8px 12px;display:flex;flex-direction:column;gap:2px;min-width:0}
.plan .cell .k{color:var(--muted);font-size:12px}
.plan .cell .v{font:600 18px/1.3 var(--f-mono);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.plan .cell .s{color:var(--muted);font-size:12px}
.warnline{color:var(--accent);font-weight:600}
.recs{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
@media (max-width:420px){.recs{grid-template-columns:1fr}}
.tfchip{font:600 11px var(--f-body);padding:1px 6px;border-radius:3px;border:1px solid var(--line);color:var(--ink)}
"""

TF_NAME = {"4h": "短線（4H）", "1d": "波段（日線）"}


# ---------------------------------------------------------------- 大盤
def regime_block(ctx):
    s = ctx["btc_score"]
    strong = ctx["cfg"]["btc_strong_score"]
    pos = (s + 7) / 14 * 100
    if s >= strong:
        title, txt = "BTC 多頭明確：只考慮做多", "回測中，順著 BTC 明確趨勢的結構訊號在短線和波段都是正的；逆勢做空會被標成 D 級。"
    elif s <= -strong:
        title, txt = "BTC 空頭明確：只考慮做空", "回測中，順著 BTC 明確趨勢的結構訊號在短線和波段都是正的；逆勢做多會被標成 D 級。"
    else:
        title, txt = "BTC 在震盪區：觀望", "BTC 分數介於 −3 與 +3 之間時，短線與波段的結構訊號在 6 年回測裡都是負的。這時候不出 A 級，最好的策略是等。"
    bull = "BTC 在 200 日均線之上（長期牛市結構）" if ctx["btc_bull"] else "BTC 在 200 日均線之下（長期熊市結構）"
    items = ""
    for k, name, w, desc in sg.SCORE_ITEMS:
        val = ctx["btc_items"].get(k, 0)
        left = 50 if val >= 0 else 50 - abs(val) / w * 50
        width = abs(val) / w * 50
        col = "var(--long)" if val > 0 else "var(--short)"
        items += (f'<span title="{e(desc)}">{e(name)}</span><span class="bar"><i style="left:{left}%;width:{width}%;'
                  f'background:{col}"></i></span><span class="num">{val:+.0f}/{w}</span>')
    cls = "up" if s > 0 else "dn" if s < 0 else ""
    zw = (7 - strong + 1) / 14 * 100
    return f"""
<section class="regime" aria-label="大盤狀態">
  <div>
    <div class="lbl">BTC 日線方向分數（−7 ~ +7）　現價 <span class="mono">{fp(ctx['btc_price'], 0)}</span></div>
    <div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap">
      <span class="big {cls}">{s:+.0f}</span><span style="font:600 24px var(--f-display)">{e(ctx['btc_label'])}</span></div>
    <div class="gauge" role="img" aria-label="分數 {s:+.0f}">
      <div class="track"></div>
      <div class="zone" style="left:0;width:{zw:.1f}%;background:var(--short)"></div>
      <div class="zone" style="right:0;width:{zw:.1f}%;background:var(--long)"></div>
      <div class="mark" style="left:{pos:.1f}%"></div>
    </div>
    <div class="gticks"><span>−7</span><span>−{strong}</span><span>0</span><span>+{strong}</span><span>+7</span></div>
    <p class="note" style="margin:10px 0 0">{e(bull)}，200 日均線 <span class="mono">{fp(ctx['btc_ema200'], 0)}</span>。
    6 年回測裡，牛熊本身沒有比「BTC 日線分數」多提供資訊，所以只列出來參考，不參與分級。</p>
  </div>
  <div style="display:flex;flex-direction:column;gap:14px;min-width:0">
    <div class="guide"><strong>{e(title)}</strong><span class="note">{e(txt)}</span></div>
    <div class="items">{items}</div>
  </div>
</section>"""


# ---------------------------------------------------------------- 策略卡
def hist_line(p):
    h = p.get("hist") or {}
    o = p.get("hist_oos") or {}
    if not h.get("n"):
        return "回測樣本不足"
    return (f"同級同方向 6 年 {h['n']} 筆：勝率 {h['win']:.0f}%、平均 {r_(h['avg_r'])}；"
            f"樣本外 {o.get('n', 0)} 筆 平均 {r_(o.get('avg_r'))}；最長連虧 {p.get('streak') or '—'} 筆")


def plan_cells(p, cfg):
    d = p["dir"]
    lo = "低" if d == 1 else "高"
    stop_name = f"回檔{lo}" if p["stop_key"] == "pullback" else f"結構{lo}"
    hold = p.get("hold_med")
    hold_txt = (f"約 {hold / 24:.0f} 天" if hold and hold >= 48 else f"約 {hold:.0f} 小時" if hold else "—")
    px = p.get("position_x")
    pos_txt = (f"本金的 {px * 100:.0f}%" if px and px < 1 else f"本金的 {px:.1f} 倍（需 {px:.1f}x 槓桿）" if px else "—")
    return f"""<div class="plan">
<div class="cell"><span class="k">進場</span><span class="v">{fp(p['entry'])}</span><span class="s">{"日線" if p['tf'] == '1d' else "4H"}收盤確認價；可在 {fp(p['trigger'])} 掛單等回踩</span></div>
<div class="cell"><span class="k">停損（{stop_name}）</span><span class="v">{fp(p['stop'])}</span><span class="s">距進場 {p['risk_pct']:.1f}%</span></div>
<div class="cell"><span class="k">止盈</span><span class="v" style="font-size:14px;font-family:var(--f-body)">{e(p['tp_text'])}</span></div>
<div class="cell"><span class="k">預估持有</span><span class="v">{hold_txt}</span><span class="s">歷史中位數；最長 {"60 天" if p['tf'] == '1d' else "7 天"}，到期出場</span></div>
<div class="cell"><span class="k">建議倉位</span><span class="v">{pos_txt}</span><span class="s">停損時虧本金 {p.get('risk_per_trade', 1):g}%（依回測最大回撤換算）</span></div>
</div>"""


def rec_card(rec, ctx, level=0, big=False):
    cfg = ctx["cfg"]
    sym = rec["symbol"]
    pre = "coin/" if level == 0 else ""
    if rec["action"] == "觀望":
        waits = ""
        for w in sorted(rec["waits"], key=lambda w: abs(w["dist"]))[:4]:
            crossed = (w["dist"] <= 0) if w["dir"] == 1 else (w["dist"] >= 0)
            where = ("現價已越過，等這根收盤確認" if crossed else f"距現價 {pct(w['dist'])}")
            waits += (f'<li>{TF_NAME[w["tf"]]}{"做多" if w["dir"] == 1 else "做空"}：收盤{"站上" if w["dir"] == 1 else "跌破"} '
                      f'<span class="mono">{fp(w["trigger"])}</span>（{where}），且不{"破" if w["dir"] == 1 else "過"} '
                      f'<span class="mono">{fp(w["hold"])}</span>。依目前 BTC，確認後會是 <b>{e(w["grade_if"])}</b> 級</li>')
        weak = [p for p in rec["picks"] if not p["ok"]]
        weak_txt = ""
        if weak:
            weak_txt = '<p class="note" style="margin:0">有結構確認，但這個等級／方向在回測裡不賺錢：' + "、".join(
                f'{TF_NAME[p["tf"]]}{"做多" if p["dir"] == 1 else "做空"} {p["grade"]} 級' for p in weak) + "</p>"
        return f"""<article class="rec wait">
<div class="row"><a class="act wait" href="{pre}{e(sym)}.html" style="text-decoration:none">{e(sym[:-4])}　觀望</a></div>
{weak_txt}
<div><span class="k mut">等待的條件</span><ul style="margin:6px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:4px">{waits or '<li>目前沒有成形的結構</li>'}</ul></div>
</article>"""
    p = rec["main"]
    cls = "long" if p["dir"] == 1 else "short"
    f = p.get("funding") or {}
    crowd = ""
    if f.get("pct") is not None and ((p["dir"] == 1 and f["pct"] >= 90) or (p["dir"] == -1 and f["pct"] <= 10)):
        crowd = '<span class="chip warn">資金費率擁擠</span>'
    chase = f'<p class="warnline" style="margin:0">{e(rec["chase"])}</p>' if rec.get("chase") else ""
    others = [x for x in rec["picks"] if x is not p and x["ok"]]
    also = ""
    if others:
        also = '<p class="note" style="margin:0">同時成立：' + "、".join(
            f'{TF_NAME[x["tf"]]}{"做多" if x["dir"] == 1 else "做空"} {x["grade"]} 級' for x in others) + "</p>"
    return f"""<article class="rec {cls}">
<div class="row"><a class="act {cls}" href="{pre}{e(sym)}.html" style="text-decoration:none">{e(sym[:-4])}　{e(rec['action'])}</a>
{grade_chip(p['grade'])}<span class="tfchip">{TF_NAME[p['tf']]}</span>{crowd}
<span class="stamp" style="margin-left:auto">確認 {e(p['time'])}・現價 {fp(ctx_price(ctx, sym))}</span></div>
{plan_cells(p, cfg)}
{chase}
<p class="note" style="margin:0">{hist_line(p)}</p>
<p class="note" style="margin:0">方案：{e(p['strat_name'])}</p>
{also}
</article>"""


def ctx_price(ctx, sym):
    for r in ctx["rows"]:
        if r["symbol"] == sym:
            return r["price"]
    return None


# ---------------------------------------------------------------- 總覽頁
def render_index(ctx, artifact=False):
    recs = ctx["recs"]
    act = [r for r in recs.values() if r["action"] != "觀望"]
    act.sort(key=lambda r: ({"A": 0, "B": 1}[r["main"]["grade"]], r["main"]["tf"] != "1d"))
    strong = ctx["cfg"]["btc_strong_score"]
    cards = "".join(rec_card(r, ctx) for r in act)
    if not cards:
        cards = ('<div class="empty">今天沒有回測支持的進場機會。'
                 + ("BTC 在震盪區，6 年回測裡這種時候進場平均是虧的。" if abs(ctx["btc_score"]) < strong else
                    "BTC 方向明確，但目前沒有幣種剛完成結構確認。下方「觀察名單」是快要觸發的。") + "</div>")
    else:
        cards = f'<div class="recs">{cards}</div>'
    # 觀察名單：BTC 明確時，距觸發 3% 以內、會是 A/B 的
    watch = []
    for r in recs.values():
        if r["action"] != "觀望":
            continue
        for w in r["waits"]:
            if w["grade_if"] == "A/B" and abs(w["dist"]) <= 3:
                watch.append((r["symbol"], w))
    watch.sort(key=lambda x: abs(x[1]["dist"]))
    wrows = "".join(
        f'<tr><td><a href="coin/{e(s)}.html">{e(s[:-4])}</a></td><td>{TF_NAME[w["tf"]]}</td><td>{dir_chip(w["dir"])}</td>'
        f'<td class="num">{fp(w["trigger"])}</td><td class="num">{pct(w["dist"])}</td><td class="num">{fp(w["hold"])}</td></tr>'
        for s, w in watch[:30])
    watch_html = ""
    if abs(ctx["btc_score"]) >= strong:
        watch_html = (f'<section><h2>觀察名單 <small>BTC 方向明確，這些幣距離結構確認不到 3%，確認後會是 A／B 級</small></h2>'
                      + (f'<div class="tbl"><table><thead><tr><th>幣</th><th>週期</th><th>方向</th><th class="num">觸發價（收盤）</th>'
                         f'<th class="num">距現價</th><th class="num">不可破</th></tr></thead><tbody>{wrows}</tbody></table></div>'
                         if wrows else '<div class="empty">目前沒有接近觸發的幣。</div>') + '</section>')
    # 篩選命中
    btc_ctx = ctx["backtest"]
    rule_map = {r["id"]: r for r in (btc_ctx["rules"] if btc_ctx else sg.RULES)}
    hit_rows = ""
    for row in sorted(ctx["rows"], key=lambda r: -len(r["rules"])):
        if not row["rules"]:
            continue
        chips = ""
        for rid in row["rules"]:
            r = rule_map[rid]
            vd = r.get("verdict", "")
            c = "ok" if vd == "兩段都贏基準" else "ghost" if vd in ("不穩定", "樣本太少") else "bad"
            chips += f'<span class="chip {c}" title="{e(vd)}">{"▲" if r["dir"] == 1 else "▼"} {e(r["name"])}</span> '
        hit_rows += (f'<tr><td><a href="coin/{e(row["symbol"])}.html">{e(row["base"])}</a></td>'
                     f'<td class="num">{fp(row["price"])}</td><td class="num">{pct(row["chg24"])}</td>'
                     f'<td class="num">{row["score"]:+.0f}</td><td style="white-space:normal;min-width:260px">{chips}</td></tr>')
    hits = (f'<div class="tbl"><table><thead><tr><th>幣</th><th class="num">價格</th><th class="num">24h</th>'
            f'<th class="num">日線分數</th><th>今日命中（綠框＝樣本內外都贏基準；灰＝不穩定；刪除線＝沒有優勢）</th>'
            f'</tr></thead><tbody>{hit_rows}</tbody></table></div>') if hit_rows else \
        '<div class="empty">今天沒有幣種命中日線篩選規則。</div>'
    # 市場總表
    trs = ""
    for r in ctx["rows"]:
        f = r["funding"] or {}
        rec = recs[r["symbol"]]
        a = rec["action"]
        ac = (f'<span class="chip {"long" if a == "做多" else "short"}">{e(a)} {rec["main"]["grade"]}・{"波段" if rec["main"]["tf"] == "1d" else "短線"}</span>'
              if a != "觀望" else '<span class="mut">觀望</span>')
        def dist(lv, side):
            x = lv.get(side)
            if not x or x["already"]:
                return None
            return (x["trigger"] / r["price"] - 1) * 100
        dl4, ds4 = dist(r["levels"], "long"), dist(r["levels"], "short")
        dld, dsd = dist(r["levels_d"], "long"), dist(r["levels_d"], "short")
        sc = r["score"]
        trs += (f'<tr data-sym="{e(r["base"])}"><td data-v="{e(r["base"])}"><a href="coin/{e(r["symbol"])}.html">{e(r["base"])}</a></td>'
                f'<td data-v="{0 if a == "觀望" else 1}">{ac}</td>'
                f'<td class="num" data-v="{v(r["price"])}">{fp(r["price"])}</td>'
                f'<td class="num" data-v="{v(r["chg24"])}">{pct(r["chg24"])}</td>'
                f'<td class="num" data-v="{v(r["chg7"])}">{pct(r["chg7"])}</td>'
                f'<td class="num" data-v="{v(r["rs30"])}">{pct(r["rs30"])}</td>'
                f'<td class="num" data-v="{v(sc)}"><span class="{"up" if (sc or 0) > 0 else "dn" if (sc or 0) < 0 else ""}">{(f"{sc:+.0f}" if sc is not None else "—")}</span> <span class="mut">{e(r["label"])}</span></td>'
                f'<td class="num" data-v="{v(dld)}">{pct(dld) if dld is not None else "—"}</td>'
                f'<td class="num" data-v="{v(dsd)}">{pct(dsd) if dsd is not None else "—"}</td>'
                f'<td class="num" data-v="{v(dl4)}">{pct(dl4) if dl4 is not None else "—"}</td>'
                f'<td class="num" data-v="{v(ds4)}">{pct(ds4) if ds4 is not None else "—"}</td>'
                f'<td class="num" data-v="{v(f.get("rate_8h"))}">{(f"{f["rate_8h"]:+.4f}%" if f.get("rate_8h") is not None else "—")}</td>'
                f'<td class="num" data-v="{v(f.get("pct"))}">{(f"{f["pct"]:.0f}" if f.get("pct") is not None else "—")}</td>'
                f'<td class="num" data-v="{v(r["from_high"])}">{pct(r["from_high"], 1)}</td>'
                f'<td class="num" data-v="{v(r["atr_pct"])}">{(f"{r["atr_pct"]:.1f}%" if r["atr_pct"] is not None else "—")}</td></tr>')
    th = lambda t, num=True: f'<th class="sort{" num" if num else ""}">{t}</th>'  # noqa
    mkt = (f'<div class="tbl" style="max-height:640px"><table id="mkt" data-sortable><thead><tr>{th("幣", False)}{th("建議", False)}{th("價格")}{th("24h")}{th("7d")}'
           f'{th("30 日 vs BTC")}{th("日線分數")}{th("波段多方觸發")}{th("波段空方觸發")}{th("短線多方觸發")}{th("短線空方觸發")}'
           f'{th("資金費率 8h")}{th("費率百分位")}{th("距一年高")}{th("日波動")}</tr></thead><tbody>{trs}</tbody></table></div>')
    bsum = ""
    if btc_ctx:
        parts = []
        for tf in ("1d", "4h"):
            st = btc_ctx["strategies"][tf]
            a = st["grades"]["A"]
            rc = st["random"]
            parts.append(f'{TF_NAME[tf]} A 級樣本外 {a["oos"].get("n", 0)} 筆，平均 {r_(a["oos"].get("avg_r"))}'
                         f'（同條件隨機 {r_(rc["oos"].get("avg_r"))}）')
        bsum = f'<p class="note">6 年回測：{"；".join(parts)}。<a href="backtest.html">看完整回測</a></p>'
    body = f"""
{regime_block(ctx)}
<section><h2>今日策略建議 <small>只列回測支持的：A／B 級、BTC 同向、該方向在 6 年與樣本外都為正</small></h2>
{bsum}{cards}</section>
{watch_html}
<section><h2>日線篩選命中 <small>最新日 K（台北 08:00 收盤）</small></h2>{hits}</section>
<section><h2>全市場 <small>{ctx['n']} 個幣（Binance 成交額前段、且有永續合約）・點欄位排序</small></h2>
<input id="q" type="search" placeholder="搜尋幣名，例如 SOL" aria-label="搜尋幣名">
<p class="note">「觸發」：現價離結構確認的收盤價還差多少（前提是關鍵低／高點沒破）。波段看日線、短線看 4H。
資金費率百分位是目前費率在近 30 日的位置，90 以上代表做多的人很擠，10 以下代表做空的人很擠。</p>
{mkt}</section>"""
    return page("KK Compass 2", body, nav_for(0, "index"), ctx, artifact=artifact)


# ---------------------------------------------------------------- 單幣頁
def chart_payload(a, cfg):
    d = a["daily"].tail(500)
    h4 = a["h4"].tail(540)
    d0 = len(a["daily"]) - len(d)
    h40 = len(a["h4"]) - len(h4)
    k = cfg["pivot_k"]

    def ser(df, cols):
        return {c: [None if not np.isfinite(x) else round(float(x), 10) for x in df[c].values] for c in cols}

    def pack(df, i0, full, ph, pl, sets, fmt, cols):
        P = dict(t=[x.tz_convert("Asia/Taipei").strftime(fmt) for x in df.index],
                 k=[[float(o), float(c), float(l), float(h)] for o, c, l, h in df[["open", "close", "low", "high"]].values],
                 v=[float(x) for x in df["quote_volume"].values], **ser(df, cols))
        P["piv"] = [[i - i0, float(full["high"].iloc[i] if ph[i] else full["low"].iloc[i]), "H" if ph[i] else "L"]
                    for i in range(i0, len(full) - k) if ph[i] or pl[i]]
        P["sets"] = [[s["t"] - i0, float(s["entry"]), s["dir"], s["grade"]] for s in sets if s["t"] >= i0]
        return P
    return dict(D=pack(d, d0, a["daily"], a["phd"], a["pld"], a["dsetups"], "%Y-%m-%d", ["ema20", "ema50", "ema200"]),
                H=pack(h4, h40, a["h4"], a["ph"], a["pl"], a["setups"], "%m-%d %H:%M", ["ema20", "ema50"]))


CHART_JS = """
const P = __DATA__, LV = __LEVELS__;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let chart, mode = 'D';
function opt(){
  const X = P[mode], up = css('--long'), dn = css('--short'), ink = css('--ink'), mut = css('--muted'), line = css('--line'), acc = css('--accent');
  const series = [{type:'candlestick', name:'K', data:X.k, itemStyle:{color:up,color0:dn,borderColor:up,borderColor0:dn}},
    {type:'line', name:'EMA20', data:X.ema20, showSymbol:false, lineStyle:{width:1.2,color:acc}},
    {type:'line', name:'EMA50', data:X.ema50, showSymbol:false, lineStyle:{width:1.2,color:css('--gB')}}];
  if (mode==='D') series.push({type:'line', name:'EMA200', data:X.ema200, showSymbol:false, lineStyle:{width:1.4,color:css('--gD')}});
  series.push({type:'bar', name:'成交額', data:X.v, xAxisIndex:1, yAxisIndex:1, itemStyle:{color:line}});
  series.push({type:'scatter', name:'擺動點', symbolSize:7, data:X.piv.map(p=>({value:[p[0],p[1]], symbol:'triangle', symbolRotate:p[2]==='H'?180:0, itemStyle:{color:mut}})), z:5});
  series.push({type:'scatter', name:'結構確認', symbolSize:18, data:X.sets.map(s=>({value:[s[0],s[1]], symbol:'pin', itemStyle:{color:s[2]===1?up:dn}, label:{show:true, formatter:s[3], color:css('--panel'), fontSize:10, fontWeight:700}})), z:6});
  const lv = LV[mode], mk = [];
  if (lv.long && !lv.long.already) mk.push({yAxis:lv.long.trigger, lineStyle:{color:up,type:'dashed'}, label:{formatter:'多方觸發 {c}', color:up}});
  if (lv.long) mk.push({yAxis:lv.long.hold, lineStyle:{color:up,type:'dotted'}, label:{formatter:'不可破低 {c}', color:up}});
  if (lv.short && !lv.short.already) mk.push({yAxis:lv.short.trigger, lineStyle:{color:dn,type:'dashed'}, label:{formatter:'空方觸發 {c}', color:dn}});
  if (lv.short) mk.push({yAxis:lv.short.hold, lineStyle:{color:dn,type:'dotted'}, label:{formatter:'不可過高 {c}', color:dn}});
  if (mk.length) series[0].markLine = {symbol:'none', data:mk, label:{position:'insideEndTop', fontSize:11}};
  const st = mode==='H'?65:70;
  return {animation:false, backgroundColor:'transparent', textStyle:{color:ink},
    tooltip:{trigger:'axis', axisPointer:{type:'cross'}, backgroundColor:css('--panel'), borderColor:line, textStyle:{color:ink}},
    axisPointer:{link:[{xAxisIndex:'all'}]},
    grid:[{left:56,right:64,top:16,height:'64%'},{left:56,right:64,top:'76%',height:'12%'}],
    xAxis:[{type:'category',data:X.t,axisLine:{lineStyle:{color:line}},axisLabel:{color:mut}},
           {type:'category',gridIndex:1,data:X.t,axisLabel:{show:false},axisLine:{lineStyle:{color:line}}}],
    yAxis:[{scale:true,position:'right',splitLine:{lineStyle:{color:line,opacity:.6}},axisLabel:{color:mut}},
           {gridIndex:1,scale:true,axisLabel:{show:false},splitLine:{show:false}}],
    dataZoom:[{type:'inside',xAxisIndex:[0,1],start:st,end:100},{type:'slider',xAxisIndex:[0,1],bottom:4,height:16,start:st,end:100,textStyle:{color:mut},borderColor:line}],
    series};
}
function draw(){ if(!window.echarts){document.getElementById('chart').textContent='圖表載入失敗（需要網路連線）';return;}
  if(!chart) chart = echarts.init(document.getElementById('chart'));
  chart.setOption(opt(), true); }
document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{
  mode=b.dataset.m; document.querySelectorAll('.tabs button').forEach(x=>x.setAttribute('aria-pressed', x===b)); draw();}));
window.addEventListener('resize',()=>chart&&chart.resize());
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
draw();
"""


def lvl_card(lv, key, tf, row, ctx):
    x = lv.get(key)
    dsign = 1 if key == "long" else -1
    title = ("做多：不破低，再過高" if key == "long" else "做空：不過高，再破低")
    if not x:
        return (f'<div class="card"><h3>{title}</h3><p class="note" style="margin:0">目前沒有成形的結構'
                f'（{"低點已被跌破，或還沒出現反彈高點" if key == "long" else "高點已被突破，或還沒出現回落低點"}）。</p></div>')
    strong = ctx["cfg"]["btc_strong_score"]
    b = ctx["btc_score"]
    g = ("A 或 B 級（依停損寬度）" if b * dsign >= strong else "D 級（逆 BTC，回測為負）" if b * dsign <= -strong
         else "C 級（BTC 震盪，回測為負）")
    unit = "4H" if tf == "4h" else "日線"
    dist = (x["trigger"] / row["price"] - 1) * 100
    crossed = (dist <= 0) if key == "long" else (dist >= 0)
    state = ("最近已經收盤越過觸發價" if x["already"] else
             f'現價已越過觸發價 {fp(x["trigger"])}，等這根{unit}收盤確認' if crossed else
             f'等待 {unit}收盤{"站上" if key == "long" else "跌破"} {fp(x["trigger"])}（距現價 {pct(dist)}）')
    return (f'<div class="card {"long" if key == "long" else "short"}"><h3>{title}</h3><dl class="kv">'
            f'<dt>{"不可破的低點" if key == "long" else "不可過的高點"}</dt><dd>{fp(x["hold"])} <span class="mut">{e(x["hold_time"])}</span></dd>'
            f'<dt>觸發價</dt><dd>{fp(x["trigger"])} <span class="mut">{e(x["trigger_time"])}</span></dd>'
            f'</dl><p class="note" style="margin:0">{state}</p><p class="note" style="margin:0">依目前 BTC，確認後會是 {e(g)}</p></div>')


def coin_history(sym, ctx):
    b = ctx["backtest"]
    if not b:
        return ""
    out = ""
    for tf in ("1d", "4h"):
        st = b["strategies"][tf]
        pc = st["per_coin"].get(sym)
        if not pc:
            continue
        al, aa = pc["all"], pc["A"]
        trs = "".join(
            f'<tr><td class="num">{pd.Timestamp(t["signal_time"]).tz_convert("Asia/Taipei").strftime("%Y-%m-%d %H:%M")}</td>'
            f'<td>{dir_chip(t["dir"])}</td><td>{grade_chip(t["grade"])}</td><td class="num">{r_(t["r"])}</td>'
            f'<td>{e(t["reason"])}</td><td class="num">{(f"{t["hours"] / 24:.1f} 天" if t["hours"] >= 48 else f"{t["hours"]:.0f}h")}</td></tr>'
            for t in reversed(pc["recent"]))
        out += f"""<div class="card"><h3>{TF_NAME[tf]}　<small class="mut" style="font:400 12px var(--f-body)">{e(st['best_name'])}</small></h3>
<div class="stats"><div class="stat"><span class="v">{al.get('n', 0)}</span><span class="k">全部訊號</span></div>
<div class="stat"><span class="v">{al.get('win', 0):.0f}%</span><span class="k">勝率</span></div>
<div class="stat"><span class="v">{r_(al.get('avg_r'))}</span><span class="k">平均每筆</span></div>
<div class="stat"><span class="v">{aa.get('n', 0)}</span><span class="k">A 級筆數</span></div>
<div class="stat"><span class="v">{r_(aa.get('avg_r')) if aa.get('n') else '—'}</span><span class="k">A 級平均</span></div></div>
<div class="tbl"><table><thead><tr><th>確認時間</th><th>方向</th><th>等級</th><th class="num">結果</th><th>出場</th><th class="num">持有</th></tr></thead><tbody>{trs}</tbody></table></div></div>"""
    if not out:
        return ""
    return (f'<section><h2>這個幣的歷史訊號 <small>單一幣樣本少、波動大，全市場統計比較可靠</small></h2>'
            f'<div class="grid2">{out}</div></section>')


def render_coin(sym, a, row, ctx, artifact=False):
    cfg = ctx["cfg"]
    d = a["daily"].iloc[-1]
    sc = float(d["score"]) if np.isfinite(d["score"]) else 0
    items = ""
    for k, name, w, desc in sg.SCORE_ITEMS:
        val = float(d[k])
        left = 50 if val >= 0 else 50 - abs(val) / w * 50
        width = abs(val) / w * 50
        col = "var(--long)" if val > 0 else "var(--short)"
        items += (f'<span title="{e(desc)}">{e(name)}</span><span class="bar"><i style="left:{left}%;width:{width}%;'
                  f'background:{col}"></i></span><span class="num">{val:+.0f}/{w}</span>')
    f = row["funding"] or {}
    rec = ctx["recs"][sym]
    payload = json.dumps(chart_payload(a, cfg), separators=(",", ":"))
    js = CHART_JS.replace("__DATA__", payload).replace("__LEVELS__", json.dumps({"D": row["levels_d"], "H": row["levels"]}))
    btc_ctx = ctx["backtest"]
    rules_today = ""
    if row["rules"]:
        rm = {r["id"]: r for r in (btc_ctx["rules"] if btc_ctx else sg.RULES)}
        rules_today = "".join(f'<span class="chip ghost">{"▲" if rm[x]["dir"] == 1 else "▼"} {e(rm[x]["name"])}・{e(rm[x].get("verdict", ""))}</span> '
                              for x in row["rules"])
    body = f"""
<section style="flex-direction:row;flex-wrap:wrap;align-items:flex-end;gap:12px 28px">
  <div><div class="lbl mut">{e(sym)}</div><div style="font:700 44px/1 var(--f-display)">{e(sym[:-4])} <span class="mono" style="font-size:28px">{fp(row['price'])}</span></div></div>
  <div class="stats">
    <div class="stat"><span class="v">{pct(row['chg24'])}</span><span class="k">24 小時</span></div>
    <div class="stat"><span class="v">{pct(row['chg7'])}</span><span class="k">7 天</span></div>
    <div class="stat"><span class="v">{pct(row['rs30'])}</span><span class="k">30 天相對 BTC</span></div>
    <div class="stat"><span class="v">{(f"{f['rate_8h']:+.4f}%" if f.get('rate_8h') is not None else '—')}</span><span class="k">資金費率 8h{(f"（第 {f['pct']:.0f} 百分位）" if f.get('pct') is not None else '')}</span></div>
    <div class="stat"><span class="v">{row['atr_pct']:.1f}%</span><span class="k">日波動（ATR）</span></div>
  </div>
</section>
<section><h2>策略建議 <small>BTC {ctx['btc_score']:+.0f}（{e(ctx['btc_label'])}）・只在回測支持時才給方向</small></h2>{rec_card(rec, ctx, level=1, big=True)}</section>
<section><h2>K 線 <small>▲▼ 擺動點、圖釘＝結構確認（標等級）、虛線＝觸發價、點線＝不可破的高低點</small></h2>
<div class="tabs" role="group" aria-label="週期"><button data-m="D" aria-pressed="true">日線（波段）</button><button data-m="H" aria-pressed="false">4H（短線）</button></div>
<div id="chart" role="img" aria-label="{e(sym)} K 線圖"></div></section>
<section><h2>波段（日線）結構</h2><div class="grid2">{lvl_card(row['levels_d'], 'long', '1d', row, ctx)}{lvl_card(row['levels_d'], 'short', '1d', row, ctx)}</div></section>
<section><h2>短線（4H）結構</h2><div class="grid2">{lvl_card(row['levels'], 'long', '4h', row, ctx)}{lvl_card(row['levels'], 'short', '4h', row, ctx)}</div></section>
<section class="grid2">
  <div class="card"><h3>日線方向　<span class="{'up' if sc > 0 else 'dn' if sc < 0 else ''}">{sc:+.0f}</span> {e(sg.score_label(sc))}</h3>
    <div class="items">{items}</div>
    <p class="note" style="margin:0">回測顯示幣種自己的方向對結果影響不大，有區分力的是 BTC 的方向。這裡讓你知道它在大週期的位置。</p></div>
  <div class="card"><h3>日線位置</h3><dl class="kv">
    <dt>EMA20 / 50 / 200</dt><dd>{fp(d['ema20'])} / {fp(d['ema50'])} / {fp(d['ema200'])}</dd>
    <dt>距一年高點 / 低點</dt><dd>{pct(row['from_high'], 1)} / {pct(row['from_low'], 1)}</dd>
    <dt>RSI(14) / KD</dt><dd>{d['rsi']:.0f} / {d['k']:.0f}・{d['d']:.0f}</dd>
    <dt>量比（成交額÷20 日均）</dt><dd>{d['vol_ratio']:.2f}</dd>
    <dt>今日命中篩選</dt><dd style="white-space:normal">{rules_today or '—'}</dd></dl></div>
</section>
{coin_history(sym, ctx)}"""
    head = f'<script src="{ECHARTS}"></script>'
    return page(f"{sym[:-4]} 結構分析", body + f"<script>{js}</script>", nav_for(1, ""), ctx, extra_head=head, artifact=artifact)


# ---------------------------------------------------------------- 回測頁
STAT_HEAD = ('<th class="num">筆數</th><th class="num">勝率</th><th class="num">平均</th><th class="num">t 值</th>'
             '<th class="num">獲利因子</th><th class="num">累計</th><th class="num">最大回撤</th>')
STAT_HEAD_S = '<th class="num">筆數</th><th class="num">勝率</th><th class="num">平均</th><th class="num">t 值</th><th class="num">持有中位</th>'


def stat_cells(s):
    if not s or not s.get("n"):
        return '<td class="num">0</td>' + '<td class="num">—</td>' * 6
    pf = s["pf"]
    return (f'<td class="num">{s["n"]:,}</td><td class="num">{s["win"]:.1f}%</td><td class="num">{r_(s["avg_r"])}</td>'
            f'<td class="num">{s.get("t", 0):+.1f}</td><td class="num">{(f"{pf:.2f}" if math.isfinite(pf) else "∞")}</td>'
            f'<td class="num">{s["total_r"]:+.0f}R</td><td class="num">{s["max_dd_r"]:.0f}R</td>')


def stat_cells_s(s):
    if not s or not s.get("n"):
        return '<td class="num">0</td>' + '<td class="num">—</td>' * 4
    h = s.get("med_hours", 0)
    return (f'<td class="num">{s["n"]:,}</td><td class="num">{s["win"]:.0f}%</td><td class="num">{r_(s["avg_r"])}</td>'
            f'<td class="num">{s.get("t", 0):+.1f}</td><td class="num">{(f"{h / 24:.1f} 天" if h >= 48 else f"{h:.0f}h")}</td>')


def strategy_section(st, cfg):
    tf = st["tf"]
    cut = pd.Timestamp(st["cutoff"]).tz_convert("Asia/Taipei").strftime("%Y-%m-%d")
    p0 = pd.Timestamp(st["period"][0]).tz_convert("Asia/Taipei").strftime("%Y-%m")
    p1 = pd.Timestamp(st["period"][1]).tz_convert("Asia/Taipei").strftime("%Y-%m")
    G = st["grades"]
    a_o, rc_o = G["A"]["oos"], st["random"]["oos"]
    a_a, rc_a = G["A"]["all"], st["random"]["all"]
    ra = lambda s: (s.get("avg_r") or 0)  # noqa
    yrs_pos = sum(1 for s in st["years_A"].values() if s.get("n", 0) >= 10 and s["avg_r"] > 0)
    yrs_n = sum(1 for s in st["years_A"].values() if s.get("n", 0) >= 10)
    grows = "".join(f'<tr><td>{grade_chip(g)} <span class="mut">{e(sg.GRADE_TEXT[g])}</span></td>{stat_cells(G[g]["ins"])}{stat_cells(G[g]["oos"])}</tr>'
                    for g in "ABCD")
    sides = "".join(f'<tr><td>{grade_chip(g)} {"做多" if d == 1 else "做空"}</td>{stat_cells_s(G[g]["all_long" if d == 1 else "all_short"])}'
                    f'{stat_cells_s(G[g]["oos_long" if d == 1 else "oos_short"])}</tr>' for g in "AB" for d in (1, -1))
    years = sorted(set(st["years_A"]) | set(st["years_all"]))
    yrows = "".join(f'<tr><td class="num">{y}</td>{stat_cells_s(st["years_A"].get(y, {}))}{stat_cells_s(st["years_all"].get(y, {}))}</tr>'
                    for y in years)
    reg = st["regime"]
    rrows = "".join(f'<tr><td>{"牛市（BTC > 200 日均）" if bull else "熊市（BTC < 200 日均）"} {"做多" if d == 1 else "做空"}</td>{stat_cells_s(reg[(bull, d)])}</tr>'
                    for bull in (True, False) for d in (1, -1))
    vrows = "".join(f'<tr><td>{e(r["name"])}{" <span class=\'chip warn\'>主要方案</span>" if r["vi"] == st["best"] else ""}</td>{stat_cells(r["ins"])}{stat_cells(r["oos"])}</tr>'
                    for r in st["variants"])
    v1 = "".join(f'<tr><td>舊 {g} 級</td>{stat_cells(st["grades_v1"][g]["all"])}{stat_cells(st["grades_v1"][g]["oos"])}</tr>' for g in "ABC")
    two = f'<tr><th rowspan="2">分組</th><th colspan="7">樣本內（設計用）</th><th colspan="7">樣本外（驗證）</th></tr><tr>{STAT_HEAD}{STAT_HEAD}</tr>'
    two_s = f'<tr><th rowspan="2"></th><th colspan="5">全期</th><th colspan="5">樣本外</th></tr><tr>{STAT_HEAD_S}{STAT_HEAD_S}</tr>'
    return f"""
<section id="{tf}"><h2>{TF_NAME[tf]} <small>{st['n_coins']} 個幣・{p0} ～ {p1}・樣本外從 {cut} 起・主要方案：{e(st['best_name'])}</small></h2>
<div class="verdict">
<p><strong>A 級樣本外 {a_o.get('n', 0)} 筆，平均 {r_(ra(a_o))}，勝率 {a_o.get('win', 0):.0f}%；同條件隨機進場 {r_(ra(rc_o))}。</strong>
全期 A 級 {r_(ra(a_a))}，隨機 {r_(ra(rc_a))}，差距 {ra(a_a) - ra(rc_a):+.2f}R 是結構訊號本身的貢獻。
有 10 筆以上的年份中，{yrs_pos}／{yrs_n} 年 A 級為正。</p>
<p>C 級（BTC 震盪）樣本外 {r_(ra(G['C']['oos']))}，D 級（逆 BTC）樣本外 {r_(ra(G['D']['oos']))}。
最長連虧 {G['A']['all'].get('max_losing_streak', '—')} 筆、最大回撤 {G['A']['all'].get('max_dd_r', 0):.0f}R。
若每筆虧 1% 本金，帳戶曾最多回落約 {G['A']['all'].get('max_dd_r', 0):.0f}%；所以系統建議每筆只虧 <b>{st['risk_suggest']:g}%</b>，讓歷史最大回撤約 {st['risk_suggest'] * G['A']['all'].get('max_dd_r', 0):.0f}%。</p>
<p class="mut">主要方案只用樣本內的 A 級挑出，選完才看樣本外。t 值大於 2 大致代表結果不太像運氣。</p>
</div>
<div class="tbl"><table><thead>{two}</thead><tbody>{grows}</tbody></table></div>
<div class="tbl"><table><thead>{two_s}</thead><tbody>{sides}</tbody></table></div>
<h3>逐年</h3>
<div class="tbl"><table><thead><tr><th rowspan="2">年</th><th colspan="5">A 級</th><th colspan="5">全部等級</th></tr><tr>{STAT_HEAD_S}{STAT_HEAD_S}</tr></thead><tbody>{yrows}</tbody></table></div>
<h3>牛熊市（A 級）</h3>
<div class="tbl"><table><thead><tr><th></th>{STAT_HEAD_S}</tr></thead><tbody>{rrows}</tbody></table></div>
<h3>隨機對照（A 級每筆配 3 筆：同幣、同方向、同停損幅度、同出場方式，BTC 條件相同的日子隨機進場）</h3>
<div class="tbl"><table><thead><tr><th></th>{STAT_HEAD}</tr></thead><tbody>
<tr><td>A 級・全期</td>{stat_cells(a_a)}</tr><tr><td>隨機・全期</td>{stat_cells(rc_a)}</tr>
<tr><td>A 級・樣本外</td>{stat_cells(a_o)}</tr><tr><td>隨機・樣本外</td>{stat_cells(rc_o)}</tr></tbody></table></div>
<details><summary>8 種停損／止盈方案（全部等級混在一起）</summary>
<div class="tbl"><table><thead><tr><th rowspan="2">方案</th><th colspan="7">樣本內</th><th colspan="7">樣本外</th></tr><tr>{STAT_HEAD}{STAT_HEAD}</tr></thead><tbody>{vrows}</tbody></table></div></details>
<details><summary>舊分級對照（看幣種自己的順逆勢）</summary>
<div class="tbl"><table><thead><tr><th rowspan="2">分級</th><th colspan="7">全期</th><th colspan="7">樣本外</th></tr><tr>{STAT_HEAD}{STAT_HEAD}</tr></thead><tbody>{v1}</tbody></table></div></details>
</section>"""


def render_backtest(ctx, artifact=False):
    b = ctx["backtest"]
    cfg = ctx["cfg"]
    S = b["strategies"]
    rrows = ""
    for r in b["rules"]:
        c = "ok" if r["verdict"] == "兩段都贏基準" else "bad" if r["verdict"] == "沒有優勢" else "ghost"

        def cell(s):
            if not s.get("n"):
                return '<td class="num">0</td><td class="num">—</td><td class="num">—</td>'
            return f'<td class="num">{s["n"]}</td><td class="num">{s["win"]:.0f}%</td><td class="num">{pct(s["excess"])}</td>'
        rrows += (f'<tr><td style="white-space:normal;min-width:220px"><b>{"▲" if r["dir"] == 1 else "▼"} {e(r["name"])}</b><br>'
                  f'<span class="mut" style="font-size:12px">{e(r["cond"])}</span></td>{cell(r["ins"][7])}{cell(r["oos"][7])}'
                  f'<td><span class="chip {c}">{e(r["verdict"])}</span></td></tr>')
    sa, sd = S["4h"]["grades"]["A"], S["1d"]["grades"]["A"]
    ra = lambda s: (s.get("avg_r") or 0)  # noqa
    hd = lambda s: (s.get("med_hours") or 0) / 24  # noqa
    body = f"""
<section><h2>回測驗證</h2>
<div class="verdict">
<p><strong>結論：兩套策略的 A 級在 6 年回測、樣本外與隨機對照中都站得住，但前提一定是 BTC 方向明確，而且順著 BTC 做。</strong></p>
<p>短線 A 級：每筆平均 {r_(ra(sa['all']))}，持有中位約 {hd(sa['all']):.0f} 天，6 年 {sa['all'].get('n', 0)} 筆。
波段 A 級：每筆平均 {r_(ra(sd['all']))}，持有中位約 {hd(sd['all']):.0f} 天，6 年 {sd['all'].get('n', 0)} 筆。
波段每筆賺得多、但次數少、持有久；短線次數多、每筆薄。</p>
<p>BTC 震盪時（C 級）兩套都是負的，這是整份回測最一致的結論：沒有方向就不做。</p>
<p class="mut">R 是「停損金額」的倍數：+0.3R 代表停損設成虧 1 元時，平均每筆賺 0.3 元。勝率四到六成，連虧十幾筆是正常的。
短線同時持倉多、回撤大，建議每筆只用 {S['4h']['risk_suggest']:g}% 本金風險；波段 {S['1d']['risk_suggest']:g}%。</p>
</div>
<nav class="tabs"><a class="chip ghost" href="#1d">跳到波段</a><a class="chip ghost" href="#4h">跳到短線</a><a class="chip ghost" href="#rules">跳到篩選規則</a></nav>
</section>
{strategy_section(S['1d'], cfg)}
{strategy_section(S['4h'], cfg)}
<section id="rules"><h2>日線篩選規則 <small>訊號後 7 天報酬，與同期全部幣種平均比較（超額）；同幣同規則 5 天內只算一次</small></h2>
<div class="tbl"><table><thead><tr><th rowspan="2">規則與條件</th><th colspan="3">樣本內</th><th colspan="3">樣本外</th><th rowspan="2">判定</th></tr>
<tr><th class="num">次數</th><th class="num">勝率</th><th class="num">超額</th><th class="num">次數</th><th class="num">勝率</th><th class="num">超額</th></tr></thead>
<tbody>{rrows}</tbody></table></div>
<p class="note">做空規則的報酬已轉成做空方向。這是收盤到收盤的報酬，沒有停損也沒有扣成本，只用來判斷規則有沒有方向性。</p></section>
<section><h2>方法與限制</h2><div class="note" style="display:flex;flex-direction:column;gap:6px;max-width:80ch">
<span>短線：4H 收盤確認後，下一根 1H 開盤進場，用 1H K 棒逐根撮合，最長持有 7 天。波段：日線收盤確認後，隔日開盤進場，用日 K 撮合，最長 60 天。同一根同時碰到停損和目標一律算停損。</span>
<span>成本：吃單 0.055%、掛單 0.02%、滑價 0.02%，資金費率以每 8 小時 0.01% 估算（做多付、做空收）。</span>
<span>無未來函數：擺動高低點要等右側 {cfg['pivot_k']} 根 K 棒走完才算確認；BTC 分數只用當下已收盤的日 K。有自動測試檢查。</span>
<span>A 級停損上限：短線 {cfg['max_risk_pct']}%、波段 {cfg['max_risk_pct_d']}%，事先設定，不是回測挑出來的。</span>
<span>倖存者偏差：幣種清單是「今天」的成交額前段，過去下市的幣不在裡面，結果會比實際稍微樂觀。</span>
<span>價格是 Binance 現貨，不是 Bybit 合約；主流幣價差很小，小幣可能有差異。</span>
</div></section>"""
    return page("Compass 回測驗證", body, nav_for(0, "bt"), ctx, artifact=artifact)


def write_all(ctx, an, out_dir, artifact=False):
    os.makedirs(f"{out_dir}/coin", exist_ok=True)
    for fn in os.listdir(f"{out_dir}/coin"):
        if fn.endswith(".html") and fn[:-5] not in an:
            os.remove(f"{out_dir}/coin/{fn}")
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as f:
        f.write(render_index(ctx, artifact))
    if ctx["backtest"]:
        with open(f"{out_dir}/backtest.html", "w", encoding="utf-8") as f:
            f.write(render_backtest(ctx, False))
    rows = {r["symbol"]: r for r in ctx["rows"]}
    for sym, a in an.items():
        with open(f"{out_dir}/coin/{sym}.html", "w", encoding="utf-8") as f:
            f.write(render_coin(sym, a, rows[sym], ctx, artifact=False))
