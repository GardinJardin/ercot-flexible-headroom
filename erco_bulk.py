import os

import pandas as pd

# EIA-930 bulk six-month files (BA level, every BA in one file), 2016-2024.
# Source: https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_<YYYY>_<Jan_Jun|Jul_Dec>.csv
RAW_DIR = "/private/tmp/claude-502/-Users-AaryanJain-rick-prime/11650163-266b-4e9f-80c6-7e2df94142da/scratchpad/eia930_bulk"
YEARS = range(2016, 2025)

frames = []
for y in YEARS:
    for half in ["Jan_Jun", "Jul_Dec"]:
        f = os.path.join(RAW_DIR, f"EIA930_BALANCE_{y}_{half}.csv")
        raw = pd.read_csv(f, usecols=["Balancing Authority", "UTC Time at End of Hour", "Demand (MW)",
                                      "Demand (MW) (Adjusted)"], thousands=",", low_memory=False)
        raw = raw[raw["Balancing Authority"] == "ERCO"]
        frames.append(raw)
df = pd.concat(frames)

# period = UTC end of hour, same convention as the API files.
df["period"] = pd.to_datetime(df["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p").dt.tz_localize("UTC")
# Duke: adjusted demand where it exists, otherwise demand.
df["value"] = df["Demand (MW) (Adjusted)"].fillna(df["Demand (MW)"]).astype(float)
print(f"{len(df):,} rows, {df['period'].duplicated().sum()} duplicate hours, "
      f"{df['Demand (MW) (Adjusted)'].isna().sum()} blank adjusted (demand used), {df['value'].isna().sum()} blank both")
df = df.drop_duplicates("period").set_index("period")["value"].sort_index()

# Same cleaning rule as erco_total.py, on the one ERCO series.
# Blank or zero -> straight line between the nearest good values (step = diff / (bad hours + 1));
# edge runs left as is. A bad run whose neighbours straddle absent hours gets the mean of good values,
# 6 months before to 6 months after.
s = df
filled = s.where(s != 0).interpolate(method="time", limit_area="inside").fillna(s)
hours = s.index
bad = (s.isna() | (s == 0)).tolist()
i = 0
while i < len(bad):
    if not bad[i]:
        i += 1
        continue
    j = i
    while j + 1 < len(bad) and bad[j + 1]:
        j += 1
    if i > 0 and j + 1 < len(bad):
        before, after = hours[i - 1], hours[j + 1]
        if after - before > pd.Timedelta(hours=j - i + 2):
            window = s[hours[i] - pd.DateOffset(months=6):hours[j] + pd.DateOffset(months=6)]
            filled.iloc[i:j + 1] = window[window != 0].mean()
    i = j + 1
print(f"{((s.isna() | (s == 0)) & filled.notna() & (filled != 0)).sum()} values filled")

expected = pd.date_range(filled.index.min(), filled.index.max(), freq="h")  # files run on Texas dates
print(f"{filled.index.min()} -> {filled.index.max()}, {len(filled):,} hours, "
      f"{len(expected.difference(filled.index))} absent of {len(expected):,} expected")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ba_totals", "ERCO_bulk.csv")
filled.rename("value").rename_axis("period").reset_index().to_csv(out, index=False)
print(f"saved {out}")
