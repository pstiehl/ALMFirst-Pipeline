"""ALM First Southeast pipeline — Streamlit app.

    streamlit run app.py

Public NCUA data drives the map, targeting and product fit. Your pipeline
notes and any Salesforce export live in data/private/ (git-ignored).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from almpipe import pipeline as pl  # noqa: E402
from almpipe.scoring import add_priority, load_products, score  # noqa: E402

DATA = ROOT / "data" / "processed" / "credit_unions.csv.gz"
PRIVATE = ROOT / "data" / "private"
PRODUCTS_YAML = ROOT / "config" / "products.yaml"
TERRITORY_YAML = ROOT / "config" / "territory.yaml"

st.set_page_config(page_title="ALM First SE Pipeline", layout="wide", page_icon="🗺️")


# ---------- data ----------
@st.cache_data(show_spinner="Loading NCUA data…")
def load_base(mtime: float) -> pd.DataFrame:
    return pd.read_csv(DATA, dtype={"cu_number": str, "zip": str})


@st.cache_data
def rescore(base: pd.DataFrame, products_mtime: float) -> pd.DataFrame:
    # re-score on every products.yaml edit so rule changes show up instantly
    return score(base, load_products(PRODUCTS_YAML))


if not DATA.exists():
    st.error("No data yet. Run `python scripts/build_data.py` first.")
    st.stop()

products = load_products(PRODUCTS_YAML)
territory = yaml.safe_load(TERRITORY_YAML.read_text())
df = rescore(load_base(DATA.stat().st_mtime), PRODUCTS_YAML.stat().st_mtime)
clients = pl.load_clients(PRIVATE)
pipe = pl.load_pipeline(PRIVATE)
df["is_client"] = df["cu_number"].isin(clients)
df["display_name"] = df["name"].str.title()
PLABEL = {k: p["label"] for k, p in products.items()}

# ---------- sidebar filters ----------
st.sidebar.title("🗺️ SE Pipeline")
st.sidebar.caption(f"NCUA 5300 · quarter {df['quarter'].iloc[0]} · {len(df):,} US credit unions")
states = st.sidebar.multiselect("States", sorted(df["state"].dropna().unique()), default=territory["states"])
lo, hi = st.sidebar.select_slider(
    "Total assets",
    options=[0, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 1_000_000],
    value=(territory.get("min_assets_m", 50), 1_000_000),
    format_func=lambda v: "no max" if v >= 1_000_000 else (f"${v/1000:g}B" if v >= 1000 else f"${v}M"),
)
prod_filter = st.sidebar.multiselect("Top product", list(PLABEL), format_func=PLABEL.get)
min_fit = st.sidebar.slider("Min fit for selected product(s)", 0, 100, 0, 5, disabled=not prod_filter)
hide_clients = st.sidebar.checkbox("Hide current ALM First clients", value=True, help="Uses data/private/clients.csv")
query = st.sidebar.text_input("Search name / city")

mask = df["state"].isin(states) & df["assets_m"].between(lo, hi)
if prod_filter:
    mask &= df["top_product"].isin(prod_filter) | df[[f"fit_{p}" for p in prod_filter]].ge(max(min_fit, 1)).any(axis=1)
if hide_clients:
    mask &= ~df["is_client"]
if query:
    q = query.lower()
    mask &= df["name"].str.lower().str.contains(q, na=False) | df["city"].str.lower().str.contains(q, na=False)
df = add_priority(df, mask)
T = df[mask].copy()
st.sidebar.metric("Credit unions in view", f"{len(T):,}", f"${T['total_assets'].sum()/1e9:,.0f}B assets", delta_color="off")


def money(v):
    if pd.isna(v):
        return "—"
    return f"${v/1e9:,.1f}B" if abs(v) >= 1e9 else f"${v/1e6:,.0f}M"


def pct(v):
    return "—" if pd.isna(v) else f"{v*100:.1f}%"


tab_today, tab_map, tab_targets, tab_cu, tab_pipe, tab_terr = st.tabs(
    ["📋 Today", "🗺️ Map", "🎯 Targets", "🏦 Credit union", "🧭 Pipeline & import", "📊 Territory"]
)

# ---------- Today ----------
with tab_today:
    st.subheader("Who to work today")
    st.caption("Due follow-ups first, then the highest-value targets you haven't touched. Set next-action dates in 🏦 Credit union.")
    todo = pl.todays_list(T, pipe, n=st.slider("How many", 5, 50, 20, 5))
    if todo.empty:
        st.info("Nothing in view. Widen the filters.")
    else:
        show = todo.assign(
            Assets=todo["total_assets"].map(money),
            Pitch=todo["top_product"].map(PLABEL),
            Why=[r.get(f"why_{r['top_product']}", "") if isinstance(r["top_product"], str) else "" for _, r in todo.iterrows()],
        )[["bucket", "display_name", "city", "state", "Assets", "priority", "Pitch", "Why", "stage", "next_action", "next_action_date"]]
        st.dataframe(show.rename(columns={"bucket": "Bucket", "display_name": "Credit union", "priority": "Priority"}),
                     hide_index=True, width="stretch")

# ---------- Map ----------
with tab_map:
    color_by = st.radio("Color by", ["Top product", "Priority", "Pipeline stage"], horizontal=True)
    M = T.dropna(subset=["lat", "lon"]).merge(pipe[["cu_number", "stage"]], on="cu_number", how="left")
    M["stage"] = M["stage"].fillna("Target")
    M["Top product"] = M["top_product"].map(PLABEL).fillna("—")
    M["Assets"] = M["total_assets"].map(money)
    M["size"] = (M["assets_m"].clip(lower=1) ** 0.5)
    color = {"Top product": "Top product", "Priority": "priority", "Pipeline stage": "stage"}[color_by]
    fig = px.scatter_map(
        M, lat="lat", lon="lon", size="size", color=color, size_max=38, zoom=4.3,
        center={"lat": 32.5, "lon": -83.5}, height=720, map_style="carto-positron",
        hover_name="display_name",
        hover_data={"city": True, "state": True, "Assets": True, "Top product": True, "priority": True,
                    "stage": True, "lat": False, "lon": False, "size": False},
        color_continuous_scale="Viridis",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig, width="stretch")
    st.caption("Bubble size = total assets. Locations are ZIP/city centroids from the Census gazetteer, not street addresses.")

# ---------- Targets ----------
with tab_targets:
    st.subheader("Ranked targets")
    st.caption("Priority = percentile of estimated annual revenue (fit × placeholder fee) within the current view. Edit rules in config/products.yaml.")
    cols = ["priority", "display_name", "city", "state", "assets_m", "top_product", "expected_value",
            *[f"fit_{p}" for p in products], "loan_to_share", "nw_ratio", "roa", "long_asset_pct",
            "inv_pct", "afs_loss_to_nw", "share_growth_yoy", "members"]
    R = T.sort_values("expected_value", ascending=False)[cols + ["cu_number"]].copy()
    R["top_product"] = R["top_product"].map(PLABEL)
    for c in ["loan_to_share", "nw_ratio", "roa", "long_asset_pct", "inv_pct", "afs_loss_to_nw", "share_growth_yoy"]:
        R[c] = (R[c] * 100).round(1)
    st.dataframe(
        R.drop(columns="cu_number"), hide_index=True, width="stretch", height=620,
        column_config={
            "display_name": "Credit union",
            "assets_m": st.column_config.NumberColumn("Assets ($M)", format="%.0f"),
            "expected_value": st.column_config.NumberColumn("Est. annual $ (placeholder)", format="$%.0f"),
            "priority": st.column_config.ProgressColumn("Priority", min_value=0, max_value=100, format="%d"),
            **{f"fit_{p}": st.column_config.NumberColumn(products[p]["label"].split(" (")[0], format="%d") for p in products},
            "loan_to_share": "Loan/share %", "nw_ratio": "Net worth %", "roa": "ROA %",
            "long_asset_pct": "Long assets %", "inv_pct": "Securities %", "afs_loss_to_nw": "AFS loss / NW %",
            "share_growth_yoy": "Share growth YoY %",
        },
    )
    st.download_button("Download CSV", R.to_csv(index=False), "se_targets.csv", "text/csv")

# ---------- Credit union detail ----------
with tab_cu:
    opts = T.sort_values("total_assets", ascending=False)
    if opts.empty:
        st.info("Nothing in view.")
    else:
        label = opts["display_name"] + " — " + opts["city"].str.title() + ", " + opts["state"] + " (" + opts["total_assets"].map(money) + ")"
        pick = st.selectbox("Credit union", opts["cu_number"], format_func=dict(zip(opts["cu_number"], label)).get)
        r = df[df["cu_number"] == pick].iloc[0]
        st.subheader(f"{r['display_name']} · {str(r['city']).title()}, {r['state']}")
        st.caption(f"NCUA charter #{r['cu_number']} · peer group {r['peer_group']} · {'Federal' if str(r['cu_type']) == '1' else 'State'} charter"
                   + (" · ⭐ current ALM First client" if r["is_client"] else ""))
        c = st.columns(6)
        c[0].metric("Total assets", money(r["total_assets"]), pct(r["asset_growth_yoy"]) + " YoY")
        c[1].metric("Loans / shares", pct(r["loan_to_share"]))
        c[2].metric("Net worth ratio", pct(r["nw_ratio"]))
        c[3].metric("ROA (annualized)", pct(r["roa"]))
        c[4].metric("Members", f"{r['members']:,.0f}")
        c[5].metric("Priority", "—" if pd.isna(r["priority"]) else f"{r['priority']:.0f}")

        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Product fit** (why this CU might buy)")
            fit = pd.DataFrame([{
                "Product": products[p]["label"], "Fit": r[f"fit_{p}"],
                "Est. annual $": r[f"ev_{p}"], "Why": r[f"why_{p}"] or ("outside size gate" if r[f"fit_{p}"] == 0 else "size only"),
            } for p in products]).sort_values("Est. annual $", ascending=False)
            st.dataframe(fit, hide_index=True, width="stretch",
                         column_config={"Fit": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                                        "Est. annual $": st.column_config.NumberColumn(format="$%.0f")})
            st.markdown("**Balance sheet vs national peer group** (percentile, 100 = highest)")
            peer = pd.DataFrame([
                {"Metric": n, "Value": pct(r[m]), "Peer percentile": r.get(f"{m}_pctl")}
                for m, n in [("loan_to_share", "Loan / share"), ("nw_ratio", "Net worth ratio"), ("roa", "ROA"),
                             ("long_asset_pct", "Long assets / assets"), ("liquid_pct", "Liquid assets / assets"),
                             ("inv_pct", "Securities / assets"), ("share_growth_yoy", "Share growth YoY")]
            ])
            st.dataframe(peer, hide_index=True, width="stretch",
                         column_config={"Peer percentile": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")})
        with right:
            st.markdown("**Pipeline** (saved locally, never committed)")
            cur = pipe[pipe["cu_number"] == pick]
            cur = cur.iloc[0].to_dict() if len(cur) else {}
            with st.form(f"pipe_{pick}"):
                stage = st.selectbox("Stage", pl.STAGES, index=pl.STAGES.index(cur.get("stage")) if cur.get("stage") in pl.STAGES else 0)
                prods = list(products)
                default_p = cur.get("product") if cur.get("product") in prods else (r["top_product"] if r["top_product"] in prods else prods[0])
                product = st.selectbox("Lead product", prods, index=prods.index(default_p), format_func=PLABEL.get)
                nxt = st.text_input("Next action", value=cur.get("next_action") or "")
                nd = pd.to_datetime(cur.get("next_action_date"), errors="coerce")
                nxt_date = st.date_input("Next action date", value=None if pd.isna(nd) else nd.date())
                notes = st.text_area("Notes", value=cur.get("notes") or "", height=120)
                touched = st.checkbox("Log a touch today")
                if st.form_submit_button("Save"):
                    pipe = pl.upsert(pipe, {
                        "cu_number": pick, "stage": stage, "product": product, "next_action": nxt,
                        "next_action_date": nxt_date.isoformat() if nxt_date else None,
                        "last_touch": dt.date.today().isoformat() if touched else cur.get("last_touch"),
                        "notes": notes,
                    })
                    pl.save_pipeline(pipe, PRIVATE)
                    st.success("Saved to data/private/pipeline.csv")
            st.markdown(f"[NCUA profile](https://mapping.ncua.gov/ResearchCreditUnion?charterNumber={r['cu_number']}) · "
                        f"[Google](https://www.google.com/search?q={str(r['name']).replace(' ', '+')}+credit+union+{r['state']})")

# ---------- Pipeline & import ----------
with tab_pipe:
    st.subheader("Pipeline")
    P = pipe.merge(df[["cu_number", "display_name", "state", "total_assets", "top_product"]], on="cu_number", how="left")
    if P.empty:
        st.info("No pipeline entries yet. Open a credit union and hit Save.")
    else:
        P["Assets"] = P["total_assets"].map(money)
        P["product"] = P["product"].map(PLABEL)
        by_stage = P.groupby("stage").size().reindex(pl.STAGES).dropna()
        st.plotly_chart(px.bar(by_stage, orientation="h", labels={"value": "Accounts", "stage": ""}, height=260), width="stretch")
        st.dataframe(P[["display_name", "state", "Assets", "stage", "product", "next_action", "next_action_date", "last_touch", "notes"]],
                     hide_index=True, width="stretch")

    st.divider()
    st.subheader("Import a Salesforce export (CSV)")
    st.caption("Matched to NCUA records by name + state. The file is read in memory; only the match (charter number, stage) is saved locally.")
    up = st.file_uploader("Salesforce report CSV", type=["csv"])
    if up is not None:
        sf = pd.read_csv(up, dtype=str)
        cols = list(sf.columns)
        guess = lambda keys: next((i for i, c in enumerate(cols) if any(k in c.lower() for k in keys)), 0)  # noqa: E731
        name_col = st.selectbox("Account name column", cols, index=guess(["account name", "account", "name"]))
        state_col = st.selectbox("State column", ["(none)", *cols], index=1 + guess(["state", "billing state"]))
        stage_col = st.selectbox("Stage column (optional)", ["(none)", *cols], index=0)
        matched = pl.match_to_ncua(sf, df, name_col, None if state_col == "(none)" else state_col)
        ok = matched["cu_number"].notna()
        st.write(f"Matched **{ok.sum()} / {len(matched)}** accounts to NCUA charters.")
        st.dataframe(matched[[name_col, "ncua_name", "match_score", "cu_number"]], hide_index=True, width="stretch")
        if st.button("Add matched accounts to pipeline"):
            for _, m in matched[ok].iterrows():
                if (pipe["cu_number"] == m["cu_number"]).any():
                    continue
                stage = m.get(stage_col) if stage_col != "(none)" else None
                pipe = pl.upsert(pipe, {"cu_number": m["cu_number"], "stage": stage if stage in pl.STAGES else "Target"})
            pl.save_pipeline(pipe, PRIVATE)
            st.success("Added. See the table above.")

# ---------- Territory ----------
with tab_terr:
    st.subheader("Territory at a glance")
    S = T.groupby("state").agg(
        CUs=("cu_number", "count"), Assets_B=("total_assets", lambda s: s.sum() / 1e9),
        Over_500M=("assets_m", lambda s: int((s >= 500).sum())), Over_1B=("assets_m", lambda s: int((s >= 1000).sum())),
        Est_rev_M=("expected_value", lambda s: s.sum() / 1e6),
    ).sort_values("Est_rev_M", ascending=False)
    st.dataframe(S.round(1), width="stretch")
    st.plotly_chart(px.bar(S.reset_index(), x="state", y="Est_rev_M", labels={"Est_rev_M": "Est. annual revenue pool ($M, placeholder pricing)"}, height=320),
                    width="stretch")
    mix = T["top_product"].map(PLABEL).value_counts()
    st.plotly_chart(px.pie(values=mix.values, names=mix.index, title="Top product across targets", height=360), width="stretch")
