# Tutorial — EV Emission Scenario

This tutorial varies the electric-vehicle (EV) ratio in the vehicle fleet to
quantify how fleet composition affects emissions. It demonstrates the
**vehicle type editing** workflow and the **cross-scenario SQL** strength of
AgentSUMO.

## Step 1 — Generate a Seoul baseline

```text
Simulate traffic in Gangnam Station, Seoul within a 1 km radius for one hour
under medium traffic conditions. Save it as "ev_0pct".
```

The default vehicle type distribution is conventional combustion vehicles.
This serves as the 0% EV baseline.

## Step 2 — Create the 25% and 75% scenarios

```text
For the network and routes of ev_0pct, create two variants:
- ev_25pct: 25% of vehicles are electric
- ev_75pct: 75% of vehicles are electric
Run both and store them under their respective simulation_ids.
```

The agent will:

1. Classify as **Complex** (multi-step, multiple scenarios).
2. For each ratio, call `vehicle_type_edit_tool` with the corresponding
   `electric_ratio` parameter against the existing route file. This produces
   a modified route file with the new fleet composition.
3. Re-run `sumo_runner` + `xml_to_sqlite_tool` for each.

```{tip}
EV scenarios reuse the same network and OD matrix — only the vehicle types
change. This is the cheapest kind of variant to produce and the most
informative for emission analysis.
```

## Step 3 — Cross-scenario emission comparison

```text
Compare total CO2, NOx, and PMx emissions across ev_0pct, ev_25pct, and
ev_75pct. Show absolute values and percentage changes versus the baseline.
```

The agent issues a single SQL query joining the three `simulation_id`s in the
`trips` table (or alternatively `edge_metrics` for spatial breakdown), sums
the per-vehicle emission columns, and returns a 3×3 comparison table. The
emission columns come straight from SUMO's HBEFA-based emission model —
see the schema for `trips` in [Database Schema](../database/index.md).

## Step 4 — Per-vehicle insight

```text
For the 75% EV scenario, which vehicle types contributed most to total NOx
emissions? Group by fuel type.
```

The agent joins `trips` to `vehicle_info` on `(simulation_id, trip_id =
vehicle_id)` and groups by `vehicle_info.fuel_type`. Electric vehicles report
zero tailpipe emissions; the remaining NOx comes from the residual
combustion fleet.

## Step 5 — Visualize

```text
Show the per-edge CO2 emission heatmap for ev_0pct and ev_75pct side by
side using the difference mode.
```

The comparative heatmap visualizes the spatial distribution of emission
reduction. Edges with steep declines (highways, ring roads) versus edges
where reductions are subtle (local streets where idling is dominant) become
immediately visible.

## What you've practiced

- Fleet composition editing without re-generating routes.
- Three-way numeric comparison via SQL on the `trips` table.
- Grouping by `vehicle_info.fuel_type` for fleet-level insight.
- Spatial difference visualization for emission distributions.
