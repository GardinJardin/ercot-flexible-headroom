import os
import sys

import altair as alt
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
st.caption("Highlights specific year")


def year_chart(df, cols, colors, y_title):
    # Years as categories (no "2,030" commas); no .interactive(), so no scroll zoom or drag pan.
    wide = df[["Year"] + cols].copy()
    wide["Year"] = wide["Year"].astype(str)
    long = wide.melt(id_vars="Year", value_vars=cols, var_name="Series", value_name="Value")
    x = alt.X("Year:O", title="Years", axis=alt.Axis(labelAngle=0))
    lines = alt.Chart(long).mark_line(point=True).encode(
        x=x, y=alt.Y("Value:Q", title=y_title),
        color=alt.Color("Series:N", scale=alt.Scale(domain=cols, range=colors), legend=alt.Legend(orient="bottom", title=None)))
    # Invisible hover targets, one per year. nearest=True splits the chart into one hover zone per year, so the
    # year's box (year first, then each line's value) shows wherever the pointer is, not only on the dots.
    hover = alt.selection_point(fields=["Year"], nearest=True, on="mouseover", empty=False)
    tip = [alt.Tooltip("Year:O", title="Year")] + [alt.Tooltip(field=c, type="quantitative", title=c, format=",.2f") for c in cols]
    targets = alt.Chart(wide).mark_point(opacity=0).encode(x=x, tooltip=tip).add_params(hover)
    return alt.layer(lines, targets)


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
# Small collapsed "Details" header (only this expander, via its container key); the text inside keeps its normal size
st.markdown("""<style>
.st-key-cap_details summary { padding-top: 0.2rem; padding-bottom: 0.2rem; min-height: 0; }
.st-key-cap_details summary p { font-size: 0.8rem; }
</style>""", unsafe_allow_html=True)
with st.container(key="cap_details"):
    with st.expander("Details", expanded=False):
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
st.caption("*How much big flexible load the ERCOT grid can take, if that load obeys the set curtailment rate. The light blue line "
         "represents headroom over time at that specific curtailment rate: essentially how much power it gets if it agrees to a "
         "specific curtailment rate. The dark blue line represents how much big load ERCOT's forecast says wants to connect.*")
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
st.altair_chart(year_chart(head, [hcol, "Big load average (GW)"], ["#83c9ff", "#0068c9"], "GW"), use_container_width=True)
st.dataframe(head.style.apply(highlight, axis=1).format(
    {"Year": "{:d}", "Hours over capacity": "{:,d}", hcol: "{:.2f}",
     "Big load average (GW)": "{:.1f}", "Big load peak (GW)": "{:.1f}"}), hide_index=True)
with st.expander("Documentation: Flexible headroom", expanded=False):
    st.markdown(f"""
**What it calculates**
- Headroom is the largest constant, around-the-clock block of big flexible load ERCOT can add while that load is fully or partially curtailed for the chosen share of the year.
- Each hour, the room left is the grid's capacity minus normal demand. Any part of the added load that doesn't fit in that hour is switched off, or curtailed. A root finder searches for the load size whose yearly switched-off share equals your rate.
- If normal demand alone exceeds capacity in enough hours, headroom is 0. Each such hour is 1/8,760 of the year.
- "Big load wants in" is ERCOT's forecast of new large loads: signed contracts plus officer letters (unsigned requests a utility executive has vouched for). ERCOT already discounts these for estimated drop-outs and adds a 180-day delay. We keep those discounts as they are.
- "Big load wants in" is all of that load. "Headroom" is how much of it could connect as flexible load. The gap between them is load that would need new plants or lines, or a higher curtailment rate.
- This section and "One flexible site" answer different scenarios: here, contracts and officer letters together are the flexible pool; there, contracts are firm and officer letters are left out. Don't compare their numbers directly.

**Demand caveats**
- Averaged weather: the forecast averages 17 past weather years (2008-2024), so there are no heat domes or winter storms like Uri 2021. Headroom is optimistic; real headroom in a bad-weather year is lower.
- No climate trend and no efficiency gains: future weather is assumed to look like the past, and homes and appliances don't get more efficient.
- Big loads are likely undercounted from about 2030: the forecast only knows about projects that have already filed, and projects file only a few years before they run.
- Every big load is treated as able to switch off. In reality, Texas SB 6's size threshold and timing, and some load types (factories, hydrogen, oil and gas), may not qualify.
- Existing crypto mines (3.4 GW in 2025, rising to 18.1 GW) stay in normal demand. They already cut back at peaks, so normal demand at peak may be slightly overstated.

**Capacity caveats**
- Capacity starts from the highest demand ERCOT has actually served: {summer_cap:,.0f} MW in summer (July 22, 2026, 5-6 pm) and {winter_cap:,.0f} MW in winter (Feb 20, 2025). New plants and retirements from EIA's 2026 outlook are added on top from 2027.
- Evening capacity is probably overstated: the summer record was set while solar was still producing, but that cap applies to every hour from April to October.
- The summer cap comes from June-August data but applies to April-October; the winter cap comes from December-February data and applies to November-March.
- The numbers include plants EIA's model expects to be built, not just announced ones. With announced plants only, headroom collapses much earlier (2030 at 0.5%: 12.9 to 8.5 GW; from 2032, zero at every rate).
- No new plants are built in response to ERCOT's big loads (EIA's outlook projects Texas demand far below ERCOT's forecast), so this is "room if supply doesn't respond."
- About 8 GW of solar EIA expects later in 2026 is counted nowhere, which makes capacity conservative.
- Solar may be slightly overstated: EIA's outlook and EIA's plant inventory count Texas solar differently (34.8 vs 30.0 GW in 2025).
- Solar and wind follow a typical day for each month (measured 2019-2025). Windless or cloudy days are not modeled. We take the installed sizes of solar and wind at each point in time and calculate the fraction of that size generated in each hour of each month.
- Gas, coal and nuclear count at full summer size every hour; breakdowns and cold-weather losses are ignored.
- Batteries are credited by ERCOT's 2-hour ELCC (the share of battery size counted on at peak), a conservative choice. They barely affect the result.
- The whole grid is treated as one point. Local power-line limits are not modeled, so a site can be blocked locally even when the state as a whole has room.
- Transmission growth isn't accounted for, and transmission is not modeled as a constraint: so far, "capacity" only looks at generation capacity. Every new plant counts toward capacity everywhere in ERCOT from the year it's added, which assumes the lines to carry its power get built in time. New wind and solar are mostly in West Texas and are already curtailed when lines out of the region are full. Planned line projects (e.g. ERCOT's Permian Basin 765 kV plan) aren't modeled either. Headroom from the 2030s onward is probably overstated.

**Reading the numbers**
- Use yearly totals, not hourly details. The forecast lays each month's load onto 2008's calendar, so the order of hours isn't real. There's no answer to "when" or "for how many hours in a row", based on the data currently used.
- 2032 dips because of EIA's planned coal and gas retirements that year, which come before its model builds replacements.
""")

# ---- 4. One flexible site ----
st.header("One flexible site")
st.caption("*The share of your site's power that gets switched off each year: its curtailment rate.*")
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
st.altair_chart(year_chart(site, ["Curtailment rate (%)"], ["#0068c9"], "% of the year"), use_container_width=True)
st.dataframe(site.style.apply(highlight, axis=1).format(
    {"Year": "{:d}", "Hours cut": "{:,d}", "Hours fully off": "{:,d}", "Max MW cut": "{:.1f}",
     "Total MWh cut": "{:,d}", "Curtailment rate (%)": "{:.3f}",
     "Contracted big load average (GW)": "{:.1f}"}), hide_index=True)
st.caption("Queue assumption: the site is behind all contracted big loads and ahead of all officer-letter loads. This is unverified.")
with st.expander("Documentation: One flexible site", expanded=False):
    st.markdown("""
**What it calculates**
- One site of the size you set connects as flexible load and wants its full size every hour.
- The site is new load, added on top of ERCOT's forecast. It can't be one of the projects the forecast already counts, or that load would be counted twice.
- Who's ahead in line: normal customers and big loads with signed contracts come first and are never cut. Officer-letter loads aren't included, meaning your added site is assumed to come before them.
- Each hour: switched off = normal demand + contracted loads + your site - capacity, kept between 0 and your site's size.
- Curtailment rate = total switched off over the year / (site size x hours in the year).
- Columns: "Hours cut" counts hours with any cut. "Hours fully off" counts hours where the whole site is off. "Max MW cut" is the largest single-hour cut. "Total MWh cut" is the year's switched-off energy. "Contracted big load average" is context only.

**Caveats specific to the site**
- Different scenario from "Flexible headroom": contracts are firm and officer letters are left out here, while headroom treats both together as flexible. Don't compare their numbers directly.
- The order in line is assumed. How ERCOT actually orders curtailment among flexible loads under SB 6 has not been checked. If the site is also behind officer-letter loads, its cuts are much higher.
- Contracted loads are never cut, even in hours when demand alone exceeds capacity. The site absorbs the whole shortage.
- Mostly all-or-nothing: when the grid is short, it's usually short by far more than the site, so most cut hours are full switch-offs (2028: 346 of 358 at 100 MW).
- Bigger sites get cut more, because they only fit in hours with more spare room.

**Shared caveats (same model as headroom)**
- Averaged weather: every cut is a lower bound. Real cuts in a bad-weather year are higher.
- Use yearly totals only. The hour order isn't real, so there's no longest switch-off or time-of-day pattern, based on the data currently used.
- The numbers include plants EIA's model expects to be built. With announced plants only, the 100 MW site is cut 32.8% of 2030 instead of 18.3%, and about 99% of hours from 2035.
- Capacity starts from the record peaks. Evening capacity is probably overstated, the grid is treated as one point, and gas, coal and nuclear count at full size every hour.
- Transmission isn't modeled, as a constraint or as growth: every new plant counts everywhere in ERCOT from the year it's added, so cuts from the 2030s onward are probably understated.
- Big loads are likely undercounted from about 2030. No climate trend and no efficiency gains.
- 2032 spikes because of EIA's planned coal and gas retirements that year.
""")

# ---- 5. Caveats ----
with st.expander("Caveats", expanded=True):
    st.markdown("""
- Averaged weather: every cut is a floor and every headroom number is optimistic.
- The numbers include EIA model-built plant additions, not just announced plants.
- The grid is treated as one point: local power-line limits are not modeled, and new transmission is assumed to keep up with new plants.
- Not modeled yet: power prices or the dollar value of flexibility, the actual SB 6 curtailment rules (triggers, notice, limits on how long or how often a site is cut), locations below the whole state, and a reserve margin.

Full details are in each section's Documentation.
""")

# ---- 6. Data sources ----
st.caption("Data sources: EIA-930, EIA-860M (Aug 2026), EIA AEO2026 tables 54.1/56.1, ERCOT 2025 LTLF, ERCOT CDR Dec 2025.")
