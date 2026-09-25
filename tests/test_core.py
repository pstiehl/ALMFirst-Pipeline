import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from almpipe import metrics, pipeline as pl  # noqa: E402
from almpipe.scoring import add_priority, load_products, score  # noqa: E402

PRODUCTS = load_products(ROOT / "config" / "products.yaml")


def _cu(**kw):
    base = dict(
        cu_number="1", name="TEST", city="TAMPA", state="FL", zip="33601", peer_group=6, cycle_date="2026-06-30",
        total_assets=1e9, total_loans=7e8, total_shares=8e8, cash_on_hand=1e6, cash_on_deposit=5e7,
        total_investments=2e8, investments_le_1y=2e7, investments_5_10y=5e7, investments_gt_10y=1e7,
        net_worth=1.1e8, net_income_ytd=4e6, members=90000, borrowings=0, re_loans=3e8,
        fixed_mtg_gt_15y=1e8, hybrid_mtg_gt_5y=0, afs_unrealized=-1e7, benefit_ins_collateral_csv=0,
        benefit_ins_endorse_csv=0, employees_ft=250, employees_pt=10,
    )
    base.update(kw)
    return base


def _frame(*rows):
    return metrics.add_ratios(pd.DataFrame([_cu(**r) for r in rows]))


def test_ratios():
    d = _frame({})
    r = d.iloc[0]
    assert r.loan_to_share == pytest.approx(0.875)
    assert r.nw_ratio == pytest.approx(0.11)
    assert r.roa == pytest.approx(0.008)  # 4M over 6 months, annualized
    assert r.long_asset_pct == pytest.approx(0.16)


def test_cpst_threshold():
    d = score(_frame({"total_assets": 12e9}, {"total_assets": 7e9, "cu_number": "2"}, {"total_assets": 1e9, "cu_number": "3"}), PRODUCTS)
    assert d.loc[0, "fit_cpst"] >= 90
    assert 60 <= d.loc[1, "fit_cpst"] < d.loc[0, "fit_cpst"]
    assert d.loc[2, "fit_cpst"] == 0  # outside the gate


def test_reasons_explain_score():
    d = score(_frame({"total_loans": 8e8, "total_shares": 8.2e8, "net_worth": 7e7}), PRODUCTS)
    why = d.loc[0, "why_alm_advisory"]
    assert "Loan-to-share >95%" in why and "Net worth ratio <8%" in why


def test_small_cu_gated_out():
    d = score(_frame({"total_assets": 40e6}), PRODUCTS)
    assert d.loc[0, "expected_value"] == 0
    assert pd.isna(d.loc[0, "top_product"])


def test_priority_within_mask():
    d = score(_frame({}, {"cu_number": "2", "total_assets": 5e9}), PRODUCTS)
    d = add_priority(d, pd.Series([True, True]))
    assert d.loc[1, "priority"] > d.loc[0, "priority"]


def test_name_match_and_today(tmp_path):
    cus = pd.DataFrame({"cu_number": ["10", "11"], "name": ["SUNCOAST", "VYSTAR"], "state": ["FL", "FL"]})
    sf = pd.DataFrame({"Account": ["Suncoast Credit Union", "VyStar Credit Union", "Nope FCU"], "St": ["FL", "FL", "FL"]})
    m = pl.match_to_ncua(sf, cus, "Account", "St")
    assert list(m["cu_number"][:2]) == ["10", "11"] and pd.isna(m["cu_number"][2])

    pipe = pl.upsert(pl.load_pipeline(tmp_path), {"cu_number": "11", "stage": "Contacted", "next_action_date": "2026-01-01"})
    pl.save_pipeline(pipe, tmp_path)
    assert len(pl.load_pipeline(tmp_path)) == 1
    targets = cus.assign(priority=[90, 10])
    t = pl.todays_list(targets, pipe, today=dt.date(2026, 9, 25))
    assert t.iloc[0]["cu_number"] == "11" and t.iloc[0]["bucket"] == "Due / overdue"
