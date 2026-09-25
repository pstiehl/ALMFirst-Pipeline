"""Download and parse NCUA quarterly 5300 Call Report bulk data.

Source: https://ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data
Each quarter is one zip with FOICU.txt (profile: name, address, peer group)
and FS220*.txt (financial accounts). Account codes are documented in
AcctDesc.txt inside the zip.

Dollar amounts are in whole dollars. Income accounts are year-to-date.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = "https://ncua.gov/files/publications/analysis/call-report-data-{q}.zip"
UA = {"User-Agent": "Mozilla/5.0 (ALMFirst-Pipeline research script)"}

# friendly name -> 5300 account code. Add fields here; the loader finds
# whichever FS220*.txt file carries each column.
ACCOUNTS = {
    # NCUA re-coded parts of the 5300 in 2022 (CECL/"AS", "NV", "RL" codes).
    # Legacy codes like 703/704A/799D/945/789A are still in the headers but blank.
    "total_assets": "ACCT_010",
    "total_loans": "ACCT_025B",
    "total_shares": "ACCT_018",
    "cash_on_hand": "ACCT_730A",
    "cash_on_deposit": "ACCT_730B",
    "total_investments": "ACCT_NV0158",   # total investment securities
    "investments_le_1y": "ACCT_NV0153",
    "investments_5_10y": "ACCT_NV0156",
    "investments_gt_10y": "ACCT_NV0157",
    "net_worth": "ACCT_997",
    "net_income_ytd": "ACCT_661A",
    "members": "ACCT_083",
    "borrowings": "ACCT_860C",
    "re_loans": "ACCT_RL0047",           # all 1-4 family + consumer real estate
    "fixed_mtg_gt_15y": "ACCT_RL0002",
    "hybrid_mtg_gt_5y": "ACCT_RL0008",
    "afs_unrealized": "ACCT_EQ0009",
    "benefit_ins_collateral_csv": "ACCT_NV0170",  # split-dollar / benefit funding
    "benefit_ins_endorse_csv": "ACCT_NV0173",
    "employees_ft": "ACCT_564A",
    "employees_pt": "ACCT_564B",
}

PROFILE_COLS = {
    "CU_NUMBER": "cu_number",
    "CU_NAME": "name",
    "STREET": "street",
    "CITY": "city",
    "STATE": "state",
    "ZIP_CODE": "zip",
    "CU_TYPE": "cu_type",  # 1 = federal, 2 = state chartered
    "Peer_Group": "peer_group",
    "CYCLE_DATE": "cycle_date",
    "YEAR_OPENED": "year_opened",
    "IsMDI": "is_mdi",
}


def download_quarter(quarter: str, raw_dir: Path) -> Path:
    """quarter like '2026-06'. Caches the zip under raw_dir."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"call-report-data-{quarter}.zip"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    req = urllib.request.Request(URL.format(q=quarter), headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if not data.startswith(b"PK"):
        raise RuntimeError(f"NCUA quarter {quarter} not available (not a zip)")
    dest.write_bytes(data)
    return dest


def latest_available_quarter(raw_dir: Path, start: str | None = None, tries: int = 6) -> str:
    """Walk back from `start` (or today) to the newest published quarter."""
    import datetime as dt

    d = dt.date.today() if start is None else dt.date(int(start[:4]), int(start[5:7]), 1)
    y, m = d.year, ((d.month - 1) // 3) * 3 + 3
    if m > d.month:
        m -= 3
    for _ in range(tries):
        if m <= 0:
            y, m = y - 1, m + 12
        q = f"{y}-{m:02d}"
        try:
            download_quarter(q, raw_dir)
            return q
        except Exception:
            m -= 3
    raise RuntimeError("No NCUA quarter found in the last %d quarters" % tries)


def _read(z: zipfile.ZipFile, name: str, usecols=None) -> pd.DataFrame:
    with z.open(name) as f:
        return pd.read_csv(
            io.TextIOWrapper(f, encoding="latin-1"),
            usecols=usecols,
            dtype=str,
            low_memory=False,
        )


def load_quarter(zip_path: Path) -> pd.DataFrame:
    """One row per credit union: profile + the ACCOUNTS fields (float $)."""
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    prof = _read(z, "FOICU.txt", usecols=lambda c: c in PROFILE_COLS)
    prof = prof.rename(columns=PROFILE_COLS)

    wanted = {v.upper(): k for k, v in ACCOUNTS.items()}
    out = prof.set_index("cu_number")
    found: set[str] = set()
    for n in sorted(x for x in names if x.upper().startswith("FS220") and x.endswith(".txt")):
        with z.open(n) as f:
            header = f.readline().decode("latin-1").strip().replace('"', "").split(",")
        cols = [c for c in header if c.upper() in wanted and c.upper() not in found]
        if not cols:
            continue
        keep = {c.upper() for c in cols} | {"CU_NUMBER"}
        df = _read(z, n, usecols=lambda c: c.upper() in keep)
        df = df.rename(columns={c: "CU_NUMBER" for c in df.columns if c.upper() == "CU_NUMBER"}).set_index("CU_NUMBER")
        df = df.rename(columns={c: wanted[c.upper()] for c in cols})
        df = df.apply(pd.to_numeric, errors="coerce")
        out = out.join(df, how="left")
        found.update(c.upper() for c in cols)
    missing = set(wanted) - found
    for code in missing:
        out[wanted[code]] = float("nan")
    out = out.reset_index().rename(columns={"index": "cu_number"})
    out["cycle_date"] = pd.to_datetime(out["cycle_date"], errors="coerce").dt.date.astype(str)
    out["zip"] = out["zip"].astype(str).str.extract(r"(\d{5})")[0]
    return out
