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
            sections.append(self._load_template("unified_system.md"))

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
## Web Interface: Interactive Options UI (CRITICAL)

**When running via web interface, use `[SIM_OPTIONS]` marker to trigger interactive UI!**

### When to Use [SIM_OPTIONS]

When user requests a simulation and you need to ask for parameters (area, traffic, duration),
include `[SIM_OPTIONS]` at the END of your response. This triggers an interactive options panel
in the web interface where users can:
- Select area on map (instead of typing coordinates)
- Click buttons for traffic level (한산/보통/혼잡)
- Click buttons for duration (30분/1시간/2시간)

### Example Usage

**User**: "강남역을 시뮬레이션 하고싶어"

**Your Response**:
```
강남역 시뮬레이션을 준비하겠습니다.

아래에서 옵션을 선택해주세요:
- 영역: 지도에서 직접 선택
- 교통량: 한산/보통/혼잡
- 시간: 30분/1시간/2시간

[SIM_OPTIONS]
```

### Important Rules

1. **Only use for NEW simulation requests** - not for analysis, comparison planning, or other tasks
2. **Place marker at the very END** of your message
3. **Keep the text brief** - the UI will provide the options
4. **After user submits options**, you'll receive a message with all parameters → then execute simulation

### When NOT to Use [SIM_OPTIONS]

- User already provided all parameters (area, traffic, duration)
- User selected area on map (bbox already in message)
- Task is analysis, comparison, or non-simulation work
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



