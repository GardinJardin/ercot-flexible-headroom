import os
from zoneinfo import ZoneInfo

import pandas as pd

# ERCOT grid capacity by (year, month, hour), "anchored" (user, 2026-10-13; details in prediction_v1_assumptions.md):
#   capacity = base(month) + sum over types of [change since 2026 x factor(type, month, hour)]
# base = the highest demand the grid has actually served (summer cap Apr-Oct, winter cap Nov-Mar; see load_caps).
# change(y) = (cumulative additions(y) - cumulative additions(2026)) - (cumulative retirements(y) - cumulative retirements(2026)),
#   0 for y <= 2026. Source: EIA AEO2026 Texas, cb2026 case (Counterfactual Baseline): Table 54.1 (all types) and
#   Table 56.1 (solar and wind separately). Years 2025-2050 only.
# Factors: coal, fossil steam, combined cycle, combustion turbine/diesel, nuclear, hydrogen, fuel cells, pumped storage = 1 every
#   hour (net SUMMER ratings, so cold-weather output is understated). Solar, wind = ERCO_capacity_factors.csv (typical day per
#   month, 2019-2025 average; solar runs somewhat high: output exceeds nameplate in some hours, and 860M solar at end-2025 is
#   30.0 GW vs AEO 34.8 GW). Other renewables = 1 every hour (the pipeline's 'other' factor is invalid; hydro/biomass can run at will).
# Batteries (diurnal storage): only additions after 2027 count (2026-2027 batteries are inside the proven peak) x ERCOT CDR
#   ELCC of the "BESS - 2.0 hr" row (fleet average is 1.65 h in EIA-860M), season of the month, LOWER of the two CDR hours;
#   CDR covers 2026-2030, later years use 2030.
# Solar/wind additions in Table 56.1 are totals (planned + unplanned): with REAL_ONLY they are cut to Table 54.1's
#   renewables planned share of that year. Retirements are always subtracted.
REAL_ONLY = False  # False = planned + unplanned (EIA model-built) additions; True = planned additions only

# zoneinfo, not the "America/Chicago" string: pandas then uses pytz, whose rules drop daylight saving after 2037.
TEXAS = ZoneInfo("America/Chicago")
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project folder, two levels up
SUMMER_MONTHS = [4, 5, 6, 7, 8, 9, 10]  # months the summer cap applies to; the rest get the winter cap
BATTERY_ROW = "BESS - 2.0 hr"
BATTERY_START = 2027  # batteries count only from additions after this year
FIRST_YEAR, LAST_YEAR = 2025, 2050
THERMAL = ["CoalSteam", "OtherFossilSt", "CombinedCycle", "CombustionTur", "NuclearPower", "PumpedStorage",
           "HydrogenTurbine", "FuelCells"]  # factor 1 every hour (Table 54.1 code endings)


def load_caps():
    """(summer_cap, winter_cap) in MW: max demand served in Jun-Aug / Dec-Feb over all history on disk."""
    hist = pd.concat([pd.read_csv(os.path.join(root, "ba_totals", f), parse_dates=["period"])
                      for f in ["ERCO_bulk.csv", "ERCO.csv"]])
    hist_month = hist["period"].dt.tz_convert(TEXAS).dt.month
    summer_cap = hist.loc[hist_month.isin([6, 7, 8]), "value"].max()
    winter_cap = hist.loc[hist_month.isin([12, 1, 2]), "value"].max()
    return summer_cap, winter_cap


def aeo_table(file):
    """EIA table as a DataFrame: row code -> columns 2025..2050 (GW)."""
    t = pd.read_excel(os.path.join(root, "data", file), header=None).set_index(0)
    t = t.loc[t.index.notna(), list(range(2, 28))].astype(float)
    t.columns = range(FIRST_YEAR, LAST_YEAR + 1)
    return t


# ---- load everything once ----
SUMMER_CAP, WINTER_CAP = load_caps()

t54 = aeo_table("EIA_AEO2026_suptab_54.1_capacity.xlsx")
t56 = aeo_table("EIA_AEO2026_suptab_56.1_renewables.xlsx")


def adds(name):
    """Cumulative additions (GW) by year for a Table 54.1 type: planned (+ unplanned unless REAL_ONLY)."""
    out = t54.loc["EPD001:ca_" + name]
    return out if REAL_ONLY else out + t54.loc["EPD001:da_" + name]


def rets(name):
    return t54.loc["EPD001:ea_" + name]


# Table 54.1 renewables planned share of (planned + unplanned) additions, per year (1 when there are none)
ren_planned = t54.loc["EPD001:ca_RenewableSour"]
ren_total = ren_planned + t54.loc["EPD001:da_RenewableSour"]
share = (ren_planned / ren_total).where(ren_total > 0, 1.0)

solar_add = t56.loc["REG001:add_solar_photo"]
wind_add = t56.loc["REG001:add_on_wind"]
if REAL_ONLY:
    solar_add, wind_add = solar_add * share, wind_add * share
# Table 56.1 has no retirement rows: implied retirement = additions - (capacity now - capacity in 2025)
solar_ret = t56.loc["REG001:add_solar_photo"] - (t56.loc["REG001:ca_SolarPhotovol"] - t56.loc["REG001:ca_SolarPhotovol"][2025])
wind_ret = t56.loc["REG001:add_on_wind"] - (t56.loc["REG001:ca_Wind"] - t56.loc["REG001:ca_Wind"][2025])
# other renewables = renewables total minus solar and wind (additions and retirements)
other_add = adds("RenewableSour") - solar_add - wind_add
other_ret = rets("RenewableSour") - solar_ret - wind_ret

# per type, GW by year: additions - retirements, cumulative since Dec 2025
net = {"flat": sum(adds(n) - rets(n) for n in THERMAL),
       "solar": solar_add - solar_ret,
       "wind": wind_add - wind_ret,
       "other": other_add - other_ret,
       "battery": adds("DiurnalStorage") - rets("DiurnalStorage")}

# change since 2026 in MW, per year per type
CHANGE = {}
for y in range(FIRST_YEAR, LAST_YEAR + 1):
    CHANGE[y] = {}
    for k, v in net.items():
        start = BATTERY_START if k == "battery" else 2026  # batteries: only additions after 2027 count
        CHANGE[y][k] = 1000 * (v[y] - v[start]) if y > start else 0

# solar / wind factors by (type, month, hour-ending)
fac = pd.read_csv(os.path.join(root, "data", "ERCO_capacity_factors.csv"))
FACTOR = {(r.type, r.month, r.hour_ending): r.factor for r in fac[fac["type"].isin(["solar", "wind"])].itertuples()}

# battery ELCC: (season, label) -> lower of the Peak Load Hour and Peak Net Load Hour values for BATTERY_ROW
elcc = pd.read_excel(os.path.join(root, "data", "ERCOT_CDR_Dec2025.xlsx"), sheet_name="ELCCs", header=None)
BATTERY = {}
for col in range(4, elcc.shape[1]):
    season, label = elcc.iloc[3, col], str(elcc.iloc[4, col])
    label = label[:-2] if label.endswith(".0") else label
    vals = elcc.loc[elcc[2] == BATTERY_ROW, col]
    BATTERY[(season, label)] = float(vals.min())


def battery_factor(year, month):
    """CDR season: Summer Jun-Sep, Fall Oct-Nov, Winter Dec-Feb, Spring Mar-May (season start dates in CDR 'Unit Details')."""
    if month in (6, 7, 8, 9):
        season, y = "Summer", year
    elif month in (10, 11):
        season, y = "Fall", year
    elif month in (3, 4, 5):
        season, y = "Spring", year
    else:
        season, y = "Winter", year if month == 12 else year - 1  # Jan-Feb belong to the winter that began last December
    y = min(max(y, 2026), 2030)  # CDR covers 2026-2030
    label = f"{y}/{y + 1}" if season == "Winter" else str(y)
    return BATTERY[(season, label)]


def capacity(year, month, hour):
    """Grid capacity in MW for a Texas calendar year, month (1-12) and hour-ending (1-24)."""
    if year < FIRST_YEAR or year > LAST_YEAR:
        raise ValueError(f"year {year} outside {FIRST_YEAR}-{LAST_YEAR}")
    if hour < 1 or hour > 24 or month < 1 or month > 12:
        raise ValueError(f"bad month {month} or hour-ending {hour}")
    c = CHANGE[year]
    base = SUMMER_CAP if month in SUMMER_MONTHS else WINTER_CAP
    return (base + c["flat"] + c["other"]
            + c["solar"] * FACTOR[("solar", month, hour)]
            + c["wind"] * FACTOR[("wind", month, hour)]
            + c["battery"] * battery_factor(year, month))


def show_year(year, hours=(6, 12, 17, 19, 21)):
    """Print capacity (MW) by month at a few hour-endings, for checking."""
    print(f"Capacity {year} (MW), REAL_ONLY={REAL_ONLY}; columns = hour-ending {list(hours)}")
    for m in range(1, 13):
        print(f"  month {m:2d}: " + "  ".join(f"{capacity(year, m, h):9,.0f}" for h in hours))
