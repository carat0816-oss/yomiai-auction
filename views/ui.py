"""画面どうしで共通の見た目（見出し・ルールの図解）。盤面と同じ色づかいにそろえる。"""
from __future__ import annotations

import streamlit as st

_HEADER = """
<style>
.ya-ph{{margin:0 0 6px}}
.ya-ph .ya-eb{{font-size:11px;font-weight:800;letter-spacing:.18em;color:#2a78d6}}
.ya-ph h1{{font-size:30px;line-height:1.25;margin:4px 0 6px;color:#14213a;padding:0}}
.ya-ph p{{margin:0;color:#56627a;font-size:14px;line-height:1.7}}
</style>
<div class="ya-ph"><div class="ya-eb">{eyebrow}</div><h1>{title}</h1><p>{desc}</p></div>
"""


def page_header(eyebrow: str, title: str, desc: str = ""):
    st.html(_HEADER.format(eyebrow=eyebrow, title=title, desc=desc))


_RULES = """
<style>
.ya-rules{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:6px 0 4px;font-family:inherit}
.ya-rule{background:#12213a;color:#eef2f9;border-radius:16px;padding:14px 14px 12px;position:relative;overflow:hidden}
.ya-rule .ya-n{font-size:11px;font-weight:800;letter-spacing:.15em;color:#9aa6bd}
.ya-rule h3{font-size:15px;margin:4px 0 10px;color:#fff;padding:0;line-height:1.4}
.ya-rule p{font-size:12px;line-height:1.7;margin:8px 0 0;color:#c7cfdd}
.ya-pic{height:74px;display:flex;align-items:center;justify-content:center;gap:8px}
.ya-c{width:38px;height:54px;border-radius:7px;background:#fffdf7;display:flex;align-items:center;justify-content:center;
   font-weight:900;font-size:20px;box-shadow:0 4px 10px #0006}
.ya-c.y{color:#1c5cab;border-top:5px solid #3987e5}.ya-c.a{color:#b8461b;border-top:5px solid #eb6834}
.ya-c.back{background:repeating-linear-gradient(45deg,#eb6834 0 5px,#b8461b 5px 10px);box-shadow:inset 0 0 0 3px #fff,0 4px 10px #0006}
.ya-c.dim{opacity:.4;filter:grayscale(1)}
.ya-prize{width:46px;height:62px;border-radius:9px;background:linear-gradient(155deg,#fff3c4,#ffd666 45%,#d9a12b);color:#3b2a00;
   display:flex;align-items:center;justify-content:center;font-weight:900;font-size:26px;box-shadow:0 0 0 2px #fff8,0 4px 10px #0006}
.ya-vs{font-size:11px;color:#9aa6bd;font-weight:800}
.ya-tag{font-size:11px;font-weight:800;padding:2px 8px;border-radius:999px;background:#ffe08a;color:#3b2a00}
@media(max-width:640px){.ya-rules{grid-template-columns:1fr}}
</style>
<div class="ya-rules">
  <div class="ya-rule"><div class="ya-n">STEP 1</div><h3>得点カードが1枚めくられる</h3>
    <div class="ya-pic"><div class="ya-prize">8</div></div>
    <p>1〜10の得点カードを、10ラウンドで1枚ずつ取り合う。</p></div>
  <div class="ya-rule"><div class="ya-n">STEP 2</div><h3>お互いに1枚、伏せて出す</h3>
    <div class="ya-pic"><div class="ya-c y">7</div><span class="ya-vs">VS</span><div class="ya-c back"></div></div>
    <p>大きい数を出した方が、その点をもらう。使った札は戻らない。</p></div>
  <div class="ya-rule"><div class="ya-n">STEP 3</div><h3>同じ数なら相打ち</h3>
    <div class="ya-pic"><div class="ya-c y">9</div><div class="ya-c a">9</div><span class="ya-tag">流れる</span></div>
    <p>その得点カードは誰のものにもならない。流れていない点の過半数を取れば勝ち確定。</p></div>
</div>
"""


def rules_card():
    st.html(_RULES)


_STEP = """
<div style="display:flex;align-items:center;gap:10px;margin:22px 0 2px">
  <span style="flex:none;width:26px;height:26px;border-radius:50%;background:#12213a;color:#fff;font-weight:800;
    font-size:13px;display:flex;align-items:center;justify-content:center">{n}</span>
  <span style="font-size:18px;font-weight:800;color:#14213a">{title}</span>
  <span style="flex:1;height:1px;background:#d9e0ec"></span>
</div>
"""


def step(n: int, title: str):
    """手順の見出し（番号つき）。"""
    st.html(_STEP.format(n=n, title=title))