#!/usr/bin/env python3
"""Build data/processed/credit_unions.csv.gz from public NCUA + Census data.

    python scripts/build_data.py                 # newest published quarter
    python scripts/build_data.py --quarter 2026-06

Keeps every US credit union (national peer comparisons); the app filters to
the territory in config/territory.yaml. Raw zips cache in data/raw/ (ignored).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from almpipe import geo, metrics, ncua  # noqa: E402
from almpipe.scoring import load_products, score  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "credit_unions.csv.gz"
PCTL = ["loan_to_share", "nw_ratio", "roa", "long_asset_pct", "liquid_pct", "inv_pct", "share_growth_yoy"]


def year_ago(q: str) -> str:
    return f"{int(q[:4]) - 1}{q[4:]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", help="YYYY-MM (03/06/09/12). Default: newest available")
    a = ap.parse_args()

    q = a.quarter or ncua.latest_available_quarter(RAW)
    print(f"quarter {q}")
    cur = ncua.load_quarter(ncua.download_quarter(q, RAW))
    try:
        prior = ncua.load_quarter(ncua.download_quarter(year_ago(q), RAW))
        print(f"year-ago {year_ago(q)}: {len(prior)} CUs")
    except Exception as e:  # growth columns become NaN
        print(f"year-ago quarter unavailable ({e}); growth metrics blank")
        prior = None

    d = metrics.add_ratios(cur)
    d = metrics.add_growth(d, prior)
    d = metrics.add_peer_percentiles(d, PCTL)
    d = geo.geocode(d, geo.load_zcta(RAW), geo.load_places(RAW))
    d = score(d, load_products(ROOT / "config" / "products.yaml"))
    d["quarter"] = q

    OUT.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT, index=False, compression="gzip")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(d)} credit unions, "
          f"geocoded by zip {int((d.geo_source == 'zip').sum())}, city {int((d.geo_source == 'city').sum())}, "
          f"place {int((d.geo_source == 'place').sum())}, state {int((d.geo_source == 'state').sum())}")


if __name__ == "__main__":
    main()
