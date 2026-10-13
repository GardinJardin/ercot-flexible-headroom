import os

import pandas as pd

from eia_pipeline import get_subregions, load_subregion

now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H")

series = {}
for code in get_subregions("ERCO"):
    df = load_subregion(code, now, ask=False)
    series[code] = df.set_index("period")["value"]

# Every hour that at least one subregion has. An hour no subregion has stays absent.
all_hours = sorted(set().union(*[s.index for s in series.values()]))

cleaned = []
for code, s in series.items():
    s = s.reindex(all_hours)  # hours this subregion is missing become blank
    # Blank or zero -> straight line between the nearest good values on each side:
    # step = (after - before) / (bad hours + 1), stepped per hour.
    # limit_area="inside": a bad run at the start or end (only one neighbour) is left as is.
    filled = s.where(s != 0).interpolate(method="time", limit_area="inside")
    filled = filled.fillna(s)  # keeps edge zeros as 0

    # A bad run whose good neighbours sit on opposite sides of a whole-ERCOT outage
    # (hours absent from all_hours) gets this subregion's average instead of the line:
    # the mean of its good values from 6 months before the run to 6 months after it.
    bad = (s.isna() | (s == 0)).tolist()
    i = 0
    while i < len(bad):
        if not bad[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(bad) and bad[j + 1]:
            j += 1
        if i > 0 and j + 1 < len(bad):  # edge runs are left as is
            before, after = all_hours[i - 1], all_hours[j + 1]
            if after - before > pd.Timedelta(hours=j - i + 2):  # clock hours in between are missing
                window = s[all_hours[i] - pd.DateOffset(months=6):all_hours[j] + pd.DateOffset(months=6)]
                filled.iloc[i:j + 1] = window[window != 0].mean()
        i = j + 1

    print(f"{code}: {((s.isna() | (s == 0)) & filled.notna() & (filled != 0)).sum()} values filled")
    cleaned.append(filled)

total = pd.concat(cleaned).groupby(level=0).sum(min_count=1)
total = total.rename_axis("period").reset_index()
print(total)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ba_totals", "ERCO.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)
total.to_csv(out, index=False)
print(f"saved {out}")
