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

from agentsumo.server.settings.settings import sumo_environment
from agentsumo.server.utils.file_utils import ensure_directory
from agentsumo.server.utils.path_utils import get_output_path
from agentsumo.server.utils.sumo_utils import (
    geocode_location,
    get_edge_ids_from_road_name,
    find_nearest_edge,
    check_coordinates_in_network
)

logger = logging.getLogger("agentsumo.server.vehicle_manager")


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
            logger.info(f"차량 생성 시작: {source_location} → {destination_location} (geocoding: {use_geocoding})")
            
            # Get source and destination edges based on mode
            if use_geocoding:
                # NEW: Location-based approach (geocoding + nearest edge)
                
                # Step 1: Geocode locations
                source_coords = geocode_location(source_location)
                if not source_coords:
                    return {"status": "error", "message": f"출발지 위치를 찾을 수 없습니다: {source_location}"}
                
                dest_coords = geocode_location(destination_location)
                if not dest_coords:
                    return {"status": "error", "message": f"목적지 위치를 찾을 수 없습니다: {destination_location}"}
                
                # Step 2: Validate coordinates are within network bounds
                source_valid, source_info = check_coordinates_in_network(
                    net_file, source_coords[0], source_coords[1], buffer_km=1.0
                )
                if not source_valid:
                    bbox = source_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"출발지 '{source_location}'가 네트워크 범위 밖입니다.\n"
                            f"- 입력 좌표: ({source_coords[0]:.4f}, {source_coords[1]:.4f})\n"
                            f"- 네트워크 범위: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- 네트워크 중심에서 거리: {source_info.get('distance_km', 'N/A')}km\n"
                            f"💡 해결: 해당 위치를 포함하는 네트워크를 먼저 생성하세요."
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
                            f"목적지 '{destination_location}'가 네트워크 범위 밖입니다.\n"
                            f"- 입력 좌표: ({dest_coords[0]:.4f}, {dest_coords[1]:.4f})\n"
                            f"- 네트워크 범위: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- 네트워크 중심에서 거리: {dest_info.get('distance_km', 'N/A')}km\n"
                            f"💡 해결: 해당 위치를 포함하는 네트워크를 먼저 생성하세요."
                        )
                    }
                
                # Step 3: Find nearest edges (within validated network)
                source_result = find_nearest_edge(net_file, source_coords[0], source_coords[1], search_radius)
                if not source_result:
                    return {
                        "status": "error",
                        "message": f"출발지 좌표 {source_coords} 주변 {search_radius}km 내에 edge를 찾을 수 없습니다."
                    }
                source_edge, source_dist = source_result
                
                dest_result = find_nearest_edge(net_file, dest_coords[0], dest_coords[1], search_radius)
                if not dest_result:
                    return {
                        "status": "error",
                        "message": f"목적지 좌표 {dest_coords} 주변 {search_radius}km 내에 edge를 찾을 수 없습니다."
                    }
                destination_edge, dest_dist = dest_result
                
                logger.info(f"✅ Geocoding 성공: 출발지={source_edge} ({source_dist:.1f}m), 목적지={destination_edge} ({dest_dist:.1f}m)")
                
            else:
                # Road name-based approach (uses edge.getName())
                source_edge_ids = get_edge_ids_from_road_name(net_file, source_location)
                destination_edge_ids = get_edge_ids_from_road_name(net_file, destination_location)

                if not source_edge_ids or not destination_edge_ids:
                    return {"status": "error", "message": "유효한 출발지 또는 목적지 도로명을 찾을 수 없습니다."}

                # Select representative edges (middle values)
                source_edge = source_edge_ids[len(source_edge_ids)//2]
                destination_edge = destination_edge_ids[len(destination_edge_ids)//2]

                logger.info(f"✅ 도로명 매칭 성공: 출발지={source_edge}, 목적지={destination_edge}")
            
            # Calculate shortest path
            net = sumolib.net.readNet(net_file)
            try:
                source = net.getEdge(source_edge)
                dest = net.getEdge(destination_edge)
            except Exception as e:
                return {"status": "error", "message": f"네트워크에서 edge를 찾을 수 없습니다: {e}"}
            
            path_edges = net.getShortestPath(source, dest, vClass="passenger")[0]
            if not path_edges:
                return {"status": "error", "message": "최단 경로를 찾을 수 없습니다."}
            
            route_string = " ".join([e.getID() for e in path_edges])
            
            # Copy and modify file
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_vehgen_{ts}.rou.xml"
            ensure_directory(output_path)
            
            # Check if source and destination are the same file
            if Path(route_file).resolve() == route_file_copy.resolve():
                # print(f"[AgentSUMO] Source and destination are the same: {route_file}")
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
            
            mode_msg = "장소 기반 (geocoding)" if use_geocoding else "도로명 기반"
            msg = (f"{vehicle_count}대의 차량이 추가되었습니다. "
                   f"출발지: {source_location}, 목적지: {destination_location} ({mode_msg})")
            logger.info(f"✅ 차량 생성 완료: {msg}")
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}
            
        except Exception as e:
            logger.error(f"차량 생성 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def generate_flow(
        self,
        route_file: str,
        net_file: str,
        source: str,
        dest: str,
        begin: float,
        end: float,
        vehs_per_hour: int,
        flow_id: str = None,
        output_dir: str = "output/trips",
        use_geocoding: bool = True,
        search_radius: float = 0.3
    ) -> Dict[str, Any]:
        """
        Generate a flow from source to destination with specified parameters.
        
        Args:
            route_file: Route file path
            net_file: Network file path
            source: Source location (place name)
            dest: Destination location (place name)
            begin: Start time in seconds
            end: End time in seconds
            vehs_per_hour: Vehicles per hour
            flow_id: Flow ID (auto-generated if None)
            output_dir: Output directory for results
            use_geocoding: If True, use geocoding + nearest edge search
            search_radius: Search radius in km for nearest edge
            
        Returns:
            Dict[str, Any]: Generation result with status and metadata
        """
        try:
            logger.info(f"Flow 생성 시작: {source} → {dest} ({begin}-{end}s, {vehs_per_hour} vehs/hour)")
            
            # Generate flow ID if not provided
            if not flow_id:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                flow_id = f"flow_{ts}"
            
            # Get source and destination edges (reuse existing logic)
            if use_geocoding:
                # Geocode locations
                source_coords = geocode_location(source)
                if not source_coords:
                    return {"status": "error", "message": f"출발지 위치를 찾을 수 없습니다: {source}"}
                
                dest_coords = geocode_location(dest)
                if not dest_coords:
                    return {"status": "error", "message": f"목적지 위치를 찾을 수 없습니다: {dest}"}
                
                # Validate coordinates are within network bounds
                source_valid, source_info = check_coordinates_in_network(
                    net_file, source_coords[0], source_coords[1], buffer_km=1.0
                )
                if not source_valid:
                    bbox = source_info.get('bbox', [])
                    return {
                        "status": "error",
                        "message": (
                            f"출발지 '{source}'가 네트워크 범위 밖입니다.\n"
                            f"- 입력 좌표: ({source_coords[0]:.4f}, {source_coords[1]:.4f})\n"
                            f"- 네트워크 범위: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- 네트워크 중심에서 거리: {source_info.get('distance_km', 'N/A')}km\n"
                            f"💡 해결: 해당 위치를 포함하는 네트워크를 먼저 생성하세요."
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
                            f"목적지 '{dest}'가 네트워크 범위 밖입니다.\n"
                            f"- 입력 좌표: ({dest_coords[0]:.4f}, {dest_coords[1]:.4f})\n"
                            f"- 네트워크 범위: ({bbox[1]:.4f}~{bbox[3]:.4f}, {bbox[0]:.4f}~{bbox[2]:.4f})\n"
                            f"- 네트워크 중심에서 거리: {dest_info.get('distance_km', 'N/A')}km\n"
                            f"💡 해결: 해당 위치를 포함하는 네트워크를 먼저 생성하세요."
                        )
                    }
                
                # Find nearest edges
                source_result = find_nearest_edge(net_file, source_coords[0], source_coords[1], search_radius)
                if not source_result:
                    return {
                        "status": "error",
                        "message": f"출발지 좌표 {source_coords} 주변 {search_radius}km 내에 edge를 찾을 수 없습니다."
                    }
                source_edge, source_dist = source_result
                
                dest_result = find_nearest_edge(net_file, dest_coords[0], dest_coords[1], search_radius)
                if not dest_result:
                    return {
                        "status": "error",
                        "message": f"목적지 좌표 {dest_coords} 주변 {search_radius}km 내에 edge를 찾을 수 없습니다."
                    }
                destination_edge, dest_dist = dest_result
                
                logger.info(f"✅ Geocoding 성공: 출발지={source_edge} ({source_dist:.1f}m), 목적지={destination_edge} ({dest_dist:.1f}m)")
                
            else:
                return {"status": "error", "message": "Flow 생성은 geocoding 모드만 지원됩니다. use_geocoding=True를 사용하세요."}
            
            # Calculate shortest path
            net = sumolib.net.readNet(net_file)
            try:
                source_edge_obj = net.getEdge(source_edge)
                dest_edge_obj = net.getEdge(destination_edge)
            except Exception as e:
                return {"status": "error", "message": f"네트워크에서 edge를 찾을 수 없습니다: {e}"}
            
            path_edges = net.getShortestPath(source_edge_obj, dest_edge_obj, vClass="passenger")[0]
            if not path_edges:
                return {"status": "error", "message": "최단 경로를 찾을 수 없습니다."}
            
            # Copy and modify file
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_flow_{ts}.rou.xml"
            ensure_directory(output_path)
            
            # Check if source and destination are the same file
            if Path(route_file).resolve() == route_file_copy.resolve():
                route_file_copy = Path(route_file)
            else:
                shutil.copy2(route_file, route_file_copy)
            
            tree = ET.parse(route_file_copy)
            root = tree.getroot()
            
            # Generate flow with safety parameters
            flow = ET.SubElement(root, "flow", {
                "id": flow_id,
                "from": source_edge,
                "to": destination_edge,
                "begin": str(begin),
                "end": str(end),
                "vehsPerHour": str(vehs_per_hour),
                "type": "passenger",
                "departLane": "free",
                "departPos": "random_free",
                "departSpeed": "random"
            })
            
            tree.write(route_file_copy, encoding="utf-8", xml_declaration=True)
            
            msg = (f"Flow '{flow_id}' 생성 완료: {source} → {dest} "
                   f"({begin}-{end}s, {vehs_per_hour} vehs/hour)")
            logger.info(f"✅ Flow 생성 완료: {msg}")
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}
            
        except Exception as e:
            logger.error(f"Flow 생성 실패: {e}")
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
            # print(f"[AgentSUMO] vehicle_type_edit_tool 실행됨: route_file={route_file}, electric_ratio={electric_ratio}")
            
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            route_file_copy = output_path / f"{Path(route_file).stem}_vehtype_{ts}.rou.xml"
            ensure_directory(output_path)
            
            # Check if source and destination are the same file
            if Path(route_file).resolve() == route_file_copy.resolve():
                # print(f"[AgentSUMO] Source and destination are the same: {route_file}")
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
            # print(f"[AgentSUMO] vehicle_type_edit_tool 완료: {msg}")
            return {"status": "success", "route_file": str(route_file_copy), "message": msg}
            
        except Exception as e:
            # print(f"[AgentSUMO] vehicle_type_edit_tool 오류: {e}")
            return {"status": "error", "message": str(e)}
