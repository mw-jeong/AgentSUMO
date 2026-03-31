"""
Settings for SUMO MCP Server.
"""

import os
from pathlib import Path


def _load_sumo_home() -> str:
    """Load SUMO_HOME from sumo_home.txt or environment variable."""
    # 프로젝트 루트의 sumo_home.txt 확인
    project_root = Path(__file__).parent.parent.parent.parent
    sumo_home_file = project_root / "sumo_home.txt"

    # 1. 파일에서 로드
    if sumo_home_file.exists():
        with open(sumo_home_file, 'r') as f:
            path = f.read().strip()
            if path:
                return path

    # 2. 환경 변수에서 로드
    env_path = os.environ.get("SUMO_HOME")
    if env_path:
        return env_path

    # 3. 기본값 (macOS)
    return "/Library/Frameworks/EclipseSUMO.framework/Versions/1.24.0/EclipseSUMO"


class SUMOEnvironment:
    """SUMO environment settings."""

    # SUMO 환경 설정 (sumo_home.txt > 환경변수 > 기본값)
    SUMO_HOME = _load_sumo_home()

    # 기본 경로들
    BASE_DIR = Path(__file__).parent.parent.parent
    DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
    
    # 출력 디렉토리들
    NETWORKS_DIR = DEFAULT_OUTPUT_DIR / "networks"
    TRIPS_DIR = DEFAULT_OUTPUT_DIR / "trips"
    SIMULATIONS_DIR = DEFAULT_OUTPUT_DIR / "simulations"
    ANALYSIS_DIR = DEFAULT_OUTPUT_DIR / "analysis"
    REPORTS_DIR = DEFAULT_OUTPUT_DIR / "reports"
    VISUALIZATIONS_DIR = DEFAULT_OUTPUT_DIR / "visualizations"
    
    # 데이터 파일 경로
    OSM_PBF_PATH = BASE_DIR / "data" / "new-york-latest.osm.pbf"
    
    # SUMO 도구 경로들
    @classmethod
    def get_tool_path(cls, tool_name: str) -> str:
        """Get path to SUMO tool."""
        return os.path.join(cls.SUMO_HOME, "share", "sumo", "tools", tool_name)
    
    @classmethod
    def get_binary_path(cls, binary_name: str) -> str:
        """Get path to SUMO binary."""
        return os.path.join(cls.SUMO_HOME, "bin", binary_name)


class SimulationSettings:
    """Simulation settings."""
    
    # 시뮬레이션 기본값들
    DEFAULT_DURATION = 3600  # 1시간
    DEFAULT_SEED = 42
    
    # 교통 조건별 비율
    TRAFFIC_RATIOS = {
        "light": 0.2,
        "medium": 0.8, 
        "heavy": 1.5
    }
    
    # 차량 타입별 비율
    DEFAULT_ELECTRIC_RATIO = 0.2
    
    # 시뮬레이션 시간 범위
    DEFAULT_BEGIN_TIME = 0
    DEFAULT_END_TIME = 3600
    # DEFAULT_END_TIME = 2700  # 트립 출발은 45분까지, 시뮬레이션은 3600초까지


class NetworkSettings:
    """Network settings."""
    
    # 네트워크 생성 기본값들
    DEFAULT_GRID_SIZE = 500  # meters
    DEFAULT_BUFFER = 0.003  # degrees
    
    # 도로 타입 매핑
    TYPE_FILES = "osmNetconvert.typ.xml"
    
    # 네트워크 변환 옵션들
    NETCONVERT_OPTIONS = [
        "--proj.utm",
        "--keep-edges.by-vclass", "passenger",
        "--output.street-names",
        "--remove-edges.by-type", "highway.motorway,highway.motorway_link"
    ]


class VisualizationSettings:
    """Visualization settings."""
    
    # 시각화 기본 설정
    DEFAULT_DPI = 300
    DEFAULT_EDGE_WIDTH = 0.5
    DEFAULT_EDGE_COLOR = "#606060"
    DEFAULT_SELECTED_WIDTH = 1.0
    DEFAULT_SELECTED_COLOR = "#800000"
    
    # 컬러맵 설정
    DEFAULT_COLORMAP = "#0:#606060,0.25:#00c000,0.5:#ffff00,0.75:#c00000,1:#600000"
    # DEFAULT_COLORMAP = "#0:#808080,0.00000001:#00ff00,0.3:#ffff00,0.5:#ff8000,0.7:#ff0000,1:#800000"
    # DEFAULT_COLORMAP = "#0:#606060,0.0000000001:#00c000,0.4:#ff8000,0.6:#c00000,1:#600000"
    
    # 축 레이블
    XLABEL = "[m]"
    YLABEL = "[m]"


class AnalysisSettings:
    """Analysis settings."""
    
    # 분석 기본 설정
    DEFAULT_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
    
    # 통계 계산 옵션들
    STATS_PATTERNS = {
        'count': r'count (\d+)',
        'min': r'min ([\d.]+)',
        'max': r'max ([\d.]+)',
        'mean': r'mean ([\d.]+)',
        'Q1': r'Q1 ([\d.]+)',
        'median': r'median ([\d.]+)',
        'Q3': r'Q3 ([\d.]+)',
        'stdDev': r'stdDev ([\d.]+)'
    }
    
    # 단위 변환 설정
    SPEED_CONVERSION = 3.6  # m/s to km/h
    DISTANCE_CONVERSION = 1000  # m to km
    EMISSION_CONVERSION = 1000000  # mg to g


# 전역 설정 인스턴스
sumo_environment = SUMOEnvironment()
simulation_settings = SimulationSettings()
network_settings = NetworkSettings()
visualization_settings = VisualizationSettings()
analysis_settings = AnalysisSettings()
