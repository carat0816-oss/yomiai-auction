"""ゲームのルールと、局面から特徴量を作る計算。Streamlit に依存しない純粋な関数だけを置く。

プレイヤーは 0 と 1 の2人（対戦画面では 0＝人間、1＝AI）。
- 両者とも 1〜10 の手札を持ち、得点カード 1〜10 をシャッフルした順に10ラウンド戦う
- 得点カードが公開されたら、両者が伏せて1枚ずつ出す。大きい方がその得点カードの点を取る
- 同じ数なら「相打ち」。その得点カードは誰のものにもならず流れる（両者の札も消える）
- 使った札は戻らない。出した札は公開されるので、相手の残りの手札はわかる
- 流れた点があるので、勝ち確定のラインは「(55 − 流れた点) の過半数」になる
"""
from __future__ import annotations

import random
from statistics import mean

CARDS = list(range(1, 11))
N_ROUNDS = len(CARDS)
HIGH = 8  # 「強い札」とみなす下限


def new_game(rng: random.Random | None = None, prizes: list[int] | None = None) -> dict:
    rng = rng or random.Random()
    if prizes is None:
        prizes = CARDS[:]
        rng.shuffle(prizes)
    return {"prizes": list(prizes), "r": 0, "hands": [CARDS[:], CARDS[:]], "score": [0, 0], "burned": 0, "log": []}


def is_over(state: dict) -> bool:
    return state["r"] >= N_ROUNDS


def resolve(state: dict, c0: int, c1: int) -> dict:
    """両者の札でラウンドを1つ進めた、新しい局面を返す（元の局面は変えない）。"""
    if c0 not in state["hands"][0] or c1 not in state["hands"][1]:
        raise ValueError("手札にない札は出せません")
    r = state["r"]
    prize = state["prizes"][r]
    score, burned = state["score"][:], state["burned"]
    if c0 == c1:
        winner = -1                     # 相打ち：得点カードは流れる
        burned += prize
    else:
        winner = 0 if c0 > c1 else 1
        score[winner] += prize
    hands = [[c for c in state["hands"][0] if c != c0], [c for c in state["hands"][1] if c != c1]]
    log = state["log"] + [{"round": r + 1, "prize": prize, "cards": [c0, c1], "winner": winner, "score": score[:]}]
    return {"prizes": state["prizes"], "r": r + 1, "hands": hands, "score": score, "burned": burned, "log": log}


def remaining(state: dict) -> int:
    """まだ誰のものでもない点（これから出てくる得点カードの合計）。"""
    return sum(state["prizes"][state["r"]:])


def win_line(state: dict) -> int:
    """これだけ取れば勝ち確定になる点数（流れていない点の過半数）。"""
    return (sum(CARDS) - state["burned"]) // 2 + 1


def clinched(state: dict, me: int) -> bool:
    """もう逆転されない（残りを全部相手が取っても勝つ）か。"""
    return state["score"][me] > state["score"][1 - me] + remaining(state)


def outcome(state: dict, me: int) -> float:
    """終局の勝ち負け（me から見て 勝ち=1・引き分け=0.5・負け=0）。"""
    a, b = state["score"][me], state["score"][1 - me]
    return 1.0 if a > b else 0.0 if a < b else 0.5


def rank_in(value: int, values: list[int]) -> float:
    """values の中で value が下から何番目か（0〜1）。1枚しかなければ 1。"""
    if len(values) <= 1:
        return 1.0
    return sum(v < value for v in values) / (len(values) - 1)


# ---------------------------------------------------------------------------
# 特徴量① 札を選ぶ瞬間の局面（me が選ぶ側）
# ---------------------------------------------------------------------------
def _hand_stats(hand: list[int], prefix: str) -> dict:
    return {f"{prefix}_max": max(hand), f"{prefix}_min": min(hand), f"{prefix}_mean": round(mean(hand), 3),
            f"{prefix}_high": sum(c >= HIGH for c in hand)}


def situation(state: dict, me: int, think_ms: list[float | None] | None = None) -> dict:
    """得点カードが公開された直後の局面を、me の目線で数値にする。"""
    opp = 1 - me
    r = state["r"]
    prize = state["prizes"][r]
    unrevealed = state["prizes"][r:]          # 今回の得点カードを含む、まだ誰のものでもない得点カード
    left_after = sum(state["prizes"][r + 1:])
    line = win_line(state)
    mine, theirs = state["hands"][me], state["hands"][opp]
    past = state["log"]
    # 自分のこれまでの「強気さ」：出した札の手札内順位 − 得点カードの順位（＋なら得点の割に強い札を出す）
    aggr, hands_before, prizes_before = [], [CARDS[:]], state["prizes"][:]
    for i, lg in enumerate(past):
        hand = hands_before[-1]
        aggr.append(rank_in(lg["cards"][me], hand) - rank_in(lg["prize"], prizes_before[i:]))
        hands_before.append([c for c in hand if c != lg["cards"][me]])
    last = past[-1] if past else None
    thinks = [t for t in (think_ms or []) if t is not None]
    return {
        "round_no": r + 1,
        "rounds_left": N_ROUNDS - r,
        "prize": prize,
        "prize_rank": round(rank_in(prize, unrevealed), 3),
        "prize_share": round(prize / (prize + left_after), 3),
        "score_diff": state["score"][me] - state["score"][opp],
        "points_left": left_after + prize,
        "burned": state["burned"],
        "my_need": max(0, line - state["score"][me]),
        "opp_need": max(0, line - state["score"][opp]),
        **_hand_stats(mine, "my"),
        **_hand_stats(theirs, "opp"),
        "max_gap": max(mine) - max(theirs),
        "sum_gap": sum(mine) - sum(theirs),
        "last_card": last["cards"][me] if last else 0,
        "last_opp_card": last["cards"][opp] if last else 0,
        "last_result": 0 if not last else (1 if last["winner"] == me else -1 if last["winner"] == opp else 0),
        "aggr_mean": round(mean(aggr), 3) if aggr else 0.0,
        "last_think_ms": thinks[-1] if thinks else None,
    }


def candidate_rows(sit: dict, hand: list[int], opp_hand: list[int]) -> list[dict]:
    """手札の候補1枚ごとの特徴量（situation と合わせて1行）。"""
    rows = []
    for c in hand:
        cr = rank_in(c, hand)
        rows.append({**sit, "card": c, "card_rank": round(cr, 3), "rank_gap": round(cr - sit["prize_rank"], 3),
                     "card_minus_prize": c - sit["prize"], "is_max": int(c == max(hand)), "is_min": int(c == min(hand)),
                     "sure_win": int(c > max(opp_hand)), "can_tie": int(c in opp_hand)})
    return rows


# ---------------------------------------------------------------------------
# 特徴量② ラウンドの合間（次の得点カードが公開される前）の局面 → 勝率モデル用
# ---------------------------------------------------------------------------
def between(state: dict, me: int) -> dict:
    opp = 1 - me
    left = remaining(state)
    mine, theirs = state["hands"][me], state["hands"][opp]
    diff = state["score"][me] - state["score"][opp]
    return {
        "rounds_left": N_ROUNDS - state["r"],
        "score_diff": diff,
        "points_left": left,
        "lead_ratio": round(diff / (left + 1), 3),
        "max_gap": max(mine) - max(theirs),
        "sum_gap": sum(mine) - sum(theirs),
        "high_gap": sum(c >= HIGH for c in mine) - sum(c >= HIGH for c in theirs),
        "min_gap": min(mine) - min(theirs),
    }


def replay(prizes: list[int], cards: list[tuple[int, int]]) -> list[dict]:
    """記録（得点カードの順番と、両者の出した札）から、各ラウンド直前の局面を並べ直す。"""
    state = new_game(prizes=prizes + [c for c in CARDS if c not in prizes])
    states = []
    for c0, c1 in cards:
        states.append(state)
        state = resolve(state, c0, c1)
    states.append(state)
    return states
