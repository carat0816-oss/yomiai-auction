"""📊 みんなのデータ：スプレッドシートに集まった対戦から「人の出し方のクセ」を読み解く。

画面のつくり：上にまとめ（数字とハイライト）→ タブごとに「問い → わかったこと → グラフ → 読み方」。
「わかったこと」の文は、いま表示しているデータから毎回計算する（データが少ないときはそう書く）。
"""
from __future__ import annotations

import html

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from game import replay
from ml import opp_dataset
from views.ui import answer, data_css, highlights, page_header, question, section

HUMAN, AI, GRAY = "#2a78d6", "#eb6834", "#a3acbb"
BLUES = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
GUESS = sum(1 / n for n in range(2, 11)) / 9   # 当てずっぽうで当たる率（最終ラウンドを除く9回の平均）≈ 21%
FEW = 30                                       # これより少ない手数の比較には「偶然かも」と添える
TABS = ["🃏 札の出し方", "💭 気持ちの動き", "👤 プレイヤー", "🤖 AIとの勝負", "📋 データ"]

GLOSSARY = """
**得点カード**　毎ラウンドめくられる1〜10のカード。取り合う点数そのもの。

**札**　お互いが持っている1〜10の手札。一度出すと戻らない。

**強気度**　「得点の割に、どれだけ強い札を出したか」。
出した札が手札の中で何番目に強いか（0〜1）から、得点カードが残りの得点カードの中で何番目に大きいか（0〜1）を引いた値。
**0** なら得点に見合った札、**＋** なら得点の割に強い札（強気）、**−** なら控えめ。

**相打ち**　同じ数字を出して、得点カードが誰のものにもならないこと。

**AIの読みの的中率**　AIが「この人は次にこの札を出す」と一番に予想した札が当たった割合。
当てずっぽうなら約 21%（手札が10枚→2枚と減っていく9回の平均）。
"""


# ---------------------------------------------------------------------------
# データの準備
# ---------------------------------------------------------------------------
def dummy_settings(key: str) -> list[dict]:
    """練習用のダミー（ボット同士の対戦）を作る。設定は折りたたんでおく。"""
    with st.expander("ダミーデータの設定", icon=":material/tune:"):
        c1, c2, c3 = st.columns(3)
        n = c1.slider("ボットの人数", 5, 80, 30, key=f"{key}_n")
        k = c2.slider("1人あたりの試合数", 1, 10, 3, key=f"{key}_k")
        seed = c3.number_input("乱数の種", 0, 999, 0, key=f"{key}_seed")
    return _dummy(n, k, int(seed))


@st.cache_data(show_spinner=False)
def _dummy(n, k, seed):
    from ai import dummy_games
    return dummy_games(n, k, seed)


@st.cache_data(show_spinner=False)
def decisions(games: list[dict]) -> pd.DataFrame:
    """人間が札を出した1回＝1行（出した札の特徴量つき）。"""
    df = opp_dataset(games)
    if df.empty:
        return df
    d = df[df["chosen"] == 1].copy()
    d["強気度"] = d["rank_gap"]
    return d


@st.cache_data(show_spinner=False)
def round_frame(games: list[dict]) -> pd.DataFrame:
    """1ラウンド＝1行（人間側の目線）。相打ちの分析に使う。"""
    rows = []
    for g in games:
        states = replay(g["prizes"], [(r["human_card"], r["ai_card"]) for r in g["rounds"]])
        for i, r in enumerate(g["rounds"]):
            st_ = states[i]
            mine, theirs = st_["hands"][0], st_["hands"][1]
            c = r["human_card"]
            rows.append({"player": g["player"], "得点カード": st_["prizes"][i], "残り手札": len(mine),
                         "点差": st_["score"][0] - st_["score"][1], "相打ち": c == r["ai_card"],
                         "最強札が同じ": max(mine) == max(theirs),
                         "人間の選択": "最強札をぶつけた" if c == max(mine) else "最弱札で譲った" if c == min(mine)
                         else "その間の札"})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["点差"] = pd.cut(df["点差"], [-56, -6, -1, 0, 5, 56], labels=["6点以上負け", "1〜5点負け", "同点", "1〜5点勝ち", "6点以上勝ち"])
    return df


# ---------------------------------------------------------------------------
# 表示の小道具
# ---------------------------------------------------------------------------
def _few(n: int) -> str:
    return f"（ただし比べた手数がまだ {n} 手と少ないので、偶然の差かもしれません）" if n < FEW else ""


def _show(chart, height: int = 280):
    """グラフの見た目をそろえる：文字は大きめ、目盛りと枠は控えめ。"""
    st.altair_chart(chart.properties(height=height)
                    .configure_axis(labelFontSize=13, titleFontSize=13, labelColor="#56627a", titleColor="#56627a",
                                    gridColor="#e9edf3", domainColor="#c9d1de", tickColor="#c9d1de", titleFontWeight=600)
                    .configure_legend(labelFontSize=13, titleFontSize=13, orient="top")
                    .configure_view(stroke=None), width="stretch")


def _bars(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str, fmt: str, color: str = HUMAN,
          sort=None, horizontal: bool = False, zero_rule: bool = False):
    """値ラベルつきの棒グラフ（細い棒・角丸・値は棒の先に書く）。"""
    if horizontal:
        enc = dict(y=alt.Y(f"{x}:N", title=None, sort=sort, axis=alt.Axis(labelLimit=240)), x=alt.X(f"{y}:Q", title=y_title))
        bar = alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=4, height={"band": 0.6})
        txt = alt.Chart(df).mark_text(align="left", dx=6, fontSize=14, fontWeight=700, color="#14213a")
    else:
        enc = dict(x=alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=0)),
                   y=alt.Y(f"{y}:Q", title=y_title))
        bar = alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=4, width={"band": 0.55})
        txt = alt.Chart(df).mark_text(baseline="bottom", dy=-5, fontSize=14, fontWeight=700, color="#14213a")
    layers = [bar.encode(**enc, tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)])]
    if zero_rule and not horizontal:   # マイナスの値は棒の下に書く
        below = alt.Chart(df).mark_text(baseline="top", dy=5, fontSize=14, fontWeight=700, color="#14213a")
        layers += [txt.transform_filter(f"datum['{y}'] >= 0").encode(**enc, text=alt.Text(f"{y}:Q", format=fmt)),
                   below.transform_filter(f"datum['{y}'] < 0").encode(**enc, text=alt.Text(f"{y}:Q", format=fmt))]
    else:
        layers.append(txt.encode(**enc, text=alt.Text(f"{y}:Q", format=fmt)))
    if zero_rule:
        layers.append(alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color="#56627a").encode(y="z:Q"))
    return alt.layer(*layers)


def _read_more(text: str):
    with st.expander("グラフの読み方・注意", icon=":material/menu_book:"):
        st.markdown(text)


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
def show_shared(games: list[dict], store):
    data_css()
    page_header("DATA", "みんなのデータ",
                "AIと対戦した人が「データ提供に同意」して送った記録です。人はどんなときに強い札を出し、"
                "負けたら熱くなるのか？ 集まったデータから、人間の「読み合いのクセ」を探します。")

    top = st.columns([3, 4, 1.4], vertical_alignment="bottom")
    with top[0]:
        src = st.segmented_control("見るデータ", ["みんなのデータ", "ダミー（練習用）"], default="みんなのデータ",
                                   key="shared_src", required=True)
    dummy = src == "ダミー（練習用）"
    if dummy:
        games = dummy_settings("shared")
        st.warning("いま表示しているのは、5つの型（比例型・強気型・慎重型・温存型・気まぐれ型）のボットが遊んだ"
                   "**架空のデータ**です。画面の見え方を試すためのもので、人間のデータではありません。", icon=":material/smart_toy:")
    if not games:
        st.info("まだ記録がありません。対戦のあと「みんなのデータに送る」と、ここに集まります。"
                "左上の「ダミー（練習用）」で、画面の見え方を先に試せます。", icon=":material/inbox:")
        return
    players = sorted({x["player"] for x in games})
    with top[1]:
        chosen = st.multiselect("プレイヤーで絞り込む", players, key="shared_players", placeholder="全員")
    with top[2]:
        with st.popover("用語の説明", icon=":material/help:", width="stretch"):
            st.markdown(GLOSSARY)
    if chosen:
        games = [x for x in games if x["player"] in chosen]
    if not games:
        st.info("該当する記録がありません。")
        return

    g = pd.DataFrame([{k: v for k, v in x.items() if k not in ("rounds", "prizes")} for x in games])
    for c in ("read_top1", "read_prob", "ai_model"):   # ダミーにはない列（空欄でそろえる）
        if c not in g.columns:
            g[c] = np.nan if c != "ai_model" else "ダミー"
    g["read_top1"] = pd.to_numeric(g["read_top1"], errors="coerce")
    g["人間の勝ち"] = g["my_score"] > g["ai_score"]
    d = decisions(games)
    rr = round_frame(games)
    real_read = not dummy and g["read_top1"].notna().any()

    _summary(g, d, rr, real_read)
    t1, t2, t3, t4, t5 = st.tabs(TABS)
    with t1:
        _tab_cards(d)
    with t2:
        _tab_mind(d, rr, dummy)
    with t3:
        _tab_players(g, d)
    with t4:
        _tab_ai(g, real_read)
    with t5:
        _tab_data(g, games, store, dummy)


def _slope(d: pd.DataFrame) -> float:
    if len(d) < 3 or d["prize"].nunique() < 2:
        return float("nan")
    return float(np.polyfit(d["prize"], d["card"], 1)[0])


def _after(d: pd.DataFrame) -> pd.DataFrame:
    """前のラウンドの結果ごとの強気度（2ラウンド目以降・最後の1枚は選べないので除く）。"""
    x = d[(d["round_no"] > 1) & (d["round_no"] < 10)]
    x = x.assign(前のラウンド=x["last_result"].map({1: "勝った", 0: "相打ち", -1: "負けた"}))
    return x.groupby("前のラウンド")["強気度"].agg(["mean", "size"]).reindex(["勝った", "相打ち", "負けた"]).dropna()


def _summary(g, d, rr, real_read):
    m = st.columns(5)
    m[0].metric("試合", f"{len(g)} 試合", border=True, height="stretch")
    m[1].metric("プレイヤー", f"{g['player'].nunique()} 人", border=True, height="stretch")
    m[2].metric("出された手", f"{len(d)} 手", border=True, height="stretch")
    trend = (g["人間の勝ち"].rolling(10, min_periods=1).mean() * 100).round(1).tolist()
    m[3].metric("人間側の勝率", f"{g['人間の勝ち'].mean():.0%}", border=True, chart_data=trend if len(g) > 2 else None,
                chart_type="area", help="グラフは直近10試合ごとの勝率の移り変わり")
    if real_read:
        rate = g["read_top1"].mean()
        m[4].metric("AIの読みの的中率", f"{rate:.0%}", delta=f"{(rate - GUESS) * 100:+.0f}pt",
                    delta_description="当てずっぽう比", delta_color="off", border=True, height="stretch", help="AIが一番に予想した札が当たった割合。当てずっぽうなら約21%")
    else:
        m[4].metric("相打ちの割合", f"{rr['相打ち'].mean():.0%}", border=True, height="stretch", help="同じ数字を出して得点が流れたラウンドの割合")

    s = _slope(d)
    aft = _after(d)
    cards = [{"k": "得点が1上がると、出す札は…", "v": "—" if np.isnan(s) else f"{s:+.2f}", "u": "",
              "d": "ほぼ1なら得点に合わせて札を選ぶ人が多い。0に近いと得点と関係なく出している。",
              "go": TABS[0], "c": HUMAN}]
    if {"勝った", "負けた"} <= set(aft.index):
        diff = aft.loc["負けた", "mean"] - aft.loc["勝った", "mean"]
        cards.append({"k": "負けた直後の強気度（勝った直後との差）", "v": f"{diff:+.2f}", "u": "",
                      "d": "＋なら負けると熱くなる、−なら慎重になる傾向。", "go": TABS[1], "c": AI})
    cards.append({"k": "相打ちになったラウンド", "v": f"{rr['相打ち'].mean():.0%}", "u": f"（{int(rr['相打ち'].sum())}回）",
                  "d": "同じ数字がぶつかって、得点カードが誰のものにもならなかった割合。", "go": TABS[1], "c": "#1baf7a"})
    if real_read:
        best = g.groupby("player")["read_top1"].mean().sort_values()
        cards.append({"k": "いちばん読まれにくい人", "v": html.escape(str(best.index[0])), "u": f"的中 {best.iloc[0]:.0%}",
                      "d": "AIの予想が一番当たらなかったプレイヤー。", "go": TABS[3], "c": "#4a3aa7"})
    if len(g) < 20:
        answer(f"まだ {len(g)} 試合分のデータです。人数と試合数が増えると、下の数字やグラフは大きく変わることがあります。"
               "傾向は「いまのところ」として見てください。", warn=True, tag="データが少なめ")
    section("HIGHLIGHTS ─ いまのデータから")
    highlights(cards)


# ---- タブ1：札の出し方 -----------------------------------------------------------
def _tab_cards(d: pd.DataFrame):
    c1, c2 = st.columns(2, gap="large")
    with c1:
        question("Q1", "得点カードが大きいほど、大きい札を出す？", "得点カードの数字ごとに、出した札の平均をとりました。")
        by = d.groupby("prize")["card"].agg(["mean", "size"]).reset_index().rename(columns={"prize": "得点カード", "mean": "出した札の平均"})
        s = _slope(d)
        if np.isnan(s):
            answer("まだ比べられるほどデータがありません。", warn=True)
        else:
            hi, lo = d.loc[d["prize"] >= 8, "card"].mean(), d.loc[d["prize"] <= 3, "card"].mean()
            how = ("得点に合わせて札を選ぶ人が多いようです" if s >= 0.6 else "ある程度は得点に合わせています" if s >= 0.3
                   else "得点とあまり関係なく札を出しています")
            extra = f"得点カードが8以上なら平均 <b>{hi:.1f}</b>、3以下なら <b>{lo:.1f}</b> を出しています。" if not (np.isnan(hi) or np.isnan(lo)) else ""
            answer(f"得点カードが1大きくなると、出す札は平均で <b>{s:+.2f}</b> 大きくなります。{how}。{extra}{_few(len(d))}")
        same = pd.DataFrame({"得点カード": range(1, 11), "得点と同じ数字": range(1, 11)})
        _show(alt.layer(
            _bars(by, "得点カード", "出した札の平均", "得点カード", "出した札の平均", ".1f", sort=list(range(1, 11))),
            alt.Chart(same).mark_line(color=GRAY, strokeDash=[5, 4], strokeWidth=2).encode(x="得点カード:N", y="得点と同じ数字:Q"),
            alt.Chart(same.tail(1)).mark_text(align="right", dx=-4, dy=-10, color="#56627a", fontSize=12).encode(
                x="得点カード:N", y="得点と同じ数字:Q", text=alt.value("点線＝得点と同じ数字")),
        ), 300)
        _read_more("- 青い棒が **点線に沿っていれば**、得点カードと同じくらいの数字を出しています\n"
                   "- 棒が点線より **上** なら得点の割に強い札、**下** なら控えめな札を出しています\n"
                   "- 「+0.80」のような数字は、全部の手に直線を当てはめたときの傾きです")
    with c2:
        question("Q2", "どの組み合わせがよく出る？", "得点カードと出した札の組み合わせを数えました。色が濃いほどよく出ています。")
        heat = d.groupby(["prize", "card"]).size().reset_index(name="回数")
        top = heat.sort_values("回数", ascending=False).iloc[0]
        near = (abs(d["card"] - d["prize"]) <= 1).mean()
        answer(f"いちばん多いのは、得点カード <b>{int(top.prize)}</b> に札 <b>{int(top.card)}</b> を出した組み合わせ（{int(top.回数)}回）。"
               f"得点と±1以内の札を出したのは全体の <b>{near:.0%}</b> です（でたらめに出すと約28%）。")
        _show(alt.Chart(heat).mark_rect(stroke="white", strokeWidth=2, cornerRadius=3).encode(
            x=alt.X("prize:O", title="得点カード", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("card:O", title="出した札", sort="descending"),
            color=alt.Color("回数:Q", scale=alt.Scale(range=BLUES), legend=alt.Legend(title="回数", orient="right")),
            tooltip=[alt.Tooltip("prize:O", title="得点カード"), alt.Tooltip("card:O", title="出した札"), "回数"],
        ), 330)
        _read_more("- 左下から右上への **斜めの帯** が濃いほど、「得点に見合った札」を出す人が多いということです\n"
                   "- 左上（小さい得点に大きい札）が濃ければ、序盤から強い札を使ってしまう人が多いということです")

    question("Q3", "ラウンドが進むと、出し方は変わる？", "ラウンドごとの強気度の平均。0＝得点に見合った札、＋＝強気、−＝控えめ。")
    x = d[d["round_no"] < 10]
    if x.empty:
        answer("まだデータがありません。", warn=True)
        return
    by = x.groupby("round_no")["強気度"].mean().reset_index().rename(columns={"round_no": "ラウンド"})
    early, late = x.loc[x["round_no"] <= 3, "強気度"].mean(), x.loc[x["round_no"] >= 7, "強気度"].mean()
    if not (np.isnan(early) or np.isnan(late)):
        mood = lambda v: "強気" if v > 0.05 else "控えめ" if v < -0.05 else "ほぼ得点どおり"
        answer(f"序盤（1〜3ラウンド）は <b>{early:+.2f}</b>（{mood(early)}）、終盤（7〜9ラウンド）は <b>{late:+.2f}</b>（{mood(late)}）です。"
               "強い札を温存して後半に使う人が多いと、序盤はマイナス・終盤はプラスになります。")
    line = alt.Chart(by).encode(x=alt.X("ラウンド:O", axis=alt.Axis(labelAngle=0)), y=alt.Y("強気度:Q", title="強気度の平均"))
    _show(alt.layer(
        alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color="#56627a", strokeDash=[4, 3]).encode(y="z:Q"),
        line.mark_line(color=HUMAN, strokeWidth=2.5),
        line.mark_circle(color=HUMAN, size=90, stroke="white", strokeWidth=2).encode(tooltip=["ラウンド", alt.Tooltip("強気度:Q", format="+.2f")]),
        line.mark_text(dy=-14, fontSize=13, fontWeight=700, color="#14213a").encode(text=alt.Text("強気度:Q", format="+.2f")),
    ), 260)
    _read_more("- 最後の10ラウンド目は手札が1枚で選べないので、グラフから除いています\n"
               "- 終盤は手札が少なく選べる札が限られるので、強気度は気持ちだけでなく **手札の事情** でも動きます")


# ---- タブ2：気持ちの動き ---------------------------------------------------------
def _tab_mind(d: pd.DataFrame, rr: pd.DataFrame, dummy: bool):
    c1, c2 = st.columns(2, gap="large")
    with c1:
        question("Q4", "負けた直後は、強気になる？", "直前のラウンドの結果ごとに、次に出した札の強気度を比べました。")
        t = _after(d)
        if {"勝った", "負けた"} <= set(t.index):
            diff = t.loc["負けた", "mean"] - t.loc["勝った", "mean"]
            n = int(min(t.loc["負けた", "size"], t.loc["勝った", "size"]))
            verdict = ("負けた直後のほうが <b>強気</b> になっています。取り返したくなる気持ちが出ているのかもしれません"
                       if diff > 0.05 else "負けた直後のほうが <b>控えめ</b> です。負けると慎重になる人が多いようです"
                       if diff < -0.05 else "勝った直後と負けた直後で、<b>ほとんど差がありません</b>")
            answer(f"{verdict}（差 {diff:+.2f}）。{_few(n)}")
        else:
            answer("まだ比べられるほどデータがありません。", warn=True)
        df = t.reset_index().assign(ラベル=lambda x: x["前のラウンド"] + "（" + x["size"].astype(int).astype(str) + "手）")
        _show(_bars(df, "ラベル", "mean", "直前のラウンド", "強気度の平均", "+.2f", sort=list(df["ラベル"]), zero_rule=True), 260)
        _read_more("- 棒が上に伸びるほど「得点の割に強い札」を出しています\n"
                   "- 直前の結果だけでなく、手札の残り方も影響します。勝った直後は強い札を使った後のことが多いので、"
                   "そのぶん強気度が下がりやすい点に注意してください")
    with c2:
        question("Q5", "大一番ほど、長く考える？", "今回の得点カードが「残りの点全体」の何%かで分けて、考えた時間の中央値を比べました。")
        if dummy or d["think_ms"].isna().all():
            answer("考えた時間は、人間が実際に遊んだ記録（みんなのデータ）にだけあります。", warn=True, tag="データなし")
        else:
            th = d.dropna(subset=["think_ms"]).assign(
                重み=lambda x: pd.cut(x["prize_share"], [0, .1, .2, .35, 1], labels=["〜10%", "10〜20%", "20〜35%", "35%〜"]))
            t = th.groupby("重み", observed=True)["think_ms"].agg(["median", "size"]).reset_index()
            t["秒"] = t["median"] / 1000
            if len(t) >= 2:
                a, b = t.iloc[0], t.iloc[-1]
                answer(f"点の重みが {a['重み']} の場面は <b>{a['秒']:.1f}秒</b>、{b['重み']} の大一番は <b>{b['秒']:.1f}秒</b> でした。"
                       + ("大事な場面ほど長く考えています。" if b["秒"] > a["秒"] * 1.15 else
                          "大一番でも、考える時間はあまり変わりません。") + _few(int(min(a["size"], b["size"]))))
            _show(_bars(t, "重み", "秒", "今回の得点カードの重み", "考えた時間の中央値（秒）", ".1f", sort=list(t["重み"])), 260)
            _read_more("- 考えた時間は、ブラウザで札が出せるようになってから、クリックするまでです\n"
                       "- 平均ではなく **中央値** なので、席を外していた長い時間に引っぱられにくくしています")

    c3, c4 = st.columns(2, gap="large")
    with c3:
        question("Q6", "リードしている側ほど、相打ちになる？", "ラウンド前の点差（人間 − AI）ごとに、相打ちになった割合を出しました。")
        t = rr.groupby("点差", observed=True)["相打ち"].agg(["mean", "size"]).reset_index()
        t["割合"] = t["mean"] * 100
        answer(f"全体では <b>{rr['相打ち'].mean():.0%}</b> のラウンドが相打ちでした。"
               "点が流れると残りの点が減るので、リードしている側には得になります。")
        _show(_bars(t, "点差", "割合", "ラウンド前の点差（人間 − AI）", "相打ちになった割合（%）", ".0f",
                    sort=["6点以上負け", "1〜5点負け", "同点", "1〜5点勝ち", "6点以上勝ち"]), 260)
        _read_more("- 「同点」には1ラウンド目（0対0）も入ります。序盤は両者の手札が同じで相打ちが起きやすいので、"
                   "点差だけの効果とは言えません\n- 回数：" + " ／ ".join(f"{a} {b}回" for a, b in zip(t["点差"], t["size"])))
    with c4:
        question("Q7", "最強札が同じで、大きい得点が出たら？", "両者の一番強い札が同じ数字で、得点カードが7以上の場面だけを集めました。")
        same = rr.query("最強札が同じ and 得点カード >= 7 and 残り手札 > 1")
        if same.empty:
            answer("該当する場面がまだありません。", warn=True)
        else:
            order = ["最強札をぶつけた", "最弱札で譲った", "その間の札"]
            t = same["人間の選択"].value_counts().reindex(order, fill_value=0).rename_axis("選択").reset_index(name="回数")
            t["割合"] = t["回数"] / t["回数"].sum() * 100
            top = t.sort_values("回数", ascending=False).iloc[0]
            answer(f"{len(same)} 場面のうち、いちばん多かったのは <b>{top['選択']}</b>（{top['割合']:.0f}%）でした。")
            _show(_bars(t, "選択", "割合", "", "割合（%）", ".0f", sort=order, horizontal=True), 180)
            _read_more("- **最強札をぶつける**：相手も最強札で来たら相打ちで止められる。来なければ点が取れる\n"
                       "- **最弱札で譲る**：点は取られても、自分の最強札が「出せば必ず勝つ札」として残る\n"
                       "- 正解は1つではなく、相手がどちらを選びそうかの **読み合い** になります")


# ---- タブ3：プレイヤー -----------------------------------------------------------
def _tab_players(g: pd.DataFrame, d: pd.DataFrame):
    names = sorted(g["player"].unique())
    me = st.session_state.get("last_player")
    question("P1", "プレイヤーのカルテ", "名前を選ぶと、その人の出し方を「みんな」と比べます。対戦で送った名前を選んでみてください。")
    who = st.selectbox("プレイヤー", names, index=names.index(me) if me in names else 0, key="shared_who")
    mg, md = g[g["player"] == who], d[d["player"] == who]
    m = st.columns(4)
    m[0].metric("試合", f"{len(mg)} 試合", border=True)
    m[1].metric("勝率", f"{mg['人間の勝ち'].mean():.0%}", delta=f"{(mg['人間の勝ち'].mean() - g['人間の勝ち'].mean()) * 100:+.0f}pt",
                delta_description="みんな比", border=True)
    m[2].metric("強気度", f"{md['強気度'].mean():+.2f}", delta=f"{md['強気度'].mean() - d['強気度'].mean():+.2f}", delta_description="みんな比",
                delta_color="off", border=True, help="0＝得点に見合った札、＋＝強気、−＝控えめ")
    if mg["read_top1"].notna().any():
        r = mg["read_top1"].mean()
        m[3].metric("AIの読みの的中率", f"{r:.0%}", delta=f"{(r - g['read_top1'].mean()) * 100:+.0f}pt", delta_description="みんな比",
                    delta_color="inverse", border=True, help="低いほど読まれにくい")
    else:
        m[3].metric("出した手", f"{len(md)} 手", border=True)
    comp = pd.concat([
        md.groupby("prize")["card"].mean().rename(html.escape(str(who))),
        d.groupby("prize")["card"].mean().rename("みんな"),
    ], axis=1).reset_index().melt("prize", var_name="誰", value_name="出した札の平均").dropna()
    hi_me, hi_all = md.loc[md["prize"] >= 8, "card"].mean(), d.loc[d["prize"] >= 8, "card"].mean()
    if not np.isnan(hi_me):
        diff = hi_me - hi_all
        answer(f"{html.escape(str(who))} さんは、得点カードが8以上のときに平均 <b>{hi_me:.1f}</b> を出しています（みんなは {hi_all:.1f}）。"
               + ("大きい得点で勝負に出るタイプです。" if diff > 0.7 else "大きい得点でも札を温存するタイプです。" if diff < -0.7
                  else "みんなと同じくらいの出し方です。") + _few(len(md)), tag="カルテ")
    enc = dict(x=alt.X("prize:O", title="得点カード", axis=alt.Axis(labelAngle=0)), y=alt.Y("出した札の平均:Q", scale=alt.Scale(domain=[0, 10])),
               color=alt.Color("誰:N", scale=alt.Scale(domain=[html.escape(str(who)), "みんな"], range=[HUMAN, GRAY]),
                               legend=alt.Legend(title=None)))
    base = alt.Chart(comp).encode(**enc)
    _show(alt.layer(base.mark_line(strokeWidth=2.5),
                    base.mark_circle(size=80, stroke="white", strokeWidth=2, opacity=1).encode(
                        tooltip=[alt.Tooltip("prize:O", title="得点カード"), "誰", alt.Tooltip("出した札の平均:Q", format=".1f")])), 260)

    st.divider()
    question("P2", "プレイヤー一覧", "列の見出しをクリックすると並べ替えられます。「札の出し方」は得点カード1→10のときに出した札の平均です。")
    per = d.groupby("player").agg(手数=("card", "size"), 強気度=("強気度", "mean"), ばらつき=("強気度", "std"))
    shape = d.pivot_table(index="player", columns="prize", values="card", aggfunc="mean").reindex(columns=range(1, 11))
    per["札の出し方"] = shape.fillna(0).round(1).values.tolist()
    gg = g.groupby("player").agg(試合=("game_id", "size"), 勝率=("人間の勝ち", "mean"), 自分=("my_score", "mean"),
                                 AI=("ai_score", "mean"), AIの的中率=("read_top1", "mean"))
    gg["平均点差"] = gg["自分"] - gg["AI"]
    table = gg.drop(columns=["自分", "AI"]).join(per).sort_values(["試合", "勝率"], ascending=False).reset_index()
    table[["勝率", "AIの的中率"]] *= 100
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "player": st.column_config.TextColumn("プレイヤー", pinned=True),
        "試合": st.column_config.NumberColumn("試合", format="%d"),
        "勝率": st.column_config.ProgressColumn("勝率", format="%.0f%%", min_value=0, max_value=100, color="blue"),
        "AIの的中率": st.column_config.ProgressColumn("AIの読みの的中率", format="%.0f%%", min_value=0, max_value=100, color="orange",
                                                  help="低いほど読まれにくい"),
        "平均点差": st.column_config.NumberColumn("平均点差", format="%+.1f", help="自分の点 − AIの点の平均"),
        "手数": st.column_config.NumberColumn("手数", format="%d"),
        "強気度": st.column_config.NumberColumn("強気度", format="%+.2f", help="0＝得点に見合った札、＋＝強気、−＝控えめ"),
        "ばらつき": st.column_config.NumberColumn("ばらつき", format="%.2f", help="強気度の標準偏差。大きいほど出し方が読まれにくいはず"),
        "札の出し方": st.column_config.BarChartColumn("札の出し方（得点1→10）", y_min=0, y_max=10, color="blue",
                                                 help="得点カード1〜10のときに出した札の平均。右上がりなら得点に合わせて出している"),
    })

    question("P3", "プレイスタイルの地図", "1つの点が1人。右ほど強気、上ほど出し方が気まぐれ（読みにくい）。点の大きさは手数です。")
    sc = table.dropna(subset=["ばらつき"])
    if sc.empty:
        answer("2手以上出した人がいると表示されます。", warn=True)
        return
    a = max(0.3, float(sc["強気度"].abs().max()) * 1.25)   # 0（得点どおり）を真ん中にする
    base = alt.Chart(sc).encode(x=alt.X("強気度:Q", title="← 控えめ　　強気度の平均　　強気 →",
                                        scale=alt.Scale(domain=[-a, a]), axis=alt.Axis(format="+.1f", tickCount=7)),
                                y=alt.Y("ばらつき:Q", title="ばらつき（気まぐれさ）", scale=alt.Scale(domainMin=0)))
    layers = [alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(color=GRAY, strokeDash=[4, 3]).encode(x="z:Q"),
              base.mark_circle(color=HUMAN, stroke="white", strokeWidth=2, opacity=.85).encode(
                  size=alt.Size("手数:Q", legend=None, scale=alt.Scale(range=[80, 500])),
                  tooltip=["player", "試合", alt.Tooltip("強気度:Q", format="+.2f"), alt.Tooltip("ばらつき:Q", format=".2f"),
                           alt.Tooltip("勝率:Q", format=".0f")])]
    if len(sc) <= 20:   # 人数が少ないうちは名前を直接書く
        layers.append(base.mark_text(dy=-14, fontSize=12, fontWeight=600, color="#14213a").encode(text="player:N"))
    _show(alt.layer(*layers), 340)
    _read_more("- **右上**：強気で、出し方も読みにくい人\n- **右下**：いつも強気で一貫している人（読まれやすいかも）\n"
               "- **左下**：いつも控えめで一貫している人\n- **左上**：控えめだけど、ときどき思い切る人")


# ---- タブ4：AIとの勝負 -----------------------------------------------------------
def _tab_ai(g: pd.DataFrame, real_read: bool):
    if not real_read:
        answer("AIの読みの成績は、人間が実際にAIと対戦した記録（みんなのデータ）で表示されます。", warn=True, tag="データなし")
        return
    r = g.dropna(subset=["read_top1"]).reset_index(drop=True)
    r["何試合目"] = r.index + 1
    r["直近10試合の平均"] = r["read_top1"].rolling(10, min_periods=1).mean()
    rate = r["read_top1"].mean()
    question("Q8", "AIの読みは、どれくらい当たっている？", "AIが「次はこの札を出す」と一番に予想した札が当たった割合を、試合ごとに並べました。")
    answer(f"これまでの平均は <b>{rate:.0%}</b>。当てずっぽう（約{GUESS:.0%}）の <b>{rate / GUESS:.1f}倍</b> 当たっています。"
           + ("人間のクセをかなり読めています。" if rate > GUESS * 1.6 else "少しは読めていますが、まだ人間のほうが一枚上手です。"
              if rate > GUESS * 1.15 else "まだ当てずっぽうと大差ありません。データが増えると変わるかもしれません。"))
    base = alt.Chart(r).encode(x=alt.X("何試合目:Q", title="何試合目（送られた順）"))
    guess = pd.DataFrame({"y": [GUESS], "label": [f"当てずっぽう {GUESS:.0%}"]})
    _show(alt.layer(
        alt.Chart(guess).mark_rule(color=GRAY, strokeDash=[5, 4], strokeWidth=2).encode(y="y:Q"),
        alt.Chart(guess).mark_text(align="left", x=4, dy=-8, color="#56627a", fontSize=12).encode(y="y:Q", text="label:N"),
        base.mark_circle(size=55, color="#c3c9d4").encode(
            y=alt.Y("read_top1:Q", title="的中率", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            tooltip=["player", alt.Tooltip("read_top1:Q", title="的中率", format=".0%"), alt.Tooltip("ai_model:N", title="AIの版")]),
        base.mark_line(strokeWidth=2.5, color=AI).encode(y="直近10試合の平均:Q"),
    ), 300)
    _read_more("- 灰色の点＝1試合ごとの的中率、オレンジの線＝直近10試合の平均\n"
               "- 最後の10ラウンド目は手札が1枚で読むまでもないので、的中率から除いています\n"
               "- AIは新しい版になるほど、みんなのデータで学び直しています（版は下の表）")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        question("A1", "AIの版ごとの成績")
        ver = g.groupby("ai_model").agg(試合=("game_id", "size"), 人間の勝率=("人間の勝ち", "mean"),
                                        読みの的中率=("read_top1", "mean")).reset_index()
        ver[["人間の勝率", "読みの的中率"]] *= 100
        st.dataframe(ver, hide_index=True, width="stretch", column_config={
            "ai_model": st.column_config.TextColumn("AIの版"),
            "人間の勝率": st.column_config.ProgressColumn("人間の勝率", format="%.0f%%", min_value=0, max_value=100, color="blue"),
            "読みの的中率": st.column_config.ProgressColumn("読みの的中率", format="%.0f%%", min_value=0, max_value=100, color="orange"),
        })
        st.caption("同じ人が何度も遊ぶと上手くなるので、後の版ほど人間が強い相手と戦っている点に注意してください。")
    with c2:
        question("A2", "読まれにくい人ランキング")
        rank = g.groupby("player")["read_top1"].agg(["mean", "size"]).dropna().sort_values("mean").reset_index()
        rank.insert(0, "順位", range(1, len(rank) + 1))
        rank["mean"] *= 100
        st.dataframe(rank.head(20), hide_index=True, width="stretch", column_config={
            "順位": st.column_config.NumberColumn("順位", format="%d位"),
            "player": st.column_config.TextColumn("プレイヤー"),
            "mean": st.column_config.ProgressColumn("AIの的中率", format="%.0f%%", min_value=0, max_value=100, color="orange"),
            "size": st.column_config.NumberColumn("試合", format="%d"),
        })
        st.caption("AIの予想が当たらなかった順。1試合だけだと運の影響が大きいので、試合数もあわせて見てください。")


# ---- タブ5：データ ---------------------------------------------------------------
COLUMNS = {
    "game_id": "試合ごとの番号", "received_at": "送られた日時", "player": "プレイヤー名", "ai_level": "AIの強さ",
    "my_score": "人間の得点", "ai_score": "AIの得点", "result": "勝敗（人間から見て）", "burned": "相打ちで流れた点",
    "read_top1": "AIの読みの的中率", "read_prob": "AIが当たった札に付けていた確率の平均", "ai_model": "対戦したAIの版",
}


def _tab_data(g: pd.DataFrame, games: list[dict], store, dummy: bool):
    question("DL", "生のデータ", "このページのグラフは、すべてこの表から計算しています。CSVで書き出して、自分で分析することもできます。")
    rounds = pd.DataFrame([{"game_id": x["game_id"], "player": x["player"], **r} for x in games for r in x["rounds"]])
    c1, c2, c3 = st.columns(3)
    c1.download_button("試合ごとのCSV", g.to_csv(index=False).encode("utf-8-sig"), "yomiai_games.csv", "text/csv",
                       width="stretch", icon=":material/download:")
    c2.download_button("ラウンドごとのCSV", rounds.to_csv(index=False).encode("utf-8-sig"), "yomiai_rounds.csv",
                       "text/csv", width="stretch", icon=":material/download:")
    c3.download_button("学習用CSV（特徴量つき）", opp_dataset(games).to_csv(index=False).encode("utf-8-sig"),
                       "yomiai_features.csv", "text/csv", width="stretch", icon=":material/download:")
    shown = g[[c for c in COLUMNS if c in g.columns]]
    st.dataframe(shown, hide_index=True, width="stretch", height=360, column_config={
        k: st.column_config.Column(k, help=v) for k, v in COLUMNS.items()} | {
        "read_top1": st.column_config.NumberColumn("read_top1", help=COLUMNS["read_top1"], format="percent"),
    })
    with st.expander("列の意味", icon=":material/table_view:"):
        st.dataframe(pd.DataFrame({"列": list(COLUMNS), "意味": list(COLUMNS.values())}), hide_index=True, width="stretch")
        st.markdown("ラウンドごとのCSVには、得点カード（prize）・両者の札（human_card, ai_card）・考えた時間（think_ms, ミリ秒）・"
                    "AIの予想（ai_read）が入っています。")
    if not dummy:
        if store.kind == "sheet":
            st.caption("不適切な名前や消してほしい記録は、スプレッドシートの yomiai_games タブの行を消すと、"
                       "1分ほどでここからも消えます（yomiai_rounds の行は残っていても無視されます）。")
        else:
            st.caption("Secrets が設定されていないため、手元の data/ フォルダに保存しています。")
