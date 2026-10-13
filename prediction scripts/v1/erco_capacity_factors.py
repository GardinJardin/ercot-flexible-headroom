import os
from zoneinfo import ZoneInfo

import pandas as pd

# Capacity factors for ERCOT renewables: hourly measured output (EIA-930 net generation by fuel, data/ERCO_fuel.parquet)
# divided by the installed size of that type in that month (EIA-860M rebuild, data/ERCO_installed_capacity_monthly.csv),
# then averaged by Texas month and hour of day. Later multiplied by future installed sizes to get hour-by-hour supply.
# Fuel -> type: SUN -> solar, WND -> wind, WAT -> hydro, OTH -> other_renewables. OTH is uncertain: EIA-930 "other" may
# include non-renewable units, so its factor is checked below (a factor near or above 1 means OTH is bigger than the
# biomass/landfill-gas fleet it is divided by).
# Texas time: UTC end of hour -> America/Chicago wall clock (zoneinfo, not the string: pandas would use pytz, wrong
# after 2037). Hour-ending = wall-clock end hour, 00:00 -> hour 24 of the previous day. DST quirk: on the fall-back
# day the repeated hour is labelled 1 twice (ERCOT labels it 2 twice) and spring-forward skips 3 instead of 2 — one hour
# a year, negligible in the averages. Month and year = the Texas date of the hour.
# Hours with no installed size (Sep 2026 on, after the 860M inventory date) are dropped. Blank values are dropped.
# Negative output and factors > 1 are kept as EIA gives them and reported.
# Outputs: data/ERCO_capacity_factors_by_year.csv (year, month, hour_ending, type, factor = mean over that year-month's
# days, hours_used) and data/ERCO_capacity_factors.csv (month, hour_ending, type, factor = mean of the yearly factors
# over FULL Texas years only, each year weighted equally, plus min and max across those years).
TEXAS = ZoneInfo("America/Chicago")
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project folder: v1 -> prediction scripts -> project
FUEL = os.path.join(root, "data", "ERCO_fuel.parquet")
CAP = os.path.join(root, "data", "ERCO_installed_capacity_monthly.csv")
OUT_YEAR = os.path.join(root, "data", "ERCO_capacity_factors_by_year.csv")
OUT = os.path.join(root, "data", "ERCO_capacity_factors.csv")
FUEL_TO_TYPE = {"SUN": "solar", "WND": "wind", "WAT": "hydro", "OTH": "other_renewables"}

fuel = pd.read_parquet(FUEL)
df = fuel[fuel["fueltype"].isin(FUEL_TO_TYPE)].copy()
df["type"] = df["fueltype"].map(FUEL_TO_TYPE)
local = df["period"].dt.tz_convert(TEXAS).dt.tz_localize(None) - pd.Timedelta(hours=1)  # Texas wall-clock start of hour
df["year"] = local.dt.year
df["month"] = local.dt.month
df["hour_ending"] = local.dt.hour + 1
df["cap_month"] = local.dt.strftime("%Y-%m")
df["date"] = local.dt.date

cap = pd.read_csv(CAP)
df = df.merge(cap, left_on=["cap_month", "type"], right_on=["month", "type"], how="left", suffixes=("", "_cap"))
no_cap = df["installed_MW"].isna()
print(f"Hours dropped, no installed size for that month: {no_cap.sum()} rows "
      f"({df.loc[no_cap, 'cap_month'].min()} -> {df.loc[no_cap, 'cap_month'].max()})")
df = df[~no_cap]
blank = df["value"].isna()
print(f"Blank values dropped: {blank.sum()}")
df = df[~blank]
zero_cap = df["installed_MW"] <= 0
print(f"Rows in months with installed size 0: {zero_cap.sum()} (dropped)")
df = df[~zero_cap]
df["factor"] = df["value"] / df["installed_MW"]

for t, g in df.groupby("type"):
    print(f"{t}: {len(g):,} hours, negative output {(g['value'] < 0).sum()} (min {g['value'].min():.0f} MW), "
          f"factor > 1: {(g['factor'] > 1).sum()} (max {g['factor'].max():.2f}), mean factor {g['factor'].mean():.3f}")
print("Mean factor by Texas year:")
print(df.groupby(["year", "type"])["factor"].mean().unstack().round(3))

by_year = (df.groupby(["year", "month", "hour_ending", "type"])["factor"].agg(["mean", "count"])
           .reset_index().rename(columns={"mean": "factor", "count": "hours_used"}))
by_year.to_csv(OUT_YEAR, index=False)
print(f"saved {OUT_YEAR}: {len(by_year):,} rows")

# Full years: the data runs from Jan 1 to Dec 31 (Texas dates). Gaps inside a year don't disqualify it (2025 lacks
# Dec 5, a whole day EIA doesn't have); missing days are printed.
dates = df.groupby("year")["date"].agg(["min", "max", "nunique"])
full = [y for y, r in dates.iterrows() if r["min"].strftime("%m-%d") == "01-01" and r["max"].strftime("%m-%d") == "12-31"]
for y in full:
    missing = pd.Timestamp(year=y, month=12, day=31).dayofyear - dates.loc[y, "nunique"]
    print(f"{y}: {missing} Texas days missing")
print(f"Full Texas years used for the average: {full}")
avg = (by_year[by_year["year"].isin(full)].groupby(["month", "hour_ending", "type"])["factor"]
       .agg(["mean", "min", "max"]).reset_index().rename(columns={"mean": "factor"}))
avg.to_csv(OUT, index=False)
print(f"saved {OUT}: {len(avg):,} rows")
print(f"Averaged factors > 1: {(avg['factor'] > 1).sum()}, negative: {(avg['factor'] < 0).sum()}")
show = avg[avg["month"].isin([1, 8]) & avg["hour_ending"].isin([8, 12, 17, 19, 21]) & avg["type"].isin(["solar", "wind"])]
print(show.pivot_table(index=["month", "hour_ending"], columns="type", values="factor").round(3))
