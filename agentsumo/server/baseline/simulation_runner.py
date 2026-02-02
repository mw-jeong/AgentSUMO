"""
Simulation execution functionality for SUMO MCP Server.

Uses subprocess for simulation execution with FCD output for post-simulation replay.
"""

import subprocess
import time
import datetime
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from xml.etree.ElementTree import Element, SubElement, ElementTree

from agentsumo.server.settings.settings import sumo_environment, simulation_settings
from agentsumo.server.utils.file_utils import copy_to_workdir, copy_additional_files
from agentsumo.server.utils.path_utils import get_output_path, get_working_directory

logger = logging.getLogger(__name__)


class SimulationRunner:
    """Simulation execution class for SUMO simulations using subprocess."""

    def __init__(self):
        self.environment = sumo_environment
        self.sim_settings = simulation_settings

    def run(
        self,
        net_file: str,
        trip_file: Optional[str] = None,
        route_file: Optional[str] = None,
        duration: int = 3600,
        output_dir: str = "output/simulations",
        additional_files: Optional[List[str]] = None,
        policy_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run SUMO simulation using subprocess with FCD output for replay.

        Args:
            net_file: Network file path (tag will be extracted from filename)
            trip_file: Trip file path (optional)
            route_file: Route file path (optional)
            duration: Simulation duration in seconds
            output_dir: Output directory for simulation results
            additional_files: List of additional XML files to include
            policy_type: Policy type for batch simulation file naming

        Returns:
            Dict[str, Any]: Simulation result with status and output files
        """
        try:
            # Setup working directory and paths
            base_dir = get_working_directory()
            output_path = get_output_path(output_dir)

            if not Path(net_file).is_absolute():
                net_file = str(base_dir / net_file)

            # Handle additional files - reset for new baseline simulations
            if policy_type == "baseline":
                additional_files = []
            else:
                additional_files = additional_files or []

            # Generate unique output file names
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = Path(net_file).stem if net_file else "simulation"

            # Use network filename as prefix (extracts tag automatically)
            prefix = base_name

            output_files = self._generate_output_filenames(prefix, timestamp)

            # Copy input files to working directory
            file_names = self._copy_input_files(
                net_file, trip_file, route_file, output_path, None
            )

            # Copy additional files
            additional_file_names = copy_additional_files(
                additional_files, output_path, None
            )

            # Generate additional.add.xml
            add_file = self._generate_additional_file(output_path, output_files, duration)

            # Generate SUMO configuration
            config_file = self._generate_config_file(
                output_path, file_names, additional_file_names, add_file,
                output_files, duration, timestamp
            )

            # Run SUMO simulation using subprocess
            result = self._run_simulation_subprocess(
                config_file, output_path, output_files
            )

            # Prepare result
            return self._prepare_result(
                result, output_path, output_files, base_dir, duration
            )

        except Exception as e:
            return {
                "status": "error",
                "output_files": [],
                "message": f"Simulation failed: {str(e)}",
                "simulation_time": 0.0,
                "metadata": {"error_type": type(e).__name__}
            }

    def _generate_output_filenames(self, prefix: str, timestamp: str) -> Dict[str, str]:
        """Generate output filenames for simulation results."""
        return {
            "tripinfo": f"{prefix}_tripinfo_{timestamp}.xml",
            "summary": f"{prefix}_summary_{timestamp}.xml",
            "emission": f"{prefix}_emission_{timestamp}.xml",
            "netstate_dump": f"{prefix}_netstate_{timestamp}.xml",
            "netstate_dump_emission": f"{prefix}_netstate_emission_{timestamp}.xml",
            # "fcd": f"{prefix}_fcd_{timestamp}.xml"
        }

    def _copy_input_files(
        self, net_file: str, trip_file: Optional[str], route_file: Optional[str],
        output_path: Path, split_id: Optional[str]
    ) -> Dict[str, str]:
        """Copy input files to working directory."""
        # Always use regular copies (tag is extracted from network filename)
        net_file_name = copy_to_workdir(net_file, output_path)
        trip_file_name = copy_to_workdir(trip_file, output_path) if trip_file else None
        route_file_name = copy_to_workdir(route_file, output_path) if route_file else None

        return {
            "net_file": net_file_name,
            "trip_file": trip_file_name,
            "route_file": route_file_name
        }

    def _generate_additional_file(self, output_path: Path, output_files: Dict[str, str], duration: int) -> str:
        """Generate additional.add.xml file for simulation."""
        add_file = "additional.add.xml"
        add_path = output_path / add_file

        add_root = Element("additional")
        edge_data = SubElement(add_root, "edgeData", {
            "id": "dump_output",
            "freq": str(duration),
            "file": output_files["netstate_dump"],
        })
        # edge_data_emission = SubElement(add_root, "edgeData", {
        #     "id": "dump_output_emission",
        #     "freq": str(duration),
        #     "file": output_files["netstate_dump_emission"],
        #     "type": "emissions",
        #     "excludeEmpty": "true",
        # })

        ElementTree(add_root).write(add_path, encoding="utf-8", xml_declaration=True)
        return add_file

    def _generate_config_file(
        self, output_path: Path, file_names: Dict[str, str],
        additional_file_names: List[str], add_file: str,
        output_files: Dict[str, str], duration: int, timestamp: str
    ) -> Path:
        """Generate SUMO configuration file."""
        config_file = output_path / f"simulation_{timestamp}.sumocfg"
        cfg_root = Element("configuration")

        # Input section
        input_tag = SubElement(cfg_root, "input")
        SubElement(input_tag, "net-file", {"value": file_names["net_file"]})

        if file_names["route_file"]:
            SubElement(input_tag, "route-files", {"value": file_names["route_file"]})
        elif file_names["trip_file"]:
            SubElement(input_tag, "trip-files", {"value": file_names["trip_file"]})

        # Additional files
        additional_files_list = [add_file, "vehicle_types.add.xml"]
        additional_files_list.extend(additional_file_names)
        SubElement(input_tag, "additional-files", {
            "value": ",".join(additional_files_list)
        })

        # Time section
        time_tag = SubElement(cfg_root, "time")
        SubElement(time_tag, "begin", {"value": "0"})
        SubElement(time_tag, "end", {"value": str(duration)})

        # Output section
        output_tag = SubElement(cfg_root, "output")
        SubElement(output_tag, "tripinfo-output", {"value": output_files["tripinfo"]})
        # SubElement(output_tag, "summary-output", {"value": output_files["summary"]})
        # SubElement(output_tag, "emission-output", {"value": output_files["emission"]})
        # SubElement(output_tag, "fcd-output", {"value": output_files["fcd"]})
        # SubElement(output_tag, "fcd-output.geo", {"value": "true"})  # Include lon/lat coordinates
        # Note: tls-switch-output removed - not supported in current SUMO version
        # Traffic light states will be simulated based on time in frontend

        # Report section
        report_tag = SubElement(cfg_root, "report")
        SubElement(report_tag, "verbose", {"value": "true"})
        SubElement(report_tag, "no-step-log", {"value": "true"})

        ElementTree(cfg_root).write(config_file, encoding="utf-8", xml_declaration=True)
        return config_file

    def _run_simulation_subprocess(
        self,
        config_file: Path,
        output_path: Path,
        output_files: Dict[str, str]
    ) -> subprocess.CompletedProcess:
        """
        Run SUMO simulation using subprocess.

        Returns subprocess.CompletedProcess with elapsed time attribute.
        """
        start_time = time.time()
        sumo_binary = self.environment.get_binary_path("sumo")

        # Build command
        sumo_cmd = [
            sumo_binary,
            "-c", str(config_file),
            "--no-warnings"
        ]

        logger.info(f"Running SUMO simulation: {config_file.name}")

        try:
            result = subprocess.run(
                sumo_cmd,
                capture_output=True,
                text=True,
                cwd=str(output_path),
                timeout=600  # 10 minute timeout
            )

            elapsed = time.time() - start_time
            result.elapsed = elapsed

            logger.info(f"Simulation completed in {elapsed:.2f} seconds")

            return result

        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_time

            # Create a mock result for timeout
            class TimeoutResult:
                returncode = 1
                stdout = ""
                stderr = f"Simulation timed out after {elapsed:.2f} seconds"
                elapsed = elapsed

            return TimeoutResult()

    def _prepare_result(
        self, result: Any, output_path: Path,
        output_files: Dict[str, str], base_dir: Path, duration: int
    ) -> Dict[str, Any]:
        """Prepare simulation result."""
        # Convert to absolute paths for result analyzer
        tripinfo_abs = str(output_path / output_files["tripinfo"])
        edgedata_abs = str(output_path / output_files["netstate_dump"])
        edgedata_emission_abs = str(output_path / output_files["netstate_dump_emission"])
        # fcd_abs = str(output_path / output_files["fcd"])

        if result.returncode != 0:
            return {
                "status": "warning",
                "output_files": [tripinfo_abs, edgedata_abs, edgedata_emission_abs],
                "message": f"Simulation completed with warnings in {result.elapsed:.2f} seconds\n{result.stderr}",
                "simulation_time": result.elapsed,
                "metadata": {
                    "working_directory": str(base_dir),
                    "absolute_tripinfo": tripinfo_abs,
                    "absolute_edgedata": edgedata_abs,
                    "absolute_edgedata_emission": edgedata_emission_abs,
                    # "absolute_fcd": fcd_abs,
                    "return_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            }

        return {
            "status": "success",
            "output_files": [tripinfo_abs, edgedata_abs, edgedata_emission_abs],
            "message": f"Simulation executed successfully in {result.elapsed:.2f} seconds.",
            "simulation_time": result.elapsed,
            "metadata": {
                "working_directory": str(base_dir),
                "absolute_tripinfo": tripinfo_abs,
                "absolute_edgedata": edgedata_abs,
                "absolute_edgedata_emission": edgedata_emission_abs,
                # "absolute_fcd": fcd_abs,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        }
