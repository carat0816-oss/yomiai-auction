import streamlit as st

from ai import MIN_HUMAN_DECISIONS, Brain
from registry import load_brain, load_registry, model_path
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


@st.cache_resource(show_spinner="AIを読み込んでいます…", max_entries=8)
def _load(slug: str, mtime: int):
    return load_brain(slug)


def get_brain(slug: str | None) -> Brain:
    """版の学習済みモデルを読み込む（学習はしない。新しい版は train_model.py で作る）。"""
    if not slug or not model_path(slug).exists():
        return Brain()   # 版がまだないときは、ルールだけで動く
    return _load(slug, model_path(slug).stat().st_mtime_ns)


registry = load_registry()
active = next((v for v in registry["versions"] if v["slug"] == registry.get("active")), None)

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
    st.markdown(f"**現役のAI**　{active['name'] if active else 'ルールのみ'}")
    if active:
        st.caption(f"{active['created_at']} 公開 ／ {active['n_games']} 試合・{active['n_moves']} 手で学習")
    st.markdown(f"**集まったデータ**　{len(games)} 試合 ／ {n_rounds} 手")
    if n_rounds < MIN_HUMAN_DECISIONS:
        st.progress(n_rounds / MIN_HUMAN_DECISIONS,
                    text=f"AIの読みを学習できるまで あと {MIN_HUMAN_DECISIONS - n_rounds} 手")
    else:
        new = n_rounds - (active["n_moves"] if active else 0)
        st.progress(1.0, text=f"学習できます（現役の版より {max(new, 0)} 手多い）")
    st.caption(f"保存先：{store.label}")
    if store.kind == "local":
        st.caption("※ Secrets にスプレッドシートの設定がないため、手元の data/ に保存しています")
    if st.button("🔄 最新のデータを読み込む"):
        load_shared.clear()
        st.rerun()

if page == "🎮 対戦":
    show_play(get_brain, registry, store, load_shared)
elif page == "📊 みんなのデータ":
    show_shared(games, store)
else:
    show_lab(games, registry)
