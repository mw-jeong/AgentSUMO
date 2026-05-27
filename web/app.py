"""
AgentSUMO Web Application

FastAPI 기반 웹 서버
- REST API: 네트워크 목록, 상태 조회 등
- WebSocket: 실시간 채팅
"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import sumolib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
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
            _agent = AgentSUMO(
                enable_debug=False,
                interface="web",
                enable_filesystem_mcp=True,
                filesystem_directories=[
                    str(AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "agent" / "additional_files_guide"),
                    str(AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output")
                ]
            )
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

    @app.get("/landing")
    async def landing_page(request: Request):
        """Landing page (design preview)"""
        return templates.TemplateResponse(
            "landing.html",
            {"request": request}
        )

    @app.get("/preview")
    async def preview_page(request: Request):
        """Main interface dark theme preview"""
        mapbox_token = AgentSUMOConfig.get_mapbox_token()
        return templates.TemplateResponse(
            "main_dark.html",
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
                        # Skip hidden/internal files
                        if entry.name.startswith('.'):
                            continue
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

            # Build edge length lookup for filtering
            edge_lengths = {}
            for edge in net.getEdges():
                edge_lengths[edge.getID()] = edge.getLength()

            # Filter out very short edges (< 5m) — intersection connectors
            # produce extreme outlier values for all metrics
            filtered_values = {
                eid: val for eid, val in edge_values.items()
                if edge_lengths.get(eid, 0) >= 5.0
            }
            if not filtered_values:
                filtered_values = edge_values

            # Use percentile-based bounds to handle outliers (all attributes)
            sorted_vals = sorted(filtered_values.values())
            n = len(sorted_vals)
            p5_val = sorted_vals[int(n * 0.05)]
            p95_val = sorted_vals[min(int(n * 0.95), n - 1)]
            min_val = p5_val
            max_val = p95_val
            val_range = max_val - min_val if max_val != min_val else 1

            # Build GeoJSON with heatmap values (no invert — frontend handles colormap direction)
            features = []
            for edge in net.getEdges():
                edge_id = edge.getID()
                if edge_id not in edge_values:
                    continue

                if edge.getLength() < 5.0:
                    continue

                shape = edge.getShape()
                if len(shape) < 2:
                    continue

                coords = [net.convertXY2LonLat(x, y) for x, y in shape]
                value = edge_values[edge_id]
                normalized = max(0.0, min((value - min_val) / val_range, 1.0))

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
    # Dashboard API
    # ============================================

    @app.get("/api/dashboard")
    async def get_dashboard_data(sim_a: str, sim_b: str = None):
        """Get dashboard data for one or two simulations"""
        try:
            output_dir = get_output_dir()
            if not output_dir:
                return JSONResponse(content={"error": "No output directory"}, status_code=404)

            analysis_dir = output_dir / "analysis"
            db_files = list(analysis_dir.glob("*.db")) if analysis_dir.exists() else []
            if not db_files:
                return JSONResponse(content={"error": "No analysis DB found"}, status_code=404)

            db_path = str(db_files[0])
            if Path(db_path).stat().st_size == 0:
                return JSONResponse(content={"error": "DB is empty"}, status_code=404)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            def get_kpi(sim_id):
                r = conn.execute("""
                    SELECT COUNT(*) as trip_count,
                           AVG(duration) as avg_duration,
                           AVG(waitingTime) as avg_waiting,
                           AVG(timeLoss) as avg_timeloss,
                           AVG(routeLength) as avg_route_length,
                           SUM(CO2_abs) as total_co2,
                           SUM(fuel_abs) as total_fuel,
                           SUM(NOx_abs) as total_nox
                    FROM trips WHERE simulation_id=?
                """, (sim_id,)).fetchone()
                if not r or r['trip_count'] == 0:
                    return None

                # Average speed from edge_metrics
                spd = conn.execute("""
                    SELECT AVG(speed) as avg_speed FROM edge_metrics
                    WHERE simulation_id=? AND speed > 0
                """, (sim_id,)).fetchone()

                return {
                    "trip_count": r['trip_count'],
                    "avg_duration": round(r['avg_duration'], 1),
                    "avg_waiting": round(r['avg_waiting'], 1),
                    "avg_timeloss": round(r['avg_timeloss'], 1),
                    "avg_route_length": round(r['avg_route_length'], 1),
                    "total_co2_kg": round((r['total_co2'] or 0) / 1e6, 1),
                    "total_fuel_L": round((r['total_fuel'] or 0) / 1e6, 1),
                    "total_nox_g": round((r['total_nox'] or 0) / 1000, 1),
                    "avg_speed_kmh": round((spd['avg_speed'] or 0) * 3.6, 1)
                }

            def get_duration_distribution(sim_id):
                buckets = [
                    ("< 1 min", 0, 60),
                    ("1-3 min", 60, 180),
                    ("3-5 min", 180, 300),
                    ("5-10 min", 300, 600),
                    ("10+ min", 600, 999999)
                ]
                result = []
                for label, lo, hi in buckets:
                    r = conn.execute(
                        "SELECT COUNT(*) as cnt FROM trips WHERE simulation_id=? AND duration>=? AND duration<?",
                        (sim_id, lo, hi)
                    ).fetchone()
                    result.append({"bucket": label, "count": r['cnt']})
                return result

            def get_top_congested(sim_id, limit=5):
                """Get top congested roads aggregated by road name, length-weighted"""
                rows = conn.execute("""
                    SELECT edge_id, AVG(density) as density, AVG(speed) as speed,
                           AVG(waitingTime) as waiting_time
                    FROM edge_metrics
                    WHERE simulation_id=? AND density > 0
                    GROUP BY edge_id
                """, (sim_id,)).fetchall()

                # Load network for road names and lengths
                net_file_row = conn.execute(
                    "SELECT net_file FROM simulations WHERE simulation_id=?", (sim_id,)
                ).fetchone()

                net = None
                if net_file_row and net_file_row['net_file']:
                    try:
                        net = sumolib.net.readNet(net_file_row['net_file'])
                    except Exception:
                        pass

                if not net:
                    return []

                # Aggregate by road name (length-weighted, skip < 5m edges)
                road_data = {}  # name -> {sum_density_x_len, sum_speed_x_len, sum_wait_x_len, total_len, edge_ids}
                for r in rows:
                    try:
                        edge = net.getEdge(r['edge_id'])
                        length = edge.getLength()
                        if length < 5.0:
                            continue
                        name = edge.getName()
                        if not name:
                            continue
                    except Exception:
                        continue

                    if name not in road_data:
                        road_data[name] = {
                            "sum_d": 0, "sum_s": 0, "sum_w": 0,
                            "total_len": 0, "edge_ids": []
                        }
                    rd = road_data[name]
                    rd["sum_d"] += r['density'] * length
                    rd["sum_s"] += r['speed'] * length
                    rd["sum_w"] += r['waiting_time'] * length
                    rd["total_len"] += length
                    rd["edge_ids"].append(r['edge_id'])

                # Compute weighted averages and sort
                result = []
                for name, rd in road_data.items():
                    if rd["total_len"] == 0:
                        continue
                    result.append({
                        "name": name,
                        "density": round(rd["sum_d"] / rd["total_len"], 1),
                        "speed_kmh": round(rd["sum_s"] / rd["total_len"] * 3.6, 1),
                        "waiting_time": round(rd["sum_w"] / rd["total_len"], 1),
                        "total_length_m": round(rd["total_len"], 0),
                        "segment_count": len(rd["edge_ids"]),
                        "edge_ids": rd["edge_ids"]
                    })

                result.sort(key=lambda x: x["density"], reverse=True)
                return result[:limit]

            # Build response
            kpi_a = get_kpi(sim_a)
            if not kpi_a:
                conn.close()
                return JSONResponse(content={"error": f"No data for {sim_a}"}, status_code=404)

            data = {
                "sim_a": sim_a,
                "kpi_a": kpi_a,
                "duration_dist_a": get_duration_distribution(sim_a),
                "top_congested_a": get_top_congested(sim_a),
                "has_compare": sim_b is not None
            }

            if sim_b:
                kpi_b = get_kpi(sim_b)
                if kpi_b:
                    data["sim_b"] = sim_b
                    data["kpi_b"] = kpi_b
                    data["duration_dist_b"] = get_duration_distribution(sim_b)
                    data["top_congested_b"] = get_top_congested(sim_b)

            conn.close()
            return JSONResponse(content=data)

        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ============================================
    # Compare Heatmap API (DB-based)
    # ============================================

    COMPARE_ATTRIBUTES = [
        'density', 'speed', 'waitingTime', 'timeLoss',
        'occupancy', 'laneDensity', 'traveltime', 'sampledSeconds',
        'CO2_abs', 'NOx_abs', 'fuel_abs', 'CO_abs', 'PMx_abs'
    ]

    # Attributes where higher = better (need inverted colormap)
    INVERT_ATTRIBUTES = {'speed', 'speedRelative'}

    @app.get("/api/db/simulations")
    async def list_db_simulations():
        """List simulation IDs from the analysis DB"""
        try:
            output_dir = get_output_dir()
            if not output_dir:
                return JSONResponse(content={"simulations": [], "db_path": None})

            analysis_dir = output_dir / "analysis"
            if not analysis_dir.exists():
                return JSONResponse(content={"simulations": [], "db_path": None})

            # Find first .db file
            db_files = list(analysis_dir.glob("*.db"))
            if not db_files:
                return JSONResponse(content={"simulations": [], "db_path": None})

            db_path = str(db_files[0])

            # Skip empty DB files
            if Path(db_path).stat().st_size == 0:
                return JSONResponse(content={"simulations": [], "db_path": None})

            conn = sqlite3.connect(db_path)

            # Check if simulations table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='simulations'"
            ).fetchone()
            if not table_check:
                conn.close()
                return JSONResponse(content={"simulations": [], "db_path": db_path})

            rows = conn.execute(
                "SELECT simulation_id, description, vehicle_count, net_file FROM simulations ORDER BY created_at"
            ).fetchall()
            conn.close()

            sims = []
            for r in rows:
                # Skip entries with no description (auto-generated duplicates)
                if r[1] is None:
                    continue
                sims.append({
                    "id": r[0],
                    "label": r[1],
                    "description": r[1],
                    "vehicle_count": r[2],
                    "net_file": r[3]
                })

            return JSONResponse(content={
                "simulations": sims,
                "db_path": db_path,
                "count": len(sims)
            })
        except Exception as e:
            logger.error(f"Error listing DB simulations: {e}")
            return JSONResponse(content={"error": str(e), "simulations": []}, status_code=500)

    @app.get("/api/compare")
    async def compare_simulations(
        network_name: str,
        sim_a: str,
        sim_b: str = None,
        db_path: str = None
    ):
        """
        Compare one or two simulations. Returns GeoJSON with all attributes.
        All attribute values + normalized values are included per edge.
        """
        try:
            import sqlite3 as sqlite3_mod

            net_file = find_network_file(network_name)
            if not net_file:
                return JSONResponse(content={"error": f"Network not found: {network_name}"}, status_code=404)

            # Find DB
            if not db_path:
                analysis_dir = get_output_dir() / "analysis"
                db_files = list(analysis_dir.glob("*.db")) if analysis_dir.exists() else []
                if not db_files:
                    return JSONResponse(content={"error": "No analysis DB found"}, status_code=404)
                db_path = str(db_files[0])

            conn = sqlite3_mod.connect(db_path)
            conn.row_factory = sqlite3_mod.Row

            attrs = COMPARE_ATTRIBUTES

            # Build AVG query for all attributes
            avg_cols = ", ".join(f"AVG({a}) as {a}" for a in attrs)

            # Query sim_a
            rows_a = conn.execute(
                f"SELECT edge_id, {avg_cols} FROM edge_metrics WHERE simulation_id=? GROUP BY edge_id",
                (sim_a,)
            ).fetchall()

            data_a = {r['edge_id']: dict(r) for r in rows_a}

            # Query sim_b if provided
            data_b = {}
            if sim_b:
                rows_b = conn.execute(
                    f"SELECT edge_id, {avg_cols} FROM edge_metrics WHERE simulation_id=? GROUP BY edge_id",
                    (sim_b,)
                ).fetchall()
                data_b = {r['edge_id']: dict(r) for r in rows_b}

            conn.close()

            if not data_a:
                return JSONResponse(content={"error": f"No data for simulation: {sim_a}"}, status_code=404)

            # Parse network for geometry
            net = sumolib.net.readNet(str(net_file))

            # Build edge length filter
            edge_objs = {e.getID(): e for e in net.getEdges()}

            # Collect values for percentile normalization (per attribute)
            attr_values_a = {a: [] for a in attrs}
            attr_values_b = {a: [] for a in attrs}
            attr_values_diff = {a: [] for a in attrs}

            # First pass: collect values (filtered by length >= 5m)
            valid_edges = set()
            for edge_id in data_a:
                edge_obj = edge_objs.get(edge_id)
                if not edge_obj or edge_obj.getLength() < 5.0:
                    continue
                valid_edges.add(edge_id)
                for a in attrs:
                    val = data_a[edge_id].get(a)
                    if val is not None:
                        attr_values_a[a].append(val)
                    if sim_b and edge_id in data_b:
                        val_b = data_b[edge_id].get(a)
                        if val_b is not None:
                            attr_values_b[a].append(val_b)
                        if val is not None and val_b is not None:
                            attr_values_diff[a].append(val_b - val)

            # Compute percentile bounds per attribute
            def percentile_bounds(values):
                if not values:
                    return 0, 1
                s = sorted(values)
                n = len(s)
                lo = s[int(n * 0.05)]
                hi = s[min(int(n * 0.95), n - 1)]
                if hi == lo:
                    hi = lo + 1
                return lo, hi

            bounds_a = {a: percentile_bounds(attr_values_a[a]) for a in attrs}
            bounds_b = {a: percentile_bounds(attr_values_b[a]) for a in attrs}

            # Diff bounds: symmetric around 0 so that 0 = white center
            def symmetric_bounds(values):
                if not values:
                    return -1, 1
                s = sorted(values)
                n = len(s)
                lo = s[int(n * 0.05)]
                hi = s[min(int(n * 0.95), n - 1)]
                extent = max(abs(lo), abs(hi))
                if extent == 0:
                    extent = 1
                return -extent, extent

            bounds_diff = {a: symmetric_bounds(attr_values_diff[a]) for a in attrs}

            # Build GeoJSON
            features = []
            for edge_id in valid_edges:
                edge_obj = edge_objs.get(edge_id)
                if not edge_obj:
                    continue

                shape = edge_obj.getShape()
                if len(shape) < 2:
                    continue

                coords = [net.convertXY2LonLat(x, y) for x, y in shape]

                props = {
                    "id": edge_id,
                    "name": edge_obj.getName() or edge_id,
                    "length": edge_obj.getLength(),
                    "lanes": edge_obj.getLaneNumber(),
                }

                for a in attrs:
                    val_a = data_a[edge_id].get(a)

                    if val_a is not None:
                        props[f"{a}_a"] = round(val_a, 4)
                        lo, hi = bounds_a[a]
                        norm = max(0.0, min((val_a - lo) / (hi - lo), 1.0))
                        props[f"n_{a}_a"] = round(norm, 4)
                    else:
                        props[f"{a}_a"] = None
                        props[f"n_{a}_a"] = 0

                    if sim_b and edge_id in data_b:
                        val_b = data_b[edge_id].get(a)
                        if val_b is not None:
                            props[f"{a}_b"] = round(val_b, 4)
                            lo, hi = bounds_b[a]
                            norm = max(0.0, min((val_b - lo) / (hi - lo), 1.0))
                            props[f"n_{a}_b"] = round(norm, 4)

                            # Diff — symmetric around 0: normalized 0.5 = no change
                            diff = val_b - val_a if val_a is not None else 0
                            props[f"{a}_diff"] = round(diff, 4)
                            lo_d, hi_d = bounds_diff[a]
                            norm_d = max(0.0, min((diff - lo_d) / (hi_d - lo_d), 1.0))
                            props[f"n_{a}_diff"] = round(norm_d, 4)
                        else:
                            props[f"{a}_b"] = None
                            props[f"n_{a}_b"] = 0
                            props[f"{a}_diff"] = None
                            props[f"n_{a}_diff"] = 0.5
                    else:
                        props[f"{a}_b"] = None
                        props[f"n_{a}_b"] = 0
                        props[f"{a}_diff"] = None
                        props[f"n_{a}_diff"] = 0.5

                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": props
                })

            geojson = {"type": "FeatureCollection", "features": features}

            # Center
            if features:
                all_coords = []
                for f in features:
                    all_coords.extend(f["geometry"]["coordinates"])
                lons = [c[0] for c in all_coords]
                lats = [c[1] for c in all_coords]
                center = {"lon": sum(lons)/len(lons), "lat": sum(lats)/len(lats)}
            else:
                center = {"lon": 127.028, "lat": 37.497}

            # Return bounds info for legend
            bounds_info = {}
            for a in attrs:
                lo_a, hi_a = bounds_a[a]
                bounds_info[a] = {"min_a": round(lo_a, 2), "max_a": round(hi_a, 2)}
                if sim_b:
                    lo_b, hi_b = bounds_b[a]
                    lo_d, hi_d = bounds_diff[a]
                    bounds_info[a].update({
                        "min_b": round(lo_b, 2), "max_b": round(hi_b, 2),
                        "min_diff": round(lo_d, 2), "max_diff": round(hi_d, 2)
                    })

            return JSONResponse(content={
                "geojson": geojson,
                "center": center,
                "edge_count": len(features),
                "attributes": attrs,
                "bounds": bounds_info,
                "sim_a": sim_a,
                "sim_b": sim_b,
                "has_compare": sim_b is not None
            })

        except Exception as e:
            logger.error(f"Error comparing simulations: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ============================================
    # Replay API
    # ============================================

    @app.get("/api/simulation/progress")
    async def get_simulation_progress():
        """Get current simulation progress"""
        sims_dir = get_simulations_dir()
        if sims_dir:
            progress_file = sims_dir / ".sim_progress.json"
            if progress_file.exists():
                try:
                    data = json.loads(progress_file.read_text())
                    return JSONResponse(content=data)
                except Exception:
                    pass
        return JSONResponse(content={"percent": -1})

    @app.get("/api/tool/progress")
    async def get_tool_progress():
        """Get current tool execution progress"""
        output_dir = get_output_dir()
        if output_dir:
            progress_file = output_dir / ".tool_progress.json"
            if progress_file.exists():
                try:
                    return JSONResponse(content=json.loads(progress_file.read_text()))
                except Exception:
                    pass
        return JSONResponse(content={"tools": []})

    @app.get("/api/replay/list")
    async def list_replay_files():
        """List available replay files with DB description matching"""
        try:
            sims_dir = get_simulations_dir()
            if not sims_dir:
                return JSONResponse(content={"replays": [], "count": 0})

            # Load DB: map net_file stem to description
            netfile_to_desc = {}
            try:
                output_dir = get_output_dir()
                if output_dir:
                    analysis_dir = output_dir / "analysis"
                    if analysis_dir.exists():
                        db_files = list(analysis_dir.glob("*.db"))
                        if db_files and db_files[0].stat().st_size > 0:
                            conn = sqlite3.connect(str(db_files[0]))
                            try:
                                rows = conn.execute(
                                    "SELECT net_file, description FROM simulations WHERE description IS NOT NULL"
                                ).fetchall()
                                for net_file, desc in rows:
                                    if net_file:
                                        stem = Path(net_file).stem  # e.g. "selected_area.net"
                                        netfile_to_desc[stem] = desc
                            except Exception:
                                pass
                            conn.close()
            except Exception:
                pass

            replays = []
            for f in sims_dir.iterdir():
                if f.is_file() and '_replay_' in f.name and f.name.endswith('.json'):
                    parts = f.name.split('_replay_')
                    if len(parts) >= 2:
                        base_name = parts[0]
                        timestamp = parts[1].replace('.json', '')
                        size_mb = f.stat().st_size / 1024 / 1024

                        # Match by net_file stem == replay base_name
                        display_name = netfile_to_desc.get(base_name, f"{base_name} ({timestamp})")

                        replays.append({
                            "name": display_name,
                            "base_name": base_name,
                            "filename": f.name,
                            "timestamp": timestamp,
                            "size_mb": round(size_mb, 1)
                        })

            return JSONResponse(content={
                "replays": sorted(replays, key=lambda x: x["timestamp"], reverse=True),
                "count": len(replays)
            })
        except Exception as e:
            logger.error(f"Error listing replay files: {e}")
            return JSONResponse(content={"error": str(e), "replays": []}, status_code=500)

    @app.get("/api/replay/{replay_filename}")
    async def get_replay_data(replay_filename: str):
        """Load replay file data for playback"""
        import json as _json
        try:
            replay_file = find_simulation_file(replay_filename)
            if replay_file is None:
                return JSONResponse(
                    content={"error": f"Replay file not found: {replay_filename}"},
                    status_code=404
                )

            logger.info(f"Loading replay: {replay_file.name} ({replay_file.stat().st_size / 1024 / 1024:.1f} MB)")

            with open(replay_file, 'r') as f:
                data = _json.load(f)

            return JSONResponse(content=data)

        except Exception as e:
            logger.error(f"Error loading replay file: {e}")
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

    @app.post("/api/upload/od")
    async def upload_od_file(file: UploadFile = File(...)):
        """Upload OD data CSV file"""
        try:
            upload_dir = AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output" / "uploads" / "od"
            upload_dir.mkdir(parents=True, exist_ok=True)

            dest = upload_dir / file.filename
            content = await file.read()
            dest.write_bytes(content)

            logger.info(f"OD file uploaded: {file.filename} ({len(content)/1024:.1f} KB)")
            return JSONResponse(content={
                "status": "success",
                "filename": file.filename,
                "path": str(dest),
                "size": len(content)
            })
        except Exception as e:
            logger.error(f"OD upload failed: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.post("/api/upload/shapefile")
    async def upload_shapefile(files: list[UploadFile] = File(...)):
        """Upload shapefile (multiple files: .shp, .shx, .dbf, .prj, etc.)"""
        try:
            upload_dir = AgentSUMOConfig.PROJECT_ROOT / "agentsumo" / "output" / "uploads" / "shp"
            upload_dir.mkdir(parents=True, exist_ok=True)

            uploaded = []
            shp_path = None
            for f in files:
                dest = upload_dir / f.filename
                content = await f.read()
                dest.write_bytes(content)
                uploaded.append(f.filename)
                if f.filename.endswith(".shp"):
                    shp_path = str(dest)

            logger.info(f"Shapefile uploaded: {uploaded}")
            return JSONResponse(content={
                "status": "success",
                "files": uploaded,
                "shp_path": shp_path
            })
        except Exception as e:
            logger.error(f"Shapefile upload failed: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.post("/api/clean")
    async def clean_output():
        """Clean output directory (same logic as clean.py)"""
        try:
            output_dir = get_output_dir()
            if output_dir is None:
                return JSONResponse(content={"message": "No output directory", "deleted": 0})

            preserve_files = {"vehicle_types.add.xml"}
            clean_folders = ["networks", "trips", "simulations", "analysis", "reports", "visualizations", "additional"]

            deleted_count = 0
            preserved_count = 0

            for folder_name in clean_folders:
                folder = output_dir / folder_name
                if not folder.exists():
                    continue

                for entry in folder.iterdir():
                    if entry.name in preserve_files:
                        preserved_count += 1
                    elif entry.is_file():
                        entry.unlink()
                        deleted_count += 1
                    elif entry.is_dir():
                        import shutil
                        shutil.rmtree(entry)
                        deleted_count += 1

            # Also delete state file
            if output_dir:
                state_file = output_dir / ".agentsumo_state.json"
                if state_file.exists():
                    state_file.unlink()
                    deleted_count += 1

            logger.info(f"Clean output: {deleted_count} deleted, {preserved_count} preserved")

            return JSONResponse(content={
                "status": "success",
                "deleted": deleted_count,
                "preserved": preserved_count,
                "message": f"{deleted_count} files deleted, {preserved_count} preserved"
            })
        except Exception as e:
            logger.error(f"Error cleaning output: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.post("/api/reset-session")
    async def reset_session():
        """Reset entire session: clean output files + recreate AgentSUMO instance"""
        global _agent
        try:
            # 1. Close existing agent (MCP connections)
            async with _agent_lock:
                if _agent:
                    await _agent.close()
                    _agent = None

            # 2. Clean output files
            output_dir = get_output_dir()
            deleted_count = 0
            if output_dir:
                preserve_files = {"vehicle_types.add.xml"}
                clean_folders = ["networks", "trips", "simulations", "analysis", "reports", "visualizations", "additional"]
                for folder_name in clean_folders:
                    folder = output_dir / folder_name
                    if not folder.exists():
                        continue
                    for entry in folder.iterdir():
                        if entry.name in preserve_files:
                            continue
                        elif entry.is_file():
                            entry.unlink()
                            deleted_count += 1
                        elif entry.is_dir():
                            import shutil
                            shutil.rmtree(entry)
                            deleted_count += 1

            # 3. Delete state file
            if output_dir:
                state_file = output_dir / ".agentsumo_state.json"
                if state_file.exists():
                    state_file.unlink()
                    logger.info("State file deleted")

            # 4. Recreate agent (will be lazy-created on next get_agent() call)
            logger.info(f"Session reset: {deleted_count} files deleted, agent will be recreated on next request")

            return JSONResponse(content={
                "status": "success",
                "deleted": deleted_count,
                "message": f"Session reset. {deleted_count} files deleted."
            })
        except Exception as e:
            logger.error(f"Error resetting session: {e}")
            return JSONResponse(content={"error": str(e)}, status_code=500)

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
    # WebSocket for Chat
    # ============================================

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        """WebSocket endpoint for chat"""
        await websocket.accept()
        logger.info("WebSocket connection established")

        try:
            agent = await get_agent()

            # Set up progress callback — writes to file for polling
            _progress_file = Path(get_output_dir() or "/tmp") / ".tool_progress.json"

            async def progress_callback(tool_name: str, status: str, message: str = None):
                """Write progress to file for frontend polling"""
                logger.info(f"📡 Progress: {tool_name} - {status}")
                try:
                    if tool_name == "__intermediate_text__":
                        # Send intermediate text directly via WS (best-effort)
                        try:
                            await websocket.send_json({"type": "intermediate", "data": message})
                        except Exception:
                            pass
                        return

                    # Read current progress state
                    tools = []
                    if _progress_file.exists():
                        try:
                            tools = json.loads(_progress_file.read_text()).get("tools", [])
                        except Exception:
                            tools = []

                    if status == "started":
                        tools.append({"tool": tool_name, "status": "started"})
                    elif status in ("completed", "error"):
                        # Update latest matching tool
                        for t in reversed(tools):
                            if t["tool"] == tool_name and t["status"] == "started":
                                t["status"] = status
                                break

                    _progress_file.write_text(json.dumps({"tools": tools}))
                except Exception as e:
                    logger.warning(f"Failed to write progress: {e}")

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
                        # Clean up tool progress file
                        try:
                            _progress_file.unlink(missing_ok=True)
                        except Exception:
                            pass
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
