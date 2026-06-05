# Tools

AgentSUMO uses the [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) as a uniform protocol for tool discovery and invocation. Three MCP
servers run alongside the Planner Agent, each with a distinct responsibility.

::::{grid} 1 1 3 3
:gutter: 3

:::{grid-item-card} AgentSUMO MCP Server
:link: agentsumo/index
:link-type: doc
:class-card: sd-text-center

**Owner:** This project · **Tools:** 26

Our own server. Wraps every SUMO utility AgentSUMO needs: network
generation, demand modeling, policy edits, result parsing, and
visualization.
:::

:::{grid-item-card} Filesystem MCP Server
:link: filesystem
:link-type: doc
:class-card: sd-text-center

**Owner:** Anthropic · **Tools:** 7 in use

Anthropic's reference server. AgentSUMO uses it to read user uploads,
write supplementary XML configuration files, and inspect generated
artifacts.
:::

:::{grid-item-card} SQLite MCP Server
:link: sqlite
:link-type: doc
:class-card: sd-text-center

**Owner:** Anthropic · **Tools:** 6 (Query / Schema / Analysis)

Anthropic's reference server. AgentSUMO uses it for natural-language
querying of `simulations.db` after `xml_to_sqlite_tool` ingest, with a
read-driven workflow by default.
:::

::::

```{seealso}
- [Schema](../database/index.md) — the SQLite database layout populated by
  `xml_to_sqlite_tool` and queried through the SQLite MCP server.
- [Tutorials](../tutorials/index.md) — end-to-end walkthroughs that exercise
  these tools in real policy scenarios.
```

```{toctree}
:hidden:
:caption: Tools

agentsumo/index
filesystem
sqlite
```
