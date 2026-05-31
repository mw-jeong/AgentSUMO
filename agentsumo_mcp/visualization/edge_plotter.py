"""
Edge visualization functionality for SUMO MCP Server.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from agentsumo_mcp.settings.settings import sumo_environment, visualization_settings
from agentsumo_mcp.utils.path_utils import get_output_path
from agentsumo_mcp.utils.sumo_utils import get_edge_ids_from_road_name


class EdgePlotter:
    """Edge plotting class for SUMO networks."""

    def __init__(self):
        self.environment = sumo_environment
        self.viz_settings = visualization_settings

    def visualize_edge(
        self,
        net_file: str,
        road_name: str,
        output_dir: str = "output/visualizations"
    ) -> Dict[str, Any]:
        """
        Visualize a SUMO network file with selected edges highlighted and save as PNG image.

        Args:
            net_file: Path to the SUMO network file (.net.xml)
            road_name: Name of the road to highlight
            output_dir: Output directory for visualization files

        Returns:
            Dict[str, Any]: Visualization result with status and output file
        """
        try:
            # Create output directory
            output_path = get_output_path(output_dir)

            # Get edge IDs from road name using edge.getName()
            edge_ids = get_edge_ids_from_road_name(net_file, road_name)
            
            if not edge_ids:
                return {
                    "status": "error",
                    "output_file": None,
                    "message": f"No edges found for road name: {road_name}"
                }
            
            # Generate output filename
            net_name = Path(net_file).stem
            safe_road_name = road_name.replace(" ", "_").replace("/", "_")
            output_file = output_path / f"{net_name}_edge_{safe_road_name}.png"
            
            # Create temporary selection file
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
                for edge_id in edge_ids:
                    tmp.write(f"edge:{edge_id}\n")
                selection_path = tmp.name
            
            # Run plot_net_selection.py
            plot_script = os.path.join(
                self.environment.SUMO_HOME, "share", "sumo", "tools", 
                "visualization", "plot_net_selection.py"
            )
            
            subprocess.run([
                "python3", plot_script,
                "-n", net_file,
                "-i", selection_path,
                "-o", str(output_file),
                "--dpi", str(self.viz_settings.DEFAULT_DPI),
                "--edge-width", str(self.viz_settings.DEFAULT_EDGE_WIDTH),
                "--edge-color", self.viz_settings.DEFAULT_EDGE_COLOR,
                "--selected-width", str(self.viz_settings.DEFAULT_SELECTED_WIDTH),
                "--selected-color", self.viz_settings.DEFAULT_SELECTED_COLOR,
                "--xlabel", self.viz_settings.XLABEL,
                "--ylabel", self.viz_settings.YLABEL
            ], check=True)
            
            # Clean up temporary file
            os.remove(selection_path)
            
            msg = f"Edge visualization saved: {output_file} (highlighted {len(edge_ids)} edges)"

            return {
                "status": "success",
                "output_file": str(output_file),
                "highlighted_edges": edge_ids,
                "message": msg
            }

        except Exception as e:
            return {
                "status": "error",
                "output_file": None,
                "message": f"Edge visualization failed: {str(e)}"
            }

    def visualize_policy_target(
        self,
        net_file: str,
        target_road_name: str,
        reference_location: Optional[str] = None,
        radius_km: Optional[float] = None,
        output_dir: str = "output/visualizations"
    ) -> Dict[str, Any]:
        """
        Visualize policy target area using SUMO's built-in plot_net_selection.py.

        Args:
            net_file: Network file path
            target_road_name: Road name (e.g., "테헤란로")
            reference_location: Reference point (e.g., "강남역")
            radius_km: Radius in km (e.g., 0.3)
            output_dir: Output directory

        Returns:
            Dict with visualization file path and metadata
        """
        try:
            # Create output directory
            output_path = get_output_path(output_dir)

            # Get all edges of target road
            if not target_road_name:
                return {"status": "error", "message": "target_road_name required"}

            all_road_edges = get_edge_ids_from_road_name(net_file, target_road_name)
            
            if not all_road_edges:
                return {"status": "error", "message": f"Road '{target_road_name}' not found"}
            
            # Filter by radius if specified
            selected_edges = []
            if reference_location and radius_km:
                from agentsumo_mcp.utils.sumo_utils import geocode_location
                import sumolib
                
                ref_coords = geocode_location(reference_location)
                if ref_coords:
                    ref_lat, ref_lon = ref_coords
                    net = sumolib.net.readNet(net_file)
                    
                    for edge_id in all_road_edges:
                        try:
                            edge = net.getEdge(edge_id)
                            shape = edge.getShape()
                            if shape:
                                mid_point = shape[len(shape) // 2]
                                edge_lon, edge_lat = net.convertXY2LonLat(mid_point[0], mid_point[1])
                                
                                from geopy.distance import distance
                                dist_km = distance((ref_lat, ref_lon), (edge_lat, edge_lon)).km
                                
                                if dist_km <= radius_km:
                                    selected_edges.append(edge_id)
                        except:
                            continue
            else:
                selected_edges = all_road_edges  # No filtering
            
            # Generate output filename
            net_name = Path(net_file).stem
            safe_road_name = target_road_name.replace(" ", "_").replace("/", "_")
            suffix = f"{reference_location}_{radius_km}km" if reference_location and radius_km else "full"
            output_file = output_path / f"{net_name}_{safe_road_name}_policy_target_{suffix}.png"
            
            # Create temporary selection file for SUMO's plot_net_selection.py
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
                for edge_id in selected_edges:
                    tmp.write(f"edge:{edge_id}\n")
                selection_path = tmp.name
            
            # Run SUMO's plot_net_selection.py (same as visualize_edge)
            plot_script = os.path.join(
                self.environment.SUMO_HOME, "share", "sumo", "tools", 
                "visualization", "plot_net_selection.py"
            )
            
            subprocess.run([
                "python3", plot_script,
                "-n", net_file,
                "-i", selection_path,
                "-o", str(output_file),
                "--dpi", str(self.viz_settings.DEFAULT_DPI),
                "--edge-width", str(self.viz_settings.DEFAULT_EDGE_WIDTH),
                "--edge-color", self.viz_settings.DEFAULT_EDGE_COLOR,
                "--selected-width", str(self.viz_settings.DEFAULT_SELECTED_WIDTH),
                "--selected-color", self.viz_settings.DEFAULT_SELECTED_COLOR,
                "--xlabel", self.viz_settings.XLABEL,
                "--ylabel", self.viz_settings.YLABEL
            ], check=True)
            
            # Clean up temporary file
            os.remove(selection_path)
            
            msg = f"Policy target visualization saved: {output_file}\n"
            msg += f"Target road: {target_road_name} ({len(all_road_edges)} segments)\n"
            msg += f"Policy area: {len(selected_edges)} segments"
            if reference_location and radius_km:
                msg += f" (within {radius_km}km of {reference_location})"
            
            return {
                "status": "success",
                "output_file": str(output_file),
                "message": msg,
                "metadata": {
                    "total_segments": len(all_road_edges),
                    "selected_segments": len(selected_edges),
                    "reference": reference_location,
                    "radius_km": radius_km
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "output_file": None,
                "message": f"Policy visualization failed: {str(e)}"
            }