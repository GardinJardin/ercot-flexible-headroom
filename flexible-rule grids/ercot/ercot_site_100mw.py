import os
import sys

import numpy as np
import pandas as pd

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(here)), "prediction scripts", "v1"))
from erco_capacity import TEXAS, REAL_ONLY, capacity  # noqa: E402  (same capacity as prediction v1)

# Switch-off for ONE 100 MW flexible site in ERCOT, every full forecast year (copy of Task C,
# prediction scripts/erco_switchoff_100mw.py, on the flexible-rule split).
# Demand = ERCOT forecast minus officer-letter loads = normal grid + contracted big loads (ercot_split_forecast.py files).
# Queue assumption (open question, library/ignorance-ledger.md 2026-10-13): our site sits BEHIND every contracted big load
# (they stay as firm demand) and AHEAD of every officer-letter load (assumed curtailed first, or never built). Roughly a
# signing-date line; how ERCOT actually orders curtailment among flexible loads under SB 6 is unverified.
# Cap per hour = capacity(year, month, hour-ending) from prediction scripts/v1/erco_capacity.py.
# cut_t = max(0, D_t + 100 - cap_t), capped at 100 (hours already over the cap: the site is fully off).
# Curtailment rate = sum(cut) / (100 * hours in year). Each row is one hour, so MW summed = MWh.
# Forecast caveats (prediction_v1_assumptions.md): hour order is fake (2008 calendar), so no longest-event number; hourly
# values average 17 weather years, so peaks are milder than real ones and every cut number here is a FLOOR, until extreme
# events are overlaid on the forecast or handled some other way.
SITE_MW = 100

files = {k: pd.read_csv(os.path.join(here, f"ERCO_forecast_{k}.csv"), parse_dates=["period"])
         for k in ["base", "bigloads", "officer_letters"]}
if not all((files[k]["period"] == files["base"]["period"]).all() for k in files):
    raise SystemExit("Forecast files don't share the same hours; rerun ercot_split_forecast.py.")
df = files["base"][["period"]].copy()
df["contracts"] = files["bigloads"]["value"] - files["officer_letters"]["value"]
df["value"] = files["base"]["value"] + df["contracts"]  # = ercot_net - ercot_officer_letters
df["local"] = df["period"].dt.tz_convert(TEXAS)
# period is the END of the hour: local 00:00 is hour-ending 24 of the previous day, so month/year come from the hour's start
start = df["local"] - pd.Timedelta(hours=1)
he = df["local"].dt.hour.replace(0, 24)
df["cap"] = [capacity(y, m, h) for y, m, h in zip(start.dt.year, start.dt.month, he)]
df["year"] = df["local"].dt.year
df["cut"] = np.clip(df["value"] + SITE_MW - df["cap"], 0, SITE_MW)  # MW switched off each hour

print(f"Site {SITE_MW} MW, behind contracts / ahead of officer letters. REAL_ONLY = {REAL_ONLY}")
rows = []
for year, d in df.groupby("year"):
    if len(d) < 8000:  # partial edge year (the forecast ends 2045-01-01 00:00 Texas time)
        continue
    rows.append({"year": year, "hours_cut": int((d["cut"] > 0).sum()), "hours_fully_off": int((d["cut"] >= SITE_MW).sum()),
                 "max_mw": round(d["cut"].max(), 1), "total_mwh": round(d["cut"].sum()),
                 "rate_%": round(d["cut"].sum() / (SITE_MW * len(d)) * 100, 3),
                 "contracts_avg_GW": round(d["contracts"].mean() / 1000, 1)})
print(pd.DataFrame(rows).to_string(index=False))
