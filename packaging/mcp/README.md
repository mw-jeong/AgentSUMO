<!-- mcp-name: io.github.mw-jeong/agentsumo-mcp -->

# agentsumo-mcp

[![PyPI](https://img.shields.io/pypi/v/agentsumo-mcp.svg)](https://pypi.org/project/agentsumo-mcp/)
[![arXiv](https://img.shields.io/badge/arXiv-2511.06804-b31b1b.svg)](https://arxiv.org/abs/2511.06804)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

MCP server for [SUMO](https://eclipse.dev/sumo/) (Simulation of Urban MObility) traffic simulation. Orchestrate network extraction, trip generation, scenario customization, simulation runs, and SQL-based result analysis from any MCP-compatible LLM client.

## Features

- **Pipeline tools**: OSM extraction -> network conversion -> trip generation -> route generation -> simulation
- **Scenario customization**: edge editing, lane reduction, speed limit changes, vehicle generation, traffic-light timing
- **Result analysis**: ingest tripinfo / edgedata / summary XML into SQLite for natural-language SQL queries
- **Visualization**: network plots, edge data heatmaps, policy-target visualizations
- **Geocoding**: place name -> coordinate -> nearest edge resolution
- **Bundled defaults**: ships a default `vehicle_types.add.xml` (passenger / electric / gasoline) that is auto-seeded into the simulation directory on the first `sumo_runner` call, so the SUMO additional-file dependency works without any manual setup

## Requirements

- Python 3.10 or later
- [SUMO](https://eclipse.dev/sumo/) installed locally (`SUMO_HOME` environment variable set)

## Installation

```bash
pip install agentsumo-mcp
```

Or run without installing via [`uvx`](https://docs.astral.sh/uv/guides/tools/):

```bash
uvx agentsumo-mcp
```

## Configuration

Set `SUMO_HOME` to point at your local SUMO installation:

```bash
export SUMO_HOME=/path/to/sumo
```

On macOS with the official SUMO installer this is usually `/Library/Frameworks/EclipseSUMO.framework/Versions/<version>/EclipseSUMO`.

## Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentsumo": {
      "command": "uvx",
      "args": ["agentsumo-mcp"],
      "env": {
        "SUMO_HOME": "/path/to/sumo"
      }
    }
  }
}
```

## Usage with other MCP clients

Any MCP client that supports stdio transport works:

```bash
agentsumo-mcp
```

## Tools

The server exposes 26 tools across five categories (aligned with Table 3 of the paper):

| Category | Examples |
|----------|----------|
| Scenario Generation | `osm_extract`, `net_convert`, `trip_generate`, `route_generate`, `sumo_runner` |
| Policy Experimentation | `edge_edit_tool`, `reduce_lanes_tool`, `speed_limit_edit_tool`, `vehicle_generation_tool`, `flow_generation_tool`, `tls_offset_tool`, `tls_adaptation_tool` |
| Result Analysis | `xml_to_sqlite_tool`, `simulation_report_tool` |
| Visualization | `visualize_net_tool`, `visualize_edge_tool`, `visualize_policy_target_tool`, `visualize_edgedata_tool` |
| Utility Functions | `network_summary_tool`, `route_analysis_tool`, `analyze_road_details_tool`, `get_road_names_tool`, `validate_od_coordinates_tool`, `web_search_tool` |

Each tool returns structured JSON suitable for downstream LLM reasoning.

## Citation

If you use AgentSUMO in academic work, please cite:

```bibtex
@article{jeong2025agentsumo,
  title         = {AgentSUMO: An Agentic Framework for Interactive Simulation Scenario Generation in SUMO via Large Language Models},
  author        = {Jeong, Minwoo and Chang, Jeeyun and Yoon, Yoonjin},
  journal       = {arXiv preprint arXiv:2511.06804},
  year          = {2025},
  url           = {https://arxiv.org/abs/2511.06804}
}
```

## License

MIT. See [LICENSE](LICENSE).
