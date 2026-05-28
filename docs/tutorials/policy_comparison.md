# Tutorial — Policy Comparison (Webster vs. Green Wave)

This tutorial compares two classical traffic-signal control strategies on a
Seoul corridor: **Webster cycle adaptation** (cycle-length optimization based
on saturation flow) and **Green-Wave offset coordination** (offset
optimization so that platoons travel at signal speed without stopping).

## Step 1 — Generate a baseline with default signals

```text
Simulate traffic in Gangnam Station, Seoul within a 1 km radius for one hour
under medium traffic conditions. Save it as "signal_default".
```

The simulation uses SUMO's default signal timings, generated when the network
was created.

## Step 2 — Apply Webster cycle adaptation

```text
On the same network and routes, apply Webster cycle adaptation to optimize
the traffic light cycle lengths. Save as "signal_webster".
```

The agent calls `tls_adaptation_tool` (which wraps SUMO's
`tlsCycleAdaptation.py`). The tool requires both the network and the route
file, since cycle length is optimized for the actual demand. The output is a
supplementary XML configuration file that overrides default cycle lengths.
The simulation then re-runs with that additional file.

## Step 3 — Apply Green-Wave offset coordination

```text
On the same network and routes, apply Green-Wave offset coordination. Save
as "signal_greenwave".
```

The agent calls `tls_offset_tool` (wrapping SUMO's `tlsCoordinator.py`),
which computes optimal offsets so that signal groups along a corridor turn
green in a coordinated wave.

## Step 4 — Compare

```text
Compare signal_default, signal_webster, and signal_greenwave in terms of:
1. Average trip duration
2. Average waiting time
3. Average speed
4. Total CO2 emissions
Tell me which strategy performs best on each metric and overall.
```

The agent issues a single SQL query against `trips` for the three scenarios
and returns a comparison table. It typically observes that Green-Wave shines
on average speed and trip duration (platoons pass through corridors without
stops) while Webster reduces total waiting time when the corridor is
saturated.

## Step 5 — Generate the cross-scenario HTML report

```text
Generate an HTML report comparing all three scenarios.
```

The report includes the cross-scenario comparison table with percentage
changes for every KPI, trip-duration distribution histograms, the top
congested roads in each scenario, and an inline SVG of the study area for
geographic context.

## What you've practiced

- Signal timing optimization with two different SUMO utilities through
  AgentSUMO's MCP wrappers (`tls_offset_tool`, `tls_adaptation_tool`).
- Reusing a single network + route pair across multiple signal strategies
  (signal control is a supplementary configuration, not a network mutation).
- Three-scenario quantitative comparison through structured SQL.
- Automated cross-scenario HTML report generation.
