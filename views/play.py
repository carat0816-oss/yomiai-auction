"""🎮 対戦画面：AIと10ラウンド戦い、リザルトを見て、同意したら「みんなのデータ」に送る。"""
from __future__ import annotations

import random
import time
import uuid

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v2 as components

from game import N_ROUNDS, is_over, new_game, outcome, resolve
from store import LEVELS, PROFILE, clean_game
from views.ui import page_header, rules_card

HUMAN, AI = "#2a78d6", "#eb6834"
MAX_PER_SESSION = 40     # 1回の接続で送れる試合数（いたずら対策）
GUESS_9 = sum(1 / n for n in range(2, N_ROUNDS + 1))   # 最終ラウンド以外を当てずっぽうで当てる回数の期待値
BOARD = Path(__file__).resolve().parent.parent / "board"


def _fmt_read(read: dict, k: int = 3) -> str:
    top = sorted(read.items(), key=lambda x: -x[1])[:k]
    return " ".join(f"{c}:{p:.0%}" for c, p in top)


def _start():
    ss = st.session_state
    ss.game_id = str(uuid.uuid4())
    ss.rng = random.Random()
    ss.state = new_game(ss.rng)
    ss.rec = {"prizes": ss.state["prizes"], "rounds": [], "ai_level": ss.get("ai_level") or "ふつう",
              "profile": {k: ss.get(f"profile_{k}") for k in PROFILE},
              "version": ss.get("ai_version")}   # 試合の途中で版が変わらないよう、始めた時点の版を覚える
    ss.pending = None
    ss.last = None
    ss.pop("consent", None)


def _play(card: int, think_ms=None):
    """人間が札を出した。AIの札は、このラウンドが始まった時点で決めてある（後出しはしない）。
    考えた時間は、ブラウザで測った値（盤面に札が出てからクリックまで）を優先する。"""
    ss = st.session_state
    p = ss.pending
    if p is None or card not in ss.state["hands"][0]:
        return
    think = round(think_ms) if isinstance(think_ms, (int, float)) and 0 <= think_ms < 3_600_000 \
        else round((time.time() - p["shown_at"]) * 1000)
    read = p["read"]
    top = max(read, key=read.get)
    ss.rec["rounds"].append({"human_card": card, "ai_card": p["card"], "think_ms": think, "read_top": top,
                             "read_prob": round(read.get(card, 0.0), 4), "ai_read": _fmt_read(read),
                             "ai_win": round(p["win"], 4)})
    before = ss.state
    ss.state = resolve(before, card, p["card"])
    ss.last = {"log": ss.state["log"][-1], "read": read, "top": top, "ev": p["ev"], "card": card,
               "ai_card": p["card"], "win": p["win"]}
    ss.pending = None


def _intro(registry: dict):
    page_header("YOMIAI AUCTION", "読み合いオークション",
                "1〜10の手札で、得点カードを取り合う心理戦。AIはみんなの対戦データから、あなたが出しそうな札を予測してきます。")
    rules_card()
    versions = registry["versions"]
    with st.container(border=True):
        st.markdown("**プレイ前のしつもん**　<small>任意。予測モデルの材料になります</small>", unsafe_allow_html=True)
        cols = st.columns(len(PROFILE))
        for col, (k, (label, choices)) in zip(cols, PROFILE.items()):
            col.selectbox(label, choices, index=len(choices) - 1, key=f"profile_{k}")
        c1, c2 = st.columns(2)
        c1.segmented_control("AIの強さ", list(LEVELS), default="ふつう", key="ai_level")
        if versions:
            names = {v["slug"]: v["name"] + ("（現役）" if v["slug"] == registry.get("active") else "") for v in versions}
            slugs = list(names)
            if st.session_state.get("ai_version") not in slugs:
                st.session_state.ai_version = registry.get("active") or slugs[0]
            c2.selectbox("対戦するAIの版", slugs, format_func=names.get, key="ai_version")
    st.button("対戦スタート →", type="primary", width="stretch", on_click=_start)
    if versions:
        with st.expander("AIの版（リリースノート）"):
            release_notes(registry)


def release_notes(registry: dict):
    """版ごとの公開日・学習データ・成績・メモ。"""
    for v in registry["versions"]:
        m = v.get("metrics", {})
        tag = "　`現役`" if v["slug"] == registry.get("active") else ""
        st.markdown(f"**{v['name']}**{tag}　<small>{v['created_at']}</small>", unsafe_allow_html=True)
        facts = [f"{v['n_games']} 試合・{v['n_moves']} 手で学習", f"読み：{v['model']}"]
        if "読みの的中率" in m:
            facts.append(f"読みの的中率 {m['読みの的中率']:.0%}（ルールなら {m['ルールの的中率']:.0%}）")
        if "ボット相手の勝率" in m:
            facts.append(f"ボット相手の勝率 {m['ボット相手の勝率']:.0%}")
        st.caption(" ／ ".join(facts) + (f"\n\n{v['notes']}" if v.get("notes") else ""))


@st.cache_resource
def _load_board(asset_version):
    return components.component(
        "yomiai_board",
        html=(BOARD / "board.html").read_text(encoding="utf-8"),
        css=(BOARD / "board.css").read_text(encoding="utf-8"),
        js=(BOARD / "board.js").read_text(encoding="utf-8"),
    )


def _board_data(brain) -> dict:
    """盤面に渡す局面。まだ公開されていない得点カードの順番は渡さない（見えてしまうため）。"""
    ss = st.session_state
    s = ss.state
    over = is_over(s)
    last = ss.get("last")
    win_p = outcome(s, 0) if over else float(1 - brain.value([s], 1)[0])
    return {
        "r": s["r"], "n": N_ROUNDS, "over": over,
        "prize": None if over else s["prizes"][s["r"]],
        "score": s["score"], "hands": s["hands"], "win_p": round(win_p, 4),
        "log": [{"round": lg["round"], "prize": lg["prize"], "cards": lg["cards"], "winner": lg["winner"],
                 "score": lg["score"]} for lg in s["log"]],
        "last": None if not last else {
            "round": last["log"]["round"], "top": last["top"],
            "read": {str(c): round(p, 4) for c, p in last["read"].items()},
            "ev": [[a, round(v, 4)] for a, v in sorted(last["ev"].items(), key=lambda x: -x[1])[:3]],
        },
    }


def _board(brain):
    ss = st.session_state
    board = _load_board(tuple((BOARD / f).stat().st_mtime_ns for f in ("board.html", "board.css", "board.js")))
    res = board(key=f"board_{ss.game_id}", data=_board_data(brain), on_play_change=lambda: None)
    move = res.play if res is not None else None
    if move and not is_over(ss.state) and move.get("round") == ss.state["r"]:
        _play(int(move["card"]), move.get("think_ms"))
        st.rerun()


def _queued():
    """テスト用の入口：session_state["queued_play"] に置いた札を出す（画面の盤面と同じ処理）。"""
    ss = st.session_state
    q = ss.pop("queued_play", None)
    if q and "state" in ss and not is_over(ss.state):
        _ensure_pending()
        _play(int(q["card"]), q.get("think_ms"))


def _ensure_pending():
    ss = st.session_state
    if ss.pending is None and not is_over(ss.state):
        thinks = [r["think_ms"] for r in ss.rec["rounds"]]
        choice = ss.brain.choose(ss.state, 1, ss.rng, thinks, ss.rec["profile"], LEVELS[ss.rec["ai_level"]])
        ss.pending = {**choice, "shown_at": time.time()}


def _playing(brain):
    ss = st.session_state
    ss.rec.setdefault("ai_model", brain.version)
    _ensure_pending()
    _board(brain)
    c1, c2 = st.columns([3, 1])
    c1.caption(f"AI：{brain.version}（強さ {ss.rec['ai_level']}）／ 相手の読み：{brain.opp_name}")
    if c2.button("対戦をやめる", width="stretch"):
        for k in ("state", "rec", "pending", "last", "game_id"):
            ss.pop(k, None)
        st.rerun()

def _share(store, load_shared):
    ss = st.session_state
    saved = ss.setdefault("saved_ids", set())
    with st.container(border=True):
        if ss.game_id in saved:
            st.success("この対戦を「みんなのデータ」（スプレッドシート）に送りました。AIの学習に使われます。")
            return
        st.markdown("**📤 この対戦を「みんなのデータ」に送る**")
        if "player_name" not in ss:
            ss.player_name = ss.get("last_player", "")
        player = st.text_input("プレイヤー名（ニックネームにしてください）", max_chars=16, key="player_name",
                               placeholder="例：よみあい名人")
        consent = st.checkbox("データ提供に同意する（名前・しつもんの答え・出した札と考えた時間が保存され、"
                              "このアプリを使う全員が見られます。AIの学習にも使われます）", key="consent")
        if st.button("送る", disabled=not consent, key="share"):
            if len(saved) >= MAX_PER_SESSION:
                st.warning("この接続で送れる回数の上限に達しました。ページを読み込み直してください。")
                return
            game = clean_game(ss.game_id, player, ss.rec)
            if not game:
                st.error("記録の形式がおかしいため、送れませんでした。")
                return
            try:
                store.append(game)
            except Exception as e:
                st.error(f"データの保存に失敗しました：{e}")
                return
            saved.add(ss.game_id)
            ss.last_player = player
            load_shared.clear()
            st.rerun()


def _result(brain, store, load_shared):
    ss = st.session_state
    s, rec = ss.state, ss.rec
    me, ai = s["score"]
    _board(brain)
    a, b, c = st.columns(3)
    a.metric("結果", "勝ち" if me > ai else "負け" if me < ai else "引き分け", f"{me - ai:+d} 点", delta_color="normal", border=True)
    hits = sum(r["read_top"] == r["human_card"] for r in rec["rounds"][:-1])
    b.metric("AIの読みの的中", f"{hits} / {N_ROUNDS - 1}", border=True)
    think = [r["think_ms"] for r in rec["rounds"]]
    c.metric("平均の考えた時間", f"{sum(think) / len(think) / 1000:.1f} 秒", border=True)
    st.caption(f"AIの読みの的中は、残り1枚で決まっている最終ラウンドを除いた{N_ROUNDS - 1}回のうちの数。"
               f"当てずっぽうなら平均 {GUESS_9:.1f} 回くらい当たります。")
    _share(store, load_shared)
    df = pd.DataFrame([{"ラウンド": i + 1, "得点カード": lg["prize"],
                        "あなた": lg["cards"][0], "AI": lg["cards"][1],
                        "勝者": {0: "あなた", 1: "AI", -1: "相打ち（流れた）"}[lg["winner"]],
                        "AIの読み": r["ai_read"], "出した札にAIがつけた確率": r["read_prob"],
                        "考えた時間（秒）": round(r["think_ms"] / 1000, 1)}
                       for i, (lg, r) in enumerate(zip(s["log"], rec["rounds"]))])
    t1, t2 = st.tabs(["📈 ふりかえり", "📋 全ラウンド・CSV"])
    with t1:
        st.markdown("#### 得点カードに対して、どの札を出した？")
        long = df.melt(id_vars=["ラウンド", "得点カード"], value_vars=["あなた", "AI"], var_name="プレイヤー",
                       value_name="出した札")
        chart = alt.Chart(long).mark_circle(size=110, opacity=0.9, stroke="white", strokeWidth=2).encode(
            x=alt.X("得点カード:Q", scale=alt.Scale(domain=[0, 11]), axis=alt.Axis(values=list(range(1, 11)))),
            y=alt.Y("出した札:Q", scale=alt.Scale(domain=[0, 11]), axis=alt.Axis(values=list(range(1, 11)))),
            color=alt.Color("プレイヤー:N", scale=alt.Scale(domain=["あなた", "AI"], range=[HUMAN, AI]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["ラウンド", "得点カード", "プレイヤー", "出した札"]).properties(height=280)
        st.altair_chart(chart, width="stretch")
        st.caption("斜めの線に近いほど「得点に見合った札」を出しています。上にずれると強気、下にずれると温存。")
        st.markdown("#### AIはどれくらい読めていた？")
        st.bar_chart(df.set_index("ラウンド")[["出した札にAIがつけた確率"]], color=HUMAN, height=200)
        st.caption("各ラウンドで、あなたが実際に出した札に、AIが前もってつけていた確率。高いほど読まれています。")
    with t2:
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button("CSVで保存", df.to_csv(index=False).encode("utf-8-sig"), "yomiai_game.csv", "text/csv")
    if st.button("もう一度対戦する", type="primary", width="stretch"):
        for k in ("state", "rec", "pending", "last", "game_id"):
            ss.pop(k, None)
        st.rerun()


def show_play(get_brain, registry: dict, store, load_shared):
    ss = st.session_state
    if "state" in ss:
        brain = get_brain(ss.rec.get("version"))       # 試合中は、始めたときの版のまま
    else:
        brain = get_brain(ss.get("ai_version") or registry.get("active"))
    ss.brain = brain
    _queued()
    if "state" not in ss:
        _intro(registry)
    elif not is_over(ss.state):
        _playing(brain)
    else:
        _result(brain, store, load_shared)
