"""
Data visualization functionality for SUMO MCP Server.
"""

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import logging

from agentsumo_mcp.settings.settings import sumo_environment, visualization_settings
from agentsumo_mcp.utils.path_utils import get_output_path

logger = logging.getLogger("agentsumo_mcp.visualization")


class DataPlotter:
    """Data plotting class for SUMO simulation results."""
    
    def __init__(self):
        self.environment = sumo_environment
        self.viz_settings = visualization_settings
    
    def _extract_attribute_range(
        self, 
        edgedata_file: str, 
        attribute: str,
        add_padding: bool = True
    ) -> Tuple[float, float]:
        """
        Extract min and max values for a given attribute from edgedata XML.
        
        Args:
            edgedata_file: Path to edgedata XML file
            attribute: Attribute name (e.g., 'density', 'speed', 'occupancy')
            add_padding: Whether to add 10% padding to the range
            
        Returns:
            Tuple[float, float]: (min_value, max_value)
        """
        try:
            tree = ET.parse(edgedata_file)
            root = tree.getroot()
            
            values = []
            
            # Iterate through all intervals and edges
            for interval in root.findall('.//interval'):
                for edge in interval.findall('edge'):
                    value_str = edge.get(attribute)
                    if value_str is not None:
                        try:
                            values.append(float(value_str))
                        except ValueError:
                            continue
            
            if not values:
                logger.warning(f"No valid '{attribute}' values found in {edgedata_file}. Using default range [0, 60].")
                return (0.0, 60.0)
            
            min_val = min(values)
            max_val = max(values)
            
            # Add 10% padding to avoid edge cases (optional)
            if add_padding:
                range_padding = (max_val - min_val) * 0.1
                min_val = max(0, min_val - range_padding)  # Don't go below 0
                max_val = max_val + range_padding
            
            logger.info(f"✅ Extracted '{attribute}' range: [{min_val:.2f}, {max_val:.2f}]")
            return (min_val, max_val)
            
        except Exception as e:
            logger.error(f"Failed to extract attribute range: {e}. Using default [0, 60].")
            return (0.0, 60.0)
    
    def _extract_unified_range(
        self,
        edgedata_files: list,
        attribute: str
    ) -> Tuple[float, float]:
        """
        Extract unified min/max range from multiple edgedata files.
        Useful for comparing multiple simulations with consistent scale.
        
        Args:
            edgedata_files: List of edgedata XML file paths
            attribute: Attribute name
            
        Returns:
            Tuple[float, float]: (global_min, global_max)
        """
        try:
            all_mins = []
            all_maxs = []
            
            for file in edgedata_files:
                min_val, max_val = self._extract_attribute_range(file, attribute, add_padding=False)
                all_mins.append(min_val)
                all_maxs.append(max_val)
            
            global_min = min(all_mins)
            global_max = max(all_maxs)
            
            # Add 10% padding to unified range
            range_padding = (global_max - global_min) * 0.1
            global_min = max(0, global_min - range_padding)
            global_max = global_max + range_padding
            
            logger.info(f"✅ Unified '{attribute}' range from {len(edgedata_files)} files: [{global_min:.2f}, {global_max:.2f}]")
            return (global_min, global_max)
            
        except Exception as e:
            logger.error(f"Failed to extract unified range: {e}. Using default [0, 60].")
            return (0.0, 60.0)
    
    def visualize_edgedata(
        self,
        net_file: str,
        edgedata_file: str,
        attribute: str = "density",
        output_dir: str = "output/visualizations",
        scale_mode: str = "auto",
        comparison_files: Optional[list] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Visualize SUMO edgedata with flexible scaling modes.
        
        Scale Modes:
        - 'auto': Dynamic scale based on current file's data (default)
        - 'unified': Unified scale across multiple files (for comparison)
        - 'fixed': User-defined fixed scale (min_value, max_value required)
        
        Args:
            net_file: Path to the SUMO network file (.net.xml)
            edgedata_file: Path to the SUMO edgeData output file (.xml)
            attribute: The attribute to visualize (e.g., 'density', 'speed', 'CO2_abs')
            output_dir: Output directory for visualization files
            scale_mode: Scale mode ('auto' | 'unified' | 'fixed')
            comparison_files: List of files for unified scale (required for 'unified' mode)
            min_value: Minimum value for fixed scale (required for 'fixed' mode)
            max_value: Maximum value for fixed scale (required for 'fixed' mode)
            
        Returns:
            Dict[str, Any]: Visualization result with status and output file
            
        Examples:
            # Auto scale (single analysis)
            visualize_edgedata(..., scale_mode='auto')
            
            # Unified scale (policy comparison)
            visualize_edgedata(..., scale_mode='unified', 
                             comparison_files=['before.xml', 'after.xml'])
            
            # Fixed scale (standardized)
            visualize_edgedata(..., scale_mode='fixed', 
                             min_value=0, max_value=100)
        """
        try:
            # Create output directory
            output_path = get_output_path(output_dir)
            
            # Generate output filename with %s placeholder for multiple time intervals
            edgedata_name = Path(edgedata_file).stem
            output_file = output_path / f"{edgedata_name}_{attribute}_heatmap_%s.png"
            
            # Run plot_net_dump.py
            plot_script = os.path.join(
                self.environment.SUMO_HOME, "share", "sumo", "tools", 
                "visualization", "plot_net_dump.py"
            )
            
            # print(f"[DEBUG] SUMO_HOME: {self.environment.SUMO_HOME}")
            # print(f"[DEBUG] Plot script: {plot_script}")
            # print(f"[DEBUG] Script exists: {os.path.exists(plot_script)}")
            # print(f"[DEBUG] Working directory: {os.getcwd()}")
            # print(f"[DEBUG] Net file exists: {os.path.exists(net_file)}")
            # print(f"[DEBUG] Edge data file exists: {os.path.exists(edgedata_file)}")
            
            # Determine min/max values based on scale_mode
            if scale_mode == 'auto':
                # Dynamic scale from current file only
                min_val, max_val = self._extract_attribute_range(edgedata_file, attribute)
                logger.info(f"🎨 Scale mode: AUTO (current file only)")
                
            elif scale_mode == 'unified':
                # Unified scale across multiple files
                if not comparison_files:
                    logger.warning("'unified' mode requires comparison_files. Falling back to 'auto'.")
                    min_val, max_val = self._extract_attribute_range(edgedata_file, attribute)
                else:
                    # Include current file in unified range
                    all_files = [edgedata_file] + list(comparison_files)
                    min_val, max_val = self._extract_unified_range(all_files, attribute)
                    logger.info(f"🎨 Scale mode: UNIFIED ({len(all_files)} files)")
                    
            elif scale_mode == 'fixed':
                # User-defined fixed scale
                if min_value is None or max_value is None:
                    logger.warning("'fixed' mode requires min_value and max_value. Falling back to 'auto'.")
                    min_val, max_val = self._extract_attribute_range(edgedata_file, attribute)
                else:
                    min_val, max_val = min_value, max_value
                    logger.info(f"🎨 Scale mode: FIXED (user-defined: [{min_val:.2f}, {max_val:.2f}])")
                    
            else:
                logger.warning(f"Unknown scale_mode '{scale_mode}'. Using 'auto'.")
                min_val, max_val = self._extract_attribute_range(edgedata_file, attribute)
            
            # Set SUMO_HOME environment variable for subprocess
            env = os.environ.copy()
            env['SUMO_HOME'] = self.environment.SUMO_HOME
            
            result = subprocess.run([
                "python3", plot_script,
                "-n", net_file,
                "-i", f"{edgedata_file},{edgedata_file}",
                "-o", str(output_file),
                "-m", f"{attribute},{attribute}",
                "--dpi", "700",
                "--colormap", self.viz_settings.DEFAULT_COLORMAP,
                "--min-color-value", "0.1",
                "--max-color-value", f"{max_val:.2f}",
                "--log-colors",
                "--color-bar-label", f"{attribute.capitalize()}",
                "--xlabel", self.viz_settings.XLABEL,
                "--ylabel", self.viz_settings.YLABEL
            ], capture_output=True, text=True, cwd=os.getcwd(), env=env)
            
            # print(f"[DEBUG] Command return code: {result.returncode}")
            # print(f"[DEBUG] STDOUT: {result.stdout}")
            # print(f"[DEBUG] STDERR: {result.stderr}")
            
            if result.returncode != 0:
                raise RuntimeError(f"plot_net_dump.py failed with return code {result.returncode}: {result.stderr}")
            
            msg = f"Edge data visualization saved: {output_file} (attribute: {attribute}, scale: {scale_mode}, range: [{min_val:.2f}, {max_val:.2f}])"

            return {
                "status": "success",
                "output_file": str(output_file),
                "attribute": attribute,
                "scale_mode": scale_mode,
                "min_value": min_val,
                "max_value": max_val,
                "message": msg
            }
            
        except Exception as e:
            return {
                "status": "error",
                "output_file": None,
                "message": f"Edge data visualization failed: {str(e)}"
            }
