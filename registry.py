"""AIの版（学習済みモデル）の一覧と保存・読み込み。

models/registry.json に版の一覧を、models/<slug>.joblib に学習済みのモデル（ai.Brain）を置く。
アプリはここから読み込むだけで、学習はしない。新しい版は train_model.py で作る。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import joblib

MODELS_DIR = Path(__file__).resolve().parent / "models"
REGISTRY = MODELS_DIR / "registry.json"


def slugify(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z.]+", "-", name.strip().lower()).strip("-")
    if not s:
        raise ValueError("版の名前には英数字を入れてください（例：Yomi 1.1）")
    return s


def load_registry() -> dict:
    """{"active": 現役の版の slug, "versions": [新しい順の版の情報]}"""
    if not REGISTRY.exists():
        return {"active": None, "versions": []}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def model_path(slug: str) -> Path:
    return MODELS_DIR / f"{slug}.joblib"


def load_brain(slug: str):
    # joblib（pickle）は読み込むファイルの中身を実行できるので、信頼できるファイルだけを読む。
    # ここで読むのは、管理者が train_model.py で作ってリポジトリに入れた models/ の中身だけ。
    return joblib.load(model_path(slug))


def save_version(brain, meta: dict, activate: bool = True) -> dict:
    """学習済みの brain を保存して、一覧に書き足す（同じ名前があれば置きかえる）。"""
    MODELS_DIR.mkdir(exist_ok=True)
    slug = slugify(meta["name"])
    brain.version = meta["name"]
    joblib.dump(brain, model_path(slug), compress=3)
    reg = load_registry()
    entry = {"slug": slug, "created_at": time.strftime("%Y-%m-%d %H:%M"), **meta}
    reg["versions"] = [entry] + [v for v in reg["versions"] if v["slug"] != slug]
    if activate or not reg.get("active"):
        reg["active"] = slug
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry
