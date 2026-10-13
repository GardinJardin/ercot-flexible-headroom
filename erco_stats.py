import os

import pandas as pd

# Duke's window: 2016-01-01 through 2024-12-31 (UTC).
START = pd.Timestamp("2016-01-01T00", tz="UTC")
END = pd.Timestamp("2024-12-31T23", tz="UTC")
# Duke's seasons: summer peak = Jun-Aug, winter peak = Dec-Feb (months in Texas local time).
SUMMER = [6, 7, 8]
WINTER = [12, 1, 2]

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ba_totals", "ERCO_bulk.csv")
df = pd.read_csv(path, parse_dates=["period"])
df = df[df["period"].between(START, END)].reset_index(drop=True)
df["local"] = df["period"].dt.tz_convert("America/Chicago")

print(f"Window:       {df['period'].min():%Y-%m-%dT%H} -> {df['period'].max():%Y-%m-%dT%H} UTC, {len(df):,} hours")


def show(label, rows):
    peak = rows.loc[rows["value"].idxmax()]
    print(f"{label} {peak['period']:%Y-%m-%dT%H} UTC ({peak['local']:%Y-%m-%d %H:00} Texas), {peak['value']:,.0f} MWh")
    return peak


peak = show("Peak hour:   ", df)
show("Summer peak: ", df[df["local"].dt.month.isin(SUMMER)])
show("Winter peak: ", df[df["local"].dt.month.isin(WINTER)])

average = df["value"].mean()
print(f"Average load: {average:,.0f} MWh")
print(f"Load factor:  {average / peak['value']:.3f}")
