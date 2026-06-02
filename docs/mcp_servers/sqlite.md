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

| Tool | Purpose |
|---|---|
| `read_query` | Execute a `SELECT` query and return rows. |
| `query` | Generic SQL execution endpoint. |
| `list_tables` | List the tables in `simulations.db`. |
| `describe_table` | Inspect a table's schema. |
| `append_insight` | Persist intermediate analytical findings as session memos. |

## How AgentSUMO uses it

The server is configured for **read-only** access to `outputs/simulations.db`.
Write access is reserved to AgentSUMO's own `xml_to_sqlite_tool` and
`simulation_report_tool`, so the analytical agent cannot accidentally
mutate simulation results during a session.

Three concrete patterns:

1. **Natural-language analytics.** Questions like *"Which road had the worst
   congestion?"* or *"Compare CO₂ emissions across the three EV scenarios"*
   are translated to SQL by the LLM and executed through `read_query`.
2. **Schema introspection during reasoning.** `list_tables` and
   `describe_table` let the agent inspect the database before constructing a
   query — useful when it has been a few turns since the last
   `xml_to_sqlite_tool` call.
3. **Session-level memos.** `append_insight` lets the agent record
   intermediate findings that survive across tool calls within the same
   conversation.

The same database holds **all simulation runs in a single file**, keyed by a
unique `simulation_id`. This is what enables cross-scenario relational
querying through ordinary SQL `JOIN` — see [Database](../database/index.md)
for the relational model.
