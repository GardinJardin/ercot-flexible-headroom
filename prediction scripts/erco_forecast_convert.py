import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pyxlsb import open_workbook

# Converts ERCOT's 2025 Long-Term Load Forecast (ERCOT Adjusted, hourly) into the same format as the historical
# files: ba_totals/ERCO_forecast.csv with `period` (UTC, end of hour) and `value` (MW, column `ercot_net`).
# The source file is Texas clock time with daylight saving, labelled by hour ENDING 1-24: the spring-forward day
# has 23 rows (hour 2 skipped), the fall-back day 25 rows (hour 2 twice). The rows are consecutive real hours, so
# UTC end of hour = the first row's UTC end of hour + row number. Every row is checked against its local label.
# zoneinfo, not the "America/Chicago" string: pandas then uses pytz, whose rules drop daylight saving after 2037.
TEXAS = ZoneInfo("America/Chicago")
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project folder, one level up
SOURCE = os.path.join(root, "data", "ERCO_LTLF_2025_adjusted_hourly_forecast.xlsb")
OUT = os.path.join(root, "ba_totals", "ERCO_forecast.csv")

rows = []
with open_workbook(SOURCE) as wb:
    with wb.get_sheet(1) as sheet:
        for i, row in enumerate(sheet.rows()):
            v = [c.v for c in row]
            if i == 0:
                cols = [v.index(k) for k in ["year", "month", "day", "hour", "ercot_net"]]
                continue
            if v[0] is None:
                continue
            rows.append([v[j] for j in cols])
df = pd.DataFrame(rows, columns=["year", "month", "day", "hour", "value"])
df[["year", "month", "day", "hour"]] = df[["year", "month", "day", "hour"]].astype(int)
print(f"Read {len(df):,} rows, years {df['year'].min()}-{df['year'].max()}")

# Local end of hour as labelled (hour 24 -> 00:00 the next day).
local_end = pd.to_datetime(df[["year", "month", "day"]]) + pd.to_timedelta(df["hour"], unit="h")
first = local_end.iloc[0].tz_localize(TEXAS).tz_convert("UTC")
df["period"] = first + pd.to_timedelta(np.arange(len(df)), unit="h")

# Checks: day lengths, and every row's UTC time read back in Texas time matches its label.
day_len = df.groupby(["year", "month", "day"])["hour"].transform("size")
odd_days = df.loc[day_len != 24].groupby(["year", "month", "day"]).size()
print(f"Days not 24 rows: {len(odd_days)} ({(odd_days == 23).sum()} with 23, {(odd_days == 25).sum()} with 25, "
      f"{((odd_days != 23) & (odd_days != 25)).sum()} other)")
readback = df["period"].dt.tz_convert(TEXAS).dt.tz_localize(None)
# The first copy of the repeated fall hour ends at 01:00 standard time, which is labelled hour 2: the only allowed mismatch.
first_repeat = (day_len == 25) & (df["hour"] == 2) & ~df.duplicated(["year", "month", "day", "hour"])
mismatch = (readback != local_end) & ~first_repeat
print(f"Rows whose UTC time disagrees with their local label: {mismatch.sum()}")
print(f"Blank values: {df['value'].isna().sum()}, zero or negative: {(df['value'] <= 0).sum()}")
print(f"UTC range {df['period'].iloc[0]} -> {df['period'].iloc[-1]}")
if mismatch.any() or ((odd_days != 23) & (odd_days != 25)).any():
    raise SystemExit("Not saved: times don't line up, see counts above.")

df[["period", "value"]].to_csv(OUT, index=False)
print(f"saved {OUT}")
