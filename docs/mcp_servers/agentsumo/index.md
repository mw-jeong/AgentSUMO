# AgentSUMO MCP Server

Twenty-six tools that drive every SUMO operation in AgentSUMO — from
downloading an OSM extract to ingesting simulation results into SQLite.
The tools are grouped into five categories that follow the simulation
workflow.

## Categories

::::{grid} 1 2 2 3
:gutter: 3

:::{grid-item-card} Scenario Generation
:link: scenario_generation
:link-type: doc

**5 tools** — construct a SUMO baseline simulation: OSM → network → trips
→ routes → run.
:::

:::{grid-item-card} Policy Experimentation
:link: policy_experimentation
:link-type: doc

**8 tools** — modify infrastructure, demand, and signal control to test
interventions.
:::

:::{grid-item-card} Result Analysis
:link: result_analysis
:link-type: doc

**2 tools** — convert SUMO XML output to SQLite and generate HTML reports.
:::

:::{grid-item-card} Visualization
:link: visualization
:link-type: doc

**4 tools** — render networks, edge highlights, and per-edge metric
heatmaps.
:::

:::{grid-item-card} Utility
:link: utility
:link-type: doc

**7 tools** — network statistics, route analysis, road-name ↔ edge-id
translation, OD-coordinate validation, web-search grounding.
:::

::::

```{toctree}
:hidden:
:caption: AgentSUMO MCP

scenario_generation
policy_experimentation
result_analysis
visualization
utility
```
