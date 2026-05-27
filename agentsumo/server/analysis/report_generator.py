"""
Report generation functionality for SUMO MCP Server (Claude-powered version).

This version uses Claude to generate natural language reports from JSON data.
Claude leverages its built-in traffic engineering knowledge without hardcoded thresholds.
"""

import json
import datetime
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from agentsumo.server.utils.path_utils import get_output_path

logger = logging.getLogger("agentsumo.server.report_generator")


class ReportGenerator:
    """Claude-powered report generation class for SUMO simulation results."""
    
    def __init__(self, claude_api_key: Optional[str] = None):
        """
        Initialize report generator with Claude API.
        
        Args:
            claude_api_key: Optional Anthropic API key. If not provided,
                          will try to get from environment variable.
        
        Raises:
            RuntimeError: If Claude API is not available
        """
        self.claude_api_key = claude_api_key
        
        try:
            import anthropic
            
            api_key = claude_api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is required for report generation.\n"
                    "Set environment variable: export ANTHROPIC_API_KEY='your-api-key'"
                )
            
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info("✅ Claude API 초기화 성공")
            
        except ImportError:
            raise RuntimeError(
                "anthropic package is required for report generation.\n"
                "Install: pip install anthropic"
            )
    
    def _generate_report_with_claude(self, tripinfo_data: dict, edgedata_data: dict) -> str:
        """
        Generate report using Claude API.
        
        Args:
            tripinfo_data: Parsed tripinfo JSON data
            edgedata_data: Parsed edgedata JSON data
            
        Returns:
            str: Natural language report in Markdown format
        """
        # Prepare simplified data for Claude (avoid token overflow)
        summary_data = {
            "simulation_info": tripinfo_data.get("simulation_info", {}),
            "trip_attributes_summary": {},
            "emissions_summary": {},
            "edge_statistics_summary": {}
        }
        
        # Extract key statistics (mean, median, min, max) only
        for attr, data in tripinfo_data.get("trip_attributes", {}).items():
            stats = data.get("statistics", {})
            summary_data["trip_attributes_summary"][attr] = {
                "mean": stats.get("mean"),
                "median": stats.get("median"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "unit": data.get("metadata", {}).get("unit"),
                "description": data.get("metadata", {}).get("description")
            }
        
        for attr, data in tripinfo_data.get("emissions", {}).items():
            stats = data.get("statistics", {})
            summary_data["emissions_summary"][attr] = {
                "mean": stats.get("mean"),
                "median": stats.get("median"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "unit": data.get("metadata", {}).get("unit"),
                "description": data.get("metadata", {}).get("description")
            }
        
        for attr, data in edgedata_data.get("edge_statistics", {}).items():
            stats = data.get("statistics", {})
            summary_data["edge_statistics_summary"][attr] = {
                "mean": stats.get("mean"),
                "min": stats.get("min"),
                "max": stats.get("max"),
                "min_edge": stats.get("min_edge"),
                "max_edge": stats.get("max_edge"),
                "unit": data.get("metadata", {}).get("unit"),
                "description": data.get("metadata", {}).get("description")
            }
        
        # Create prompt for Claude (leveraging its built-in traffic engineering knowledge)
        system_prompt = """You are an expert traffic simulation analyst with deep knowledge of urban mobility, transportation engineering, and traffic flow theory.

Generate a comprehensive, natural language report in Korean from SUMO (Simulation of Urban MObility) simulation data.

**Report Structure:**
1. 📊 시뮬레이션 개요 (총 차량, 도로 구간 수, 시뮬레이션 범위)
2. 🚦 교통 흐름 분석 (이동 시간, 거리, 속도, 대기 시간, 시간 손실)
3. 🌱 환경 영향 분석 (CO2, 연료, NOx, PMx 배출량)
4. 📍 주요 병목 구간 및 문제 지점 식별
5. 💡 종합 인사이트 및 개선 권장사항

**Analysis Approach:**
- Apply your traffic engineering expertise to assess traffic performance
- Use your knowledge of Level of Service (LOS), congestion patterns, and emission standards
- Interpret metrics in context (consider network size, vehicle count, simulation duration)
- Identify root causes, not just symptoms
- Suggest specific, actionable improvements based on traffic engineering principles

**Formatting:**
- Clear, professional Korean when user is Korean, English when user is English.
- Convert all units to user-friendly formats (seconds → 분, meters → km, m/s → km/h)
- Clean Markdown structure
- Minimal emojis (section headers only)
- Focus on insights over raw numbers

Your goal is to provide expert analysis that helps users understand traffic conditions and make informed decisions."""

        user_prompt = f"""Analyze this SUMO traffic simulation data and generate a comprehensive expert report:

```json
{json.dumps(summary_data, indent=2, ensure_ascii=False)}
```

Apply your traffic engineering expertise to:
1. Assess overall traffic performance (is this good or problematic?)
2. Identify key bottlenecks and inefficiencies
3. Explain underlying causes using traffic flow principles
4. Provide specific, actionable recommendations for improvement
5. Highlight any notable patterns or anomalies

Be thorough, precise, and professional."""

        try:
            # Call Claude API
            logger.info("Claude API 호출 중...")
            
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            # Extract response
            report = message.content[0].text
            
            # Add metadata footer
            report += f"\n\n---\n"
            report += f"*SUMO 시뮬레이션 결과를 분석한 리포트입니다.*\n"
            report += f"*생성 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            
            logger.info("✅ Claude 기반 리포트 생성 완료")
            return report
            
        except Exception as e:
            logger.error(f"Claude API 호출 실패: {e}")
            raise RuntimeError(f"리포트 생성 실패: {str(e)}")
    
    def generate_report(
        self,
        tripinfo_json: str,
        edgedata_json: str,
        output_dir: str = "output/reports"
    ) -> Dict[str, Any]:
        """
        Generate comprehensive natural language simulation report from JSON data.
        
        Args:
            tripinfo_json: Tripinfo JSON file path
            edgedata_json: Edgedata JSON file path
            output_dir: Output directory for report files
            
        Returns:
            Dict[str, Any]: Report generation result with status and metadata
        """
        try:
            # Create output directory
            output_path = get_output_path(output_dir)
            
            # Load JSON files
            with open(tripinfo_json, 'r', encoding='utf-8') as f:
                tripinfo_data = json.load(f)
            
            with open(edgedata_json, 'r', encoding='utf-8') as f:
                edgedata_data = json.load(f)
            
            # Generate report using Claude (required)
            logger.info("리포트 생성 시작...")
            report_content = self._generate_report_with_claude(tripinfo_data, edgedata_data)
            
            # Save report file
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = output_path / f"simulation_report_{timestamp}.md"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            # Prepare metadata
            metadata = {
                "total_vehicles": tripinfo_data.get("simulation_info", {}).get("total_vehicles", 0),
                "total_edges": edgedata_data.get("simulation_info", {}).get("total_edges", 0),
                "generation_method": "claude",
                "report_length": len(report_content),
                "model": "claude-sonnet-4-20250514"
            }
            
            msg = f"Successfully generated simulation report using Claude (Sonnet 4.0)."
            logger.info(f"✅ {msg}")
            
            return {
                "status": "success",
                "report_file": str(report_file),
                "metadata": metadata,
                "message": msg
            }
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"❌ simulation_report_tool 실패: {e}")
            logger.error(f"상세 에러:\n{error_detail}")
            return {
                "status": "error", 
                "message": str(e),
                "detail": error_detail
            }
    
    def extract_key_metrics(self, tripinfo_data: dict, edgedata_data: dict) -> dict:
        """
        Extract key metrics from tripinfo and edgedata for Q&A system.
        
        Args:
            tripinfo_data: Parsed tripinfo JSON data
            edgedata_data: Parsed edgedata JSON data
            
        Returns:
            dict: Key metrics organized by category
        """
        metrics = {
            "simulation_info": {
                "total_vehicles": tripinfo_data.get("simulation_info", {}).get("total_vehicles", 0),
                "total_edges": edgedata_data.get("simulation_info", {}).get("total_edges", 0)
            },
            "trip_metrics": {},
            "traffic_metrics": {},
            "emission_metrics": {}
        }
        
        # Extract trip metrics
        trip_attrs = tripinfo_data.get("trip_attributes", {})
        for attr_name in ["duration", "routeLength", "timeLoss", "waitingTime"]:
            if attr_name in trip_attrs:
                stats = trip_attrs[attr_name].get("statistics", {})
                metrics["trip_metrics"][attr_name] = {
                    "mean": stats.get("mean", 0),
                    "median": stats.get("median", 0),
                    "min": stats.get("min", 0),
                    "max": stats.get("max", 0)
                }
        
        # Extract traffic metrics from edgedata
        edge_stats = edgedata_data.get("edge_statistics", {})
        for attr_name in ["speed", "density", "waitingTime"]:
            if attr_name in edge_stats:
                stats = edge_stats[attr_name].get("statistics", {})
                metrics["traffic_metrics"][attr_name] = {
                    "mean": stats.get("mean", 0),
                    "median": stats.get("median", 0),
                    "min": stats.get("min", 0),
                    "max": stats.get("max", 0),
                    "min_edge": stats.get("min_edge"),
                    "max_edge": stats.get("max_edge")
                }
        
        # Extract emission metrics
        emissions = tripinfo_data.get("emissions", {})
        for emission_name in ["CO2_abs", "fuel_abs", "NOx_abs", "PMx_abs"]:
            if emission_name in emissions:
                stats = emissions[emission_name].get("statistics", {})
                metrics["emission_metrics"][emission_name] = {
                    "mean": stats.get("mean", 0),
                    "median": stats.get("median", 0),
                    "min": stats.get("min", 0),
                    "max": stats.get("max", 0)
                }
        
        return metrics