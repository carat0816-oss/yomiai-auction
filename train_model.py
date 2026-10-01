"""新しいAIの版を作る（管理者が手元で実行する）。

    .venv\\Scripts\\python train_model.py --name "Yomi 1.1" --notes "50試合に増えたので学習し直し"

スプレッドシート（.streamlit/secrets.toml がなければ data/）の最新の対戦で学習し、成績を測って
models/ に保存し、models/registry.json に書き足す。できたら git で push すると、公開アプリに反映される。
"""
from __future__ import annotations

import argparse
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from ai import MIN_HUMAN_DECISIONS, Brain, ai_vs_bots, train_brain
from ml import (MODELS, OPP_DEFAULT, OPP_FEATURES, binary_metrics, cross_validate, decision_metrics, heuristic_opp,
                normalize, opp_dataset, win_dataset)
from registry import load_registry, save_version, slugify
from store import LocalStore, SheetStore

ROOT = Path(__file__).resolve().parent


def load_games(local: bool) -> tuple[list[dict], str]:
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if not local and secrets.exists():
        s = tomllib.loads(secrets.read_text(encoding="utf-8"))
        return SheetStore(dict(s["gcp_service_account"]), s["sheet_url"]).load(100000), "スプレッドシート"
    return LocalStore(ROOT / "data").load(100000), "data/"


def evaluate(games: list[dict], model: str, features: list[str], params: dict | None) -> dict:
    """交差検証（人ごとに分ける）で、相手の手の予測と勝率モデルの成績を測る。"""
    out = {}
    odf = opp_dataset(games)
    n_moves = odf["decision"].nunique() if not odf.empty else 0
    if n_moves >= MIN_HUMAN_DECISIONS and odf["player"].nunique() >= 3:
        p = cross_validate(odf, "chosen", features, [model], "group", params)["oof"][model]
        m = decision_metrics(odf, normalize(odf, np.nan_to_num(p, nan=1e-6)))
        out["読みの的中率"] = round(m["的中率（1位）"], 3)
        out["ルールの的中率"] = round(decision_metrics(odf, heuristic_opp(odf))["的中率（1位）"], 3)
    wdf = win_dataset(games)
    if len(wdf) >= 40 and wdf["won"].nunique() == 2 and wdf["game_id"].nunique() >= 5:
        p = cross_validate(wdf, "won", ["lead_ratio", "max_gap", "sum_gap", "high_gap", "min_gap", "rounds_left",
                                        "score_diff", "points_left"], ["LightGBM"], "group", None, "game_id")
        out["勝率モデルAUC"] = round(binary_metrics(wdf["won"].to_numpy(), p["oof"]["LightGBM"])["AUC"], 3)
    return out


def main():
    ap = argparse.ArgumentParser(description="新しいAIの版を作る")
    ap.add_argument("--name", required=True, help='版の名前（例："Yomi 1.1"）')
    ap.add_argument("--notes", default="", help="何を変えたかのメモ（リリースノートに出る）")
    ap.add_argument("--model", default="LightGBM", choices=MODELS, help="相手の手の予測に使うモデル")
    ap.add_argument("--features", default=",".join(OPP_DEFAULT), help="特徴量（カンマ区切り）")
    ap.add_argument("--no-activate", action="store_true", help="現役にしない（一覧に追加だけ）")
    ap.add_argument("--local", action="store_true", help="スプレッドシートではなく data/ の記録を使う")
    ap.add_argument("--yes", action="store_true", help="同じ名前の版があっても確認せずに置きかえる")
    a = ap.parse_args()

    slug = slugify(a.name)
    features = [f.strip() for f in a.features.split(",") if f.strip()]
    unknown = [f for f in features if f not in OPP_FEATURES]
    if unknown:
        sys.exit(f"知らない特徴量があります：{unknown}")
    if any(v["slug"] == slug for v in load_registry()["versions"]) and not a.yes:
        if input(f"「{a.name}」はもうあります。置きかえますか？ [y/N] ").strip().lower() != "y":
            sys.exit("やめました。")

    t0 = time.time()
    games, source = load_games(a.local)
    n_moves = sum(len(g["rounds"]) for g in games)
    print(f"データ：{source} から {len(games)} 試合・{n_moves} 手（{len({g['player'] for g in games})} 人）")
    if n_moves < MIN_HUMAN_DECISIONS:
        print(f"※ 人間の手が {MIN_HUMAN_DECISIONS} 手に足りないので、相手の読みはルール（ベースライン）のままです。"
              "勝率モデルだけを学習します。")

    brain: Brain = train_brain(games, opp_name=a.model, opp_features=features)
    print("成績を測っています…")
    metrics = evaluate(games, a.model, features, None)
    metrics["ボット相手の勝率"] = round(ai_vs_bots(brain, n=100), 3)
    meta = {
        "name": a.name, "notes": a.notes,
        "opp": brain.opp_name, "win": brain.win_name,
        "model": a.model if brain.opp_model is not None else "ルール", "features": features,
        "n_games": len(games), "n_moves": n_moves, "data_source": source,
        "metrics": metrics,
    }
    entry = save_version(brain, meta, activate=not a.no_activate)
    print(f"\n保存しました：models/{entry['slug']}.joblib（{time.time() - t0:.0f} 秒）")
    for k, v in metrics.items():
        print(f"  {k}：{v:.1%}" if k != "勝率モデルAUC" else f"  {k}：{v:.3f}")
    print(f"  現役：{'はい' if not a.no_activate else 'いいえ（一覧に追加だけ）'}")
    print("\n公開アプリに反映するには：\n  git add models\n  git commit -m \"AIの版を追加\"\n  git push")


if __name__ == "__main__":
    main()
