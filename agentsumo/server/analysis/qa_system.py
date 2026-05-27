"""
Q&A system for SUMO MCP Server.
"""

import json
from typing import Dict, Any

from agentsumo.server.settings.settings import analysis_settings
from .report_generator import ReportGenerator


class QASystem:
    """Q&A system class for SUMO simulation results."""
    
    def __init__(self):
        self.settings = analysis_settings
        self.report_generator = ReportGenerator()
    
    def generate_qa_answer(self, context: dict) -> str:
        """Generate answer to user question based on simulation data."""
        
        question = context["question"].lower()
        metrics = context["metrics"]
        
        # Helper functions
        def format_time(seconds):
            if seconds < 60:
                return f"{seconds:.1f}초"
            elif seconds < 3600:
                return f"{seconds/60:.1f}분"
            else:
                return f"{seconds/3600:.1f}시간"
        
        def format_distance(meters):
            if meters < 1000:
                return f"{meters:.1f}m"
            else:
                return f"{meters/1000:.1f}km"
        
        def format_speed(mps):
            kmph = mps * self.settings.SPEED_CONVERSION
            return f"{kmph:.1f} km/h"
        
        def format_emission(mg):
            if mg > self.settings.EMISSION_CONVERSION:
                return f"{mg/self.settings.EMISSION_CONVERSION:.1f} g"
            else:
                return f"{mg:.1f} mg"
        
        # Answer based on question type
        if "co2" in question or "배출량" in question:
            if "높으면" in question or "나쁜" in question or "영향" in question:
                return "네, CO2 배출량이 높으면 환경에 좋지 않습니다. CO2는 주요 온실가스로 기후변화의 원인이 됩니다. 현재 시뮬레이션에서 평균 CO2 배출량은 차량당 " + format_emission(metrics["emission_metrics"].get("CO2_abs", {}).get("mean", 0)) + "입니다."
            
            co2_data = metrics["emission_metrics"].get("CO2_abs", {})
            if co2_data:
                return f"현재 시뮬레이션의 CO2 배출량 정보:\n- 평균: {format_emission(co2_data['mean'])}/차량\n- 중간값: {format_emission(co2_data['median'])}/차량\n- 최소: {format_emission(co2_data['min'])}/차량\n- 최대: {format_emission(co2_data['max'])}/차량"
        
        elif "혼잡" in question or "congestion" in question:
            if "가장" in question or "어디" in question:
                waiting_data = metrics["traffic_metrics"].get("waitingTime", {})
                if waiting_data and waiting_data.get("max_edge"):
                    return f"가장 혼잡한 도로는 {waiting_data['max_edge']} 구간입니다. 이 구간의 대기 시간은 {format_time(waiting_data['max'])}로 가장 길게 나타났습니다."
            
            waiting_data = metrics["traffic_metrics"].get("waitingTime", {})
            if waiting_data:
                return f"전체적인 교통 혼잡 상황:\n- 평균 대기 시간: {format_time(waiting_data['mean'])}\n- 중간값 대기 시간: {format_time(waiting_data['median'])}\n- 최대 대기 시간: {format_time(waiting_data['max'])} ({waiting_data.get('max_edge', 'N/A')} 구간)"
        
        elif "속도" in question or "speed" in question:
            speed_data = metrics["traffic_metrics"].get("speed", {})
            if speed_data:
                return f"속도 정보:\n- 평균 속도: {format_speed(speed_data['mean'])}\n- 중간값 속도: {format_speed(speed_data['median'])}\n- 최저 속도: {format_speed(speed_data['min'])} ({speed_data.get('min_edge', 'N/A')} 구간)\n- 최고 속도: {format_speed(speed_data['max'])} ({speed_data.get('max_edge', 'N/A')} 구간)"
        
        elif "시간" in question or "duration" in question:
            duration_data = metrics["trip_metrics"].get("duration", {})
            if duration_data:
                return f"이동 시간 정보:\n- 평균 이동 시간: {format_time(duration_data['mean'])}\n- 중간값 이동 시간: {format_time(duration_data['median'])}\n- 최단 이동 시간: {format_time(duration_data['min'])}\n- 최장 이동 시간: {format_time(duration_data['max'])}"
        
        elif "거리" in question or "distance" in question or "경로" in question:
            route_data = metrics["trip_metrics"].get("routeLength", {})
            if route_data:
                return f"이동 거리 정보:\n- 평균 이동 거리: {format_distance(route_data['mean'])}\n- 중간값 이동 거리: {format_distance(route_data['median'])}\n- 최단 이동 거리: {format_distance(route_data['min'])}\n- 최장 이동 거리: {format_distance(route_data['max'])}"
        
        elif "차량" in question or "vehicle" in question:
            total_vehicles = metrics["simulation_info"]["total_vehicles"]
            return f"시뮬레이션에 참여한 총 차량 수는 {total_vehicles:,}대입니다."
        
        elif "도로" in question or "edge" in question:
            total_edges = metrics["simulation_info"]["total_edges"]
            return f"시뮬레이션 네트워크의 총 도로 구간 수는 {total_edges:,}개입니다."
        
        elif "연료" in question or "fuel" in question:
            fuel_data = metrics["emission_metrics"].get("fuel_abs", {})
            if fuel_data:
                return f"연료 소비량 정보:\n- 평균: {format_emission(fuel_data['mean'])}/차량\n- 중간값: {format_emission(fuel_data['median'])}/차량\n- 최소: {format_emission(fuel_data['min'])}/차량\n- 최대: {format_emission(fuel_data['max'])}/차량"
        
        else:
            # General summary
            return f"""시뮬레이션 결과 요약:

기본 정보:
- 총 차량 수: {metrics['simulation_info']['total_vehicles']:,}대
- 총 도로 구간 수: {metrics['simulation_info']['total_edges']:,}개

교통 상황:
- 평균 속도: {format_speed(metrics['traffic_metrics'].get('speed', {}).get('mean', 0))}
- 평균 대기 시간: {format_time(metrics['traffic_metrics'].get('waitingTime', {}).get('mean', 0))}

환경 영향:
- 평균 CO2 배출량: {format_emission(metrics['emission_metrics'].get('CO2_abs', {}).get('mean', 0))}/차량

더 구체적인 질문이 있으시면 말씀해 주세요!"""
        
        return "죄송합니다. 해당 질문에 대한 답변을 찾을 수 없습니다. 다른 질문을 해주시거나 더 구체적으로 말씀해 주세요."
    
    def answer_question(
        self,
        tripinfo_json: str,
        edgedata_json: str,
        question: str
    ) -> Dict[str, Any]:
        """
        Answer questions about simulation results using JSON data.
        
        Args:
            tripinfo_json: Tripinfo JSON file path
            edgedata_json: Edgedata JSON file path
            question: Question about simulation results (in Korean or English)
            
        Returns:
            Dict[str, Any]: Q&A result with status and answer
        """
        try:
            # print(f"[AgentSUMO] simulation_qa_tool 실행됨")
            # print(f"  - tripinfo_json: {tripinfo_json}")
            # print(f"  - edgedata_json: {edgedata_json}")
            # print(f"  - question: {question}")
            
            # Load JSON files
            # print(f"📊 Loading tripinfo JSON: {tripinfo_json}")
            with open(tripinfo_json, 'r', encoding='utf-8') as f:
                tripinfo_data = json.load(f)
            
            # print(f"📊 Loading edgedata JSON: {edgedata_json}")
            with open(edgedata_json, 'r', encoding='utf-8') as f:
                edgedata_data = json.load(f)
            
            # Extract key metrics for context
            # print("🔍 Extracting key metrics...")
            metrics = self.report_generator.extract_key_metrics(tripinfo_data, edgedata_data)
            
            # Prepare context for Q&A
            context = {
                "question": question,
                "metrics": metrics,
                "tripinfo_data": tripinfo_data,
                "edgedata_data": edgedata_data
            }
            
            # Generate answer using reasoning
            # print("💭 Generating answer...")
            answer = self.generate_qa_answer(context)
            
            # Prepare metadata
            metadata = {
                "question_type": "general" if any(word in question.lower() for word in ["좋은", "나쁜", "영향", "의미"]) else "specific",
                "data_sources_used": ["tripinfo", "edgedata"]
            }
            
            msg = f"Successfully answered question about simulation results."
            # print(f"[AgentSUMO] simulation_qa_tool 완료: {msg}")
            
            return {
                "status": "success",
                "answer": answer,
                "message": msg,
                "metadata": metadata
            }
            
        except Exception as e:
            # print(f"[AgentSUMO] simulation_qa_tool 오류: {e}")
            return {
                "status": "error",
                "answer": None,
                "message": f"QA failed: {str(e)}",
                "metadata": {}
            }
