"""
Default-file ensure helpers.

The AgentSUMO MCP Server ships a small set of fixture files in
``agentsumo_mcp/defaults/`` that SUMO needs at simulation time. The
helpers here lazily materialize those fixtures onto disk the first time
a tool needs them, so both:

* users who install ``agentsumo-mcp`` from PyPI as a standalone server, and
* users who clone the full AgentSUMO repository,

get the same default ``vehicle_types.add.xml`` without manual setup.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_DEFAULTS_PACKAGE = "agentsumo_mcp.defaults"
_VEHICLE_TYPES_FILENAME = "vehicle_types.add.xml"


def ensure_vehicle_types_default(sim_dir: Path | str) -> Path:
    """Make sure a default ``vehicle_types.add.xml`` exists under ``sim_dir``.

    If the destination already contains a ``vehicle_types.add.xml`` (the user
    may have edited it via the vType guide workflow), it is left untouched.
    Otherwise the packaged default is copied in.

    Args:
        sim_dir: Target directory, typically ``<output>/simulations``.

    Returns:
        Absolute path to the ensured file.
    """
    sim_dir = Path(sim_dir)
    sim_dir.mkdir(parents=True, exist_ok=True)
    target = sim_dir / _VEHICLE_TYPES_FILENAME

    if not target.exists():
        source = files(_DEFAULTS_PACKAGE) / _VEHICLE_TYPES_FILENAME
        target.write_bytes(source.read_bytes())

    return target
