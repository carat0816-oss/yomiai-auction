"""対戦記録 → 学習用の表。モデルの作成・交差検証・指標・重要度・部分依存もここに置く。"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from game import between, candidate_rows, replay, situation

# ---------------------------------------------------------------------------
# 説明変数の候補：列名 → (日本語の名前, 説明)
# ---------------------------------------------------------------------------
OPP_FEATURES = {
    "card": ("候補の札", "この札を出すかどうかを予測する"),
    "card_rank": ("候補の札の手札内順位（0〜1）", "残りの手札の中で、下から何番目の強さか"),
    "rank_gap": ("札の順位 − 得点カードの順位", "＋なら、得点の割に強い札"),
    "abs_rank_gap": ("|札の順位 − 得点カードの順位|", "得点に見合った札ほど 0 に近い（作った特徴量）"),
    "card_minus_prize": ("札 − 得点カード", "数字そのものの差"),
    "is_max": ("手札で一番強い札か", "1/0"),
    "is_min": ("手札で一番弱い札か", "1/0"),
    "sure_win": ("出せば必ず勝つ札か", "相手の最強札より大きい"),
    "can_tie": ("相手も持っている数か", "同じ数を出し合うと相打ちで、得点カードは流れる"),
    "prize": ("得点カード", "今回の得点カードの数字"),
    "prize_rank": ("得点カードの順位（0〜1）", "残りの得点カードの中で、どれくらい大きいか"),
    "prize_share": ("今回の点が残り全体に占める割合", "大きいほど大一番"),
    "round_no": ("ラウンド", "1〜10"),
    "score_diff": ("点差（自分−相手）", "＋ならリードしている"),
    "burned": ("流れた点", "これまでに相打ちで流れた得点カードの合計"),
    "my_need": ("勝ち確定まであと何点（自分）", "流れた点を引いた残りの過半数まで"),
    "opp_need": ("勝ち確定まであと何点（相手）", ""),
    "my_max": ("自分の最強札", ""),
    "my_mean": ("自分の手札の平均", ""),
    "my_high": ("自分の強い札（8以上）の枚数", ""),
    "opp_max": ("相手の最強札", ""),
    "opp_high": ("相手の強い札（8以上）の枚数", ""),
    "max_gap": ("最強札の差（自分−相手）", ""),
    "sum_gap": ("手札の合計の差（自分−相手）", ""),
    "last_card": ("前のラウンドに出した札", "1ラウンド目は 0"),
    "last_opp_card": ("前のラウンドに相手が出した札", ""),
    "last_result": ("前のラウンドの結果", "勝ち 1／相打ち 0／負け −1"),
    "aggr_mean": ("その人のここまでの強気さ", "これまで出した札の順位 − 得点カードの順位 の平均"),
    "last_think_ms": ("前のラウンドで考えた時間（ms）", ""),
}
OPP_DEFAULT = ["card_rank", "rank_gap", "abs_rank_gap", "card", "is_max", "is_min", "sure_win", "can_tie",
               "prize", "prize_share", "round_no", "score_diff", "my_need", "opp_need", "max_gap", "last_result",
               "aggr_mean"]
WIN_FEATURES = {
    "rounds_left": ("残りラウンド数", ""),
    "score_diff": ("点差（自分−相手）", ""),
    "points_left": ("残りの点の合計", "まだ誰も取っていない点"),
    "lead_ratio": ("点差 ÷ 残りの点", "逆転の難しさ（作った特徴量）"),
    "max_gap": ("最強札の差", ""),
    "sum_gap": ("手札の合計の差", ""),
    "high_gap": ("強い札の枚数の差", ""),
    "min_gap": ("最弱札の差", ""),
}
WIN_DEFAULT = list(WIN_FEATURES)
CATEGORICAL = {"boardgame", "style"}

# 答えを見てから決まる列。入れると「カンニング」になる
LEAKS = {
    "think_ms": "このラウンドで考えた時間。AIは人間が札を出す前に自分の札を決めるので、予測の時点ではわからない",
    "winner": "このラウンドの勝ち負けそのもの",
    "opp_card": "相手（AI）がこのラウンドに出した札。同時に出すので、出す前には見えない",
}

MODELS = ["ロジスティック回帰", "決定木", "ランダムフォレスト", "LightGBM"]


# ---------------------------------------------------------------------------
# 対戦記録 → 表
# 記録の形：{"game_id", "player", "prizes": [10個], "rounds": [{"human_card", "ai_card", "think_ms"}, ...], ...}
# ---------------------------------------------------------------------------
def _cards(g: dict) -> list[tuple[int, int]]:
    return [(int(r["human_card"]), int(r["ai_card"])) for r in g["rounds"]]


def opp_dataset(games: list[dict]) -> pd.DataFrame:
    """人間側（プレイヤー0）が札を選んだ1回ごとに、手札の候補を1行ずつ並べた表。chosen＝実際に出したか。"""
    rows = []
    for g in games:
        cards = _cards(g)
        states = replay(g["prizes"], cards)
        thinks = [r.get("think_ms") for r in g["rounds"]]
        for i, (c0, _) in enumerate(cards):
            st = states[i]
            sit = situation(st, 0, thinks[:i])
            for row in candidate_rows(sit, st["hands"][0], st["hands"][1]):
                row.update(abs_rank_gap=abs(row["rank_gap"]), chosen=int(row["card"] == c0),
                           decision=f'{g["game_id"]}#{i + 1}', game_id=g["game_id"], player=g["player"],
                           boardgame=g.get("boardgame") or "答えない", style=g.get("style") or "答えない",
                           think_ms=thinks[i])
                rows.append(row)
    return pd.DataFrame(rows)


def win_dataset(games: list[dict]) -> pd.DataFrame:
    """ラウンドの合間の局面（両者の目線）→ 最終的に勝ったか。引き分けの試合は除く。"""
    rows = []
    for g in games:
        states = replay(g["prizes"], _cards(g))
        final = states[-1]["score"]
        if final[0] == final[1] or len(states) < 11:
            continue
        for me in (0, 1):
            won = int(final[me] > final[1 - me])
            for i, st in enumerate(states[:-1]):
                rows.append({**between(st, me), "won": won, "me": me, "round_no": i + 1,
                             "game_id": g["game_id"], "player": g["player"] if me == 0 else "AI側"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# モデル
# ---------------------------------------------------------------------------
def make_model(name: str, features: list[str], params: dict | None = None) -> Pipeline:
    p = params or {}
    num = [f for f in features if f not in CATEGORICAL]
    cat = [f for f in features if f in CATEGORICAL]
    pre = ColumnTransformer([
        ("num", Pipeline([("fill", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), num),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
    ], sparse_threshold=0)
    if name == "ロジスティック回帰":
        est = LogisticRegression(C=p.get("C", 1.0), max_iter=2000)
    elif name == "決定木":
        est = DecisionTreeClassifier(max_depth=p.get("max_depth", 5), min_samples_leaf=p.get("min_leaf", 20),
                                     random_state=0)
    elif name == "ランダムフォレスト":
        est = RandomForestClassifier(n_estimators=p.get("n_trees", 200), max_depth=p.get("max_depth", 8),
                                     min_samples_leaf=p.get("min_leaf", 10), n_jobs=-1, random_state=0)
    elif name == "LightGBM":
        from lightgbm import LGBMClassifier
        est = LGBMClassifier(n_estimators=p.get("n_trees", 200), learning_rate=p.get("lr", 0.05),
                             num_leaves=p.get("leaves", 15), min_child_samples=p.get("min_leaf", 20),
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0)
    else:
        raise ValueError(name)
    return Pipeline([("pre", pre), ("model", est)])


def normalize(df: pd.DataFrame, score: np.ndarray) -> np.ndarray:
    """候補ごとのスコアを、同じ判断（decision）の中で合計1になるように割る。"""
    s = pd.Series(np.clip(score, 1e-6, None), index=df.index)
    return (s / s.groupby(df["decision"]).transform("sum")).to_numpy()


def heuristic_opp(df: pd.DataFrame) -> np.ndarray:
    """ベースライン：「得点カードと同じくらいの順位の札を出す」と決め打ちした予測。"""
    return normalize(df, np.exp(-(df["rank_gap"].to_numpy() ** 2) / (2 * 0.25 ** 2)))


def decision_metrics(df: pd.DataFrame, prob: np.ndarray) -> dict:
    """1回の判断ごとの指標：一番確率が高い札が当たった割合・実際の札につけた確率・対数損失。"""
    d = df[["decision", "chosen"]].assign(p=prob)
    top = d.loc[d.groupby("decision")["p"].idxmax()]
    actual = d[d["chosen"] == 1]["p"].clip(1e-6, 1)
    return {"的中率（1位）": float(top["chosen"].mean()), "実際の札につけた確率": float(actual.mean()),
            "対数損失（判断ごと）": float(-np.log(actual).mean())}


def make_folds(df: pd.DataFrame, how: str, unit: str = "player", k: int = 5) -> list:
    """交差検証の分け方。
    - group：人ごとに分ける（テストの人は学習に一度も出てこない＝初めて対戦する人を当てられるか）
    - random：試合ごとにランダムに分ける（同じ人の別の試合が学習側にいるので、成績は甘めに出やすい）
    どちらも、同じ試合の行は同じ側に入れる（候補の行が分かれると、判断ごとの指標が出せない）。"""
    if how == "group" and df[unit].nunique() >= 3:
        n = min(k, df[unit].nunique())
        return list(GroupKFold(n_splits=n).split(np.zeros(len(df)), groups=df[unit]))
    rng = np.random.default_rng(0)
    gid = {g: int(rng.integers(0, k)) for g in df["game_id"].unique()}
    fold = df["game_id"].map(gid).to_numpy()
    return [(np.where(fold != i)[0], np.where(fold == i)[0]) for i in range(k) if (fold == i).any()]


def cross_validate(df: pd.DataFrame, target: str, features: list[str], names: list[str], how: str,
                   params: dict | None = None, unit: str = "player") -> dict:
    """交差検証で、全行の「学習に使っていないときの予測」（out-of-fold）を作る。"""
    folds = make_folds(df, how, unit)
    y = df[target].to_numpy()
    out = {}
    for name in names:
        oof = np.full(len(df), np.nan)
        for tr, te in folds:
            if len(np.unique(y[tr])) < 2:
                continue
            m = make_model(name, features, params).fit(df.iloc[tr][features], y[tr])
            oof[te] = m.predict_proba(df.iloc[te][features])[:, 1]
        out[name] = oof
    return {"oof": out, "folds": len(folds)}


def binary_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    ok = ~np.isnan(p)
    y, p = y[ok], np.clip(p[ok], 1e-6, 1 - 1e-6)
    return {"AUC": roc_auc_score(y, p) if len(np.unique(y)) > 1 else np.nan,
            "正解率": accuracy_score(y, p >= 0.5), "対数損失": log_loss(y, p, labels=[0, 1])}


def permutation_importance(df: pd.DataFrame, target: str, features: list[str], name: str,
                           params: dict | None = None, unit: str = "player", repeats: int = 3) -> pd.Series:
    """人（または試合）単位で 75%/25% に分け、テスト側で列を1つずつシャッフルして AUC がどれだけ下がるか。"""
    groups = df[unit] if df[unit].nunique() >= 4 else df["game_id"]
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0).split(df, groups=groups))
    train, test = df.iloc[tr], df.iloc[te]
    m = make_model(name, features, params).fit(train[features], train[target])
    y = test[target].to_numpy()
    base = roc_auc_score(y, m.predict_proba(test[features])[:, 1])
    rng = np.random.default_rng(0)
    drops = {}
    for f in features:
        vals = []
        for _ in range(repeats):
            shuffled = test[features].copy()
            shuffled[f] = rng.permutation(shuffled[f].to_numpy())
            vals.append(base - roc_auc_score(y, m.predict_proba(shuffled)[:, 1]))
        drops[f] = float(np.mean(vals))
    return pd.Series(drops).sort_values(ascending=False)


def partial_dependence(model: Pipeline, X: pd.DataFrame, feature: str, grid: list) -> pd.DataFrame:
    """ある列だけを grid の値に置きかえたとき、予測確率の平均がどう変わるか。"""
    sample = X.sample(min(len(X), 600), random_state=0)
    rows = []
    for v in grid:
        Z = sample.copy()
        Z[feature] = v
        rows.append({"値": v, "予測確率の平均": float(model.predict_proba(Z)[:, 1].mean())})
    return pd.DataFrame(rows)


def logistic_coefs(model: Pipeline, features: list[str]) -> pd.Series:
    """ロジスティック回帰の係数（標準化後なので、列どうしで大きさを比べられる）。"""
    names = model.named_steps["pre"].get_feature_names_out()
    coefs = model.named_steps["model"].coef_[0]
    clean = [n.split("__", 1)[1] for n in names]
    return pd.Series(coefs, index=clean).sort_values(key=abs, ascending=False)
