# Prediction v1: documentation and assumptions

Written by the user 2026-10-13, with factual corrections from the ERCOT 2025 LTLF report applied (marked "corrected").
Becomes the header of the prediction v1 script once it exists.

- **Data source:** ERCOT Adjusted Forecast (2025 Long-Term Load Forecast, hourly, ERCOT + 8 weather zones, 2025–2034).
  It predicts future hourly load by adding a base forecast (driven by weather and by projected numbers of homes and
  businesses), EV charging, existing flexible loads (mostly crypto mines), and large-load projects already filed with
  power companies (shrunk for typical delays, oversizing and drop-outs), minus rooftop solar.
- **This forecast is the baseline underneath any new deal made with our software.** So it assumes the software is not
  used on loads already filed with power companies and counted in the forecast (signed contracts or officer letters,
  i.e. unsigned requests a power-company executive vouches for). Otherwise the load is counted twice.
- **Corrected:** the baseline already includes flexible load from crypto mines (modeled from how they have reduced
  use at peak hours and high prices). It does NOT include any data center that has agreed to curtailment: every
  data center in the forecast is assumed to run nonstop. This software can be used to help create flexible-connect
  deals for specific loads at a specific curtailment rate.
- **Corrected:** the forecast only counts large loads that have already filed, and projects usually file only a few years
  before they run. So the later forecast years (roughly 2030+) likely undercount large loads. ERCOT republishes the
  forecast yearly, but there is always a lag between loads that will actually be added and loads the forecast knows about.
- **Grid capacity:** the forecast's demand peaks are not tied to what the grid can actually supply, so grid potential is
  measured with historical demand peaks (the highest demand the grid has actually served) instead.
- **Corrected:** baseline growth (excluding large loads, flexible loads, EVs and rooftop solar) comes from how
  electricity use responded to weather, time of day and the number of homes and businesses in 2019–2024, applied to
  forecast numbers of homes and businesses (from Moody's economic forecasts). It does NOT use climate models: it replays
  past weather (2008–2024) and averages the results, so it assumes future weather looks like the past (no climate change).
- **Drop-outs are already priced in; we don't change them.** The forecast already shrinks filed large-load projects:
  officer-letter projects are counted at 55.4% (about 45% assumed never built), and new data centers at 49.8% of the
  power they requested (built sites have historically used about half). Plus a 180-day delay on every project.
  We keep these numbers as they are.
- **Averaged weather = milder peaks, no freak events.** The forecast averages the results of 17 past weather years,
  so its peaks are milder than any real year and it does not include extreme weather events (heat domes, winter storms
  like Uri 2021). Possible later addition: an overlay of predicted extreme events.
- **Grid capacity frozen at the historical peak.** Assumes no new power plants or lines get built. This underestimates
  available headroom, and since forecast load keeps growing, headroom will probably go negative after a few years.
- **The whole grid is treated as one point.** Room is checked ERCOT-wide; local power-line limits (e.g. a site in West
  Texas blocked locally while the state as a whole has room) are not modeled.
- **Zero efficiency gains.** The forecast assumes homes and appliances don't get more efficient, which overstates future
  household load and so underestimates headroom.
- **Not accurate for specific hours or dates.** The forecast decides how much load each month has, then places those
  values onto days and hours by copying 2008's calendar pattern. So the yearly totals and monthly spread are usable, but
  the load at a specific date and hour is not a real prediction. Fine for our yearly curtailment rate (a sum over the
  year, where order doesn't matter); not usable for questions about when, or how many hours in a row, curtailment happens.
- **No weather or climate trends.** Future weather is not predicted: the forecast replays the actual recorded weather of
  each past year (2008–2024) as if it happened again, then averages the 17 results. So it does not account for changes in
  larger weather or climate trends (e.g. hotter summers, milder winters, more frequent extremes).
- **If grid capacity comes from ERCOT's capacity reports (CDR / LTSA) instead of history:** it counts generation only
  (power plants, not power lines, so local line limits are still ignored), and it swaps proven capacity (the highest
  demand the grid has actually served) for planned capacity (plants ERCOT expects to be built and available).
- **Future grid capacity** (user, 2026-10-13): predicted by adding future generation addition forecasts to the total
  2016-2026 calculated grid capacity (highest demand actually served: 91,088 MW summer, 80,380 MW winter; corrected from
  2016-2024 to match the script), for now ignoring transmission constraints. Additions count from 2027 on, since the
  2016-2026 peaks already reflect everything built before then.
- **Evening capacity unproven:** the summer cap was set at 6 pm with solar still producing, but is applied to every hour,
  including after sunset, so evening headroom is probably overstated. Details in the project CLAUDE.md, section
  "Known limit: historical peak demand as grid capacity" (applies to every headroom script).
- **Capacity function (user, 2026-10-13), to be built as `erco_capacity.py`:** capacity(year, month, hour) = proven peak
  (91,088 MW summer / 80,380 MW winter) + each type's additions since 2026 × that type's factor at (month, hour) −
  retirements the same way ("anchored", not a bottom-up sum of every plant). Gas/coal/nuclear count at full (summer)
  size every hour. Uses both real-project and EIA model-built additions, with a switch to run real-projects-only as a check.
- **Batteries:** counted as additions after 2027 only (2026 batteries are already inside the proven peak) × ERCOT's
  reliability factor from the CDR (ELCC sheet, 2026–2030, held flat after 2030). The CDR publishes that factor at only
  2 hours per season (e.g. summer 5 pm and 9 pm); every hour of that season uses the LOWER of the two (user, 2026-10-13):
  simple and conservative, small effect since batteries matter mainly at peaks. Battery handling to be revisited Oct 14
  with EIA-930 hourly battery output, EIA-860 storage hours and EIA's future battery sizes.
- **Future renewable sizes are yearly** (user, 2026-10-13): how much solar, wind and other renewables Texas will have
  is one number per year, out to 2050 (EIA AEO2026: solar and wind separately from Table 56.1, other renewables as the
  remainder of Table 54.1's renewables total; e.g. solar 34.8 GW in 2025 → 51.5 GW in 2027). Nothing within a year:
  a plant added in 2028 counts for all of 2028.
- **Renewable output shape is a "typical day" per month** (user, 2026-10-13): each source's factor (output ÷ size) is
  24 hour-of-day values per month (288 per source), averaged from measured hourly output. It varies by month and hour
  of day, but every day within a month gets the same shape, so individual days (a cloudy or windless day) are not
  represented.
- **Capacity function built (2026-10-13, `erco_capacity.py`), choices made while building:** (1) EIA's solar/wind table has additions as totals
  only (no planned/unplanned split, no retirements); for the real-projects-only switch they are cut by the renewables planned share from
  the all-types table, which is crude. (2) Other renewables (biomass, waste) counted at full size every hour; the amount is tiny (8 MW in
  2027, 145 MW in 2044). (3) Batteries use ERCOT's 2-hour row: the Texas battery fleet averages 1.65 hours (EIA-860M, 30,020 MWh / 18,204 MW).
  (4) ERCOT's seasons for the battery factor: summer Jun-Sep, fall Oct-Nov, winter Dec-Feb, spring Mar-May (the workbook's own season-month
  table is empty; these are its season start dates). January-February belong to the winter that began the December before. (5) With these
  inputs, headroom is zero from 2027 on: the load forecast (138 GW peak in 2030) grows far faster than EIA's capacity additions
  (about 98 GW in 2030), so nearly every hour is already over the cap. The forecast counts large loads that EIA's baseline has no plants for.
