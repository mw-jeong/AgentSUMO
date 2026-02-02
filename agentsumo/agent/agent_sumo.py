"""
AgentSUMO - AI Agent for SUMO Simulations

Version 0.1: Basic version with chat + tool calling
"""

import anthropic
from typing import List, Dict, Any, Optional, Callable
import json
import logging
import re

from agentsumo.client import SUMOMCPClient
from agentsumo.core import AgentSUMOConfig
from agentsumo.agent.prompts import PromptBuilder


logger = logging.getLogger("agentsumo.agent")


class AgentSUMO:
    """
    Claude + MCP 기반 대화형 SUMO 시뮬레이션 Agent
    
    Version 0.2: Self-Adaptive Prompting
    - Multi-turn conversation
    - Tool calling via MCP
    - State tracking
    - Self-adaptive reasoning (Simple/Complex/Agentic)
    - Prompt caching (90% cost reduction)
    
    Features:
    - Claude가 스스로 task complexity를 판단
    - 적절한 reasoning mode 자동 선택
    - Chain-of-Thought for complex tasks
    - Extended Thinking for agentic tasks
    """
    
    def __init__(
        self,
        model: str = None,
        max_tokens: int = 4096,
        enable_logging: bool = True,
        enable_debug: bool = False,
        interface: str = "cli",
        db_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        enable_sumo_mcp: bool = True,
        inject_state: bool = True  # [임시] SUMOLanguageExpert용 - 나중에 제거
    ):
        """
        Args:
            model: Claude 모델 (기본: config.DEFAULT_MODEL)
            max_tokens: 최대 응답 토큰
            enable_logging: 로깅 활성화
            enable_debug: 디버그 모드 (raw response 표시)
            interface: 실행 환경 ("cli" or "web")
            db_path: SQLite DB 경로 (None이면 기본 경로에서 자동 탐색)
            system_prompt: 커스텀 시스템 프롬프트 (None이면 unified_system.md 사용)
            enable_sumo_mcp: SUMO MCP 활성화 여부 (False면 SQLite만 사용)
            inject_state: [임시] SUMOLanguageExpert 실험용 - 나중에 제거 예정
                         State context를 유저 메시지에 주입할지 여부 (기본: True)
                         Text-to-SQL 실험처럼 state가 불필요한 경우 False로 설정
        """
        self.debug = enable_debug
        self.interface = interface
        self._init_db_path = db_path  # start()에서 사용
        self._custom_system_prompt = system_prompt  # 커스텀 시스템 프롬프트
        self._enable_sumo_mcp = enable_sumo_mcp  # SUMO MCP 활성화 여부
        self._inject_state = inject_state  # [임시] State 주입 여부 - SUMOLanguageExpert용
        # Claude API 초기화
        self.claude = anthropic.Anthropic(
            api_key=AgentSUMOConfig.get_claude_api_key()
        )
        
        # 설정
        self.model = model or AgentSUMOConfig.DEFAULT_MODEL
        self.max_tokens = max_tokens
        
        # 로깅
        if enable_logging:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s [%(levelname)s] %(message)s'
            )
        
        # 다중 MCP Clients
        self.mcp_clients: Dict[str, Any] = {
            "sumo": None,     # SUMO MCP Server (필수)
            "sqlite": None    # SQLite MCP Server (선택적)
        }
        self.tools: List[Dict] = []
        
        # 대화 이력 (공식 Multi-turn 패턴)
        self.conversation_history: List[Dict[str, Any]] = []
        
        # 상태 추적 (SQLite 지원 확장)
        self.simulation_state = {
            "current_network": None,
            "baseline_network": None,     # 원본 네트워크 (정책 비교용)
            "current_routes": None,
            "last_results": None,
            "current_db": None,           # SQLite DB 경로
            "sqlite_enabled": False,      # SQLite MCP 활성화 상태
            "simulations": []             # DB에 저장된 시뮬레이션 목록
        }
        
        # Prompt Builder (동적 프롬프트 생성)
        self.prompt_builder = PromptBuilder()

        # Progress callback for real-time updates (optional)
        self._progress_callback: Optional[Callable[[str, str], None]] = None

        logger.info("AgentSUMO 초기화 완료")

    def set_progress_callback(self, callback: Callable[[str, str], None]):
        """
        Set a callback for progress updates during tool execution.

        Args:
            callback: Function that takes (tool_name, status) as arguments
                     status can be: "started", "completed", "error"
        """
        self._progress_callback = callback

    def _emit_progress(self, tool_name: str, status: str, message: str = None):
        """Emit progress update if callback is set"""
        if self._progress_callback:
            try:
                self._progress_callback(tool_name, status, message)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    async def start(self, db_path: Optional[str] = None):
        """
        Agent 시작 및 MCP 연결

        Args:
            db_path: SQLite DB 경로 (None이면 기본 경로에서 자동 탐색)

        작업:
        1. SUMO MCP Client 연결 (필수)
        2. SQLite MCP Client 연결 (db_path가 있고 파일 존재 시 자동 활성화)
        3. Tools 로드 및 통합
        4. Claude tools 형식으로 변환
        """
        from pathlib import Path as PathlibPath

        logger.info("🚀 AgentSUMO 시작...")

        # 1. SUMO MCP 연결 (enable_sumo_mcp=True일 때만)
        sumo_tools = []
        if self._enable_sumo_mcp:
            logger.info("SUMO MCP Server 연결 중...")
            self.mcp_clients["sumo"] = SUMOMCPClient()
            await self.mcp_clients["sumo"].__aenter__()

            sumo_tools = await self.mcp_clients["sumo"].list_tools()
            logger.info(f"✅ SUMO MCP: {len(sumo_tools)} tools")
        else:
            logger.info("⏭️ SUMO MCP 비활성화 (SQLite 전용 모드)")

        # 2. SQLite MCP 연결
        # db_path가 없으면 기본 경로에서 자동 탐색
        sqlite_tools = []

        if db_path is None:
            # 기본 경로에서 DB 파일 자동 탐색
            try:
                from agentsumo.server.utils.path_utils import get_output_path

                analysis_dir = get_output_path("output/analysis")

                if analysis_dir.exists():
                    db_files = list(analysis_dir.glob("*.db"))

                    if db_files:
                        # 가장 최근에 수정된 DB 파일 선택
                        latest_db = max(db_files, key=lambda p: p.stat().st_mtime)
                        db_path = str(latest_db)
                        logger.info(f"📊 기존 DB 파일 발견: {latest_db.name}")
                    else:
                        logger.info("📊 SQLite MCP: 기존 DB 파일 없음. DB 생성 후 자동 활성화됩니다.")
                else:
                    logger.info("📊 SQLite MCP: analysis 디렉토리 없음. DB 생성 후 자동 활성화됩니다.")

            except Exception as e:
                logger.warning(f"⚠️ SQLite MCP 자동 탐색 실패: {e}. 계속 진행합니다.")

        # db_path가 있고 파일이 존재하면 SQLite 자동 활성화
        if db_path and PathlibPath(db_path).exists():
            try:
                from agentsumo.client.sqlite_mcp_client import SQLiteMCPClient

                logger.info(f"SQLite MCP Server 연결 중... (DB: {db_path})")
                self.mcp_clients["sqlite"] = SQLiteMCPClient(db_path)
                await self.mcp_clients["sqlite"].__aenter__()

                sqlite_tools = await self.mcp_clients["sqlite"].list_tools()

                self.simulation_state["sqlite_enabled"] = True
                self.simulation_state["current_db"] = db_path

                logger.info(f"✅ SQLite MCP: {len(sqlite_tools)} tools")

            except Exception as e:
                logger.error(f"SQLite MCP 연결 실패: {e}. 계속 진행합니다.")
        elif db_path:
            logger.warning(f"⚠️ DB 파일이 존재하지 않습니다: {db_path}")
        
        # 3. Tools 통합
        all_mcp_tools = sumo_tools + sqlite_tools
        self.tools = self._convert_mcp_to_claude_tools(all_mcp_tools)
        
        logger.info(f"✅ 총 {len(self.tools)}개 도구 로드 완료")
        logger.info("✅ AgentSUMO 준비 완료!\n")
    
    async def close(self):
        """Agent 종료 - 모든 MCP 연결 종료"""
        logger.info("AgentSUMO 종료 중...")
        
        import asyncio
        
        for name, client in self.mcp_clients.items():
            if client:
                try:
                    # Timeout 5초로 종료 시도
                    await asyncio.wait_for(
                        client.__aexit__(None, None, None),
                        timeout=5.0
                    )
                    logger.info(f"✅ {name} MCP 연결 종료")
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️  {name} MCP 종료 timeout (무시)")
                except Exception as e:
                    logger.warning(f"⚠️  {name} MCP 종료 오류 (무시): {e}")
        
        logger.info("👋 AgentSUMO 종료 완료")
    
    async def __aenter__(self):
        """Context manager 진입"""
        await self.start(db_path=self._init_db_path)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        await self.close()
        return False
    
    def _convert_mcp_to_claude_tools(self, mcp_tools) -> List[Dict]:
        """
        MCP tools를 Claude tools 형식으로 변환
        
        Claude Tool Schema:
        {
            "name": str,
            "description": str,
            "input_schema": dict (JSON Schema)
        }
        """
        claude_tools = []
        
        for tool in mcp_tools:
            claude_tool = {
                "name": tool.name,
                "description": tool.description or f"Tool: {tool.name}",
                "input_schema": tool.inputSchema
            }
            claude_tools.append(claude_tool)
        
        logger.debug(f"Converted {len(claude_tools)} tools")
        return claude_tools
    
    async def chat(self, user_message: str) -> str:
        """
        사용자와 대화 (Multi-turn + Self-Adaptive Prompting)
        
        Claude가 스스로 task complexity를 판단하고 적절한 reasoning mode 선택.
        
        Args:
            user_message: 사용자 메시지
            
        Returns:
            str: Agent 응답
        """
        import time
        start_time = time.time()
        
        logger.info(f"\n👤 User: {user_message}")
        
        # 0. SQLite MCP 자동 활성화 체크 (DB 생성 후 자동 연결)
        await self._check_and_enable_sqlite_if_needed()
        
        # 1. State context를 유저 메시지에 추가 (Anthropic 캐싱 최적화)
        # [임시] inject_state=False면 state 주입 안 함 (SUMOLanguageExpert 실험용)
        if self._inject_state:
            state_context = self.prompt_builder.format_context(self.simulation_state)
            message_with_context = f"{state_context}\n\n---\n\n{user_message}"
        else:
            message_with_context = user_message

        self.conversation_history.append({
            "role": "user",
            "content": message_with_context
        })

        # 2. Claude 호출 (시스템 프롬프트는 고정, state는 유저 메시지에)
        prompt_start = time.time()
        if self._custom_system_prompt:
            system_prompt = self._custom_system_prompt
        else:
            system_prompt = self.prompt_builder.build_unified_prompt(
                interface=self.interface
            )
        prompt_time = time.time() - prompt_start
        if prompt_time > 0.1:
            logger.debug(f"프롬프트 빌드 시간: {prompt_time:.2f}초")

        claude_start = time.time()
        response = self._call_claude(system_prompt)
        claude_time = time.time() - claude_start
        logger.debug(f"Claude API 호출 시간: {claude_time:.2f}초")
        
        # Debug: Raw response 출력
        if self.debug:
            self._debug_print_response(response)
        
        # 3. Tool use 처리
        if response.stop_reason == "tool_use":
            tool_start = time.time()
            result = await self._handle_tool_use(response)
            tool_time = time.time() - tool_start
            logger.debug(f"Tool 처리 시간: {tool_time:.2f}초")
            total_time = time.time() - start_time
            logger.info(f"총 응답 시간: {total_time:.2f}초")
            return result
        
        # 4. 일반 텍스트 응답 (모든 content blocks 처리)
        assistant_text = self._extract_text_from_response(response)
        
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content
        })
        
        total_time = time.time() - start_time
        logger.info(f"AgentSUMO: {assistant_text[:100]}...")
        logger.info(f"총 응답 시간: {total_time:.2f}초 (Claude: {claude_time:.2f}초)")
        
        return assistant_text
    
    def _call_claude(self, system_prompt: str = None):
        """
        Claude API 호출 (Prompt Caching + Self-Adaptive Prompting)
        
        Features:
        - Prompt Caching: 90% 비용 절감
        - Self-Adaptive: Claude가 스스로 task complexity 판단
        - Unified Prompt: 모든 reasoning modes 포함
        
        공식 문서: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
        
        Args:
            system_prompt: 이미 빌드된 시스템 프롬프트 (None이면 새로 빌드)
        """
        # Unified self-adaptive system prompt (state 제외 - 유저 메시지에 포함)
        if system_prompt is None:
            if self._custom_system_prompt:
                system_prompt = self._custom_system_prompt
            else:
                system_prompt = self.prompt_builder.build_unified_prompt(
                    interface=self.interface
                )
        
        # System prompt with caching (5분간 캐시)
        system_config = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}  # ✅ 캐싱!
            }
        ]
        
        # Extended Thinking 설정 (필수!)
        # Prompt engineering만으로는 한계 - API 파라미터 필요
        # System Prompt가 "언제 사용할지" guide, API가 "사용 가능하게" enable
        thinking_config = None
        if "claude-sonnet-4" in self.model or "claude-opus-4" in self.model:
            thinking_budget = min(10000, self.max_tokens - 1000)
            if thinking_budget > 1000:
                thinking_config = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget
                }
        
        # API 호출 파라미터 구성
        api_params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_config,
            "tools": self.tools,
            "messages": self.conversation_history
        }

        # Extended Thinking은 지원하는 모델에서만 추가 (Sonnet 4, Opus 4)
        if thinking_config is not None:
            api_params["thinking"] = thinking_config

        response = self.claude.messages.create(**api_params)
        
        return response
    
    async def _handle_tool_use(self, response) -> str:
        """
        Tool use 처리 (공식 패턴)
        
        1. Tool 실행
        2. 결과를 conversation에 추가
        3. Claude에 다시 전달
        """
        tool_results = []
        
        # Tool 실행
        for content in response.content:
            if content.type == "tool_use":
                logger.info(f"  🔧 도구 실행: {content.name}")
                logger.debug(f"     파라미터: {content.input}")

                # Emit progress: tool started
                self._emit_progress(content.name, "started", f"Executing {content.name}...")

                try:
                    # MCP Client로 실행 (자동으로 적절한 client 선택)
                    result = await self._route_tool_call(
                        content.name,
                        content.input
                    )
                    
                    # 상태 업데이트 (간단한 버전)
                    self._update_state(content.name, result)
                    
                    # Tool 결과 확인 및 에러 체크
                    result_content = str(result.content[0].text)
                    
                    # SQLite 도구의 에러 메시지 확인 (Database error, Error: 등)
                    sqlite_tool_names = ["query", "read_query", "list_tables", "describe_table", "append_insight"]
                    if content.name in sqlite_tool_names:
                        # SQLite 도구는 "Database error: ..." 또는 "Error: ..." 형식으로 에러 반환
                        if result_content.startswith("Database error:") or result_content.startswith("Error:"):
                            error_msg = result_content
                            logger.error(f"     ❌ SQLite Tool 에러: {error_msg}")
                            # 에러 메시지를 명확하게 전달
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": error_msg,
                                "is_error": True
                            })
                        else:
                            # 성공한 경우
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result_content
                            })
                            logger.info(f"     ✅ 완료")
                            self._emit_progress(content.name, "completed", f"{content.name} completed successfully")
                    else:
                        # 일반 도구: JSON 파싱하여 status 확인
                        try:
                            result_parsed = json.loads(result_content)
                            # dict인 경우만 status 체크, list나 다른 타입은 성공으로 처리
                            if isinstance(result_parsed, dict) and result_parsed.get("status") == "error":
                                error_msg = result_parsed.get("message", "Unknown error")
                                logger.error(f"     ❌ Tool 에러: {error_msg}")
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": f"Error: {error_msg}",
                                    "is_error": True
                                })
                            else:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": result_content
                                })
                                logger.info(f"     ✅ 완료")
                                self._emit_progress(content.name, "completed", f"{content.name} completed successfully")

                                # sumo_runner 실행 후 자동으로 DB 생성
                                if content.name == "sumo_runner":
                                    await self._auto_create_db_after_simulation(result)
                        except json.JSONDecodeError:
                            # JSON이 아닌 경우 그대로 전달
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result_content
                            })
                            logger.info(f"     ✅ 완료")
                            self._emit_progress(content.name, "completed", f"{content.name} completed")

                except Exception as e:
                    logger.error(f"     ❌ 예외 발생: {e}")
                    # Emit progress: tool error
                    self._emit_progress(content.name, "error", str(e))
                    
                    # 에러도 결과로 전달
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content.id,
                        "content": f"Error: {str(e)}",
                        "is_error": True
                    })
        
        # Conversation history 업데이트
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content  # Tool use 포함
        })
        
        self.conversation_history.append({
            "role": "user",
            "content": tool_results  # Tool 결과
        })
        
        # 결과와 함께 다시 Claude 호출
        final_response = self._call_claude()
        
        # Debug: Raw response 출력
        if self.debug:
            self._debug_print_response(final_response)
        
        # Tool use가 연쇄적으로 일어날 수 있음
        if final_response.stop_reason == "tool_use":
            return await self._handle_tool_use(final_response)
        
        # 최종 텍스트 응답 (모든 content blocks 처리, thinking 포함!)
        final_text = self._extract_text_from_response(final_response)
        
        self.conversation_history.append({
            "role": "assistant",
            "content": final_response.content
        })
        
        logger.info(f"🤖 AgentSUMO: {final_text[:100]}...")
        
        return final_text
    
    async def _route_tool_call(self, tool_name: str, tool_input: dict):
        """
        Tool 호출을 적절한 MCP client로 라우팅

        Args:
            tool_name: Tool name
            tool_input: Tool arguments

        Returns:
            Tool execution result
        """
        # SQLite MCP tools
        sqlite_tool_names = ["query", "read_query", "list_tables", "describe_table", "append_insight"]

        if tool_name in sqlite_tool_names:
            if not self.mcp_clients.get("sqlite") or not self.mcp_clients["sqlite"].is_connected:
                raise RuntimeError(
                    f"SQLite MCP가 연결되지 않았습니다. "
                    f"Tool '{tool_name}'를 사용하려면 먼저 SQLite MCP를 활성화하세요."
                )

            logger.debug(f"  → SQLite MCP로 라우팅: {tool_name}")
            return await self.mcp_clients["sqlite"].call_tool(tool_name, tool_input)

        # SUMO MCP tools
        else:
            logger.debug(f"  → SUMO MCP로 라우팅: {tool_name}")
            return await self.mcp_clients["sumo"].call_tool(tool_name, tool_input)

    def _update_state(self, tool_name: str, result):
        """
        상태 업데이트 (SQLite 지원 포함)
        """
        try:
            # MCP 응답 형식 확인
            if not result.content or len(result.content) == 0:
                logger.warning(f"⚠️ {tool_name}: result.content가 비어있음")
                return
            
            content_str = str(result.content[0].text)
            logger.debug(f"🔍 {tool_name} 응답 내용 (처음 200자): {content_str[:200]}")
            
            # SQLite tools that return list format (not dict) - skip state update
            sqlite_list_tools = ["read_query", "list_tables", "describe_table"]
            if tool_name in sqlite_list_tools:
                # These tools return list of dicts, not a single dict
                # State update is not needed for these tools
                logger.debug(f"   {tool_name}는 리스트 형식 반환 (상태 업데이트 불필요)")
                return
            
            # Try JSON parsing first
            try:
                result_dict = json.loads(content_str)
            except json.JSONDecodeError:
                # If JSON parsing fails, try ast.literal_eval for Python dict strings
                # This handles SQLite query results that return Python dict format
                try:
                    import ast
                    parsed = ast.literal_eval(content_str)
                    # Check if it's a list (SQLite query results)
                    if isinstance(parsed, list):
                        logger.debug(f"✅ {tool_name}: 리스트 형식 반환 (상태 업데이트 불필요)")
                        return
                    result_dict = parsed
                    logger.debug(f"✅ {tool_name}: Python dict 파싱 성공 (ast.literal_eval)")
                except (ValueError, SyntaxError) as e:
                    # If both fail, log and skip state update (non-critical)
                    logger.warning(f"⚠️ {tool_name}: JSON/Python dict 파싱 실패 - {e}")
                    logger.debug(f"   원본 내용: {content_str[:500]}")
                    return
            
            if tool_name == "net_generate":
                net_file = result_dict.get("net_file")
                logger.debug(f"🔍 net_generate 결과: {result_dict}")
                
                if not net_file:
                    logger.warning(f"⚠️ net_generate: net_file이 None입니다. 전체 결과: {result_dict}")
                    return
                
                self.simulation_state["current_network"] = net_file
                # Set baseline if not already set (first network generation)
                if not self.simulation_state.get("baseline_network"):
                    self.simulation_state["baseline_network"] = net_file
                    logger.info(f"📌 Baseline network set: {net_file}")
                else:
                    logger.info(f"🔄 Current network updated: {net_file}")
                
            elif tool_name == "trip_generate":
                self.simulation_state["current_routes"] = result_dict.get("route_file")
                
            elif tool_name in ["reduce_lanes_tool", "edge_edit_tool", "speed_limit_edit_tool"]:
                # Policy tools update current_network (but keep baseline unchanged)
                modified_net = result_dict.get("net_file")
                if modified_net:
                    self.simulation_state["current_network"] = modified_net
                    logger.info(f"🔄 Policy applied: current_network = {modified_net}")
                    logger.info(f"📌 Baseline remains: {self.simulation_state.get('baseline_network')}")
                
            elif tool_name == "sumo_runner":
                self.simulation_state["last_results"] = result_dict.get("output_files")
                
            elif tool_name == "xml_to_sqlite_tool":
                # SQLite DB 생성 시
                db_file = result_dict.get("db_file")
                simulation_id = result_dict.get("simulation_id")
                metadata = result_dict.get("metadata", {})
                
                self.simulation_state["current_db"] = db_file
                
                # 시뮬레이션 목록 업데이트
                sim_info = {
                    "simulation_id": simulation_id,
                    "trip_count": metadata.get("trip_count", 0)
                }
                
                # 중복 제거 후 추가
                self.simulation_state["simulations"] = [
                    s for s in self.simulation_state.get("simulations", [])
                    if s.get("simulation_id") != simulation_id
                ]
                self.simulation_state["simulations"].append(sim_info)
                
                logger.info(f"📊 State 업데이트: SQLite DB = {db_file}")
                logger.info(f"   현재 DB에 {len(self.simulation_state['simulations'])}개 시뮬레이션")
        
        except Exception as e:
            logger.debug(f"상태 업데이트 실패 (무시): {e}")
    
    async def _auto_create_db_after_simulation(self, sumo_result):
        """
        sumo_runner 실행 후 자동으로 SQLite DB 생성
        
        Note: SQLite MCP 활성화는 다음 chat() 호출 시 자동으로 처리됩니다.
        """
        try:
            # 결과에서 output_files 추출
            content_str = str(sumo_result.content[0].text)
            result_dict = json.loads(content_str)
            output_files = result_dict.get("output_files", [])
            
            if len(output_files) < 3:
                return
            
            # xml_to_sqlite_tool 자동 호출 및 상태 업데이트
            db_result = await self._route_tool_call(
                "xml_to_sqlite_tool",
                {
                    "tripinfo_xml": output_files[0],
                    "edgedata_xml": output_files[1],
                    "edgedata_emission_xml": output_files[2]
                }
            )
            self._update_state("xml_to_sqlite_tool", db_result)

            # 같은 턴에서 SQLite 쿼리 사용 가능하도록 즉시 활성화
            await self._check_and_enable_sqlite_if_needed()

        except Exception as e:
            logger.debug(f"DB 자동 생성 실패 (무시): {e}")
    
    def _debug_print_response(self, response):
        """
        Debug 모드: Claude raw response 출력
        
        Args:
            response: Claude API response
        """
        print("\n" + "🐛"*35)
        print("DEBUG: Claude Raw Response")
        print("🐛"*35)
        
        print(f"\n📊 Response Info:")
        print(f"  - Model: {response.model}")
        print(f"  - Stop Reason: {response.stop_reason}")
        print(f"  - Usage: {response.usage}")
        
        print(f"\n📦 Content Blocks ({len(response.content)}):")
        for i, block in enumerate(response.content, 1):
            print(f"\n  Block {i}:")
            print(f"    Type: {block.type if hasattr(block, 'type') else 'unknown'}")
            
            if hasattr(block, 'type'):
                if block.type == "text":
                    preview = block.text[:200] if len(block.text) > 200 else block.text
                    print(f"    Text: {preview}...")
                
                elif block.type == "thinking":
                    preview = block.thinking[:200] if len(block.thinking) > 200 else block.thinking
                    print(f"    Thinking: {preview}...")
                
                elif block.type == "tool_use":
                    print(f"    Tool: {block.name}")
                    print(f"    Args: {block.input}")
        
        print("\n" + "🐛"*35 + "\n")
    
    def _extract_text_from_response(self, response) -> str:
        """
        Claude 응답에서 텍스트 추출 (thinking 블록 제외)
        
        Claude의 응답은 여러 content blocks로 구성될 수 있음:
        - text blocks: 일반 응답
        - thinking blocks: <thinking> 또는 <extended_thinking> (내부 추론, 사용자에게 표시 안 함)
        
        Args:
            response: Claude API response
            
        Returns:
            사용자에게 표시할 응답 문자열 (thinking 블록 제외)
        """
        parts = []
        
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "text":
                    # 일반 텍스트만 추가
                    parts.append(block.text)
                
                # thinking 블록은 제외 (내부 추론이므로 사용자에게 표시하지 않음)
                # elif block.type == "thinking":
                #     pass
        
        # 텍스트 블록만 결합
        full_text = "\n\n".join(parts)
        
        # 텍스트 안에 <thinking> 또는 <extended_thinking> 태그가 있으면 제거
        full_text = re.sub(r'<thinking>.*?</thinking>', '', full_text, flags=re.DOTALL)
        full_text = re.sub(r'<extended_thinking>.*?</extended_thinking>', '', full_text, flags=re.DOTALL)
        
        return full_text.strip()
    
    # 기존 _get_system_prompt()와 _get_context_summary()는
    # PromptBuilder로 대체되었습니다
    
    def get_state(self) -> Dict[str, Any]:
        """현재 상태 조회"""
        return {
            "simulation_state": self.simulation_state,
            "conversation_turns": len(self.conversation_history) // 2,
            "tools_available": len(self.tools),
            "model": self.model
        }
    
    def reset_conversation(self):
        """대화 이력만 리셋 (상태 유지)"""
        self.conversation_history = []
        logger.info("대화 이력 리셋")
    
    async def _check_and_enable_sqlite_if_needed(self):
        """
        SQLite MCP 첫 활성화
        
        xml_to_sqlite_tool로 DB 생성 후, 다음 chat()에서 자동으로 활성화.
        
        IMPORTANT: 재연결은 하지 않음! 한 세션 = 한 DB
        - 같은 지역 여러 정책 → 같은 DB에 누적 (재연결 불필요)
        - 다른 지역 → 새 세션 시작 (재시작 필요)
        """
        current_db = self.simulation_state.get("current_db")
        sqlite_enabled = self.simulation_state.get("sqlite_enabled", False)
        
        # 이미 활성화됐으면 즉시 skip (성능 최적화)
        if sqlite_enabled:
            return
        
        # DB 있고, 아직 활성화 안 됐으면 → 첫 활성화!
        if current_db:
            logger.info(f"🔄 SQLite MCP 첫 활성화 중... (DB: {current_db})")
            
            try:
                from agentsumo.client.sqlite_mcp_client import SQLiteMCPClient
                
                # 새 DB로 연결 (첫 활성화, 재연결 아님!)
                self.mcp_clients["sqlite"] = SQLiteMCPClient(current_db)
                await self.mcp_clients["sqlite"].__aenter__()
                
                # Tools 로드 및 추가
                sqlite_tools = await self.mcp_clients["sqlite"].list_tools()
                new_claude_tools = self._convert_mcp_to_claude_tools(sqlite_tools)
                self.tools.extend(new_claude_tools)
                
                # State 업데이트
                self.simulation_state["sqlite_enabled"] = True
                
                logger.info(f"✅ SQLite MCP 활성화 완료! ({len(sqlite_tools)} tools 추가)")
                logger.info(f"   → 이제 상세 SQL 쿼리가 가능합니다.")
                
            except Exception as e:
                logger.error(f"❌ SQLite MCP 활성화 실패: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # 실패해도 계속 진행 (graceful degradation)
    
    def reset_all(self):
        """모든 상태 리셋"""
        self.conversation_history = []
        self.simulation_state = {
            "current_network": None,
            "baseline_network": None,     # 원본 네트워크 (정책 비교용)
            "current_routes": None,
            "last_results": None,
            "current_db": None,
            "sqlite_enabled": False,
            "simulations": []
        }
        logger.info("전체 상태 리셋")

