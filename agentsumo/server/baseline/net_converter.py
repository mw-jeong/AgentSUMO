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

from agentsumo.server.settings.settings import sumo_environment, network_settings
from agentsumo.server.utils.path_utils import get_output_path

logger = logging.getLogger("agentsumo.server.net_converter")


class NetConverter:
    """Converts OSM data to SUMO network format."""

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

    def _run_netconvert(
        self, osm_file: str, net_file: str, bbox: Optional[List[float]] = None
    ) -> None:
        """Run SUMO netconvert to convert OSM → .net.xml."""
        netconvert_path = self.environment.get_binary_path("netconvert")
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
