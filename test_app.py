"""Streamlit の画面のテスト（AppTest）。保存先は一時フォルダにする。"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

data_dir = Path(tempfile.mkdtemp())
os.environ["YOMIAI_DATA"] = str(data_dir)
APP = str(Path(__file__).with_name("app.py"))
T = 120


def button(at, label):
    return next(b for b in at.button if b.label == label)


# 盤面のJSに構文エラーがないか（Node.js があるときだけ確かめる）
if shutil.which("node"):
    js = Path(tempfile.mkdtemp()) / "board.mjs"
    js.write_text(Path(__file__).with_name("board").joinpath("board.js").read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["node", "--check", str(js)], check=True)
    print("PASS: 盤面JSの構文")

at = AppTest.from_file(APP, default_timeout=T).run()
assert not at.exception, at.exception
button(at, "対戦スタート →").click().run()
assert not at.exception, at.exception
# 10ラウンド：毎回、残っている一番小さい札を出す（盤面のクリックと同じ処理を通す）
for r in range(10):
    hand = at.session_state["state"]["hands"][0]
    at.session_state["queued_play"] = {"card": min(hand), "think_ms": 1200}
    at.run()
    assert not at.exception, at.exception
    assert len(at.session_state["state"]["hands"][0]) == 9 - r
assert at.session_state["state"]["r"] == 10
assert any(m.label == "AIの読みの的中" for m in at.metric)
assert at.session_state["rec"]["rounds"][0]["think_ms"] == 1200
print("PASS: 対戦を最後まで進めてリザルト")

# 送る：同意するまで送れない → 送るとファイルに1試合・10ラウンド
assert at.button(key="share").disabled
# 名前が空欄だと送れない
at.checkbox(key="consent").check().run()
at.text_input(key="player_name").input("   ")
at.button(key="share").click().run()
assert not at.exception, at.exception
assert any("プレイヤー名を入れて" in w.value for w in at.warning)
assert not (data_dir / "yomiai_games.jsonl").exists()
print("PASS: 名前が空欄なら送れない")
at.text_input(key="player_name").input("テスト花子")
at.button(key="share").click().run()
assert not at.exception, at.exception
games = [json.loads(x) for x in (data_dir / "yomiai_games.jsonl").read_text(encoding="utf-8").splitlines()]
rounds = (data_dir / "yomiai_rounds.jsonl").read_text(encoding="utf-8").splitlines()
assert len(games) == 1 and len(rounds) == 10
assert games[0]["player"] == "テスト花子" and games[0]["boardgame"] == "答えない"
assert not any(b.key == "share" for b in at.button)          # 同じ試合は二度送れない
print("PASS: 同意して送る・二重送信の防止")

# もう一度 → 新しい試合
button(at, "もう一度対戦する").click().run()
assert "state" not in at.session_state
print("PASS: もう一度対戦")

# みんなのデータ（本物1試合）とダミー
at.sidebar.radio(key="page").set_value("📊 みんなのデータ").run()
assert not at.exception, at.exception
assert at.metric[0].value == "1 試合"
at.segmented_control(key="shared_src").set_value("ダミー（練習用）").run()
assert not at.exception, at.exception
assert at.metric[0].value == "90 試合"
at.multiselect(key="shared_players").select(at.multiselect(key="shared_players").options[0]).run()
assert not at.exception, at.exception
at.multiselect(key="shared_players").set_value([]).run()
at.segmented_control(key="shared_src").set_value("みんなのデータ").run()
print("PASS: みんなのデータ（本物・ダミー・絞り込み）")

# プレイヤーのカルテ：送った名前が最初に選ばれている
assert at.selectbox(key="shared_who").value == "テスト花子"
assert len(at.tabs) == 5
print("PASS: プレイヤーのカルテ")
