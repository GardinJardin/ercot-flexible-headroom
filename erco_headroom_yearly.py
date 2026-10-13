import os

import numpy as np
import pandas as pd
from scipy.optimize import root_scalar

# Duke's headroom method (see erco_headroom.py), solved one year at a time.
# Assumption: transmission + generation capacity never shrinks, so the highest load ever served
# in the window could have been served in every year of it.
# Assumption: no climate change. Peaks come from 2016-2024 weather only, so used as a guide to future
# years this likely underestimates future summer peak load (hotter summers) and overestimates future
# winter peak load (milder winters on average; extreme cold snaps like Uri 2021 can still break this).
# Caps stay the max seasonal demand over the WHOLE window (user, 2026-10-12):
#   summer cap = max of Jun-Aug, applied Apr-Oct; winter cap = max of Dec-Feb, applied Nov-Mar.
# Per year: curtailed_t = max(0, D_t + L - cap_t); rate(L) = sum(curtailed) / (L * hours in year).
YEARS = list(range(2016, 2025))  # Duke's window, Texas calendar years
TARGETS = [0.001, 0.0025, 0.005, 0.01, 0.05]

here = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(here, "ba_totals", "ERCO_bulk.csv"), parse_dates=["period"])
df["local"] = df["period"].dt.tz_convert("America/Chicago")
df = df[df["local"].dt.year.isin(YEARS)].reset_index(drop=True)
month = df["local"].dt.month

summer_cap = df.loc[month.isin([6, 7, 8]), "value"].max()
winter_cap = df.loc[month.isin([12, 1, 2]), "value"].max()
df["cap"] = np.where(month.isin([4, 5, 6, 7, 8, 9, 10]), summer_cap, winter_cap)
print(f"Summer cap {summer_cap:,.0f} MW, winter cap {winter_cap:,.0f} MW")

gap = (df["cap"] - df["value"]).to_numpy()  # room under the cap each hour
year = df["local"].dt.year.to_numpy()

rows = []
for y in YEARS:
    gap_y = gap[year == y]

    def rate(L):
        return np.maximum(0, L - gap_y).sum() / (L * len(gap_y))

    row = {"year": y}
    for t in TARGETS:
        L = root_scalar(lambda L: rate(L) - t, bracket=[1, 100_000], method="brentq").root
        row[f"headroom_gw_{t * 100:g}pct"] = round(L / 1000, 2)
    rows.append(row)

table = pd.DataFrame(rows)
print(table.to_string(index=False))
out = os.path.join(here, "erco_headroom_yearly.csv")
table.to_csv(out, index=False)
print(f"saved {out}")
