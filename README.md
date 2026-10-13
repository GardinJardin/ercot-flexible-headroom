# ERCOT flexible-load headroom

How much big flexible (curtailable) load, such as data centers, can ERCOT (the Texas grid) absorb at a given yearly curtailment rate, and how does that compare with how much big load wants to connect? And for one flexible site of a given size, how much of the year does it get switched off?

Live app: `<link coming>`

## Method

- **Demand:** ERCOT 2025 Long-Term Load Forecast (hourly, 2025-2044), split into the normal grid and big new loads (signed contracts plus officer letters, as ERCOT already adjusted them for delays and drop-outs).
- **Hourly capacity:** the highest demand ERCOT has actually served (91,088 MW summer / 80,380 MW winter, EIA-930), plus EIA AEO2026 additions minus retirements after 2026. Gas, coal and nuclear count at full size every hour; solar and wind are weighted by measured month-by-hour output factors; batteries by ERCOT CDR ELCC (reliability) factors.
- **Headroom:** the flat 24/7 load whose yearly curtailed share equals the target rate, found by root-finding.
- **One site:** add a flat site of the chosen size to demand and count the hours and energy above capacity.

## Key caveats

- **Averaged weather.** The forecast averages 17 past weather years, so peaks are milder than any real year and there are no extreme events. Curtailment numbers are floors.
- **Hour order is not real.** Monthly load is laid onto 2008's calendar pattern, so yearly totals hold but specific dates, hours and run lengths of curtailment do not.
- **The grid is one point.** Room is checked ERCOT-wide; local transmission limits are not modeled.
- **Evening capacity is probably overstated.** The summer peak was served at 6 pm with solar still producing, but the cap is applied to every hour, including after sunset.
- **Includes EIA model-built additions.** Future capacity uses EIA's projected (not yet real) plants as well as announced projects; a real-projects-only switch exists as a check.
- **Site queue order is assumed.** The single site sits behind every contracted load and ahead of every officer-letter load. How ERCOT orders curtailment under Texas SB 6 is unverified.
- All forecast big loads are treated as flexible-eligible, which may be too broad (SB 6 scope and load type not checked per project).

## Data sources

EIA-930 (hourly demand and generation), EIA-860M (August 2026 generator inventory), EIA AEO2026 supplemental tables 54.1 and 56.1, ERCOT 2025 Long-Term Load Forecast, ERCOT Capacity, Demand and Reserves report (CDR), December 2025.

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
```

## Repo layout

- `prediction scripts/v1/` - capacity function, renewable output factors, installed capacity and the headroom forecast, with `prediction_v1_assumptions.md`.
- `flexible-rule grids/ercot/` - forecast split into normal grid and big loads, flexible-load headroom, the single-site run, with `ercot_flexible_assumptions.md`.
- `data/` - downloaded inputs (ERCOT forecast and CDR, EIA AEO and 860M tables) and derived factor tables.
- `ba_totals/` - hourly ERCOT totals pulled from EIA-930 and the converted load forecast.
- `eia_pipeline.py` - pulls EIA-930 data; needs your own EIA API key in `.env` as `API_KEY`.
