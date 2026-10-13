import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import root_scalar

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(here)), "prediction scripts", "v1"))
from erco_capacity import TEXAS, REAL_ONLY, capacity, load_caps  # noqa: E402  (same capacity as prediction v1)

# Headroom for ERCOT's big flexible loads, all forecast years in one table.
# Same method as prediction scripts/v1/erco_headroom_forecast.py, but demand = ERCOT's forecast MINUS its big new loads
# (contracts + officer letters; split by ercot_split_forecast.py). Headroom = how much big flexible load ERCOT can absorb
# in total at each curtailment rate; printed next to how much big load the forecast says wants in (average and peak).
# Cap per hour = capacity(year, month, hour-ending) from v1/erco_capacity.py. Hours where demand is already above the cap:
# added load fully curtailed. Assumptions: ercot_flexible_assumptions.md.
TARGETS = [0.001, 0.0025, 0.005, 0.01, 0.05]

base = pd.read_csv(os.path.join(here, "ERCO_forecast_base.csv"), parse_dates=["period"])
big = pd.read_csv(os.path.join(here, "ERCO_forecast_bigloads.csv"), parse_dates=["period"])
base["big"] = big["value"]
base["local"] = base["period"].dt.tz_convert(TEXAS)
# period is the END of the hour: local 00:00 is hour-ending 24 of the previous day, so month/year come from the hour's start
start = base["local"] - pd.Timedelta(hours=1)
he = base["local"].dt.hour.replace(0, 24)
base["cap"] = [capacity(y, m, h) for y, m, h in zip(start.dt.year, start.dt.month, he)]
base["year"] = base["local"].dt.year

summer_cap, winter_cap = load_caps()
print(f"Base: summer cap {summer_cap:,.0f} MW, winter cap {winter_cap:,.0f} MW; REAL_ONLY = {REAL_ONLY}")

rows = []
for year, d in base.groupby("year"):
    if len(d) < 8000:  # partial edge year (the forecast ends 2045-01-01 00:00 Texas time)
        continue
    gap = (d["cap"] - d["value"]).to_numpy()
    over = gap < 0
    gap = np.maximum(gap, 0)  # overloaded hours: no room, the added load is fully curtailed

    def rate(L):
        return np.maximum(0, L - gap).sum() / (L * len(gap))

    row = {"year": year, "hours_over": int(over.sum())}
    for t in TARGETS:
        if rate(1) >= t:
            L = 0
        else:
            L = root_scalar(lambda L: rate(L) - t, bracket=[1, 300_000], method="brentq").root
        row[f"{t * 100:g}%"] = round(L / 1000, 2)
    row["big_avg_GW"] = round(d["big"].mean() / 1000, 1)
    row["big_peak_GW"] = round(d["big"].max() / 1000, 1)
    rows.append(row)

print("Headroom (GW) for big flexible loads at each curtailment rate, vs big load wanting in:")
print(pd.DataFrame(rows).to_string(index=False))
