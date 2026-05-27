# Policy Experimentation Tools

The eight Policy Experimentation tools modify three orthogonal aspects of a
baseline simulation: **infrastructure** (the road network), **demand** (the
vehicle fleet and OD flows), and **signal control** (traffic-light timings).

| Aspect | Tool | Trip-file reusable? |
|---|---|---|
| Infrastructure | `edge_edit_tool` | **No** — regenerate trips. |
|   | `reduce_lanes_tool` | Yes. |
|   | `speed_limit_edit_tool` | Yes. |
| Demand | `vehicle_generation_tool` | Yes (adds vehicles to route file). |
|   | `flow_generation_tool` | Yes (adds flows to route file). |
|   | `vehicle_type_edit_tool` | Yes (vType reassignment). |
| Signal control | `tls_offset_tool` | Yes (emits supplementary XML). |
|   | `tls_adaptation_tool` | Yes (emits supplementary XML). |

```{important}
After `edge_edit_tool` you **must** re-run `trip_generate` and
`route_generate`: deleted edges invalidate any pre-existing route file. The
other infrastructure tools preserve edge IDs and let the existing route file
be reused.
```

---

## Infrastructure tools

### `edge_edit_tool`

Delete specific road segments from the network — used for closure scenarios.
Trip and route files must be regenerated after this operation.

```python
def edge_edit_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None,
)
```

**Parameters**

- `net_file` *(str)* — Network to modify.
- `target_road_name` *(str, optional)* — Road name to target (e.g.,
  `"Teheran-ro"`).
- `edge_ids` *(list, optional)* — Explicit edge IDs to delete instead of a
  road-name lookup.
- `reference_location` *(str, optional)* — Anchor for spatial filtering.
- `radius_km` *(float, optional)* — Radius around `reference_location`.

**Returns** — `{status, net_file, requires_reroute=True}`.

---

### `reduce_lanes_tool`

Reduce lanes on road segments. Two modes:

- **Relative** — `reduce_by=1` removes one lane from each matching segment.
- **Absolute** — `remain_lanes=2` collapses each matching segment to exactly
  two lanes (special-case scenarios).

Trip and route files can be reused because edge IDs are preserved — only
lane count changes.

```python
def reduce_lanes_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None,
    reduce_by: int = None,
    remain_lanes: int = None,
)
```

**Returns** — `{status, net_file, modified_edges}`.

---

### `speed_limit_edit_tool`

Modify the posted speed limit on selected segments. Supports localized
application using `reference_location` + `radius_km`. Trip and route files
can be reused.

```python
def speed_limit_edit_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None,
    new_speed_kmph: float = None,
)
```

**Returns** — `{status, net_file, modified_edges, new_speed_kmph}`.

---

## Demand tools

### `vehicle_generation_tool`

Add one or more individual vehicles between two locations, with optimal-path
routing. Supports geocoded place names (`use_geocoding=True`) for
landmark-based scenarios.

```python
def vehicle_generation_tool(
    route_file: str,
    net_file: str,
    source_location: str,
    destination_location: str,
    vehicle_id: str = "genveh_0",
    depart_time: float = 0.0,
    depart_time_range: list = None,
    vehicle_count: int = 1,
    output_dir: str = "output/trips",
    use_geocoding: bool = False,
    search_radius: float = 0.3,
)
```

**Returns** — `{status, route_file, generated_vehicles}`.

---

### `flow_generation_tool`

Add a continuous vehicle flow between two locations over a time window
(`vehs_per_hour`). Used for surge scenarios — post-event traffic,
evacuation, peak-hour studies. The tool sets safe SUMO insertion attributes
(`departLane="free"`, `departPos="random_free"`, `departSpeed="random"`) to
avoid insertion failures.

```python
def flow_generation_tool(
    route_file: str,
    net_file: str,
    source: str,
    dest: str,
    begin: float,
    end: float,
    vehs_per_hour: int,
    flow_id: str = None,
    output_dir: str = "output/trips",
    use_geocoding: bool = True,
    search_radius: float = 0.3,
)
```

**Returns** — `{status, route_file, flow_id, vehs_per_hour}`.

---

### `vehicle_type_edit_tool`

Reassign vehicle types in the route file according to an electric-vehicle
ratio. Used for fleet-composition scenarios (e.g., 25% EV adoption). The
tool preserves trip IDs and OD pairs — only `vType` assignments change.

```python
def vehicle_type_edit_tool(
    route_file: str,
    electric_ratio: float,
    output_dir: str = "output/trips",
)
```

**Returns** — `{status, route_file, electric_ratio, vtype_summary}`.

---

## Signal control tools

### `tls_offset_tool`

Optimize traffic-light **offsets** via SUMO's `tlsCoordinator.py`
(Green-Wave coordination). The tool writes a supplementary XML file
containing offset adjustments; `sumo_runner` loads it via `additional_files`.

```python
def tls_offset_tool(
    net_file: str,
    route_file: str,
    output_dir: str = "output/simulations",
)
```

**Returns** — `{status, additional_file}`.

---

### `tls_adaptation_tool`

Optimize traffic-light **cycle lengths** via SUMO's `tlsCycleAdaptation.py`
(Webster-style optimization). Like `tls_offset_tool`, the result is a
supplementary XML file passed to `sumo_runner` via `additional_files`.

```python
def tls_adaptation_tool(
    net_file: str,
    route_file: str,
    output_dir: str = "output/simulations",
)
```

**Returns** — `{status, additional_file}`.
