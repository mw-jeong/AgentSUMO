"""
OSM data extraction functionality for SUMO MCP Server.

Extracts OpenStreetMap road network data for a given area using:
1. Local .pbf file + osmium (fast, preferred)
2. osmGet.py online download (fallback)
"""

import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd
import geopandas as gpd
from shapely.ops import unary_union
from geopy.geocoders import Nominatim
from geopy.distance import distance

from agentsumo.server.settings.settings import sumo_environment, network_settings
from agentsumo.server.utils.path_utils import get_output_path

logger = logging.getLogger("agentsumo.server.osm_extractor")


class OsmExtractor:
    """OSM data extraction from various input sources."""

    def __init__(self):
        self.environment = sumo_environment

    def extract(
        self,
        city_en: str,
        bbox: Optional[List[float]] = None,
        city: Optional[str] = None,
        radius: Optional[float] = None,
        od_data_file: Optional[str] = None,
        zone_shp_file: Optional[str] = None,
        column_mapping: Optional[Dict[str, str]] = None,
        output_dir: str = "output/networks"
    ) -> Dict[str, Any]:
        """
        Extract OSM data for a given area.

        Args:
            city_en: English name for file naming (e.g., "gangnam", "manhattan")
            bbox: Direct bounding box [west, south, east, north]
            city: City name for geocoding (e.g., "Gangnam Station")
            radius: Search radius in km (used with city)
            od_data_file: OD CSV file path (bbox auto-computed from coordinates)
            zone_shp_file: Zone shapefile path (bbox auto-computed from geometry)
            column_mapping: Column name mapping for non-standard CSV
            output_dir: Output directory

        Returns:
            Dict with osm_file, bbox, tag
        """
        try:
            output_path = get_output_path(output_dir)
            tag = self._sanitize_tag(city_en)

            actual_bbox = self._determine_bbox(
                bbox, city, radius, od_data_file, zone_shp_file, column_mapping
            )

            osm_file = self._extract_osm_data(actual_bbox, tag, output_path)

            return {
                "status": "success",
                "osm_file": osm_file,
                "bbox": actual_bbox,
                "tag": tag,
                "message": f"Successfully extracted OSM data for {tag}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"OSM extraction failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }

    def _sanitize_tag(self, city_en: str) -> str:
        """Generate safe file tag from city_en."""
        if not city_en or not city_en.strip():
            raise ValueError("city_en is required for file naming")
        tag = re.sub(r'[^a-zA-Z0-9]+', '_', city_en.strip().lower())
        if not tag.replace('_', ''):
            raise ValueError(f"Invalid city_en: '{city_en}'")
        return tag

    def _determine_bbox(
        self,
        bbox: Optional[List[float]],
        city: Optional[str],
        radius: Optional[float],
        od_data_file: Optional[str],
        zone_shp_file: Optional[str],
        column_mapping: Optional[Dict[str, str]]
    ) -> List[float]:
        """Determine bounding box from inputs (priority: bbox > od_data > shp > city+radius)."""
        if bbox and len(bbox) == 4:
            logger.info(f"Using direct bbox: {bbox}")
            return bbox
        if od_data_file:
            return self._get_bbox_from_od_data(od_data_file, column_mapping)
        if zone_shp_file:
            return self._get_bbox_from_shapefile(zone_shp_file)
        if city and radius:
            return self._get_bbox_from_city(city, radius)
        raise ValueError(
            "One of the following is required: bbox, od_data_file, zone_shp_file, or city+radius"
        )

    def _get_bbox_from_city(self, city: str, radius: float) -> List[float]:
        """Get bounding box from city name and radius (km)."""
        geolocator = Nominatim(user_agent="agent-sumo")
        location = geolocator.geocode(city, exactly_one=True)
        if not location:
            raise ValueError(f"Could not geocode city: {city}")

        center_lat, center_lon = location.latitude, location.longitude
        north = distance(kilometers=radius).destination((center_lat, center_lon), bearing=45).latitude
        south = distance(kilometers=radius).destination((center_lat, center_lon), bearing=225).latitude
        east = distance(kilometers=radius).destination((center_lat, center_lon), bearing=45).longitude
        west = distance(kilometers=radius).destination((center_lat, center_lon), bearing=225).longitude

        return [west, south, east, north]

    def _get_bbox_from_shapefile(self, zone_shp_file: str) -> List[float]:
        """Get bounding box from shapefile geometry."""
        gdf = gpd.read_file(zone_shp_file)
        return list(unary_union(gdf.geometry).bounds)

    def _get_bbox_from_od_data(
        self, od_data_file: str, column_mapping: Optional[Dict[str, str]] = None
    ) -> List[float]:
        """Get bounding box from OD coordinate data with column mapping support."""
        df = pd.read_csv(od_data_file)
        mapping = column_mapping or {}

        o_lon_col = mapping.get("O_lon", "O_lon")
        o_lat_col = mapping.get("O_lat", "O_lat")
        d_lon_col = mapping.get("D_lon", "D_lon")
        d_lat_col = mapping.get("D_lat", "D_lat")

        lon_cols = [o_lon_col, d_lon_col]
        lat_cols = [o_lat_col, d_lat_col]

        # Validate columns exist
        for col in lon_cols + lat_cols:
            if col not in df.columns:
                raise ValueError(
                    f"Column '{col}' not found in CSV. "
                    f"Available columns: {list(df.columns)}. "
                    f"Use column_mapping to specify correct column names."
                )

        min_lon = df[lon_cols].min().min()
        max_lon = df[lon_cols].max().max()
        min_lat = df[lat_cols].min().min()
        max_lat = df[lat_cols].max().max()

        buffer = network_settings.DEFAULT_BUFFER
        return [
            round(min_lon - buffer, 6),
            round(min_lat - buffer, 6),
            round(max_lon + buffer, 6),
            round(max_lat + buffer, 6)
        ]

    def _extract_osm_data(self, bbox: List[float], tag: str, output_path: Path) -> str:
        """
        Extract OSM data using hybrid strategy:
        1. Try osmium with local .pbf (fast)
        2. Fallback to osmGet.py (slow, universal)
        """
        logger.info("Starting OSM data extraction...")

        pbf_file = self._find_local_pbf(bbox)

        if pbf_file:
            logger.info(f"Local .pbf found: {Path(pbf_file).name}")
            try:
                return self._extract_with_osmium(bbox, pbf_file, tag, output_path)
            except Exception as e:
                logger.warning(f"osmium failed: {e}. Trying osmGet.py...")

        logger.info("Downloading from OSM API (osmGet.py)...")
        try:
            return self._extract_with_osmget(bbox, tag, output_path)
        except Exception as e:
            logger.error(f"osmGet.py also failed: {e}")
            raise RuntimeError("OSM extraction failed. Check osmium or osmGet.py.") from e

    def _find_local_pbf(self, bbox: List[float]) -> Optional[str]:
        """Find local .pbf file matching the bbox center."""
        center_lon = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2

        data_dir = self.environment.BASE_DIR.parent / "data"

        if 33 < center_lat < 39 and 124 < center_lon < 132:
            pbf = data_dir / "south-korea-latest.osm.pbf"
            if pbf.exists():
                logger.info("Using local Korea OSM data")
                return str(pbf)

        elif 40 < center_lat < 41.5 and -75 < center_lon < -73:
            pbf = data_dir / "new-york-latest.osm.pbf"
            if pbf.exists():
                logger.info("Using local New York OSM data")
                return str(pbf)

        logger.info("No local .pbf file found (online download needed)")
        return None

    def _extract_with_osmium(
        self, bbox: List[float], pbf_file: str, tag: str, output_path: Path
    ) -> str:
        """Extract OSM data from local .pbf using osmium (fast)."""
        osm_file = output_path / f"{tag}.osm"
        logger.info(f"Running osmium extract (bbox: {bbox})")

        subprocess.run([
            "osmium", "extract",
            f"--bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            pbf_file,
            "-o", str(osm_file),
            "--overwrite"
        ], check=True, capture_output=True)

        logger.info(f"OSM extraction complete: {osm_file.name}")
        return str(osm_file)

    def _extract_with_osmget(
        self, bbox: List[float], tag: str, output_path: Path
    ) -> str:
        """Download OSM data using osmGet.py (slow, universal fallback)."""
        osmget_path = self.environment.get_tool_path("osmGet.py")
        if not os.path.exists(osmget_path):
            raise FileNotFoundError(f"osmGet.py not found: {osmget_path}")

        bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        logger.info("Downloading via osmGet.py (this may take a while)...")

        subprocess.run([
            "python3", osmget_path,
            f"--bbox={bbox_str}",
            "--prefix", tag,
            "--output-dir", str(output_path)
        ], check=True, capture_output=True)

        osm_file = output_path / f"{tag}_bbox.osm.xml"
        logger.info(f"OSM download complete: {osm_file.name}")
        return str(osm_file)
