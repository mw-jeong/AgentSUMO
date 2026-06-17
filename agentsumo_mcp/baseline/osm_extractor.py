"""
OSM data extraction functionality for SUMO MCP Server.

Extracts OpenStreetMap road network data for a given area using:
1. Local .pbf file + osmium (fast, preferred when PBF is present)
2. Direct HTTP via Overpass interpreter (online fallback, replaces osmGet.py)
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

from agentsumo_mcp.settings.settings import sumo_environment, network_settings
from agentsumo_mcp.utils.path_utils import get_output_path
from agentsumo_mcp.baseline.osm_http import (
    extract_osm_via_http,
    download_pbf_for_region,
    identify_region,
)

logger = logging.getLogger("agentsumo_mcp.osm_extractor")


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
        Extract OSM data using three-stage fallback chain:
          1. Overpass HTTP — fast for small/medium bbox, no local data required.
          2. Local PBF cache + osmium — if HTTP fails and PBF already on disk.
          3. Download Geofabrik PBF + osmium — last resort, large one-time fetch.
        """
        logger.info("Starting OSM data extraction...")

        # Stage 1: Overpass HTTP
        try:
            logger.info("Stage 1/3: Overpass interpreter (HTTP)")
            return extract_osm_via_http(bbox, tag, output_path)
        except Exception as e:
            logger.warning(f"Overpass HTTP failed: {e}. Trying local PBF...")

        # Stage 2: Local PBF (cached)
        pbf_file = self._find_local_pbf(bbox)
        if pbf_file:
            logger.info(f"Stage 2/3: Local PBF + osmium ({Path(pbf_file).name})")
            try:
                return self._extract_with_osmium(bbox, pbf_file, tag, output_path)
            except Exception as e:
                logger.warning(f"osmium on cached PBF failed: {e}. "
                               f"Trying Geofabrik download...")
        else:
            logger.info("Stage 2/3: no cached PBF found; proceeding to download.")

        # Stage 3: Download PBF from Geofabrik
        if identify_region(bbox) is None:
            raise RuntimeError(
                f"OSM extraction failed. Overpass unavailable and bbox center "
                f"is not covered by any known Geofabrik region "
                f"(supported regions in osm_http.REGIONS)."
            )

        try:
            logger.info("Stage 3/3: Geofabrik PBF download + osmium")
            downloaded_pbf = download_pbf_for_region(bbox)
            return self._extract_with_osmium(bbox, str(downloaded_pbf), tag, output_path)
        except Exception as e:
            logger.error(f"Geofabrik download path failed: {e}")
            raise RuntimeError(
                "OSM extraction failed across all three stages "
                "(Overpass HTTP, local PBF, Geofabrik download)."
            ) from e

    def _find_local_pbf(self, bbox: List[float]) -> Optional[str]:
        """
        Look up a cached Geofabrik PBF that covers bbox.

        Search order:
          1. default_data_dir() — primary cache (~/.agentsumo/data/ or
             $AGENTSUMO_DATA_DIR). This is where Stage 3 downloads are saved,
             so cache hits are stable across sessions and reused on later runs.
          2. BASE_DIR/data — repo-relative fallback. Lets developers and
             existing local installs reuse PBFs they already keep with the
             source tree without copying them.

        Region identification is delegated to osm_http.identify_region so the
        single REGIONS table is the only place to add new countries/states.
        """
        from agentsumo_mcp.baseline.osm_http import default_data_dir

        region = identify_region(bbox)
        if region is None:
            logger.info(
                "No PBF region covers this bbox (Stage 3 download will not be "
                "possible if Overpass also fails)."
            )
            return None

        filename = f"{region['name']}-latest.osm.pbf"

        primary = default_data_dir() / filename
        if primary.exists():
            logger.info(f"PBF cache hit (user dir): {primary}")
            return str(primary)

        legacy = self.environment.BASE_DIR / "data" / filename
        if legacy.exists():
            logger.info(f"PBF cache hit (repo-relative): {legacy}")
            return str(legacy)

        logger.info(
            f"No cached PBF for region '{region['name']}' "
            f"(checked {primary} and {legacy})."
        )
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

