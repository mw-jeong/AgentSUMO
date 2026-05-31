"""
Vehicle management tools for SUMO MCP Server.
"""

import xml.etree.ElementTree as ET
import datetime
import random
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
import sumolib
import logging

from agentsumo_mcp.settings.settings import sumo_environment
from agentsumo_mcp.utils.file_utils import ensure_directory
from agentsumo_mcp.utils.path_utils import get_output_path
from agentsumo_mcp.utils.sumo_utils import (
    geocode_location,
    get_edge_ids_from_road_name,
    find_nearest_edge,
    find_nearest_edges_ranked,
    check_coordinates_in_network
)

logger = logging.getLogger("agentsumo_mcp.vehicle_manager")


class VehicleManager:
    """Vehicle management class for SUMO simulations."""

    def __init__(self):
        self.environment = sumo_environment

    def generate_vehicles(
        self,
        route_file: str,
        net_file: str,
        source_location: str,
        destination_location: str,
        vehicle_id: str = "genveh_0",
        depart_time: float = 0.0,
        depart_time_range: Optional[List[float]] = None,
        vehicle_count: int = 1,
        output_dir: str = "output/trips",
        use_geocoding: bool = False,
        search_radius: float = 0.3
    ) -> Dict[str, Any]:
        """
        Add vehicles from source to destination with optimal path calculation.

        Supports two modes:
        1. Road name-based: Searches by road name using edge.getName()
        2. Location-based: Uses geocoding to find nearest edges

        Args:
            route_file: Route file path
            net_file: Network file path
            source_location: Source location (road name or place name)
                - Road name mode: '강남대로', '테헤란로'
                - Location mode: '강남역', 'Gangnam Station, Seoul'
            destination_location: Destination location (road name or place name)
            vehicle_id: Vehicle ID prefix (default: "genveh_0")
            depart_time: Departure time in seconds (default: 0.0)
            depart_time_range: Departure time range [min, max] in seconds (optional)
            vehicle_count: Number of vehicles to generate (default: 1)
            output_dir: Output directory for results
            use_geocoding: If True, use geocoding + nearest edge search (default: False)
            search_radius: Search radius in km for nearest edge (default: 0.3 = 300m)

        Returns:
            Dict[str, Any]: Generation result with status and metadata
        """
        try:
            logger.info(f"Vehicle generation started: {source_location} -> {destination_location} (geocoding: {use_geocoding})")

            # Get source and destination edges based on mode
            if use_geocoding:
                # NEW: Location-based approach (geocoding + nearest edge)

                # Step 1: Geocode locations
                source_coords = geocode_location(source_location)
                if not source_coords:
                    return {"status": "error", "message": f"Source location not found: {source_location}"}

                dest_coords = geocode_location(destination_location)
                if not dest_coords:
                    return {"status": "error", "message": f"Destination location not found: {destination_location}"}

                # Step 2: Validate coordinates are within network bounds
                source_valid, source_info = check_coordinates_in_network(
                    net_file, source_coords[0], source_coords[1], buffer_km=1.0
                )
                if not source_valid:
                    bbox = source_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"Source '{source_location}' is outside network bounds.\n"
                            f"- Input coordinates: ({source_coords[0]:.4f}, {source_coords[1]:.4f})\n"
                            f"- Network bounds: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- Distance from network center: {source_info.get('distance_km', 'N/A')}km\n"
                            f"Hint: generate a network that covers this location first."
                        )
                    }

                dest_valid, dest_info = check_coordinates_in_network(
                    net_file, dest_coords[0], dest_coords[1], buffer_km=1.0
                )
                if not dest_valid:
                    bbox = dest_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"Destination '{destination_location}' is outside network bounds.\n"
                            f"- Input coordinates: ({dest_coords[0]:.4f}, {dest_coords[1]:.4f})\n"
                            f"- Network bounds: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- Distance from network center: {dest_info.get('distance_km', 'N/A')}km\n"
                            f"Hint: generate a network that covers this location first."
                        )
                    }

                # Step 3: Find nearest edges (within validated network)
                source_result = find_nearest_edge(net_file, source_coords[0], source_coords[1], search_radius)
                if not source_result:
                    return {
                        "status": "error",
                        "message": f"No edge found within {search_radius}km of source coordinates {source_coords}."
                    }
                source_edge, source_dist = source_result

                dest_result = find_nearest_edge(net_file, dest_coords[0], dest_coords[1], search_radius)
                if not dest_result:
                    return {
                        "status": "error",
                        "message": f"No edge found within {search_radius}km of destination coordinates {dest_coords}."
                    }
                destination_edge, dest_dist = dest_result

                logger.info(f"Geocoding success: source={source_edge} ({source_dist:.1f}m), destination={destination_edge} ({dest_dist:.1f}m)")

            else:
                # Road name-based approach (uses edge.getName())
                source_edge_ids = get_edge_ids_from_road_name(net_file, source_location)
                destination_edge_ids = get_edge_ids_from_road_name(net_file, destination_location)

                if not source_edge_ids or not destination_edge_ids:
                    return {"status": "error", "message": "Could not find valid source or destination road name."}

                # Select representative edges (middle values)
                source_edge = source_edge_ids[len(source_edge_ids)//2]
                destination_edge = destination_edge_ids[len(destination_edge_ids)//2]

                logger.info(f"Road name match success: source={source_edge}, destination={destination_edge}")

            # Calculate shortest path
            net = sumolib.net.readNet(net_file)
            try:
                source = net.getEdge(source_edge)
                dest = net.getEdge(destination_edge)
            except Exception as e:
                return {"status": "error", "message": f"Edge not found in network: {e}"}

            path_edges = net.getShortestPath(source, dest, vClass="passenger")[0]
            if not path_edges:
                return {"status": "error", "message": "No shortest path found."}

            route_string = " ".join([e.getID() for e in path_edges])

            # Copy and modify file
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_vehgen_{ts}.rou.xml"
            ensure_directory(output_path)

            # Check if source and destination are the same file
            if Path(route_file).resolve() == route_file_copy.resolve():
                route_file_copy = Path(route_file)
            else:
                shutil.copy2(route_file, route_file_copy)

            tree = ET.parse(route_file_copy)
            root = tree.getroot()

            # Generate vehicles (with time distribution)
            for i in range(vehicle_count):
                if depart_time_range:
                    depart = random.uniform(depart_time_range[0], depart_time_range[1])
                else:
                    depart = depart_time + i * 10  # 10-second intervals

                vehicle = ET.SubElement(root, "vehicle", {
                    "id": f"{vehicle_id}_{i}",
                    "type": "passenger",
                    "depart": str(depart)
                })
                ET.SubElement(vehicle, "route", {"edges": route_string})

            tree.write(route_file_copy, encoding="utf-8", xml_declaration=True)

            mode_msg = "location-based (geocoding)" if use_geocoding else "road-name-based"
            msg = (f"Added {vehicle_count} vehicles. "
                   f"Source: {source_location}, Destination: {destination_location} ({mode_msg})")
            logger.info(f"Vehicle generation complete: {msg}")
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}

        except Exception as e:
            logger.error(f"Vehicle generation failed: {e}")
            return {"status": "error", "message": str(e)}

    def generate_flow(
        self,
        route_file: str,
        net_file: str,
        source: str = None,
        dest: str = None,
        begin: float = 0.0,
        end: float = 3600.0,
        vehs_per_hour: int = None,
        number: int = None,
        flow_id: str = None,
        output_dir: str = "output/trips",
        use_geocoding: bool = True,
        search_radius: float = 0.3,
        source_lat: float = None,
        source_lon: float = None,
        dest_lat: float = None,
        dest_lon: float = None,
    ) -> Dict[str, Any]:
        """
        Generate a flow from source to destination.

        Two ways to specify locations:
        1. Place names (source/dest) — uses geocoding to find coordinates
        2. Direct coordinates (source_lat/lon, dest_lat/lon) — skips geocoding

        Two ways to specify vehicle count:
        1. vehs_per_hour — rate-based (SUMO <flow vehsPerHour="N">)
        2. number — total count (SUMO <flow number="N">)
        Exactly one of (vehs_per_hour, number) must be provided.
        """
        try:
            # Validate vehicle count parameters
            if vehs_per_hour is None and number is None:
                return {"status": "error", "message": "Must specify either vehs_per_hour or number."}
            if vehs_per_hour is not None and number is not None:
                return {"status": "error", "message": "Cannot specify both vehs_per_hour and number."}

            count_desc = f"{number} vehicles" if number else f"{vehs_per_hour} vehs/hour"

            # Determine edge resolution mode
            has_coords = all(v is not None for v in [source_lat, source_lon, dest_lat, dest_lon])
            has_names = source is not None and dest is not None
            source_coords = None  # Will be set in geocoding mode
            dest_coords = None

            if not has_coords and not has_names:
                return {"status": "error", "message": "Must specify either source/dest (place names) or source_lat/lon, dest_lat/lon (coordinates)."}

            logger.info(f"Flow generation started: {'coordinate mode' if has_coords else 'place name mode'} ({begin}-{end}s, {count_desc})")

            # Generate flow ID if not provided
            if not flow_id:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                flow_id = f"flow_{ts}"

            if has_coords:
                # COORDINATE MODE — skip geocoding, use find_nearest_edge directly
                source_valid, source_info = check_coordinates_in_network(
                    net_file, source_lat, source_lon, buffer_km=1.0
                )
                if not source_valid:
                    return {"status": "error", "message": f"Source coordinates ({source_lat}, {source_lon}) are outside network bounds."}

                dest_valid, dest_info = check_coordinates_in_network(
                    net_file, dest_lat, dest_lon, buffer_km=1.0
                )
                if not dest_valid:
                    return {"status": "error", "message": f"Destination coordinates ({dest_lat}, {dest_lon}) are outside network bounds."}

                source_result = find_nearest_edge(net_file, source_lat, source_lon, search_radius)
                if not source_result:
                    return {"status": "error", "message": f"No edge found within {search_radius}km of source coordinates ({source_lat},{source_lon})."}
                source_edge, source_dist = source_result

                dest_result = find_nearest_edge(net_file, dest_lat, dest_lon, search_radius)
                if not dest_result:
                    return {"status": "error", "message": f"No edge found within {search_radius}km of destination coordinates ({dest_lat},{dest_lon})."}
                destination_edge, dest_dist = dest_result

                logger.info(f"Coordinates -> edge: source={source_edge} ({source_dist:.1f}m), destination={destination_edge} ({dest_dist:.1f}m)")
                coord_desc = f"({source_lat:.4f},{source_lon:.4f})->({dest_lat:.4f},{dest_lon:.4f})"

            elif use_geocoding and has_names:
                # GEOCODING MODE — existing logic
                source_coords = geocode_location(source)
                if not source_coords:
                    return {"status": "error", "message": f"Source location not found: {source}"}

                dest_coords = geocode_location(dest)
                if not dest_coords:
                    return {"status": "error", "message": f"Destination location not found: {dest}"}

                source_valid, source_info = check_coordinates_in_network(
                    net_file, source_coords[0], source_coords[1], buffer_km=1.0
                )
                if not source_valid:
                    bbox = source_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"Source '{source}' is outside network bounds.\n"
                            f"- Input coordinates: ({source_coords[0]:.4f}, {source_coords[1]:.4f})\n"
                            f"- Network bounds: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- Distance from network center: {source_info.get('distance_km', 'N/A')}km\n"
                            f"Hint: generate a network that covers this location first."
                        )
                    }

                dest_valid, dest_info = check_coordinates_in_network(
                    net_file, dest_coords[0], dest_coords[1], buffer_km=1.0
                )
                if not dest_valid:
                    bbox = dest_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"Destination '{dest}' is outside network bounds.\n"
                            f"- Input coordinates: ({dest_coords[0]:.4f}, {dest_coords[1]:.4f})\n"
                            f"- Network bounds: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- Distance from network center: {dest_info.get('distance_km', 'N/A')}km\n"
                            f"Hint: generate a network that covers this location first."
                        )
                    }

                source_result = find_nearest_edge(net_file, source_coords[0], source_coords[1], search_radius)
                if not source_result:
                    return {"status": "error", "message": f"No edge found within {search_radius}km of source coordinates {source_coords}."}
                source_edge, source_dist = source_result

                dest_result = find_nearest_edge(net_file, dest_coords[0], dest_coords[1], search_radius)
                if not dest_result:
                    return {"status": "error", "message": f"No edge found within {search_radius}km of destination coordinates {dest_coords}."}
                destination_edge, dest_dist = dest_result

                logger.info(f"Geocoding success: source={source_edge} ({source_dist:.1f}m), destination={destination_edge} ({dest_dist:.1f}m)")
                coord_desc = f"{source} -> {dest}"

            else:
                return {"status": "error", "message": "Flow generation only supports geocoding mode or coordinate mode."}

            # Calculate shortest path with fallback retry
            net = sumolib.net.readNet(net_file)
            path_edges = None

            # Try primary edges first
            try:
                source_edge_obj = net.getEdge(source_edge)
                dest_edge_obj = net.getEdge(destination_edge)
                path_edges = net.getShortestPath(source_edge_obj, dest_edge_obj, vClass="passenger")[0]
            except Exception as e:
                logger.warning(f"Primary edge path calculation failed: {e}")

            # If primary path fails, try alternative edges via fallback retry
            if not path_edges:
                logger.info("Primary path failed - starting fallback retry")

                # Get ranked candidates for source and dest
                source_candidates = find_nearest_edges_ranked(
                    net_file, source_lat or 0, source_lon or 0, search_radius
                ) if has_coords else [(source_edge, 0)]
                dest_candidates = find_nearest_edges_ranked(
                    net_file, dest_lat or 0, dest_lon or 0, search_radius
                ) if has_coords else [(destination_edge, 0)]

                # For geocoding mode, get candidates from resolved coordinates
                if not has_coords and has_names:
                    if source_coords:
                        source_candidates = find_nearest_edges_ranked(
                            net_file, source_coords[0], source_coords[1], search_radius
                        )
                    if dest_coords:
                        dest_candidates = find_nearest_edges_ranked(
                            net_file, dest_coords[0], dest_coords[1], search_radius
                        )

                for s_edge_id, s_dist in source_candidates:
                    for d_edge_id, d_dist in dest_candidates:
                        if s_edge_id == source_edge and d_edge_id == destination_edge:
                            continue  # Already tried
                        try:
                            s_obj = net.getEdge(s_edge_id)
                            d_obj = net.getEdge(d_edge_id)
                            candidate_path = net.getShortestPath(s_obj, d_obj, vClass="passenger")[0]
                            if candidate_path:
                                path_edges = candidate_path
                                logger.info(
                                    f"Fallback success: using "
                                    f"{s_edge_id}({s_dist:.0f}m)->{d_edge_id}({d_dist:.0f}m) "
                                    f"instead of {source_edge}->{destination_edge}"
                                )
                                source_edge = s_edge_id
                                destination_edge = d_edge_id
                                break
                        except Exception:
                            continue
                    if path_edges:
                        break

            if not path_edges:
                return {"status": "error", "message": "No shortest path found. No path exists between source and destination edges."}

            # Copy and modify file
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_flow_{ts}.rou.xml"
            ensure_directory(output_path)

            if Path(route_file).resolve() == route_file_copy.resolve():
                route_file_copy = Path(route_file)
            else:
                shutil.copy2(route_file, route_file_copy)

            tree = ET.parse(route_file_copy)
            root = tree.getroot()

            # Generate flow with safety parameters
            flow_attrs = {
                "id": flow_id,
                "from": source_edge,
                "to": destination_edge,
                "begin": str(begin),
                "end": str(end),
                "type": "passenger",
                "departLane": "free",
                "departPos": "random_free",
                "departSpeed": "random"
            }
            if number is not None:
                flow_attrs["number"] = str(number)
            else:
                flow_attrs["vehsPerHour"] = str(vehs_per_hour)

            ET.SubElement(root, "flow", flow_attrs)
            tree.write(route_file_copy, encoding="utf-8", xml_declaration=True)

            msg = f"Flow '{flow_id}' generated: {coord_desc} ({begin}-{end}s, {count_desc})"
            logger.info(msg)
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}

        except Exception as e:
            logger.error(f"Flow generation failed: {e}")
            return {"status": "error", "message": str(e)}

    def edit_vehicle_types(
        self,
        route_file: str,
        electric_ratio: float,
        output_dir: str = "output/trips"
    ) -> Dict[str, Any]:
        """
        Reassign vehicle types in the route file according to the electric_ratio.

        Args:
            route_file: Route file path
            electric_ratio: Ratio of electric vehicles (0.0 to 1.0)
            output_dir: Output directory for results

        Returns:
            Dict[str, Any]: Edit result with status and metadata
        """
        try:
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_vehtype_{ts}.rou.xml"
            ensure_directory(output_path)

            # Check if source and destination are the same file
            if Path(route_file).resolve() == route_file_copy.resolve():
                route_file_copy = Path(route_file)
            else:
                shutil.copy2(route_file, route_file_copy)

            tree = ET.parse(route_file_copy)
            root = tree.getroot()
            vehicles = root.findall("vehicle")

            for vehicle in vehicles:
                rnd = random.random()
                if rnd < electric_ratio:
                    vehicle.set("type", "electric")
                else:
                    vehicle.set("type", "gasoline")

            tree.write(route_file_copy, encoding="utf-8", xml_declaration=True)

            msg = f"Vehicle types reassigned (Electric Ratio: {electric_ratio})."
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}

        except Exception as e:
            return {"status": "error", "message": str(e)}
