"""🤖 モデル工房：特徴量とモデルを選んで学習・評価し、気に入ったモデルをAIに採用する。"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ml import (LEAKS, MODELS, OPP_DEFAULT, OPP_FEATURES, WIN_DEFAULT, WIN_FEATURES, binary_metrics, cross_validate,
                decision_metrics, heuristic_opp, logistic_coefs, make_model, normalize, opp_dataset,
                partial_dependence, permutation_importance, win_dataset)
from views.shared import choose_source
from views.ui import page_header, step

COLORS = {"ロジスティック回帰": "#2a78d6", "決定木": "#eb6834", "ランダムフォレスト": "#1baf7a", "LightGBM": "#eda100",
          "ルール（ベースライン）": "#898781", "当てずっぽう": "#c3c2b7", "点差だけ（ベースライン）": "#898781"}
TASKS = {
    "opp": "🃏 相手が次に出す札を当てる（AIの読み）",
    "win": "🏁 この局面から勝てるかを当てる（勝率メーター）",
}
MIN_ROWS = {"opp": 30, "win": 40}


@st.cache_data(show_spinner=False)
def _datasets(games: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    return opp_dataset(games), win_dataset(games)


@st.cache_data(show_spinner="学習・評価しています…")
def _evaluate(df: pd.DataFrame, task: str, features: tuple, names: tuple, how: str, params: dict) -> dict:
    target, unit = ("chosen", "player") if task == "opp" else ("won", "game_id")
    cv = cross_validate(df, target, list(features), list(names), how, params, unit)
    y = df[target].to_numpy()
    rows, curves = [], {}
    for name, p in cv["oof"].items():
        m = binary_metrics(y, p)
        if task == "opp":
            m.update(decision_metrics(df, normalize(df, np.nan_to_num(p, nan=1e-6))))
        rows.append({"モデル": name, **m})
        curves[name] = p
    # ベースライン（比べる相手）
    if task == "opp":
        h = heuristic_opp(df)
        rows.append({"モデル": "ルール（ベースライン）", **binary_metrics(y, h), **decision_metrics(df, h)})
        u = normalize(df, np.ones(len(df)))
        rows.append({"モデル": "当てずっぽう", **binary_metrics(y, u), **decision_metrics(df, u)})
        curves["ルール（ベースライン）"] = h
    else:
        b = cross_validate(df, target, ["lead_ratio"], ["ロジスティック回帰"], how, None, unit)["oof"]["ロジスティック回帰"]
        rows.append({"モデル": "点差だけ（ベースライン）", **binary_metrics(y, b)})
        curves["点差だけ（ベースライン）"] = b
    return {"table": pd.DataFrame(rows).set_index("モデル"), "curves": curves, "folds": cv["folds"]}


@st.cache_resource(show_spinner=False)
def _fit_all(df: pd.DataFrame, target: str, features: tuple, name: str, params_key: tuple):
    return make_model(name, list(features), dict(params_key)).fit(df[list(features)], df[target])


def _calibration(df: pd.DataFrame, target: str, curves: dict, task: str) -> pd.DataFrame:
    out = []
    for name, p in curves.items():
        q = normalize(df, np.nan_to_num(p, nan=1e-6)) if task == "opp" else p
        d = pd.DataFrame({"p": q, "y": df[target].to_numpy()}).dropna()
        d["bin"] = pd.cut(d["p"], np.linspace(0, 1, 11), include_lowest=True)
        g = d.groupby("bin", observed=True).agg(予測=("p", "mean"), 実際=("y", "mean"), 行数=("y", "size")).reset_index(drop=True)
        out.append(g[g["行数"] >= 5].assign(モデル=name))
    return pd.concat(out, ignore_index=True)


def _color(names):
    return alt.Scale(domain=list(names), range=[COLORS.get(n, "#4a3aa7") for n in names])


def show_lab(games: list[dict], registry: dict):
    page_header("MODEL LAB", "モデル工房",
                "集まった対戦データで予測モデルを作って比べる場所です。良いモデルができたら、対戦AIに採用できます。")
    step(1, "データを選ぶ")
    games, dummy = choose_source(games, "lab")
    opp_df, win_df = _datasets(games)
    step(2, "何を予測する？")
    task = st.radio("何を予測する？", list(TASKS), format_func=TASKS.get, key="lab_task", label_visibility="collapsed")
    df = opp_df if task == "opp" else win_df
    feats_all = OPP_FEATURES if task == "opp" else WIN_FEATURES
    default = OPP_DEFAULT if task == "opp" else WIN_DEFAULT
    target = "chosen" if task == "opp" else "won"
    if task == "opp":
        st.caption("人間が札を出した1回ごとに、手札の候補1枚＝1行の表を作り、「実際にその札を出したか（1/0）」を2値分類します。"
                   "予測した確率を候補の中で合計1になるように割ると、「どの札を出しそうか」の確率分布になります。")
    else:
        st.caption("ラウンドの合間の局面1つ＝1行（両者の目線で2行）。その試合に最終的に勝ったか（1/0）を2値分類します。"
                   "引き分けの試合は除いています。")
    n_decisions = df["decision"].nunique() if task == "opp" and not df.empty else len(df)
    if len(df) < MIN_ROWS[task] or df.empty or df[target].nunique() < 2:
        st.info(f"まだデータが少なすぎます（いま {n_decisions} 件）。対戦を集めるか、上の「ダミー（練習用）」で試してください。")
        return
    st.markdown(f"**データ：{len(df):,} 行**（{'判断' if task == 'opp' else '局面'} {n_decisions:,} 件、"
                f"{df['player'].nunique()} 人）")

    step(3, "特徴量とモデルを選んで学習")
    with st.form("lab_form"):
        features = st.multiselect("説明変数（特徴量）", list(feats_all), default=default,
                                  format_func=lambda f: feats_all[f][0], key=f"lab_feats_{task}")
        with st.expander("特徴量の説明"):
            st.dataframe(pd.DataFrame([{"列名": k, "名前": v[0], "説明": v[1]} for k, v in feats_all.items()]),
                         hide_index=True, width="stretch")
        with st.expander("⚠️ 候補に入れていない列（リーク）"):
            st.markdown("答えを見てからでないとわからない列は、入れると成績がよく見えますが、本番では使えません。")
            st.dataframe(pd.DataFrame([{"列名": k, "理由": v} for k, v in LEAKS.items()]), hide_index=True,
                         width="stretch")
        names = st.multiselect("モデル", MODELS, default=["ロジスティック回帰", "LightGBM"], key="lab_models")
        how = st.radio("テストの分け方", ["group", "random"], horizontal=True, key="lab_how",
                       format_func={"group": "人ごとに分ける（初めての相手を当てる）",
                                    "random": "試合ごとにランダム（同じ人の別の試合が学習側に入る）"}.get)
        with st.expander("ハイパーパラメータ"):
            c1, c2, c3 = st.columns(3)
            params = {"max_depth": c1.slider("木の深さ（決定木・RF）", 2, 12, 5),
                      "min_leaf": c2.slider("葉の最小サンプル数", 5, 100, 20),
                      "n_trees": c3.slider("木の本数（RF・LightGBM）", 50, 500, 200, step=50),
                      "lr": c1.select_slider("学習率（LightGBM）", [0.01, 0.03, 0.05, 0.1, 0.2], 0.05),
                      "leaves": c2.slider("葉の数（LightGBM）", 4, 63, 15),
                      "C": c3.select_slider("正則化の弱さ C（ロジスティック）", [0.01, 0.1, 1.0, 10.0, 100.0], 1.0)}
        go = st.form_submit_button("学習して評価する", type="primary", width="stretch")
    if go:
        if not features or not names:
            st.warning("特徴量とモデルを1つ以上選んでください。")
            return
        st.session_state.lab_cfg = dict(task=task, features=tuple(features), names=tuple(names), how=how,
                                        params=params, dummy=dummy)
    cfg = st.session_state.get("lab_cfg")
    if not cfg or cfg["task"] != task:
        st.caption("条件を選んで「学習して評価する」を押してください。")
        return
    res = _evaluate(df, task, cfg["features"], cfg["names"], cfg["how"], cfg["params"])

    step(4, "成績を見る（交差検証）")
    st.caption(f"{res['folds']}分割の交差検証。どの行も「その行を学習に使っていないモデル」で予測した値で採点しています。")
    tab = res["table"].copy()
    fmt = {c: "{:.1%}" for c in ("的中率（1位）", "実際の札につけた確率", "正解率") if c in tab}
    fmt.update({c: "{:.3f}" for c in ("AUC", "対数損失", "対数損失（判断ごと）") if c in tab})
    st.dataframe(tab.style.format(fmt, na_rep="—"), width="stretch")
    if task == "opp":
        st.caption("的中率（1位）＝一番確率が高いとした札が当たった割合。対数損失＝実際の札につけた確率の −log の平均"
                   "（小さいほど良い）。AUC は候補1行ずつの2値分類としての成績です。")
    else:
        st.caption("AUC＝勝つ局面ほど高い確率をつけられているか（0.5で当てずっぽう、1で完璧）。")

    st.markdown("#### 予測の確率は信用できる？（キャリブレーション）")
    cal = _calibration(df, target, res["curves"], task)
    names_all = list(res["curves"])
    line = alt.Chart(pd.DataFrame({"x": [0, 1]})).mark_line(color="#c3c2b7", strokeDash=[4, 4]).encode(x="x:Q", y="x:Q")
    st.altair_chart(line + alt.Chart(cal).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2).encode(
        x=alt.X("予測:Q", title="予測した確率", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("実際:Q", title="実際に起きた割合", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("モデル:N", scale=_color(names_all), legend=alt.Legend(orient="top", title=None)),
        tooltip=["モデル", alt.Tooltip("予測:Q", format=".0%"), alt.Tooltip("実際:Q", format=".0%"), "行数"],
    ).properties(height=300), width="stretch")
    st.caption("点線に近いほど「70%と言ったら7割当たる」正直なモデル。5行未満の区間は表示していません。")

    st.markdown("#### どの特徴量が効いている？")
    pick = st.selectbox("モデル", cfg["names"], key="lab_pick")
    unit = "player" if task == "opp" else "game_id"
    imp = _importance(df, target, cfg["features"], pick, cfg["params"], unit)
    imp_df = imp.rename("AUCの低下").reset_index().rename(columns={"index": "特徴量"})
    imp_df["名前"] = imp_df["特徴量"].map(lambda f: feats_all[f][0])
    st.altair_chart(alt.Chart(imp_df).mark_bar(color=COLORS.get(pick, "#2a78d6"), cornerRadiusEnd=4).encode(
        x=alt.X("AUCの低下:Q"), y=alt.Y("名前:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
        tooltip=["名前", alt.Tooltip("AUCの低下:Q", format=".4f")]).properties(height=max(160, 24 * len(imp_df))),
        width="stretch")
    st.caption("permutation importance：テスト用の人（25%）のデータで、その列だけをシャッフルしたら AUC がどれだけ下がるか。"
               "大きいほど、その列に頼って予測しています。")
    model = _fit_all(df, target, cfg["features"], pick, tuple(sorted(cfg["params"].items())))
    if pick == "ロジスティック回帰":
        with st.expander("ロジスティック回帰の係数"):
            co = logistic_coefs(model, list(cfg["features"]))
            st.dataframe(co.rename("係数（標準化後）").to_frame().assign(
                名前=lambda x: [feats_all.get(i, (i,))[0] if i in feats_all else i for i in x.index]), width="stretch")
            st.caption("＋なら、その値が大きいほど「1」（出す／勝つ）になりやすい。標準化してあるので大きさを比べられます。")

    st.markdown("#### 特徴量を動かすと、予測はどう変わる？（部分依存）")
    num_feats = [f for f in cfg["features"] if f not in ("boardgame", "style")]
    f = st.selectbox("特徴量", num_feats, format_func=lambda x: feats_all[x][0], key="lab_pdp")
    vals = df[f].dropna()
    grid = sorted(vals.unique()) if vals.nunique() <= 25 else list(np.quantile(vals, np.linspace(0.02, 0.98, 20)))
    pdps = []
    for name in cfg["names"]:
        m = _fit_all(df, target, cfg["features"], name, tuple(sorted(cfg["params"].items())))
        pdps.append(partial_dependence(m, df[list(cfg["features"])], f, grid).assign(モデル=name))
    pdp = pd.concat(pdps)
    st.altair_chart(alt.Chart(pdp).mark_line(point=alt.OverlayMarkDef(size=50, filled=True), strokeWidth=2).encode(
        x=alt.X("値:Q", title=feats_all[f][0]), y=alt.Y("予測確率の平均:Q", axis=alt.Axis(format="%")),
        color=alt.Color("モデル:N", scale=_color(list(cfg["names"])), legend=alt.Legend(orient="top", title=None)),
        tooltip=["モデル", "値", alt.Tooltip("予測確率の平均:Q", format=".1%")]).properties(height=280), width="stretch")
    st.caption("ほかの列はそのままで、この列だけを横軸の値に置きかえたときの、予測確率の平均。"
               "ロジスティック回帰はなめらかなS字、木のモデルは階段状になります。")

    if task == "opp":
        _example(df, model, cfg, pick)
        step(5, "この設定で、対戦AIの新しい版を作る")
        active = next((v for v in registry["versions"] if v["slug"] == registry.get("active")), None)
        if active and "読みの的中率" in active.get("metrics", {}):
            mine = res["table"].loc[pick, "的中率（1位）"] if pick in res["table"].index else None
            st.caption(f"現役の {active['name']} の読みの的中率は {active['metrics']['読みの的中率']:.1%}"
                       + (f"、いまの「{pick}」は {mine:.1%}（{'ダミー' if dummy else 'みんなの'}データでの値）" if mine else "")
                       + "。上回っていれば、新しい版にする価値があります。")
        st.markdown("対戦AIは、管理者が手元で作った**決まった版**を使います（公開アプリが勝手に学習し直すことはありません）。"
                    "この設定で版を作るには、手元のフォルダで次を実行して、できたファイルを push します。")
        name = "Yomi " + _next_version(registry)
        st.code(f'.venv\\Scripts\\python train_model.py --name "{name}" --model {pick} '
                f'--features {",".join(cfg["features"])} --notes "ここに変えた点を書く"', language="bash")
        st.caption("ハイパーパラメータは既定の値で学習します。データはその時点のスプレッドシートの全対戦を使います。")


def _next_version(registry: dict) -> str:
    """次の版の番号の案（いちばん新しい版の小数点以下を1つ上げる）。"""
    import re
    for v in registry["versions"]:
        m = re.search(r"(\d+)\.(\d+)", v["name"])
        if m:
            return f"{m.group(1)}.{int(m.group(2)) + 1}"
    return "1.0"


@st.cache_data(show_spinner="重要度を計算しています…")
def _importance(df, target, features, name, params, unit):
    return permutation_importance(df, target, list(features), name, params, unit)


def _example(df: pd.DataFrame, model, cfg, name):
    st.markdown("#### 実際の1場面で見てみる")
    st.caption("学習に使ったデータの中から1場面を選んで、モデルの読みと実際に出した札を比べます。")
    decs = df["decision"].unique()
    i = st.number_input("場面の番号", 0, len(decs) - 1, 0, key="lab_example")
    d = df[df["decision"] == decs[int(i)]].copy()
    d["予測"] = normalize(d, model.predict_proba(d[list(cfg["features"])])[:, 1])
    first = d.iloc[0]
    st.markdown(f"{first['player']}　ラウンド {first['round_no']}｜得点カード **{first['prize']}**"
                f"｜点差 {first['score_diff']:+d}｜流れた点 {first['burned']}")
    d["実際"] = d["chosen"].map({1: "出した札", 0: "その他"})
    st.altair_chart(alt.Chart(d).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("card:O", title="手札"), y=alt.Y("予測:Q", axis=alt.Axis(format="%"), title=f"{name} の予測"),
        color=alt.Color("実際:N", scale=alt.Scale(domain=["出した札", "その他"], range=["#2a78d6", "#c3c2b7"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("card:O", title="札"), alt.Tooltip("予測:Q", format=".0%")]).properties(height=260),
        width="stretch")
    st.caption("※ この場面は学習にも使われているので、交差検証の成績より当たりやすく見えます。")
