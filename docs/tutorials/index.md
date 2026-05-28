# Tutorials

## Video tutorial

A guided walkthrough of AgentSUMO covering setup, the web interface,
issuing natural-language requests, applying policy interventions, and using
the SQLite-backed dashboard for cross-scenario comparison.

```{raw} html
<div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; border-radius: 8px; background: #111518; display: flex; align-items: center; justify-content: center;">
  <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #8aa69c; font-family: ui-sans-serif, system-ui, sans-serif;">
    <div style="text-align: center;">
      <div style="font-size: 1.2em; color: #7ab800; font-weight: 600;">Tutorial Video</div>
      <div style="margin-top: 0.4em;">Coming soon (TBD)</div>
      <div style="margin-top: 0.4em; font-size: 0.9em;">A YouTube embed will replace this placeholder.</div>
    </div>
  </div>
</div>
```

## Launching the web interface

AgentSUMO ships with a browser-based interface that combines the agent
chat, an interactive map, and a database-driven dashboard in a single
three-panel view.

```bash
source .venv/bin/activate
python web.py
```

The FastAPI server starts on `http://localhost:8000`. The backend exposes
RESTful endpoints for files, networks, simulations, and database queries,
plus a WebSocket channel for real-time chat and tool-execution updates.

## Three-panel layout

```
┌──────────────┬──────────────────────────┬─────────────┐
│ File Explorer│  Map  /  Dashboard       │  Chat       │
│  (left)      │  (center)                │  (right)    │
│              │                          │             │
│  networks/   │  Mapbox GL JS:           │  Agent      │
│  trips/      │   - road network         │  responses  │
│  simulations/│   - density heatmap      │  Tool calls │
│  reports/    │   - vehicle replay       │  Progress   │
│  visualiza-  │   - difference compare   │             │
│   tions/     │                          │             │
└──────────────┴──────────────────────────┴─────────────┘
```

### Left — File explorer

A hierarchical tree of every artifact AgentSUMO has produced, grouped by
output category: networks, trips, simulations, reports, visualizations.
Clicking a file previews it (XML inline, PNG inline, HTML opens in a new
tab). Clicking `simulations.db` opens the dashboard.

### Center — Map and dashboard

The center panel hosts the primary view. By default it shows an interactive
Mapbox map with the SUMO road network drawn as a GeoJSON layer. The same
panel can switch to several other modes:

- **Heatmap** — color-coded edge-level metric (density, speed, emissions)
  overlaid on the network.
- **Replay** — frame-by-frame vehicle replay using the JSON capture from
  `sumo_runner`. Playback controls support play/pause, seek bar, and speeds
  of 1×, 5×, 10×, 15×.
- **Difference heatmap** — visual diff between two scenarios with symmetric
  color scaling centered on zero.
- **Comparative dashboard** — KPI table (avg trip duration, waiting time,
  speed, CO₂), trip-duration distribution histograms, top congested roads,
  with cross-scenario percentage changes color-coded green/red.

The map's toolbar exposes basemap switching via
{menuselection}`Toolbar --> Basemap --> Mapbox dark / streets / satellite`
and an {guilabel}`Edge Selection` tool for manual policy targeting.

### Right — Chat sidebar

The chat sidebar streams the Planner Agent's responses in real time over a
WebSocket. It shows tool invocations as they happen (with progress
indicators), the agent's clarification questions (Interactive Planning
Protocol), and final answers including inline tables and SQL results.

## Agent-driven map control

The Planner Agent does not render the map itself — it embeds **structured
markers** in its natural-language responses, and the client parses them to
trigger map operations. The three markers in the current implementation are:

| Marker | Effect |
|---|---|
| `[SEARCH_LOCATION:Gangnam Station]` | Geocode the location and drop a pin on the map. |
| `[SHOW_ROUTE:e1,e2,e3\|#39ff8a\|net_file]` | Highlight a route across the listed edges in the given color. |
| `[EDGE_SELECT]` | Activate edge-selection mode on the map, prompting the user to click road segments. |

Markers are stripped from the user-visible reply, so the agent's natural
language stays clean while the map updates automatically.

## Visual policy targeting

Rather than typing SUMO edge IDs, you can specify a policy target by
clicking on the map:

1. Click the {guilabel}`Select` tool in the map toolbar.
2. Click road segments — each selected edge is added to a selection panel
   showing its name, lane count, speed limit, and length.
3. Choose a policy type from the {guilabel}`Policy` dropdown (lane
   reduction, road closure, speed change, rerouter installation).
4. Click {guilabel}`Submit`. The client sends a structured message to the
   agent containing the edge IDs and the requested intervention.
5. The agent applies the corresponding policy tool (`reduce_lanes_tool`,
   `edge_edit_tool`, `speed_limit_edit_tool`, etc.) and re-runs the
   pipeline.

This spatial selection mechanism is the bridge between the visual map and
the agent's tool layer.

## Simulation replay

When `sumo_runner` executes, it captures vehicle states (position, speed,
heading) at configurable time intervals via SUMO's TraCI and produces a
frame-indexed JSON file. The replay layer reads that file and renders
vehicles as points with a four-stop speed-based color gradient:

- Red — stationary ($v \approx 0$)
- Orange — slow ($v \approx 5$ m/s)
- Green — normal flow ($v \approx 10$ m/s)
- Cyan — free flow ($v \geq 15$ m/s)

Linear interpolation between consecutive frames keeps motion smooth at any
playback speed.

## Database-driven dashboard

The comparative dashboard queries `simulations.db` directly via REST
endpoints:

- `/api/db/simulations` — list every `simulation_id`.
- `/api/compare?ids=A,B` — return KPIs for selected scenarios with
  percentage deltas vs. the first.
- `/api/dashboard?id=baseline` — return the full set of metrics for one
  simulation.

When two or more scenarios are selected, the dashboard displays percentage
changes color-coded green (improvement) and red (degradation). Trip-duration
distributions are shown as horizontal bar charts with configurable time
buckets. The top-N most congested roads are ranked by length-weighted
average density, with clickable entries that highlight the corresponding
segments on the map.

## Automated HTML report

The dashboard's {guilabel}`Export Report` button calls
`db_based_simulation_report_tool`, which renders a self-contained HTML
report from the database. The report includes the full KPI tables, the
trip-duration histograms, the top congested roads, an inline SVG of the
study area with the busiest edges highlighted, and cross-scenario
comparison if multiple `simulation_id`s are present. Reports are served at
`/api/report/<path>` and can be opened in a new tab or downloaded for
offline review.

## REST API

The web backend is built on FastAPI and exposes ~25 endpoints covering file
inspection, simulation listing, dashboard data, heatmaps, replay,
traffic-light parsing, and SUMO config loading. They are intended for the
built-in client but are stable enough to support custom front-ends or
analytical integrations. Inspect the OpenAPI schema at
`http://localhost:8000/docs` when the server is running.

## Use cases

End-to-end walkthroughs that reproduce the paper case studies. Each starts
from a plain-English prompt and ends with a quantitative comparison stored
in the database.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} Seoul Lane Closure
:link: seoul_lane_closure
:link-type: doc

Close lanes on Teheran-ro near Gangnam Station and quantify the impact.
:::

:::{grid-item-card} Manhattan Post-Event Management
:link: manhattan_post_event
:link-type: doc

Mitigate post-event traffic surges around Madison Square Garden.
:::

:::{grid-item-card} EV Emission Scenario
:link: ev_emission_scenario
:link-type: doc

Compare emissions across 0%, 25%, and 75% electric-vehicle adoption rates.
:::

:::{grid-item-card} Policy Comparison
:link: policy_comparison
:link-type: doc

Webster vs. Green-Wave signal timing in a side-by-side comparative report.
:::

::::

```{seealso}
- [Tools](../mcp_servers/index.md) — reference for every MCP tool the
  Planner Agent invokes during these walkthroughs.
- [Schema](../database/index.md) — structure of `simulations.db`, useful
  for writing your own follow-up SQL after a tutorial.
```

```{toctree}
:hidden:
:caption: Use Cases

seoul_lane_closure
manhattan_post_event
ev_emission_scenario
policy_comparison
```
