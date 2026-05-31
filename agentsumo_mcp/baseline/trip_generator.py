"""
Trip generation functionality for SUMO MCP Server.

Generates trip demand (trips.xml) from OD data.
Route assignment (duarouter) is handled separately by RouteGenerator.
"""

import subprocess
import xml.etree.ElementTree as ET
import collections
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
import sumolib

from agentsumo_mcp.settings.settings import sumo_environment, simulation_settings
from agentsumo_mcp.utils.path_utils import get_output_path, get_working_directory


# Default column mappings for backward compatibility
DEFAULT_COORDINATE_MAPPING = {
    "O_lon": "O_lon",
    "O_lat": "O_lat",
    "D_lon": "D_lon",
    "D_lat": "D_lat",
    "O_time_relative": "O_time_relative"
}

DEFAULT_ZONE_MAPPING = {
    "zone_O": "h3_lv9_O",
    "zone_D": "h3_lv9_D",
    "O_time_relative": "O_time_relative",
    "zone_id_column": "h3_indx"
}


class TripGenerator:
    """Trip demand generation for SUMO simulations."""

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
        column_mapping: Optional[Dict[str, str]] = None,
        output_dir: str = "output/trips"
    ) -> Dict[str, Any]:
        """
        Generate trip demand for SUMO simulation.

        Args:
            trip_type: "RandomOD" or "RealOD"
            net_file: Network file path (.net.xml)
            od_type: "coordinate" or "zone" (for RealOD)
            od_data_file: OD CSV file path
            zone_shp_file: Zone shapefile path (for zone OD)
            traffic_condition: "light", "medium", or "heavy" (for RandomOD)
            column_mapping: Column name mapping for non-standard CSV files
            output_dir: Output directory

        Returns:
            Dict with trip_file path and trip_count
        """
        try:
            if trip_type not in ["RandomOD", "RealOD"]:
                return {
                    "status": "error",
                    "message": f"Invalid trip_type: {trip_type}. Must be 'RandomOD' or 'RealOD'"
                }

            base_dir = get_working_directory()
            output_path = get_output_path(output_dir)

            if not Path(net_file).is_absolute():
                net_file = str(base_dir / net_file)

            tag = Path(net_file).stem
            trip_file = str(output_path / f"{tag}.trips.xml")
            trip_count = 0

            if trip_type == "RandomOD":
                trip_count = self._generate_random_od(
                    net_file, trip_file, traffic_condition
                )
            elif trip_type == "RealOD" and od_type == "zone":
                trip_count = self._generate_real_od_zone(
                    net_file, trip_file, zone_shp_file, od_data_file,
                    output_path, tag, column_mapping
                )
            elif trip_type == "RealOD" and od_type == "coordinate":
                trip_count = self._generate_real_od_coordinate(
                    net_file, trip_file, od_data_file, column_mapping
                )
            else:
                return {
                    "status": "error",
                    "message": "Invalid parameters. RealOD requires od_type='coordinate' or 'zone'."
                }

            return {
                "status": "success",
                "trip_file": trip_file,
                "message": f"Successfully generated {trip_count} trips",
                "trip_count": trip_count,
                "metadata": {
                    "working_directory": str(base_dir),
                    "absolute_trip_file": str(Path(trip_file).absolute())
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Trip generation failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }

    def _generate_random_od(self, net_file: str, trip_file: str, traffic_condition: str) -> int:
        """Generate random OD trips using SUMO's randomTrips.py."""
        if not traffic_condition:
            raise ValueError("traffic_condition is required for RandomOD")

        net = sumolib.net.readNet(net_file)
        edge_count = len(net.getEdges())

        ratio = self.sim_settings.TRAFFIC_RATIOS.get(traffic_condition, 1.0)
        vehicle_count = int(edge_count * ratio)

        begin, end = self.sim_settings.DEFAULT_BEGIN_TIME, self.sim_settings.DEFAULT_END_TIME
        period = (end - begin) / vehicle_count

        randomTrips_path = self.environment.get_tool_path("randomTrips.py")
        net_file_abs = str(Path(net_file).absolute())
        trip_file_abs = str(Path(trip_file).absolute())
        temp_route_file = str(Path(trip_file).parent / "temp_validate.rou.xml")

        randomTrips_cmd = [
            "python", randomTrips_path,
            "-n", net_file_abs,
            "-o", trip_file_abs,
            "--begin", str(begin),
            "--end", str(end),
            "--period", str(period),
            "--validate",
            "--route-file", temp_route_file,
            "--seed", str(self.sim_settings.DEFAULT_SEED),
            "--trip-attributes",
            'type="passenger" departLane="free" departSpeed="random" departPos="random_free"'
        ]

        result = subprocess.run(randomTrips_cmd, capture_output=True, text=True, check=False)

        temp_route_path = Path(temp_route_file)
        if temp_route_path.exists():
            temp_route_path.unlink()

        if not Path(trip_file).exists():
            raise RuntimeError(f"Trip file was not created. Command output: {result.stderr}")

        tree = ET.parse(trip_file)
        return len(tree.getroot().findall(".//trip"))

    def _generate_real_od_zone(
        self, net_file: str, trip_file: str, zone_shp_file: str,
        od_data_file: str, output_path: Path, tag: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> int:
        """Generate real OD trips from zone data (shapefile + CSV)."""
        mapping = column_mapping or {}
        id_column = mapping.get("zone_id_column", DEFAULT_ZONE_MAPPING["zone_id_column"])

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
        self._create_taz_relation(od_data_file, taz_path, tazRelation_path, column_mapping)

        # 4. od2trips
        od2trips_path = self.environment.get_binary_path("od2trips")
        subprocess.run([
            od2trips_path,
            "--taz-files", taz_path,
            "--tazrelation-files", tazRelation_path,
            "-o", trip_file,
            "--vtype", "passenger"
        ], check=True, capture_output=True)

        tree = ET.parse(trip_file)
        return len(tree.getroot().findall(".//trip"))

    def _generate_real_od_coordinate(
        self, net_file: str, trip_file: str, od_data_file: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> int:
        """Generate real OD trips from coordinate data with column mapping support."""
        df = pd.read_csv(od_data_file)
        net = sumolib.net.readNet(net_file)

        mapping = column_mapping or {}
        o_lon_col = mapping.get("O_lon", DEFAULT_COORDINATE_MAPPING["O_lon"])
        o_lat_col = mapping.get("O_lat", DEFAULT_COORDINATE_MAPPING["O_lat"])
        d_lon_col = mapping.get("D_lon", DEFAULT_COORDINATE_MAPPING["D_lon"])
        d_lat_col = mapping.get("D_lat", DEFAULT_COORDINATE_MAPPING["D_lat"])
        time_col = mapping.get("O_time_relative", DEFAULT_COORDINATE_MAPPING["O_time_relative"])

        # Validate columns exist
        required = {
            "O_lon": o_lon_col, "O_lat": o_lat_col,
            "D_lon": d_lon_col, "D_lat": d_lat_col,
            "O_time_relative": time_col
        }
        for key, col in required.items():
            if col not in df.columns:
                raise ValueError(
                    f"Column '{col}' (mapped from '{key}') not found in CSV. "
                    f"Available: {list(df.columns)}"
                )

        df = df.sort_values(by=time_col)

        def get_edge(lon, lat):
            try:
                x, y = net.convertLonLat2XY(lon, lat)
                edges = net.getNeighboringEdges(x, y, 1000)
                if edges:
                    return min(edges, key=lambda e: e[1])[0].getID()
            except Exception:
                return None

        with open(trip_file, "w") as f:
            f.write('<routes>\n')
            for idx, row in df.iterrows():
                from_edge = get_edge(row[o_lon_col], row[o_lat_col])
                to_edge = get_edge(row[d_lon_col], row[d_lat_col])
                if from_edge and to_edge:
                    depart = int(row[time_col])
                    f.write(f'  <trip id="{idx}" depart="{depart}" from="{from_edge}" to="{to_edge}"/>\n')
            f.write('</routes>\n')

        tree = ET.parse(trip_file)
        return len(tree.getroot().findall(".//trip"))

    def _create_taz_relation(
        self, od_data_file: str, taz_file: str, tazRelation_path: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> None:
        """Create tazRelation.xml from OD data with column mapping support."""
        df = pd.read_csv(od_data_file)

        mapping = column_mapping or {}
        zone_o_col = mapping.get("zone_O", DEFAULT_ZONE_MAPPING["zone_O"])
        zone_d_col = mapping.get("zone_D", DEFAULT_ZONE_MAPPING["zone_D"])
        time_col = mapping.get("O_time_relative", DEFAULT_ZONE_MAPPING["O_time_relative"])

        tree = ET.parse(taz_file)
        root = tree.getroot()
        valid_ids = {t.attrib["id"] for t in root.findall("taz")}

        interval_sec = 3600
        intervals = collections.defaultdict(lambda: collections.defaultdict(int))

        for _, row in df.iterrows():
            try:
                t = int(row[time_col])
                o = row[zone_o_col]
                d = row[zone_d_col]
                if o not in valid_ids or d not in valid_ids:
                    continue
                start = (t // interval_sec) * interval_sec
                end = start + interval_sec
                intervals[(start, end)][(o, d)] += 1
            except Exception:
                continue

        root_xml = ET.Element("data")
        for idx, ((start, end), od_dict) in enumerate(sorted(intervals.items())):
            int_el = ET.SubElement(root_xml, "interval", id=str(idx), begin=str(start), end=str(end))
            for (o, d), c in od_dict.items():
                ET.SubElement(int_el, "tazRelation", **{"from": o, "to": d, "count": str(c)})

        ET.ElementTree(root_xml).write(tazRelation_path, encoding="utf-8", xml_declaration=True)
