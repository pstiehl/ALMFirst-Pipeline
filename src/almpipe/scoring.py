"""Product-fit scoring driven by config/products.yaml.

fit_<product>      0-100, how well the balance sheet matches the product
why_<product>      the reasons that fired, so the pitch is explainable
ev_<product>       fit/100 * estimated annual fee (placeholder pricing)
top_product        product with the highest expected value
expected_value     sum of ev_* across products (what the account is worth)
priority           0-100 rank of expected_value within the scored set
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def load_products(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())["products"]


def _test(v: pd.Series, op: str, value) -> pd.Series:
    if op == "gt":
        return v > value
    if op == "lt":
        return v < value
    if op == "between":
        lo, hi = value
        return (v >= lo) & (v < hi)
    raise ValueError(f"unknown op {op}")


def _fee(d: pd.DataFrame, fee: dict) -> pd.Series:
    basis = fee.get("basis", "flat")
    if basis == "flat":
        f = pd.Series(float(fee.get("min", 0)), index=d.index)
        s = fee.get("scale_with_assets")
        if s:
            f = (f + d["total_assets"] / 1e9 * s["per_billion"]).clip(upper=s["cap"])
        return f
    if basis == "assets":
        b = d["total_assets"]
    elif basis == "investments":
        b = d["total_investments"].fillna(0)
    elif basis == "discretionary_aum":
        # existing benefit-plan investments + CDA capacity (5% of net worth)
        b = d["employee_benefit_investments"].fillna(0) + 0.05 * d["net_worth"].clip(lower=0).fillna(0)
    else:
        raise ValueError(basis)
    return (b * fee["bps"] / 1e4).clip(lower=fee.get("min", 0), upper=fee.get("max", np.inf))


def score(d: pd.DataFrame, products: dict) -> pd.DataFrame:
    d = d.copy()
    ev_cols = []
    for key, p in products.items():
        g = p.get("gate", {})
        in_gate = d["assets_m"].between(g.get("min_assets_m", 0), g.get("max_assets_m", np.inf))
        pts = pd.Series(float(p.get("base", 0)), index=d.index)
        reasons = pd.Series([[] for _ in range(len(d))], index=d.index)
        for s in p.get("signals", []):
            col = d[s["metric"]] if s["metric"] in d else pd.Series(np.nan, index=d.index)
            hit = _test(col, s["op"], s["value"]).fillna(False).astype(bool)
            pts = pts + hit * s["points"]
            for i in hit[hit].index:
                reasons.at[i] = reasons.at[i] + [s["reason"]]
        fit = pts.clip(upper=100).where(in_gate, 0.0)
        d[f"fit_{key}"] = fit.round(0)
        d[f"why_{key}"] = reasons.where(in_gate, None).map(lambda r: "; ".join(r) if r else "")
        d[f"fee_{key}"] = _fee(d, p.get("fee", {"basis": "flat", "min": 0})).round(-2)
        d[f"ev_{key}"] = (fit / 100 * d[f"fee_{key}"]).round(-2)
        ev_cols.append(f"ev_{key}")
    ev = d[ev_cols]
    d["expected_value"] = ev.sum(axis=1)
    d["top_product"] = ev.idxmax(axis=1).str.removeprefix("ev_").where(ev.max(axis=1) > 0)
    d["top_product_label"] = d["top_product"].map({k: p["label"] for k, p in products.items()})
    return d


def add_priority(d: pd.DataFrame, mask: pd.Series | None = None) -> pd.DataFrame:
    """Priority 0-100 = percentile of expected value within `mask` (territory)."""
    d = d.copy()
    m = mask if mask is not None else pd.Series(True, index=d.index)
    d["priority"] = np.nan
    d.loc[m, "priority"] = (d.loc[m, "expected_value"].rank(pct=True) * 100).round(0)
    return d
