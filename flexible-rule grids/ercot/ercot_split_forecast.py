import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pyxlsb import open_workbook

# Splits ERCOT's 2025 Long-Term Load Forecast (ERCOT Adjusted, hourly) into:
#   big loads   = ercot_contracts + ercot_officer_letters (new large loads, treated as flexible-eligible;
#                 assumptions in ercot_flexible_assumptions.md)
#   normal grid = ercot_net - big loads
#   officer letters alone = ercot_officer_letters (for the 100 MW site script, which keeps contracts as firm demand)
# Saved next to this script as ERCO_forecast_base.csv, ERCO_forecast_bigloads.csv and ERCO_forecast_officer_letters.csv
# (period, value), same format as the
# other totals: period = UTC end of hour, value = MW. Time conversion as in prediction scripts/erco_forecast_convert.py:
# the source is Texas clock time with daylight saving, hour ENDING 1-24; rows are consecutive real hours, so
# UTC end of hour = first row's UTC end of hour + row number, checked against every row's local label.
TEXAS = ZoneInfo("America/Chicago")  # zoneinfo, not the string: pandas then uses pytz, which drops DST after 2037
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(here))  # project folder, two levels up
SOURCE = os.path.join(root, "data", "ERCO_LTLF_2025_adjusted_hourly_forecast.xlsb")
TOTAL = os.path.join(root, "ba_totals", "ERCO_forecast.csv")

rows = []
with open_workbook(SOURCE) as wb:
    with wb.get_sheet(1) as sheet:
        for i, row in enumerate(sheet.rows()):
            v = [c.v for c in row]
            if i == 0:
                cols = [v.index(k) for k in ["year", "month", "day", "hour", "ercot_net", "ercot_contracts",
                                             "ercot_officer_letters"]]
                continue
            if v[0] is None:
                continue
            rows.append([v[j] for j in cols])
df = pd.DataFrame(rows, columns=["year", "month", "day", "hour", "net", "contracts", "officer_letters"])
df[["year", "month", "day", "hour"]] = df[["year", "month", "day", "hour"]].astype(int)
print(f"Read {len(df):,} rows, years {df['year'].min()}-{df['year'].max()}")

local_end = pd.to_datetime(df[["year", "month", "day"]]) + pd.to_timedelta(df["hour"], unit="h")
first = local_end.iloc[0].tz_localize(TEXAS).tz_convert("UTC")
df["period"] = first + pd.to_timedelta(np.arange(len(df)), unit="h")
day_len = df.groupby(["year", "month", "day"])["hour"].transform("size")
first_repeat = (day_len == 25) & (df["hour"] == 2) & ~df.duplicated(["year", "month", "day", "hour"])
mismatch = (df["period"].dt.tz_convert(TEXAS).dt.tz_localize(None) != local_end) & ~first_repeat
print(f"Rows whose UTC time disagrees with their local label: {mismatch.sum()}")

df["big"] = df["contracts"] + df["officer_letters"]
df["base"] = df["net"] - df["big"]
print(f"Blank values: {df[['net', 'contracts', 'officer_letters']].isna().sum().sum()}, "
      f"negative big loads: {(df['big'] < 0).sum()}, normal grid <= 0: {(df['base'] <= 0).sum()}")

# Check: normal grid + big loads = the existing total forecast file, hour by hour.
total = pd.read_csv(TOTAL, parse_dates=["period"])
diff = np.abs(total["value"].to_numpy() - (df["base"] + df["big"]).to_numpy())
same_hours = (total["period"].to_numpy() == df["period"].to_numpy()).all()
print(f"Check vs ERCO_forecast.csv: same hours {same_hours}, max |difference| {diff.max():.6f} MW")
if mismatch.any() or not same_hours or diff.max() > 1e-6:
    raise SystemExit("Not saved: checks failed, see above.")

df[["period", "base"]].rename(columns={"base": "value"}).to_csv(os.path.join(here, "ERCO_forecast_base.csv"), index=False)
df[["period", "big"]].rename(columns={"big": "value"}).to_csv(os.path.join(here, "ERCO_forecast_bigloads.csv"), index=False)
df[["period", "officer_letters"]].rename(columns={"officer_letters": "value"}).to_csv(
    os.path.join(here, "ERCO_forecast_officer_letters.csv"), index=False)
print(f"saved ERCO_forecast_base.csv, ERCO_forecast_bigloads.csv and ERCO_forecast_officer_letters.csv in {here}")
