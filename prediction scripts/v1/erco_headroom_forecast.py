import os

import numpy as np
import pandas as pd
from scipy.optimize import root_scalar

from erco_capacity import SUMMER_MONTHS, TEXAS, REAL_ONLY, capacity, load_caps, root  # noqa: F401 (re-exported for other scripts)

# Duke's headroom method (see erco_headroom_yearly.py) on ONE forecast year.
# Demand: ERCOT's future hourly forecast (assumptions in prediction_v1_assumptions.md).
# Cap (grid capacity) for every hour: capacity(year, month, hour-ending) from erco_capacity.py = the highest demand the grid has
# actually served, from ALL history on disk (ERCO_bulk.csv 2016-2024 + ERCO.csv 2019-05 -> now; summer cap = max of Jun-Aug applied
# Apr-Oct, winter cap = max of Dec-Feb applied Nov-Mar) + EIA AEO2026 Texas capacity changes since 2026, each type x its
# hourly factor (solar/wind typical day, batteries CDR ELCC, thermal at full summer rating). In 2026 nothing changes, so the cap
# is the flat historical peak. Switches (REAL_ONLY etc.) and all choices live in erco_capacity.py.
# Hours where forecast demand is already above the cap: the added load is fully curtailed (gets 0 MW).
# Other hours as before: curtailed_t = max(0, L - (cap_t - D_t)); rate(L) = sum(curtailed) / (L * hours in year).
# Importable: load_caps(), capacity() and the constants; the run only happens when this file is run directly.
YEAR = 2026  # Texas calendar year to run
TARGETS = [0.001, 0.0025, 0.005, 0.01, 0.05]
FORECAST = os.path.join(root, "ba_totals", "ERCO_forecast.csv")  # placeholder: period (UTC, end of hour), value (MW)


if __name__ == "__main__":
    summer_cap, winter_cap = load_caps()
    print(f"Base: summer cap {summer_cap:,.0f} MW, winter cap {winter_cap:,.0f} MW; REAL_ONLY = {REAL_ONLY}")

    df = pd.read_csv(FORECAST, parse_dates=["period"])
    df["local"] = df["period"].dt.tz_convert(TEXAS)
    df = df[df["local"].dt.year == YEAR].reset_index(drop=True)
    # period is the END of the hour: local 00:00 is hour-ending 24 of the previous day, so month/year come from the hour's start
    start = df["local"] - pd.Timedelta(hours=1)
    he = df["local"].dt.hour.replace(0, 24)
    df["cap"] = [capacity(y, m, h) for y, m, h in zip(start.dt.year, start.dt.month, he)]

    gap = (df["cap"] - df["value"]).to_numpy()  # room under the cap each hour
    over = gap < 0
    print(f"Year {YEAR}: {len(df):,} hours, {over.sum():,} already over the cap ({over.mean():.2%})")
    gap = np.maximum(gap, 0)  # overloaded hours: no room, the added load is fully curtailed

    def rate(L):
        return np.maximum(0, L - gap).sum() / (L * len(gap))

    for t in TARGETS:
        if rate(1) >= t:  # overloaded hours alone already exceed this curtailment rate
            L = 0
        else:
            L = root_scalar(lambda L: rate(L) - t, bracket=[1, 100_000], method="brentq").root
        print(f"Headroom at {t:.2%} curtailment: {L / 1000:,.2f} GW")
