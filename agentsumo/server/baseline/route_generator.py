"""
Route generation functionality for SUMO MCP Server.

Converts trip files to route files using SUMO's duarouter.
"""

import logging
from pathlib import Path
from typing import Dict, Any
import subprocess

from agentsumo.server.settings.settings import sumo_environment
from agentsumo.server.utils.path_utils import get_output_path, get_working_directory

logger = logging.getLogger("agentsumo.server.route_generator")


class RouteGenerator:
    """Generates routes from trips using duarouter."""

    def __init__(self):
        self.environment = sumo_environment

    def generate(
        self,
        net_file: str,
        trip_file: str,
        output_dir: str = "output/trips"
    ) -> Dict[str, Any]:
        """
        Generate routes from trip file using duarouter.

        Args:
            net_file: SUMO network file path (.net.xml)
            trip_file: Trip file path (.trips.xml)
            output_dir: Output directory for route file

        Returns:
            Dict with route_file path
        """
        try:
            base_dir = get_working_directory()
            output_path = get_output_path(output_dir)

            if not Path(net_file).is_absolute():
                net_file = str(base_dir / net_file)
            if not Path(trip_file).is_absolute():
                trip_file = str(base_dir / trip_file)

            tag = Path(trip_file).stem.replace('.trips', '')
            route_file = str(output_path / f"{tag}.rou.xml")

            self._run_duarouter(net_file, trip_file, route_file)

            return {
                "status": "success",
                "route_file": route_file,
                "message": f"Successfully generated routes: {Path(route_file).name}",
                "metadata": {
                    "working_directory": str(base_dir),
                    "absolute_route_file": str(Path(route_file).absolute())
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Route generation failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }

    def _run_duarouter(self, net_file: str, trip_file: str, route_file: str) -> None:
        """Run duarouter to convert trips → routes."""
        duarouter_path = self.environment.get_binary_path("duarouter")

        net_file_abs = str(Path(net_file).absolute())
        trip_file_abs = str(Path(trip_file).absolute())
        route_file_abs = str(Path(route_file).absolute())

        logger.info(f"Running duarouter: {Path(trip_file).name} → {Path(route_file).name}")

        result = subprocess.run([
            duarouter_path,
            "-n", net_file_abs,
            "-t", trip_file_abs,
            "-o", route_file_abs,
            "--ignore-errors"
        ], capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            raise subprocess.CalledProcessError(
                result.returncode,
                [duarouter_path],
                output=result.stdout,
                stderr=error_msg
            )

        logger.info(f"Route generation complete: {Path(route_file).name}")
