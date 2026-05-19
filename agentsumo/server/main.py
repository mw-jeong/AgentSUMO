"""
Main MCP server for SUMO.

This is the entry point for the modular SUMO MCP Server.
All tools are registered here and imported from their respective modules.
"""

from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List

# Import core functionality (AgentSUMO branding)
from agentsumo.server.baseline.network_generator import NetworkGenerator
from agentsumo.server.baseline.trip_generator import TripGenerator
from agentsumo.server.baseline.simulation_runner import SimulationRunner

# Import customization tools
from agentsumo.server.customization.network_editor import NetworkEditor
from agentsumo.server.customization.vehicle_manager import VehicleManager
from agentsumo.server.customization.traffic_lights import TrafficLightManager

# Import analysis functionality
from agentsumo.server.analysis.result_parser import ResultParser
from agentsumo.server.analysis.report_generator import ReportGenerator
from agentsumo.server.analysis.qa_system import QASystem

# Import visualization functionality
from agentsumo.server.visualization.network_plotter import NetworkPlotter
from agentsumo.server.visualization.edge_plotter import EdgePlotter
from agentsumo.server.visualization.data_plotter import DataPlotter

# Initialize MCP server
mcp = FastMCP("SUMO Baseline")

# Initialize all components
network_generator = NetworkGenerator()
trip_generator = TripGenerator()
simulation_runner = SimulationRunner()

network_editor = NetworkEditor()
vehicle_manager = VehicleManager()
traffic_light_manager = TrafficLightManager()

result_parser = ResultParser()
# Note: ReportGenerator는 tool 실행 시점에 lazy initialization
# (API key 필수이므로 import 시점 초기화 방지)

network_plotter = NetworkPlotter()
edge_plotter = EdgePlotter()
data_plotter = DataPlotter()


# =============== CORE FUNCTIONALITY ===============

@mcp.tool()
def net_generate(
    city: str = None,
    city_en: str = None,
    radius: float = None,
    bbox: list = None,
    trip_type: str = "",
    od_type: str = None,
    od_data_file: str = None,
    zone_shp_file: str = None,
    output_dir: str = "output/networks"
) -> Dict[str, Any]:
    """
    Generate a SUMO network for traffic simulation.

    ⚠️ CRITICAL: ALWAYS provide city/city_en for file naming!
    - city: Location name (e.g., "Gangnam Station", "강남역")
    - city_en: English name for file (e.g., "gangnam_station")
    - Without city info, file naming will fail!

    For direct bbox (from map selection):
    - bbox: [west, south, east, north] (e.g., [127.0153, 37.4905, 127.0400, 37.5058])
    - city_en: for file naming (e.g., "selected_area")
    - trip_type: "RandomOD"
    - bbox takes PRIORITY over city+radius!

    For RandomOD simulation (city-based):
    - city/city_en + radius (in km, not meters!)
    - trip_type: "RandomOD"

    For RealOD-coordinate:
    - trip_type: "RealOD", od_type: "coordinate"
    - od_data_file: CSV with O_lon, D_lon, O_lat, D_lat

    For RealOD-zone:
    - trip_type: "RealOD", od_type: "zone"
    - zone_shp_file: shapefile path
    """
    return network_generator.generate(
        city=city, city_en=city_en, radius=radius, bbox=bbox, trip_type=trip_type,
        od_type=od_type, od_data_file=od_data_file, zone_shp_file=zone_shp_file,
        output_dir=output_dir
    )


@mcp.tool()
def trip_generate(
    trip_type: str,
    net_file: str,
    od_type: str = None,
    od_data_file: str = None,
    zone_shp_file: str = None,
    traffic_condition: str = None,
    output_dir: str = "output/trips"
) -> Dict[str, Any]:
    """
    Generate trips for SUMO simulation.
    
    IMPORTANT: For RealOD-zone simulation, use:
    - trip_type: "RealOD"
    - od_type: "zone"
    - zone_shp_file: path to shapefile
    
    For RealOD-coordinate simulation, use:
    - trip_type: "RealOD" 
    - od_type: "coordinate"
    - od_data_file: path to CSV with O_lon, D_lon, O_lat, D_lat columns
    
    For RandomOD simulation, use:
    - trip_type: "RandomOD"
    - traffic_condition: REQUIRED - Choose from "light" (low traffic), "medium" (moderate traffic), or "heavy" (high traffic)
    """
    # For RandomOD trips, traffic_condition is required
    if trip_type == "RandomOD" and traffic_condition is None:
        return {
            "status": "error",
            "message": "traffic_condition is required for RandomOD trip generation. Please specify: 'light', 'medium', or 'heavy'",
            "available_options": ["light", "medium", "heavy"],
            "description": {
                "light": "Low traffic density (rural areas, off-peak hours)",
                "medium": "Moderate traffic density (typical urban traffic)", 
                "heavy": "High traffic density (rush hour, dense urban areas)"
            }
        }
    
    return trip_generator.generate(
        trip_type=trip_type, net_file=net_file, od_type=od_type,
        od_data_file=od_data_file, zone_shp_file=zone_shp_file,
        traffic_condition=traffic_condition, output_dir=output_dir
    )


@mcp.tool()
def sumo_runner(
    net_file: str,
    trip_file: str = None,
    route_file: str = None,
    duration: int = 3600,
    output_dir: str = "output/simulations",
    additional_files: list = None,
    policy_type: str = None
):
    """
    Run SUMO simulation with enhanced error handling and monitoring.
    
    Args:
        net_file: Network file path (tag will be extracted from filename)
        trip_file: Trip file path (optional)
        route_file: Route file path (optional)
        duration: Simulation duration in seconds
        output_dir: Output directory for simulation results
        additional_files: List of additional XML files to include
        policy_type: Policy type for batch simulation file naming
    """
    return simulation_runner.run(
        net_file=net_file, trip_file=trip_file, route_file=route_file,
        duration=duration, output_dir=output_dir, additional_files=additional_files,
        policy_type=policy_type
    )


# =============== NETWORK EDITING TOOLS ===============

@mcp.tool()
def edge_edit_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None
):
    """
    Delete specific road segments from the network file.

    ⚠️🚨 CRITICAL: After using this tool, you MUST regenerate trip files!
    Route files contain explicit edge lists - if those edges are deleted, the route file becomes INVALID!
    Workflow: edge_edit → trip_generate → sumo_runner (REQUIRED!)

    🌟 REALISTIC USAGE: Specify reference_location + radius_km for partial road closure!

    Three modes (priority order):
    1. edge_ids: Delete exact edges (most precise, but requires knowing edge IDs)
    2. target_road_name + reference_location + radius_km: Delete road segments near a location (REALISTIC!)
    3. target_road_name only: Delete entire road (extreme scenario, use with caution!)

    Examples:
        # REALISTIC: Block 300m of Teheran-ro near Gangnam Station (construction scenario)
        edge_edit_tool(
            net_file="gangnam_station.net.xml",
            target_road_name="테헤란로",
            reference_location="강남역",
            radius_km=0.3
        )
        # Then: trip_generate → sumo_runner (MUST regenerate trip!)

        # EXTREME: Block entire Teheran-ro (unrealistic!)
        edge_edit_tool(
            net_file="gangnam_station.net.xml",
            target_road_name="테헤란로"
        )
        # Then: trip_generate → sumo_runner (MUST regenerate trip!)

    Args:
        net_file: Network file path
        route_file: Route file path (optional, but will be invalidated after edge deletion)
        output_dir: Output directory for results
        target_road_name: Road name to delete from network (e.g., '테헤란로')
        edge_ids: Specific edge IDs to delete (list, optional)
        reference_location: Reference point for partial deletion (str, optional, e.g., "강남역")
        radius_km: Radius in km around reference (float, optional, e.g., 0.3)

    Returns:
        Dict with status, net_file, and requires_reroute=True (indicating trip regeneration needed)
    """
    return network_editor.edit_edge(
        net_file=net_file, route_file=route_file, output_dir=output_dir,
        target_road_name=target_road_name, edge_ids=edge_ids,
        reference_location=reference_location, radius_km=radius_km
    )


@mcp.tool()
def reduce_lanes_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None,
    reduce_by: int = None,
    remain_lanes: int = None
):
    """
    Reduce lanes on road segments with two modes.

    ✅ Trip file can be reused - edges still exist, only lane count changed.
    Workflow: reduce_lanes → sumo_runner (reuse existing trip file)

    **MODE 1: Relative Reduction (RECOMMENDED for most policies)**
    - reduce_by: Reduce N lanes from each segment
    - Example: reduce_by=1 → 5→4, 3→2, 2→1, 1→1 (balanced reduction)

    **MODE 2: Absolute Reduction (for special cases)**
    - remain_lanes: Set all segments to N lanes
    - Example: remain_lanes=1 → 5→1, 3→1, 2→1, 1→1 (extreme reduction)

    REALISTIC USAGE: Use reference_location + radius_km for localized lane reduction!

    Examples:
        # BALANCED POLICY: Reduce 1 lane from each segment
        reduce_lanes_tool(
            net_file="gangnam_station.net.xml",
            target_road_name="테헤란로",
            reference_location="강남역",
            radius_km=0.5,
            reduce_by=1  # Each segment: 5→4, 3→2, 2→1, 1→1
        )
        # Then: sumo_runner (reuse trip file - no trip_generate needed!)

        # EXTREME POLICY: Set all segments to 1 lane
        reduce_lanes_tool(
            net_file="gangnam_station.net.xml",
            target_road_name="테헤란로",
            reference_location="강남역",
            radius_km=0.5,
            remain_lanes=1  # All segments: 5→1, 3→1, 2→1, 1→1
        )
        # Then: sumo_runner (reuse trip file - no trip_generate needed!)

    Args:
        net_file: Network file path
        route_file: Route file path (optional, can be reused after this tool)
        output_dir: Output directory for results
        target_road_name: Road name to reduce lanes (e.g., '테헤란로')
        edge_ids: Specific edge IDs (optional)
        reference_location: Reference point (optional, e.g., "강남역")
        radius_km: Radius in km (optional, e.g., 0.5)
        reduce_by: Number of lanes to reduce from each segment (RECOMMENDED!)
        remain_lanes: Number of lanes to remain (ABSOLUTE - use with caution)
    """
    return network_editor.reduce_lanes(
        net_file=net_file, route_file=route_file, output_dir=output_dir,
        target_road_name=target_road_name, edge_ids=edge_ids,
        reference_location=reference_location, radius_km=radius_km,
        reduce_by=reduce_by, remain_lanes=remain_lanes
    )


@mcp.tool()
def speed_limit_edit_tool(
    net_file: str,
    route_file: str = None,
    output_dir: str = "output/networks",
    target_road_name: str = None,
    edge_ids: list = None,
    reference_location: str = None,
    radius_km: float = None,
    new_speed_kmph: float = None
):
    """
    Modify speed limits on specific road segments (supports partial application).

    ✅ Trip file can be reused - edges still exist, only speed limit changed.
    Workflow: speed_limit_edit → sumo_runner (reuse existing trip file)

    REALISTIC USAGE: Use reference_location + radius_km for localized speed limit changes!

    Examples:
        # REALISTIC: Reduce speed to 40km/h on 500m of Teheran-ro near Gangnam Station
        speed_limit_edit_tool(
            net_file="gangnam_station.net.xml",
            target_road_name="테헤란로",
            reference_location="강남역",
            radius_km=0.5,
            new_speed_kmph=40.0
        )
        # Then: sumo_runner (reuse trip file - no trip_generate needed!)

    Args:
        net_file: Network file path
        route_file: Route file path (optional, can be reused after this tool)
        output_dir: Output directory for results
        target_road_name: Road name (e.g., '테헤란로')
        edge_ids: Specific edge IDs (optional)
        reference_location: Reference point (optional, e.g., "강남역")
        radius_km: Radius in km (optional, e.g., 0.5)
        new_speed_kmph: New speed limit in km/h (e.g., 40.0)
    """
    return network_editor.edit_speed_limit(
        net_file=net_file, route_file=route_file, output_dir=output_dir,
        target_road_name=target_road_name, edge_ids=edge_ids,
        reference_location=reference_location, radius_km=radius_km,
        new_speed_kmph=new_speed_kmph
    )


# =============== VEHICLE MANAGEMENT TOOLS ===============

@mcp.tool()
def vehicle_generation_tool(
    route_file: str,
    net_file: str,
    source_location: str,
    destination_location: str,
    vehicle_id: str = "genveh_0",
    depart_time: float = 0.0,
    depart_time_range: list = None,
    vehicle_count: int = 1,
    output_dir: str = "output/trips",
    use_geocoding: bool = False,
    search_radius: float = 0.3
):
    """
    Add vehicles from source to destination with optimal path calculation.

    SUPPORTS TWO MODES:

    1. Road Name Mode:
       - Use exact road names (e.g., '테헤란로', '강남대로')
       - Set use_geocoding=False (default)

    2. Location Mode (Recommended):
       - Use any location name or place (e.g., '강남역', '코엑스', 'Gangnam Station, Seoul')
       - Uses geocoding to find coordinates, then finds nearest edges
       - Set use_geocoding=True
       - Automatically validates if location is within network bounds

    IMPORTANT NOTES:
    - Location Mode validates coordinates against network bounds (1km buffer)
    - If location is outside network, you'll get a clear error with network bbox info
    - Search radius is 300m by default (sufficient for most cases)

    Args:
        route_file: Route file path
        net_file: Network file path
        source_location: Source location (road name OR place name)
        destination_location: Destination location (road name OR place name)
        vehicle_id: Vehicle ID prefix (default: "genveh_0")
        depart_time: Departure time in seconds (default: 0.0)
        depart_time_range: Departure time range [min, max] in seconds (optional)
        vehicle_count: Number of vehicles to generate (default: 1)
        output_dir: Output directory for results
        use_geocoding: If True, use location-based mode with geocoding (default: False)
        search_radius: Search radius in km for nearest edge (default: 0.3 = 300m)

    Examples:
        Road name mode:
        vehicle_generation_tool(
            route_file="routes.rou.xml",
            net_file="gangnam.net.xml",
            source_location="테헤란로",
            destination_location="강남대로",
            use_geocoding=False
        )

        Location mode (RECOMMENDED):
        vehicle_generation_tool(
            route_file="routes.rou.xml",
            net_file="gangnam.net.xml",
            source_location="강남역",
            destination_location="코엑스",
            use_geocoding=True,
            vehicle_count=20
        )
    """
    return vehicle_manager.generate_vehicles(
        route_file=route_file, net_file=net_file, source_location=source_location,
        destination_location=destination_location, vehicle_id=vehicle_id,
        depart_time=depart_time, depart_time_range=depart_time_range,
        vehicle_count=vehicle_count, output_dir=output_dir,
        use_geocoding=use_geocoding, search_radius=search_radius
    )


@mcp.tool()
def flow_generation_tool(
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
):
    """
    Generate a flow from source to destination with specified parameters.
    
    This tool creates SUMO flows with safety parameters to prevent vehicle insertion failures:
    - departLane="free": Selects the least congested lane
    - departPos="random_free": Places vehicles at random free positions
    - departSpeed="random": Uses realistic departure speeds
    
    Perfect for MSG evacuation scenarios and other large-scale vehicle generation needs.
    
    Args:
        route_file: Route file path
        net_file: Network file path
        source: Source location (place name, e.g., "Madison Square Garden")
        dest: Destination location (place name, e.g., "North Point")
        begin: Start time in seconds (e.g., 0.0)
        end: End time in seconds (e.g., 1800.0)
        vehs_per_hour: Vehicles per hour (e.g., 260)
        flow_id: Flow ID (auto-generated if None)
        output_dir: Output directory for results
        use_geocoding: If True, use geocoding + nearest edge search (default: True)
        search_radius: Search radius in km for nearest edge (default: 0.3)
    
    Examples:
        MSG evacuation flow:
        flow_generation_tool(
            route_file="routes.rou.xml",
            net_file="manhattan.net.xml",
            source="Madison Square Garden",
            dest="North Point",
            begin=0.0,
            end=1800.0,
            vehs_per_hour=260
        )
        
        Multiple flows for different time periods:
        flow_generation_tool(source="MSG", dest="North", begin=0, end=1800, vehs_per_hour=260)
        flow_generation_tool(source="MSG", dest="North", begin=1800, end=3600, vehs_per_hour=160)
        flow_generation_tool(source="MSG", dest="North", begin=3600, end=7200, vehs_per_hour=40)
    """
    return vehicle_manager.generate_flow(
        route_file=route_file, net_file=net_file, source=source, dest=dest,
        begin=begin, end=end, vehs_per_hour=vehs_per_hour, flow_id=flow_id,
        output_dir=output_dir, use_geocoding=use_geocoding, search_radius=search_radius
    )


@mcp.tool()
def vehicle_type_edit_tool(
    route_file: str,
    electric_ratio: float,
    output_dir: str = "output/trips"
):
    """
    Reassign vehicle types in the route file according to the electric_ratio.
    
    Args:
        route_file: Route file path
        electric_ratio: Ratio of electric vehicles (0.0 to 1.0)
        output_dir: Output directory for results
    """
    return vehicle_manager.edit_vehicle_types(
        route_file=route_file, electric_ratio=electric_ratio, output_dir=output_dir
    )


# =============== TRAFFIC LIGHT TOOLS ===============

@mcp.tool()
def tls_offset_tool(
    net_file: str,
    route_file: str,
    output_dir: str = "output/simulations"
):
    """
    Run SUMO tlsCoordinator.py to optimize traffic light offsets and generate an additional XML file.
    
    Args:
        net_file: Network file path (tag will be extracted from filename)
        route_file: Route file path
        output_dir: Output directory for results
    """
    return traffic_light_manager.optimize_offsets(
        net_file=net_file, route_file=route_file, output_dir=output_dir
    )


@mcp.tool()
def tls_adaptation_tool(
    net_file: str,
    route_file: str,
    output_dir: str = "output/simulations"
):
    """
    Run SUMO tlsCycleAdaptation.py to optimize traffic light cycles and generate an additional XML file.
    
    Args:
        net_file: Network file path (tag will be extracted from filename)
        route_file: Route file path
        output_dir: Output directory for results
    """
    return traffic_light_manager.optimize_cycles(
        net_file=net_file, route_file=route_file, output_dir=output_dir
    )


# =============== ANALYSIS TOOLS ===============

# DEPRECATED: SQLite MCP 도입으로 더 이상 사용하지 않음
# DB가 자동 생성되므로 read_query로 분석
# @mcp.tool()
def result_analyzer_tool(
    tripinfo_file: str,
    edgedata_file: str,
    edgedata_emission_file: str,
    output_dir: str = "output/analysis"
):
    """
    Parse SUMO simulation results (tripinfo, edgedata, edgedata_emission) into LLM-friendly JSON format.
    
    IMPORTANT: After running sumo_runner, extract the 3 output files from output_files list:
    - output_files[0] → tripinfo_file
    - output_files[1] → edgedata_file  
    - output_files[2] → edgedata_emission_file
    
    This tool creates summary statistics using SUMO's attributeStats tool.
    Returns:
    - tripinfo_json: Vehicle trip statistics (duration, routeLength, emissions, etc.)
    - edgedata_json: Road segment statistics (speed, density, waitingTime, etc.)
    
    🚨 NEXT STEP: After this tool, ALWAYS call simulation_report_tool with the returned JSON paths!
    
    For detailed queries (Top N, specific edges), use xml_to_sqlite_tool instead.
    
    Args:
        tripinfo_file: Tripinfo XML file path (from sumo_runner output_files[0])
        edgedata_file: Edgedata XML file path (from sumo_runner output_files[1])
        edgedata_emission_file: Edgedata emission XML file path (from sumo_runner output_files[2])
        output_dir: Output directory for JSON files (default: output/analysis)
    
    Returns:
        Dict with tripinfo_json and edgedata_json file paths
    """
    return result_parser.analyze_results(
        tripinfo_file=tripinfo_file, edgedata_file=edgedata_file,
        edgedata_emission_file=edgedata_emission_file, output_dir=output_dir
    )


@mcp.tool()
def xml_to_sqlite_tool(
    tripinfo_xml: str,
    edgedata_xml: str,
    edgedata_emission_xml: str,
    output_dir: str = "output/analysis",
    simulation_id: str = None,
    net_file: str = None,
    route_file: str = None,
    description: str = None
):
    """
    Convert SUMO XML results to SQLite database for advanced SQL-based analysis.

    IMPORTANT: This enables detailed queries that summary statistics cannot answer:
    - Top N queries (e.g., "density 높은 도로 Top 10은?")
    - Specific edge analysis (e.g., "강남역 교차로 혼잡도는?")
    - Comparative analysis (e.g., "정책 전후 density 변화는?")
    - Temporal analysis (e.g., "시간대별 속도 변화는?")

    DATABASE SCHEMA (IMPORTANT):
    - simulations: (simulation_id, created_at, vehicle_count, net_file, route_file, description)
    - trips: (simulation_id, trip_id, duration, routeLength, waitingTime, timeLoss, depart, arrival,
              departLane, arrivalLane, departPos, arrivalPos, departSpeed, arrivalSpeed, departDelay,
              waitingCount, stopTime, rerouteNo, vType, speedFactor, vaporized,
              CO2_abs, CO_abs, HC_abs, NOx_abs, PMx_abs, fuel_abs, electricity_abs, all_attributes)
      * 주요 속성은 개별 컬럼으로 저장, 나머지는 all_attributes JSON 컬럼에 저장
    - edge_metrics: (simulation_id, edge_id, interval_begin, interval_end, speed, density, waitingTime,
                     timeLoss, occupancy, entered, left, arrived, departed, laneChangedFrom, laneChangedTo, all_attributes)
      * 비집계 방식: 모든 interval 데이터를 그대로 저장 (시간대별 분석 가능)
      * 주요 속성은 개별 컬럼으로 저장, 나머지는 all_attributes JSON 컬럼에 저장
      * PRIMARY KEY: (simulation_id, edge_id, interval_begin)

    KEY: Table name is 'edge_metrics', NOT 'edgedata'!

    DESIGN: Single unified DB with simulation_id for comparative studies
    - Same network's simulations → Same DB file
    - Different simulations → Different simulation_ids in same DB
    - Enables SQL JOIN for before/after comparison

    Args:
        tripinfo_xml: Path to tripinfo XML file
        edgedata_xml: Path to edgedata XML file
        edgedata_emission_xml: Path to edgedata emission XML file
        output_dir: Output directory for database (default: output/analysis)
        simulation_id: REQUIRED — NEVER leave as None!
            Format: "{N}_{scenario_name}" where N is the sequential number.
            - Check current simulations in context to determine N.
            - Use short, descriptive English names.
            - Examples: "1_baseline", "2_road_closure_teheran", "3_lane_reduction_gangnam",
              "4_tls_optimize_seocho", "5_speed_limit_gangnam"
        net_file: Path to network (.net.xml) file used in this simulation
        route_file: Path to route (.rou.xml) file used in this simulation
        description: REQUIRED — NEVER leave as None!
            Human-readable English description of the scenario.
            Displayed in the UI for scenario comparison.
            Always describe WHAT was changed and WHERE.
            Examples:
            - "Baseline simulation (Gangnam Station 1km)"
            - "Road closure on Teheran-ro near Gangnam Station (500m)"
            - "Lane reduction on Gangnam-daero (3 to 2 lanes)"
            - "Signal timing optimization at Seocho-daero intersection"
            - "Speed limit reduced to 30km/h on Teheran-ro"

    Returns:
        Dict with db_file, simulation_id, and metadata

    Examples:
        xml_to_sqlite_tool(
            tripinfo_xml="gangnam_tripinfo.xml",
            edgedata_xml="gangnam_edgedata.xml",
            edgedata_emission_xml="gangnam_emission.xml",
            simulation_id="1_baseline",
            description="Baseline simulation (Gangnam Station 1km)"
        )

        xml_to_sqlite_tool(
            ...,
            simulation_id="2_road_closure_teheran",
            description="Road closure on Teheran-ro near Gangnam Station (7 segments)"
        )
    """
    from agentsumo.server.analysis.xml_to_sqlite import XMLToSQLiteConverter, extract_tag_from_xml
    from agentsumo.server.utils.path_utils import get_output_path
    from pathlib import Path

    converter = XMLToSQLiteConverter()

    # Extract tag from filename
    tag = extract_tag_from_xml(tripinfo_xml)

    # DB filename (without timestamp - accumulative)
    # Use get_output_path to ensure agentsumo/output/analysis/ base directory
    output_path = get_output_path(output_dir)
    db_file = output_path / f"{tag}_analysis.db"

    result = converter.convert_simulation_results(
        tripinfo_xml=tripinfo_xml,
        edgedata_xml=edgedata_xml,
        edgedata_emission_xml=edgedata_emission_xml,
        output_db=str(db_file),
        simulation_id=simulation_id,
        net_file=net_file,
        route_file=route_file,
        description=description
    )

    return result


@mcp.tool()
def db_based_simulation_report_tool(
    db_path: str,
    executive_summary: str = "",
    output_dir: str = "output/reports"
):
    """
    Generate a comprehensive HTML simulation analysis report from SQLite database.

    This is the FINAL deliverable of a simulation analysis session.
    It summarizes ALL scenarios in the database with KPIs, comparisons, congestion analysis, and emissions.

    The report is a standalone dark-themed HTML file that can be:
    - Viewed in the web interface (click from file tree)
    - Opened in any browser
    - Shared as a file

    IMPORTANT — Before calling this tool:
    1. Query the database (read_query) to understand the simulation results
    2. Write an executive_summary (1-2 paragraphs, English, professional tone) that covers:
       - Context: what area was studied and what problem was investigated
       - Key findings: most significant results from scenario comparison
       - Risks/concerns: any metrics that worsened or areas of concern
       - Recommendation: what action should urban stakeholders take based on the analysis
       Focus on insights useful for urban decision-makers (policymakers, planners, city officials).
       Do NOT list raw numbers — interpret them.

    Args:
        db_path: Path to SQLite database file
        executive_summary: LLM-generated executive summary for urban stakeholders (English, 1-2 paragraphs)
        output_dir: Output directory for report files

    Returns:
        Dict with report_file path and metadata
    """
    import sqlite3 as sqlite3_mod
    import datetime
    from pathlib import Path
    import sumolib
    from agentsumo.server.utils.path_utils import get_output_path

    try:
        conn = sqlite3_mod.connect(db_path)
        conn.row_factory = sqlite3_mod.Row

        # Get all scenarios (skip auto-generated ones)
        sims = conn.execute(
            "SELECT simulation_id, description, vehicle_count, net_file, created_at FROM simulations WHERE description IS NOT NULL ORDER BY created_at"
        ).fetchall()

        if not sims:
            conn.close()
            return {"status": "error", "message": "No simulations with descriptions found in database"}

        # Get network info from first simulation
        net_file = sims[0]['net_file']
        net_name = Path(net_file).stem.replace('.net', '').replace('_', ' ').title() if net_file else 'Unknown'

        # Network stats via sumolib
        net_edges = 0
        net_junctions = 0
        svg_lines = ""
        try:
            net = sumolib.net.readNet(net_file)
            edges = net.getEdges()
            net_edges = len(edges)
            net_junctions = len(net.getNodes())

            # Generate SVG network visualization
            all_x, all_y = [], []
            for e in edges:
                for x, y in e.getShape():
                    all_x.append(x); all_y.append(y)

            if all_x:
                svg_w, svg_h = 600, 350
                x_min, x_max = min(all_x), max(all_x)
                y_min, y_max = min(all_y), max(all_y)
                x_range = x_max - x_min or 1
                y_range = y_max - y_min or 1
                scale = min(svg_w / x_range, svg_h / y_range) * 0.92
                ox = (svg_w - x_range * scale) / 2
                oy = (svg_h - y_range * scale) / 2

                svg_paths = []
                for e in edges:
                    if e.getLength() < 3:
                        continue
                    shape = e.getShape()
                    points = []
                    for x, y in shape:
                        sx = (x - x_min) * scale + ox
                        sy = svg_h - ((y - y_min) * scale + oy)
                        points.append(f"{sx:.1f},{sy:.1f}")
                    if len(points) >= 2:
                        svg_paths.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#5b8c00" stroke-width="1.2" stroke-opacity="0.6"/>')
                svg_lines = "\n".join(svg_paths)
        except Exception as e:
            logger.warning(f"Network SVG generation failed: {e}")

        # Per-scenario KPI data
        scenarios = []
        for sim in sims:
            sid = sim['simulation_id']
            r = conn.execute("""
                SELECT COUNT(*) as trips, AVG(duration) as dur, AVG(waitingTime) as wait,
                       AVG(timeLoss) as tl, AVG(routeLength) as rlen,
                       SUM(CO2_abs)/1e6 as co2_kg, SUM(fuel_abs)/1e6 as fuel_L,
                       SUM(NOx_abs)/1e3 as nox_g, SUM(PMx_abs)/1e3 as pm_g
                FROM trips WHERE simulation_id=?
            """, (sid,)).fetchone()

            spd = conn.execute(
                "SELECT AVG(speed) as s FROM edge_metrics WHERE simulation_id=? AND speed > 0", (sid,)
            ).fetchone()

            # Duration distribution
            dist = []
            for label, lo, hi in [("<1 min",0,60),("1-3 min",60,180),("3-5 min",180,300),("5-10 min",300,600),("10+ min",600,999999)]:
                cnt = conn.execute("SELECT COUNT(*) FROM trips WHERE simulation_id=? AND duration>=? AND duration<?", (sid, lo, hi)).fetchone()[0]
                dist.append({"bucket": label, "count": cnt})

            scenarios.append({
                "id": sid,
                "desc": sim['description'],
                "vehicles": sim['vehicle_count'],
                "created": sim['created_at'][:16],
                "trips": r['trips'],
                "avg_duration": r['dur'],
                "avg_wait": r['wait'],
                "avg_timeloss": r['tl'],
                "avg_speed_kmh": round((spd['s'] or 0) * 3.6, 1),
                "co2_kg": round(r['co2_kg'] or 0, 1),
                "fuel_L": round(r['fuel_L'] or 0, 2),
                "nox_g": round(r['nox_g'] or 0, 1),
                "pm_g": round(r['pm_g'] or 0, 2),
                "duration_dist": dist
            })

        # Congestion analysis (from first scenario — baseline)
        base_sid = sims[0]['simulation_id']
        congested = []
        try:
            net_for_names = sumolib.net.readNet(net_file)
            rows = conn.execute("""
                SELECT edge_id, AVG(density) as d, AVG(speed) as s, AVG(waitingTime) as w
                FROM edge_metrics WHERE simulation_id=? AND density > 0 GROUP BY edge_id
            """, (base_sid,)).fetchall()

            road_data = {}
            for r in rows:
                try:
                    edge = net_for_names.getEdge(r['edge_id'])
                    if edge.getLength() < 5:
                        continue
                    name = edge.getName()
                    if not name:
                        continue
                    length = edge.getLength()
                except Exception:
                    continue
                if name not in road_data:
                    road_data[name] = {"sd": 0, "ss": 0, "sw": 0, "tl": 0}
                rd = road_data[name]
                rd["sd"] += r['d'] * length
                rd["ss"] += r['s'] * length
                rd["sw"] += r['w'] * length
                rd["tl"] += length

            for name, rd in sorted(road_data.items(), key=lambda x: x[1]["sd"]/x[1]["tl"] if x[1]["tl"] else 0, reverse=True)[:5]:
                if rd["tl"] == 0:
                    continue
                congested.append({
                    "name": name,
                    "density": round(rd["sd"] / rd["tl"], 1),
                    "speed_kmh": round(rd["ss"] / rd["tl"] * 3.6, 1),
                    "wait_min": round(rd["sw"] / rd["tl"] / 60, 1)
                })
        except Exception:
            pass

        conn.close()

        # Helper functions for formatting
        def fmt_time(s):
            if s is None: return "—"
            if s < 60: return f"{s:.1f}s"
            return f"{s/60:.1f} min"

        def fmt_num(n):
            if n is None: return "—"
            return f"{n:,.1f}"

        def diff_pct(a, b):
            if not a or a == 0: return "—"
            pct = (b - a) / abs(a) * 100
            sign = "+" if pct > 0 else ""
            return f"{sign}{pct:.0f}%"

        # Build HTML
        base = scenarios[0]
        has_compare = len(scenarios) > 1
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # KPI comparison table rows
        kpi_rows = ""
        metrics = [
            ("Avg Trip Duration", "avg_duration", True, fmt_time),
            ("Avg Waiting Time", "avg_wait", True, fmt_time),
            ("Avg Time Loss", "avg_timeloss", True, fmt_time),
            ("Avg Speed", "avg_speed_kmh", False, lambda v: f"{v:.1f} km/h"),
            ("Total CO₂", "co2_kg", True, lambda v: f"{v:,.1f} kg"),
            ("Total Fuel", "fuel_L", True, lambda v: f"{v:,.2f} L"),
            ("Total NOx", "nox_g", True, lambda v: f"{v:,.1f} g"),
            ("Completed Trips", "trips", False, lambda v: f"{v:,}"),
        ]

        for label, key, higher_bad, formatter in metrics:
            row = f"<tr><td style='color:#8aa69c;'>{label}</td>"
            vals = [s[key] for s in scenarios]
            for i, v in enumerate(vals):
                row += f"<td style='text-align:right;'>{formatter(v)}</td>"
            if has_compare:
                d = diff_pct(vals[0], vals[-1])
                color = "#ff5a5a" if ("+" in d and higher_bad) or ("-" in d and not higher_bad) else "#2166ac" if d != "—" else "#556e66"
                row += f"<td style='text-align:right; color:{color}; font-weight:600;'>{d}</td>"
            row += "</tr>"
            kpi_rows += row

        # Scenario headers
        scenario_headers = "".join(f"<th style='text-align:right;'>{s['id']}</th>" for s in scenarios)
        if has_compare:
            scenario_headers += "<th style='text-align:right;'>Change</th>"

        # Duration distribution bars
        dist_html = ""
        max_count = max(d["count"] for s in scenarios for d in s["duration_dist"]) or 1
        for i, bucket_info in enumerate(base["duration_dist"]):
            bucket = bucket_info["bucket"]
            dist_html += f"<div style='display:flex; align-items:center; margin-bottom:4px; gap:8px;'>"
            dist_html += f"<span style='width:60px; text-align:right; font-size:12px; color:#8aa69c;'>{bucket}</span>"
            dist_html += f"<div style='flex:1; display:flex; flex-direction:column; gap:2px;'>"
            for j, s in enumerate(scenarios):
                cnt = s["duration_dist"][i]["count"]
                pct = cnt / max_count * 100
                color = "#5b8c00" if j == 0 else "#ffb84d"
                dist_html += f"<div style='height:8px; background:{color}; width:{pct}%; border-radius:3px; opacity:0.7;'></div>"
            dist_html += "</div>"
            dist_html += f"<span style='width:30px; font-size:11px; color:#556e66; text-align:right;'>{base['duration_dist'][i]['count']}</span>"
            dist_html += "</div>"

        # Legend for distribution
        dist_legend = ""
        if has_compare:
            dist_legend = "<div style='display:flex; gap:16px; justify-content:center; margin-top:8px; font-size:11px; color:#556e66;'>"
            dist_legend += "<span><span style='display:inline-block;width:10px;height:10px;background:#5b8c00;border-radius:2px;margin-right:4px;'></span>Base</span>"
            dist_legend += "<span><span style='display:inline-block;width:10px;height:10px;background:#ffb84d;border-radius:2px;margin-right:4px;'></span>Compare</span>"
            dist_legend += "</div>"

        # Congestion table
        congestion_rows = ""
        for i, c in enumerate(congested):
            congestion_rows += f"<tr><td style='color:#556e66; font-weight:600;'>{i+1}</td><td>{c['name']}</td><td style='text-align:right;'>{c['density']}</td><td style='text-align:right;'>{c['speed_kmh']} km/h</td><td style='text-align:right;'>{c['wait_min']} min</td></tr>"

        # Scenario list
        scenario_list = ""
        for s in scenarios:
            scenario_list += f"""
            <div style="background:rgba(0,0,0,0.15); border:1px solid rgba(91,140,0,0.12); border-radius:8px; padding:12px; margin-bottom:8px;">
                <div style="font-weight:500; color:#dce8e3; margin-bottom:4px;">{s['id']}</div>
                <div style="font-size:13px; color:#8aa69c;">{s['desc']}</div>
                <div style="font-size:11px; color:#556e66; margin-top:4px;">{s['vehicles']} vehicles · {s['created']}</div>
            </div>"""

        # Emission comparison
        emission_rows = ""
        emission_metrics = [("CO₂", "co2_kg", "kg"), ("Fuel", "fuel_L", "L"), ("NOx", "nox_g", "g"), ("PM", "pm_g", "g")]
        for label, key, unit in emission_metrics:
            row = f"<tr><td style='color:#8aa69c;'>{label}</td>"
            for s in scenarios:
                row += f"<td style='text-align:right;'>{s[key]:,.1f} {unit}</td>"
            if has_compare:
                d = diff_pct(scenarios[0][key], scenarios[-1][key])
                color = "#2166ac" if "-" in d else "#ff5a5a" if "+" in d else "#556e66"
                row += f"<td style='text-align:right; color:{color}; font-weight:600;'>{d}</td>"
            row += "</tr>"
            emission_rows += row

        # Assemble HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentSUMO Analysis Report</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"/>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Pretendard',sans-serif; background:#080a0c; color:#dce8e3; padding:40px; max-width:900px; margin:0 auto; line-height:1.6; }}
  h1 {{ font-size:28px; font-weight:700; margin-bottom:8px; }}
  h2 {{ font-size:16px; font-weight:600; color:#7ab800; letter-spacing:1.5px; text-transform:uppercase; margin:32px 0 16px 0; padding-bottom:8px; border-bottom:1px solid rgba(91,140,0,0.2); }}
  .subtitle {{ font-size:14px; color:#556e66; margin-bottom:32px; }}
  .summary {{ background:rgba(91,140,0,0.06); border:1px solid rgba(91,140,0,0.15); border-radius:10px; padding:20px; margin-bottom:32px; font-size:15px; line-height:1.7; color:#8aa69c; }}
  table {{ width:100%; border-collapse:collapse; margin:12px 0; font-size:13px; }}
  th {{ text-align:left; padding:8px 10px; color:#556e66; font-weight:500; font-size:12px; border-bottom:1px solid rgba(91,140,0,0.15); }}
  td {{ padding:8px 10px; border-bottom:1px solid rgba(91,140,0,0.06); color:#8aa69c; }}
  tr:hover td {{ color:#dce8e3; }}
  .svg-container {{ background:rgba(0,0,0,0.3); border:1px solid rgba(91,140,0,0.15); border-radius:10px; padding:16px; margin:12px 0; text-align:center; }}
  .footer {{ margin-top:40px; padding-top:16px; border-top:1px solid rgba(91,140,0,0.1); font-size:11px; color:#556e66; text-align:center; }}
</style>
</head>
<body>
<h1>AgentSUMO Analysis Report</h1>
<div class="subtitle">Generated {now} · {len(scenarios)} scenario(s) analyzed</div>

<div class="summary">
<strong>Study Area:</strong> {net_name} · {net_edges:,} edges · {net_junctions:,} junctions<br>
<strong>Scenarios:</strong> {', '.join(s['desc'] for s in scenarios)}
</div>

{'<h2>Executive Summary</h2><div class="summary" style="font-size:15px; line-height:1.8; color:#dce8e3;">' + executive_summary + '</div>' if executive_summary else ''}

<h2>Study Area Network</h2>
<div class="svg-container">
<svg width="600" height="350" viewBox="0 0 600 350" xmlns="http://www.w3.org/2000/svg" style="background:rgba(0,0,0,0.2); border-radius:6px;">
{svg_lines}
</svg>
</div>

<h2>Scenarios</h2>
{scenario_list}

<h2>Performance Comparison</h2>
<table>
<thead><tr><th>Metric</th>{scenario_headers}</tr></thead>
<tbody>{kpi_rows}</tbody>
</table>

<h2>Trip Duration Distribution</h2>
{dist_html}
{dist_legend}

<h2>Most Congested Roads (Baseline)</h2>
<table>
<thead><tr><th>#</th><th>Road</th><th>Density</th><th>Speed</th><th>Wait</th></tr></thead>
<tbody>{congestion_rows}</tbody>
</table>

<h2>Emission Summary</h2>
<table>
<thead><tr><th>Pollutant</th>{scenario_headers}</tr></thead>
<tbody>{emission_rows}</tbody>
</table>

<div class="footer">
AgentSUMO · AI-Powered Traffic Simulation Platform · {now}
</div>
</body>
</html>"""

        # Save report
        output_path = get_output_path(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_path / f"report_{timestamp}.html"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html)

        return {
            "status": "success",
            "report_file": str(report_file),
            "scenarios": len(scenarios),
            "message": f"Report generated: {report_file.name}"
        }

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": str(e),
            "detail": traceback.format_exc()
        }


# DEPRECATED: result_analyzer_tool 비활성화로 함께 비활성화
# DB 기반 리포트는 db_based_simulation_report_tool 사용
# @mcp.tool()
def simulation_report_tool(
    tripinfo_json: str,
    edgedata_json: str,
    output_dir: str = "output/reports"
):
    """
    Generate comprehensive natural language simulation report from JSON data using Claude.
    
    🚨 CRITICAL: ALWAYS call this tool after result_analyzer_tool!
    
    This is THE PRIMARY WAY to generate professional traffic analysis reports.
    DO NOT analyze simulation results manually - use this tool for accurate, 
    expert-level traffic engineering analysis.
    
    WORKFLOW (MANDATORY):
    1. sumo_runner → XML files
    2. result_analyzer_tool → JSON files (tripinfo_json, edgedata_json)
    3. THIS TOOL → Professional report with traffic engineering insights
    
    REQUIRES: ANTHROPIC_API_KEY environment variable
    
    This tool uses Claude (Sonnet 4.0) with traffic engineering expertise to:
    - Analyze JSON data comprehensively
    - Apply traffic flow theory and LOS standards
    - Identify bottlenecks and root causes
    - Provide actionable recommendations
    
    Args:
        tripinfo_json: Tripinfo JSON file path
        edgedata_json: Edgedata JSON file path
        output_dir: Output directory for report files
    
    Returns:
        Dict with report_file path and metadata
    """
    # Lazy initialization (API key required)
    report_generator = ReportGenerator()
    
    return report_generator.generate_report(
        tripinfo_json=tripinfo_json, edgedata_json=edgedata_json, output_dir=output_dir
    )


# DEPRECATED: JSON 기반 QA → SQLite read_query 사용
# @mcp.tool()
def simulation_qa_tool(
    tripinfo_json: str,
    edgedata_json: str,
    question: str
):
    """
    Answer questions about simulation results using JSON data.

    NOTE: This is a basic rule-based QA system.
    For detailed queries (Top N, specific edges, comparisons), use SQLite MCP with read_query tool.

    Args:
        tripinfo_json: Tripinfo JSON file path
        edgedata_json: Edgedata JSON file path
        question: Question about simulation results (in Korean or English)
    """
    from agentsumo.server.analysis.qa_system import QASystem
    qa_system = QASystem()

    return qa_system.answer_question(
        tripinfo_json=tripinfo_json, edgedata_json=edgedata_json, question=question
    )


# =============== NETWORK & ROUTE ANALYSIS TOOLS ===============

@mcp.tool()
def network_summary_tool(net_file: str):
    """
    Get a comprehensive summary of a SUMO network.

    Use when user asks about the network, its size, or what roads are included.
    Returns edge count, junction count, total road length, bounding box, and road name list.

    Args:
        net_file: Path to the SUMO network file (.net.xml)

    Returns:
        Dict with network statistics and road names
    """
    import sumolib

    try:
        net = sumolib.net.readNet(net_file)
        edges = net.getEdges()
        nodes = net.getNodes()

        # Basic stats
        total_length = sum(e.getLength() for e in edges)
        total_lanes = sum(e.getLaneNumber() for e in edges)

        # Bounding box
        all_x, all_y = [], []
        for e in edges:
            for x, y in e.getShape():
                all_x.append(x); all_y.append(y)

        bbox = None
        if all_x:
            min_lon, min_lat = net.convertXY2LonLat(min(all_x), min(all_y))
            max_lon, max_lat = net.convertXY2LonLat(max(all_x), max(all_y))
            bbox = {
                "south": round(min_lat, 4), "north": round(max_lat, 4),
                "west": round(min_lon, 4), "east": round(max_lon, 4)
            }

        # Road names (unique, sorted)
        road_names = sorted(set(e.getName() for e in edges if e.getName()))

        # Speed limit stats
        speeds = [e.getSpeed() for e in edges if e.getLength() >= 5]
        avg_speed_kmh = round(sum(speeds) / len(speeds) * 3.6, 1) if speeds else 0

        return {
            "status": "success",
            "net_file": net_file,
            "edges": len(edges),
            "junctions": len(nodes),
            "total_road_length_km": round(total_length / 1000, 2),
            "total_lanes": total_lanes,
            "avg_speed_limit_kmh": avg_speed_kmh,
            "bbox": bbox,
            "road_names": road_names,
            "road_count": len(road_names),
            "traffic_lights": len(net.getTrafficLights())
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def route_analysis_tool(
    net_file: str,
    origin: str,
    destination: str,
    routing_mode: str = "distance",
    weight_file: str = None,
    weight_attribute: str = "traveltime",
    compare_net_file: str = None,
    compare_weight_file: str = None
):
    """
    Analyze the optimal route between two locations in the network.

    Accepts place names (e.g., "강남역", "Gangnam Station") or road names (e.g., "테헤란로").

    TWO ROUTING MODES:
    1. "distance" (default): Shortest path by edge length. Works without simulation data.
    2. "traveltime": Optimal path using actual simulation results (edgedata XML) as edge weights.
       Requires weight_file (edgedata XML from a previous simulation).
       Can also use other attributes: "density", "CO2_abs", etc.

    Use cases:
    - "강남역에서 삼성역까지 최단 경로는?" → routing_mode="distance"
    - "실제 통행시간 기반 최적 경로는?" → routing_mode="traveltime", weight_file=edgedata.xml
    - "CO2 최소 경로는?" → routing_mode="traveltime", weight_attribute="CO2_abs"
    - "도로 차단 후 경로 변화는?" → compare_net_file + compare_weight_file

    In web mode, use [SHOW_ROUTE:edges|color|net_file_name] marker to visualize the result.
    Always include net_file_name from the result so routes render on the correct network.

    Args:
        net_file: Network file path
        origin: Origin location (place name, landmark, or road name)
        destination: Destination location (place name, landmark, or road name)
        routing_mode: "distance" (default, edge length) or "traveltime" (simulation-weighted)
        weight_file: Edgedata XML file for weighted routing (required when routing_mode="traveltime").
                     Use the netstate/edgedata file from simulation output.
        weight_attribute: Attribute to use as edge weight (default: "traveltime").
                         Other options: "density", "CO2_abs", "fuel_abs", etc.
        compare_net_file: Optional second network for before/after route comparison
        compare_weight_file: Optional edgedata for the comparison network

    Returns:
        Dict with route edges, distance, time, road names.
        If comparison provided, includes both routes and diff.
    """
    import sumolib
    import subprocess
    import tempfile
    import xml.etree.ElementTree as ET
    from pathlib import Path
    from agentsumo.server.utils.sumo_utils import (
        geocode_location, find_nearest_edge, check_coordinates_in_network,
        get_edge_ids_from_road_name
    )
    from agentsumo.server.settings.settings import sumo_environment

    def resolve_location(net, net_path, loc_name):
        """Resolve location to edge — geocoding first, road name fallback"""
        coords = geocode_location(loc_name)
        if coords:
            valid, info = check_coordinates_in_network(net_path, coords[0], coords[1], buffer_km=1.5)
            if valid:
                result = find_nearest_edge(net_path, coords[0], coords[1], 0.5)
                if result:
                    return result[0], coords
        edge_ids = get_edge_ids_from_road_name(net_path, loc_name)
        if edge_ids:
            return edge_ids[len(edge_ids)//2], None
        return None, None

    def compute_route_stats(net, edge_ids):
        """Compute distance, free-flow time, and road names for a route"""
        total_dist = 0
        total_time = 0
        road_names = []
        seen = set()
        for eid in edge_ids:
            try:
                e = net.getEdge(eid)
                total_dist += e.getLength()
                total_time += e.getLength() / max(e.getSpeed(), 0.1)
                name = e.getName()
                if name and name not in seen:
                    road_names.append(name)
                    seen.add(name)
            except Exception:
                pass
        return total_dist, total_time, road_names

    def route_via_sumolib(net, origin_eid, dest_eid):
        """Distance-based shortest path via sumolib"""
        src = net.getEdge(origin_eid)
        dst = net.getEdge(dest_eid)
        path_result = net.getShortestPath(src, dst, vClass="passenger")
        if path_result and path_result[0]:
            return [e.getID() for e in path_result[0]]
        return None

    def route_via_duarouter(net_path, origin_eid, dest_eid, wt_file, wt_attr):
        """Weighted routing via SUMO duarouter"""
        duarouter_bin = sumo_environment.get_binary_path("duarouter")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create trip file
            trip_file = Path(tmpdir) / "trip.xml"
            trip_file.write_text(
                f'<trips>\n'
                f'  <trip id="analysis" depart="0" from="{origin_eid}" to="{dest_eid}"/>\n'
                f'</trips>\n'
            )

            output_file = Path(tmpdir) / "routes.xml"

            cmd = [
                duarouter_bin,
                "--net-file", str(net_path),
                "--trip-files", str(trip_file),
                "--output-file", str(output_file),
                "--no-warnings", "true",
                "--ignore-errors", "true",
            ]

            if wt_file:
                cmd.extend(["--weight-files", str(wt_file)])
                if wt_attr:
                    cmd.extend(["--weight-attribute", wt_attr])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if not output_file.exists():
                return None

            # Parse route output
            tree = ET.parse(str(output_file))
            for vehicle in tree.findall('.//vehicle'):
                route_elem = vehicle.find('route')
                if route_elem is not None:
                    edges_str = route_elem.get('edges', '')
                    if edges_str:
                        return edges_str.split()
        return None

    def analyze_single(net_path, origin_name, dest_name, mode, wt_file, wt_attr):
        """Full analysis for one network"""
        net = sumolib.net.readNet(str(net_path))

        origin_eid, origin_coords = resolve_location(net, str(net_path), origin_name)
        if not origin_eid:
            return None, None, f"Could not find origin: {origin_name}"

        dest_eid, dest_coords = resolve_location(net, str(net_path), dest_name)
        if not dest_eid:
            return None, None, f"Could not find destination: {dest_name}"

        # Route calculation
        if mode == "traveltime" and wt_file:
            edge_ids = route_via_duarouter(net_path, origin_eid, dest_eid, wt_file, wt_attr)
            if not edge_ids:
                # Fallback to distance
                edge_ids = route_via_sumolib(net, origin_eid, dest_eid)
                mode = "distance (fallback)"
        else:
            edge_ids = route_via_sumolib(net, origin_eid, dest_eid)

        if not edge_ids:
            return None, None, f"No route found from {origin_name} to {dest_name}"

        total_dist, total_time, road_names = compute_route_stats(net, edge_ids)

        route_data = {
            "route_edge_ids": edge_ids,
            "route_edge_count": len(edge_ids),
            "distance_m": round(total_dist, 1),
            "distance_km": round(total_dist / 1000, 2),
            "freeflow_time_s": round(total_time, 1),
            "freeflow_time_min": round(total_time / 60, 1),
            "road_names_along_route": road_names,
            "routing_mode": mode,
            "origin_edge": origin_eid,
            "destination_edge": dest_eid,
        }

        coords_info = {"origin_coords": origin_coords, "dest_coords": dest_coords}
        return route_data, coords_info, None

    try:
        # Primary route
        route_data, coords_info, error = analyze_single(
            net_file, origin, destination, routing_mode, weight_file, weight_attribute
        )

        if error:
            return {"status": "error", "message": error}

        result = {
            "status": "success",
            "origin": origin,
            "destination": destination,
            "net_file_name": Path(net_file).name,
            **route_data
        }

        if weight_file and routing_mode == "traveltime":
            result["weight_file"] = weight_file
            result["weight_attribute"] = weight_attribute

        # Comparison route
        if compare_net_file:
            cmp_mode = "traveltime" if compare_weight_file else "distance"
            cmp_data, _, cmp_error = analyze_single(
                compare_net_file, origin, destination, cmp_mode, compare_weight_file, weight_attribute
            )

            if cmp_error:
                result["compare"] = {"status": "error", "message": cmp_error}
            else:
                base_dist = route_data["distance_m"]
                base_time = route_data["freeflow_time_s"]
                cmp_dist = cmp_data["distance_m"]
                cmp_time = cmp_data["freeflow_time_s"]

                cmp_data["distance_change_pct"] = round((cmp_dist - base_dist) / max(base_dist, 1) * 100, 1)
                cmp_data["time_change_pct"] = round((cmp_time - base_time) / max(base_time, 1) * 100, 1)
                cmp_data["route_changed"] = route_data["route_edge_ids"] != cmp_data["route_edge_ids"]
                cmp_data["net_file_name"] = Path(compare_net_file).name
                result["compare"] = cmp_data

        return result

    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "detail": traceback.format_exc()}


# =============== VISUALIZATION TOOLS ===============

@mcp.tool()
def visualize_net_tool(
    net_file: str,
    output_dir: str = "output/visualizations"
):
    """
    Visualize a SUMO network file and save as PNG image.

    ⚠️ IMPORTANT: Only use when user EXPLICITLY requests visualization!
    - User says "show network map", "visualize network" → Use this
    - User asks about simulation results → Do NOT use, answer with text

    Args:
        net_file: Path to the SUMO network file (.net.xml)
        output_dir: Output directory for visualization files
    """
    return network_plotter.visualize_network(net_file=net_file, output_dir=output_dir)


@mcp.tool()
def visualize_edge_tool(
    net_file: str,
    road_name: str,
    output_dir: str = "output/visualizations"
):
    """
    Visualize a SUMO network file with selected edges highlighted and save as PNG image.

    Only use when user EXPLICITLY requests edge visualization!
    - User says "show edge details", "visualize this road" → Use this
    - User asks "which road is congested?" → Do NOT use, answer with text

    Args:
        net_file: Path to the SUMO network file (.net.xml)
        road_name: Name of the road to highlight
        output_dir: Output directory for visualization files
    """
    return edge_plotter.visualize_edge(
        net_file=net_file, road_name=road_name, output_dir=output_dir
    )


@mcp.tool()
def visualize_policy_target_tool(
    net_file: str,
    target_road_name: str,
    reference_location: str = None,
    radius_km: float = None,
    output_dir: str = "output/visualizations"
):
    """
    Visualize policy target area using SUMO's built-in visualization.

    Only use when user EXPLICITLY requests to preview policy area!
    - User says "show me which roads will be affected" → Use this
    - User just wants to apply policy → Do NOT use, proceed with policy tool

    This tool helps visualize which road segments will be affected by a policy
    before actually applying it. Essential for confirming policy target area!

    VISUALIZATION:
    - Shows ONLY the selected road segments within the specified radius
    - Uses SUMO's standard plot_net_selection.py for consistent styling
    - Clean, focused view of the policy target area

    USE CASES:
    1. "Show me which part of 테헤란로 near 강남역 within 300m will be affected"
    2. "Visualize policy target before deleting road segments"
    3. "Preview lane reduction area before applying"

    REALISTIC WORKFLOW:
    Step 1: Use this tool to visualize policy area
    Step 2: Confirm the target area is correct
    Step 3: Apply policy using edge_edit_tool/reduce_lanes_tool/speed_limit_edit_tool

    Args:
        net_file: Network file path
        target_road_name: Road name (e.g., "테헤란로", "Teheran-ro")
        reference_location: Reference point (e.g., "강남역", "Gangnam Station")
        radius_km: Radius in km (e.g., 0.3 for 300m)
        output_dir: Output directory

    Returns:
        PNG file showing selected road segments only

    EXAMPLE:
    visualize_policy_target_tool(
        net_file="gangnam_station.net.xml",
        target_road_name="테헤란로",
        reference_location="강남역 교차로",
        radius_km=0.3
    )
    → Shows: Only the 300m segment of 테헤란로 near 강남역 (selected segments)
    """
    return edge_plotter.visualize_policy_target(
        net_file=net_file,
        target_road_name=target_road_name,
        reference_location=reference_location,
        radius_km=radius_km,
        output_dir=output_dir
    )


@mcp.tool()
def analyze_road_details_tool(
    net_file: str,
    target_road_name: str,
    reference_location: str = None,
    radius_km: float = None,
    include_lane_details: bool = True
):
    """
    Analyze detailed road information (lanes, speed limits, length, etc.).

    This tool provides comprehensive analysis of road segments including:
    - Number of lanes per segment
    - Speed limits (km/h)
    - Road length and width
    - Statistical summary (averages, min/max)

    USE CASES:
    1. "테헤란로 강남역 근처 500m 구간의 차선 수와 속도제한을 알려줘"
    2. "현재 도로 상태를 분석해서 정책 적용 전후 비교"
    3. "도로 용량 분석 (차선 수 × 길이)"

    Args:
        net_file: Network file path
        target_road_name: Road name (e.g., "테헤란로", "Teheran-ro")
        reference_location: Reference point (e.g., "강남역", "Gangnam Station")
        radius_km: Radius in km (e.g., 0.5 for 500m)
        include_lane_details: Whether to include per-lane information

    Returns:
        Dict with detailed road analysis including:
        - segments: List of segment details
        - statistics: Overall statistics (avg lanes, speed, length)
        - summary: Human-readable summary
        - filtering: Location filtering info (if applied)

    EXAMPLE:
    analyze_road_details_tool(
        net_file="gangnam_station.net.xml",
        target_road_name="테헤란로",
        reference_location="강남역",
        radius_km=0.5
    )
    → Returns: 강남역 500m 이내 테헤란로 segments의 상세 분석
    """
    from agentsumo.server.utils.sumo_utils import analyze_road_by_name_and_location

    return analyze_road_by_name_and_location(
        net_file=net_file,
        target_road_name=target_road_name,
        reference_location=reference_location,
        radius_km=radius_km,
        include_lane_details=include_lane_details
    )


@mcp.tool()
def visualize_edgedata_tool(
    net_file: str,
    edgedata_file: str,
    attribute: str = "density",
    output_dir: str = "output/visualizations",
    scale_mode: str = "auto",
    comparison_files: list = None,
    min_value: float = None,
    max_value: float = None
):
    """
    🎨 Visualize SUMO edgedata with flexible scaling modes for comparison.

    ⚠️ IMPORTANT: Only use when user EXPLICITLY requests heatmap/visualization!
    - User says "show heatmap", "visualize density", "show congestion map" → Use this
    - User asks "which road is congested?", "어느 도로가 정체?" → Do NOT use, answer with text from SQL query

    **SCALE MODES:**
    
    1. **'auto'** (default): Dynamic scale from current file
       - Best for: Single simulation analysis
       - Scale: Optimized for current data range
    
    2. **'unified'**: Consistent scale across multiple files
       - Best for: Policy comparison (before/after)
       - Requires: comparison_files parameter
       - Example: Compare baseline vs policy A vs policy B
    
    3. **'fixed'**: User-defined fixed scale
       - Best for: Standardized reports, academic papers
       - Requires: min_value and max_value parameters
       - Example: Always use [0, 100] for all simulations
    
    **USE CASES:**
    
    # Single simulation analysis (auto scale)
    visualize_edgedata_tool(..., scale_mode="auto")
    → Optimized color contrast for this simulation
    
    # Policy comparison (unified scale)
    visualize_edgedata_tool(
        edgedata_file="after.xml",
        scale_mode="unified",
        comparison_files=["before.xml"]
    )
    → Same colors mean same values across both
    
    # Standardized scale (fixed)
    visualize_edgedata_tool(..., scale_mode="fixed", min_value=0, max_value=100)
    → All simulations use [0, 100] scale
    
    Args:
        net_file: Path to the SUMO network file (.net.xml)
        edgedata_file: Path to the SUMO edgeData output file (.xml)
        attribute: Attribute to visualize (e.g., 'density', 'speed', 'CO2_abs')
        output_dir: Output directory for visualization files
        scale_mode: Scale mode ('auto' | 'unified' | 'fixed')
        comparison_files: List of files for unified scale (for 'unified' mode)
        min_value: Minimum value for fixed scale (for 'fixed' mode)
        max_value: Maximum value for fixed scale (for 'fixed' mode)
    """
    return data_plotter.visualize_edgedata(
        net_file=net_file,
        edgedata_file=edgedata_file,
        attribute=attribute,
        output_dir=output_dir,
        scale_mode=scale_mode,
        comparison_files=comparison_files,
        min_value=min_value,
        max_value=max_value
    )


# =============== UTILITY TOOLS ===============

@mcp.tool()
def get_road_names_tool(
    edge_ids: list,
    net_file: str
):
    """
    Convert SUMO edge IDs to actual road names using edge.getName().

    IMPORTANT: Use this after congestion analysis to show human-readable road names!

    This tool maps SUMO's technical edge IDs to real-world street names,
    making analysis results much more understandable and actionable.

    Args:
        edge_ids: List of SUMO edge IDs to convert (e.g., ["194926855#1", "420901920#0"])
        net_file: Network file path used in simulation.
                  When working with DB data, get this from:
                  SELECT net_file FROM simulations WHERE simulation_id = '<your_sim_id>'

    Returns:
        Dict mapping edge_id → road_name

    Example workflow:
        1. SQL query for Top 10 density:
           read_query("SELECT edge_id, avg_density FROM edge_metrics ORDER BY avg_density DESC LIMIT 10")
           → ["194926855#1", "1030139836#1", ...]

        2. Get net_file from DB (if using DB data):
           read_query("SELECT net_file FROM simulations WHERE simulation_id = 'baseline'")
           → "/path/to/network.net.xml"

        3. Convert to road names:
           get_road_names_tool(
               edge_ids=["194926855#1", "1030139836#1", ...],
               net_file="/path/to/network.net.xml"  # Use actual path from step 2 or user-provided
           )
           → {"194926855#1": "9th Avenue", "1030139836#1": "Broadway", ...}

        4. Present results:
           "Top 10 Congested Roads:
            1. 9th Avenue: 800 veh/km
            2. Broadway: 731 veh/km
            ..."

    Note:
        - Returns "Unnamed Road" if road name not set in network
    """
    from agentsumo.server.utils.sumo_utils import get_road_names_from_edges

    return get_road_names_from_edges(edge_ids, net_file)


@mcp.tool()
def get_edge_ids_from_road_name_tool(
    road_name: str,
    net_file: str
):
    """
    Convert road name to SUMO edge IDs using edge.getName().

    IMPORTANT: Use this when user asks questions with road names (e.g., "테헤란로의 밀도는?")

    This tool maps human-readable road names to SUMO's technical edge IDs,
    enabling SQL queries based on road names.

    Args:
        road_name: Road name (e.g., "테헤란로", "강남대로", "9th Avenue")
        net_file: Network file path used in simulation.
                  When working with DB data, get this from:
                  SELECT net_file FROM simulations WHERE simulation_id = '<your_sim_id>'

    Returns:
        List[str]: List of edge IDs matching the road name

    Example workflow:
        1. User asks: "테헤란로의 밀도는?"

        2. Get net_file from DB (if using DB data):
           read_query("SELECT net_file FROM simulations WHERE simulation_id = 'baseline'")
           → "/path/to/network.net.xml"

        3. Convert road name to edge IDs:
           get_edge_ids_from_road_name_tool(
               road_name="테헤란로",
               net_file="/path/to/network.net.xml"  # Use actual path from step 2
           )
           → ["375049565#11", "375049565#12", "375049565#13", ...]

        4. Use in SQL query:
           read_query("SELECT AVG(density) FROM edge_metrics WHERE edge_id IN ('375049565#11', '375049565#12', ...)")

        5. Present results with road name (not edge IDs)

    Note:
        - Returns all edge segments for the given road name
        - Raises ValueError if road name not found
    """
    from agentsumo.server.utils.sumo_utils import get_edge_ids_from_road_name

    return get_edge_ids_from_road_name(net_file, road_name)


# =============== SERVER STARTUP ===============

if __name__ == "__main__":
    # STDIO transport for local MCP client (recommended for AgentSUMO)
    # This allows local development without exposing to public internet
    mcp.run(transport="stdio")
    
    # Note: SSE transport for MCP Connector requires public URL
    # mcp.run(transport="sse")  # Runs on default port (usually 8000)
