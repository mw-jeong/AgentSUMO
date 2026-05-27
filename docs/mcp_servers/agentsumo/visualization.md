# Visualization Tools

Four tools render PNG images of the network and edge-level metrics, used
either as standalone artifacts or as previews before applying policy
interventions.

```{important}
All four tools are docstring-annotated to fire **only on explicit user
request**. The Planner Agent does not generate images during routine
scenario construction — only when the user asks to see the network, preview
a policy target, or render a heatmap.
```

---

## `visualize_net_tool`

Render the SUMO network as a PNG. Used when the user wants a static image of
the network topology.

```python
def visualize_net_tool(
    net_file: str,
    output_dir: str = "output/visualizations",
)
```

**Returns** — `{visualization_file, image_metadata}`.

---

## `visualize_edge_tool`

Render the network with a specified road **highlighted**, useful for showing
where a particular road sits within the broader network.

```python
def visualize_edge_tool(
    net_file: str,
    road_name: str,
    output_dir: str = "output/visualizations",
)
```

**Returns** — `{visualization_file}`.

---

## `visualize_policy_target_tool`

Preview the **policy-target area** before applying interventions. Shows only
the road segments within the specified radius around a reference location —
the same segments that, e.g., `reduce_lanes_tool` or `speed_limit_edit_tool`
would modify if called with identical parameters. Part of the
clarify-before-execute step in the Interactive Planning Protocol.

```python
def visualize_policy_target_tool(
    net_file: str,
    target_road_name: str,
    reference_location: str = None,
    radius_km: float = None,
    output_dir: str = "output/visualizations",
)
```

**Returns** — `{visualization_file, segments_selected}`.

---

## `visualize_edgedata_tool`

Render an edge-level **metric heatmap** (density, speed, waiting time,
occupancy, per-edge emissions) over the network. Supports three scale modes
for comparing across runs:

- `"auto"` — dynamic per-file scaling. Best for inspecting a single run.
- `"unified"` — consistent color scale across `comparison_files`. Best for
  visually comparing baseline vs. policy outcomes.
- `"fixed"` — caller specifies `min_value` / `max_value`. Best for batch
  reports where scales must match exactly.

```python
def visualize_edgedata_tool(
    net_file: str,
    edgedata_file: str,
    attribute: str = "density",
    output_dir: str = "output/visualizations",
    scale_mode: str = "auto",
    comparison_files: list = None,
    min_value: float = None,
    max_value: float = None,
)
```

**Parameters**

- `edgedata_file` *(str)* — Path to `edgeData.xml` or
  `edgeData_emission.xml`.
- `attribute` *(str)* — Metric to map onto colors. Common values: `density`,
  `speed`, `waitingTime`, `occupancy`, `CO2_abs`, `NOx_abs`, `PMx_abs`,
  `fuel_abs`.
- `scale_mode` *(str)* — `"auto"`, `"unified"`, or `"fixed"`.
- `comparison_files` *(list, optional)* — Used with `"unified"` mode to lock
  the color scale across runs.

**Returns** — `{visualization_file, scaling_metadata}`.
