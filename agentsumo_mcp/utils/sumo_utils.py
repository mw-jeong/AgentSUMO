"""
SUMO-specific utilities for SUMO MCP Server.

Includes:
- Network and road utilities (edge ID lookup, coordinate validation)
- Geocoding utilities (location name to coordinate conversion)
- SUMO-specific analysis tools
- OSM road name extraction
"""

import os
import subprocess
import xml.etree.ElementTree as ET
from collections import deque, defaultdict
from typing import List, Optional, Tuple, Dict, Set
import sumolib
import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from agentsumo_mcp.settings.settings import sumo_environment

logger = logging.getLogger("agentsumo_mcp.sumo_utils")

# Cache for largest connected component edge sets, keyed by net_file path
_largest_component_cache: Dict[str, Set[str]] = {}


def _get_largest_component_edges(net) -> Set[str]:
    """
    Compute the largest weakly connected component of a SUMO network.

    Uses BFS on nodes treating all edges as undirected. Returns the set of
    edge IDs belonging to the largest component. Internal edges (junction
    edges starting with ':') are excluded from the component calculation
    but edges in the largest component are returned.

    Args:
        net: sumolib.net.Net object (already loaded)

    Returns:
        Set[str]: Edge IDs in the largest weakly connected component
    """
    # Only consider non-internal edges for component detection
    edges = [e for e in net.getEdges() if not e.getID().startswith(':')]

    # Build node adjacency (undirected — weakly connected)
    adj: Dict[str, Set[str]] = defaultdict(set)
    for edge in edges:
        fn = edge.getFromNode().getID()
        tn = edge.getToNode().getID()
        adj[fn].add(tn)
        adj[tn].add(fn)

    # BFS to find all components, track the largest
    visited: Set[str] = set()
    largest: Set[str] = set()

    for start in adj:
        if start in visited:
            continue
        component: Set[str] = set()
        queue = deque([start])
        while queue:
            n = queue.popleft()
            if n in visited:
                continue
            visited.add(n)
            component.add(n)
            for nb in adj[n]:
                if nb not in visited:
                    queue.append(nb)
        if len(component) > len(largest):
            largest = component

    # Convert node set → edge ID set
    component_edges = {e.getID() for e in edges if e.getFromNode().getID() in largest}

    logger.info(
        f"Connected component analysis: {len(component_edges)} edges "
        f"in largest component out of {len(edges)} total "
        f"({len(component_edges)/len(edges)*100:.1f}%)"
    )

    return component_edges


# =============== GEOCODING UTILITIES ===============

def geocode_location(
    location_name: str,
    user_agent: str = "agent-sumo",
    timeout: int = 10
) -> Optional[Tuple[float, float]]:
    """
    Convert location name to geographic coordinates (latitude, longitude).
    
    Args:
        location_name: Location name to geocode (e.g., '강남역', 'Gangnam Station, Seoul')
        user_agent: User agent for Nominatim API (default: 'agent-sumo')
        timeout: Request timeout in seconds (default: 10)
        
    Returns:
        Tuple[float, float]: (latitude, longitude) or None if geocoding fails
        
    Examples:
        >>> coords = geocode_location("강남역")
        >>> print(coords)
        (37.497952, 127.027619)
        
        >>> coords = geocode_location("Times Square, New York")
        >>> print(coords)
        (40.758896, -73.985130)
    """
    try:
        geolocator = Nominatim(user_agent=user_agent, timeout=timeout)
        location = geolocator.geocode(location_name, exactly_one=True)
        
        if not location:
            logger.warning(f"Location not found: {location_name}")
            return None

        logger.info(f"Geocoding success: {location_name} -> ({location.latitude}, {location.longitude})")
        return (location.latitude, location.longitude)

    except GeocoderTimedOut:
        logger.error(f"Geocoding timeout: {location_name}")
        return None
    except GeocoderServiceError as e:
        logger.error(f"Geocoding service error: {e}")
        return None
    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        return None


# =============== NETWORK AND ROAD UTILITIES ===============

def get_edge_ids_from_road_name(net_file: str, road_name: str) -> List[str]:
    """
    Get edge IDs from network file based on road name.

    Uses edge.getName() from SUMO network (requires --output.street-names option).

    Args:
        net_file: SUMO network file path
        road_name: Road name (e.g., '테헤란로', '강남대로')

    Returns:
        List[str]: List of edge IDs matching the road name

    Raises:
        ValueError: If network file not found or road name not found
    """
    if not os.path.exists(net_file):
        raise ValueError(f"Network file not found: {net_file}")

    net = sumolib.net.readNet(net_file)
    matching_edges = [e.getID() for e in net.getEdges() if e.getName() == road_name]

    if not matching_edges:
        raise ValueError(f"No edges found for road name: {road_name}")

    logger.info(f"'{road_name}' -> found {len(matching_edges)} edges")
    return matching_edges


def check_coordinates_in_network(
    net_file: str,
    lat: float,
    lon: float,
    buffer_km: float = 1.0
) -> Tuple[bool, dict]:
    """
    Check if geographic coordinates are within network bounds.
    
    Args:
        net_file: SUMO network file path
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        buffer_km: Buffer distance in kilometers to allow outside network (default: 1.0)
        
    Returns:
        Tuple[bool, dict]: 
            - is_valid: True if coordinates are within network bounds + buffer
            - network_info: Dictionary with network metadata
                {
                    'bbox': [min_lon, min_lat, max_lon, max_lat],
                    'center': (center_lat, center_lon),
                    'distance_km': distance from network center,
                    'is_within_bounds': True/False (before buffer)
                }
    
    Examples:
        >>> is_valid, info = check_coordinates_in_network("gangnam.net.xml", 37.498, 127.028)
        >>> if not is_valid:
        ...     print(f"Coordinates outside network bounds: {info}")
    """
    try:
        net = sumolib.net.readNet(net_file)
        
        # Convert input coordinates to network XY coordinates
        x, y = net.convertLonLat2XY(lon, lat)
        
        # Get network bounding box (in network XY coordinates)
        # getBBoxXY() returns ((xmin, ymin), (xmax, ymax)) or (xmin, ymin, xmax, ymax)
        boundary = net.getBBoxXY()
        if len(boundary) == 2:
            # Format: ((xmin, ymin), (xmax, ymax))
            (xmin, ymin), (xmax, ymax) = boundary
        else:
            # Format: (xmin, ymin, xmax, ymax)
            xmin, ymin, xmax, ymax = boundary
        
        # Convert buffer from km to meters (network uses meters)
        buffer_m = buffer_km * 1000
        
        # Check if coordinates are within bounds (with buffer)
        is_within_bounds = (
            xmin <= x <= xmax and
            ymin <= y <= ymax
        )
        
        is_within_buffer = (
            (xmin - buffer_m) <= x <= (xmax + buffer_m) and
            (ymin - buffer_m) <= y <= (ymax + buffer_m)
        )
        
        # Calculate network center in XY coordinates
        center_x = (xmin + xmax) / 2
        center_y = (ymin + ymax) / 2
        
        # Calculate distance from center in meters, then convert to km
        distance_m = ((x - center_x)**2 + (y - center_y)**2)**0.5
        distance_km = distance_m / 1000
        
        # Convert bbox corners back to lat/lon for info (with better error handling)
        try:
            min_lon, min_lat = net.convertXY2LonLat(xmin, ymin)
            max_lon, max_lat = net.convertXY2LonLat(xmax, ymax)
            center_lon, center_lat = net.convertXY2LonLat(center_x, center_y)
            bbox = [min_lon, min_lat, max_lon, max_lat]
            center = (center_lat, center_lon)
        except:
            # Fallback: use XY coordinates if projection fails
            bbox = [xmin, ymin, xmax, ymax]
            center = (center_x, center_y)
            logger.debug("Using XY coordinates for bbox (projection unavailable)")
        
        network_info = {
            'bbox': bbox,
            'center': center,
            'distance_km': round(distance_km, 2),
            'is_within_bounds': is_within_bounds,
            'buffer_km': buffer_km
        }
        
        if not is_within_buffer:
            logger.warning(
                f"Coordinates ({lat}, {lon}) are outside network bounds. "
                f"Distance from network center: {distance_km:.2f}km"
            )

        return (is_within_buffer, network_info)

    except Exception as e:
        logger.error(f"Network validation failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        # Fail gracefully - allow operation to continue
        return (True, {'error': str(e)})


def find_nearest_edge(
    net_file: str,
    lat: float,
    lon: float,
    radius: float = 0.3
) -> Optional[Tuple[str, float]]:
    """
    Find the nearest edge to a geographic coordinate, filtered to the largest
    connected component of the network.

    Edges on disconnected islands (parking lots, park paths, service roads)
    are excluded so that any two edges returned by this function are guaranteed
    to be in the same weakly connected component — eliminating "shortest path
    not found" failures caused by disconnected network fragments.

    Args:
        net_file: SUMO network file path
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        radius: Search radius in kilometers (default: 0.3 = 300 meters)

    Returns:
        Tuple[str, float]: (edge_id, distance_in_meters) or None if no edge found
    """
    try:
        net = sumolib.net.readNet(net_file)

        # Get or compute the largest connected component (cached per net_file)
        abs_path = os.path.abspath(net_file)
        if abs_path not in _largest_component_cache:
            _largest_component_cache[abs_path] = _get_largest_component_edges(net)
        largest_component = _largest_component_cache[abs_path]

        # Convert lat/lon to network coordinates (x, y)
        x, y = net.convertLonLat2XY(lon, lat)

        # Convert radius from km to meters (SUMO uses meters internally)
        radius_m = radius * 1000

        # Get neighboring edges within radius
        edges = net.getNeighboringEdges(x, y, radius_m)

        if not edges or len(edges) == 0:
            logger.warning(
                f"No edge found within {radius}km of coordinates ({lat}, {lon}). "
                f"Try increasing the radius."
            )
            return None

        # Filter to largest connected component only
        filtered = [(edge, dist) for edge, dist in edges if edge.getID() in largest_component]

        if not filtered:
            logger.warning(
                f"All edges near ({lat}, {lon}) belong to disconnected components. "
                f"{len(edges)} edges before filtering -> 0 after. Falling back to the closest original edge."
            )
            filtered = list(edges)

        # Sort by distance and pick the closest edge
        distances_and_edges = sorted([(dist, edge) for edge, dist in filtered], key=lambda x: x[0])
        dist, closest_edge = distances_and_edges[0]

        edge_id = closest_edge.getID()
        skipped = len(edges) - len(filtered)
        if skipped > 0:
            logger.info(
                f"Nearest edge found: {edge_id} "
                f"(coords: {lat}, {lon}, distance: {dist:.2f}m, "
                f"excluded {skipped} disconnected edges)"
            )
        else:
            logger.info(
                f"Nearest edge found: {edge_id} "
                f"(coords: {lat}, {lon}, distance: {dist:.2f}m)"
            )

        return (edge_id, dist)

    except ImportError as e:
        logger.error(
            "pyproj library is required. Install with: pip install pyproj"
        )
        raise RuntimeError("pyproj is not installed.") from e
    except Exception as e:
        logger.error(f"Nearest edge search failed: {e}")
        return None


def find_nearest_edges_ranked(
    net_file: str,
    lat: float,
    lon: float,
    radius: float = 0.3,
    max_candidates: int = 5
) -> List[Tuple[str, float]]:
    """
    Return multiple candidate edges ranked by distance, filtered to the largest
    connected component. Used by generate_flow() for fallback retry when the
    closest edge fails path computation.

    Args:
        net_file: SUMO network file path
        lat: Latitude (WGS84)
        lon: Longitude (WGS84)
        radius: Search radius in kilometers (default: 0.3)
        max_candidates: Maximum number of candidates to return (default: 5)

    Returns:
        List of (edge_id, distance_in_meters), sorted by distance ascending.
        Empty list if no edges found.
    """
    try:
        net = sumolib.net.readNet(net_file)

        abs_path = os.path.abspath(net_file)
        if abs_path not in _largest_component_cache:
            _largest_component_cache[abs_path] = _get_largest_component_edges(net)
        largest_component = _largest_component_cache[abs_path]

        x, y = net.convertLonLat2XY(lon, lat)
        radius_m = radius * 1000
        edges = net.getNeighboringEdges(x, y, radius_m)

        if not edges:
            return []

        filtered = [(edge, dist) for edge, dist in edges if edge.getID() in largest_component]
        if not filtered:
            filtered = list(edges)

        ranked = sorted([(dist, edge) for edge, dist in filtered], key=lambda x: x[0])
        return [(edge.getID(), dist) for dist, edge in ranked[:max_candidates]]

    except Exception as e:
        logger.error(f"Ranked nearest-edge search failed: {e}")
        return []


def run_attribute_stats(input_path: str) -> str:
    """
    Run SUMO attribute statistics tool.
    
    Args:
        input_path: Input file path
        
    Returns:
        str: Statistics output
        
    Raises:
        RuntimeError: If tool execution fails
    """
    import sys
    
    try:
        attribute_stats_path = sumo_environment.get_tool_path("output/attributeStats.py")
        
        if not os.path.exists(attribute_stats_path):
            raise FileNotFoundError(f"attributeStats.py not found at: {attribute_stats_path}")
        
        # Verify input file exists
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        env = os.environ.copy()
        env['SUMO_HOME'] = sumo_environment.SUMO_HOME

        # attributeStats.py is a Python script, so run it through the Python interpreter
        result = subprocess.run([
            sys.executable,  # current Python interpreter
            attribute_stats_path,
            input_path
        ], capture_output=True, text=True, check=True, env=env)

        return result.stdout
    except subprocess.CalledProcessError as e:
        # attributeStats.py execution failed (stderr included)
        raise RuntimeError(
            f"attributeStats failed for {input_path}\n"
            f"Return code: {e.returncode}\n"
            f"Stderr: {e.stderr}\n"
            f"Stdout: {e.stdout}"
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"File not found: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}")




def get_road_names_from_edges(
    edge_ids: List[str],
    net_file: str
) -> Dict[str, str]:
    """
    Convert SUMO edge IDs to actual road names using edge.getName().

    Uses edge.getName() from SUMO network (requires --output.street-names option).

    Args:
        edge_ids: List of SUMO edge IDs (e.g., ["194926855#1", "420901920#0"])
        net_file: SUMO network file path

    Returns:
        Dict mapping edge_id → road_name

    Example:
        {
            "194926855#1": "9th Avenue",
            "420901920#0": "Broadway",
            "-481315648#1": "West 42nd Street"
        }
    """
    try:
        net = sumolib.net.readNet(net_file)
        result = {}

        for edge_id in edge_ids:
            try:
                edge = net.getEdge(edge_id)
                name = edge.getName()
                result[edge_id] = name if name else "Unnamed Road"
            except Exception:
                result[edge_id] = f"Unknown ({edge_id})"

        logger.info(f"Converted {len(edge_ids)} edge IDs to road names")
        return result

    except Exception as e:
        logger.error(f"Road name conversion failed: {e}")
        return {edge_id: f"Error ({edge_id})" for edge_id in edge_ids}


# =============== ROAD ANALYSIS UTILITIES ===============

def analyze_road_segments(
    net_file: str,
    edge_ids: List[str],
    include_lane_details: bool = True
) -> Dict[str, any]:
    """
    Analyze detailed information of road segments.
    
    Args:
        net_file: SUMO network file path
        edge_ids: List of edge IDs to analyze
        include_lane_details: Whether to include per-lane information
        
    Returns:
        Dict containing:
        - segments: List of segment details
        - statistics: Overall statistics
        - summary: Human-readable summary
    """
    try:
        import sumolib
        
        # Load network
        net = sumolib.net.readNet(net_file)
        
        segments = []
        total_lanes = 0
        total_length = 0.0
        speed_limits = []
        lane_counts = []
        
        for edge_id in edge_ids:
            try:
                edge = net.getEdge(edge_id)
                lanes = edge.getLanes()
                
                segment_info = {
                    "edge_id": edge_id,
                    "num_lanes": len(lanes),
                    "total_length": edge.getLength(),
                    "lanes": []
                }
                
                # Per-lane details
                if include_lane_details:
                    for i, lane in enumerate(lanes, 1):
                        lane_info = {
                            "lane_index": i,
                            "speed_limit_ms": lane.getSpeed(),
                            "speed_limit_kmh": lane.getSpeed() * 3.6,
                            "width": lane.getWidth(),
                            "length": lane.getLength()
                        }
                        segment_info["lanes"].append(lane_info)
                        speed_limits.append(lane.getSpeed() * 3.6)
                
                segments.append(segment_info)
                total_lanes += len(lanes)
                total_length += edge.getLength()
                lane_counts.append(len(lanes))
                
            except Exception as e:
                logger.warning(f"Failed to analyze edge {edge_id}: {e}")
                continue
        
        # Calculate statistics
        if segments:
            avg_lanes = total_lanes / len(segments)
            avg_length = total_length / len(segments)
            min_lanes = min(lane_counts) if lane_counts else 0
            max_lanes = max(lane_counts) if lane_counts else 0
            
            if speed_limits:
                avg_speed = sum(speed_limits) / len(speed_limits)
                min_speed = min(speed_limits)
                max_speed = max(speed_limits)
            else:
                avg_speed = min_speed = max_speed = 0
            
            statistics = {
                "total_segments": len(segments),
                "total_lanes": total_lanes,
                "total_length_m": total_length,
                "total_length_km": total_length / 1000,
                "avg_lanes_per_segment": round(avg_lanes, 1),
                "avg_length_per_segment": round(avg_length, 1),
                "min_lanes": min_lanes,
                "max_lanes": max_lanes,
                "avg_speed_kmh": round(avg_speed, 1),
                "min_speed_kmh": round(min_speed, 1),
                "max_speed_kmh": round(max_speed, 1)
            }
            
            # Generate summary
            summary = f"Road analysis: {len(segments)} segments, "
            summary += f"{total_lanes} lanes total, "
            summary += f"total length {total_length/1000:.1f}km, "
            summary += f"avg {avg_lanes:.1f} lanes/segment, "
            summary += f"speed limit {min_speed:.0f}-{max_speed:.0f}km/h"

        else:
            statistics = {}
            summary = "No segments to analyze."
        
        return {
            "status": "success",
            "segments": segments,
            "statistics": statistics,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Road analysis failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "segments": [],
            "statistics": {},
            "summary": f"Analysis failed: {str(e)}"
        }


def analyze_road_by_name_and_location(
    net_file: str,
    target_road_name: str,
    reference_location: Optional[str] = None,
    radius_km: Optional[float] = None,
    include_lane_details: bool = True
) -> Dict[str, any]:
    """
    Analyze road segments filtered by name and location.

    Args:
        net_file: Network file path
        target_road_name: Road name (e.g., "테헤란로")
        reference_location: Reference point (e.g., "강남역")
        radius_km: Radius in km (e.g., 0.3)
        include_lane_details: Whether to include per-lane information

    Returns:
        Dict with road analysis results
    """
    try:
        # Get edge IDs
        if not target_road_name:
            return {"status": "error", "message": "target_road_name required"}

        all_road_edges = get_edge_ids_from_road_name(net_file, target_road_name)
        
        if not all_road_edges:
            return {"status": "error", "message": f"Road '{target_road_name}' not found"}
        
        # Filter by radius if specified
        selected_edges = []
        if reference_location and radius_km:
            ref_coords = geocode_location(reference_location)
            if ref_coords:
                ref_lat, ref_lon = ref_coords
                net = sumolib.net.readNet(net_file)
                
                for edge_id in all_road_edges:
                    try:
                        edge = net.getEdge(edge_id)
                        shape = edge.getShape()
                        if shape:
                            mid_point = shape[len(shape) // 2]
                            edge_lon, edge_lat = net.convertXY2LonLat(mid_point[0], mid_point[1])
                            
                            from geopy.distance import distance
                            dist_km = distance((ref_lat, ref_lon), (edge_lat, edge_lon)).km
                            
                            if dist_km <= radius_km:
                                selected_edges.append(edge_id)
                    except:
                        continue
            else:
                return {"status": "error", "message": f"Geocoding failed for '{reference_location}'"}
        else:
            selected_edges = all_road_edges  # No filtering
        
        # Analyze selected edges
        result = analyze_road_segments(net_file, selected_edges, include_lane_details)
        
        # Add filtering info
        if reference_location and radius_km:
            result["filtering"] = {
                "reference_location": reference_location,
                "radius_km": radius_km,
                "total_road_segments": len(all_road_edges),
                "filtered_segments": len(selected_edges)
            }
            result["summary"] = f"Within {radius_km}km of {reference_location}: " + result["summary"]
        
        return result
        
    except Exception as e:
        logger.error(f"Road analysis by location failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "segments": [],
            "statistics": {},
            "summary": f"Analysis failed: {str(e)}"
        }


