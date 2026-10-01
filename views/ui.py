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


# ---- みんなのデータ用の部品 ------------------------------------------------------
_DATA_CSS = """
<style>
.ya-q{display:flex;align-items:flex-start;gap:12px;margin:26px 0 8px}
.ya-q .ya-qn{flex:none;min-width:34px;height:34px;padding:0 6px;border-radius:10px;background:#12213a;color:#fff;
  font-weight:800;font-size:14px;display:flex;align-items:center;justify-content:center;letter-spacing:.04em}
.ya-q h3{font-size:21px;line-height:1.4;margin:2px 0 4px;padding:0;color:#14213a}
.ya-q p{margin:0;font-size:15px;line-height:1.75;color:#3d4a63}
.ya-ans{display:flex;gap:12px;align-items:flex-start;background:#eef5fd;border:1px solid #cde2fb;border-left:5px solid #2a78d6;
  border-radius:12px;padding:12px 16px;margin:4px 0 10px}
.ya-ans .ya-tag{flex:none;font-size:12px;font-weight:800;color:#fff;background:#2a78d6;border-radius:999px;padding:3px 10px;margin-top:2px}
.ya-ans div{font-size:16px;line-height:1.75;color:#14213a}
.ya-ans b{color:#1c5cab}
.ya-ans.warn{background:#fdf6e9;border-color:#f5dfb3;border-left-color:#eda100}.ya-ans.warn .ya-tag{background:#b87b00}
.ya-hl{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:8px 0 6px}
.ya-hl .ya-card{background:#fff;border:1px solid #d9e0ec;border-radius:16px;padding:14px 16px 13px;position:relative;overflow:hidden}
.ya-hl .ya-card:before{content:"";position:absolute;inset:0 auto 0 0;width:5px;background:var(--c,#2a78d6)}
.ya-hl .ya-k{font-size:13px;font-weight:800;color:#56627a}
.ya-hl .ya-v{font-size:30px;font-weight:900;color:#14213a;line-height:1.25;margin:4px 0 2px}
.ya-hl .ya-v small{font-size:15px;font-weight:700;color:#56627a;margin-left:4px}
.ya-hl .ya-d{font-size:14px;line-height:1.65;color:#3d4a63}
.ya-hl .ya-go{font-size:12px;color:#2a78d6;font-weight:700;margin-top:6px}
.ya-sec{font-size:13px;font-weight:800;letter-spacing:.14em;color:#2a78d6;margin:18px 0 0}
</style>
"""


def data_css():
    st.html(_DATA_CSS)


def question(n: str, title: str, lead: str = ""):
    """分析の1つ分の見出し：番号と「問い」、何を見ているかの一文。"""
    st.html(f'<div class="ya-q"><span class="ya-qn">{n}</span><div><h3>{title}</h3>'
            + (f"<p>{lead}</p>" if lead else "") + "</div></div>")


def answer(text: str, warn: bool = False, tag: str = "わかったこと"):
    """データから計算した答え（太字は <b> で）。データが足りないときは warn=True で黄色にする。"""
    st.html(f'<div class="ya-ans{" warn" if warn else ""}"><span class="ya-tag">{tag}</span><div>{text}</div></div>')


def highlights(cards: list[dict]):
    """ページ上部のまとめカード。cards：{"k": 見出し, "v": 大きい数字, "u": 単位, "d": 説明, "go": 詳しく見る場所, "c": 色}"""
    html = "".join(
        f'<div class="ya-card" style="--c:{c.get("c", "#2a78d6")}"><div class="ya-k">{c["k"]}</div>'
        f'<div class="ya-v">{c["v"]}<small>{c.get("u", "")}</small></div><div class="ya-d">{c["d"]}</div>'
        + (f'<div class="ya-go">→ {c["go"]}</div>' if c.get("go") else "") + "</div>" for c in cards)
    st.html(f'<div class="ya-hl">{html}</div>')


def section(label: str):
    st.html(f'<div class="ya-sec">{label}</div>')
