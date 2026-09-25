"""Local pipeline + Salesforce import.

Everything here reads/writes data/private/, which is git-ignored. Contact
names, emails and phones never enter the repo. Salesforce stays the system
of record; this layer only adds "who next, why, what to pitch".
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
from pathlib import Path

import pandas as pd

STAGES = ["Target", "Researching", "Contacted", "Meeting set", "Proposal", "Negotiating", "Won", "Lost", "Not a fit"]
OPEN_STAGES = STAGES[:6]
PIPE_COLS = ["cu_number", "stage", "product", "next_action", "next_action_date", "last_touch", "notes"]

_STOP = r"\b(federal|credit|union|fcu|cu|community|inc|the|of|and)\b"


def norm_name(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    s = re.sub(_STOP, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_pipeline(private_dir: Path) -> pd.DataFrame:
    p = private_dir / "pipeline.csv"
    if not p.exists():
        return pd.DataFrame(columns=PIPE_COLS)
    df = pd.read_csv(p, dtype={"cu_number": str})
    for c in PIPE_COLS:
        if c not in df:
            df[c] = None
    return df[PIPE_COLS]


def save_pipeline(df: pd.DataFrame, private_dir: Path) -> None:
    private_dir.mkdir(parents=True, exist_ok=True)
    df[PIPE_COLS].to_csv(private_dir / "pipeline.csv", index=False)


def upsert(df: pd.DataFrame, row: dict) -> pd.DataFrame:
    row = {c: row.get(c) for c in PIPE_COLS}
    row["cu_number"] = str(row["cu_number"])
    df = df[df["cu_number"].astype(str) != row["cu_number"]]
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def load_clients(private_dir: Path) -> set[str]:
    """data/private/clients.csv with a `cu_number` or `name`+`state` column."""
    p = private_dir / "clients.csv"
    return set(pd.read_csv(p, dtype=str)["cu_number"].dropna()) if p.exists() else set()


def match_to_ncua(sf: pd.DataFrame, cus: pd.DataFrame, name_col: str, state_col: str | None, cutoff: float = 0.85) -> pd.DataFrame:
    """Attach cu_number to each Salesforce row by fuzzy name (+ state) match."""
    cus = cus.assign(_n=cus["name"].map(norm_name))
    out = sf.copy()
    nums, scores, matched = [], [], []
    for _, r in sf.iterrows():
        pool = cus
        if state_col and pd.notna(r.get(state_col)):
            pool = cus[cus["state"] == str(r[state_col]).strip().upper()[:2]]
        n = norm_name(r[name_col])
        exact = pool[pool["_n"] == n]
        if len(exact) == 1:
            nums.append(exact.iloc[0]["cu_number"]); scores.append(1.0); matched.append(exact.iloc[0]["name"]); continue
        best = difflib.get_close_matches(n, pool["_n"].tolist(), n=1, cutoff=cutoff)
        if best:
            hit = pool[pool["_n"] == best[0]].iloc[0]
            nums.append(hit["cu_number"]); matched.append(hit["name"])
            scores.append(round(difflib.SequenceMatcher(None, n, best[0]).ratio(), 2))
        else:
            nums.append(None); scores.append(0.0); matched.append(None)
    out["cu_number"], out["match_score"], out["ncua_name"] = nums, scores, matched
    return out


def todays_list(targets: pd.DataFrame, pipe: pd.DataFrame, today: dt.date | None = None, n: int = 25) -> pd.DataFrame:
    """Overdue/due follow-ups first, then highest-priority untouched targets."""
    today = today or dt.date.today()
    t = targets.merge(pipe, on="cu_number", how="left")
    t["stage"] = t["stage"].fillna("Target")
    t = t[t["stage"].isin(OPEN_STAGES)]
    due = pd.to_datetime(t["next_action_date"], errors="coerce")
    now = pd.Timestamp(today)
    t["bucket"] = "New target"
    t.loc[due.notna() & (due <= now), "bucket"] = "Due / overdue"
    t.loc[due.notna() & (due > now), "bucket"] = "Scheduled"
    order = {"Due / overdue": 0, "New target": 1, "Scheduled": 2}
    t["_o"] = t["bucket"].map(order)
    t["_d"] = due
    t = t[t["bucket"] != "Scheduled"].sort_values(["_o", "_d", "priority"], ascending=[True, True, False])
    return t.drop(columns=["_o", "_d"]).head(n)
