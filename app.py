import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
from scipy.optimize import root_scalar

here = os.path.dirname(os.path.abspath(__file__))
ercot = os.path.join(here, "flexible-rule grids", "ercot")
# app.py sits at the project root, so the v1 folder is one level down (ercot_flexible_headroom.py goes two levels up instead)
sys.path.insert(0, os.path.join(here, "prediction scripts", "v1"))
from erco_capacity import TEXAS, REAL_ONLY, capacity, load_caps  # noqa: E402  (same capacity as prediction v1)

st.set_page_config(page_title="ERCOT flexible-load headroom", layout="wide")


@st.cache_data(show_spinner=False)
def build():
    # Hourly ERCOT forecast with the grid capacity for each hour.
    # Hours check: ercot_site_100mw.py lines 29-31. Cap column: ercot_flexible_headroom.py lines 20-28.
    files = {k: pd.read_csv(os.path.join(ercot, f"ERCO_forecast_{k}.csv"), parse_dates=["period"])
             for k in ["base", "bigloads", "officer_letters"]}
    if not all((files[k]["period"] == files["base"]["period"]).all() for k in files):
        raise SystemExit("Forecast files don't share the same hours; rerun ercot_split_forecast.py.")
    df = files["base"][["period"]].copy()
    df["base"] = files["base"]["value"]
    df["big"] = files["bigloads"]["value"]
    df["officer_letters"] = files["officer_letters"]["value"]
    df["contracts"] = df["big"] - df["officer_letters"]
    df["local"] = df["period"].dt.tz_convert(TEXAS)
    # period is the END of the hour: local 00:00 is hour-ending 24 of the previous day, so month/year come from the hour's start
    start = df["local"] - pd.Timedelta(hours=1)
    he = df["local"].dt.hour.replace(0, 24)
    df["cap"] = [capacity(y, m, h) for y, m, h in zip(start.dt.year, start.dt.month, he)]
    df["year"] = df["local"].dt.year
    return df[["year", "base", "big", "officer_letters", "contracts", "cap"]]


with st.spinner("Building the hourly forecast and capacity table (first load takes a while)..."):
    data = build()

st.title("ERCOT flexible-load headroom")
st.write("How much big flexible (curtailable) load can ERCOT absorb at a given curtailment rate, compared with how much big "
         "load wants in? And how much does one flexible site get switched off?")

sel_year = st.slider("Year", 2025, 2044, 2030)


def highlight(row):
    # subtle background on the selected year's row
    return ["background-color: rgba(255, 193, 7, 0.25)" if row["Year"] == sel_year else "" for _ in row]


# ---- 2. Grid capacity lookup ----
st.header("Grid capacity lookup")
c1, c2, c3 = st.columns(3)
cy = c1.number_input("Year", 2025, 2050, 2030, step=1)
cm = c2.number_input("Month", 1, 12, 7, step=1)
ch = c3.number_input("Hour-ending", 1, 24, 17, step=1)
st.metric("Grid capacity (MW)", f"{capacity(int(cy), int(cm), int(ch)):,.0f}")
summer_cap, winter_cap = load_caps()
st.markdown(f"""
- Valid years are 2025-2050 for capacity; demand data covers 2025-2044.
- Hour-ending 17 means 4-5 pm Texas time.
- Capacity = the highest demand ERCOT actually served (summer cap {summer_cap:,.0f} MW for Apr-Oct, winter cap {winter_cap:,.0f} MW for Nov-Mar),
  plus EIA AEO2026 additions minus retirements after 2026. Solar and wind are weighted by their measured month x hour output factors,
  and batteries by the ERCOT CDR ELCC.
- Assumptions: REAL_ONLY = {REAL_ONLY} (False = includes EIA model-built plants, not just planned ones); the grid is treated as
  one point (no transmission limits); after-sunset summer capacity is probably overstated.
""")

# ---- 3. Flexible headroom ----
st.header("Flexible headroom")
rate_pct = st.number_input("Curtailment rate (%)", min_value=0.01, max_value=20.0, value=5.0, step=0.05)
t = rate_pct / 100

# Math copied from ercot_flexible_headroom.py lines 33-53, with one target t instead of TARGETS.
hrows = []
for year, d in data.groupby("year"):
    if len(d) < 8000:  # partial edge year (the forecast ends 2045-01-01 00:00 Texas time)
        continue
    gap = (d["cap"] - d["base"]).to_numpy()
    over = gap < 0
    gap = np.maximum(gap, 0)  # overloaded hours: no room, the added load is fully curtailed

    def rate(L):
        return np.maximum(0, L - gap).sum() / (L * len(gap))

    if rate(1) >= t:
        L = 0
    else:
        L = root_scalar(lambda L: rate(L) - t, bracket=[1, 300_000], method="brentq").root
    hrows.append({"Year": year, "Hours over capacity": int(over.sum()),
                  f"Headroom at {rate_pct:g}% (GW)": round(L / 1000, 2),
                  "Big load average (GW)": round(d["big"].mean() / 1000, 1),
                  "Big load peak (GW)": round(d["big"].max() / 1000, 1)})
head = pd.DataFrame(hrows)
hcol = f"Headroom at {rate_pct:g}% (GW)"

r = head[head["Year"] == sel_year].iloc[0]
st.metric(f"{sel_year}: big flexible load that fits at {rate_pct:g}% curtailment",
          f"{r[hcol]:.2f} GW fits, {r['Big load average (GW)']:.1f} GW wants in")
st.line_chart(head.set_index("Year")[[hcol, "Big load average (GW)"]], y_label="GW")
st.dataframe(head.style.apply(highlight, axis=1).format(
    {"Year": "{:d}", "Hours over capacity": "{:,d}", hcol: "{:.2f}",
     "Big load average (GW)": "{:.1f}", "Big load peak (GW)": "{:.1f}"}), hide_index=True)

# ---- 4. One flexible site ----
st.header("One flexible site")
SITE_MW = st.number_input("Site size (MW)", min_value=1, max_value=5000, value=100, step=1)

# Math copied from ercot_site_100mw.py lines 30-49, with SITE_MW from the input.
sdf = data.copy()
sdf["value"] = sdf["base"] + sdf["contracts"]  # = ercot_net - ercot_officer_letters
sdf["cut"] = np.clip(sdf["value"] + SITE_MW - sdf["cap"], 0, SITE_MW)  # MW switched off each hour
srows = []
for year, d in sdf.groupby("year"):
    if len(d) < 8000:  # partial edge year
        continue
    srows.append({"Year": year, "Hours cut": int((d["cut"] > 0).sum()),
                  "Hours fully off": int((d["cut"] >= SITE_MW).sum()),
                  "Max MW cut": round(d["cut"].max(), 1), "Total MWh cut": round(d["cut"].sum()),
                  "Curtailment rate (%)": round(d["cut"].sum() / (SITE_MW * len(d)) * 100, 3),
                  "Contracted big load average (GW)": round(d["contracts"].mean() / 1000, 1)})
site = pd.DataFrame(srows)

r = site[site["Year"] == sel_year].iloc[0]
st.metric(f"{sel_year}: {SITE_MW} MW site curtailment rate",
          f"{r['Curtailment rate (%)']:.3f}%, {int(r['Hours cut']):,} hours cut")
st.line_chart(site.set_index("Year")[["Curtailment rate (%)"]], y_label="% of the year")
st.dataframe(site.style.apply(highlight, axis=1).format(
    {"Year": "{:d}", "Hours cut": "{:,d}", "Hours fully off": "{:,d}", "Max MW cut": "{:.1f}",
     "Total MWh cut": "{:,d}", "Curtailment rate (%)": "{:.3f}",
     "Contracted big load average (GW)": "{:.1f}"}), hide_index=True)
st.caption("Queue assumption: the site is behind all contracted big loads and ahead of all officer-letter loads. This is unverified.")

# ---- 5. Caveats ----
with st.expander("Caveats", expanded=True):
    st.markdown("""
- Averaged weather: the forecast averages 17 past weather years, with no heat domes or winter storms like Uri. Every cut is a floor and every headroom number is optimistic.
- The hour order is not real (the forecast copies a 2008 calendar), so there are no event lengths, only yearly totals.
- The grid is treated as one point. Local power-line limits are not modeled.
- Evening capacity is probably overstated: the summer cap was set at 6 pm with solar still producing, but is applied to every hour.
- The numbers include EIA model-built plant additions. With planned plants only, headroom collapses much earlier (e.g. 2030 at 0.5%: 12.9 to 8.5 GW).
- The big-load forecast counts only filed projects, so it likely undercounts after about 2030.
- All big loads are treated as flexible-eligible, though the law's size threshold and the load types may not all qualify.
""")

# ---- 6. Data sources ----
st.caption("Data sources: EIA-930, EIA-860M (Aug 2026), EIA AEO2026 tables 54.1/56.1, ERCOT 2025 LTLF, ERCOT CDR Dec 2025.")
