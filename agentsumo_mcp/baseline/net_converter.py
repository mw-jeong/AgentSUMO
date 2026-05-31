"""
SUMO network conversion functionality.

Converts OSM (.osm) files to SUMO network (.net.xml) using netconvert.
"""

import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from agentsumo_mcp.settings.settings import sumo_environment, network_settings
from agentsumo_mcp.utils.path_utils import get_output_path

logger = logging.getLogger("agentsumo_mcp.net_converter")


class NetConverter:
    """Converts OSM data to SUMO network format."""

    # Bounding boxes for country-specific type file auto-detection
    # (min_lat, max_lat, min_lon, max_lon)
    COUNTRY_BBOX = {
        "kr": (33.0, 39.0, 124.0, 132.0),
    }
    # Country-specific type files (stored in settings directory)
    COUNTRY_TYPE_FILES = {
        "kr": "osmNetconvert_kr_urban.typ.xml",
    }

    def __init__(self):
        self.environment = sumo_environment
        self.network_settings = network_settings

    def convert(
        self,
        osm_file: str,
        city_en: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        output_dir: str = "output/networks"
    ) -> Dict[str, Any]:
        """
        Convert OSM file to SUMO network.

        Args:
            osm_file: Path to .osm file (from osm_extract)
            city_en: English name for output file naming (auto-derived from osm_file if omitted)
            bbox: Bounding box for boundary trimming [west, south, east, north]
            output_dir: Output directory

        Returns:
            Dict with net_file path
        """
        try:
            output_path = get_output_path(output_dir)

            # Determine output filename
            if city_en:
                tag = re.sub(r'[^a-zA-Z0-9]+', '_', city_en.strip().lower())
            else:
                tag = Path(osm_file).stem

            net_file = str(output_path / f"{tag}.net.xml")

            self._run_netconvert(osm_file, net_file, bbox)

            return {
                "status": "success",
                "net_file": net_file,
                "message": f"Successfully converted OSM to SUMO network: {tag}.net.xml"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Network conversion failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }

    def _detect_country(self, osm_file: str, bbox: Optional[List[float]] = None) -> Optional[str]:
        """Detect country from bbox or OSM file coordinates."""
        # Use provided bbox first
        if bbox:
            center_lat = (bbox[1] + bbox[3]) / 2
            center_lon = (bbox[0] + bbox[2]) / 2
            for country, (min_lat, max_lat, min_lon, max_lon) in self.COUNTRY_BBOX.items():
                if min_lat <= center_lat <= max_lat and min_lon <= center_lon <= max_lon:
                    return country
            return None

        # Fallback: read OSM file bounds
        try:
            import xml.etree.ElementTree as ET
            for event, elem in ET.iterparse(osm_file, events=("end",)):
                if elem.tag == "bounds":
                    min_lat = float(elem.get("minlat", 0))
                    max_lat = float(elem.get("maxlat", 0))
                    min_lon = float(elem.get("minlon", 0))
                    max_lon = float(elem.get("maxlon", 0))
                    center_lat = (min_lat + max_lat) / 2
                    center_lon = (min_lon + max_lon) / 2
                    for country, (c_min_lat, c_max_lat, c_min_lon, c_max_lon) in self.COUNTRY_BBOX.items():
                        if c_min_lat <= center_lat <= c_max_lat and c_min_lon <= center_lon <= c_max_lon:
                            return country
                    break
                elem.clear()
        except Exception as e:
            logger.warning(f"Failed to detect country from OSM file: {e}")
        return None

    def _run_netconvert(
        self, osm_file: str, net_file: str, bbox: Optional[List[float]] = None
    ) -> None:
        """Run SUMO netconvert to convert OSM → .net.xml."""
        netconvert_path = self.environment.get_binary_path("netconvert")

        # Auto-detect country and select type file
        country = self._detect_country(osm_file, bbox)
        if country and country in self.COUNTRY_TYPE_FILES:
            settings_dir = Path(__file__).parent.parent / "settings"
            type_files = str(settings_dir / self.COUNTRY_TYPE_FILES[country])
            logger.info(f"Detected country '{country}' — using {self.COUNTRY_TYPE_FILES[country]}")
        else:
            type_files = os.path.join(
                self.environment.SUMO_HOME, "share", "sumo", "data", "typemap",
                self.network_settings.TYPE_FILES
            )

        cmd = [
            netconvert_path,
            "--osm-files", osm_file,
            "--type-files", type_files,
            "-o", net_file
        ] + self.network_settings.NETCONVERT_OPTIONS

        if bbox:
            geo_boundary = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            cmd.extend(["--keep-edges.in-geo-boundary", geo_boundary])

        logger.info(f"Running netconvert: {Path(osm_file).name} → {Path(net_file).name}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=error_msg
            )

        logger.info(f"Network conversion complete: {Path(net_file).name}")
