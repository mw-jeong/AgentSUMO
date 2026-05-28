# Tutorial — Seoul Lane Closure

This walkthrough reproduces one of the paper's headline case studies: assessing
the impact of a lane reduction on Teheran-ro, near Gangnam Station, Seoul.
You'll generate a baseline simulation, apply a lane reduction, rerun the
pipeline, and compare the two outcomes.

## Step 1 — Generate the baseline

Open the web interface and paste:

```text
Simulate traffic in Gangnam Station, Seoul within a 1 km radius for one hour
under medium traffic conditions.
```

The Planner Agent will:

1. Classify this as a **Simple** task (clear objectives, all parameters
   present).
2. Confirm the inferred parameters — city: Gangnam-Station, radius: 1 km,
   duration: 3600 s, traffic condition: medium.
3. Run the Scenario Generation pipeline:

   - `osm_extract` — downloads OSM data within the bounding box
   - `net_convert` — converts to SUMO `.net.xml`
   - `trip_generate` — generates random OD demand
   - `route_generate` — assigns shortest-path routes
   - `sumo_runner` — executes the simulation, producing `tripinfo.xml`,
     `edgeData.xml`, and `edgeData_emission.xml`
   - `xml_to_sqlite_tool` — stores the run as `simulation_id = "baseline"`

When the run completes, the file explorer shows the new artifacts under
`outputs/networks/` and `outputs/simulations/`. The map renders the network
with edge density as a heatmap overlay.

## Step 2 — Apply the lane reduction

Paste:

```text
Reduce the lanes on Teheran-ro by one in the current network. Save the result
as a new scenario called "teheran_lane_reduction".
```

The agent will:

1. Classify this as a **Complex** task (multi-step: locate the road, validate
   the operation, apply, regenerate trips).
2. Call `analyze_road_details_tool` on `target_road_name = "Teheran-ro"` with
   `reference_location` = the Gangnam-Station coordinates and
   `radius_km = 1.0`, to identify which edges to modify.
3. Call `visualize_policy_target_tool` to render a preview of the targeted
   edges on the map — confirm before proceeding.
4. Call `reduce_lanes_tool` with `reduce_by = 1`, producing a modified network.
5. Re-run `trip_generate` and `route_generate` against the new network (lane
   reduction can change edge IDs), then `sumo_runner`, then
   `xml_to_sqlite_tool` with `simulation_id = "teheran_lane_reduction"`.

```{tip}
You can apply policies graphically too: enter edge-selection mode via the map
toolbar, click the road segments you want, choose "Lane Reduction" from the
dropdown, and submit. The agent receives a structured marker and applies the
same `reduce_lanes_tool` call without you having to type any edge IDs.
```

## Step 3 — Compare the two scenarios

Paste:

```text
Compare the two scenarios in terms of average trip duration, waiting time,
average speed, and total CO2 emissions. Highlight the five roads whose
density changed the most.
```

The agent will:

1. Issue SQL queries against `trips` (for trip-level metrics) and
   `edge_metrics` (for road-level density), joined to `edge_info` for human
   readable road names.
2. Return a markdown table with the four KPIs side-by-side and percentage
   changes.
3. Render a **comparative heatmap** in the center panel showing per-edge
   density delta between the two scenarios.

## Step 4 — Generate an HTML report

For sharing with stakeholders:

```text
Generate an HTML report comparing the baseline and the lane-reduction scenario.
```

The agent invokes `db_based_simulation_report_tool`, which queries the SQLite
database for both `simulation_id`s, computes KPIs, ranks the most congested
roads, renders an inline SVG of the study-area network, and writes a
self-contained HTML file to `outputs/reports/`. Open it in a new tab to share.

## What you've practiced

- Natural-language scenario generation (Simple task).
- Policy intervention with the Planner Agent's clarify-before-execute step
  (Complex task).
- Cross-scenario comparison through SQL on the structured database.
- Visual comparative analysis via the comparative dashboard.
- Automated HTML report export.

Continue with [Manhattan Post-Event Management](manhattan_post_event.md) for a
more agentic case, or jump to the
[AgentSUMO MCP Server reference](../mcp_servers/agentsumo/index.md) to see
every tool the agent called along the way.
