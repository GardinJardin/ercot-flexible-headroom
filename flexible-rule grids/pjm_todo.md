# PJM port: everything needed (parked 2026-10-13)

Goal: the same result as `ercot/ercot_flexible_headroom.py` for PJM — how much big flexible load PJM can absorb at
0.1 / 0.25 / 0.5 / 1 / 5% curtailment per year, next to how much big load wants in. Status: **parked**; ERCOT goes first.
Approach (user, 2026-10-13): **copy the ERCOT scripts and modify them for PJM** (no shared-calculator refactor). Put the
work in `flexible-rule grids/pjm/`, matching `ercot/` (not confirmed yet).

Why PJM: closest ERCOT analogue — official shortfall (2028/29 capacity auction ~6.8 GW short of the reliability
requirement) plus a curtail-first proposal for new large loads (see rick-prime `projects/a16z-academy/research/2026-10-13-ercot-like-bas.md`).

## Datasets (found and opened by an agent 2026-10-13 in scratch; NOT yet approved or downloaded into the project)

| # | Purpose | PJM version | Status |
|---|---|---|---|
| 1 | Capacity base (highest demand served) | EIA-930 code `PJM`: bulk six-month files 2016+ (same columns as ERCOT, `Demand (MW) (Adjusted)`), API region-data 2019→now; 20 subregions (AE, AEP, AP, ATSI, BC, CE, DAY, DEOK, DOM, DPL, DUQ, EKPC, JC, ME, PE, PEP, PL, PN, PS, RECO) | Same as ERCOT. No PJM footprint change found after 2015 (from memory, unverified) |
| 2 | Future hourly demand | PJM 2026 Load Forecast (Jan 2026), page https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process. Hourly: `https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/<zone>-hourly-forecast.zip` (22 zones, one xlsx per year 2026–2046, ~16 MB each, columns forecast_date, current_hour_ending 1–24, _NAME_ = final_load, ~400 weather-year columns). Big loads: Table B-9 in `.../2026-load-report-tables.xlsx` (yearly MW by zone; RTO 6,403 MW 2026 → 16,242 2028 → 33,707 2030 → 55,089 2033 → ~81.8 GW 2046). Monthly zone peak/energy: `.../library/reports-notices/load-forecast/2026-load-report-data.xlsx`. Large-load breakdown: `.../2026-load-adjustment-breakdown-for-capacity-obligations.xlsx` | **Hourly files include big loads but don't split them out** |
| 3 | Future capacity changes by type | EIA AEO2026 suptab 54.10–54.13 + 56.10–56.13 (PJM East, West, ComEd, Dominion), `https://www.eia.gov/outlooks/aeo/supplement/excel/suptab_54.10.xlsx` etc.; scenario cb2026; same row codes as Texas (prefix EPD010:/REG010: etc.) | Sum the 4 regions; footprint may not match PJM exactly (unchecked). Has an offshore wind row |
| 4 | Hourly output by fuel | EIA API fuel-type-data, respondent PJM, 2019→now: COL, NG, NUC, OIL, OTH, SUN, WAT, WND | No battery fuel type |
| 5 | Installed size history | EIA-860M `https://www.eia.gov/electricity/data/eia860m/xls/august_generator2026.xlsx` (the `/archive/xls/` path errors for August), BA code `PJM` | Solar 19.3 GW, wind 11.9 GW, batteries 0.66 GW, pumped storage 5.1 GW (net summer) |
| 6 | Battery reliability factor | PJM ELCC class ratings, 2028/29 BRA: `https://www.pjm.com/-/media/DotCom/planning/res-adeq/elcc/28-29-bra-elcc-class-ratings.pdf`; series DY28/29–DY42/43: `.../elcc/preliminary-elcc-class-ratings-for-period-dy28-dy42-elcc.pdf`. 4-hr storage 59% (28/29) → 57 → 42 → 34 → 30 → 26% (33/34); onshore wind 34%, offshore 60%, solar 7–10% | **One number per delivery year (June–May)**, no seasons/hours; only DY28/29 and 29/30 binding |
| 7 | Cross-check | 2028/29 BRA 6,831 MW short of reliability requirement (PJM release, search only); Table B-9 big-load additions (opened) | Usable |

## Script changes (copy of each ERCOT script)

Constant swaps only:
- `erco_bulk.py` → code `PJM`, output `ba_totals/PJM_bulk.csv`; re-download the 18 bulk files (old scratch copy likely gone).
- `erco_fuel_pull.py` → respondent `PJM`, output `data/PJM_fuel.parquet`.
- `erco_installed_capacity.py` → BA code `PJM`.
- `erco_capacity_factors.py` → code + time zone `America/New_York` (zoneinfo, not the string).
- headroom script → PJM files, Eastern time zone, first forecast year 2026.
- Historical subregion total (`PJM.csv`): 20-subregion pull via the pipeline (~280 API calls) — needs the user's go.

Structural:
1. **New forecast reader:** pull 22 zones × 21 yearly files (~7 GB; zip range requests allow single years), average the
   weather-year columns, sum zones, convert to UTC end of hour. PJM's hour convention / DST handling is **unverified** —
   run the same per-day 23/25-row check as ERCOT. First check whether PJM publishes a single RTO-total hourly file.
2. **Big-load split:** no hourly big-load columns, so subtract Table B-9's yearly RTO MW as a flat block from every hour.
3. **Capacity:** sum AEO 54.10–54.13 and 56.10–56.13 before the anchored formula; add an offshore wind type.
4. **Batteries:** PJM ELCC by delivery year (June–May; Jan 2029 uses 2028/29) instead of the CDR's season × 2-hour lookup.
- Unchanged: capacity formula (proven peak + change × factor), overload rule, headroom solve, 5 rates, output table.
- EIA subregion names differ from forecast zone names (BC=BGE, CE=COMED, AP=APS, DUQ=DLCO, PE=PECO, PEP=PEPCO, JC=JCPL,
  ME=METED, PN=PENLC, DAY=DAYTON); forecast has FE_EAST, OVEC, UGI with no EIA subregion. Only matters for zone-level work.

## Open decisions (user)
1. Forecast: PJM hourly files with big loads subtracted flat (Claude's pick) vs. historical shape scaled to PJM's monthly forecast peaks/energy (one small file).
2. Batteries: PJM's yearly ELCC applied to every hour (Claude's pick).
3. Offshore wind factor: use onshore wind's (Claude's pick) or leave offshore out.
4. Folder: `flexible-rule grids/pjm/`.
5. Approve datasets 1, 3, 4, 5, 7 before download.
