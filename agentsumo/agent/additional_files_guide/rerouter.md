# Rerouter — Road/Lane Closure and Rerouting

## When to Use

Use a rerouter when the user requests:
- Road closure (construction, events, emergencies)
- Lane reduction during construction
- Vehicle class restrictions (e.g., "no trucks on this road")
- Time-based traffic control (e.g., "close this road during the first half of the simulation")

Do NOT use a rerouter for permanent road removal — use `edge_edit_tool` instead.

## How It Works

A rerouter is defined in a separate `.add.xml` file and passed to `sumo_runner` via the `additional_files` parameter. The rerouter modifies traffic permissions on existing edges/lanes without changing the network file. SUMO automatically computes alternative routes for affected vehicles using Dijkstra's algorithm.

The `--device.rerouting.probability 1.0` flag is automatically applied by `sumo_runner` when a rerouter file is detected.

## XML Schema

### Root: `<rerouter>`

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| id | Yes | string | Unique identifier (e.g., "rerouter_construction") |
| edges | Yes | string (;-separated) | Edge IDs where the rerouter is installed |
| probability | No | float (0.0-1.0) | Probability of rerouting. Default: 1.0 |
| vTypes | No | string (space-separated) | Vehicle types affected. Default: all |

### Child: `<interval>`

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| begin | Yes | float (seconds) | Start time (simulation-relative, starts from 0) |
| end | Yes | float (seconds) | End time (must not exceed simulation duration) |

### Child of interval: `<closingReroute>` (road closure)

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| id | Yes | string | Edge ID to close |
| allow | No | string (space-separated) | Vehicle classes still allowed (default: none = full closure) |

### Child of interval: `<closingLaneReroute>` (lane closure)

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| id | Yes | string | Lane ID to close (format: `{edge_id}_{lane_index}`) |
| allow | No | string (space-separated) | Vehicle classes still allowed (default: "authority") |

Lane ID format: `{edge_id}_{index}` where index starts from 0.
Example: edge "abc123" with 3 lanes has lanes "abc123_0", "abc123_1", "abc123_2".
Use `edge_info` table (`num_lanes` column) to determine the number of lanes for an edge.

## Valid Vehicle Classes for `allow` / `vTypes`

passenger, truck, bus, bicycle, motorcycle, emergency, authority, taxi, delivery, coach, tram, rail, pedestrian

## Examples

### Example 1: Full Road Closure (entire simulation)

Scenario: Close a road for the full simulation duration (3600s).

```xml
<additional>
  <rerouter id="rerouter_construction" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123"/>
    </interval>
  </rerouter>
</additional>
```

### Example 2: Partial Road Closure (first half only)

Scenario: Close a road during the first half of a 3600s simulation.

```xml
<additional>
  <rerouter id="rerouter_morning" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="1800">
      <closingReroute id="edge_abc123"/>
    </interval>
  </rerouter>
</additional>
```

### Example 3: Lane Reduction (3 lanes to 2 lanes)

Scenario: Close the outermost lane of a 3-lane road.

```xml
<additional>
  <rerouter id="rerouter_lane_closure" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingLaneReroute id="edge_abc123_2"/>
    </interval>
  </rerouter>
</additional>
```

### Example 4: Emergency Vehicles Only

Scenario: Close a road but allow emergency vehicles to pass.

```xml
<additional>
  <rerouter id="rerouter_emergency_only" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123" allow="emergency"/>
    </interval>
  </rerouter>
</additional>
```

### Example 5: Multiple Roads Closure

Scenario: Close multiple road segments simultaneously.

```xml
<additional>
  <rerouter id="rerouter_area_closure" edges="edge_abc123;edge_def456;edge_ghi789" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123"/>
      <closingReroute id="edge_def456"/>
      <closingReroute id="edge_ghi789"/>
    </interval>
  </rerouter>
</additional>
```

## Constraints

- All edge IDs referenced in `edges` and `closingReroute id` must exist in the current network.
- The `edges` attribute and `closingReroute id` can reference the same edge.
- Time values are simulation-relative: 0 is the simulation start, and `end` must not exceed the simulation duration.
- The root element must be `<additional>`.

## AgentSUMO Workflow

1. Identify the target edge IDs (query `edge_info` table or use `get_edge_ids_from_road_name_tool`).
2. Create the rerouter XML file via Filesystem MCP:
   - Path: `output/additional/{scenario_name}.add.xml`
3. Call `sumo_runner` with `additional_files=["output/additional/{scenario_name}.add.xml"]`.
4. The rerouting device is automatically enabled when a rerouter is detected.
