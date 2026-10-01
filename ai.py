"""AI：相手の手を読み、勝率モデルで札を選ぶ。データが少ないうちに使うルールボットと自己対戦もここ。"""
from __future__ import annotations

import math
import random

import numpy as np
import pandas as pd

from game import between, candidate_rows, is_over, new_game, outcome, rank_in, resolve, situation
from ml import OPP_DEFAULT, WIN_DEFAULT, WIN_RICH, heuristic_opp, make_model, normalize, opp_dataset, win_dataset

MIN_HUMAN_DECISIONS = 150   # 人間の手がこれだけ集まるまでは、相手の読みにルール（ベースライン）を使う
MARGIN = 0.05               # 札選びの迷う幅：期待勝率が最善からこれだけ以内の札だけを候補にする（0.05＝5ポイント）


# ---------------------------------------------------------------------------
# ルールボット：人間っぽいクセを持った架空のプレイヤー（ダミーデータと、勝率モデルの初期学習に使う）
# ---------------------------------------------------------------------------
PERSONAS = {
    "比例型": dict(shift=0.0, noise=0.15, dump=0.0, snipe=0.3, clash=0.1),
    "強気型": dict(shift=0.2, noise=0.18, dump=0.0, snipe=0.2, clash=0.3),
    "慎重型": dict(shift=-0.15, noise=0.15, dump=0.2, snipe=0.4, clash=0.05),
    "温存型": dict(shift=0.05, noise=0.12, dump=0.7, snipe=0.6, clash=0.2),
    "気まぐれ型": dict(shift=0.0, noise=0.45, dump=0.1, snipe=0.1, clash=0.1),
}


def bot_card(state: dict, me: int, persona: dict, rng: random.Random) -> int:
    hand, opp_hand = state["hands"][me], state["hands"][1 - me]
    r = state["r"]
    prize = state["prizes"][r]
    pr = rank_in(prize, state["prizes"][r:])
    # 相手の最強札を確実に上回れるなら、ここぞで取りにいく
    winners = [c for c in hand if c > max(opp_hand)]
    if winners and pr >= 0.6 and rng.random() < persona["snipe"]:
        return min(winners)
    # 大きい得点カードで、相手の最強札と同じ数をぶつけて相打ちにする（相手に取らせない）
    if max(opp_hand) in hand and pr >= 0.7 and rng.random() < persona["clash"]:
        return max(opp_hand)
    # 小さい得点カードは最弱札で捨てる
    if pr <= 0.35 and rng.random() < persona["dump"]:
        return min(hand)
    target = min(1.0, max(0.0, pr + persona["shift"] + rng.gauss(0, persona["noise"])))
    return min(hand, key=lambda c: (abs(rank_in(c, hand) - target), rng.random()))


def make_bot_player(rng: random.Random, name: str | None = None) -> dict:
    kind = rng.choice(list(PERSONAS))
    p = dict(PERSONAS[kind])
    p["shift"] += rng.gauss(0, 0.08)                    # 同じ型でも人によって少しずつ違う
    p["noise"] = max(0.05, p["noise"] + rng.gauss(0, 0.04))
    return {"name": name or kind, "kind": kind, "persona": p}


def bot_game(p0: dict, p1: dict, rng: random.Random, game_id: str) -> dict:
    state = new_game(rng)
    rounds = []
    while not is_over(state):
        c0, c1 = bot_card(state, 0, p0["persona"], rng), bot_card(state, 1, p1["persona"], rng)
        rounds.append({"round": state["r"] + 1, "prize": state["prizes"][state["r"]], "human_card": c0, "ai_card": c1, "think_ms": None})
        state = resolve(state, c0, c1)
    return {"game_id": game_id, "player": p0["name"], "prizes": state["prizes"], "rounds": rounds,
            "boardgame": "答えない", "style": "答えない", "my_score": state["score"][0], "ai_score": state["score"][1]}


def dummy_games(n_players: int = 30, games_each: int = 3, seed: int = 0) -> list[dict]:
    """ダミーデータ：クセの違うボット n_players 人が、それぞれ games_each 試合ずつ遊んだ記録。"""
    rng = random.Random(seed)
    players = [make_bot_player(rng, f"ボット{i + 1:02d}") for i in range(n_players)]
    for p in players:
        p["name"] = f'{p["name"]}（{p["kind"]}）'
    out = []
    for p in players:
        for k in range(games_each):
            out.append(bot_game(p, make_bot_player(rng), rng, f"dummy-{seed}-{p['name']}-{k}"))
    return out


# ---------------------------------------------------------------------------
# AIの頭脳：相手の手の予測モデル＋勝率モデル
# ---------------------------------------------------------------------------
class Brain:
    def __init__(self, opp_model=None, win_model=None, opp_name="ルール（ベースライン）", win_name="ルール",
                 opp_features=OPP_DEFAULT, win_features=WIN_DEFAULT, n_human=0):
        self.opp_model, self.win_model = opp_model, win_model
        self.opp_name, self.win_name = opp_name, win_name
        self.opp_features, self.win_features = list(opp_features), list(win_features)
        self.n_human = n_human
        self.version = "ルールのみ"   # 版の名前（registry.save_version で付く）

    def read(self, state: dict, opp: int, think_ms: list | None = None, profile: dict | None = None) -> dict:
        """相手（opp）が次に出す札の確率 {札: 確率}。"""
        sit = situation(state, opp, think_ms)
        df = pd.DataFrame(candidate_rows(sit, state["hands"][opp], state["hands"][1 - opp]))
        df["abs_rank_gap"] = df["rank_gap"].abs()
        df["decision"] = "now"
        for k in ("boardgame", "style"):
            df[k] = (profile or {}).get(k, "答えない")
        if self.opp_model is None:
            p = heuristic_opp(df)
        else:
            p = normalize(df, self.opp_model.predict_proba(df[self.opp_features])[:, 1])
        return dict(zip(df["card"].astype(int), p))

    def value(self, states: list[dict], me: int) -> np.ndarray:
        """ラウンドの合間の局面で、me が最終的に勝つ確率。"""
        out = np.empty(len(states))
        live = [i for i, s in enumerate(states) if not is_over(s)]
        for i, s in enumerate(states):
            if is_over(s):
                out[i] = outcome(s, me)
        if live:
            X = pd.DataFrame([between(states[i], me) for i in live])
            if self.win_model is None:
                p = 1 / (1 + np.exp(-(4 * X["lead_ratio"] + 0.06 * X["sum_gap"] + 0.1 * X["max_gap"])))
            else:
                p = self.win_model.predict_proba(X[self.win_features])[:, 1]
            out[live] = p
        return out

    def choose(self, state: dict, me: int, rng: random.Random, think_ms=None, profile=None,
               margin: float = MARGIN) -> dict:
        """札を選ぶ。返り値：選んだ札・相手の読み・札ごとの期待勝率・候補の札。

        人間らしく迷わせるが、明らかに悪い札は選ばない：期待勝率が最善から margin 以内の札だけを候補にして、
        その中で良い札ほど選ばれやすくくじを引く（最善の札が一番選ばれやすい）。"""
        opp = 1 - me
        probs = self.read(state, opp, think_ms, profile)
        mine = state["hands"][me]
        nexts, keys = [], []
        for a in mine:
            for b in probs:
                nexts.append(resolve(state, b, a) if me == 1 else resolve(state, a, b))
                keys.append((a, b))
        vals = self.value(nexts, me)
        ev = {a: 0.0 for a in mine}
        for (a, b), v in zip(keys, vals):
            ev[a] += probs[b] * v
        best = max(ev.values())
        margin = max(margin, 1e-6)
        cands = [a for a in mine if ev[a] >= best - margin]
        weights = [math.exp((ev[a] - best) / (margin / 3)) for a in cands]
        card = rng.choices(cands, weights=weights)[0]
        z = sum(weights)
        return {"card": card, "read": probs, "ev": ev, "win": ev[card],
                "cands": {a: w / z for a, w in zip(cands, weights)}}


def ai_game(b0, b1, rng: random.Random, game_id: str, margin: float = MARGIN) -> dict:
    """AIが入った対戦（b が Brain ならAI、dict ならルールボット）。勝率モデルの学び直しに使う。"""
    state = new_game(rng)
    rounds = []
    while not is_over(state):
        cs = [b.choose(state, me, rng, margin=margin)["card"] if isinstance(b, Brain) else bot_card(state, me, b["persona"], rng)
              for me, b in enumerate((b0, b1))]
        rounds.append({"round": state["r"] + 1, "prize": state["prizes"][state["r"]], "human_card": cs[0], "ai_card": cs[1],
                       "think_ms": None})
        state = resolve(state, *cs)
    return {"game_id": game_id, "player": "AI自己対戦", "prizes": state["prizes"], "rounds": rounds}


WIN_PARAMS = {"n_trees": 400, "leaves": 31, "min_leaf": 40, "lr": 0.05}


def train_brain(human_games: list[dict], seed: int = 0, opp_name: str = "LightGBM",
                opp_features: list[str] | None = None, bootstrap_games: int = 20000, self_play_games: int = 4000,
                opp_params: dict | None = None, log=lambda msg: None) -> Brain:
    """人間の対戦記録（＋ボットとAIの自己対戦）から AI の頭脳を作る。

    勝率モデルは2段階で作る：
      1. ルールボット同士の対戦（bootstrap_games 試合）で下地を作る
      2. そのモデルで動くAIを、AI同士・ボット相手に戦わせ（self_play_games 試合）、その対戦も足して学び直す
    人間の対戦も足す。相手の読みは、人間の手が MIN_HUMAN_DECISIONS に届くまではルールを使う。"""
    rng = random.Random(seed)
    n_human = sum(len(g["rounds"]) for g in human_games)
    feats = list(opp_features or OPP_DEFAULT)
    opp_model = None
    if n_human >= MIN_HUMAN_DECISIONS:
        odf = opp_dataset(human_games)
        opp_model = make_model(opp_name, feats, opp_params).fit(odf[feats], odf["chosen"])
    opp_label = f"{opp_name}（人間 {n_human} 手で学習）" if opp_model is not None else "ルール（ベースライン）"

    log(f"ボット同士の対戦 {bootstrap_games} 試合で勝率モデルの下地を作っています…")
    boot = [bot_game(make_bot_player(rng), make_bot_player(rng), rng, f"boot-{i}") for i in range(bootstrap_games)]
    wdf = win_dataset(boot + human_games)
    win_model = make_model("LightGBM", WIN_RICH, WIN_PARAMS).fit(wdf[WIN_RICH], wdf["won"])
    brain = Brain(opp_model=opp_model, win_model=win_model, opp_name=opp_label, win_features=WIN_RICH, n_human=n_human,
                  opp_features=feats if opp_model is not None else OPP_DEFAULT)
    if self_play_games:
        log(f"AIを {self_play_games} 試合戦わせて、勝率モデルを学び直しています…")
        games = []
        for i in range(self_play_games):
            kind = i % 3   # AI同士・AIが先手・AIが後手 を順番に
            b0 = brain if kind != 2 else make_bot_player(rng)
            b1 = brain if kind != 1 else make_bot_player(rng)
            games.append(ai_game(b0, b1, rng, f"self-{i}"))
        wdf = pd.concat([wdf, win_dataset(games)], ignore_index=True)
        brain.win_model = make_model("LightGBM", WIN_RICH, WIN_PARAMS).fit(wdf[WIN_RICH], wdf["won"])
    brain.win_name = (f"LightGBM・38特徴（ボット対戦 {bootstrap_games}＋AI自己対戦 {self_play_games}"
                      + (f"＋人間 {len(human_games)} 試合" if human_games else "") + "）")
    return brain


def ai_vs_bots(brain: Brain, n: int = 200, seed: int = 1) -> float:
    """強さの確認：AI（プレイヤー1）がルールボットに勝つ割合（引き分けは0.5）。"""
    rng = random.Random(seed)
    total = 0.0
    for _ in range(n):
        p0 = make_bot_player(rng)
        state = new_game(rng)
        while not is_over(state):
            c0 = bot_card(state, 0, p0["persona"], rng)
            c1 = brain.choose(state, 1, rng)["card"]
            state = resolve(state, c0, c1)
        total += outcome(state, 1)
    return total / n

