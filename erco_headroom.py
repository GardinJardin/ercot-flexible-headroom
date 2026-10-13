import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import root_scalar

# Duke's method. Cap = max seasonal demand over the window:
#   summer cap = max of Jun-Aug, applied Apr-Oct; winter cap = max of Dec-Feb, applied Nov-Mar.
# Add a constant load L every hour; curtailed_t = max(0, D_t + L - cap_t).
# rate(L) per year = sum(curtailed) / (L * hours in year); Duke's rate = mean of the yearly rates.
YEARS = list(range(2016, 2025))  # Duke's window, Texas calendar years
TARGETS = [0.0025, 0.005, 0.01]

here = os.path.dirname(os.path.abspath(__file__))
df = pd.read_csv(os.path.join(here, "ba_totals", "ERCO_bulk.csv"), parse_dates=["period"])
df["local"] = df["period"].dt.tz_convert("America/Chicago")
df = df[df["local"].dt.year.isin(YEARS)].reset_index(drop=True)
month = df["local"].dt.month

summer_cap = df.loc[month.isin([6, 7, 8]), "value"].max()
winter_cap = df.loc[month.isin([12, 1, 2]), "value"].max()
df["cap"] = np.where(month.isin([4, 5, 6, 7, 8, 9, 10]), summer_cap, winter_cap)
print(f"Years: {YEARS}, {len(df):,} hours")
print(f"Summer cap {summer_cap:,.0f} MW, winter cap {winter_cap:,.0f} MW")

gap = (df["cap"] - df["value"]).to_numpy()  # room under the cap each hour
year = df["local"].dt.year.to_numpy()


def rate(L):
    curtailed = np.maximum(0, L - gap)
    return np.mean([curtailed[year == y].sum() / (L * (year == y).sum()) for y in YEARS])


for t in TARGETS:
    L = root_scalar(lambda L: rate(L) - t, bracket=[1, 100_000], method="brentq").root
    print(f"Headroom at {t:.2%} curtailment: {L / 1000:,.2f} GW")

Ls = np.linspace(100, 40_000, 400)
plt.plot(Ls / 1000, [rate(L) * 100 for L in Ls])
for t in TARGETS:
    plt.axhline(t * 100, color="gray", linewidth=0.5)
plt.xlabel("Added constant load L (GW)")
plt.ylabel("Mean yearly curtailment rate (%)")
plt.title(f"ERCOT rate(L), {YEARS[0]}-{YEARS[-1]}")
plt.ylim(0, 5)
out = os.path.join(here, "erco_rate.png")
plt.savefig(out, dpi=120)
print(f"saved {out}")
