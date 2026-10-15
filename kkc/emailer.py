"""每日 email：主旨、HTML（inline style，Gmail 相容）、純文字備援。"""
from __future__ import annotations

import html

TF_NAME = {"4h": "短線（4H）", "1d": "波段（日線）"}
LONG, SHORT, MUTED, INK, LINE, ACC = "#18865a", "#c43d35", "#5d686c", "#182024", "#d5d9d2", "#b9770e"


def fp(x):
    a = abs(x)
    nd = 2 if a >= 100 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.1 else 6 if a >= 0.01 else 8
    return f"{x:,.{nd}f}"


def e(x):
    return html.escape(str(x))


def _hold(h):
    if not h:
        return "—"
    return f"約 {h / 24:.0f} 天" if h >= 48 else f"約 {h:.0f} 小時"


def _pos(p):
    px = p.get("position_x")
    if not px:
        return "—"
    return f"本金的 {px * 100:.0f}%" if px < 1 else f"本金的 {px:.1f} 倍"


def plan_rows(p):
    d = p["dir"]
    lo = "低" if d == 1 else "高"
    stop_name = f"回檔{lo}" if p["stop_key"] == "pullback" else f"結構{lo}"
    rows = [("進場", f"{fp(p['entry'])}（或掛 {fp(p['trigger'])} 等回踩）"),
            ("停損", f"{fp(p['stop'])}（{stop_name}，距進場 {p['risk_pct']:.1f}%）"),
            ("止盈", p["tp_text"]),
            ("預估持有", _hold(p.get("hold_med"))),
            ("建議倉位", f"{_pos(p)}（停損時虧本金 {p.get('risk_per_trade', 1):g}%）")]
    h = p.get("hist") or {}
    if h.get("n"):
        rows.append(("回測", f"同級同方向 {h['n']} 筆，勝率 {h['win']:.0f}%，平均 {h['avg_r']:+.2f}R，最長連虧 {p.get('streak', '—')} 筆"))
    f = p.get("funding") or {}
    if f.get("rate_8h") is not None:
        crowd = ""
        if f.get("pct") is not None and ((d == 1 and f["pct"] >= 90) or (d == -1 and f["pct"] <= 10)):
            crowd = "；⚠ 同方向的人很擠"
        rows.append(("資金費率 8h", f"{f['rate_8h']:+.4f}%" + (f"（近 30 日第 {f['pct']:.0f} 百分位）" if f.get("pct") is not None else "") + crowd))
    return rows


def _usp_rows(p):
    px = p.get("position_x")
    pos = (f"本金的 {px * 100:.0f}%" if px and px < 1 else f"本金的 {px:.1f} 倍" if px else "—")
    h, o = p.get("hist") or {}, p.get("hist_oos") or {}
    rows = [("進場", f"美股開盤市價買進（參考昨收 {fp(p['entry'])}）"),
            ("停損", f"{fp(p['stop'])}（距昨收 {p['risk_pct']:.1f}%）"),
            ("出場", p["tp_text"]),
            ("建議倉位", f"{pos}（停損時虧本金 {p['risk_per_trade']:g}%）")]
    if h.get("n"):
        rows.append(("回測", f"20 年 {h['n']} 筆，勝率 {h['win']:.0f}%，平均 {h['avg_r']:+.2f}R（樣本外 {o.get('avg_r', 0):+.2f}R）"))
    return rows


def usm_html(usm):
    """美股區：QQQ 大盤＋通過驗證的策略訊號。"""
    if not usm:
        return f'<p style="color:{MUTED}">今天沒有美股資料。</p>'
    if usm.get("error"):
        return f'<p style="color:{SHORT}">{e(usm["error"])}</p>'
    q = usm["qqq"]
    qcol = LONG if q["score"] >= 2 else SHORT if q["score"] <= -2 else MUTED
    head = (f'<div style="font-size:15px;margin:8px 0 2px">QQQ 日線方向 <b style="font-size:26px;color:{qcol}">{q["score"]:+.0f}</b> {e(q["label"])}'
            f'<span style="color:{MUTED}">・{fp(q["price"])}・{"200 日均線之上" if q["up"] else "200 日均線之下"}・資料日 {e(usm["date"])}（美東）</span></div>')
    td = f'style="padding:4px 10px 4px 0;color:{MUTED};vertical-align:top;white-space:nowrap"'
    tv = f'style="padding:4px 0;color:{INK};font-family:Menlo,Consolas,monospace"'
    s2 = [x for x in usm["signals"] if x["strat"] == "S2"]
    s1 = [x for x in usm["signals"] if x["strat"] == "S1"]
    cards = ""
    for p in s2:
        rows = "".join(f"<tr><td {td}>{e(k)}</td><td {tv}>{e(v)}</td></tr>" for k, v in _usp_rows(p))
        cards += (f'<div style="border:1px solid {LINE};border-left:5px solid {LONG};border-radius:6px;padding:12px 16px;margin:0 0 12px">'
                  f'<div style="font-size:20px;font-weight:bold;color:{LONG}">{e(p["symbol"])}　做多'
                  f'<span style="font-size:13px;color:{INK};font-weight:normal">　新高突破・{e(p["date"])} 收盤確認</span></div>'
                  f'<table style="border-collapse:collapse;font-size:14px;margin-top:8px">{rows}</table></div>')
    st = usm.get("stats", {})
    a2 = st.get("S2", {}).get("all", {})
    body = (f'<h3 style="font-size:16px;margin:12px 0 6px">新高突破（主力策略）</h3>'
            + (cards or f'<p style="color:{MUTED};margin:0">昨天沒有股票觸發。</p>')
            + (f'<p style="font-size:12px;color:{MUTED};margin:4px 0 0">收盤創一年新高、放量、在 200 日均線之上。20 年 {a2.get("n", 0)} 筆，'
               f'平均 {a2.get("avg_r", 0):+.2f}R（同條件隨機進場約 +0.04R），勝率約 35%，靠大賺的少數幾筆獲利。</p>' if a2.get("n") else ""))
    if s1:
        rows = "".join(
            f'<tr style="border-top:1px solid {LINE}"><td style="padding:4px 10px 4px 0"><b>{e(p["symbol"])}</b></td>'
            f'<td style="padding:4px 10px 4px 0;font-family:Menlo,Consolas,monospace">{fp(p["entry"])}</td>'
            f'<td style="padding:4px 10px 4px 0;font-family:Menlo,Consolas,monospace">停損 {fp(p["stop"])}（{p["risk_pct"]:.0f}%）</td>'
            f'<td style="padding:4px 0;font-size:12px">站上 5 日均線出場</td></tr>' for p in s1)
        a1 = st.get("S1", {}).get("all", {})
        warn = ("今天同時觸發很多檔，代表大盤整體急跌，這些幾乎是同一個賭注，最多挑 2～3 檔。" if len(s1) >= 5 else "")
        body += (f'<h3 style="font-size:16px;margin:18px 0 6px">多頭回檔候選（高勝率、小獲利）</h3>'
                 f'<table style="border-collapse:collapse;font-size:13px;width:100%">{rows}</table>'
                 f'<p style="font-size:12px;color:{MUTED};margin:4px 0 0">長期多頭裡短線急跌（RSI2 &lt; 10）。勝率約 {a1.get("win", 65):.0f}%，'
                 f'但每筆平均只有 {a1.get("avg_r", 0):+.2f}R，屬於小賺型；建議每筆只用本金 0.25% 風險。{e(warn)}</p>')
    return head + body + (f'<p style="font-size:12px;color:{MUTED};margin:8px 0 0">美股只做多：20 年回測顯示股票做空長期虧損。'
                          f'訊號用前一個美股交易日收盤判斷，台北晚上美股開盤時進場。</p>')


def usm_text(usm):
    if not usm:
        return ["今天沒有美股資料。"]
    if usm.get("error"):
        return [usm["error"]]
    q = usm["qqq"]
    out = [f"QQQ 日線方向 {q['score']:+.0f} {q['label']}・{fp(q['price'])}・{'200 日均線之上' if q['up'] else '200 日均線之下'}（資料日 {usm['date']} 美東）"]
    s2 = [x for x in usm["signals"] if x["strat"] == "S2"]
    s1 = [x for x in usm["signals"] if x["strat"] == "S1"]
    out.append("新高突破（主力）：" + ("昨天沒有股票觸發" if not s2 else ""))
    for p in s2:
        out.append(f"  {p['symbol']} 做多")
        out += [f"    {k}：{v}" for k, v in _usp_rows(p)]
    if s1:
        out.append(f"多頭回檔候選（高勝率、小獲利，最多挑 2～3 檔）：")
        out += [f"  {p['symbol']} 昨收 {fp(p['entry'])}，停損 {fp(p['stop'])}（{p['risk_pct']:.0f}%），站上 5 日均線出場" for p in s1]
    return out


def us_html(us):
    """美股與商品觀察表。只描述狀態，不給建議。"""
    if not us:
        return ""
    rows = ""
    for x in us:
        if x.get("error"):
            rows += f'<tr><td style="padding:6px 10px 6px 0">{e(x["name"])}</td><td colspan="3" style="color:{MUTED}">{e(x["error"])}</td></tr>'
            continue
        sc = x["score"]
        col = LONG if (sc or 0) >= 2 else SHORT if (sc or 0) <= -2 else MUTED
        c7 = x["chg7"] or 0
        rows += (f'<tr style="border-top:1px solid {LINE}"><td style="padding:6px 10px 6px 0;vertical-align:top;white-space:nowrap"><b>{e(x["name"])}</b></td>'
                 f'<td style="padding:6px 10px 6px 0;vertical-align:top;font-family:Menlo,Consolas,monospace;white-space:nowrap">{fp(x["price"])}<br>'
                 f'<span style="color:{LONG if c7 > 0 else SHORT};font-size:12px">7日 {c7:+.1f}%</span></td>'
                 f'<td style="padding:6px 10px 6px 0;vertical-align:top;color:{col};white-space:nowrap">'
                 f'{(f"{sc:+.0f}" if sc is not None else "—")}</td>'
                 f'<td style="padding:6px 0;vertical-align:top;font-size:13px">{e(x["desc"])}</td></tr>')
    return (f'<h3 style="font-size:16px;margin:22px 0 4px">觀察清單狀態（含商品）</h3>'
            f'<p style="margin:0 0 6px;font-size:12px;color:{MUTED}">報價為 Hyperliquid 股票／商品永續合約。'
            f'20 年回測顯示：結構訊號在美股與商品上沒有勝過隨機進場，股票做空長期平均虧損，'
            f'所以這裡只描述狀態與環境，不給進場建議。</p>'
            f'<table style="border-collapse:collapse;font-size:14px;width:100%"><tr style="color:{MUTED};font-size:12px">'
            f'<td>標的</td><td>價格</td><td>日線分數</td><td>狀態</td></tr>{rows}</table>')


def build_email(ctx, report_url=None):
    recs = ctx["recs"]
    acts = [r for r in recs.values() if r["action"] != "觀望"]
    acts.sort(key=lambda r: ({"A": 0, "B": 1}[r["main"]["grade"]], r["main"]["tf"] != "1d"))
    s = ctx["btc_score"]
    strong = ctx["cfg"]["btc_strong_score"]
    date = ctx["now_tw"][:10]
    if acts:
        c_part = f"幣 {len(acts)} 檔：" + "、".join(
            f"{r['symbol'][:-4]}{'多' if r['main']['dir'] == 1 else '空'}" for r in acts[:3]) + ("…" if len(acts) > 3 else "")
    else:
        c_part = f"幣 觀望（BTC {s:+.0f}）"
    usm = ctx.get("usm") or {}
    s2 = [x for x in usm.get("signals", []) if x["strat"] == "S2"]
    s1 = [x for x in usm.get("signals", []) if x["strat"] == "S1"]
    if usm.get("error"):
        u_part = "美股 資料錯誤"
    elif s2:
        u_part = "美股 突破：" + "、".join(x["symbol"] for x in s2[:3]) + ("…" if len(s2) > 3 else "")
    elif s1:
        u_part = f"美股 回檔候選 {len(s1)} 檔"
    else:
        u_part = "美股 無訊號"
    subject = f"KK Compass {date}｜{c_part}｜{u_part}"
    if s >= strong:
        guide = "BTC 多頭明確：只考慮做多。"
    elif s <= -strong:
        guide = "BTC 空頭明確：只考慮做空。"
    else:
        guide = "BTC 在震盪區：回測中這種時候進場平均是虧的，今天觀望。"
    # 觀察名單
    watch = []
    if abs(s) >= strong:
        for r in recs.values():
            if r["action"] != "觀望":
                continue
            for w in r["waits"]:
                if w["grade_if"] == "A/B" and abs(w["dist"]) <= 3:
                    watch.append((r["symbol"], w))
        watch.sort(key=lambda x: abs(x[1]["dist"]))
    watch_title = "觀察名單（距觸發 3% 內）"
    if abs(s) == strong - 1:  # 差 1 分就會變明確：預先列出那個方向接近觸發的幣
        dn = 1 if s > 0 else -1
        guide += f"BTC 分數再{'升' if dn == 1 else '降'} 1 分就會進入{'多' if dn == 1 else '空'}頭明確，下面是屆時會成立的候選。"
        for r in recs.values():
            for w in r["waits"]:
                if w["dir"] == dn and abs(w["dist"]) <= 3:
                    watch.append((r["symbol"], w))
        watch.sort(key=lambda x: abs(x[1]["dist"]))
        watch_title = f"若 BTC 轉為{'多' if dn == 1 else '空'}頭明確：接近觸發的候選（距 3% 內）"
    b = ctx["backtest"]["strategies"]

    # ---------------- HTML
    td = f'style="padding:4px 10px 4px 0;color:{MUTED};vertical-align:top;white-space:nowrap"'
    tv = f'style="padding:4px 0;color:{INK};font-family:Menlo,Consolas,monospace"'
    cards = ""
    for r in acts:
        p = r["main"]
        col = LONG if p["dir"] == 1 else SHORT
        rows = "".join(f"<tr><td {td}>{e(k)}</td><td {tv}>{e(v)}</td></tr>" for k, v in plan_rows(p))
        chase = (f'<p style="margin:6px 0 0;color:{ACC};font-weight:bold">{e(r["chase"])}</p>' if r.get("chase") else "")
        cards += (f'<div style="border:1px solid {LINE};border-left:5px solid {col};border-radius:6px;padding:12px 16px;margin:0 0 12px">'
                  f'<div style="font-size:20px;font-weight:bold;color:{col}">{e(p["symbol"][:-4])}　{e(r["action"])}'
                  f'<span style="font-size:13px;color:{INK};font-weight:normal">　{e(p["grade"])} 級・{e(TF_NAME[p["tf"]])}・確認 {e(p["time"])}</span></div>'
                  f'<table style="border-collapse:collapse;font-size:14px;margin-top:8px">{rows}</table>{chase}</div>')
    if not cards:
        cards = f'<p style="color:{MUTED}">今天沒有回測支持的進場機會。</p>'
    wrows = "".join(
        f'<tr><td style="padding:3px 12px 3px 0">{e(sym[:-4])}</td><td style="padding:3px 12px 3px 0">{e(TF_NAME[w["tf"]])}</td>'
        f'<td style="padding:3px 12px 3px 0;color:{LONG if w["dir"] == 1 else SHORT}">{"做多" if w["dir"] == 1 else "做空"}</td>'
        f'<td style="padding:3px 12px 3px 0;font-family:Menlo,Consolas,monospace">收盤{"站上" if w["dir"] == 1 else "跌破"} {fp(w["trigger"])}</td>'
        f'<td style="padding:3px 0;font-family:Menlo,Consolas,monospace">{w["dist"]:+.2f}%</td></tr>' for sym, w in watch[:12])
    watch_html = (f'<h3 style="font-size:16px;margin:20px 0 6px">{e(watch_title)}</h3>'
                  f'<table style="border-collapse:collapse;font-size:14px">{wrows}</table>') if wrows else ""
    sd, s4 = b["1d"]["grades"]["A"], b["4h"]["grades"]["A"]
    bt_line = (f'回測（6 年）：波段 A 級每筆平均 {sd["all"].get("avg_r", 0):+.2f}R（樣本外 {sd["oos"].get("avg_r", 0):+.2f}R）；'
               f'短線 A 級 {s4["all"].get("avg_r", 0):+.2f}R（樣本外 {s4["oos"].get("avg_r", 0):+.2f}R）。')
    link = (f'<p style="margin:16px 0"><a href="{e(report_url)}" style="background:{ACC};color:#fff;padding:8px 16px;'
            f'border-radius:4px;text-decoration:none;font-weight:bold">打開完整報告</a></p>') if report_url else ""
    btc_col = LONG if s > 0 else SHORT if s < 0 else MUTED
    html_body = f"""<div style="font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;color:{INK};max-width:640px;line-height:1.6">
<div style="font-size:13px;color:{MUTED}">KK Compass 2・{e(ctx['now_tw'])}（台北）</div>
<h2 style="font-size:20px;margin:14px 0 4px;padding:6px 10px;background:#f3e3c3;color:{INK};border-radius:4px">₿ 加密貨幣區</h2>
<div style="font-size:15px;margin:8px 0 2px">BTC 日線方向 <b style="font-size:26px;color:{btc_col}">{s:+.0f}</b> {e(ctx['btc_label'])}
<span style="color:{MUTED}">・現價 {fp(ctx['btc_price'])}・{"200 日均線之上" if ctx['btc_bull'] else "200 日均線之下"}</span></div>
<p style="margin:4px 0 16px;font-weight:bold">{e(guide)}</p>
<h3 style="font-size:16px;margin:0 0 8px">今日策略建議</h3>
{cards}{watch_html}
<h2 style="font-size:20px;margin:26px 0 4px;padding:6px 10px;background:#dfe8f1;color:{INK};border-radius:4px">🇺🇸 美股區</h2>
{usm_html(usm)}{us_html(ctx.get("us"))}{link}
<p style="font-size:12px;color:{MUTED};margin-top:20px">{e(bt_line)}<br>
這是規則式工具的輸出，不是投資建議；回測代表過去，不保證未來。下單前請自行確認價格。</p></div>"""

    # ---------------- 純文字
    lines = [f"KK Compass 2・{ctx['now_tw']}（台北）", "", "【加密貨幣區】",
             f"BTC 日線方向 {s:+.0f} {ctx['btc_label']}・現價 {fp(ctx['btc_price'])}", guide, "", "今日策略建議"]
    if acts:
        for r in acts:
            p = r["main"]
            lines.append(f"\n{p['symbol'][:-4]} {r['action']}｜{p['grade']} 級・{TF_NAME[p['tf']]}・確認 {p['time']}")
            lines += [f"  {k}：{v}" for k, v in plan_rows(p)]
            if r.get("chase"):
                lines.append(f"  {r['chase']}")
    else:
        lines.append("今天沒有回測支持的進場機會。")
    if watch:
        lines += ["", watch_title]
        lines += [f"  {sym[:-4]} {TF_NAME[w['tf']]} {'做多' if w['dir'] == 1 else '做空'} 收盤{'站上' if w['dir'] == 1 else '跌破'} {fp(w['trigger'])}（{w['dist']:+.2f}%）"
                  for sym, w in watch[:12]]
    lines += ["", "【美股區】"] + usm_text(usm)
    if ctx.get("us"):
        lines += ["", "觀察清單狀態（Hyperliquid 報價）"]
        for x in ctx["us"]:
            if x.get("error"):
                lines.append(f"  {x['name']}：{x['error']}")
                continue
            lines.append(f"  {x['name']} {fp(x['price'])}（7日 {x['chg7']:+.1f}%）：{x['desc']}")
    if report_url:
        lines += ["", f"完整報告：{report_url}"]
    lines += ["", bt_line, "這是規則式工具的輸出，不是投資建議。"]
    return subject, html_body, "\n".join(lines)


def build_scan_email(plans, btc_score, cfg):
    """晚間 4H 掃描：只在有新訊號時寄。"""
    from datetime import datetime, timedelta, timezone
    now = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    names = "、".join(f"{p['symbol'][:-4]}{'多' if p['dir'] == 1 else '空'}" for p in plans[:4]) + ("…" if len(plans) > 4 else "")
    subject = f"KK Compass 短線訊號 {now[5:]}｜{names}"
    td = f'style="padding:4px 10px 4px 0;color:{MUTED};vertical-align:top;white-space:nowrap"'
    tv = f'style="padding:4px 0;color:{INK};font-family:Menlo,Consolas,monospace"'
    cards, lines = "", [f"KK Compass 短線（4H）訊號・{now}（台北）", f"BTC 日線方向 {btc_score:+.0f}", ""]
    for p in plans:
        col = LONG if p["dir"] == 1 else SHORT
        act = "做多" if p["dir"] == 1 else "做空"
        rows = plan_rows(p) + [("現價", f"{fp(p['price_now'])}（離確認價 {p['moved_r']:+.1f}R）")]
        chase = ""
        if p["moved_r"] > 1:
            chase = "價格已經離確認價超過 1R，追價的盈虧比變差，建議等回踩或放棄。"
        cards += (f'<div style="border:1px solid {LINE};border-left:5px solid {col};border-radius:6px;padding:12px 16px;margin:0 0 12px">'
                  f'<div style="font-size:20px;font-weight:bold;color:{col}">{e(p["symbol"][:-4])}　{act}'
                  f'<span style="font-size:13px;color:{INK};font-weight:normal">　{e(p["grade"])} 級・短線（4H）・確認 {e(p["time"])}</span></div>'
                  f'<table style="border-collapse:collapse;font-size:14px;margin-top:8px">'
                  + "".join(f"<tr><td {td}>{e(k)}</td><td {tv}>{e(v)}</td></tr>" for k, v in rows)
                  + "</table>" + (f'<p style="margin:6px 0 0;color:{ACC};font-weight:bold">{e(chase)}</p>' if chase else "") + "</div>")
        lines.append(f"{p['symbol'][:-4]} {act}｜{p['grade']} 級・短線（4H）・確認 {p['time']}")
        lines += [f"  {k}：{v}" for k, v in rows]
        if chase:
            lines.append("  " + chase)
        lines.append("")
    html_body = (f'<div style="font-family:-apple-system,\'PingFang TC\',\'Microsoft JhengHei\',sans-serif;color:{INK};max-width:640px;line-height:1.6">'
                 f'<div style="font-size:13px;color:{MUTED}">KK Compass 短線（4H）訊號・{e(now)}（台北）・BTC 日線方向 {btc_score:+.0f}</div>'
                 f'<h3 style="font-size:16px;margin:10px 0 8px">新的進場訊號</h3>{cards}'
                 f'<p style="font-size:12px;color:{MUTED}">短線最長持有 7 天；回測中短線優勢比波段薄、連虧可以很長，請照建議倉位。'
                 f'這是規則式工具的輸出，不是投資建議；下單前請在 Bybit 確認價格。</p></div>')
    lines.append("短線最長持有 7 天；請照建議倉位。這是規則式工具的輸出，不是投資建議。")
    return subject, html_body, "\n".join(lines)
