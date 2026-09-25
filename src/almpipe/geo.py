"""ZIP -> lat/lon using the free Census ZCTA gazetteer (no API key, no rate limit).

Credit unions whose ZIP is not a ZCTA (PO-box ZIPs) fall back to the Census
place (city) centroid, then the average of other CUs in the same city, then
the state centroid. Good enough for a territory map; not for driving directions.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

GAZ_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"
PLACE_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip"
_LSAD = r"\s+(city|town|village|cdp|borough|municipality|city and borough|urban county|metropolitan government.*|consolidated government.*|unified government.*|\(balance\))$"


def _fetch_txt(url: str, raw_dir: Path, **kw) -> pd.DataFrame:
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / url.rsplit("/", 1)[1]
    if not dest.exists():
        with urllib.request.urlopen(url, timeout=120) as r:
            dest.write_bytes(r.read())
    z = zipfile.ZipFile(dest)
    name = [n for n in z.namelist() if n.endswith(".txt")][0]
    with z.open(name) as f:
        g = pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep="\t", **kw)
    g.columns = [c.strip() for c in g.columns]
    return g


def load_places(raw_dir: Path) -> pd.DataFrame:
    g = _fetch_txt(PLACE_URL, raw_dir, dtype=str)
    city = g["NAME"].str.lower()
    for _ in range(2):
        city = city.str.replace(_LSAD, "", regex=True)
    g = g.assign(city_key=city.str.replace(r"[^a-z ]", "", regex=True).str.strip(), state=g["USPS"])
    g["lat"] = g["INTPTLAT"].astype(float)
    g["lon"] = g["INTPTLONG"].astype(float)
    # keep the largest place when a name repeats within a state
    g["ALAND"] = g["ALAND"].astype(float)
    g = g.sort_values("ALAND", ascending=False).drop_duplicates(["state", "city_key"])
    return g[["state", "city_key", "lat", "lon"]]


def load_zcta(raw_dir: Path) -> pd.DataFrame:
    g = _fetch_txt(GAZ_URL, raw_dir, dtype={"GEOID": str})
    return g.rename(columns={"GEOID": "zip", "INTPTLAT": "lat", "INTPTLONG": "lon"})[["zip", "lat", "lon"]]


def geocode(df: pd.DataFrame, zcta: pd.DataFrame, places: pd.DataFrame | None = None) -> pd.DataFrame:
    d = df.merge(zcta, on="zip", how="left")
    d["geo_source"] = d["lat"].notna().map({True: "zip", False: None})
    if places is not None:
        key = d["city"].str.lower().str.replace(r"[^a-z ]", "", regex=True).str.strip()
        pl = d[["state"]].assign(city_key=key).merge(places, on=["state", "city_key"], how="left")
        pl.index = d.index
        m = d["lat"].isna() & pl["lat"].notna()
        d.loc[m, ["lat", "lon"]] = pl.loc[m, ["lat", "lon"]].values
        d.loc[m, "geo_source"] = "place"
    city = d.groupby(["state", "city"])[["lat", "lon"]].transform("mean")
    m = d["lat"].isna() & city["lat"].notna()
    d.loc[m, ["lat", "lon"]] = city.loc[m, ["lat", "lon"]].values
    d.loc[m, "geo_source"] = "city"
    st = d.groupby("state")[["lat", "lon"]].transform("mean")
    m = d["lat"].isna() & st["lat"].notna()
    d.loc[m, ["lat", "lon"]] = st.loc[m, ["lat", "lon"]].values
    d.loc[m, "geo_source"] = "state"
    return d
