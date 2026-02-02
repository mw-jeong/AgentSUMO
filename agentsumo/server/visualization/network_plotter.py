"""
Network visualization functionality for SUMO MCP Server.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any
import sumolib

from agentsumo.server.settings.settings import sumo_environment, visualization_settings
from agentsumo.server.utils.path_utils import get_output_path


class NetworkPlotter:
    """Network plotting class for SUMO networks."""
    
    def __init__(self):
        self.environment = sumo_environment
        self.viz_settings = visualization_settings
    
    def visualize_network(
        self,
        net_file: str,
        output_dir: str = "output/visualizations"
    ) -> Dict[str, Any]:
        """
        Visualize a SUMO network file and save as PNG image.
        
        Args:
            net_file: Path to the SUMO network file (.net.xml)
            output_dir: Output directory for visualization files
            
        Returns:
            Dict[str, Any]: Visualization result with status and output file
        """
        try:
            # print(f"[AgentSUMO] visualize_net_tool 실행됨")
            # print(f"  - net_file: {net_file}")
            # print(f"  - output_dir: {output_dir}")
            
            # Create output directory
            output_path = get_output_path(output_dir)
            
            # Generate output filename
            net_name = Path(net_file).stem
            output_file = output_path / f"{net_name}_network.png"
            
            # Read network to get first edge
            net = sumolib.net.readNet(net_file)
            first_edge = next(iter(net.getEdges())).getID()
            
            # Create temporary selection file
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
                tmp.write(f"edge:{first_edge}\n")
                tmp_path = tmp.name
            
            # Run plot_net_selection.py
            plot_script = os.path.join(
                self.environment.SUMO_HOME, "share", "sumo", "tools", 
                "visualization", "plot_net_selection.py"
            )
            
            subprocess.run([
                "python3", plot_script,
                "-n", net_file,
                "-i", tmp_path,
                "-o", str(output_file),
                "--dpi", str(self.viz_settings.DEFAULT_DPI),
                "--edge-width", str(self.viz_settings.DEFAULT_EDGE_WIDTH),
                "--edge-color", self.viz_settings.DEFAULT_EDGE_COLOR,
                "--selected-width", str(self.viz_settings.DEFAULT_EDGE_WIDTH),
                "--selected-color", self.viz_settings.DEFAULT_EDGE_COLOR,
                "--xlabel", self.viz_settings.XLABEL,
                "--ylabel", self.viz_settings.YLABEL
            ], check=True)
            
            # Clean up temporary file
            os.remove(tmp_path)
            
            msg = f"Network visualization saved: {output_file}"
            # print(f"[AgentSUMO] visualize_net_tool 완료: {msg}")
            
            return {
                "status": "success",
                "output_file": str(output_file),
                "message": msg
            }
            
        except Exception as e:
            # print(f"[AgentSUMO] visualize_net_tool 오류: {e}")
            return {
                "status": "error",
                "output_file": None,
                "message": f"Network visualization failed: {str(e)}"
            }
