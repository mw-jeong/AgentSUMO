"""
AgentSUMO 설정

전역 설정 및 환경 변수 관리
"""

from pathlib import Path
import os


class AgentSUMOConfig:
    """AgentSUMO 전역 설정"""
    
    # 프로젝트 루트
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    
    # 데이터 디렉토리
    DATA_DIR = PROJECT_ROOT / "data"
    OUTPUT_DIR = PROJECT_ROOT / "output"
    CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"
    
    # Claude API 설정
    CLAUDE_API_KEY_FILE = PROJECT_ROOT / "claude_api.txt"
    
    # 모델 선택 (용도에 따라 변경)
    # - "claude-sonnet-4-5-20250929" 
    # - "claude-3-5-haiku-latest"
    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"  # 현재 설정
    
    # MCP Client 설정 (현재 미사용 - MCP Client에서 하드코딩)
    # MCP_CONNECTION_TIMEOUT = 10.0  # 초
    # MCP_TOOL_TIMEOUT = 300.0       # 초 (5분)
    # MCP_MAX_RETRIES = 3

    # AgentSUMO 설정 (현재 미사용 - agent_sumo.py에서 하드코딩)
    # AGENT_MAX_ITERATIONS = 10      # 최대 반복 횟수
    # AGENT_MAX_TOKENS = 4096        # Claude 응답 최대 토큰
    
    @classmethod
    def get_claude_api_key(cls) -> str:
        """Claude API 키 로드"""
        if not cls.CLAUDE_API_KEY_FILE.exists():
            raise FileNotFoundError(f"API key 파일을 찾을 수 없습니다: {cls.CLAUDE_API_KEY_FILE}")
        
        with open(cls.CLAUDE_API_KEY_FILE, 'r') as f:
            return f.read().strip()
    
    # Mapbox 설정
    MAPBOX_TOKEN_FILE = PROJECT_ROOT / "mapbox_token.txt"

    @classmethod
    def get_mapbox_token(cls) -> str:
        """Mapbox 토큰 로드 (파일 > 환경변수, 없으면 에러)"""
        # 1. 파일에서 로드
        if cls.MAPBOX_TOKEN_FILE.exists():
            with open(cls.MAPBOX_TOKEN_FILE, 'r') as f:
                token = f.read().strip()
                if token:
                    return token

        # 2. 환경변수에서 로드
        env_token = os.environ.get("MAPBOX_TOKEN") or os.environ.get("MAPBOX_ACCESS_TOKEN")
        if env_token:
            return env_token

        # 3. 토큰이 없으면 에러
        raise FileNotFoundError(
            "Mapbox 토큰이 필요합니다. mapbox_token.txt 파일을 생성하거나 MAPBOX_TOKEN 환경변수를 설정하세요."
        )

    @classmethod
    def ensure_directories(cls):
        """필요한 디렉토리 생성"""
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.OUTPUT_DIR.mkdir(exist_ok=True)

        # 출력 하위 디렉토리
        (cls.OUTPUT_DIR / "networks").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "trips").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "simulations").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "analysis").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "reports").mkdir(exist_ok=True)
        (cls.OUTPUT_DIR / "visualizations").mkdir(exist_ok=True)

