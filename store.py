"""対戦記録を Googleスプレッドシートに保存・読み込みする（sorting-factory の store.py と同じ仕組み）。

- Streamlit の Secrets にサービスアカウントとスプレッドシートの URL があれば、そのシートに2つのタブを作って保存する
    yomiai_games ：1試合＝1行（プレイヤー・結果・AIの読みの的中率など）
    yomiai_rounds：1ラウンド＝1行（得点カード・両者の札・考えた時間・AIの読みなど）
  スプレッドシート上でそのままフィルタ・集計できる形にしてある
- Secrets がなければ、手元の data/ に同じ形の jsonl で保存する（動作確認用）
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import streamlit as st

from game import CARDS, N_ROUNDS, replay

GAME_TAB, ROUND_TAB = "yomiai_games", "yomiai_rounds"
GAME_COLS = ["game_id", "received_at", "player", "boardgame", "style", "ai_level", "my_score", "ai_score",
             "result", "burned", "read_top1", "read_prob", "ai_model", "version"]
ROUND_COLS = ["game_id", "player", "round", "prize", "human_card", "ai_card", "winner",
              "human_total", "ai_total", "burned_total", "think_ms", "ai_read", "read_prob", "ai_win"]
# プレイ前の質問（いまは画面に出していない。スプレッドシートの列は、前の記録とそろえるため残す）
PROFILE = {
    "boardgame": ("ボードゲームやカードゲームはよくやる？", ["よくやる", "ときどき", "あまりやらない", "答えない"]),
    "style": ("自分は慎重派？大胆派？", ["慎重派", "どちらでもない", "大胆派", "答えない"]),
}
LEVELS = {"やさしい": 0.25, "ふつう": 0.10, "本気": 0.03}   # 迷う幅：期待勝率が最善からこれだけ以内の札を候補にする
MAX_NAME = 16
VERSION = 2   # 2：同点は相打ちで得点カードが流れるルール（1は持ち越しありの試作）


def _num(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)) and math.isfinite(v):
        return v
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def clean_game(game_id: str, player: str, rec: dict) -> dict | None:
    """画面で記録した1試合を検査して、保存してよい形にそろえる。ルール上ありえない記録なら None。"""
    try:
        prizes = [int(p) for p in rec["prizes"]]
        rounds = rec["rounds"]
        cards = [(int(r["human_card"]), int(r["ai_card"])) for r in rounds]
        if sorted(prizes) != CARDS or len(cards) != N_ROUNDS:
            return None
        states = replay(prizes, cards)   # 手札にない札を出していたらここで ValueError
    except (KeyError, TypeError, ValueError):
        return None
    final = states[-1]["score"]
    # 最終ラウンドは残り1枚で読むまでもないので、読みの成績からは除く
    read_hits = [r.get("read_top") == r["human_card"] for r in rounds[:-1]]
    read_probs = [_num(r.get("read_prob")) for r in rounds[:-1]]
    read_probs = [p for p in read_probs if p is not None]
    profile = rec.get("profile") or {}
    return {
        "game_id": str(game_id)[:40],
        "player": str(player or "").strip()[:MAX_NAME] or "ゲスト",
        **{k: profile.get(k) if profile.get(k) in choices else "答えない" for k, (_, choices) in PROFILE.items()},
        "ai_level": rec.get("ai_level") if rec.get("ai_level") in LEVELS else "ふつう",
        "my_score": final[0], "ai_score": final[1],
        "result": "勝ち" if final[0] > final[1] else "負け" if final[0] < final[1] else "引き分け",
        "burned": states[-1]["burned"],
        "read_top1": round(sum(read_hits) / len(read_hits), 3),
        "read_prob": round(sum(read_probs) / len(read_probs), 3) if read_probs else "",
        "ai_model": str(rec.get("ai_model") or "")[:60],
        "prizes": prizes,
        "rounds": [{
            "round": i + 1, "prize": prizes[i],
            "human_card": c0, "ai_card": c1,
            "winner": {0: "あなた", 1: "AI", -1: "相打ち"}[states[i + 1]["log"][-1]["winner"]],
            "human_total": states[i + 1]["score"][0], "ai_total": states[i + 1]["score"][1],
            "burned_total": states[i + 1]["burned"],
            "think_ms": _num(rounds[i].get("think_ms")),
            "ai_read": str(rounds[i].get("ai_read") or "")[:60],
            "read_prob": _num(rounds[i].get("read_prob")), "ai_win": _num(rounds[i].get("ai_win")),
        } for i, (c0, c1) in enumerate(cards)],
    }


def _blank(v):
    return "" if v is None else v


def _rows(game: dict) -> tuple[list, list[list]]:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    g = {**game, "received_at": now, "version": VERSION}
    grow = [_blank(g.get(k)) for k in GAME_COLS]
    rrows = [[_blank({**r, "game_id": game["game_id"], "player": game["player"]}.get(k)) for k in ROUND_COLS]
             for r in game["rounds"]]
    return grow, rrows


def assemble(game_rows: list[dict], round_rows: list[dict]) -> list[dict]:
    """2つのタブの行 → 1試合ずつの記録（分析・学習で使う形）。壊れた試合は飛ばす。"""
    by_game: dict[str, list[dict]] = {}
    for r in round_rows:
        by_game.setdefault(str(r.get("game_id")), []).append(r)
    out = []
    for g in game_rows:
        if (_num(g.get("version")) or 0) < VERSION:   # ルールが違う古い記録は混ぜない
            continue
        gid = str(g.get("game_id"))
        rs = sorted(by_game.get(gid, []), key=lambda r: _num(r.get("round")) or 0)
        try:
            rounds = [{"round": int(_num(r["round"])), "prize": int(_num(r["prize"])),
                       "human_card": int(_num(r["human_card"])), "ai_card": int(_num(r["ai_card"])),
                       "think_ms": _num(r.get("think_ms")), "ai_read": str(r.get("ai_read") or ""),
                       "read_prob": _num(r.get("read_prob")), "ai_win": _num(r.get("ai_win"))} for r in rs]
            prizes = [r["prize"] for r in rounds]
            replay(prizes, [(r["human_card"], r["ai_card"]) for r in rounds])
        except (KeyError, TypeError, ValueError):
            continue
        if len(rounds) != N_ROUNDS or sorted(prizes) != CARDS:
            continue
        out.append({**{k: g.get(k) for k in GAME_COLS}, "game_id": gid, "player": str(g.get("player") or "ゲスト"),
                    "my_score": _num(g.get("my_score")), "ai_score": _num(g.get("ai_score")),
                    "read_top1": _num(g.get("read_top1")), "read_prob": _num(g.get("read_prob")),
                    "prizes": prizes, "rounds": rounds})
    return out


class SheetStore:
    kind = "sheet"
    label = "Googleスプレッドシート"

    def __init__(self, info: dict, url: str):
        import gspread  # Secrets があるときだけ使う

        book = gspread.service_account_from_dict(info).open_by_url(url)
        self.url = url
        self.tabs = {}
        for name, cols in ((GAME_TAB, GAME_COLS), (ROUND_TAB, ROUND_COLS)):
            try:
                ws = book.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = book.add_worksheet(name, rows=1000, cols=len(cols))
            if ws.row_values(1) != cols:
                ws.update([cols], "A1")
            self.tabs[name] = ws

    def append(self, game: dict) -> None:
        grow, rrows = _rows(game)
        # ラウンドを先に書く（途中で失敗しても、試合の行がなければ読み込み側で無視される）
        self.tabs[ROUND_TAB].append_rows(rrows, value_input_option="RAW")
        self.tabs[GAME_TAB].append_row(grow, value_input_option="RAW")

    def load(self, limit: int) -> list[dict]:
        games = self.tabs[GAME_TAB].get_all_records(expected_headers=GAME_COLS, value_render_option="UNFORMATTED_VALUE")
        rounds = self.tabs[ROUND_TAB].get_all_records(expected_headers=ROUND_COLS,
                                                      value_render_option="UNFORMATTED_VALUE")
        return assemble(games[-limit:], rounds)


class LocalStore:
    kind = "local"
    label = "ローカルファイル（data/）"

    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.files = {GAME_TAB: folder / f"{GAME_TAB}.jsonl", ROUND_TAB: folder / f"{ROUND_TAB}.jsonl"}

    def append(self, game: dict) -> None:
        grow, rrows = _rows(game)
        with self.files[ROUND_TAB].open("a", encoding="utf-8") as fp:
            for r in rrows:
                fp.write(json.dumps(dict(zip(ROUND_COLS, r)), ensure_ascii=False) + "\n")
        with self.files[GAME_TAB].open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(dict(zip(GAME_COLS, grow)), ensure_ascii=False) + "\n")

    def _read(self, tab: str) -> list[dict]:
        path = self.files[tab]
        if not path.exists():
            return []
        rows = []
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return rows

    def load(self, limit: int) -> list[dict]:
        return assemble(self._read(GAME_TAB)[-limit:], self._read(ROUND_TAB))


_NO_SECRETS = (KeyError, FileNotFoundError, getattr(st.errors, "StreamlitSecretNotFoundError", FileNotFoundError))


@st.cache_resource
def _local_store(path: str):
    return LocalStore(Path(path))


@st.cache_resource
def _sheet_store(url: str, info_json: str):
    return SheetStore(json.loads(info_json), url)


def get_store():
    # テストでは YOMIAI_DATA で保存先のフォルダを差し替える（Secrets があっても本物のシートに書かない）
    if os.environ.get("YOMIAI_DATA"):
        return _local_store(os.environ["YOMIAI_DATA"])
    try:
        info = dict(st.secrets["gcp_service_account"])
        url = st.secrets["sheet_url"]
    except _NO_SECRETS:
        return _local_store(str(Path(__file__).parent / "data"))
    return _sheet_store(url, json.dumps(info, sort_keys=True))
