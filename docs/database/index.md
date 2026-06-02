# Schema

After SUMO produces XML output, AgentSUMO's `xml_to_sqlite_tool` parses it
into a relational SQLite database (`simulations.db`) — the structured
representation of simulation results. This page documents that schema so
custom SQL workflows can sit alongside the agent's natural-language access.

The schema is defined in
[`agentsumo_mcp/analysis/xml_to_sqlite.py`](https://github.com/mw-jeong/AgentSUMO/blob/main/agentsumo_mcp/analysis/xml_to_sqlite.py)
(`_create_schema`). All six tables are keyed by a `simulation_id` so
multiple runs coexist in the same file and can be compared through
ordinary SQL `JOIN`.

```{figure} ../_static/CEUS_fig2_sqlite.png
:alt: SQLite integration pipeline and 6-table schema
:width: 100%
:align: center

SQLite integration pipeline of AgentSUMO. The `xml_to_sqlite_tool`
converts SUMO XML outputs into a structured database of six linked
tables keyed by `simulation_id`. The SQLite MCP Server then exposes
query, schema inspection, and analysis tools, enabling the Planner
Agent to answer natural-language questions about simulation results
through SQL.
```

## Entity-relationship diagram

```{mermaid}
erDiagram
    simulations  ||--o{ trips         : "simulation_id"
    simulations  ||--o{ vehicle_info  : "simulation_id"
    simulations  ||--o{ edge_info     : "simulation_id"
    simulations  ||--o{ edge_metrics  : "simulation_id"
    simulations  ||--o{ network_state : "simulation_id"
    vehicle_info }o--|| trips         : "vehicle_id = trip_id"
    edge_info    ||--o{ edge_metrics  : "edge_id"

    simulations {
        TEXT    simulation_id PK
        TEXT    created_at
        INTEGER vehicle_count
        TEXT    net_file
        TEXT    route_file
        TEXT    description
    }
    trips {
        TEXT simulation_id PK
        TEXT trip_id       PK
        REAL duration
        REAL waitingTime
        REAL timeLoss
        REAL CO2_abs
        REAL fuel_abs
    }
    vehicle_info {
        TEXT simulation_id PK
        TEXT vehicle_id    PK
        TEXT vehicle_type
        TEXT fuel_type
        TEXT origin_road
        TEXT destination_road
    }
    edge_info {
        TEXT    simulation_id PK
        TEXT    edge_id       PK
        TEXT    road_name
        REAL    length
        INTEGER num_lanes
        REAL    speed_limit
    }
    edge_metrics {
        TEXT simulation_id  PK
        TEXT edge_id        PK
        REAL interval_begin PK
        REAL density
        REAL speed
        REAL waitingTime
        REAL CO2_abs
    }
    network_state {
        TEXT    simulation_id PK
        REAL    time          PK
        INTEGER running
        INTEGER halting
        REAL    meanSpeed
        REAL    meanTravelTime
        REAL    meanWaitingTime
    }
```

## Tables at a glance

| Table | Granularity | Source | Rows per simulation |
|---|---|---|---|
| `simulations` | Run | `xml_to_sqlite` metadata | 1 |
| `trips` | Vehicle trip | `tripinfo.xml` | ~ vehicle count |
| `vehicle_info` | Vehicle | `tripinfo.xml` + vType lookup | ~ vehicle count |
| `edge_info` | Road segment | SUMO `net_file` via `sumolib` | ~ edge count |
| `edge_metrics` | Edge × time interval | `edgeData.xml` + `edgeData_emission.xml` | ~ edges × intervals |
| `network_state` | Simulation time step | `summary.xml` | ~ duration / step |

---

## Tables

### `simulations`

Run-level metadata. One row per `xml_to_sqlite_tool` invocation.

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT (PK) | Caller-provided unique identifier (e.g., `"baseline"`, `"teheran_lane_reduction"`). |
| `created_at` | TEXT | ISO-8601 timestamp at ingest. |
| `vehicle_count` | INTEGER | Total trips ingested from `tripinfo.xml`. |
| `net_file` | TEXT | Path to the SUMO network used for this run. |
| `route_file` | TEXT | Path to the route file used for this run. |
| `description` | TEXT | Free-text label provided by the caller. |

**Primary key:** `simulation_id`.

---

### `trips`

One row per vehicle trip, populated from `tripinfo.xml`. Captures both trip
dynamics and per-vehicle emission totals (HBEFA-based).

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT | FK → `simulations.simulation_id`. |
| `trip_id` | TEXT | SUMO vehicle ID. |
| `depart` | REAL | Departure time in seconds. |
| `departLane` | TEXT | Lane the vehicle departed from. |
| `departPos` | REAL | Lateral departure position. |
| `departSpeed` | REAL | Departure speed (m/s). |
| `departDelay` | REAL | Delay vs. scheduled departure (s). |
| `arrival` | REAL | Arrival time in seconds. |
| `arrivalLane` | TEXT | Lane on arrival. |
| `arrivalPos` | REAL | Lateral arrival position. |
| `arrivalSpeed` | REAL | Arrival speed (m/s). |
| `duration` | REAL | Total trip duration (s). |
| `routeLength` | REAL | Distance traveled (m). |
| `waitingTime` | REAL | Cumulative time spent waiting (s). |
| `waitingCount` | INTEGER | Number of waiting events. |
| `stopTime` | REAL | Cumulative time at scheduled stops (s). |
| `timeLoss` | REAL | Time lost vs. unimpeded travel (s). |
| `rerouteNo` | INTEGER | Number of reroutes during the trip. |
| `devices` | TEXT | Comma-separated SUMO device list. |
| `vType` | TEXT | Vehicle type ID. |
| `speedFactor` | REAL | Speed factor applied to this vehicle. |
| `vaporized` | TEXT | Set if the vehicle vaporized (failed to insert / removed). |
| `CO_abs` | REAL | Total CO emissions (mg). |
| `CO2_abs` | REAL | Total CO₂ emissions (mg). |
| `HC_abs` | REAL | Total hydrocarbons (mg). |
| `PMx_abs` | REAL | Total particulate matter (mg). |
| `NOx_abs` | REAL | Total NOₓ (mg). |
| `fuel_abs` | REAL | Total fuel consumed (mL). |
| `electricity_abs` | REAL | Total electricity consumed (Wh). |

**Primary key:** `(simulation_id, trip_id)`.

---

### `vehicle_info`

Per-vehicle metadata derived from the route file and vType definitions.
Lets queries group results by fuel type or filter by origin/destination
road without re-parsing the route XML.

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT | FK → `simulations.simulation_id`. |
| `vehicle_id` | TEXT | Joins to `trips.trip_id`. |
| `vehicle_type` | TEXT | vType ID (e.g., `"passenger"`, `"ev_passenger"`). |
| `fuel_type` | TEXT | Derived classification: `gasoline`, `diesel`, `electric`, `hybrid`, etc. |
| `origin_edge` | TEXT | First edge in the vehicle's route. |
| `destination_edge` | TEXT | Last edge in the vehicle's route. |
| `origin_road` | TEXT | Human-readable name of `origin_edge`. |
| `destination_road` | TEXT | Human-readable name of `destination_edge`. |

**Primary key:** `(simulation_id, vehicle_id)`.

---

### `edge_info`

Per-edge static attributes pulled from the SUMO network via `sumolib`. The
table holds the **structural** information about each edge — the dynamic
metrics live in `edge_metrics`.

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT | FK → `simulations.simulation_id`. |
| `edge_id` | TEXT | SUMO edge ID. |
| `road_name` | TEXT | Human-readable name (e.g., `"Teheran-ro"`). |
| `length` | REAL | Edge length in meters. |
| `num_lanes` | INTEGER | Number of lanes on this edge. |
| `speed_limit` | REAL | Posted speed limit (m/s). |

**Primary key:** `(simulation_id, edge_id)`.

---

### `edge_metrics`

Per-edge per-interval traffic and emission metrics, populated from
`edgeData.xml` (traffic) and `edgeData_emission.xml` (emissions). The
emission columns come in three normalizations:

- `*_abs` — total over the interval.
- `*_normed` — length-and-time normalized.
- `*_perVeh` — per-vehicle on the edge during the interval.

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT | FK → `simulations.simulation_id`. |
| `edge_id` | TEXT | Joins to `edge_info.edge_id`. |
| `interval_begin` | REAL | Interval start (s). |
| `interval_end` | REAL | Interval end (s). |
| `sampledSeconds` | REAL | Total vehicle-seconds sampled. |
| `traveltime` | REAL | Average travel time on the edge. |
| `overlapTraveltime` | REAL | Travel time including overlap. |
| `density` | REAL | Vehicles per km. |
| `laneDensity` | REAL | Vehicles per km per lane. |
| `occupancy` | REAL | Fraction of the edge occupied. |
| `waitingTime` | REAL | Total waiting time on the edge. |
| `timeLoss` | REAL | Total time loss on the edge. |
| `speed` | REAL | Average speed (m/s). |
| `speedRelative` | REAL | `speed / speed_limit`. |
| `departed` | INTEGER | Vehicles that departed from this edge. |
| `arrived` | INTEGER | Vehicles that arrived at this edge. |
| `entered` | INTEGER | Vehicles that entered the edge. |
| `left` | INTEGER | Vehicles that left the edge. |
| `laneChangedFrom` | INTEGER | Lane-change exits. |
| `laneChangedTo` | INTEGER | Lane-change entries. |
| `CO_abs` … `electricity_abs` | REAL | Absolute emissions over the interval (7 species). |
| `CO_normed` … `electricity_normed` | REAL | Normalized emissions (7 species). |
| `CO_perVeh` … `electricity_perVeh` | REAL | Per-vehicle emissions (7 species). |

**Primary key:** `(simulation_id, edge_id, interval_begin)`.

---

### `network_state`

Network-wide per-step state extracted from `summary.xml`. Records cumulative
vehicle counts (loaded, inserted, running, waiting, ended, arrived, halting)
together with mean speed, travel time, and waiting time across all active
vehicles at each simulation step. Supports temporal analyses such as
congestion-onset detection and peak-halting comparison that vehicle-level
aggregates cannot resolve.

| Column | Type | Description |
|---|---|---|
| `simulation_id` | TEXT | FK → `simulations.simulation_id`. |
| `time` | REAL | Simulation time step (s). |
| `loaded` | INTEGER | Cumulative vehicles parsed from the route file. |
| `inserted` | INTEGER | Cumulative vehicles that entered the network. |
| `running` | INTEGER | Vehicles currently in the network at time *t*. |
| `waiting` | INTEGER | Vehicles waiting to be inserted at time *t*. |
| `ended` | INTEGER | Cumulative vehicles that left the network (arrived + vaporized). |
| `arrived` | INTEGER | Cumulative vehicles that reached their destination. |
| `halting` | INTEGER | Vehicles currently stopped (speed = 0). |
| `meanSpeed` | REAL | Mean speed of running vehicles (m/s). |
| `meanSpeedRelative` | REAL | Mean of `speed / speed_limit` ∈ [0, 1]. |
| `meanTravelTime` | REAL | Mean travel time of running vehicles (s). |
| `meanWaitingTime` | REAL | Mean waiting time of running vehicles (s). |
| `teleports` | INTEGER | Cumulative SUMO teleport events. |
| `collisions` | INTEGER | Cumulative collision events. |

**Primary key:** `(simulation_id, time)`.

---

## Indexes

The schema creates indexes on the most common access patterns:
`(simulation_id, edge_id)` on `edge_metrics`; `road_name` and `length` on
`edge_info`; `fuel_type`, `origin_road`, `destination_road` on
`vehicle_info`; and `simulation_id` on `network_state`. These keep
cross-scenario joins responsive even with tens of millions of rows.

---

## Example queries

Canonical SQL snippets you can paste into any SQLite client (or ask the
agent to run for you in natural language).

### Top-N slowest edges in one run

```{code-block} sql
:caption: Top 10 slowest edges by average speed
:linenos:

SELECT e.road_name, em.edge_id, AVG(em.speed) AS avg_speed
FROM edge_metrics em
JOIN edge_info e
  ON e.simulation_id = em.simulation_id
 AND e.edge_id = em.edge_id
WHERE em.simulation_id = 'baseline'
GROUP BY em.edge_id
ORDER BY avg_speed ASC
LIMIT 10;
```

### Per-vehicle CO₂ emissions for a fleet sub-group

```{code-block} sql
:caption: CO₂ totals grouped by fuel type

SELECT v.fuel_type, SUM(t.CO2_abs) AS total_co2_mg, COUNT(*) AS trips
FROM trips t
JOIN vehicle_info v
  ON v.simulation_id = t.simulation_id
 AND v.vehicle_id   = t.trip_id
WHERE t.simulation_id = 'ev_75pct'
GROUP BY v.fuel_type
ORDER BY total_co2_mg DESC;
```

### Departure-delay distribution

```{code-block} sql
:caption: Bucket trips by departure delay

SELECT
  CASE
    WHEN departDelay < 0   THEN 'early'
    WHEN departDelay = 0   THEN 'on time'
    WHEN departDelay < 60  THEN 'under 1 min'
    WHEN departDelay < 300 THEN '1–5 min'
    ELSE '5+ min'
  END AS bucket,
  COUNT(*) AS trips
FROM trips
WHERE simulation_id = 'baseline'
GROUP BY bucket
ORDER BY trips DESC;
```

### Origin-destination pair counts

```{code-block} sql
:caption: Top 20 OD pairs

SELECT origin_road, destination_road, COUNT(*) AS trips
FROM vehicle_info
WHERE simulation_id = 'baseline'
GROUP BY origin_road, destination_road
ORDER BY trips DESC
LIMIT 20;
```

### Side-by-side comparison of two simulations

```{code-block} sql
:caption: Cross-scenario KPI comparison (baseline vs. policy)

SELECT
  AVG(CASE WHEN simulation_id = 'baseline' THEN duration END) AS avg_dur_baseline_s,
  AVG(CASE WHEN simulation_id = 'teheran_lane_reduction' THEN duration END) AS avg_dur_policy_s,
  AVG(CASE WHEN simulation_id = 'baseline' THEN waitingTime END) AS avg_wait_baseline_s,
  AVG(CASE WHEN simulation_id = 'teheran_lane_reduction' THEN waitingTime END) AS avg_wait_policy_s,
  SUM(CASE WHEN simulation_id = 'baseline' THEN CO2_abs END) AS co2_baseline_mg,
  SUM(CASE WHEN simulation_id = 'teheran_lane_reduction' THEN CO2_abs END) AS co2_policy_mg
FROM trips
WHERE simulation_id IN ('baseline', 'teheran_lane_reduction');
```

### Time loss aggregated by road name

```{code-block} sql
:caption: Top 15 roads by cumulative time loss

SELECT e.road_name, SUM(em.timeLoss) AS total_loss_s
FROM edge_metrics em
JOIN edge_info e
  ON e.simulation_id = em.simulation_id
 AND e.edge_id = em.edge_id
WHERE em.simulation_id = 'baseline'
GROUP BY e.road_name
HAVING total_loss_s > 0
ORDER BY total_loss_s DESC
LIMIT 15;
```

### Top emitters by fuel type

```{code-block} sql
:caption: NOₓ and PMₓ emissions by fuel type

SELECT v.fuel_type,
       SUM(t.NOx_abs) AS nox_mg,
       SUM(t.PMx_abs) AS pmx_mg,
       COUNT(*)        AS trips
FROM trips t
JOIN vehicle_info v
  ON v.simulation_id = t.simulation_id
 AND v.vehicle_id   = t.trip_id
WHERE t.simulation_id = 'baseline'
GROUP BY v.fuel_type
ORDER BY nox_mg DESC;
```

### Top 5% busiest edges (length-weighted)

```{code-block} sql
:caption: Edges in the 95th percentile of mean density
:linenos:

WITH per_edge AS (
  SELECT em.edge_id,
         e.road_name,
         e.length,
         AVG(em.density) AS mean_density
  FROM edge_metrics em
  JOIN edge_info e
    ON e.simulation_id = em.simulation_id
   AND e.edge_id = em.edge_id
  WHERE em.simulation_id = 'baseline'
  GROUP BY em.edge_id
)
SELECT *
FROM per_edge
ORDER BY mean_density DESC
LIMIT (SELECT COUNT(*) / 20 FROM per_edge);
```

```{seealso}
- [Result Analysis Tools](../mcp_servers/agentsumo/result_analysis.md) —
  `xml_to_sqlite_tool` populates this schema; `simulation_report_tool`
  renders an HTML report from it.
- [SQLite MCP Server](../mcp_servers/sqlite.md) — how the Planner Agent
  queries this database in natural language.
```
