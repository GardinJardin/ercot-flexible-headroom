import os
import re
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

URL = "https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/data/"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "subregions")
LOOKBACK_HOURS = 4800
# Subregion -> BA table, two columns: subba, ba (one row per subregion).
# Built from the EIA facet endpoint (SUBBA_URL); see build_lookup.
LOOKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "subregion_lookup.csv")


def collect_subregion(subregion, start, end):
    try:
        subregion = match_code(subregion)
    except KeyError as e:
        print(f'collect_subregion("{subregion}") stopped: {e.args[0]}')
        return
    rows = []
    total = None
    offset = 0
    while total is None or len(rows) < total:
        params = {
            "api_key": os.environ["API_KEY"],
            "frequency": "hourly",
            "data[0]": "value",
            "facets[subba][]": subregion,
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": offset,
            "length": 5000,
        }
        details = f"subregion={subregion}, start={start}, end={end}, offset={offset}"
        for wait in range(0, 110, 10):  # 11 attempts: waits 0, 10, ... 100s (~9 min total)
            time.sleep(wait)
            r = requests.get(URL, params=params)
            time.sleep(1)
            text = r.text.lower()
            throttled = r.status_code == 429 or "rate limit" in text or "rate_limit" in text
            if not throttled:
                break
        body = r.text.replace(os.environ["API_KEY"], "***")[:500]
        if throttled:
            raise RuntimeError(f"EIA API throttled after 11 attempts over ~9 min ({details}): {body}")
        if r.status_code != 200:
            raise RuntimeError(f"EIA API error HTTP {r.status_code} ({details}): {body}")
        response = r.json()["response"]
        total = int(response["total"])
        if total == 0:
            raise ValueError(f"EIA returned no rows ({details}, total=0)")
        page = response["data"]
        if not page:
            raise ValueError(f"EIA returned an empty page before reaching total ({details}, total={total}, rows so far={len(rows)})")
        rows.extend(page)
        offset += 5000

    df = pd.DataFrame(rows, columns=["period", "value", "subba", "parent"])
    df["period"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
    df["value"] = df["value"].astype(float)
    df = df.sort_values("period").reset_index(drop=True)
    save_subregion(df)
    return df


def save_subregion(df):
    if df.empty:
        raise ValueError("No data to save: EIA returned no rows for this subregion in that range")
    codes = df["subba"].unique()
    if len(codes) != 1:
        raise ValueError(f"Expected exactly one subba code, got {list(codes)}")
    code = codes[0]
    # Duplicate hours: blank copies lose to a non-blank copy, then one copy per hour is kept at random.
    df = df[~(df["value"].isna() & df["period"].isin(df.loc[df["value"].notna(), "period"]))]
    df = df.sample(frac=1).drop_duplicates("period")
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{code}.parquet")
    if not os.path.exists(path):
        df.sort_values("period").reset_index(drop=True).to_parquet(path)
        print(f"{code}: new file, {len(df)} rows saved")
        return
    stored = pd.read_parquet(path)
    # A blank (NaN) from EIA never overwrites a stored hour; a blank for a new hour is kept.
    df = df[~(df["value"].isna() & df["period"].isin(stored["period"]))]
    overlap = stored["period"].isin(df["period"])
    replaced = int(overlap.sum())
    added = len(df) - replaced
    merged = pd.concat([stored[~overlap], df]).sort_values("period").reset_index(drop=True)
    merged.to_parquet(path)
    print(f"{code}: {replaced} rows replaced, {added} added")


def load_subregion(subba, now, ask=True):
    try:
        subba = match_code(subba)
    except KeyError as e:
        print(f'load_subregion("{subba}") stopped: {e.args[0]}')
        return
    # Find the file by case-insensitive name ("dom.parquet" counts as DOM).
    files = os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else []
    found = [f for f in files if f.endswith(".parquet") and f[:-len(".parquet")].lower() == subba.lower()]
    if len(found) > 1:
        print(f'load_subregion("{subba}") stopped: multiple files match {subba}: {found}')
        return
    if found:
        return pd.read_parquet(os.path.join(DATA_DIR, found[0]))
    path = os.path.join(DATA_DIR, f"{subba}.parquet")
    if ask:
        answer = input(f"No stored data for {subba}. Pull it from EIA now? (y/n): ")
        if answer != "y":
            raise FileNotFoundError(f"No data stored for {subba}")
    start = (pd.to_datetime(now, format="%Y-%m-%dT%H", utc=True) - pd.DateOffset(years=15)).strftime("%Y-%m-%dT%H")
    collect_subregion(subba, start, now)
    return pd.read_parquet(path)


def update_subregion(subba, now):
    try:
        subba = match_code(subba)
    except KeyError as e:
        print(f'update_subregion("{subba}") stopped: {e.args[0]}')
        return
    stored = load_subregion(subba, now, ask=False)
    last = stored["period"].max()
    start = (last - pd.Timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H")
    collect_subregion(subba, start, now)
    merged = load_subregion(subba, now, ask=False)
    window = merged["period"].between(
        pd.to_datetime(start, format="%Y-%m-%dT%H", utc=True),
        pd.to_datetime(now, format="%Y-%m-%dT%H", utc=True),
    )
    return merged[window].reset_index(drop=True)


SUBBA_URL = "https://api.eia.gov/v2/electricity/rto/region-sub-ba-data/facet/subba/"
_lookup = None


def build_lookup():
    # The lookup lives in LOOKUP_PATH and is rebuilt from EIA only when that
    # file is missing (delete it to refresh). Read every column as a string so
    # codes like "0001" keep leading zeros and "Frep" stays case-exact.
    if os.path.exists(LOOKUP_PATH):
        table = pd.read_csv(LOOKUP_PATH, dtype=str, keep_default_na=False)
    else:
        # Each facet has an id (subregion code) and an alias
        # "PARENT: (CODE) Name"; the parent BA is parsed from the alias.
        r = requests.get(SUBBA_URL, params={"api_key": os.environ["API_KEY"]})
        if r.status_code != 200:
            raise RuntimeError(f"EIA API error: HTTP {r.status_code}")
        rows = []
        for facet in r.json()["response"]["facets"]:
            match = re.fullmatch(r"([^:]+): \(([^)]+)\) .+", facet["alias"])
            if match is None or match.group(2) != facet["id"]:
                raise ValueError(f"Unexpected alias for {facet['id']}: {facet['alias']}")
            rows.append((match.group(2), match.group(1)))
        table = pd.DataFrame(rows, columns=["subba", "ba"])
        os.makedirs(os.path.dirname(LOOKUP_PATH), exist_ok=True)
        table.to_csv(LOOKUP_PATH, index=False)
    sub_to_ba = {}
    ba_to_subs = {}
    for code, ba in zip(table["subba"], table["ba"]):
        sub_to_ba[code] = ba
        ba_to_subs.setdefault(ba, []).append(code)
    return sub_to_ba, ba_to_subs


def _get_lookup():
    global _lookup
    if _lookup is None:
        _lookup = build_lookup()
    return _lookup


def match_code(subba):
    # Case-insensitive match against the lookup; returns EIA's exact code ("dom" -> "DOM").
    matches = [code for code in _get_lookup()[0] if code.lower() == subba.lower()]
    if not matches:
        raise KeyError(f"Unknown subregion: {subba}")
    if len(matches) > 1:
        raise KeyError(f"Ambiguous subregion: {subba} matches {matches}")
    return matches[0]


def match_ba(ba):
    # Case-insensitive match against the lookup; returns EIA's exact BA code ("pjm" -> "PJM").
    matches = [code for code in _get_lookup()[1] if code.lower() == ba.lower()]
    if not matches:
        raise KeyError(f"Unknown BA: {ba}")
    if len(matches) > 1:
        raise KeyError(f"Ambiguous BA: {ba} matches {matches}")
    return matches[0]


def get_ba(subba):
    sub_to_ba = _get_lookup()[0]
    if subba not in sub_to_ba:
        raise KeyError(f"Unknown subregion: {subba}")
    return sub_to_ba[subba]


def get_subregions(ba):
    ba_to_subs = _get_lookup()[1]
    if ba not in ba_to_subs:
        raise KeyError(f"Unknown BA: {ba}")
    return list(ba_to_subs[ba])


def ba_total(ba, now):
    try:
        ba = match_ba(ba)
    except KeyError as e:
        print(f'ba_total("{ba}") stopped: {e.args[0]}')
        return
    codes = get_subregions(ba)
    frames = []
    for code in codes:
        frames.append(load_subregion(code, now, ask=False))
    df = pd.concat(frames).groupby("period", as_index=False)["value"].sum(min_count=1)
    df["value"] = df["value"].astype(float)
    df["ba"] = ba
    df = df.sort_values("period").reset_index(drop=True)
    return df


def backfill(ba, start, end):
    for code in get_subregions(ba):
        try:
            if os.path.exists(os.path.join(DATA_DIR, f"{code}.parquet")):
                update_subregion(code, end)
            else:
                collect_subregion(code, start, end)
        except Exception as e:
            message = str(e)
            key = os.environ.get("API_KEY")
            if key:
                message = message.replace(key, "***")
            print(f"{code}: error - {message}")


def backfill_all(start, end):
    for ba in _get_lookup()[1]:
        backfill(ba, start, end)
