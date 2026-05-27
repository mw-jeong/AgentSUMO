# Result Analysis Tools

Two tools convert SUMO's raw XML outputs into structured, analyzable artifacts:
one ingests the XML into a queryable SQLite database, the other renders a
cross-scenario HTML report from that database.

---

## `xml_to_sqlite_tool`

Convert SUMO XML results (`tripinfo`, `edgeData`, `edgeData_emission`) into a
SQLite database. This unlocks SQL-based analytical workflows that would be
prohibitively expensive on raw XML — Top-N queries, cross-scenario joins,
temporal aggregation, and natural-language analysis through the SQLite MCP
server.

```python
def xml_to_sqlite_tool(
    tripinfo_xml: str,
    edgedata_xml: str,
    edgedata_emission_xml: str,
    output_dir: str = "output/analysis",
    simulation_id: str = None,
    net_file: str = None,
    route_file: str = None,
    description: str = None,
)
```

**Parameters**

- `tripinfo_xml` *(str)* — Path to `tripinfo.xml` from `sumo_runner`.
- `edgedata_xml` *(str)* — Path to `edgeData.xml`.
- `edgedata_emission_xml` *(str)* — Path to `edgeData_emission.xml`.
- `simulation_id` *(str)* — A unique identifier for this run. **Required for
  cross-scenario comparison.** If omitted, the tool generates one from the
  timestamp.
- `net_file`, `route_file` *(str)* — Stored alongside metadata so analytical
  joins can include road-name resolution.
- `description` *(str)* — Free-text label (e.g.,
  `"Teheran-ro 1-lane reduction"`). Stored in the `simulations` table.

**Returns** — `{db_file, simulation_id, metadata}`. `db_file` points at
`simulations.db`; subsequent runs append to the same file. `metadata`
summarizes counts (trips ingested, edges, intervals).

**Tables populated**

- `simulations` — one new row keyed by `simulation_id`.
- `trips` — one row per vehicle trip extracted from `tripinfo.xml`.
- `vehicle_info` — per-vehicle metadata (vehicle type, fuel type, OD edges).
- `edge_info` — per-edge static attributes (road name, length, lane count,
  speed limit) sourced from `net_file` via `sumolib`.
- `edge_metrics` — per-edge × per-interval traffic and emission metrics
  derived from `edgeData.xml` and `edgeData_emission.xml`.

See [Database](../../database/index.md) for the full schema.

---

## `db_based_simulation_report_tool`

Generate a comprehensive standalone HTML report from the SQLite database.
This is the **final deliverable** of a simulation analysis session. The
report summarizes **all** scenarios in the database with KPIs, cross-scenario
comparison tables, top congested roads, trip-duration distributions, and an
inline SVG of the study-area network.

```python
def db_based_simulation_report_tool(
    db_path: str,
    executive_summary: str = "",
    output_dir: str = "output/reports",
)
```

**Parameters**

- `db_path` *(str)* — Path to `simulations.db` (returned by
  `xml_to_sqlite_tool`).
- `executive_summary` *(str, optional)* — Top-of-report narrative written by
  the agent. If omitted, the report starts directly with the comparison
  table.

**Returns** — `{status, report_file, scenarios}`. `report_file` is the
standalone HTML path; `scenarios` lists every `simulation_id` included.

**Report contents**

For each scenario, the tool computes:

- **Trip-level KPIs** — average duration, average waiting time, average
  speed, total CO₂ emissions, total fuel consumption, completed trips.
- **Edge-level rankings** — top congested roads via length-weighted average
  density.
- **Trip duration distribution** — horizontal bar chart with configurable
  time buckets.
- **Cross-scenario comparison table** — percentage changes for every
  performance metric when at least two scenarios are present, color-coded
  green (improvement) and red (degradation).
- **Inline SVG of the study area** — generated from the SUMO `net_file`
  stored in the `simulations` table, with the top-N most congested edges
  highlighted.

The output is self-contained: no external dependencies beyond a CDN-hosted
font, suitable for sharing with non-technical stakeholders.
