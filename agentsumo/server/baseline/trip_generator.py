"""
Trip generation functionality for SUMO MCP Server.
"""

import subprocess
import xml.etree.ElementTree as ET
import collections
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
import sumolib

from agentsumo.server.settings.settings import sumo_environment, simulation_settings
from agentsumo.server.utils.path_utils import get_output_path, get_working_directory


class TripGenerator:
    """Trip generation class for SUMO simulations."""
    
    def __init__(self):
        self.environment = sumo_environment
        self.sim_settings = simulation_settings
    
    def generate(
        self,
        trip_type: str,
        net_file: str,
        od_type: Optional[str] = None,
        od_data_file: Optional[str] = None,
        zone_shp_file: Optional[str] = None,
        traffic_condition: Optional[str] = None,
        output_dir: str = "output/trips"
    ) -> Dict[str, Any]:
        """
        Generate trips for SUMO simulation.
        
        Args:
            trip_type: Trip generation type: RandomOD, RealOD
            net_file: Network file path (tag will be extracted from filename)
            od_type: OD type for RealOD: 'zone' or 'coordinate'
            od_data_file: OD data file path (RealOD-coordinate only)
            zone_shp_file: Zone shapefile path (RealOD-zone only)
            traffic_condition: Traffic intensity level (RandomOD only)
            output_dir: Output directory for trip files
            
        Returns:
            Dict[str, Any]: Generation result with status and metadata
        """
        try:
            # Input validation
            if trip_type not in ["RandomOD", "RealOD"]:
                return {
                    "status": "error",
                    "message": f"Invalid trip_type: {trip_type}. Must be one of: RandomOD, RealOD"
                }
            
            # Setup working directory and paths
            base_dir = get_working_directory()
            output_path = get_output_path(output_dir)
            
            if not Path(net_file).is_absolute():
                net_file = str(base_dir / net_file)
            
            # Generate file tag from net_file (extract from network filename)
            tag = Path(net_file).stem
            
            trip_file = str(output_path / f"{tag}.trips.xml")
            route_file = str(output_path / f"{tag}.rou.xml")
            trip_count = 0
            
            # Generate trips based on type
            if trip_type == "RandomOD":
                trip_count = self._generate_random_od(
                    net_file, trip_file, traffic_condition
                )
            elif trip_type == "RealOD" and od_type == "zone":
                trip_count = self._generate_real_od_zone(
                    net_file, trip_file, zone_shp_file, od_data_file, output_path, tag
                )
            elif trip_type == "RealOD" and od_type == "coordinate":
                trip_count = self._generate_real_od_coordinate(
                    net_file, trip_file, od_data_file
                )
            else:
                return {
                    "status": "error",
                    "message": "입력 파라미터가 부족하거나 올바르지 않습니다."
                }
            
            # Generate routes using duarouter
            self._generate_routes(net_file, trip_file, route_file)
            
            return {
                "status": "success",
                "trip_file": trip_file,
                "route_file": route_file,
                "message": f"Successfully generated {trip_count} trips",
                "trip_count": trip_count,
                "metadata": {
                    "working_directory": str(base_dir),
                    "absolute_trip_file": str(Path(trip_file).absolute()),
                    "absolute_route_file": str(Path(route_file).absolute())
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Trip generation failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }
    
    def _generate_random_od(self, net_file: str, trip_file: str, traffic_condition: str) -> int:
        """Generate random OD trips."""
        if not traffic_condition:
            raise ValueError("traffic_condition이 필요합니다.")
        
        # Calculate vehicle count based on network size
        net = sumolib.net.readNet(net_file)
        edge_count = len(net.getEdges())
        
        ratio = self.sim_settings.TRAFFIC_RATIOS.get(traffic_condition, 1.0)
        vehicle_count = int(edge_count * ratio)
        
        begin, end = self.sim_settings.DEFAULT_BEGIN_TIME, self.sim_settings.DEFAULT_END_TIME
        period = (end - begin) / vehicle_count
        
        # Run randomTrips.py
        # Note: Use absolute paths and specify --route-file to avoid stray files
        randomTrips_path = self.environment.get_tool_path("randomTrips.py")
        net_file_abs = str(Path(net_file).absolute())
        trip_file_abs = str(Path(trip_file).absolute())

        # Create a temp route file path in the same directory as trip_file
        temp_route_file = str(Path(trip_file).parent / "temp_validate.rou.xml")

        randomTrips_cmd = [
            "python", randomTrips_path,
            "-n", net_file_abs,
            "-o", trip_file_abs,
            "--begin", str(begin),
            "--end", str(end),
            "--period", str(period),
            "--validate",
            "--route-file", temp_route_file,  # Explicit route file to avoid stray files
            "--seed", str(self.sim_settings.DEFAULT_SEED),
            "--trip-attributes", 'type="passenger" departLane="free" departSpeed="random" departPos="random_free"'
        ]

        result = subprocess.run(
            randomTrips_cmd,
            capture_output=True,
            text=True,
            check=False
        )

        # Clean up temp route file (we'll generate proper routes later with duarouter)
        temp_route_path = Path(temp_route_file)
        if temp_route_path.exists():
            temp_route_path.unlink()
        
        if not Path(trip_file).exists():
            raise RuntimeError(f"Trip file was not created. Command output: {result.stderr}")
        
        # Count trips
        tree = ET.parse(trip_file)
        root = tree.getroot()
        return len(root.findall(".//trip"))
    
    def _generate_real_od_zone(
        self, net_file: str, trip_file: str, zone_shp_file: str, 
        od_data_file: str, output_path: Path, tag: str
    ) -> int:
        """Generate real OD trips from zone data."""
        id_column = "h3_indx"
        poly_path = str(output_path / f"{tag}.poly.xml")
        taz_path = str(output_path / f"{tag}.taz.xml")
        tazRelation_path = str(output_path / f"{tag}.tazRelation.xml")
        
        # 1. polyconvert (shp → poly.xml)
        polyconvert_path = self.environment.get_binary_path("polyconvert")
        subprocess.run([
            polyconvert_path,
            "-n", net_file,
            "--shapefile", zone_shp_file[:-4] if zone_shp_file.endswith('.shp') else zone_shp_file,
            "--shapefile.id-column", id_column,
            "--type", "taz",
            "--proj.utm", "true",
            "-o", poly_path
        ], check=True, capture_output=True)
        
        # 2. edgesInDistricts (poly.xml → taz.xml)
        edgesInDistricts_path = self.environment.get_tool_path("edgesInDistricts.py")
        subprocess.run([
            edgesInDistricts_path,
            "-n", net_file,
            "-t", poly_path,
            "-o", taz_path
        ], check=True, capture_output=True)
        
        # 3. Create tazRelation.xml from OD data
        self._create_taz_relation(od_data_file, taz_path, tazRelation_path)
        
        # 4. od2trips
        od2trips_path = self.environment.get_binary_path("od2trips")
        subprocess.run([
            od2trips_path,
            "--taz-files", taz_path,
            "--tazrelation-files", tazRelation_path,
            "-o", trip_file,
            "--vtype", "passenger"
        ], check=True, capture_output=True)
        
        # Count trips
        tree = ET.parse(trip_file)
        root = tree.getroot()
        return len(root.findall(".//trip"))
    
    def _generate_real_od_coordinate(self, net_file: str, trip_file: str, od_data_file: str) -> int:
        """Generate real OD trips from coordinate data."""
        df = pd.read_csv(od_data_file)
        net = sumolib.net.readNet(net_file)
        df = df.sort_values(by="O_time_relative")
        
        def get_edge(lon, lat):
            try:
                x, y = net.convertLonLat2XY(lon, lat)
                edges = net.getNeighboringEdges(x, y, 1000)
                if edges:
                    return min(edges, key=lambda x: x[1])[0].getID()
            except:
                return None
        
        with open(trip_file, "w") as f:
            f.write('<routes>\n')
            for idx, row in df.iterrows():
                from_edge = get_edge(row["O_lon"], row["O_lat"])
                to_edge = get_edge(row["D_lon"], row["D_lat"])
                if from_edge and to_edge:
                    trip = f'  <trip id="{idx}" depart="{int(row["O_time_relative"])}" from="{from_edge}" to="{to_edge}"/>\n'
                    f.write(trip)
            f.write('</routes>\n')
        
        tree = ET.parse(trip_file)
        root = tree.getroot()
        return len(root.findall(".//trip"))
    
    
    def _create_taz_relation(self, od_data_file: str, taz_file: str, tazRelation_path: str) -> None:
        """Create tazRelation.xml from OD data."""
        df = pd.read_csv(od_data_file)
        tree = ET.parse(taz_file)
        root = tree.getroot()
        valid_ids = {t.attrib["id"] for t in root.findall("taz")}
        interval_sec = 3600
        intervals = collections.defaultdict(lambda: collections.defaultdict(int))
        
        for _, row in df.iterrows():
            try:
                t = int(row["O_time_relative"])
                o = row["h3_lv9_O"]
                d = row["h3_lv9_D"]
                if o not in valid_ids or d not in valid_ids:
                    continue
                start = (t // interval_sec) * interval_sec
                end = start + interval_sec
                intervals[(start, end)][(o, d)] += 1
            except:
                continue
        
        root_xml = ET.Element("data")
        for idx, ((start, end), od_dict) in enumerate(sorted(intervals.items())):
            int_el = ET.SubElement(root_xml, "interval", id=str(idx), begin=str(start), end=str(end))
            for (o, d), c in od_dict.items():
                ET.SubElement(int_el, "tazRelation", **{"from": o, "to": d, "count": str(c)})
        
        ET.ElementTree(root_xml).write(tazRelation_path, encoding="utf-8", xml_declaration=True)
    
    
    def _generate_routes(self, net_file: str, trip_file: str, route_file: str) -> None:
        """Generate routes using duarouter."""
        duarouter_path = self.environment.get_binary_path("duarouter")
        
        # Ensure absolute paths for all files
        net_file_abs = str(Path(net_file).absolute())
        trip_file_abs = str(Path(trip_file).absolute())
        route_file_abs = str(Path(route_file).absolute())
        
        subprocess.run([
            duarouter_path,
            "-n", net_file_abs,
            "-t", trip_file_abs,
            "-o", route_file_abs,
            "--ignore-errors"
        ], check=True, capture_output=True)
