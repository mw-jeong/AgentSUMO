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

Four concrete patterns:

1. **Natural-language analytics.** Questions like *"Which road had the worst
   congestion?"* or *"Compare CO₂ emissions across the three EV scenarios"*
   are translated to SQL by the LLM and executed through `read_query`.
2. **Schema introspection during reasoning.** `list_tables` and
   `describe_table` let the agent inspect the database before constructing a
   query — useful when it has been a few turns since the last
   `xml_to_sqlite_tool` call.
3. **Materializing derived tables.** `write_query` and `create_table` let
   the agent persist a per-corridor aggregate, a pre-joined view, or any
   other derived structure that subsequent questions reuse without
   rerunning the underlying joins.
4. **Session-level memos.** `append_insight` lets the agent record
   intermediate findings that survive across tool calls within the same
   conversation.

The same database holds **all simulation runs in a single file**, keyed by a
unique `simulation_id`. This is what enables cross-scenario relational
querying through ordinary SQL `JOIN` — see [Database](../database/index.md)
for the relational model.
