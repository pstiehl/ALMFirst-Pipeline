"""Balance-sheet ratios derived from 5300 fields.

All ratios are fractions (0.12 = 12%). Growth uses the year-ago quarter so
seasonality does not create false signals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    return (a / b.replace(0, np.nan)).astype(float)


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    month = pd.to_datetime(d["cycle_date"], errors="coerce").dt.month.fillna(12)
    A = d["total_assets"]
    z = lambda c: d[c].fillna(0)  # noqa: E731

    d["assets_m"] = A / 1e6
    d["loan_to_share"] = _div(d["total_loans"], d["total_shares"])
    d["nw_ratio"] = _div(d["net_worth"], A)
    d["roa"] = _div(d["net_income_ytd"] * 12 / month, A)
    d["cash"] = z("cash_on_hand") + z("cash_on_deposit")
    d["cash_pct"] = _div(d["cash"], A)
    d["inv_pct"] = _div(d["total_investments"], A)
    d["liquid_pct"] = _div(z("cash") + z("investments_le_1y"), A)
    d["long_asset_pct"] = _div(
        z("fixed_mtg_gt_15y") + z("hybrid_mtg_gt_5y") + z("investments_5_10y") + z("investments_gt_10y"), A
    )
    d["mortgage_pct"] = _div(d["re_loans"], A)
    d["borrow_pct"] = _div(z("borrowings"), A)
    d["afs_loss_to_nw"] = _div(-z("afs_unrealized"), d["net_worth"])
    d["employee_benefit_investments"] = z("benefit_ins_collateral_csv") + z("benefit_ins_endorse_csv")
    d["emp_benefit_m"] = d["employee_benefit_investments"] / 1e6
    d["employees"] = z("employees_ft") + z("employees_pt") * 0.5
    return d


def add_growth(cur: pd.DataFrame, prior: pd.DataFrame | None) -> pd.DataFrame:
    d = cur.copy()
    cols = {"total_assets": "asset_growth_yoy", "total_shares": "share_growth_yoy", "total_loans": "loan_growth_yoy"}
    if prior is None or prior.empty:
        for c in cols.values():
            d[c] = np.nan
        return d
    p = prior.set_index("cu_number")[list(cols)]
    j = d.set_index("cu_number")
    for src, dst in cols.items():
        j[dst] = _div(j[src], p[src].reindex(j.index)) - 1
    return j.reset_index()


def add_peer_percentiles(d: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Percentile (0-100) of each metric within the NCUA peer group, nationally."""
    d = d.copy()
    for m in metrics:
        d[f"{m}_pctl"] = d.groupby("peer_group")[m].rank(pct=True) * 100
    return d
