"""
Network generation functionality for SUMO MCP Server.
"""

import os 
import subprocess 
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd
import geopandas as gpd
from shapely.ops import unary_union
from geopy.geocoders import Nominatim
from geopy.geocoders import GoogleV3
from geopy.distance import distance
import re
import logging

from agentsumo.server.settings.settings import sumo_environment, network_settings
from agentsumo.server.utils.path_utils import get_output_path


logger = logging.getLogger("agentsumo.server.network_generator")


class NetworkGenerator:
    """Network generation class for SUMO networks."""
    
    def __init__(self):
        self.environment = sumo_environment
        self.network_settings = network_settings
    
    def generate(
        self,
        city: Optional[str] = None,
        city_en: Optional[str] = None,
        radius: Optional[float] = None,
        bbox: Optional[List[float]] = None,
        trip_type: str = "",
        od_type: Optional[str] = None,
        od_data_file: Optional[str] = None,
        zone_shp_file: Optional[str] = None,
        output_dir: str = "output/networks",
        split_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a SUMO network for traffic simulation.

        Args:
            city: Target city name for geocoding (RandomOD only)
            city_en: English city name for file naming (e.g., 'Gangnam Station')
            radius: Simulation radius in kilometers (RandomOD only), not meters.
            bbox: Direct bounding box [west, south, east, north] (takes priority over city+radius)
            trip_type: Trip generation type: RandomOD, RealOD
            od_type: OD type for RealOD: 'zone' or 'coordinate'
            od_data_file: OD data file path (RealOD-coordinate only)
            zone_shp_file: Zone shapefile path (RealOD-zone only)
            output_dir: Output directory for network files
            split_id: Split identifier for batch simulation (e.g., 'zone1', 'hour_07', 'zone1_hour_07')

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
            
            if trip_type == "RealOD" and od_type not in ["zone", "coordinate"]:
                return {
                    "status": "error", 
                    "message": "od_type must be 'zone' or 'coordinate' for RealOD"
                }
            
            # Setup output directory
            output_path = get_output_path(output_dir)
            
            # Auto-extract split_id from od_data_file if not provided
            if not split_id and od_data_file:
                split_id = self._extract_split_id_from_od_file(od_data_file)
            
            # Generate file tag (prioritize split_id for batch simulation)
            tag = self._get_file_tag(city_en, city, split_id)
            net_file = str(output_path / f"{tag}.net.xml")
            metadata = {}
            
            # Get bounding box based on trip type (direct bbox takes priority)
            if bbox and len(bbox) == 4:
                logger.info(f"Using direct bbox: {bbox}")
                actual_bbox = bbox
            else:
                actual_bbox = self._get_bounding_box(
                    trip_type, city, radius, od_type, od_data_file, zone_shp_file
                )
            bbox = actual_bbox
            
            # Extract OSM data
            osm_extract = self._extract_osm_data(bbox, tag, output_path)
            
            # Convert to SUMO network (pass bbox for boundary trimming)
            self._convert_to_network(osm_extract, net_file, bbox)
            
            metadata["bbox"] = bbox
            metadata["osm_file"] = osm_extract
            
            return {
                "status": "success",
                "net_file": net_file,
                "message": f"Successfully generated network for {tag}",
                "metadata": metadata
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Network generation failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }
    
    def _extract_split_id_from_od_file(self, od_data_file: str) -> Optional[str]:
        """Intelligently extract split_id from OD data file using multiple strategies."""
        try:
            filename = Path(od_data_file).stem
            
            # Strategy 1: Filename pattern matching
            patterns = [
                r'(zone\d+)_hour_(\d+)',  # zone1_hour_07 → zone1_hour_07
                r'(zone\d+)',              # zone1 → zone1
                r'(hour_\d+)',             # hour_07 → hour_07
                r'(\w+)_OD',               # any_prefix_OD → any_prefix
                r'(\w+)_od'                # any_prefix_od → any_prefix
            ]
            
            for pattern in patterns:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 1:
                        return match.group(1)
                    elif len(match.groups()) == 2:
                        return f"{match.group(1)}_hour_{match.group(2)}"
            
            # Strategy 2: Check if file contains zone information
            try:
                import pandas as pd
                df = pd.read_csv(od_data_file, nrows=5)  # Read only first 5 rows for efficiency
                
                # Look for zone column
                zone_columns = [col for col in df.columns if 'zone' in col.lower()]
                if zone_columns:
                    unique_zones = df[zone_columns[0]].unique()
                    if len(unique_zones) == 1:
                        return f"zone{unique_zones[0]}"
                
                # Look for hour information in time column
                time_columns = [col for col in df.columns if 'time' in col.lower() or 'hour' in col.lower()]
                if time_columns:
                    df[time_columns[0]] = pd.to_datetime(df[time_columns[0]])
                    unique_hours = df[time_columns[0]].dt.hour.unique()
                    if len(unique_hours) == 1:
                        return f"hour_{unique_hours[0]:02d}"
                        
            except Exception:
                pass  # If CSV reading fails, continue to next strategy
            
            # Strategy 3: Use filename as fallback (but validate it's meaningful)
            fallback = filename.replace('_OD', '').replace('_od', '').strip()
            # Only return if it's meaningful (not empty or just underscores)
            if fallback and fallback.replace('_', ''):
                return fallback
            return None
            
        except Exception:
            return None
    
    def _get_file_tag(self, city_en: Optional[str], city: Optional[str], split_id: Optional[str] = None) -> str:
        """
        Generate file tag from split_id (batch simulation) or city names (single simulation).
        
        Validates that the tag is meaningful (not just '_' or empty).
        """
        def is_valid_tag(tag: str) -> bool:
            """Check if tag is meaningful (not just underscores or empty)."""
            if not tag or not tag.strip():
                return False
            # Remove all underscores and check if anything remains
            cleaned = tag.replace('_', '').strip()
            return len(cleaned) > 0
        
        # Prioritize split_id for batch simulation
        if split_id and isinstance(split_id, str) and split_id.strip():
            tag = re.sub(r'[^a-zA-Z0-9]+', '_', split_id.strip().lower())
            if is_valid_tag(tag):
                return tag
                
        if city_en and isinstance(city_en, str) and city_en.strip():
            tag = re.sub(r'[^a-zA-Z0-9]+', '_', city_en.strip().lower())
            if is_valid_tag(tag):
                return tag
                
        if city and isinstance(city, str) and city.strip():
            tag = re.sub(r'[^a-zA-Z0-9]+', '_', city.strip().lower())
            if is_valid_tag(tag):
                return tag
        
        # Provide clear error message
        raise ValueError(
            f"유효한 city 정보가 필요합니다. "
            f"제공된 값: city='{city}', city_en='{city_en}', split_id='{split_id}'. "
            f"예: city='Gangnam Station' 또는 city_en='gangnam_station'"
        )
    
    def _get_bounding_box(
        self,
        trip_type: str,
        city: Optional[str],
        radius: Optional[float],
        od_type: Optional[str],
        od_data_file: Optional[str],
        zone_shp_file: Optional[str]
    ) -> List[float]:
        """Get bounding box based on trip type."""
        
        if trip_type == "RandomOD":
            return self._get_bbox_from_city(city, radius)
        elif trip_type == "RealOD" and od_type == "zone" and zone_shp_file:
            return self._get_bbox_from_shapefile(zone_shp_file)
        elif trip_type == "RealOD" and od_type == "coordinate" and od_data_file:
            return self._get_bbox_from_od_data(od_data_file)
        else:
            raise ValueError("입력 파라미터가 부족하거나 올바르지 않습니다.")
    
    def _get_bbox_from_city(self, city: str, radius: float) -> List[float]:
        """Get bounding box from city name and radius."""
        geolocator = Nominatim(user_agent="agent-sumo")
        location = geolocator.geocode(city, exactly_one=True)
        # geolocator = GoogleV3(api_key="")
        # location = geolocator.geocode(city)
        if not location:
            raise ValueError(f"도시명 위치를 찾을 수 없습니다: {city}")
        
        center_lat, center_lon = location.latitude, location.longitude

        # bearing=45/225 (diagonal), which made radius mean diagonal distance
        north = distance(kilometers=radius).destination((center_lat, center_lon), bearing=45).latitude
        south = distance(kilometers=radius).destination((center_lat, center_lon), bearing=225).latitude
        east = distance(kilometers=radius).destination((center_lat, center_lon), bearing=45).longitude
        west = distance(kilometers=radius).destination((center_lat, center_lon), bearing=225).longitude
        
        # # bearing: 0=North, 90=East, 180=South, 270=West
        # north = distance(kilometers=radius).destination((center_lat, center_lon), bearing=0).latitude
        # south = distance(kilometers=radius).destination((center_lat, center_lon), bearing=180).latitude
        # east = distance(kilometers=radius).destination((center_lat, center_lon), bearing=90).longitude
        # west = distance(kilometers=radius).destination((center_lat, center_lon), bearing=270).longitude
        
        return [west, south, east, north]
    
    def _get_bbox_from_shapefile(self, zone_shp_file: str) -> List[float]:
        """Get bounding box from shapefile."""
        gdf = gpd.read_file(zone_shp_file)
        return list(unary_union(gdf.geometry).bounds)  # (minx, miny, maxx, maxy)
    
    def _get_bbox_from_od_data(self, od_data_file: str) -> List[float]:
        """Get bounding box from OD data coordinates."""
        df = pd.read_csv(od_data_file)
        
        # Find coordinate columns
        lon_cols = [col for col in df.columns if col in ['O_lon', 'D_lon']]
        lat_cols = [col for col in df.columns if col in ['O_lat', 'D_lat']]
        
        if not lon_cols or not lat_cols:
            raise ValueError("OD 데이터에 'O_lon', 'D_lon', 'O_lat', 'D_lat' 컬럼이 필요합니다.")
        
        min_lon = df[lon_cols].min().min()
        max_lon = df[lon_cols].max().max()
        min_lat = df[lat_cols].min().min()
        max_lat = df[lat_cols].max().max()
        
        buffer = 0.003
        return [
            round(min_lon - buffer, 6),
            round(min_lat - buffer, 6),
            round(max_lon + buffer, 6),
            round(max_lat + buffer, 6)
        ]
    
    def _extract_osm_data(self, bbox: List[float], tag: str, output_path: Path) -> str:
        """
        Hybrid OSM data extraction
        
        Strategy:
        1. Try osmium with local .pbf (fast, if available)
        2. Fallback to osmGet.py (slow, but universal)
        3. Raise error if both fail
        """
        logger.info("OSM 데이터 추출 시작...")
        
        # Step 1: 로컬 .pbf 파일 찾기
        pbf_file = self._find_local_pbf(bbox)
        
        if pbf_file:
            logger.info(f"✅ 로컬 .pbf 파일 발견: {Path(pbf_file).name}")
            try:
                return self._extract_with_osmium(bbox, pbf_file, tag, output_path)
            except Exception as e:
                logger.warning(f"osmium 실패: {e}. osmGet.py로 시도...")
        
        # Step 2: osmGet.py fallback
        logger.info("온라인 다운로드 시도 (osmGet.py)...")
        try:
            return self._extract_with_osmget(bbox, tag, output_path)
        except Exception as e:
            logger.error(f"osmGet.py도 실패: {e}")
            raise RuntimeError(
                "OSM 데이터 추출 실패. osmium 또는 osmGet.py를 확인하세요."
            ) from e
    
    def _find_local_pbf(self, bbox: List[float]) -> Optional[str]:
        """
        Bounding box에 해당하는 로컬 .pbf 파일 찾기
        
        Args:
            bbox: [west, south, east, north]
            
        Returns:
            str: .pbf 파일 경로 (없으면 None)
        """
        # bbox 중심점 계산
        center_lon = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2
        
        data_dir = self.environment.BASE_DIR / "data"
        
        # 지역별 .pbf 파일 매칭
        # 한국 (126.9~129.6°E, 33.1~38.6°N)
        if 33 < center_lat < 39 and 124 < center_lon < 132:
            pbf = data_dir / "south-korea-latest.osm.pbf"
            if pbf.exists():
                logger.info("🇰🇷 한국 OSM 데이터 사용")
                return str(pbf)
        
        # 뉴욕 (40.5~41.0°N, -74.3~-73.7°E)
        elif 40 < center_lat < 41.5 and -75 < center_lon < -73:
            pbf = data_dir / "new-york-latest.osm.pbf"
            if pbf.exists():
                logger.info("🇺🇸 뉴욕 OSM 데이터 사용")
                return str(pbf)
        
        # 일본 (추가 가능)
        # elif 30 < center_lat < 46 and 128 < center_lon < 146:
        #     pbf = data_dir / "japan-latest.osm.pbf"
        
        logger.info("로컬 .pbf 파일 없음 (온라인 다운로드 필요)")
        return None
    
    def _extract_with_osmium(self, bbox: List[float], pbf_file: str, tag: str, output_path: Path) -> str:
        """
        osmium으로 OSM 데이터 추출 (빠름)
        
        Args:
            bbox: Bounding box
            pbf_file: 로컬 .pbf 파일 경로
            tag: 파일명 태그
            output_path: 출력 디렉토리
            
        Returns:
            str: 추출된 .osm 파일 경로
        """
        osm_file = output_path / f"{tag}.osm"
        
        logger.info(f"osmium extract 실행 중... (bbox: {bbox})")
        
        subprocess.run([
            "osmium", "extract",
            f"--bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            pbf_file,
            "-o", str(osm_file),
            "--overwrite"
        ], check=True, capture_output=True)
        
        logger.info(f"✅ OSM 추출 완료: {osm_file.name}")
        return str(osm_file)
    
    def _extract_with_osmget(self, bbox: List[float], tag: str, output_path: Path) -> str:
        """
        osmGet.py로 OSM 데이터 온라인 다운로드 (느림)
        
        Args:
            bbox: Bounding box
            tag: 파일명 태그
            output_path: 출력 디렉토리
            
        Returns:
            str: 다운로드된 .osm 파일 경로
        """
        osmget_path = self.environment.get_tool_path("osmGet.py")
        
        if not os.path.exists(osmget_path):
            raise FileNotFoundError(
                f"osmGet.py를 찾을 수 없습니다: {osmget_path}\n"
                f"SUMO_HOME이 올바르게 설정되었는지 확인하세요."
            )
        
        bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        
        logger.info(f"osmGet.py 다운로드 중... (시간이 걸릴 수 있습니다)")
        
        subprocess.run([
            "python3", osmget_path,
            f"--bbox={bbox_str}",
            "--prefix", tag,
            "--output-dir", str(output_path)
        ], check=True, capture_output=True)
        
        osm_file = output_path / f"{tag}_bbox.osm.xml"
        logger.info(f"✅ OSM 다운로드 완료: {osm_file.name}")
        
        return str(osm_file)
    
    def _convert_to_network(self, osm_file: str, net_file: str, bbox: Optional[List[float]] = None) -> None:
        """Convert OSM file to SUMO network.

        Args:
            osm_file: Path to OSM file
            net_file: Output network file path
            bbox: Bounding box [west, south, east, north] for trimming edges at boundary
        """
        netconvert_path = self.environment.get_binary_path("netconvert")
        type_files = os.path.join(
            self.environment.SUMO_HOME, "share", "sumo", "data", "typemap",
            self.network_settings.TYPE_FILES
        )

        netconvert_cmd = [
            netconvert_path,
            "--osm-files", osm_file,
            "--type-files", type_files,
            "-o", net_file
        ] + self.network_settings.NETCONVERT_OPTIONS

        # Add boundary trimming option if bbox is provided
        # This prevents roads from extending outside the specified area
        if bbox:
            geo_boundary = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            netconvert_cmd.extend(["--keep-edges.in-geo-boundary", geo_boundary])

        result = subprocess.run(netconvert_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout
            raise subprocess.CalledProcessError(
                result.returncode,
                netconvert_cmd,
                output=result.stdout,
                stderr=error_msg
            )
    
