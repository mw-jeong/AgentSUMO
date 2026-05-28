# Utility Tools

Five utility tools support network statistics retrieval, route analysis, and
road-name ↔ edge-ID translation. These do not modify the network or
simulation — they are reasoning aids the Planner Agent uses when constructing
scenarios or interpreting results.

---

## `network_summary_tool`

Return a comprehensive summary of a SUMO network: edge count, junction count,
total road length, bounding box, and the list of road names.

```python
def network_summary_tool(net_file: str)
```

**Returns** — `{edges, junctions, total_road_length_km, bbox, road_names,
road_count, traffic_lights}`. `bbox` is `[min_lon, min_lat, max_lon,
max_lat]`; `road_names` is a deduplicated list.

---

## `route_analysis_tool`

Compute the optimal route between two locations. Two routing modes:

- `"distance"` — shortest path by edge length, computed with `sumolib`.
- `"traveltime"` — optimal path using simulation results as edge weights,
  computed with `duarouter`. Requires `weight_file` (typically
  `edgeData.xml` from a prior run) and `weight_attribute` (e.g.,
  `"traveltime"`).

Also supports cross-network comparison: pass `compare_net_file` and
`compare_weight_file` to get baseline-vs-policy route deltas in one call.

```python
def route_analysis_tool(
    net_file: str,
    origin: str,
    destination: str,
    routing_mode: str = "distance",
    weight_file: str = None,
    weight_attribute: str = "traveltime",
    compare_net_file: str = None,
    compare_weight_file: str = None,
)
```

**Parameters**

- `origin`, `destination` *(str)* — Place names or road names. AgentSUMO
  geocodes place names with GeoPy and snaps them to the nearest network edge.
- `routing_mode` *(str)* — `"distance"` or `"traveltime"`.
- `weight_file`, `weight_attribute` *(str, optional)* — Required for
  travel-time mode.
- `compare_net_file`, `compare_weight_file` *(str, optional)* — Enable
  cross-scenario route comparison.

**Returns** — `{route_edges, distance, time, road_names, ...}`; if
comparison was requested, both routes plus diff metrics.

---

## `analyze_road_details_tool`

Retrieve detailed per-segment attributes of a named road: lane count, speed
limit (km/h), length per segment, and statistical summary. Used by the agent
to verify the road actually exists in the network before applying a policy.

```python
def analyze_road_details_tool(
    net_file: str,
    target_road_name: str,
    reference_location: str = None,
    radius_km: float = None,
    include_lane_details: bool = True,
)
```

**Parameters**

- `target_road_name` *(str)* — Road name to analyze (e.g., `"Teheran-ro"`).
- `reference_location`, `radius_km` *(optional)* — Spatial filtering when
  the road name appears in multiple places.
- `include_lane_details` *(bool)* — Whether to include per-lane breakdowns.

**Returns** — `{segments, statistics, summary, filtering_info}`.

---

## `get_road_names_tool`

Convert a list of SUMO edge IDs into human-readable road names. Used after
congestion analysis to present results with real street names rather than
technical IDs.

```python
def get_road_names_tool(edge_ids: list, net_file: str)
```

**Returns** — `{edge_id: road_name, ...}`.

---

## `get_edge_ids_from_road_name_tool`

Reverse of `get_road_names_tool`: given a road name, return the list of SUMO
edge IDs that belong to it. Enables road-name-based SQL queries on the
`edge_metrics` table (which keys on `edge_id`).

```python
def get_edge_ids_from_road_name_tool(road_name: str, net_file: str)
```

**Returns** — `[edge_id_1, edge_id_2, ...]`.
