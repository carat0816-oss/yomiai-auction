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

from game import N_ROUNDS, is_over, new_game, resolve
from store import LEVELS, clean_game
from views.ui import below_board_css, page_header, result_hero, rules_card, show_chart

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
              "profile": {},   # プレイ前の質問はなくした（スプレッドシートには「答えない」が入る）
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
               "ai_card": p["card"], "win": p["win"], "cands": p.get("cands") or {}}
    ss.pending = None
    if is_over(ss.state):
        ss.just_over = True   # リザルトは盤面のアニメーションが終わってから見せる


def _intro(registry: dict):
    page_header("YOMIAI AUCTION", "読み合いオークション",
                "1〜10の手札で、得点カードを取り合う心理戦。AIはみんなの対戦データから、あなたが出しそうな札を予測してきます。")
    rules_card()
    versions = registry["versions"]
    with st.container(border=True):
        c1, c2 = st.columns(2)
        c1.segmented_control("AIの強さ", list(LEVELS), default="ふつう", key="ai_level",
                             help="AIの読みはどれも同じ。AIは期待勝率が最善に近い札だけを候補にしてくじで選ぶ。"
                                  "強いほど候補の幅が狭い（" + "・".join(f"{k} {v * 100:.0f}ポイント以内" for k, v in LEVELS.items()) + "）")
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
    return {
        "r": s["r"], "n": N_ROUNDS, "over": over,
        "prize": None if over else s["prizes"][s["r"]],
        "score": s["score"], "hands": s["hands"],
        "log": [{"round": lg["round"], "prize": lg["prize"], "cards": lg["cards"], "winner": lg["winner"],
                 "score": lg["score"]} for lg in s["log"]],
        "last": None if not last else {
            "round": last["log"]["round"], "top": last["top"],
            "read": {str(c): round(p, 4) for c, p in last["read"].items()},
            # 期待勝率の上位3枚＋候補になった札＋実際に出した札：[札, 期待勝率, 選ばれる確率（候補外は null）]
            "ev": [[a, round(v, 4), round(last["cands"][a], 3) if a in last["cands"] else None]
                   for i, (a, v) in enumerate(sorted(last["ev"].items(), key=lambda x: -x[1]))
                   if i < 3 or a in last["cands"] or a == last["ai_card"]],
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
    below_board_css()
    with st.container(key="below_board"):
        with st.container(key="play_bar", horizontal=True, vertical_alignment="center"):
            st.markdown(f"🤖 **{brain.version}**　強さ **{ss.rec['ai_level']}**　｜　相手の読み：{brain.opp_name}")
            st.space("stretch")
            if st.button("対戦をやめる", type="tertiary", icon=":material/close:"):
                for k in ("state", "rec", "pending", "last", "game_id"):
                    ss.pop(k, None)
                st.rerun()


def _share(store, load_shared):
    ss = st.session_state
    saved = ss.setdefault("saved_ids", set())
    with st.container(key="share_box"):
        if ss.game_id in saved:
            st.success("この対戦を「みんなのデータ」（スプレッドシート）に送りました。AIの学習に使われます。")
            return
        st.markdown("#### 📤 みんなのデータに送る")
        st.caption("送った対戦は「📊 みんなのデータ」の分析と、次のAIの学習に使われます。")
        if "player_name" not in ss:
            ss.player_name = ss.get("last_player", "")
        player = st.text_input("プレイヤー名（必須・ニックネームにしてください）", max_chars=16, key="player_name",
                               placeholder="例：よみあい名人")
        consent = st.checkbox("データ提供に同意する（名前・出した札と考えた時間が保存され、"
                              "このアプリを使う全員が見られます。AIの学習にも使われます）", key="consent")
        # 名前の入力欄は、欄の外をクリックした時点で確定する。ボタンを名前で無効にすると
        # 「入力してすぐ送るを押す」とクリックが空振りするので、押したときに確かめる
        if st.button("送る", disabled=not consent, key="share"):
            if not player.strip():
                st.warning("プレイヤー名を入れてください。「みんなのデータ」で自分の記録を見つけるときに使います。", icon="✏️")
                return
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


def _comment(s: dict, rec: dict, hits: int) -> str:
    """リザルトの一言（この試合の記録から作る）。"""
    me, ai = s["score"]
    out = []
    if hits >= 5:
        out.append(f"AIにかなり読まれていました（{N_ROUNDS - 1}回中 <b>{hits}回</b> 的中）。出し方にクセが出ていたのかも。")
    elif hits <= 2:
        out.append(f"AIの読みをほとんど外させました（{N_ROUNDS - 1}回中 <b>{hits}回</b>）。読まれにくい出し方です。")
    else:
        out.append(f"AIの読みは {N_ROUNDS - 1}回中 <b>{hits}回</b> 当たりました（当てずっぽうなら約{GUESS_9:.1f}回）。")
    won = [lg for lg in s["log"] if lg["winner"] == 0]
    if won:
        lg = max(won, key=lambda x: (x["prize"], -(x["cards"][0] - x["cards"][1])))
        out.append(f"見せ場は R{lg['round']}：得点 <b>{lg['prize']}</b> を {lg['cards'][0]} 対 {lg['cards'][1]} で取りました。")
    if s["burned"]:
        out.append(f"相打ちで {s['burned']} 点が流れました。")
    if abs(me - ai) <= 3 and me != ai:
        out.append("接戦でした！")
    return " ".join(out)


def _result(brain, store, load_shared):
    ss = st.session_state
    s, rec = ss.state, ss.rec
    me, ai = s["score"]
    _board(brain)
    below_board_css(reveal_later=ss.pop("just_over", False))
    hits = sum(r["read_top"] == r["human_card"] for r in rec["rounds"][:-1])
    think = [r["think_ms"] for r in rec["rounds"]]
    ties = sum(lg["winner"] == -1 for lg in s["log"])
    df = pd.DataFrame([{"ラウンド": i + 1, "得点カード": lg["prize"],
                        "あなた": lg["cards"][0], "AI": lg["cards"][1],
                        "勝者": {0: "あなた", 1: "AI", -1: "相打ち（流れた）"}[lg["winner"]],
                        "あなたの合計": lg["score"][0], "AIの合計": lg["score"][1],
                        "AIの読み": r["ai_read"], "出した札にAIがつけた確率": r["read_prob"],
                        "考えた時間（秒）": round(r["think_ms"] / 1000, 1)}
                       for i, (lg, r) in enumerate(zip(s["log"], rec["rounds"]))])
    with st.container(key="below_board"):
        result_hero(me, ai, [
            ("AIの読みの的中", f"{hits}", f"/ {N_ROUNDS - 1}", f"当てずっぽうなら約{GUESS_9:.1f}回"),
            ("平均の考えた時間", f"{sum(think) / len(think) / 1000:.1f}", "秒", f"最長 {max(think) / 1000:.1f} 秒"),
            ("相打ち", f"{ties}", "回", f"流れた点 {s['burned']}"),
        ], _comment(s, rec, hits))
        st.space("small")
        left, right = st.columns([3, 2], gap="large")
        with right:
            _share(store, load_shared)
            if st.button("もう一度対戦する", type="primary", width="stretch", icon=":material/replay:"):
                for k in ("state", "rec", "pending", "last", "game_id"):
                    ss.pop(k, None)
                st.rerun()
            st.caption(f"対戦したAI：{rec.get('ai_model') or brain.version}（強さ {rec['ai_level']}）")
        with left, st.container(key="review_box"):
            t1, t2, t3, t4 = st.tabs(["📈 試合の流れ", "🃏 札の出し方", "🎯 AIの読み", "📋 全ラウンド"])
            with t1:
                flow = df.melt(id_vars=["ラウンド"], value_vars=["あなたの合計", "AIの合計"], var_name="誰", value_name="点")
                flow["誰"] = flow["誰"].str.replace("の合計", "")
                base = alt.Chart(flow).encode(
                    x=alt.X("ラウンド:O", axis=alt.Axis(labelAngle=0)), y=alt.Y("点:Q", title="合計点"),
                    color=alt.Color("誰:N", scale=alt.Scale(domain=["あなた", "AI"], range=[HUMAN, AI]),
                                    legend=alt.Legend(title=None)))
                show_chart(alt.layer(base.mark_line(strokeWidth=2.5), base.mark_circle(size=70, opacity=1).encode(
                    tooltip=["ラウンド", "誰", "点"])), 260)
                st.caption("ラウンドごとの合計点。線が開くほど差がついた場面です。")
            with t2:
                long = df.melt(id_vars=["ラウンド", "得点カード"], value_vars=["あなた", "AI"], var_name="プレイヤー",
                               value_name="出した札")
                diag = pd.DataFrame({"x": [0.5, 10.5], "y": [0.5, 10.5]})
                show_chart(alt.layer(
                    alt.Chart(diag).mark_line(color="#a3acbb", strokeDash=[5, 4]).encode(x="x:Q", y="y:Q"),
                    alt.Chart(long).mark_circle(size=120, opacity=0.9, stroke="white", strokeWidth=2).encode(
                        x=alt.X("得点カード:Q", scale=alt.Scale(domain=[0, 11]), axis=alt.Axis(values=list(range(1, 11)))),
                        y=alt.Y("出した札:Q", scale=alt.Scale(domain=[0, 11]), axis=alt.Axis(values=list(range(1, 11)))),
                        color=alt.Color("プレイヤー:N", scale=alt.Scale(domain=["あなた", "AI"], range=[HUMAN, AI]),
                                        legend=alt.Legend(title=None)),
                        tooltip=["ラウンド", "得点カード", "プレイヤー", "出した札"])), 300)
                st.caption("点線に近いほど「得点に見合った札」。上にずれると強気、下にずれると温存です。")
            with t3:
                rd = df[["ラウンド", "出した札にAIがつけた確率"]].copy()
                rd["当てずっぽう"] = [1 / (N_ROUNDS - i) for i in range(len(rd))]
                show_chart(alt.layer(
                    alt.Chart(rd).mark_bar(color=HUMAN, cornerRadiusEnd=4, width={"band": 0.55}).encode(
                        x=alt.X("ラウンド:O", axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("出した札にAIがつけた確率:Q", title="AIがつけていた確率", axis=alt.Axis(format="%")),
                        tooltip=["ラウンド", alt.Tooltip("出した札にAIがつけた確率:Q", format=".0%")]),
                    alt.Chart(rd).mark_tick(color="#56627a", thickness=2, size=26).encode(
                        x="ラウンド:O", y="当てずっぽう:Q", tooltip=[alt.Tooltip("当てずっぽう:Q", format=".0%")]),
                ), 260)
                st.caption("青い棒＝あなたが実際に出した札に、AIが前もってつけていた確率。高いほど読まれています。"
                           "横線は当てずっぽうの確率（手札が減るほど上がる）。")
            with t4:
                st.dataframe(df, hide_index=True, width="stretch", column_config={
                    "出した札にAIがつけた確率": st.column_config.ProgressColumn(
                        "出した札にAIがつけた確率", format="percent", min_value=0, max_value=1)})
                st.download_button("CSVで保存", df.to_csv(index=False).encode("utf-8-sig"), "yomiai_game.csv", "text/csv",
                                   icon=":material/download:")


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
