"""
Traffic light management tools for SUMO MCP Server.
"""

import datetime
import subprocess
from typing import Optional, Dict, Any

from agentsumo_mcp.settings.settings import sumo_environment
from agentsumo_mcp.utils.file_utils import ensure_directory
from agentsumo_mcp.utils.path_utils import get_output_path


class TrafficLightManager:
    """Traffic light management class for SUMO simulations."""
    
    def __init__(self):
        self.environment = sumo_environment
    
    def optimize_offsets(
        self,
        net_file: str,
        route_file: str,
        output_dir: str = "output/simulations",
        zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run SUMO tlsCoordinator.py to optimize traffic light offsets and generate an additional XML file.
        
        Args:
            net_file: Network file path
            route_file: Route file path
            output_dir: Output directory for results
            zone_id: Zone ID for zone-specific file naming (optional)
            
        Returns:
            Dict[str, Any]: Optimization result with status and metadata
        """
        try:
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Zone-specific file naming
            if zone_id:
                tls_offset_file = output_path / f"{zone_id}_tls_offset_{ts}.add.xml"
            else:
                tls_offset_file = output_path / f"tls_offset_{ts}.add.xml"
            
            ensure_directory(output_path)
            
            # Run tlsCoordinator.py
            tls_coordinator_path = self.environment.get_tool_path("tlsCoordinator.py")
            result = subprocess.run([
                "python3", tls_coordinator_path,
                "-n", net_file,
                "-r", route_file,
                "-o", str(tls_offset_file)
            ], capture_output=True, text=True, check=True)
            
            return {
                "status": "success", 
                "additional_file": str(tls_offset_file), 
                "message": "tlsCoordinator.py executed successfully."
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": str(e), 
                "additional_file": None
            }
    
    def optimize_cycles(
        self,
        net_file: str,
        route_file: str,
        output_dir: str = "output/simulations",
        zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run SUMO tlsCycleAdaptation.py to optimize traffic light cycles and generate an additional XML file.
        
        Args:
            net_file: Network file path
            route_file: Route file path
            output_dir: Output directory for results
            zone_id: Zone ID for zone-specific file naming (optional)
            
        Returns:
            Dict[str, Any]: Optimization result with status and metadata
        """
        try:
            output_path = get_output_path(output_dir)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Zone-specific file naming
            if zone_id:
                tls_adapt_file = output_path / f"{zone_id}_tls_adapt_{ts}.add.xml"
            else:
                tls_adapt_file = output_path / f"tls_adapt_{ts}.add.xml"
            
            ensure_directory(output_path)
            
            # Run tlsCycleAdaptation.py
            tls_adapt_path = self.environment.get_tool_path("tlsCycleAdaptation.py")
            result = subprocess.run([
                "python3", tls_adapt_path,
                "-n", net_file,
                "-r", route_file,
                "-o", str(tls_adapt_file),
                "-b", "0"
            ], capture_output=True, text=True, check=True)
            
            return {
                "status": "success", 
                "additional_file": str(tls_adapt_file), 
                "message": "tlsCycleAdaptation.py executed successfully."
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": str(e), 
                "additional_file": None
            }
