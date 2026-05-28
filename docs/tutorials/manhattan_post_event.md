# Tutorial — Manhattan Post-Event Traffic Management

This tutorial reproduces the Manhattan case study from the paper: managing the
post-event traffic surge after a large gathering at Madison Square Garden
(7th Avenue, Manhattan). It exercises the **Agentic** task classification —
the agent decomposes an open-ended policy problem into multiple steps.

## Step 1 — Generate the Times Square baseline

```text
Simulate traffic around Madison Square Garden, New York within a 1.5 km radius
for one hour under heavy traffic conditions.
```

The agent generates a Manhattan / Times Square / Penn Station network and a
baseline simulation. Save this run as `simulation_id = "msg_baseline"` when
prompted.

## Step 2 — Inject a post-event surge

The paper models a post-event surge by significantly increasing the vehicle
count departing from the venue area. Paste:

```text
Test strategies to mitigate post-event traffic flow near Madison Square
Garden. Generate a continuous flow of 600 vehicles per hour leaving from
7th Avenue at MSG between 18:00 and 19:00, then run the simulation and store
it as "msg_surge".
```

The agent will:

1. Classify this as **Agentic** — multi-step planning with policy intent.
2. Call `flow_generation_tool` with `source_location = "Madison Square Garden,
   New York"`, `destination_location` (a downtown sink), `begin = 64800`,
   `end = 68400`, `vehs_per_hour = 600`, `use_geocoding = True`.
3. Re-run the simulation, ingest into SQLite as `msg_surge`.

## Step 3 — Ask the agent to propose mitigations

```text
Recommend at least two mitigation strategies. For each, apply it as a separate
scenario (msg_strategy_A, msg_strategy_B) and compare them against
msg_surge.
```

The agent decomposes the problem:

- Strategy A: optimize traffic light offsets on the corridors near MSG
  (`tls_offset_tool`).
- Strategy B: adapt traffic light cycle lengths on the same corridors
  (`tls_adaptation_tool`).

Each strategy runs through `sumo_runner` + `xml_to_sqlite_tool`. The agent
then queries the database for total density, waiting time, and average speed
on the targeted corridors across the three scenarios.

```{note}
You can intervene at any step. If you'd rather try a third strategy (e.g.,
closing a specific street to general traffic with `edge_edit_tool`), simply
type the request in the chat.
```

## Step 4 — Use the spatial heatmap

Switch the center panel to **Difference Heatmap** mode and compare
`msg_strategy_A` against `msg_surge`. Edges where density dropped relative to
the surge are shaded blue; edges where density rose are red. This gives a
visual diagnosis the aggregate KPIs cannot:

```text
Compare strategy A and strategy B visually. Which strategy reduced density
most near Madison Square Garden?
```

The agent answers with a road-name-resolved summary
(`get_road_names_tool`) and a length-weighted density aggregation.

## Step 5 — Export the comparative report

```text
Generate an HTML report comparing msg_surge, msg_strategy_A, and
msg_strategy_B.
```

The resulting report includes a cross-scenario comparison table with
percentage changes for every KPI, the top congested roads in each scenario,
and an inline SVG of the study area.

## What you've practiced

- Continuous-flow demand injection (`flow_generation_tool`).
- Agentic decomposition: the agent proposed multiple strategies and applied
  each independently.
- Visual difference comparison on the map.
- Three-way scenario comparison through the HTML report.
