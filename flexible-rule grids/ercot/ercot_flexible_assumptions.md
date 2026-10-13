# ERCOT flexible-load headroom: documentation and assumptions

Started 2026-10-13. Applies to the scripts in `flexible-rule grids/ercot/`.

- **Method:** headroom (same algorithm as `prediction scripts/v1/erco_headroom_forecast.py`), but demand = ERCOT's hourly
  forecast MINUS its big new loads. Result = how much big flexible load ERCOT can absorb in total at each curtailment rate,
  to compare against how much big load wants in.
- **Which loads are subtracted:** ERCOT's own forecast columns, hour by hour (no number chosen by us):
  `ercot_contracts` (signed agreement + money committed) and `ercot_officer_letters` (unsigned, vouched for by a utility
  officer). Both are ERCOT-adjusted already (180-day delay; data centers × 0.498; officer letters × 0.554).
- **Assumption: all of those loads are treated as "flexible-eligible."** That may be too broad:
  - **The law's scope:** Texas SB 6 covers new large loads above a size threshold (believed 75 MW, from memory, needs
    checking) connecting after a certain date. Some projects in those columns may be smaller, older, or exempt.
  - **Load type:** the columns mix data centers, crypto, hydrogen, oil & gas and factories. If only some of these can
    realistically curtail, subtracting all of them overstates the flexible pool.
  - **Some may already be running:** loads that came online in 2025–26 are already inside the historical peak used as
    capacity. Subtracting them from future demand while they are also in the base slightly double-counts room. Small early on.
- **Cross-check planned:** ERCOT's CDR (Dec 2025) SB 6 scenario cuts the 2030 summer firm peak from ~132 to ~91 GW
  (~41 GW curtailed at peak). Our subtraction at the 2030 peak hour should land in a similar range.
- **Inherited from prediction v1** (see `prediction scripts/v1/prediction_v1_assumptions.md` and the project CLAUDE.md
  "Known limit" section): capacity function, typical-day renewable factors, evening-capacity caveat, grid as one point.

## Build and results (2026-10-13)

- `ercot_split_forecast.py` → `ERCO_forecast_base.csv` (normal grid) + `ERCO_forecast_bigloads.csv` (contracts + officer
  letters), UTC end of hour. Checks: 0 time mismatches, 0 blanks, base + big = `ba_totals/ERCO_forecast.csv` exactly.
- Cross-check vs CDR Dec 2025 SB 6 scenario (summer firm peak after curtailment, GW): CDR 85.4 / 88.2 / 89.3 / 91.0 for
  2027–2030 vs our normal-grid summer peak 87.7 / 88.7 / 89.5 / 90.2. Big loads at our peak hour 16.1 / 32.1 / 38.4 / 47.8
  vs CDR's curtailed 12.7 / 27.1 / 32.9 / 41.3 (CDR uses a newer forecast and also removes other demand response). Match.
- `ercot_flexible_headroom.py` (imports `capacity()` from `prediction scripts/v1/erco_capacity.py`, REAL_ONLY = False):
  headroom for big flexible loads, GW, at 0.1 / 0.25 / 0.5 / 1 / 5% vs big load average:
  2026 10.0 / 11.8 / 13.7 / 16.0 / 24.2 vs 6.9 · 2028 11.4 / 13.0 / 14.6 / 16.6 / 23.5 vs 30.0 ·
  2030 9.3 / 11.1 / 12.9 / 14.9 / 21.6 vs 48.2 · 2035 9.4 / 12.1 / 14.9 / 17.6 / 24.7 vs 57.0 ·
  2044 0 / 0 / 0 / 2.0 / 15.4 vs 57.1. Big loads exceed even the 5% headroom from 2028. 2032 dip = EIA's 2032 coal/gas
  retirements before its model-built additions.

## One 100 MW site (2026-10-13)

- `ercot_split_forecast.py` now also saves `ERCO_forecast_officer_letters.csv` (rerun: base + bigloads came back byte-identical).
- `ercot_site_100mw.py` (copy of Task C on the flexible split): demand = forecast − officer letters (contracts stay as firm demand),
  + 100 MW, cap = v1 `capacity()`. **Queue assumption:** the site sits behind every contracted load and ahead of every
  officer-letter load (unverified; how ERCOT orders curtailment under SB 6 is in the ignorance ledger). All cuts are floors
  (averaged weather); no longest-event number (fake hour order).
- Result (REAL_ONLY = False), hours cut / curtailment rate: 2026 1 / 0.01% · 2027 21 / 0.23% · **2028 358 / 3.99%** ·
  2029 738 / 8.3% · 2030 1,618 / 18.3% · 2032 3,453 / 39.0% (EIA retirement dip) · 2035 1,472 / 16.6% · 2044 2,166 / 24.6%.
  Nearly every cut hour is a full 100 MW switch-off (2028: 346 of 358).
