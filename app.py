import streamlit as st

from ai import MIN_HUMAN_DECISIONS, train_brain
from ml import OPP_DEFAULT
from store import get_store
from views.lab import show_lab
from views.play import show_play
from views.shared import show_shared

st.set_page_config(page_title="読み合いオークション", page_icon="🃏", layout="centered")

MAX_SHARED = 1000   # 読み込む「みんなのデータ」の最大試合数（新しい順）

store = get_store()


@st.cache_data(ttl=60, show_spinner=False)
def load_shared() -> list[dict]:
    return store.load(MAX_SHARED)


@st.cache_resource
def adopted() -> dict:
    """モデル工房で採用したモデル（このサーバーで遊ぶ全員で共有）。"""
    return {}


@st.cache_resource(show_spinner="AIを学習しています…", max_entries=3)
def get_brain(n_games: int, opp_name: str, opp_features: tuple, _games: list[dict]):
    # n_games が変わったとき（新しい対戦が届いたとき）だけ学習し直す
    return train_brain(_games, opp_name=opp_name, opp_features=list(opp_features))


with st.sidebar:
    st.header("🃏 読み合いオークション")
    page = st.radio("画面", ["🎮 対戦", "📊 みんなのデータ", "🤖 モデル工房"], key="page", label_visibility="collapsed")
    st.caption("※ 対戦中に画面を切り替えても、対戦は続きから再開できます")
    try:
        games = load_shared()
    except Exception as e:  # 保存先に一時的につながらなくても遊べるようにする
        games = []
        st.warning(f"データの読み込みに失敗しました：{e}")
    n_rounds = sum(len(g["rounds"]) for g in games)
    st.divider()
    st.markdown(f"**集まったデータ**　{len(games)} 試合 ／ {n_rounds} 手")
    if n_rounds < MIN_HUMAN_DECISIONS:
        st.progress(n_rounds / MIN_HUMAN_DECISIONS,
                    text=f"AIの読みの学習開始まで あと {MIN_HUMAN_DECISIONS - n_rounds} 手")
    else:
        st.progress(1.0, text="AIの読みは、みんなのデータで学習済み")
    st.caption(f"保存先：{store.label}")
    if store.kind == "local":
        st.caption("※ Secrets にスプレッドシートの設定がないため、手元の data/ に保存しています")
    if st.button("🔄 最新のデータを読み込む"):
        load_shared.clear()
        st.rerun()

choice = adopted().get("opp") or {"name": "LightGBM", "features": OPP_DEFAULT}
brain = get_brain(len(games), choice["name"], tuple(choice["features"]), games)

if page == "🎮 対戦":
    show_play(brain, store, load_shared)
elif page == "📊 みんなのデータ":
    show_shared(games, store)
else:
    show_lab(games, adopted())
