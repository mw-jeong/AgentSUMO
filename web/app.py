"""
AgentSUMO Web Application

FastAPI 기반 웹 서버
- REST API: 네트워크 목록, 상태 조회 등
- WebSocket: 실시간 채팅
"""

import asyncio
import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import sumolib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from agentsumo import AgentSUMO
from agentsumo.core import AgentSUMOConfig

logger = logging.getLogger("agentsumo.web")


# ============================================
# Helper Functions
# ============================================

def get_output_dir() -> Optional[Path]:
    """Get output directory path"""
    output_dir = AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output"
    return output_dir if output_dir.exists() else None


def get_networks_dir() -> Optional[Path]:
    """Get networks directory path"""
    networks_dir = AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output" / "networks"
    return networks_dir if networks_dir.exists() else None


def get_simulations_dir() -> Optional[Path]:
    """Get simulations directory path"""
    sims_dir = AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output" / "simulations"
    return sims_dir if sims_dir.exists() else None


def find_network_file(network_name: str) -> Optional[Path]:
    """Find network file by name"""
    networks_dir = get_networks_dir()
    if networks_dir:
        net_file = networks_dir / network_name
        if net_file.exists():
            return net_file
    return None


def find_simulation_file(filename: str, pattern: str = None) -> Optional[Path]:
    """Find simulation file by name or pattern"""
    sims_dir = get_simulations_dir()
    if not sims_dir:
        return None

    # Exact match
    exact_match = sims_dir / filename
    if exact_match.exists():
        return exact_match

    # Pattern match
    if pattern:
        for f in sims_dir.iterdir():
            if f.is_file() and pattern in f.name:
                return f

    return None

# Global agent instance (singleton per server)
_agent: Optional[AgentSUMO] = None
_agent_lock = asyncio.Lock()


async def get_agent() -> AgentSUMO:
    """Get or create AgentSUMO instance"""
    global _agent

    async with _agent_lock:
        if _agent is None:
            logger.info("Creating new AgentSUMO instance...")
            _agent = AgentSUMO(enable_debug=False, interface="web")
            await _agent.start()
            logger.info("AgentSUMO ready!")

        return _agent


def create_app() -> FastAPI:
    """Create FastAPI application"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan manager"""
        # Startup
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        logger.info("AgentSUMO Web starting...")
        yield
        # Shutdown
        global _agent
        if _agent:
            await _agent.close()
            _agent = None
        logger.info("AgentSUMO Web stopped")

    app = FastAPI(
        title="AgentSUMO Web",
        description="AI-Powered SUMO Traffic Simulation Platform",
        version="0.1.0",
        lifespan=lifespan
    )

    # Static files & templates
    web_dir = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=web_dir / "static"), name="static")
    templates = Jinja2Templates(directory=web_dir / "templates")

    # ============================================
    # Routes
    # ============================================

    @app.get("/")
    async def index(request: Request):
        """Main page"""
        mapbox_token = AgentSUMOConfig.get_mapbox_token()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "mapbox_token": mapbox_token}
        )

    @app.get("/api/state")
    async def get_state():
        """Get current agent state"""
        try:
            agent = await get_agent()
            state = agent.get_state()
            return JSONResponse(content=state)
        except Exception as e:
            return JSONResponse(
                content={"error": str(e)},
                status_code=500
            )

    @app.get("/api/networks")
    async def list_networks():
        """List available networks"""
        try:
            networks_dir = get_networks_dir()
            if networks_dir is None:
                return JSONResponse(content={"networks": [], "message": "No networks directory"})

            networks = [
                f.name for f in networks_dir.iterdir()
                if f.is_file() and f.name.endswith('.net.xml')
            ]

            return JSONResponse(content={
                "networks": sorted(networks),
                "count": len(networks),
                "directory": str(networks_dir)
            })
        except Exception as e:
            logger.error(f"Error listing networks: {e}")
            return JSONResponse(
                content={"error": str(e), "networks": []},
                status_code=500
            )

    @app.get("/api/files")
    async def list_output_files():
        """List files in output directory as tree structure"""
        try:
            output_dir = get_output_dir()
            if output_dir is None:
                return JSONResponse(content={"tree": [], "message": "No output directory"})

            def build_tree(path, base_path):
                """Recursively build file tree"""
                items = []
                try:
                    for entry in sorted(path.iterdir()):
                        rel_path = str(entry.relative_to(base_path))
                        if entry.is_dir():
                            children = build_tree(entry, base_path)
                            items.append({
                                "name": entry.name,
                                "path": rel_path,
                                "type": "folder",
                                "children": children,
                                "expanded": False  # Start collapsed
                            })
                        else:
                            # Get file info
                            stat = entry.stat()
                            size_kb = stat.st_size / 1024
                            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

                            # Determine file type icon
                            file_type = "file"
                            if entry.suffix == ".xml":
                                if "net" in entry.name:
                                    file_type = "network"
                                elif "route" in entry.name or "trip" in entry.name:
                                    file_type = "route"
                                elif "netstate" in entry.name:
                                    file_type = "simulation"
                                else:
                                    file_type = "xml"
                            elif entry.suffix == ".osm":
                                file_type = "osm"
                            elif entry.suffix == ".html":
                                file_type = "report"

                            items.append({
                                "name": entry.name,
                                "path": rel_path,
                                "type": file_type,
                                "size": f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB",
                                "modified": mtime
                            })
                except PermissionError:
                    pass
                return items

            tree = build_tree(output_dir, output_dir)

            return JSONResponse(content={
                "tree": tree,
                "root": str(output_dir)
            })
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return JSONResponse(
                content={"error": str(e), "tree": []},
                status_code=500
            )

    @app.get("/api/report/{report_path:path}")
    async def get_report(report_path: str):
        """Serve HTML report file"""
        from fastapi.responses import FileResponse
        try:
            output_dir = get_output_dir()
            if output_dir is None:
                return JSONResponse(
                    content={"error": "No output directory"},
                    status_code=404
                )

            report_file = output_dir / report_path
            if not report_file.exists() or not report_file.suffix == ".html":
                return JSONResponse(
                    content={"error": f"Report not found: {report_path}"},
                    status_code=404
                )

            return FileResponse(
                path=str(report_file),
                media_type="text/html"
            )
        except Exception as e:
            logger.error(f"Error serving report: {e}")
            return JSONResponse(
                content={"error": str(e)},
                status_code=500
            )

    @app.get("/api/network/{network_name}/geojson")
    async def get_network_geojson(network_name: str):
        """Get network as GeoJSON for map display"""
        try:
            net_file = find_network_file(network_name)
            if net_file is None:
                return JSONResponse(
                    content={"error": f"Network not found: {network_name}"},
                    status_code=404
                )

            # Parse network and convert to GeoJSON
            net = sumolib.net.readNet(str(net_file))
            features = []

            for edge in net.getEdges():
                shape = edge.getShape()
                if len(shape) < 2:
                    continue

                # Convert to lon/lat
                coords = [net.convertXY2LonLat(x, y) for x, y in shape]

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": {
                        "id": edge.getID(),
                        "name": edge.getName() or edge.getID(),
                        "speed": edge.getSpeed(),
                        "lanes": edge.getLaneNumber(),
                        "length": edge.getLength(),
                        "type": edge.getType()
                    }
                })

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            # Calculate center for map
            if features:
                all_coords = []
                for f in features:
                    all_coords.extend(f["geometry"]["coordinates"])

                lons = [c[0] for c in all_coords]
                lats = [c[1] for c in all_coords]
                center = {
                    "lon": sum(lons) / len(lons),
                    "lat": sum(lats) / len(lats)
                }
            else:
                center = {"lon": 127.028, "lat": 37.497}  # Default: Gangnam

            return JSONResponse(content={
                "geojson": geojson,
                "center": center,
                "edge_count": len(features)
            })

        except Exception as e:
            logger.error(f"Error loading network: {e}")
            return JSONResponse(
                content={"error": str(e)},
                status_code=500
            )

    @app.get("/api/simulations")
    async def list_simulations():
        """List available simulation results"""
        try:
            sims_dir = get_simulations_dir()
            if sims_dir is None:
                return JSONResponse(content={"simulations": [], "message": "No simulations directory"})

            # Find netstate files (actual SUMO output format: {name}_netstate_{timestamp}.xml)
            simulations = []
            for f in sims_dir.iterdir():
                if f.is_file() and '_netstate_' in f.name and f.name.endswith('.xml') and '_emission' not in f.name:
                    # Extract base name (e.g., "gangnam_station.net" from "gangnam_station.net_netstate_20251208_005012.xml")
                    parts = f.name.split('_netstate_')
                    if len(parts) >= 2:
                        base_name = parts[0]
                        timestamp = parts[1].replace('.xml', '')
                        simulations.append({
                            "name": f"{base_name}_{timestamp}",
                            "base_name": base_name,
                            "netstate_file": f.name,
                            "path": str(f),
                            "timestamp": timestamp
                        })

            return JSONResponse(content={
                "simulations": sorted(simulations, key=lambda x: x["timestamp"], reverse=True),
                "count": len(simulations),
                "directory": str(sims_dir)
            })
        except Exception as e:
            logger.error(f"Error listing simulations: {e}")
            return JSONResponse(
                content={"error": str(e), "simulations": []},
                status_code=500
            )

    @app.get("/api/heatmap/{network_name}/{simulation_name}")
    async def get_heatmap_geojson(network_name: str, simulation_name: str, attribute: str = "density"):
        """Get simulation results as GeoJSON heatmap for map display"""
        try:
            net_file = find_network_file(network_name)
            if net_file is None:
                return JSONResponse(
                    content={"error": f"Network not found: {network_name}"},
                    status_code=404
                )

            # Find netstate file
            netstate_file = find_simulation_file(simulation_name, pattern="_netstate_")
            if netstate_file is None:
                return JSONResponse(
                    content={"error": f"Simulation netstate not found: {simulation_name}"},
                    status_code=404
                )

            logger.info(f"Loading heatmap from: {netstate_file}")

            # Parse network
            net = sumolib.net.readNet(str(net_file))

            # Parse netstate XML and extract attribute values
            edge_values = {}
            tree = ET.parse(str(netstate_file))
            root = tree.getroot()

            for interval in root.findall('.//interval'):
                for edge in interval.findall('edge'):
                    edge_id = edge.get('id')
                    value = edge.get(attribute)
                    if value is not None:
                        try:
                            edge_values[edge_id] = float(value)
                        except ValueError:
                            pass

            if not edge_values:
                return JSONResponse(
                    content={"error": f"No data found for attribute: {attribute}"},
                    status_code=404
                )

            # Calculate min/max for normalization
            values = list(edge_values.values())
            min_val = min(values)
            max_val = max(values)
            val_range = max_val - min_val if max_val != min_val else 1

            # Build GeoJSON with heatmap values
            features = []
            for edge in net.getEdges():
                edge_id = edge.getID()
                if edge_id not in edge_values:
                    continue

                shape = edge.getShape()
                if len(shape) < 2:
                    continue

                # Convert to lon/lat
                coords = [net.convertXY2LonLat(x, y) for x, y in shape]
                value = edge_values[edge_id]
                normalized = (value - min_val) / val_range  # 0 to 1

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": {
                        "id": edge_id,
                        "name": edge.getName() or edge_id,
                        "value": value,
                        "normalized": normalized,
                        "attribute": attribute
                    }
                })

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            # Calculate center
            if features:
                all_coords = []
                for f in features:
                    all_coords.extend(f["geometry"]["coordinates"])
                lons = [c[0] for c in all_coords]
                lats = [c[1] for c in all_coords]
                center = {
                    "lon": sum(lons) / len(lons),
                    "lat": sum(lats) / len(lats)
                }
            else:
                center = {"lon": 127.028, "lat": 37.497}

            return JSONResponse(content={
                "geojson": geojson,
                "center": center,
                "edge_count": len(features),
                "attribute": attribute,
                "min_value": min_val,
                "max_value": max_val
            })

        except Exception as e:
            logger.error(f"Error loading heatmap: {e}")
            return JSONResponse(
                content={"error": str(e)},
                status_code=500
            )

    # ============================================
    # FCD Replay API
    # ============================================

    @app.get("/api/fcd/list")
    async def list_fcd_files():
        """List available FCD files for replay"""
        try:
            sims_dir = get_simulations_dir()
            if not sims_dir:
                return JSONResponse(content={"fcd_files": [], "count": 0})

            fcd_files = []
            for f in sims_dir.iterdir():
                if f.is_file() and '_fcd_' in f.name and f.name.endswith('.xml'):
                    parts = f.name.split('_fcd_')
                    if len(parts) >= 2:
                        base_name = parts[0]
                        timestamp = parts[1].replace('.xml', '')
                        fcd_files.append({
                            "name": f"{base_name}_{timestamp}",
                            "base_name": base_name,
                            "filename": f.name,
                            "path": str(f),
                            "timestamp": timestamp
                        })

            return JSONResponse(content={
                "fcd_files": sorted(fcd_files, key=lambda x: x["timestamp"], reverse=True),
                "count": len(fcd_files)
            })
        except Exception as e:
            logger.error(f"Error listing FCD files: {e}")
            return JSONResponse(content={"error": str(e), "fcd_files": []}, status_code=500)

    @app.get("/api/fcd/{fcd_filename}/parse")
    async def parse_fcd_file(fcd_filename: str, sample_rate: int = 1):
        """
        Parse FCD file and return timestep data for replay.

        Args:
            fcd_filename: FCD file name
            sample_rate: Sample every N timesteps (default 1 = all timesteps)

        Returns:
            JSON with timesteps array containing vehicle positions
        """
        try:
            fcd_file = find_simulation_file(fcd_filename)
            if fcd_file is None:
                return JSONResponse(
                    content={"error": f"FCD file not found: {fcd_filename}"},
                    status_code=404
                )

            logger.info(f"Parsing FCD file: {fcd_file}")

            # Parse FCD XML
            timesteps = []
            tree = ET.iterparse(str(fcd_file), events=('end',))

            timestep_count = 0
            for event, elem in tree:
                if elem.tag == 'timestep':
                    timestep_count += 1

                    # Apply sample rate
                    if timestep_count % sample_rate != 0:
                        elem.clear()
                        continue

                    time_val = float(elem.get('time', 0))
                    vehicles = []

                    for vehicle in elem.findall('vehicle'):
                        x_val = float(vehicle.get('x', 0))
                        y_val = float(vehicle.get('y', 0))
                        # With fcd-output.geo=true, x/y ARE lon/lat
                        # Detect if x looks like longitude (typically 100-180 for East Asia)
                        # vs SUMO local coordinates (typically 0-10000)
                        if 100 < x_val < 180 and 0 < y_val < 90:
                            lon, lat = x_val, y_val
                        else:
                            # Old FCD without geo - x/y are local coords, no lon/lat
                            lon, lat = None, None
                        vehicles.append({
                            "id": vehicle.get('id'),
                            "x": x_val,
                            "y": y_val,
                            "lon": lon,
                            "lat": lat,
                            "angle": float(vehicle.get('angle', 0)),
                            "speed": float(vehicle.get('speed', 0)),
                            "type": vehicle.get('type', 'default')
                        })

                    if vehicles:  # Only include timesteps with vehicles
                        timesteps.append({
                            "time": time_val,
                            "vehicles": vehicles
                        })

                    elem.clear()  # Free memory

            logger.info(f"Parsed {len(timesteps)} timesteps from FCD file")

            return JSONResponse(content={
                "filename": fcd_filename,
                "timesteps": timesteps,
                "total_timesteps": len(timesteps),
                "sample_rate": sample_rate
            })

        except Exception as e:
            logger.error(f"Error parsing FCD file: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.get("/api/tls/{tls_filename}/parse")
    async def parse_tls_file(tls_filename: str):
        """
        Parse TLS (Traffic Light State) file and return state changes.

        Args:
            tls_filename: TLS switch output file name

        Returns:
            JSON with traffic light state changes indexed by time
        """
        try:
            tls_file = find_simulation_file(tls_filename)
            if tls_file is None:
                return JSONResponse(
                    content={"error": f"TLS file not found: {tls_filename}"},
                    status_code=404
                )

            logger.info(f"Parsing TLS file: {tls_file}")

            # Parse TLS switch output XML
            # Format: <tlsSwitch id="..." fromLane="..." toLane="..." begin="..." end="..." duration="..."/>
            # Or: <tlsState time="..." id="..." state="..."/>
            tls_states = {}  # time -> {tls_id: state}

            tree = ET.parse(str(tls_file))
            root = tree.getroot()

            # Try parsing as tlsStates (state at each timestep)
            for state_elem in root.findall('.//tlsState'):
                time_val = float(state_elem.get('time', 0))
                tls_id = state_elem.get('id', '')
                state = state_elem.get('state', '')

                time_key = round(time_val, 1)
                if time_key not in tls_states:
                    tls_states[time_key] = {}
                tls_states[time_key][tls_id] = state

            # Also try parsing as tlsSwitch (switch events)
            for switch_elem in root.findall('.//tlsSwitch'):
                time_val = float(switch_elem.get('begin', 0))
                tls_id = switch_elem.get('id', '')
                # For switches, we just record the event
                time_key = round(time_val, 1)
                if time_key not in tls_states:
                    tls_states[time_key] = {}
                # Mark as switch event
                tls_states[time_key][tls_id] = 'switch'

            logger.info(f"Parsed {len(tls_states)} timesteps with TLS data")

            return JSONResponse(content={
                "filename": tls_filename,
                "tls_states": tls_states,
                "total_timesteps": len(tls_states)
            })

        except Exception as e:
            logger.error(f"Error parsing TLS file: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.get("/api/network/{network_name}/traffic-lights")
    async def get_traffic_light_positions(network_name: str):
        """
        Get traffic light positions from network file.

        Returns junction coordinates for all traffic lights.
        """
        try:
            net_file = find_network_file(network_name)
            if net_file is None:
                return JSONResponse(
                    content={"error": f"Network not found: {network_name}"},
                    status_code=404
                )

            # Parse network
            net = sumolib.net.readNet(str(net_file))

            traffic_lights = []
            for tls in net.getTrafficLights():
                tls_id = tls.getID()
                # Get junction for this TLS
                # TLS ID often matches junction ID, or we find connected junctions
                try:
                    # Try to get the junction directly
                    junction = net.getNode(tls_id)
                    if junction:
                        x, y = junction.getCoord()
                        lon, lat = net.convertXY2LonLat(x, y)
                        traffic_lights.append({
                            "id": tls_id,
                            "lon": lon,
                            "lat": lat,
                            "type": junction.getType()
                        })
                except:
                    # If junction not found by TLS ID, find connected edges
                    connections = tls.getConnections()
                    if connections:
                        # Get position from first connection's incoming lane
                        conn = connections[0]
                        incoming_lane = conn[0]
                        edge = incoming_lane.getEdge()
                        to_node = edge.getToNode()
                        x, y = to_node.getCoord()
                        lon, lat = net.convertXY2LonLat(x, y)
                        traffic_lights.append({
                            "id": tls_id,
                            "lon": lon,
                            "lat": lat,
                            "type": "traffic_light"
                        })

            logger.info(f"Found {len(traffic_lights)} traffic lights in network")

            return JSONResponse(content={
                "network": network_name,
                "traffic_lights": traffic_lights,
                "count": len(traffic_lights)
            })

        except Exception as e:
            logger.error(f"Error getting traffic lights: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.get("/api/fcd/{fcd_filename}/metadata")
    async def get_fcd_metadata(fcd_filename: str):
        """Get FCD file metadata without loading all data"""
        try:
            fcd_file = find_simulation_file(fcd_filename)
            if fcd_file is None:
                return JSONResponse(
                    content={"error": f"FCD file not found: {fcd_filename}"},
                    status_code=404
                )

            # Quick scan for metadata
            timestep_count = 0
            first_time = None
            last_time = None
            max_vehicles = 0

            for event, elem in ET.iterparse(str(fcd_file), events=('end',)):
                if elem.tag == 'timestep':
                    time_val = float(elem.get('time', 0))
                    vehicle_count = len(elem.findall('vehicle'))

                    if first_time is None:
                        first_time = time_val
                    last_time = time_val

                    if vehicle_count > max_vehicles:
                        max_vehicles = vehicle_count

                    timestep_count += 1
                    elem.clear()

            return JSONResponse(content={
                "filename": fcd_filename,
                "total_timesteps": timestep_count,
                "start_time": first_time,
                "end_time": last_time,
                "duration": last_time - first_time if first_time and last_time else 0,
                "max_vehicles": max_vehicles
            })

        except Exception as e:
            logger.error(f"Error getting FCD metadata: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ============================================
    # SUMO GUI API
    # ============================================

    @app.get("/api/sumocfg/list")
    async def list_sumocfg_files():
        """List available SUMO configuration files"""
        try:
            sims_dir = get_simulations_dir()
            if not sims_dir:
                return JSONResponse(content={"configs": [], "count": 0})

            cfg_files = []
            for f in sims_dir.iterdir():
                if f.is_file() and f.name.endswith('.sumocfg'):
                    parts = f.name.replace('simulation_', '').replace('.sumocfg', '')
                    cfg_files.append({
                        "name": f.name,
                        "path": str(f),
                        "timestamp": parts,
                        "directory": str(sims_dir)
                    })

            return JSONResponse(content={
                "configs": sorted(cfg_files, key=lambda x: x["timestamp"], reverse=True),
                "count": len(cfg_files)
            })
        except Exception as e:
            logger.error(f"Error listing SUMO config files: {e}")
            return JSONResponse(content={"error": str(e), "configs": []}, status_code=500)

    @app.post("/api/sumo-gui/open")
    async def open_sumo_gui(config_path: str = None, config_name: str = None):
        """
        Launch SUMO GUI with specified configuration file.

        Args:
            config_path: Full path to .sumocfg file (priority)
            config_name: Config filename to find in simulations directory

        Returns:
            JSON with status of the launch
        """
        try:
            from agentsumo.server.settings.settings import sumo_environment
            import platform

            # Find the config file
            cfg_file = None

            if config_path and Path(config_path).exists():
                cfg_file = Path(config_path)
            elif config_name:
                cfg_file = find_simulation_file(config_name)

            if cfg_file is None:
                return JSONResponse(
                    content={"error": f"Config file not found: {config_path or config_name}"},
                    status_code=404
                )

            # Launch sumo-gui

            if platform.system() == "Darwin":
                # macOS: SUMO GUI requires X11/XQuartz
                xquartz_app = "/Applications/Utilities/XQuartz.app"
                if not Path(xquartz_app).exists():
                    return JSONResponse(
                        content={
                            "error": "XQuartz is required to run SUMO GUI on macOS",
                            "solution": "Install XQuartz from https://www.xquartz.org/ and restart your Mac"
                        },
                        status_code=400
                    )

                # Start XQuartz if not running
                subprocess.Popen(
                    ["open", "-a", "XQuartz"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Give XQuartz time to start
                import time
                time.sleep(1.5)

                # Set DISPLAY for X11
                env = os.environ.copy()
                env["DISPLAY"] = ":0"

                # Get sumo-gui binary path
                sumo_gui_binary = sumo_environment.get_binary_path("sumo-gui")
                cmd = [sumo_gui_binary, "-c", str(cfg_file)]
                logger.info(f"Launching SUMO GUI with X11: {' '.join(cmd)}")
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cfg_file.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    start_new_session=True
                )
            else:
                # Linux/Windows: direct execution
                sumo_gui_binary = sumo_environment.get_binary_path("sumo-gui")
                cmd = [sumo_gui_binary, "-c", str(cfg_file)]
                logger.info(f"Launching SUMO GUI: {' '.join(cmd)}")
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cfg_file.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )

            return JSONResponse(content={
                "status": "success",
                "message": f"SUMO GUI launched with {cfg_file.name}",
                "config_file": str(cfg_file),
                "pid": process.pid
            })

        except Exception as e:
            logger.error(f"Error launching SUMO GUI: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ============================================
    # WebSocket for Simulation Replay
    # ============================================

    # Store for active replay sessions
    _replay_websockets = set()
    _replay_tasks = {}

    @app.websocket("/ws/simulation")
    async def websocket_simulation(websocket: WebSocket):
        """WebSocket endpoint for simulation replay streaming"""
        await websocket.accept()
        _replay_websockets.add(websocket)
        logger.info("Replay WebSocket connected")

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "start_replay":
                    # Start replay with provided timesteps data
                    timesteps = data.get("timesteps", [])
                    speed = data.get("speed", 1.0)  # Playback speed multiplier

                    if timesteps:
                        # Cancel any existing replay
                        if websocket in _replay_tasks:
                            _replay_tasks[websocket].cancel()

                        # Start new replay task
                        task = asyncio.create_task(
                            _run_replay(websocket, timesteps, speed)
                        )
                        _replay_tasks[websocket] = task

                elif msg_type == "stop_replay":
                    if websocket in _replay_tasks:
                        _replay_tasks[websocket].cancel()
                        del _replay_tasks[websocket]
                    await websocket.send_json({"type": "replay_stopped"})

                elif msg_type == "set_speed":
                    # Update replay speed (will be handled in next timestep)
                    pass

        except WebSocketDisconnect:
            logger.info("Replay WebSocket disconnected")
        except Exception as e:
            logger.error(f"Replay WebSocket error: {e}")
        finally:
            _replay_websockets.discard(websocket)
            if websocket in _replay_tasks:
                _replay_tasks[websocket].cancel()
                del _replay_tasks[websocket]

    async def _run_replay(websocket: WebSocket, timesteps: list, speed: float = 1.0):
        """Run replay streaming for a websocket connection"""
        try:
            await websocket.send_json({"type": "replay_started", "total_timesteps": len(timesteps)})

            prev_time = None
            for i, timestep in enumerate(timesteps):
                current_time = timestep["time"]

                # Calculate delay based on simulation time difference
                if prev_time is not None and speed > 0:
                    delay = (current_time - prev_time) / speed
                    if delay > 0:
                        await asyncio.sleep(delay)

                prev_time = current_time

                # Send vehicle positions
                await websocket.send_json({
                    "type": "vehicles",
                    "data": {
                        "time": current_time,
                        "step": i + 1,
                        "total_steps": len(timesteps),
                        "vehicles": timestep["vehicles"]
                    }
                })

            await websocket.send_json({"type": "replay_ended"})

        except asyncio.CancelledError:
            logger.info("Replay cancelled")
        except Exception as e:
            logger.error(f"Replay error: {e}")
            await websocket.send_json({"type": "replay_error", "error": str(e)})

    # ============================================
    # WebSocket for Chat
    # ============================================

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        """WebSocket endpoint for chat"""
        await websocket.accept()
        logger.info("WebSocket connection established")

        try:
            agent = await get_agent()

            # Set up progress callback for real-time tool updates
            def progress_callback(tool_name: str, status: str, message: str = None):
                """Send progress updates via WebSocket"""
                logger.info(f"📡 Progress callback: {tool_name} - {status}")
                try:
                    asyncio.ensure_future(
                        websocket.send_json({
                            "type": "progress",
                            "data": {
                                "tool": tool_name,
                                "status": status,
                                "message": message or f"{tool_name}: {status}"
                            }
                        })
                    )
                except Exception as e:
                    logger.warning(f"Failed to send progress: {e}")

            agent.set_progress_callback(progress_callback)

            # Send initial state
            await websocket.send_json({
                "type": "state",
                "data": agent.get_state()
            })

            while True:
                # Receive message
                data = await websocket.receive_json()
                msg_type = data.get("type", "chat")

                if msg_type == "chat":
                    user_message = data.get("message", "")

                    if not user_message:
                        continue

                    # Send "thinking" indicator
                    await websocket.send_json({
                        "type": "thinking",
                        "data": True
                    })

                    try:
                        # Get response from agent
                        response = await agent.chat(user_message)

                        # Send response
                        await websocket.send_json({
                            "type": "response",
                            "data": response
                        })

                        # Send updated state
                        await websocket.send_json({
                            "type": "state",
                            "data": agent.get_state()
                        })

                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "data": str(e)
                        })

                    finally:
                        await websocket.send_json({
                            "type": "thinking",
                            "data": False
                        })

                elif msg_type == "reset":
                    agent.reset_conversation()
                    await websocket.send_json({
                        "type": "state",
                        "data": agent.get_state()
                    })
                    await websocket.send_json({
                        "type": "info",
                        "data": "Conversation reset"
                    })

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")

        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    return app


# For running with uvicorn
app = create_app()
