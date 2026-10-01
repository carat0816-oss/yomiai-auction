"""📊 みんなのデータ：スプレッドシートに集まった対戦をまとめて見る・比べる・書き出す。"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from game import replay
from ml import opp_dataset
from views.ui import page_header

HUMAN, AI = "#2a78d6", "#eb6834"
BLUES = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]


def choose_source(games: list[dict], key: str) -> tuple[list[dict], bool]:
    """分析に使うデータ：スプレッドシートの本物か、練習用のダミー（ボット同士の対戦）か。"""
    src = st.segmented_control("データ", ["みんなのデータ", "ダミー（練習用）"], default="みんなのデータ", key=f"{key}_src")
    if src == "ダミー（練習用）":
        c1, c2, c3 = st.columns(3)
        n = c1.slider("ボットの人数", 5, 80, 30, key=f"{key}_n")
        k = c2.slider("1人あたりの試合数", 1, 10, 3, key=f"{key}_k")
        seed = c3.number_input("乱数の種", 0, 999, 0, key=f"{key}_seed")
        st.caption("⚠️ ダミーは、5つの「型」（比例型・強気型・慎重型・温存型・気まぐれ型）のボットが遊んだ架空のデータです。"
                   "人間のデータではありません。")
        return _dummy(n, k, int(seed)), True
    return games, False


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


def show_shared(games: list[dict], store):
    page_header("DATA", "みんなのデータ",
                "「データ提供に同意」して送られた対戦の記録です。スプレッドシートから1分ごとに読み直します。")
    games, dummy = choose_source(games, "shared")
    if not games:
        st.info("まだ記録がありません。対戦のあと「みんなのデータに送る」と、ここに集まります。"
                "上の「ダミー（練習用）」で、画面の見え方を先に試せます。")
        return
    g = pd.DataFrame([{k: v for k, v in x.items() if k not in ("rounds", "prizes")} for x in games])
    d = decisions(games)
    players = sorted(g["player"].unique())
    chosen = st.multiselect("プレイヤーで絞り込む（空なら全員）", players, key="shared_players")
    if chosen:
        g, d = g[g["player"].isin(chosen)], d[d["player"].isin(chosen)]
    if g.empty:
        st.info("該当する記録がありません。")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("試合", f"{len(g)} 試合", border=True)
    m2.metric("プレイヤー", f"{g['player'].nunique()} 人", border=True)
    m3.metric("出された手", f"{len(d)} 手", border=True)
    win = (g["my_score"] > g["ai_score"]).mean()
    m4.metric("人間側の勝率", f"{win:.0%}", border=True)

    t1, t2, t3, t4 = st.tabs(["🃏 出し方のクセ", "👤 プレイヤー別", "🤖 AIの読み", "📋 データ・CSV"])

    with t1:
        st.markdown("#### 得点カードの数字ごとに、どの札を出した？")
        heat = d.groupby(["prize", "card"]).size().reset_index(name="回数")
        st.altair_chart(alt.Chart(heat).mark_rect(stroke="white", strokeWidth=2).encode(
            x=alt.X("prize:O", title="得点カード"), y=alt.Y("card:O", title="出した札", sort="descending"),
            color=alt.Color("回数:Q", scale=alt.Scale(range=BLUES), legend=alt.Legend(title="回数")),
            tooltip=[alt.Tooltip("prize:O", title="得点カード"), alt.Tooltip("card:O", title="出した札"), "回数"],
        ).properties(height=320), width="stretch")
        st.caption("色が濃いほどよく出された組み合わせ。斜めに並ぶほど「得点に見合った札」を出す人が多いということです。")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 負けた後は強気になる？")
            lr = d[d["round_no"] > 1].assign(前のラウンド=lambda x: x["last_result"].map({1: "勝った", 0: "相打ち", -1: "負けた"}))
            t = lr.groupby("前のラウンド")["強気度"].agg(["mean", "size"]).reindex(["勝った", "相打ち", "負けた"]).dropna()
            st.bar_chart(t["mean"].rename("強気度の平均"), color=HUMAN, height=220)
            st.caption("強気度＝出した札の手札内順位 − 得点カードの順位。＋なら得点の割に強い札。"
                       + " / ".join(f"{i} {int(n)}手" for i, n in t["size"].items()))
        with c2:
            st.markdown("#### リードしている側ほど相打ちになる？")
            rr = round_frame(games)
            t = rr.groupby("点差", observed=True)["相打ち"].agg(["mean", "size"])
            st.bar_chart((t["mean"] * 100).rename("相打ちになった割合（%）"), color=HUMAN, height=220)
            st.caption("点差はラウンド前の「人間 − 相手」。点が流れると残りが減るので、リードしている側には得になります。"
                       "ただし「同点」には1ラウンド目（0対0）も入り、序盤は手札が同じで相打ちが起きやすいので、点差だけの効果とは言えません。"
                       + " / ".join(f"{i} {int(n)}回" for i, n in t["size"].items()))
        st.markdown("#### 最強札が同じで、大きい得点カードが出たら？")
        same = round_frame(games).query("最強札が同じ and 得点カード >= 7 and 残り手札 > 1")
        if same.empty:
            st.caption("該当する場面がまだありません。")
        else:
            order = ["最強札をぶつけた", "最弱札で譲った", "その間の札"]
            t = same["人間の選択"].value_counts().reindex(order, fill_value=0)
            st.bar_chart((t / t.sum() * 100).rename("割合（%）"), color=HUMAN, height=200, horizontal=True)
            st.caption(f"{len(same)} 場面。最強札をぶつけると、相手が最強札で来たときに相打ちで止められます。"
                       "最弱札で譲ると、点は取られても自分の最強札が「出せば必ず勝つ札」として残ります。")
        st.markdown("#### ラウンドが進むと？")
        st.line_chart(d.groupby("round_no")["強気度"].mean().rename("強気度の平均"), color=HUMAN, height=220)
        st.caption("終盤は手札が少なく選べる札が限られるので、強気度は気持ちだけでなく手札の事情でも動きます。")
        if not dummy and d["think_ms"].notna().any():
            st.markdown("#### 大一番ほど長く考える？")
            th = d.dropna(subset=["think_ms"]).assign(
                今回の点の重み=lambda x: pd.cut(x["prize_share"], [0, .1, .2, .35, 1], labels=["〜10%", "10〜20%", "20〜35%", "35%〜"]))
            st.bar_chart((th.groupby("今回の点の重み", observed=True)["think_ms"].median() / 1000).rename("考えた時間の中央値（秒）"),
                         color=HUMAN, height=220)
            st.caption("今回の得点カードが、残りの点全体の何%か。考えた時間は、ブラウザで札が出せるようになってからクリックまでです。")

    with t2:
        st.markdown("#### プレイヤーごとのクセ")
        per = d.groupby("player").agg(手数=("card", "size"), 強気度=("強気度", "mean"), ばらつき=("強気度", "std"))
        gg = g.assign(勝ち=g["my_score"] > g["ai_score"]).groupby("player").agg(試合=("game_id", "size"), 勝ち=("勝ち", "sum"),
                                      平均点差=("my_score", "mean"))
        gg["平均点差"] = gg["平均点差"] - g.groupby("player")["ai_score"].mean()
        table = gg.join(per).sort_values("勝ち", ascending=False).round(2)
        st.dataframe(table, width="stretch")
        st.caption("ばらつき＝強気度の標準偏差。大きい人ほど出し方が読まれにくいはずです。")
        sc = table.reset_index()
        st.altair_chart(alt.Chart(sc).mark_circle(size=120, color=HUMAN, stroke="white", strokeWidth=2).encode(
            x=alt.X("強気度:Q"), y=alt.Y("ばらつき:Q"), tooltip=["player", "試合", "強気度", "ばらつき", "平均点差"],
        ).properties(height=280), width="stretch")
        st.caption("1点＝1人。右ほど強気、上ほど気まぐれ。")

    with t3:
        if dummy or g["read_top1"].isna().all():
            st.caption("AIと実際に対戦した記録（みんなのデータ）で表示されます。")
        else:
            st.markdown("#### みんなが遊ぶほど、AIの読みは当たるようになった？")
            r = g.dropna(subset=["read_top1"]).reset_index(drop=True)
            r["何試合目"] = r.index + 1
            r["直近10試合の平均"] = r["read_top1"].rolling(10, min_periods=1).mean()
            base = alt.Chart(r).encode(x=alt.X("何試合目:Q"))
            st.altair_chart(
                base.mark_circle(size=60, color="#c3c2b7").encode(y=alt.Y("read_top1:Q", title="的中率", axis=alt.Axis(format="%")),
                                                                   tooltip=["player", "read_top1", "ai_model"])
                + base.mark_line(strokeWidth=2, color=AI).encode(y="直近10試合の平均:Q"),
                width="stretch")
            st.caption("灰色の点＝1試合ごとの的中率、線＝直近10試合の平均。当てずっぽうなら約29%です。")
            st.markdown("#### 読まれにくい人ランキング")
            st.dataframe(g.groupby("player")["read_top1"].agg(["mean", "size"]).rename(
                columns={"mean": "AIの的中率", "size": "試合"}).sort_values("AIの的中率").round(3), width="stretch")

    with t4:
        st.dataframe(g, width="stretch", hide_index=True)
        rounds = pd.DataFrame([{"game_id": x["game_id"], "player": x["player"], **r} for x in games for r in x["rounds"]])
        c1, c2, c3 = st.columns(3)
        c1.download_button("試合ごとのCSV", g.to_csv(index=False).encode("utf-8-sig"), "yomiai_games.csv", "text/csv",
                           width="stretch")
        c2.download_button("ラウンドごとのCSV", rounds.to_csv(index=False).encode("utf-8-sig"), "yomiai_rounds.csv",
                           "text/csv", width="stretch")
        c3.download_button("学習用CSV（特徴量つき）", opp_dataset(games).to_csv(index=False).encode("utf-8-sig"),
                           "yomiai_features.csv", "text/csv", width="stretch")
        if not dummy:
            if store.kind == "sheet":
                st.caption("不適切な名前や消してほしい記録は、スプレッドシートの yomiai_games タブの行を消すと、"
                           "1分ほどでここからも消えます（yomiai_rounds の行は残っていても無視されます）。")
            else:
                st.caption("Secrets が設定されていないため、手元の data/ フォルダに保存しています。")
