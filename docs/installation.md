# Installation

AgentSUMO depends on the Eclipse SUMO simulator, a Python 3.12 environment,
and an Anthropic API key. The recommended setup uses
[`uv`](https://docs.astral.sh/uv/) for fast, reproducible environment
management.

## Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.12 (strict) | The `pyproject.toml` pins `>=3.12,<3.13`. |
| SUMO | 1.24+ | Eclipse SUMO simulator. |
| `uv` | 0.4+ | Used to create the virtual environment and resolve dependencies. |
| Anthropic API key | — | Claude Sonnet 4.5 or newer recommended. |
| Mapbox token | — | For satellite/streets tiles in the web UI. |

## 1. Install SUMO

::::{tab-set}

:::{tab-item} macOS

```bash
brew install sumo
```

Alternatively, install [Eclipse SUMO](https://sumo.dlr.de/docs/Downloads.php)
directly. Note the path to the SUMO `share/` directory — you will need it
when setting `SUMO_HOME` below.

:::

:::{tab-item} Linux (Ubuntu / Debian)

```bash
sudo add-apt-repository ppa:sumo/stable
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc
```

:::

:::{tab-item} Windows

Download the official installer from
[sumo.dlr.de/docs/Downloads.php](https://sumo.dlr.de/docs/Downloads.php).
The default install path is `C:\Program Files (x86)\Eclipse\Sumo`.

:::

::::

## 2. Install `uv`

::::{tab-set}

:::{tab-item} macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

:::

:::{tab-item} Windows (PowerShell)

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

:::

::::

## 3. Clone and install AgentSUMO

```bash
git clone https://github.com/mw-jeong/AgentSUMO.git
cd AgentSUMO

# Create a Python 3.12 virtual environment
uv venv --python 3.12

# Activate it
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install the project in editable mode
uv pip install -e .
```

`uv pip install -e .` reads [pyproject.toml](https://github.com/mw-jeong/AgentSUMO/blob/main/pyproject.toml)
and pulls in every runtime dependency (Anthropic SDK, MCP, SUMO Python
tools, FastAPI, Mapbox-compatible geo libraries, and more).

## 4. Configure environment variables

AgentSUMO reads three values from a `.env` file at the project root (or
from your shell environment). Create `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SUMO_HOME=/opt/homebrew/share/sumo
MAPBOX_TOKEN=pk.eyJ1Ijoixxxxxxxxxxxxxxxxxx
```

### `ANTHROPIC_API_KEY`

Anthropic API key for the Planner Agent. Obtain one at
[console.anthropic.com](https://console.anthropic.com/). The Planner Agent
is validated against Claude Sonnet 4.5; older models may produce unstable
tool-call sequences.

### `SUMO_HOME`

Absolute path to your SUMO installation's `share/sumo` directory. AgentSUMO
uses this to locate helper scripts such as `randomTrips.py`, `duarouter`,
and `netconvert`. The directory must contain a `bin/` subdirectory with the
SUMO executables.

::::{tab-set}

:::{tab-item} macOS (Homebrew)

```text
/opt/homebrew/share/sumo
```

:::

:::{tab-item} macOS (Eclipse SUMO)

```text
/Library/Frameworks/EclipseSUMO.framework/Versions/1.24.0/EclipseSUMO
```

:::

:::{tab-item} Linux

```text
/usr/share/sumo
```

:::

:::{tab-item} Windows

```text
C:\Program Files (x86)\Eclipse\Sumo
```

:::

::::

### `MAPBOX_TOKEN`

Mapbox public access token (starts with `pk.`) for the web interface's
satellite and streets layers. Free tokens are available at
[mapbox.com](https://www.mapbox.com/).

## 5. Verify the installation

After the virtual environment is active and `.env` is in place:

```bash
python -c "import agentsumo; print('agentsumo installed')"
sumo --version
python web.py
```

The web server should start on `http://localhost:8000`. A missing or invalid
`ANTHROPIC_API_KEY` or `SUMO_HOME` aborts startup with a descriptive error.

On first start, AgentSUMO seeds the default
`output/simulations/vehicle_types.add.xml` from the packaged
`agentsumo-mcp` fixture so SUMO's additional-file dependency is in place
without manual setup. If you later edit that file via the vType guide
workflow, the seeded copy is left untouched on subsequent runs.

## Next steps

- [Tutorials](tutorials/index.md) — issue your first natural-language
  request.
