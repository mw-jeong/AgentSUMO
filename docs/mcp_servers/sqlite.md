# SQLite MCP Server

The SQLite MCP server is **maintained by Anthropic**. It exposes SQL
execution and schema inspection over MCP. AgentSUMO uses it to let the
Planner Agent answer analytical questions about simulation results through
natural-language → SQL translation against `simulations.db`.

## Official documentation

::::{grid} 1
:gutter: 2

:::{grid-item-card} modelcontextprotocol/servers-archived — SQLite
:link: https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite
:class-card: sd-text-center

`github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite`
:::

::::

## Tools used by AgentSUMO

The server exposes six tools across three categories, matching the layout
in Figure 2 of the paper.

| Category | Tool | Purpose |
|---|---|---|
| **Query** | `read_query` | Execute a `SELECT` query and return rows. |
| **Query** | `write_query` | Execute `INSERT`, `UPDATE`, or `DELETE` queries. |
| **Query** | `create_table` | Create new tables in the database. |
| **Schema** | `list_tables` | List the tables in `simulations.db`. |
| **Schema** | `describe_table` | Inspect a table's schema. |
| **Analysis** | `append_insight` | Persist intermediate analytical findings as session memos. |

## How AgentSUMO uses it

AgentSUMO's analytical workflow is **read-driven by default**. The curated
simulation pipeline ingests results through `xml_to_sqlite_tool` and renders
reports through `simulation_report_tool`, both of which manage their own
write paths so the SQLite MCP server's `write_query` and `create_table`
remain available for ad-hoc data shaping during a session without being
the primary ingest path.

Four concrete patterns:

1. **Natural-language analytics.** Questions like *"Which road had the worst
   congestion?"* or *"Compare CO₂ emissions across the three EV scenarios"*
   are translated to SQL by the LLM and executed through `read_query`.
2. **Schema introspection during reasoning.** `list_tables` and
   `describe_table` let the agent inspect the database before constructing a
   query — useful when it has been a few turns since the last
   `xml_to_sqlite_tool` call.
3. **Ad-hoc data shaping.** `write_query` and `create_table` let the agent
   materialize a scratch table (e.g., a per-corridor aggregate or a
   pre-joined view) when a follow-up question would otherwise require
   re-running a heavy join multiple times.
4. **Session-level memos.** `append_insight` lets the agent record
   intermediate findings that survive across tool calls within the same
   conversation.

The same database holds **all simulation runs in a single file**, keyed by a
unique `simulation_id`. This is what enables cross-scenario relational
querying through ordinary SQL `JOIN` — see [Database](../database/index.md)
for the relational model.
