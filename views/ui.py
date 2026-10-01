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


def show_chart(chart, height: int = 280):
    """グラフの見た目をそろえる：文字は大きめ、目盛りと枠は控えめ。"""
    st.altair_chart(chart.properties(height=height)
                    .configure_axis(labelFontSize=13, titleFontSize=13, labelColor="#56627a", titleColor="#56627a",
                                    gridColor="#e9edf3", domainColor="#c9d1de", tickColor="#c9d1de", titleFontWeight=600)
                    .configure_legend(labelFontSize=13, titleFontSize=13, orient="top")
                    .configure_view(stroke=None), width="stretch")


# ---- 対戦の下（リザルト）：盤面と同じ色づかいの見出し --------------------------------
_RESULT = """
<style>
.ya-res{{display:grid;grid-template-columns:auto 1fr;gap:18px 26px;align-items:center;border-radius:20px;padding:20px 24px;color:#f4f6fb;
  background:radial-gradient(60% 120% at 0% 0%,{glow} 0%,#12213a 70%,#0b1526 100%);box-shadow:inset 0 0 0 1px #ffffff14,0 10px 30px #0003;
  font-variant-numeric:tabular-nums}}
.ya-res .ya-eb{{font-size:11px;font-weight:800;letter-spacing:.2em;color:#b3bdd0}}
.ya-res .ya-big{{font-size:44px;font-weight:900;line-height:1.1;color:{color};margin:2px 0 4px;letter-spacing:.04em}}
.ya-res .ya-sc{{font-size:17px;font-weight:800;white-space:nowrap}}
.ya-res .ya-sc .y{{color:#9cc6f7}}.ya-res .ya-sc .a{{color:#f8b08f}}.ya-res .ya-sc small{{color:#b3bdd0;font-weight:600;font-size:13px}}
.ya-res .ya-tiles{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}
.ya-res .ya-tile{{background:#0b152699;border-radius:14px;padding:10px 14px;box-shadow:inset 0 0 0 1px #ffffff14}}
.ya-res .ya-tile .k{{font-size:12px;color:#b3bdd0;font-weight:700}}
.ya-res .ya-tile .v{{font-size:26px;font-weight:900;line-height:1.3}}
.ya-res .ya-tile .v small{{font-size:13px;color:#b3bdd0;font-weight:700;margin-left:3px}}
.ya-res .ya-tile .n{{font-size:12px;color:#c3cbda;line-height:1.5}}
.ya-res .ya-say{{grid-column:1/-1;font-size:15px;line-height:1.7;color:#dfe5ef;border-top:1px solid #ffffff1a;padding-top:12px}}
.ya-res .ya-say b{{color:#ffe08a}}
@media(max-width:760px){{.ya-res{{grid-template-columns:1fr}}.ya-res .ya-tiles{{grid-template-columns:1fr 1fr 1fr}}.ya-res .ya-tile .v{{font-size:20px}}}}
</style>
<div class="ya-res">
  <div><div class="ya-eb">RESULT</div><div class="ya-big">{title}</div>
    <div class="ya-sc"><span class="y">あなた {me}</span> <small>点</small> − <span class="a">{ai} AI</span> <small>点</small></div></div>
  <div class="ya-tiles">{tiles}</div>
  <div class="ya-say">{say}</div>
</div>
"""


def result_hero(me: int, ai: int, tiles: list[tuple[str, str, str, str]], say: str):
    """リザルトの見出し。tiles：(見出し, 値, 単位, 補足) のリスト。"""
    title, color, glow = (("勝ち！", "#9cc6f7", "#2a78d633") if me > ai else ("負け…", "#f8b08f", "#eb683426") if me < ai
                          else ("引き分け", "#ffffff", "#ffffff22"))
    html = "".join(f'<div class="ya-tile"><div class="k">{k}</div><div class="v">{v}<small>{u}</small></div>'
                   f'<div class="n">{n}</div></div>' for k, v, u, n in tiles)
    st.html(_RESULT.format(title=title, color=color, glow=glow, me=me, ai=ai, tiles=html, say=say))


# 対戦の下の部分を盤面と同じ幅にそろえる（広い画面で横に伸びすぎないように）
_BELOW = """
<style>
.st-key-below_board{max-width:1180px;margin:0 auto;width:100%}
.st-key-play_bar{background:#12213a;border-radius:14px;padding:6px 8px 6px 16px;color:#dfe5ef}
.st-key-play_bar p{color:#dfe5ef;margin:0}
.st-key-share_box{background:#fff;border:1px solid #d9e0ec;border-radius:16px;padding:16px 18px;border-top:5px solid #2a78d6}
.st-key-review_box{background:#fff;border:1px solid #d9e0ec;border-radius:16px;padding:6px 18px 12px}
</style>
"""
_REVEAL_LATER = """
<style>
/* 最後のラウンドの札がめくれて点が動き終わるまで（約3秒）、リザルトを見せない */
.st-key-below_board{animation:ya-later .6s ease 3s both}
@keyframes ya-later{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
</style>
"""


def below_board_css(reveal_later: bool = False):
    st.html(_BELOW + (_REVEAL_LATER if reveal_later else ""))
