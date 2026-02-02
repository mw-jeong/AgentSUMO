"""
Network editing tools for SUMO MCP Server.
"""

import subprocess
import xml.etree.ElementTree as ET
import datetime
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
import sumolib
import logging

from agentsumo.server.settings.settings import sumo_environment
from agentsumo.server.utils.file_utils import ensure_directory
from agentsumo.server.utils.path_utils import get_output_path
from agentsumo.server.utils.sumo_utils import get_edge_ids_from_road_name, geocode_location

logger = logging.getLogger("agentsumo.server.network_editor")


class NetworkEditor:
    """Network editing class for SUMO networks."""
    
    def __init__(self):
        self.environment = sumo_environment
    
    def edit_edge(
        self,
        net_file: str,
        route_file: Optional[str] = None,
        output_dir: str = "output/networks",
        target_road_name: str = None,
        edge_ids: Optional[list] = None,
        reference_location: Optional[str] = None,
        radius_km: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Delete specific edges or road segments from the network file.

        Three modes (in priority order):
        1. edge_ids: Specify exact edge IDs (most precise)
        2. target_road_name + reference_location + radius: Delete road segments near a location (realistic!)
        3. target_road_name only: Delete entire road (use with caution!)

        Args:
            net_file: Network file path
            route_file: Route file path (optional)
            output_dir: Output directory for results
            target_road_name: Road name (e.g., '테헤란로', '9th Avenue')
            edge_ids: Specific edge IDs to delete (e.g., ["12345#5", "12345#6"])
            reference_location: Reference point for partial deletion (e.g., "강남역", "Gangnam Station")
            radius_km: Radius around reference point in km (e.g., 0.3 for 300m)

        Returns:
            Dict[str, Any]: Edit result with status and metadata

        Examples:
            # Realistic: Delete 300m of Teheran-ro near Gangnam Station
            edit_edge(target_road_name="테헤란로", reference_location="강남역", radius_km=0.3, ...)

            # Precise: Delete specific segments
            edit_edge(edge_ids=["12345#5", "12345#6", "12345#7"], ...)

            # Extreme: Delete entire road (not recommended!)
            edit_edge(target_road_name="테헤란로", ...)
        """
        try:
            # Mode 1: Direct edge IDs (highest priority)
            if edge_ids:
                target_edge_ids = edge_ids

            # Mode 2: Road name + reference location + radius (realistic scenario!)
            elif target_road_name and reference_location and radius_km:
                # Get all edges of the road
                all_road_edges = get_edge_ids_from_road_name(net_file, target_road_name)

                # Filter by distance from reference location
                target_edge_ids = self._filter_edges_by_location(
                    net_file, all_road_edges, reference_location, radius_km
                )

                if not target_edge_ids:
                    return {
                        "status": "error",
                        "message": f"No edges found near {reference_location} within {radius_km}km"
                    }

            # Mode 3: Road name only (entire road)
            elif target_road_name:
                target_edge_ids = get_edge_ids_from_road_name(net_file, target_road_name)

            else:
                return {"status": "error", "message": "Either edge_ids, or (target_road_name + reference_location + radius), or target_road_name required"}
            
            # Use netconvert to remove edges
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            net_file_copy = output_path / f"{Path(net_file).stem}_edgeedit_{ts}.net.xml"
            ensure_directory(output_path)
            
            edge_list_string = ",".join(target_edge_ids)
            netconvert_path = self.environment.get_binary_path("netconvert")
            command = [
                netconvert_path,
                "--sumo-net-file", net_file,
                "--remove-edges.explicit", edge_list_string,
                "-o", str(net_file_copy)
            ]
            
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                return {"status": "error", "message": f"netconvert failed: {result.stderr.decode('utf-8')}"}
            
            msg = f"{len(target_edge_ids)} edges containing '{target_road_name}' removed."
            return {
                "status": "success", 
                "net_file": str(net_file_copy), 
                "route_file": None,  # New route file needed
                "message": msg,
                "requires_reroute": True  # Route recalculation needed
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _filter_edges_by_location(
        self,
        net_file: str,
        edge_ids: List[str],
        reference_location: str,
        radius_km: float
    ) -> List[str]:
        """
        Filter edges by distance from reference location.
        
        Args:
            net_file: SUMO network file
            edge_ids: List of edge IDs to filter
            reference_location: Reference point (place name or "lat,lon")
            radius_km: Radius in kilometers
            
        Returns:
            List of edge IDs within radius
        """
        try:
            # Load network first
            net = sumolib.net.readNet(net_file)
            
            # Check if reference_location is an intersection (contains "and" or "&" or comma-separated road names)
            # Format: "road1 and road2" or "road1, road2" or "road1 & road2"
            intersection_roads = None
            if " and " in reference_location.lower() or " & " in reference_location.lower() or "," in reference_location:
                # Try to parse as intersection
                import re
                # Split by "and", "&", or comma
                parts = re.split(r'\s+(and|&)\s+|,\s*', reference_location, flags=re.IGNORECASE)
                parts = [p.strip() for p in parts if p.strip() and p.lower() not in ['and', '&']]
                if len(parts) >= 2:
                    intersection_roads = parts[:2]
                    logger.info(f"🔍 Intersection detected: {intersection_roads[0]} × {intersection_roads[1]}")
            
            # If intersection detected, find intersection junction
            intersection_junction = None
            if intersection_roads:
                intersection_junction = self._find_intersection_junction(
                    net, intersection_roads[0], intersection_roads[1]
                )
                if intersection_junction:
                    # Use junction position as reference point
                    junction_pos = intersection_junction.getCoord()
                    ref_lon, ref_lat = net.convertXY2LonLat(junction_pos[0], junction_pos[1])
                    logger.info(f"📍 Intersection junction found: ({ref_lat:.6f}, {ref_lon:.6f})")
                else:
                    logger.warning(f"⚠️ Intersection junction not found, falling back to geocoding")
                    intersection_roads = None  # Fall back to geocoding
            
            # If not intersection or intersection not found, use geocoding
            if not intersection_roads or not intersection_junction:
                ref_coords = geocode_location(reference_location)
                if not ref_coords:
                    logger.error(f"Failed to geocode: {reference_location}")
                    return edge_ids  # Fallback: return all
                ref_lat, ref_lon = ref_coords
            
            # Filter edges by distance from reference point
            filtered = []
            for edge_id in edge_ids:
                try:
                    edge = net.getEdge(edge_id)
                    
                    # Get edge center position
                    shape = edge.getShape()
                    if shape:
                        # Middle point of edge
                        mid_point = shape[len(shape) // 2]
                        edge_lon, edge_lat = net.convertXY2LonLat(mid_point[0], mid_point[1])
                        
                        # Calculate distance
                        from geopy.distance import distance
                        dist_km = distance((ref_lat, ref_lon), (edge_lat, edge_lon)).km
                        
                        if dist_km <= radius_km:
                            filtered.append(edge_id)
                            logger.debug(f"  Edge {edge_id}: {dist_km:.3f}km (included)")
                        else:
                            logger.debug(f"  Edge {edge_id}: {dist_km:.3f}km (excluded)")
                except Exception as e:
                    logger.warning(f"  Edge {edge_id}: 처리 실패 ({e})")
                    continue
            
            logger.info(f"✅ {len(filtered)}/{len(edge_ids)} edges within {radius_km}km of {reference_location}")
            return filtered
            
        except Exception as e:
            logger.error(f"Edge filtering 실패: {e}")
            return edge_ids  # Fallback: return all
    
    def _find_intersection_junction(
        self,
        net: sumolib.net.Net,
        road1_name: str,
        road2_name: str
    ):
        """
        Find the junction where two roads intersect.

        Args:
            net: SUMO network object
            road1_name: First road name
            road2_name: Second road name

        Returns:
            Junction object or None if not found
        """
        try:
            # Get edges for both roads using edge.getName()
            road1_edge_objs = [e for e in net.getEdges() if e.getName() == road1_name]
            road2_edge_objs = [e for e in net.getEdges() if e.getName() == road2_name]

            if not road1_edge_objs or not road2_edge_objs:
                logger.warning(f"Could not find edges for {road1_name} or {road2_name}")
                return None

            # Check each junction
            for junction in net.getNodes():
                # Get edges connected to this junction
                incoming = junction.getIncoming()
                outgoing = junction.getOutgoing()
                all_connected = incoming + outgoing

                # Check if junction connects edges from both roads
                has_road1 = any(e in road1_edge_objs for e in all_connected)
                has_road2 = any(e in road2_edge_objs for e in all_connected)

                if has_road1 and has_road2:
                    logger.info(f"✅ Found intersection junction: {junction.getID()} at ({junction.getCoord()[0]:.2f}, {junction.getCoord()[1]:.2f})")
                    return junction

            logger.warning(f"⚠️ Intersection junction not found between {road1_name} and {road2_name}")
            return None

        except Exception as e:
            logger.error(f"Error finding intersection junction: {e}")
            return None
    
    def reduce_lanes(
        self,
        net_file: str,
        route_file: Optional[str] = None,
        output_dir: str = "output/networks",
        target_road_name: str = None,
        edge_ids: Optional[list] = None,
        reference_location: Optional[str] = None,
        radius_km: Optional[float] = None,
        remain_lanes: int = None,
        reduce_by: int = None
    ) -> Dict[str, Any]:
        """
        Reduce lanes on specific road segments (supports partial application).

        Two reduction modes:
        1. reduce_by: Reduce N lanes from each segment (RELATIVE - RECOMMENDED!)
        2. remain_lanes: Set all segments to N lanes (ABSOLUTE - for special cases)

        Three targeting modes:
        1. edge_ids: Reduce lanes on exact edges
        2. target_road_name + reference_location + radius: Reduce lanes near a location (REALISTIC!)
        3. target_road_name only: Reduce lanes on entire road (use with caution)

        Args:
            net_file: Network file path
            route_file: Route file path (optional)
            output_dir: Output directory for results
            target_road_name: Road name (e.g., '테헤란로')
            edge_ids: Specific edge IDs (optional)
            reference_location: Reference point (optional, e.g., "강남역")
            radius_km: Radius in km (optional, e.g., 0.3)
            reduce_by: Number of lanes to reduce from each segment (RECOMMENDED!)
            remain_lanes: Number of lanes to remain (ABSOLUTE - use with caution)

        Returns:
            Dict[str, Any]: Edit result with status and metadata

        Examples:
            # Relative reduction (recommended for most policies)
            reduce_by=1  # Each segment: 5→4, 3→2, 2→1, 1→1

            # Absolute reduction (for special cases)
            remain_lanes=1  # All segments: 5→1, 3→1, 2→1, 1→1
        """
        try:
            # Determine target edges
            if edge_ids:
                target_edge_ids = edge_ids
            elif target_road_name and reference_location and radius_km:
                all_road_edges = get_edge_ids_from_road_name(net_file, target_road_name)
                target_edge_ids = self._filter_edges_by_location(
                    net_file, all_road_edges, reference_location, radius_km
                )

                if not target_edge_ids:
                    return {"status": "error", "message": f"No edges near {reference_location}"}
            elif target_road_name:
                target_edge_ids = get_edge_ids_from_road_name(net_file, target_road_name)
            else:
                return {"status": "error", "message": "Either edge_ids, or (target_road_name + reference + radius), or target_road_name required"}
            
            if not target_edge_ids:
                return {"status": "error", "message": f"'{target_road_name}' 도로를 찾을 수 없습니다."}
            
            # Validate reduction parameters
            if reduce_by is None and remain_lanes is None:
                return {"status": "error", "message": "Either reduce_by or remain_lanes must be specified"}
            
            if reduce_by is not None and remain_lanes is not None:
                return {"status": "error", "message": "Cannot specify both reduce_by and remain_lanes. Choose one."}
            
            # Setup output paths
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Choose appropriate filename based on reduction mode
            if reduce_by is not None:
                net_file_final = output_path / f"{Path(net_file).stem}_reducelanes_{reduce_by}_{ts}.net.xml"
                reduction_mode = f"reduce_by_{reduce_by}"
            else:
                net_file_final = output_path / f"{Path(net_file).stem}_reducelanes_{remain_lanes}_{ts}.net.xml"
                reduction_mode = f"remain_lanes_{remain_lanes}"
            
            ensure_directory(output_path)
            
            # ✅ SUMO Official Workflow: Plain XML method
            logger.info(f"🔄 Using SUMO Plain XML workflow for lane reduction...")
            
            import tempfile
            temp_dir = Path(tempfile.mkdtemp())
            temp_prefix = temp_dir / "temp"
            
            try:
                netconvert_path = self.environment.get_binary_path("netconvert")
                
                # Step 1: Convert .net.xml to Plain XML
                logger.info(f"  Step 1: Converting to Plain XML...")
                subprocess.run([
                    netconvert_path,
                    '--sumo-net-file', net_file,
                    '--plain-output-prefix', str(temp_prefix)
                ], check=True, capture_output=True, text=True)
                
                # Plain XML files
                edg_file = Path(f"{temp_prefix}.edg.xml")
                nod_file = Path(f"{temp_prefix}.nod.xml")
                con_file = Path(f"{temp_prefix}.con.xml")
                
                # Step 2: Modify edge file (numLanes only)
                logger.info(f"  Step 2: Modifying lanes in Plain XML...")
                tree = ET.parse(edg_file)
                root = tree.getroot()
                
                modified_edges = 0
                total_lanes_before = 0
                total_lanes_after = 0
                
                for edge in root.findall("edge"):
                    edge_id = edge.get("id")
                    if edge_id in target_edge_ids:
                        current_lanes = int(edge.get("numLanes", 1))
                        total_lanes_before += current_lanes
                        
                        # Calculate new lane count
                        if reduce_by is not None:
                            new_lanes = max(1, current_lanes - reduce_by)
                        else:
                            new_lanes = remain_lanes
                        
                        # Update numLanes attribute
                        if new_lanes != current_lanes:
                            edge.set("numLanes", str(new_lanes))
                            
                            # ✅ CRITICAL: Remove <lane> child elements if present
                            # Plain XML may include lane-specific attributes
                            lanes_to_remove = edge.findall("lane")
                            if lanes_to_remove:
                                # Remove lanes beyond new_lanes
                                for i in range(new_lanes, len(lanes_to_remove)):
                                    edge.remove(lanes_to_remove[i])
                                logger.debug(f"  Removed {len(lanes_to_remove) - new_lanes} <lane> tags from {edge_id}")
                            
                            modified_edges += 1
                        
                        total_lanes_after += new_lanes
                
                tree.write(edg_file, encoding="utf-8", xml_declaration=True)
                
                # Step 3: Rebuild .net.xml from Plain XML
                # NOTE: Do NOT use --connection-files! Let netconvert auto-generate connections
                # based on new numLanes. Old connections reference invalid lane indices.
                logger.info(f"  Step 3: Rebuilding .net.xml with auto-generated junctions...")
                subprocess.run([
                    netconvert_path,
                    '--node-files', str(nod_file),
                    '--edge-files', str(edg_file),
                    # NO --connection-files! (auto-generate based on new numLanes)
                    '--output-file', str(net_file_final)
                ], check=True, capture_output=True, text=True)
                
                logger.info(f"✅ Plain XML workflow completed")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Plain XML workflow failed: {e.stderr}")
                # Cleanup temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                return {
                    "status": "error",
                    "message": f"Lane reduction failed: {e.stderr}"
                }
            finally:
                # Cleanup temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            # Generate appropriate message
            if reduce_by is not None:
                msg = f"{modified_edges} edges modified: {target_road_name} → reduced {reduce_by} lanes each"
                msg += f" (Total: {total_lanes_before} → {total_lanes_after} lanes)"
            else:
                msg = f"{modified_edges} edges modified: {target_road_name} → {remain_lanes} lanes each"
                msg += f" (Total: {total_lanes_before} → {total_lanes_after} lanes)"
            
            msg += " | Plain XML workflow ✅ | Junctions rebuilt ✅"
            
            return {
                "status": "success",
                "net_file": str(net_file_final),
                "route_file": route_file,  # Keep existing route file
                "message": msg,
                "reduction_mode": reduction_mode,
                "total_lanes_before": total_lanes_before,
                "total_lanes_after": total_lanes_after,
                "requires_reroute": False  # No route recalculation needed
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def edit_speed_limit(
        self,
        net_file: str,
        route_file: Optional[str] = None,
        output_dir: str = "output/networks",
        target_road_name: str = None,
        edge_ids: Optional[list] = None,
        reference_location: Optional[str] = None,
        radius_km: Optional[float] = None,
        new_speed_kmph: float = None
    ) -> Dict[str, Any]:
        """
        Modify speed limits on specific road segments (supports partial application).

        Three modes (same as other edit tools):
        1. edge_ids: Change speed on exact edges
        2. target_road_name + reference_location + radius: Change speed near a location (REALISTIC!)
        3. target_road_name only: Change speed on entire road

        Args:
            net_file: Network file path
            route_file: Route file path (optional)
            output_dir: Output directory for results
            target_road_name: Road name (e.g., '테헤란로')
            edge_ids: Specific edge IDs (optional)
            reference_location: Reference point (optional, e.g., "강남역")
            radius_km: Radius in km (optional, e.g., 0.5)
            new_speed_kmph: New speed limit in km/h (e.g., 40.0)

        Returns:
            Dict[str, Any]: Edit result with status and metadata
        """
        try:
            if new_speed_kmph is None:
                return {"status": "error", "message": "new_speed_kmph required"}

            # Convert km/h to m/s
            new_speed_ms = new_speed_kmph / 3.6

            # Determine target edges
            if edge_ids:
                target_edge_ids = edge_ids
            elif target_road_name and reference_location and radius_km:
                all_road_edges = get_edge_ids_from_road_name(net_file, target_road_name)
                target_edge_ids = self._filter_edges_by_location(
                    net_file, all_road_edges, reference_location, radius_km
                )

                if not target_edge_ids:
                    return {"status": "error", "message": f"No edges near {reference_location}"}
            elif target_road_name:
                target_edge_ids = get_edge_ids_from_road_name(net_file, target_road_name)
            else:
                return {"status": "error", "message": "target_road_name or edge_ids required"}
            
            if not target_edge_ids:
                return {"status": "error", "message": f"'{target_road_name}' 도로를 찾을 수 없습니다."}
            
            # Copy and modify file
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            net_file_copy = output_path / f"{Path(net_file).stem}_speedlimit_{ts}.net.xml"
            ensure_directory(output_path)
            
            # Check if source and destination are the same file
            if Path(net_file).resolve() == net_file_copy.resolve():
                net_file_copy = Path(net_file)
            else:
                shutil.copy2(net_file, net_file_copy)
            
            # Parse and modify XML
            tree = ET.parse(net_file_copy)
            root = tree.getroot()
            
            modified_edges = 0
            for edge in root.findall("edge"):
                edge_id = edge.get("id")
                if edge_id in target_edge_ids:
                    lanes = edge.findall("lane")
                    for lane in lanes:
                        lane.set("speed", str(new_speed_ms))
                    modified_edges += 1
            
            tree.write(net_file_copy, encoding="utf-8", xml_declaration=True)
            
            msg = f"{modified_edges} edges modified: {target_road_name} → {new_speed_kmph} km/h"
            return {
                "status": "success",
                "net_file": str(net_file_copy),
                "route_file": route_file,  # Keep existing route file
                "message": msg,
                "requires_reroute": False  # No route recalculation needed
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
