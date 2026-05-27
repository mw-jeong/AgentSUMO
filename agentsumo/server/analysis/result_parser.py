"""
Result parsing functionality for SUMO MCP Server.
"""

import datetime
import re
import json
from typing import Dict, Any

from agentsumo.server.settings.settings import analysis_settings
from agentsumo.server.utils.path_utils import get_output_path
from agentsumo.server.utils.sumo_utils import run_attribute_stats


class ResultParser:
    """Result parsing class for SUMO simulation results."""
    
    def __init__(self):
        self.settings = analysis_settings
    
    def parse_tripinfo_to_json(self, raw_output: str) -> dict:
        """Parse tripinfo attributeStats.py output to JSON format."""
        result = {
            "simulation_info": {
                "analysis_timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            },
            "emissions": {},
            "trip_attributes": {}
        }
        
        lines = raw_output.strip().split('\n')
        for line in lines:
            if not line.strip() or ':' not in line:
                continue
                
            tag, stats_part = line.split(':', 1)
            tag = tag.strip()
            
            if ' ' not in tag:
                continue
                
            prefix, variable = tag.split(' ', 1)
            
            # Parse statistics (ignore parentheses values)
            stats_dict = {}
            for stat_name, pattern in self.settings.STATS_PATTERNS.items():
                match = re.search(pattern, stats_part)
                if match:
                    value = match.group(1)
                    try:
                        if '.' in value:
                            stats_dict[stat_name] = float(value)
                        else:
                            stats_dict[stat_name] = int(value)
                    except ValueError:
                        stats_dict[stat_name] = value
            
            # Get metadata and interpretation
            metadata = self._get_tripinfo_metadata(prefix, variable, stats_dict)
            
            if prefix == 'emissions':
                result['emissions'][variable] = {
                    "statistics": stats_dict,
                    "metadata": metadata
                }
            elif prefix == 'tripinfo':
                result['trip_attributes'][variable] = {
                    "statistics": stats_dict,
                    "metadata": metadata
                }
        
        # Add total vehicles count
        if result['emissions']:
            first_emission = next(iter(result['emissions'].values()))
            result['simulation_info']['total_vehicles'] = first_emission['statistics'].get('count', 0)
        
        return result
    
    def parse_edgedata_to_json(self, raw_output: str) -> dict:
        """Parse edgedata/edgedata_emission attributeStats.py output to JSON format."""
        result = {
            "simulation_info": {
                "analysis_timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            },
            "edge_statistics": {}
        }
        
        lines = raw_output.strip().split('\n')
        for line in lines:
            if not line.strip() or not line.startswith('edge '):
                continue
                
            tag, stats_part = line.split(':', 1)
            _, variable = tag.strip().split(' ', 1)
            
            stats_dict = {}
            
            # Extract min/max values and edge_ids
            min_match = re.search(r'min ([\d.]+)(?: \(([^)]+)\))?', stats_part)
            max_match = re.search(r'max ([\d.]+)(?: \(([^)]+)\))?', stats_part)
            
            if min_match:
                stats_dict['min'] = float(min_match.group(1)) if '.' in min_match.group(1) else int(min_match.group(1))
                if min_match.group(2):
                    stats_dict['min_edge'] = min_match.group(2)
            
            if max_match:
                stats_dict['max'] = float(max_match.group(1)) if '.' in max_match.group(1) else int(max_match.group(1))
                if max_match.group(2):
                    stats_dict['max_edge'] = max_match.group(2)
            
            # Extract other statistics
            patterns = {
                'mean': r'mean ([\d.]+)',
                'stdDev': r'stdDev ([\d.]+)'
            }
            
            for stat_name, pattern in patterns.items():
                match = re.search(pattern, stats_part)
                if match:
                    value = match.group(1)
                    try:
                        if '.' in value:
                            stats_dict[stat_name] = float(value)
                        else:
                            stats_dict[stat_name] = int(value)
                    except ValueError:
                        stats_dict[stat_name] = value
            
            # Get metadata
            metadata = self._get_edgedata_metadata(variable, stats_dict)
            
            result['edge_statistics'][variable] = {
                "statistics": stats_dict,
                "metadata": metadata
            }
        
        # Add total edges count
        result['simulation_info']['total_edges'] = len(result['edge_statistics'])
        
        return result
    
    def _get_tripinfo_metadata(self, prefix: str, variable: str, stats: dict) -> dict:
        """Get metadata for tripinfo variables with interpretation."""
        emissions_meta = {
            "CO2_abs": ("mg", "Total CO2 emissions per vehicle"),
            "CO_abs": ("mg", "Total CO emissions per vehicle"),
            "HC_abs": ("mg", "Total HC emissions per vehicle"),
            "NOx_abs": ("mg", "Total NOx emissions per vehicle"),
            "PMx_abs": ("mg", "Total PMx emissions per vehicle"),
            "electricity_abs": ("Wh", "Total electricity consumption per vehicle"),
            "fuel_abs": ("mg", "Total fuel consumption per vehicle")
        }
        
        tripinfo_meta = {
            "duration": ("seconds", "Total travel time per vehicle"),
            "arrival": ("seconds", "Arrival time per vehicle"),
            "depart": ("seconds", "Departure time per vehicle"),
            "departDelay": ("seconds", "Departure delay per vehicle"),
            "arrivalSpeed": ("m/s", "Arrival speed per vehicle"),
            "departSpeed": ("m/s", "Departure speed per vehicle"),
            "routeLength": ("m", "Route length per vehicle"),
            "waitingTime": ("seconds", "Waiting time per vehicle"),
            "timeLoss": ("seconds", "Time loss per vehicle"),
            "speedFactor": ("float", "Speed factor per vehicle")
        }
        
        if prefix == 'emissions' and variable in emissions_meta:
            unit, desc = emissions_meta[variable]
        elif prefix == 'tripinfo' and variable in tripinfo_meta:
            unit, desc = tripinfo_meta[variable]
        else:
            unit, desc = ("unknown", "Unknown variable")
        
        # Generate interpretation
        mean_val = stats.get('mean', 0)
        interpretation = self._generate_interpretation(variable, mean_val, unit)
        
        return {
            "unit": unit,
            "description": desc,
            "interpretation": interpretation
        }
    
    def _get_edgedata_metadata(self, variable: str, stats: dict) -> dict:
        """Get metadata for edgedata variables with interpretation."""
        edge_meta = {
            "CO2_abs": ("mg", "Total CO2 emissions on this edge"),
            "CO_abs": ("mg", "Total CO emissions on this edge"),
            "HC_abs": ("mg", "Total HC emissions on this edge"),
            "NOx_abs": ("mg", "Total NOx emissions on this edge"),
            "PMx_abs": ("mg", "Total PMx emissions on this edge"),
            "fuel_abs": ("mg", "Total fuel consumption on this edge"),
            "electricity_abs": ("Wh", "Total electricity consumption on this edge"),
            "density": ("veh/km", "Vehicle density on this edge"),
            "speed": ("m/s", "Average speed on this edge"),
            "occupancy": ("%", "Occupancy rate on this edge"),
            "waitingTime": ("seconds", "Total waiting time on this edge"),
            "timeLoss": ("seconds", "Total time loss on this edge"),
            "arrived": ("vehicles", "Number of vehicles arrived on this edge"),
            "departed": ("vehicles", "Number of vehicles departed from this edge"),
            "entered": ("vehicles", "Number of vehicles entered this edge"),
            "left": ("vehicles", "Number of vehicles left this edge")
        }
        
        if variable in edge_meta:
            unit, desc = edge_meta[variable]
        else:
            unit, desc = ("unknown", "Unknown variable")
        
        # Generate interpretation with edge_id if available
        max_val = stats.get('max', 0)
        max_edge = stats.get('max_edge', 'unknown')
        mean_val = stats.get('mean', 0)
        
        if max_edge != 'unknown':
            interpretation = f"Edge {max_edge} has the highest {variable} ({max_val:.2f} {unit}), average is {mean_val:.2f} {unit}"
        else:
            interpretation = f"Maximum {variable} is {max_val:.2f} {unit}, average is {mean_val:.2f} {unit}"
        
        return {
            "unit": unit,
            "description": desc,
            "interpretation": interpretation
        }
    
    def _generate_interpretation(self, variable: str, mean_val: float, unit: str) -> str:
        """Generate interpretation for a variable."""
        if variable == 'duration':
            return f"Average travel time is {mean_val:.2f} seconds (about {mean_val/60:.1f} minutes)"
        elif variable == 'arrivalSpeed' or variable == 'departSpeed':
            return f"Average speed is {mean_val:.2f} m/s (about {mean_val*self.settings.SPEED_CONVERSION:.1f} km/h)"
        elif variable == 'routeLength':
            return f"Average route length is {mean_val:.2f} meters (about {mean_val/self.settings.DISTANCE_CONVERSION:.2f} km)"
        elif 'emissions' in variable or 'fuel' in variable:
            return f"Average {variable} is {mean_val:.2f} {unit}"
        else:
            return f"Average {variable} is {mean_val:.2f} {unit}"
    
    def analyze_results(
        self,
        tripinfo_file: str,
        edgedata_file: str,
        edgedata_emission_file: str,
        output_dir: str = "output/analysis"
    ) -> Dict[str, Any]:
        """
        Parse SUMO simulation results into LLM-friendly JSON format.
        
        Args:
            tripinfo_file: Tripinfo XML file path
            edgedata_file: Edgedata XML file path
            edgedata_emission_file: Edgedata emission XML file path
            output_dir: Output directory for JSON files
            
        Returns:
            Dict[str, Any]: Analysis result with status and metadata
        """
        try:
            # MCP stdout은 JSON 전용이므로 print 대신 logging 사용
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"result_analyzer_tool 실행됨")
            logger.debug(f"  - tripinfo: {tripinfo_file}")
            logger.debug(f"  - edgedata: {edgedata_file}")
            logger.debug(f"  - edgedata_emission: {edgedata_emission_file}")
            
            # Create output directory
            output_path = get_output_path(output_dir)
            
            # Generate unique filenames with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            tripinfo_json_file = output_path / f"tripinfo_{timestamp}.json"
            edgedata_json_file = output_path / f"edgedata_{timestamp}.json"
            
            # Parse tripinfo
            # print(f"📊 Parsing tripinfo file: {tripinfo_file}")
            tripinfo_raw = run_attribute_stats(tripinfo_file)
            tripinfo_json = self.parse_tripinfo_to_json(tripinfo_raw)
            
            # Parse edgedata and edgedata_emission
            # print(f"📊 Parsing edgedata files: {edgedata_file}, {edgedata_emission_file}")
            edgedata_raw = run_attribute_stats(edgedata_file)
            edgedata_emission_raw = run_attribute_stats(edgedata_emission_file)
            
            # Combine edgedata results
            combined_edgedata_raw = edgedata_raw + "\n" + edgedata_emission_raw
            edgedata_json = self.parse_edgedata_to_json(combined_edgedata_raw)
            
            # Save JSON files
            with open(tripinfo_json_file, 'w', encoding='utf-8') as f:
                json.dump(tripinfo_json, f, indent=2, ensure_ascii=False)
            
            with open(edgedata_json_file, 'w', encoding='utf-8') as f:
                json.dump(edgedata_json, f, indent=2, ensure_ascii=False)
            
            # Prepare metadata
            metadata = {
                "total_vehicles": tripinfo_json.get("simulation_info", {}).get("total_vehicles", 0),
                "total_edges": edgedata_json.get("simulation_info", {}).get("total_edges", 0),
                "trip_attributes_count": len(tripinfo_json.get("trip_attributes", {})),
                "emissions_count": len(tripinfo_json.get("emissions", {})),
                "edge_statistics_count": len(edgedata_json.get("edge_statistics", {}))
            }
            
            msg = f"Successfully parsed simulation results. Generated {metadata['trip_attributes_count']} trip attributes, {metadata['emissions_count']} emission metrics, and {metadata['edge_statistics_count']} edge statistics."
            # print(f"[AgentSUMO] result_analyzer_tool 완료: {msg}")
            
            return {
                "status": "success",
                "tripinfo_json": str(tripinfo_json_file),
                "edgedata_json": str(edgedata_json_file),
                "metadata": metadata,
                "message": msg
            }
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"❌ result_analyzer_tool 실패: {e}")
            logger.error(f"상세 에러:\n{error_detail}")
            return {
                "status": "error", 
                "message": str(e),
                "detail": error_detail  # 상세 에러 포함
            }
