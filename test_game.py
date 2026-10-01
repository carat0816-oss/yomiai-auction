"""ルール・特徴量・AI・保存形式のテスト（Streamlit の画面は test_app.py）。"""
import random

from ai import Brain, ai_vs_bots, dummy_games, train_brain
from game import (CARDS, between, candidate_rows, clinched, new_game, outcome, rank_in, remaining, replay, resolve,
                  situation, win_line)
from ml import MODELS, OPP_DEFAULT, cross_validate, decision_metrics, heuristic_opp, normalize, opp_dataset, win_dataset
from store import assemble, clean_game

# --- ルール ---
s = new_game(prizes=[5, 3, 10, 1, 2, 4, 6, 7, 8, 9])
assert win_line(s) == 28
s = resolve(s, 7, 7)                       # 相打ち → 5点は流れる
assert s["score"] == [0, 0] and s["burned"] == 5 and s["log"][-1]["winner"] == -1
assert win_line(s) == 26                   # (55 − 5) の過半数
s = resolve(s, 2, 9)                       # 3点だけが AI に（上乗せはない）
assert s["score"] == [0, 3] and s["burned"] == 5
assert 7 not in s["hands"][0] and 9 not in s["hands"][1] and len(s["hands"][0]) == 8
assert remaining(s) == 55 - 5 - 3 and not clinched(s, 1)
try:
    resolve(s, 7, 1)
    raise AssertionError("使った札は出せない")
except ValueError:
    pass
end = new_game(prizes=CARDS[:])
for c in CARDS:
    end = resolve(end, c, c)                # 全部相打ち
assert end["score"] == [0, 0] and end["burned"] == 55 and outcome(end, 0) == 0.5
lead = new_game(prizes=[10, 9, 8, 1, 2, 3, 4, 5, 6, 7])
lead = resolve(resolve(resolve(lead, 10, 1), 9, 2), 8, 3)   # 27点
assert lead["score"] == [27, 0] and not clinched(lead, 0)    # 残り28点を全部取られると逆転される
lead = resolve(lead, 4, 5)                                   # 1点は AI に → 27 対 1、残り27
assert not clinched(lead, 0)
lead = resolve(lead, 5, 4)                                   # 2点 → 29 対 1、残り25
assert lead["score"][0] >= win_line(lead) and clinched(lead, 0)
print("PASS: ルール（得点・相打ち・勝ち確定ライン・使った札）")

# --- 特徴量 ---
assert rank_in(10, CARDS) == 1 and rank_in(1, CARDS) == 0 and rank_in(4, [4]) == 1
s0 = new_game(prizes=[10, 1, 2, 3, 4, 5, 6, 7, 8, 9])
sit = situation(s0, 0)
assert sit["prize"] == 10 and sit["prize_rank"] == 1 and sit["prize_share"] == round(10 / 55, 3)
assert sit["my_need"] == 28 and sit["burned"] == 0
rows = candidate_rows(sit, s0["hands"][0], s0["hands"][1])
assert len(rows) == 10 and rows[9]["is_max"] == 1 and rows[9]["sure_win"] == 0 and rows[0]["can_tie"] == 1
s1 = resolve(s0, 10, 1)
sit1 = situation(s1, 0)
assert sit1["last_card"] == 10 and sit1["last_result"] == 1 and sit1["score_diff"] == 10
assert sit1["aggr_mean"] == 0                        # 最大の得点に最強札 → 強気度 0
assert situation(s1, 1)["last_result"] == -1
b = between(s1, 0)
assert b["score_diff"] == 10 and b["max_gap"] == 9 - 10 and b["rounds_left"] == 9
states = replay([10, 1, 2, 3, 4, 5, 6, 7, 8, 9], [(10, 1)])
assert states[1]["score"] == [10, 0]
print("PASS: 特徴量（順位・局面・候補・合間）")

# --- データセットとモデル ---
games = dummy_games(12, 2, seed=3)
od, wd = opp_dataset(games), win_dataset(games)
assert od.groupby("decision")["chosen"].sum().eq(1).all()          # 1回の判断で出した札はちょうど1枚
assert len(od) == sum(range(1, 11)) * len(games)                    # 候補は 10+9+…+1 行
assert set(wd["won"]) <= {0, 1}
h = heuristic_opp(od)
assert abs(normalize(od, h).sum() - od["decision"].nunique()) < 1e-6
cv = cross_validate(od, "chosen", OPP_DEFAULT, MODELS, "group")
for name, p in cv["oof"].items():
    m = decision_metrics(od, normalize(od, p))
    assert 0.18 < m["的中率（1位）"] <= 1, (name, m)
print("PASS: 学習用の表・交差検証")

# --- AI ---
brain = Brain()                                          # モデルなし（ルールだけ）でも動く
rng = random.Random(0)
st0 = new_game(rng)
ch = brain.choose(st0, 1, rng)
assert ch["card"] in st0["hands"][1] and abs(sum(ch["read"].values()) - 1) < 1e-6
trained = train_brain(dummy_games(20, 3, seed=1), bootstrap_games=300)
assert trained.opp_model is not None
for _ in range(3):                                       # 反則しない
    st_ = new_game(rng)
    while st_["r"] < 10:
        c1 = trained.choose(st_, 1, rng)["card"]
        st_ = resolve(st_, rng.choice(st_["hands"][0]), c1)
rate = ai_vs_bots(trained, n=60)
assert 0.4 < rate < 0.95, rate
print(f"PASS: AI（反則なし、ボット相手の勝率 {rate:.0%}）")

# --- 保存形式 ---
rec = {"prizes": games[0]["prizes"], "ai_level": "ふつう", "profile": {"boardgame": "よくやる", "style": "x"},
       "rounds": [{**r, "read_top": r["human_card"], "read_prob": 0.4} for r in games[0]["rounds"]]}
g = clean_game("id1", "  たろう  ", rec)
assert g["player"] == "たろう" and g["style"] == "答えない" and g["read_top1"] == 1.0
assert g["rounds"][0]["human_total"] + g["rounds"][0]["ai_total"] >= 0
bad = {**rec, "rounds": rec["rounds"][:9]}
assert clean_game("id2", "x", bad) is None
cheat = {**rec, "rounds": [{**r, "human_card": 10} for r in rec["rounds"]]}
assert clean_game("id3", "x", cheat) is None
from store import GAME_COLS, ROUND_COLS, _rows  # noqa: E402
grow, rrows = _rows(g)
back = assemble([dict(zip(GAME_COLS, grow))], [dict(zip(ROUND_COLS, r)) for r in rrows])
assert len(back) == 1 and back[0]["prizes"] == g["prizes"] and len(back[0]["rounds"]) == 10
assert assemble([dict(zip(GAME_COLS, grow))], [dict(zip(ROUND_COLS, r)) for r in rrows[:5]]) == []
print("PASS: 保存形式（検査・行への変換・読み戻し・欠けた試合の除外）")
