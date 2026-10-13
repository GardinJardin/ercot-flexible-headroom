import os

import pandas as pd

# Rebuilds ERCOT's installed generator size (MW) per type for every month, from EIA-860M (monthly generator inventory,
# data/EIA860M_august_generator2026.xlsx = "as of August 2026", the latest real file on 2026-10-13; the Sep-Dec 2026 links
# on EIA's page redirect to an error page). Used as the denominator of the capacity factors (output / installed size).
# Sheets used: Operating (generators running in Aug 2026, incl. standby/out-of-service status) + Retired (with retirement
# month/year), both filtered to Balancing Authority Code == "ERCO". A generator counts in a month if its operating
# month/year is on or before that month and it is not retired, or retired in a LATER month (not counted in its
# retirement month). Size = Nameplate Capacity (MW) (Net Summer Capacity also exists; nearly identical in total for
# solar/wind). Solar nameplate here is AC; DC Net Capacity (panel size) is ~18% larger and not used.
# Months: 2018-12 (Texas month of the first fuel hour) -> 2026-08 (the inventory date). Generators that started after
# August 2026 aren't in the file, so no later months are written.
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project folder: v1 -> prediction scripts -> project
SOURCE = os.path.join(root, "data", "EIA860M_august_generator2026.xlsx")
OUT = os.path.join(root, "data", "ERCO_installed_capacity_monthly.csv")
FIRST_MONTH = "2018-12"
LAST_MONTH = "2026-08"
# EIA-860M Technology label -> type. "All Other" (refinery/chemical-plant byproduct and purchased-steam units) is not
# renewable and is left out, as are all fossil, nuclear and flywheel types.
TYPES = {
    "Solar Photovoltaic": "solar",
    "Solar Thermal with or without Energy Storage": "solar",
    "Solar Thermal without Energy Storage": "solar",
    "Onshore Wind Turbine": "wind",
    "Conventional Hydroelectric": "hydro",
    "Wood/Wood Waste Biomass": "other_renewables",
    "Landfill Gas": "other_renewables",
    "Other Waste Biomass": "other_renewables",
    "Municipal Solid Waste": "other_renewables",
    "Geothermal": "other_renewables",
    "Batteries": "battery",
}

op = pd.read_excel(SOURCE, sheet_name="Operating", header=2)
ret = pd.read_excel(SOURCE, sheet_name="Retired", header=2)
op = op[op["Balancing Authority Code"] == "ERCO"].copy()
ret = ret[ret["Balancing Authority Code"] == "ERCO"].copy()
op["retired"] = pd.NaT
ret["retired"] = pd.to_datetime(dict(year=ret["Retirement Year"], month=ret["Retirement Month"], day=1))
gens = pd.concat([op, ret], ignore_index=True)
gens["start"] = pd.to_datetime(dict(year=gens["Operating Year"], month=gens["Operating Month"], day=1))
gens["type"] = gens["Technology"].map(TYPES)
print(f"ERCO generators: {len(op)} operating, {len(ret)} retired")
print("Technologies left out:", sorted(gens.loc[gens["type"].isna(), "Technology"].unique()))
gens = gens[gens["type"].notna()]

rows = []
for month in pd.date_range(FIRST_MONTH, LAST_MONTH, freq="MS"):
    on = (gens["start"] <= month) & (gens["retired"].isna() | (gens["retired"] > month))
    mw = gens[on].groupby("type")["Nameplate Capacity (MW)"].sum()
    for t in ["solar", "wind", "hydro", "other_renewables", "battery"]:
        rows.append([month.strftime("%Y-%m"), t, float(mw.get(t, 0.0))])
df = pd.DataFrame(rows, columns=["month", "type", "installed_MW"])
df.to_csv(OUT, index=False)
print(f"saved {OUT}: {len(df)} rows, {FIRST_MONTH} -> {LAST_MONTH}")
print(df[df["month"].str.endswith("-12") | (df["month"] == LAST_MONTH)].pivot(index="month", columns="type", values="installed_MW").round(0))
