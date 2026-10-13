import os

import numpy as np
import pandas as pd

from erco_headroom_forecast import FORECAST, SUMMER_MONTHS, TEXAS, load_caps, root

# Task C: switch-off hours for ONE 100 MW data center added to ERCOT, per year.
# Same formula as prediction v1, hour by hour, with L = 100 MW:
#   cut_t = max(0, D_t + 100 - cap_t), capped at 100 (hours already over the cap: the site is fully off).
# Caps: imported from prediction v1 (max served over ALL history), used for history AND forecast years.
#   Look-ahead on history: early years are judged against peaks set later (e.g. 2016 vs the 2026 summer peak),
#   so their cuts come out lower than erco_headroom_yearly.py (window caps). Fine for "what would this site see
#   against today's proven capacity", not for "what it saw at the time".
# Per year it prints: hours cut, max MW cut at once, longest single switch-off (hours + MWh), total MWh cut.
# An event = consecutive cut hours with no gap in the timestamps; each row is one hour, so MW summed = MWh.
# Forecast years: hour order is fake (ERCOT places monthly load on 2008's calendar, see prediction_v1_assumptions.md),
# so the longest event is not computed. Hours and MWh don't depend on order, but they are floors (see next note).
# Forecast hourly values are milder than real extremes: ERCOT averages 17 past weather years, so the forecast has no
# heat domes or winter storms (e.g. Uri 2021) and its peak hours sit lower than any real year's. Switch-off hours come
# from exactly those peak hours, so forecast cuts are underestimated: for now, forecast hours cut per year (and MWh)
# is a FLOOR, a lower bound on the real number, not an estimate of it. This only changes once the forecast hourly values
# include extreme values, e.g. by overlaying predicted extreme events on top of it, or some other measure.
SITE_MW = 100
HIST_YEARS = list(range(2016, 2026))  # 2016-2024 from ERCO_bulk.csv, 2025 from ERCO.csv
FORECAST_YEARS = [2028]


def read(path):
    df = pd.read_csv(path, parse_dates=["period"]).dropna(subset=["value"])
    df["local"] = df["period"].dt.tz_convert(TEXAS)
    return df


def switch_off(df, summer_cap, winter_cap, real_order):
    df = df.sort_values("period").reset_index(drop=True)
    cap = np.where(df["local"].dt.month.isin(SUMMER_MONTHS), summer_cap, winter_cap)
    cut = np.clip(df["value"].to_numpy() + SITE_MW - cap, 0, SITE_MW)  # MW switched off each hour
    on = cut > 0
    row = {"hours_cut": int(on.sum()), "max_mw": round(cut.max(), 1), "total_mwh": round(cut.sum(), 1),
           "longest_h": "n/a", "longest_mwh": "n/a"}
    if real_order and on.any():
        follows = (df["period"].diff() == pd.Timedelta(hours=1)).to_numpy()  # this hour directly follows the last row
        start = on & ~(np.r_[False, on[:-1]] & follows)  # cut hour that doesn't continue a running event
        events = pd.Series(cut[on]).groupby(np.cumsum(start)[on]).agg(["size", "sum"])
        longest = events.loc[events["size"].idxmax()]
        row["longest_h"], row["longest_mwh"] = int(longest["size"]), round(longest["sum"], 1)
    elif real_order:
        row["longest_h"], row["longest_mwh"] = 0, 0.0
    return row


summer_cap, winter_cap = load_caps()
print(f"Site {SITE_MW} MW. Caps (prediction v1): summer {summer_cap:,.0f} MW, winter {winter_cap:,.0f} MW")

bulk = read(os.path.join(root, "ba_totals", "ERCO_bulk.csv"))
recent = read(os.path.join(root, "ba_totals", "ERCO.csv"))
hist = pd.concat([bulk, recent[~recent["local"].dt.year.isin(bulk["local"].dt.year.unique())]])
forecast = read(FORECAST)

rows = []
for y in HIST_YEARS:
    rows.append({"year": y, "source": "history", **switch_off(hist[hist["local"].dt.year == y], summer_cap, winter_cap, True)})
for y in FORECAST_YEARS:
    rows.append({"year": y, "source": "forecast", **switch_off(forecast[forecast["local"].dt.year == y], summer_cap, winter_cap, False)})

print(pd.DataFrame(rows).to_string(index=False))
