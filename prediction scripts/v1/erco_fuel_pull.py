import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

# Pulls EIA-930 hourly net generation by fuel for ERCOT (respondent ERCO) from EIA API v2 and saves it raw to
# data/ERCO_fuel.parquet: `period` (UTC, END of hour, project convention), `fueltype` (COL, NG, NUC, OTH, SUN, WAT,
# WND, BAT), `value` (MW; BAT is negative while batteries charge). Used to measure solar/wind/other capacity factors.
# Range: EIA's first ERCO fuel hour is 2019-01-01T00 (checked 2026-10-13: nothing earlier exists) to END = the current
# UTC hour, so the pull covers everything EIA has. Pulled one calendar year (UTC) at a time, paging by offset inside each
# year: one long offset walk fails, because EIA answers HTTP 503 after ~40 s for offsets past ~374,000 (seen twice,
# 2026-10-13; the same rows by date window come back fine). ~105 calls of 5,000 rows; same throttle-retry and
# error handling as collect_subregion in eia_pipeline.py (copied, not imported). No cleaning: EIA's values as given.
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project folder: v1 -> prediction scripts -> project
load_dotenv(os.path.join(root, ".env"))
URL = "https://api.eia.gov/v2/electricity/rto/fuel-type-data/data/"
OUT = os.path.join(root, "data", "ERCO_fuel.parquet")
FIRST_YEAR = 2019
END = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H")

rows = []
for year in range(FIRST_YEAR, int(END[:4]) + 1):
    start = f"{year}-01-01T00"
    end = min(f"{year}-12-31T23", END)
    total = None
    offset = 0
    year_rows = 0
    while total is None or year_rows < total:
        params = {
            "api_key": os.environ["API_KEY"],
            "frequency": "hourly",
            "data[0]": "value",
            "facets[respondent][]": "ERCO",
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": offset,
            "length": 5000,
        }
        details = f"respondent=ERCO, start={start}, end={end}, offset={offset}"
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
            raise ValueError(f"EIA returned an empty page before reaching total ({details}, total={total}, rows so far={year_rows})")
        rows.extend(page)
        year_rows += len(page)
        offset += 5000
        print(f"{year}: {year_rows:,} / {total:,} rows", flush=True)

df = pd.DataFrame(rows, columns=["period", "fueltype", "value"])
df["period"] = pd.to_datetime(df["period"], format="%Y-%m-%dT%H", utc=True)
df["fueltype"] = df["fueltype"].astype(str)
df["value"] = df["value"].astype(float)
df = df.sort_values(["period", "fueltype"]).reset_index(drop=True)
df.to_parquet(OUT)
print(f"saved {OUT}: {len(df):,} rows, {df['period'].min()} -> {df['period'].max()}")

# Data-quality report.
all_hours = pd.date_range(df["period"].min(), df["period"].max(), freq="h")
print(f"Duplicate (hour, fuel) rows: {df.duplicated(['period', 'fueltype']).sum()}")
print(f"Hours absent for every fuel: {len(all_hours.difference(df['period']))}")
for fuel, g in df.groupby("fueltype"):
    span = pd.date_range(g["period"].min(), g["period"].max(), freq="h")
    print(f"{fuel}: {len(g):,} rows, {g['period'].min()} -> {g['period'].max()}, "
          f"missing hours in its span {len(span.difference(g['period']))}, blanks {g['value'].isna().sum()}, "
          f"zeros {(g['value'] == 0).sum()}, negatives {(g['value'] < 0).sum()}")
