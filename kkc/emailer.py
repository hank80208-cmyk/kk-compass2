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


def us_open_tw():
    """今晚美股開盤的台北時間（自動處理夏令／冬令）。"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    now = datetime.now(ny)
    day = now if now.hour < 16 else now + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    o = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ny).astimezone(ZoneInfo("Asia/Taipei"))
    return o.strftime("%m-%d %H:%M")


def _pos_text(px, base=100_000):
    if not px:
        return "—"
    return f"本金的 {px * 100:.1f}%（本金 10 萬 → 買約 {px * base:,.0f} 的股票）" if px < 1 else f"本金的 {px:.1f} 倍"


def _usp_rows(p, open_tw):
    h, o = p.get("hist") or {}, p.get("hist_oos") or {}
    rows = [("什麼時候", f"今晚美股開盤（台北 {open_tw}）"),
            ("怎麼買", f"市價單買進（參考昨收 {fp(p['entry'])}）"),
            ("停損單", f"{fp(p['stop'])}，買到後立刻掛「停損市價單、長效 GTC」（距昨收 {p['risk_pct']:.1f}%）"),
            ("怎麼賣", p["tp_text"]),
            ("買多少", f"{_pos_text(p.get('position_x'))}；打到停損只虧本金 {p['risk_per_trade']:g}%")]
    if h.get("n"):
        rows.append(("回測", f"20 年 {h['n']} 筆，勝率 {h['win']:.0f}%，平均 {h['avg_r']:+.2f}R（樣本外 {o.get('avg_r', 0):+.2f}R）"))
    return rows


def us_todo(usm):
    """美股今晚要做的事：(買進, 賣出, 停損通知, 續抱)。"""
    if not usm or usm.get("error"):
        return [], [], [], []
    buys = [p for p in usm.get("signals", []) if p.get("pick")]
    hs = usm.get("holds", [])
    return (buys, [h for h in hs if h["state"] == "sell"], [h for h in hs if h["state"] == "stopped"],
            [h for h in hs if h["state"] == "hold"])


def usm_html(usm):
    """美股區：QQQ 大盤、今晚買進卡、持有中、其他觸發、策略說明。"""
    if not usm:
        return f'<p style="color:{MUTED}">今天沒有美股資料。</p>'
    if usm.get("error"):
        return f'<p style="color:{SHORT}">{e(usm["error"])}</p>'
    open_tw = us_open_tw()
    q = usm["qqq"]
    qcol = LONG if q["score"] >= 2 else SHORT if q["score"] <= -2 else MUTED
    head = (f'<div style="font-size:15px;margin:8px 0 2px">QQQ 日線方向 <b style="font-size:26px;color:{qcol}">{q["score"]:+.0f}</b> {e(q["label"])}'
            f'<span style="color:{MUTED}">・{fp(q["price"])}・{"200 日均線之上" if q["up"] else "200 日均線之下"}・資料日 {e(usm["date"])}（美東收盤）</span></div>')
    td = f'style="padding:4px 10px 4px 0;color:{MUTED};vertical-align:top;white-space:nowrap"'
    tv = f'style="padding:4px 0;color:{INK}"'
    buys, sells, stopped, holding = us_todo(usm)
    cards = ""
    for p in buys:
        rows = "".join(f"<tr><td {td}>{e(k)}</td><td {tv}>{e(v)}</td></tr>" for k, v in _usp_rows(p, open_tw))
        tag = "新高突破（主力）" if p["strat"] == "S2" else "多頭回檔（小賺型）"
        cards += (f'<div style="border:1px solid {LINE};border-left:5px solid {LONG};border-radius:6px;padding:12px 16px;margin:0 0 12px">'
                  f'<div style="font-size:20px;font-weight:bold;color:{LONG}">{e(p["symbol"])}　買進'
                  f'<span style="font-size:13px;color:{INK};font-weight:normal">　{tag}・{e(p["date"])} 收盤觸發</span></div>'
                  f'<table style="border-collapse:collapse;font-size:14px;margin-top:8px">{rows}</table></div>')
    body = f'<h3 style="font-size:16px;margin:12px 0 6px">今晚買進</h3>' + (cards or f'<p style="color:{MUTED};margin:0">今晚沒有要買的。</p>')
    # 持有中
    hrows = ""
    for h in sells + stopped + holding:
        if h["state"] == "sell":
            act, col = f"今晚開盤市價賣出，並取消停損單（{h['why']}）", ACC
        elif h["state"] == "stopped":
            act, col = f"昨天已打到停損 {fp(h['stop'])}，停損單應已成交，請確認", SHORT
        else:
            act, col = f"續抱。停損 {fp(h['stop'])} 不動；收盤{'站上' if h['strat'] == 'S1' else '跌破'}{h['line_name']}（目前 {fp(h['line'])}）才賣", MUTED
        hrows += (f'<tr style="border-top:1px solid {LINE}"><td style="padding:5px 10px 5px 0;white-space:nowrap;vertical-align:top"><b>{e(h["symbol"])}</b><br>'
                  f'<span style="font-size:12px;color:{MUTED}">{e(h["date"])} 買・第 {h["held"]} 天</span></td>'
                  f'<td style="padding:5px 0;font-size:13px;color:{col if h["state"] != "hold" else INK}">{e(act)}</td></tr>')
    if hrows:
        body += (f'<h3 style="font-size:16px;margin:18px 0 6px">持有中（照之前的信買進的話）</h3>'
                 f'<table style="border-collapse:collapse;font-size:14px;width:100%">{hrows}</table>')
    others = [p for p in usm.get("signals", []) if not p.get("pick")]
    if others:
        body += (f'<p style="font-size:13px;margin:14px 0 0"><b>其他也有觸發、但不建議再買的：</b>{e("、".join(p["symbol"] for p in others))}。'
                 f'<span style="color:{MUTED}">同一天觸發很多檔代表大盤一起跌，這些幾乎是同一個賭注；系統只挑長期趨勢最強（離 200 日均線最遠）的前 3 檔，回測比全買好。</span></p>')
    st = usm.get("stats", {})
    a2, a1 = st.get("S2", {}).get("all", {}), st.get("S1", {}).get("all", {})
    body += (f'<p style="font-size:12px;color:{MUTED};margin:12px 0 0"><b>兩種訊號：</b>'
             f'新高突破＝收盤創一年新高、放量、在 200 日均線之上；20 年 {a2.get("n", 0)} 筆，平均 {a2.get("avg_r", 0):+.2f}R，勝率約 {a2.get("win", 35):.0f}%，靠少數大賺。'
             f'多頭回檔＝長期多頭裡短線急跌；{a1.get("n", 0)} 筆，勝率約 {a1.get("win", 65):.0f}%，但平均只有 {a1.get("avg_r", 0):+.2f}R，小賺型，所以倉位較小。'
             f'只做多（股票做空 20 年長期虧損）。</p>'
             f'<p style="font-size:12px;color:{MUTED};margin:6px 0 0"><b>券商怎麼設：</b>①開盤後下市價買單 ②成交後馬上掛「停損單（Stop／停損市價）」，價格填信上的停損價，效期選 GTC／長效 '
             f'③之後每天早上看信：寫「今晚開盤賣出」那天，開盤下市價賣單，再取消原本的停損單。</p>')
    return head + body


def usm_text(usm):
    if not usm:
        return ["今天沒有美股資料。"]
    if usm.get("error"):
        return [usm["error"]]
    open_tw = us_open_tw()
    q = usm["qqq"]
    out = [f"QQQ 日線方向 {q['score']:+.0f} {q['label']}・{fp(q['price'])}・{'200 日均線之上' if q['up'] else '200 日均線之下'}（資料日 {usm['date']} 美東）"]
    buys, sells, stopped, holding = us_todo(usm)
    out.append("今晚買進：" + ("" if buys else "沒有"))
    for p in buys:
        out.append(f"  {p['symbol']} 買進（{'新高突破' if p['strat'] == 'S2' else '多頭回檔'}）")
        out += [f"    {k}：{v}" for k, v in _usp_rows(p, open_tw)]
    for h in sells:
        out.append(f"  {h['symbol']}：今晚開盤市價賣出，並取消停損單（{h['why']}）")
    for h in stopped:
        out.append(f"  {h['symbol']}：昨天已打到停損 {fp(h['stop'])}，請確認")
    for h in holding:
        out.append(f"  {h['symbol']}：續抱，停損 {fp(h['stop'])}")
    others = [p for p in usm.get("signals", []) if not p.get("pick")]
    if others:
        out.append("其他觸發但不建議再買：" + "、".join(p["symbol"] for p in others))
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
    ubuy, usell, _, _ = us_todo(usm)
    if usm.get("error"):
        u_part = "美股 資料錯誤"
    elif ubuy or usell:
        u_part = "美股 " + "、".join([f"買{x['symbol']}" for x in ubuy[:3]] + [f"賣{x['symbol']}" for x in usell[:2]])
    else:
        u_part = "美股 不動作"
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
    else:
        cards += (f'<p style="font-size:12px;color:{MUTED};margin:0 0 8px"><b>Bybit 怎麼設：</b>開倉時打開「止盈止損」，止損填卡片上的停損價；'
                  f'止盈是固定目標價的就填目標價，是「跌破／站上均線出場」的就不填，每天看信決定。'
                  f'倉位照「建議倉位」換算，槓桿只是用來湊到這個倉位，不要因為有槓桿就買更多。</p>')
    # 今天要做的事（最上面的摘要）
    open_tw = us_open_tw()
    ubuy, usell, ustop, uhold = us_todo(usm)
    todo = []
    if acts:
        for r in acts:
            p = r["main"]
            todo.append(f"₿ {p['symbol'][:-4]} {r['action']}（{TF_NAME[p['tf']]}）：進場約 {fp(p['entry'])}，停損 {fp(p['stop'])}，倉位 {_pos(p)}")
    else:
        todo.append(f"₿ 加密貨幣：不做（BTC {s:+.0f} {ctx['btc_label']}，沒有回測支持的機會）")
    if usm.get("error"):
        todo.append("🇺🇸 美股：今天資料抓取失敗")
    else:
        if ubuy:
            todo.append(f"🇺🇸 今晚 {open_tw} 開盤買：" + "、".join(
                f"{p['symbol']}（停損 {fp(p['stop'])}，倉位本金 {p['position_x'] * 100:.1f}%）" for p in ubuy))
        if usell:
            todo.append("🇺🇸 今晚開盤賣：" + "、".join(h["symbol"] for h in usell))
        if ustop:
            todo.append("🇺🇸 已停損出場（確認一下）：" + "、".join(h["symbol"] for h in ustop))
        if uhold:
            todo.append("🇺🇸 續抱不用動：" + "、".join(h["symbol"] for h in uhold))
        if not (ubuy or usell or ustop or uhold):
            todo.append("🇺🇸 美股：今晚不用動作")
    todo_html = (f'<div style="border:2px solid {INK};border-radius:6px;padding:10px 14px;margin:10px 0 4px">'
                 f'<div style="font-size:16px;font-weight:bold;margin-bottom:4px">今天要做的事</div>'
                 + "".join(f'<div style="font-size:14px;margin:3px 0">{e(t)}</div>' for t in todo)
                 + f'<div style="font-size:12px;color:{MUTED};margin-top:4px">詳細設定（停損單、怎麼賣、買多少）在下面各區。</div></div>')
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
{todo_html}
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
    lines = [f"KK Compass 2・{ctx['now_tw']}（台北）", "", "【今天要做的事】"] + [f"  {t}" for t in todo] + ["", "【加密貨幣區】",
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
