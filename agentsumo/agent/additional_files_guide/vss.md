# Variable Speed Sign — Time-Varying Speed Control

## When to Use

Use a variable speed sign (VSS) when the user requests:
- Speed reduction on a specific road segment (e.g., school zones, construction areas)
- Time-varying speed control (e.g., "reduce speed during the first half of the simulation")
- Temporary speed limits that revert to original values

Do NOT use VSS for permanent speed limit changes — use `speed_limit_edit_tool` instead.

## How It Works

A VSS is defined in a separate `.add.xml` file and passed to `sumo_runner` via the `additional_files` parameter. The VSS overrides the network speed limit for specified lanes at specified simulation times. It does not modify the network file.

## IMPORTANT: Speed Unit is m/s

**All speed values in VSS must be in meters per second (m/s), NOT km/h.**

Use the reference table below. Do NOT attempt to calculate conversions manually.

### Speed Reference Table (km/h to m/s)

| km/h | m/s   |
|------|-------|
| 10   | 2.78  |
| 20   | 5.56  |
| 30   | 8.33  |
| 40   | 11.11 |
| 50   | 13.89 |
| 60   | 16.67 |
| 70   | 19.44 |
| 80   | 22.22 |
| 90   | 25.00 |
| 100  | 27.78 |
| 110  | 30.56 |
| 120  | 33.33 |

## XML Schema

### Root: `<variableSpeedSign>`

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| id | Yes | string | Unique identifier (e.g., "vss_school_zone") |
| lanes | Yes | string (space-separated) | Lane IDs to apply speed change |

### Child: `<step>`

| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| time | Yes | float (seconds) | Simulation time when the speed change takes effect (simulation-relative, starts from 0) |
| speed | No | float (m/s) | Target speed. Omit or set to -1 to reset to network default |

## Lane ID Format

VSS requires **lane IDs**, not edge IDs. Lane IDs follow the format: `{edge_id}_{lane_index}`

- Lane index starts from 0.
- To apply VSS to an entire edge, list ALL lanes of that edge.
- Use the `edge_info` table (`num_lanes` column) to determine the number of lanes.

Example: edge "abc123" with 3 lanes:
```
lanes="abc123_0 abc123_1 abc123_2"
```

## Examples

### Example 1: Speed Reduction for Entire Simulation

Scenario: Reduce speed to 30 km/h on a 2-lane road for the entire simulation (3600s).

```xml
<additional>
  <variableSpeedSign id="vss_construction" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="8.33"/>
  </variableSpeedSign>
</additional>
```

### Example 2: Time-Varying Speed Control

Scenario: 30 km/h for the first half, then restore to network default.

```xml
<additional>
  <variableSpeedSign id="vss_school_zone" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="8.33"/>
    <step time="1800" speed="-1"/>
  </variableSpeedSign>
</additional>
```

### Example 3: Gradual Speed Change

Scenario: Progressive speed reduction from 60 km/h to 30 km/h over three phases.

```xml
<additional>
  <variableSpeedSign id="vss_gradual" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="16.67"/>
    <step time="1200" speed="11.11"/>
    <step time="2400" speed="8.33"/>
  </variableSpeedSign>
</additional>
```

### Example 4: Multiple Road Segments

Scenario: Apply 50 km/h limit to two different road segments.

```xml
<additional>
  <variableSpeedSign id="vss_road1" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="13.89"/>
  </variableSpeedSign>
  <variableSpeedSign id="vss_road2" lanes="edge_def456_0 edge_def456_1 edge_def456_2">
    <step time="0" speed="13.89"/>
  </variableSpeedSign>
</additional>
```

## Constraints

- All lane IDs must exist in the current network.
- Speed values must be in **m/s**. Use the reference table above.
- A speed value of -1 or omitting the speed attribute resets to the network default speed.
- Time values are simulation-relative: 0 is the simulation start.
- Each `<variableSpeedSign>` must have a unique `id`.
- The root element must be `<additional>`.

## AgentSUMO Workflow

1. Identify the target edge IDs (query `edge_info` table or use `get_edge_ids_from_road_name_tool`).
2. Query `edge_info` for `num_lanes` to build the full lane ID list.
3. Look up the desired speed in the reference table above.
4. Create the VSS XML file via Filesystem MCP:
   - Path: `output/additional/{scenario_name}.add.xml`
5. Call `sumo_runner` with `additional_files=["output/additional/{scenario_name}.add.xml"]`.
