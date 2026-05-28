"""
AgentSUMO Prompt Builder

Claude 공식 가이드라인 기반 동적 프롬프트 조립
"""

from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    동적 시스템 프롬프트 생성기
    
    Markdown 템플릿을 조합하여 task type과 context에 맞는
    최적화된 시스템 프롬프트를 생성합니다.
    
    Features:
    - Task type별 adaptive prompting
    - Current state context injection
    - Template caching for performance
    - XML-structured context (Claude 최적화)
    
    Example:
        >>> builder = PromptBuilder()
        >>> prompt = builder.build_system_prompt(
        ...     task_type="complex",
        ...     current_state={"current_network": "gangnam.net.xml"}
        ... )
    """
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Args:
            templates_dir: 템플릿 디렉토리 경로 (기본: 현재 모듈 내 templates/)
        """
        if templates_dir is None:
            # 현재 파일 기준으로 templates 디렉토리 찾기
            current_file = Path(__file__)
            self.templates_dir = current_file.parent / "templates"
        else:
            self.templates_dir = Path(templates_dir)
        
        # 템플릿 캐시 (성능 최적화)
        self._cache: Dict[str, str] = {}
        
        # 프롬프트 빌드 결과 캐시 (성능 최적화)
        self._prompt_cache: Optional[str] = None
        self._cached_state_hash: Optional[str] = None
        
        # 템플릿 디렉토리 존재 확인
        if not self.templates_dir.exists():
            raise FileNotFoundError(
                f"Templates directory not found: {self.templates_dir}"
            )
        
        logger.info(f"PromptBuilder initialized with templates: {self.templates_dir}")
    
    def build_unified_prompt(
        self,
        interface: str = "cli",
        base_prompt: Optional[str] = None
    ) -> str:
        """
        Self-Adaptive Unified System Prompt 생성 (고정 부분만)

        Claude가 스스로 task complexity를 판단하고 적절한 reasoning mode를 선택.
        state는 유저 메시지에 별도로 주입하여 Anthropic 캐싱 효과 극대화.

        Args:
            interface: 실행 환경 ("cli" or "web")
            base_prompt: 커스텀 베이스 프롬프트 (None이면 unified_system.md 사용)

        Returns:
            완성된 unified 시스템 프롬프트 문자열 (state 제외)
        """
        # 캐시 키
        cache_key = f"unified_{interface}_{'custom' if base_prompt else 'default'}"

        # 캐시된 프롬프트가 있으면 재사용
        if self._prompt_cache is not None and self._cached_state_hash == cache_key:
            logger.debug("Using cached prompt")
            return self._prompt_cache

        logger.info("Building unified self-adaptive system prompt")

        if base_prompt:
            prompt = base_prompt
        else:
            sections = []

            # 1. Unified system prompt (Self-Assessment 포함)
            sections.append(self._load_template("unified_system_v2.md"))

            # 2. Interface-specific instructions
            if interface == "cli":
                sections.append(self._get_cli_instructions())
            else:  # web
                sections.append(self._get_web_instructions())

            # 섹션 결합
            prompt = "\n\n".join(sections)

        # 캐시에 저장
        self._prompt_cache = prompt
        self._cached_state_hash = cache_key

        logger.debug(f"Generated unified prompt length: {len(prompt)} characters")

        return prompt

    def _load_template(self, filename: str) -> str:
        """
        템플릿 파일 로드 (캐싱)
        
        Args:
            filename: 템플릿 파일명 (예: "base_system.md")
        
        Returns:
            템플릿 내용
        
        Raises:
            FileNotFoundError: 템플릿 파일이 없는 경우
        """
        if filename not in self._cache:
            path = self.templates_dir / filename
            
            if not path.exists():
                raise FileNotFoundError(f"Template not found: {path}")
            
            self._cache[filename] = path.read_text(encoding='utf-8')
            logger.debug(f"Loaded template: {filename}")
        
        return self._cache[filename]
    
    def format_context(self, state: Dict) -> str:
        """
        현재 상태를 XML 형식으로 포맷 (유저 메시지에 주입용)

        Claude는 XML 구조를 특히 잘 이해함 (공식 권장)
        시스템 프롬프트가 아닌 유저 메시지에 포함하여 캐싱 효과 유지.

        Args:
            state: 시뮬레이션 상태 딕셔너리

        Returns:
            XML 형식의 컨텍스트 문자열
        """
        # 안전한 접근 (기본값 제공)
        network = state.get('current_network', 'Not created')
        baseline = state.get('baseline_network', 'Not set')
        routes = state.get('current_routes', 'Not created')
        last_results = state.get('last_results', 'Not run')
        
        # last_results가 딕셔너리인 경우 상세 정보 추출
        if isinstance(last_results, dict):
            duration = last_results.get('duration', 'Unknown')
            vehicles = last_results.get('vehicles', 'Unknown')
            completed_time = last_results.get('completed_time', 'Unknown')
            
            results_text = f"""
    - Duration: {duration}s
    - Vehicles: {vehicles}
    - Completed: {completed_time}"""
        else:
            results_text = f"\n    {last_results}"
        
        # DB info
        db = state.get("current_db", "None")
        sqlite_enabled = state.get("sqlite_enabled", False)
        simulations = state.get("simulations", [])

        db_text = "None"
        if db and db != "None" and sqlite_enabled:
            sims_list = ", ".join(
                s.get("simulation_id", "")
                for s in simulations
            ) if simulations else "None"
            db_text = f"""
    <path>{db}</path>
    <simulations>{sims_list}</simulations>"""
        
        context = f"""
## Current Simulation State

```xml
<current_context>
  <baseline_network>{baseline}</baseline_network>
  <current_network>{network}</current_network>
  <routes>{routes}</routes>
  <last_simulation>{results_text}
  </last_simulation>
  <analysis_database>{db_text}
  </analysis_database>
</current_context>
```

**IMPORTANT for Policy Comparison:**
- `baseline_network`: Original network for policy comparison (USE THIS for all policy tools!)
- `current_network`: Most recent network (may include policy modifications)
- For policy experiments (reduce_lanes, edge_edit, speed_limit_edit), ALWAYS use `baseline_network` as input!

**If analysis_database is enabled, use SQLite MCP tools (read_query, list_tables) for detailed analysis.**

Use this context to avoid redundant operations and build upon existing work.
"""
        
        return context.strip()
    
    def _get_cli_instructions(self) -> str:
        """CLI 환경 전용 지침"""
        return ""

    def _get_web_instructions(self) -> str:
        """Web 환경 전용 지침"""
        return """
## Web Interface Instructions

### Simulation Options UI — [SIM_OPTIONS] Marker

When user requests a simulation and you need to ask for parameters (area, traffic, duration),
include `[SIM_OPTIONS]` at the END of your response. This triggers an interactive options panel.

Rules:
1. Only use for NEW simulation requests, not for analysis or comparison
2. Place marker at the very END of your message
3. After user submits options, you'll receive a message with all parameters → then execute
4. When showing [SIM_OPTIONS], ALWAYS mention that if the user has real OD data,
   they can click the "Real OD" tab to upload it. Example:
   "실제 OD 데이터를 갖고 계시다면, 오른쪽 상단의 **Real OD** 탭을 클릭하여 업로드할 수 있습니다."

### Map Visualization Markers (CRITICAL)

In web mode, the user has an interactive Mapbox map. Instead of generating PNG images,
use these markers to trigger map actions directly. The markers are parsed by the frontend
and will NOT be shown to the user.

**[HIGHLIGHT_ROAD:road_name]**
Use when user asks about road locations, road details, or "where is X road?"
The frontend will find ALL edges with that road name and highlight them on the map.
No need to call get_edge_ids_from_road_name_tool — just include the road name.

Example:
```
User: "테헤란로가 어디있어?"
Response: "테헤란로 is located in the Gangnam area, running east-west.
[HIGHLIGHT_ROAD:테헤란로]"
```

You can highlight multiple roads: `[HIGHLIGHT_ROAD:테헤란로][HIGHLIGHT_ROAD:강남대로]`

**[SEARCH_LOCATION:location_name]**
Use when user asks about a place, landmark, or address (not a road name).
The frontend will geocode the location, show a marker, and zoom to it.
This works even when no network is loaded — ALWAYS use it for location questions.

Example:
```
User: "강남역이 어디 있어?"
Response: "강남역 is a major subway station in Gangnam-gu, Seoul.
[SEARCH_LOCATION:강남역]"
```

User: "Times Square 위치 알려줘"
Response: "Times Square is in Midtown Manhattan, New York City.
[SEARCH_LOCATION:Times Square, New York]"

**[HIGHLIGHT_EDGES:edge_id1,edge_id2,...]**
Use only when you need to highlight SPECIFIC edge IDs (e.g., after policy application).
Include ALL edge IDs — do not truncate the list.

**[HIGHLIGHT_OD_EDGES:origin_edges|dest_edges]**
Highlight origin and destination edges in different colors after flow generation.
Origins are shown in blue (#39ccff), destinations in red (#ff4444).
Use after flow_generation_tool to visualize which edges are origins vs destinations.

Format: `[HIGHLIGHT_OD_EDGES:oEdge1,oEdge2|dEdge1,dEdge2]`
- Before `|`: comma-separated origin edge IDs (blue)
- After `|`: comma-separated destination edge IDs (red)

Example:
```
[HIGHLIGHT_OD_EDGES:218864491#1,375049565#3|504231011#0,975332778#2]
```

You can get the edge IDs from flow_generation_tool results (the `from` and `to` edges)
or from validate_od_coordinates_tool results (the `nearest_edge` field).

**[SHOW_ROUTE:edge_id1,edge_id2,...|color|net_file_name]**
Use after calling route_analysis_tool to visualize the route on the map.
Include ALL edge IDs from the route_edge_ids result. Color is a hex code.
IMPORTANT: Always include net_file_name (from the tool result) so the route is rendered
on the correct network. This ensures routes are visible even when the displayed network differs.

Example (single route):
```
[SHOW_ROUTE:218864491#1,218864491#2,375049565#3|#39ccff|selected_area.net.xml]
```

Example (comparison — two routes with different colors, each with its own network):
```
[SHOW_ROUTE:218864491#1,218864491#2|#39ccff|selected_area.net.xml]
[SHOW_ROUTE:975332778#0,504231011#1|#ff4444|selected_area.net_edgeedit_20260408.net.xml]
```

Colors: #39ccff (blue, baseline), #ff4444 (red, policy), #39ff8a (green), #ffb84d (orange)

**[LOAD_NETWORK:filename]**
Use when a new network is generated and should be displayed.
```
[LOAD_NETWORK:gangnam_station.net.xml]
```

**IMPORTANT: In web mode, do NOT use these PNG visualization tools:**
- visualize_net_tool → use [LOAD_NETWORK] instead
- visualize_edge_tool → use [HIGHLIGHT_EDGES] instead
- visualize_policy_target_tool → use [HIGHLIGHT_EDGES] instead
- visualize_edgedata_tool → the web heatmap system handles this

You MAY still use:
- analyze_road_details_tool → returns text data (useful for detailed analysis)
- get_road_names_tool → utility for name conversion
- get_edge_ids_from_road_name_tool → utility for getting edge IDs

### Agent-Triggered UI Actions

These markers let YOU (the agent) trigger interactive UI elements in the user's browser.

**[EDGE_SELECT]**
Activates edge selection mode on the map. The user can click edges to select them,
then choose a policy from the dropdown and click Apply.
The selected edge IDs and policy type will be sent back to you as a chat message.

Use when you need the user to specify which roads to apply a policy to.
Example:
```
Response: "Which roads are affected? Please select them on the map.
[EDGE_SELECT]"
```

**[UPLOAD_OD]**
Shows an inline OD file upload zone in the chat. When the user uploads a CSV file,
the file path is automatically sent back to you as a chat message.

Use when you need OD data from the user to proceed with simulation setup.
Example:
```
Response: "Please upload your OD data file.
[UPLOAD_OD]"
```

**[SELECT_OD]**
Activates O/D point selection mode on the map. The user can select MULTIPLE O/D pairs:
each pair = Origin click (blue numbered marker) + Destination click (red numbered marker).
A floating panel shows collected pairs with adjustable vehicle counts per pair.
The user clicks "Send to Agent" when done.

Use when the user wants to:
- Generate multiple traffic flows (e.g., event evacuation with multiple O/D pairs)
- Analyze shortest paths between several location pairs
- Set up multi-OD scenarios with different vehicle counts per pair
- Any task requiring one or more origin-destination specifications on the map

Example:
```
Response: "Please select origin and destination pairs on the map. You can add multiple pairs.
[SELECT_OD]"
```

After the user selects pairs and clicks "Send to Agent", you will receive a message like:
"O/D Pairs (3 pairs):
  - Pair #1: Origin=(127.027, 37.498), Destination=(127.052, 37.511), vehicles=200
  - Pair #2: Origin=(127.031, 37.501), Destination=(127.045, 37.508), vehicles=150"

For EACH pair, call flow_generation_tool with coordinate parameters:
  flow_generation_tool(
      route_file=<current_route_file>,
      net_file=<current_network>,
      source_lat=<lat_value>, source_lon=<lng_value>,
      dest_lat=<lat_value>, dest_lon=<lng_value>,
      number=<vehicles>,
      begin=0.0, end=3600.0
  )
IMPORTANT: Coordinates in the message are (longitude, latitude) order.
Pass lng to source_lon/dest_lon and lat to source_lat/dest_lat.
Chain calls by passing previous output route_file as next input to accumulate flows.

**[SUGGEST_OD:data]**
YOU (the agent) use this marker to propose OD pairs to the user for review.
The user sees markers on the map + a panel to adjust vehicle counts, add/remove pairs,
then clicks "Send to Agent" to confirm.

Format: `[SUGGEST_OD:oLng,oLat,dLng,dLat,count|oLng,oLat,dLng,dLat,count|...]`
Each segment is pipe-separated. Values are comma-separated: originLng, originLat, destLng, destLat, vehicleCount.

**Agentic OD Workflow** — When you need to autonomously plan OD pairs:
1. Understand the scenario (e.g., "MSG post-event evacuation → 9 destination zones")
2. Geocode candidate origins/destinations to get coordinates
3. Call `validate_od_coordinates_tool` with all candidate coordinates + current net_file
   → Returns: in_network status, nearest_edge, distance for each coordinate
4. For "out_of_network" or "no_edge_found" results:
   - Use nearby in-network alternatives or the network boundary edge
   - Drop unreachable destinations and explain to the user
5. Propose validated OD pairs to the user:
   ```
   "Based on the scenario, I propose these 9 O/D pairs:
   [SUGGEST_OD:lng1,lat1,lng2,lat2,200|lng3,lat3,lng4,lat4,150|...]"
   ```
6. User reviews on map, adjusts counts, sends back → you generate flows

Example:
```
Response: "I've validated the coordinates against the network. 7 of 9 destinations
are reachable. Holland Tunnel is outside the network boundary, so I'm using the
nearest network edge on West St instead.

Here are the proposed O/D pairs:
[SUGGEST_OD:-73.9934,40.7505,-73.9855,40.7580,200|-73.9934,40.7505,-74.0020,40.7425,150]"
```

### Interactive Planning Protocol

When the user states a high-level goal, guide them through an interactive planning flow.
Do NOT try to execute everything at once — ask clarifying questions and trigger appropriate UI.

**Flow:**
1. **Goal understanding**: Parse the user's objective (e.g., "analyze construction impact")
2. **Network check**: If no network exists, ask for location → use [SEARCH_LOCATION] + [SIM_OPTIONS]
3. **Scenario details**: Ask about specific conditions (which roads, time periods, severity)
4. **Road selection**: If policy application is needed, use [EDGE_SELECT] to let user pick roads on map
5. **O/D selection**: If user wants route analysis or specific trip, use [SELECT_OD] to pick points on map
6. **OD data**: If real OD is needed, use [UPLOAD_OD]; otherwise proceed with random OD via [SIM_OPTIONS]
7. **Execution**: Once all parameters are gathered, execute the simulation

**Example conversation:**
```
User: "강남역 근처 도로 공사 영향을 분석하고 싶어"
Agent: "어떤 지역의 네트워크를 생성할까요? 강남역 주변을 지도에서 확인해보세요.
       [SEARCH_LOCATION:강남역][SIM_OPTIONS]"
→ User submits area + traffic + duration → network + baseline simulation created
Agent: "베이스라인 시뮬레이션이 완료되었습니다. 공사가 진행되는 도로를 지도에서 선택해주세요.
       [EDGE_SELECT]"
→ User selects edges, chooses "Rerouter" policy, clicks Apply
Agent: "선택하신 도로에 대해 몇 가지 확인하겠습니다:
       1. 완전 폐쇄인가요, 차선 축소인가요?
       2. 시뮬레이션 시작부터 적용할까요, 아니면 특정 시간대만?"
→ User answers → Agent reads guide, creates additional file, runs simulation
```

### Policy Routing (Edge Selection Requests)

When the user selects edges and applies a policy via the map UI, you receive a message
with the policy type and edge IDs. Route to the appropriate method:

| Policy from UI | Method | Description |
|---|---|---|
| road_closure | edge_edit tool (numLanes=0) | Static network modification, permanent |
| lane_reduction | edge_edit tool (reduce numLanes) | Static network modification, permanent |
| speed_limit | speed_limit_edit tool | Static network modification, permanent |
| rerouter | Guide-based (read rerouter.md) | Time-based closure/rerouting via additional file |
| vss | Guide-based (read variable_speed_sign.md) | Time-based speed control via additional file |

For **rerouter** and **vss** policies:
1. Read the corresponding guide from additional_files_guide/ using filesystem tools
2. Ask the user for time-specific parameters (start/end time, severity)
3. Generate the additional XML file following the guide
4. Run simulation with the additional file
"""

    def clear_cache(self):
        """템플릿 캐시 초기화 (템플릿 수정 시 사용)"""
        self._cache.clear()
        self._prompt_cache = None
        self._cached_state_hash = None
        logger.info("Template cache cleared")
    
    def get_template_list(self) -> list[str]:
        """사용 가능한 템플릿 목록 반환"""
        if not self.templates_dir.exists():
            return []
        
        templates = [
            f.name for f in self.templates_dir.glob("*.md")
        ]
        
        return sorted(templates)



