"""
MCP Client for AgentSUMO
"""

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio
import logging
from datetime import datetime


# 로거 설정
logger = logging.getLogger("agentsumo.mcp_client")


class MCPClientError(Exception):
    """MCP Client 관련 에러"""
    pass


class MCPConnectionError(MCPClientError):
    """MCP 연결 에러"""
    pass


class MCPToolCallError(MCPClientError):
    """MCP Tool 호출 에러"""
    pass


class SUMOMCPClient:
    """
    SUMO MCP Server와 통신하는 클라이언트
    
    Features:
    - Timeout 설정
    - 자동 재연결
    - 상세한 에러 처리
    - 로깅
    - Health check
    
    사용법:
        async with SUMOMCPClient(
            connection_timeout=10.0,
            tool_timeout=300.0,
            max_retries=3
        ) as client:
            tools = await client.list_tools()
            result = await client.call_tool("net_generate", {...})
    """
    
    def __init__(
        self,
        python_path: str = "python",
        connection_timeout: float = 10.0,
        tool_timeout: float = 300.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        enable_logging: bool = True
    ):
        """
        Args:
            python_path: Python 실행 파일 경로
            connection_timeout: 연결 타임아웃 (초)
            tool_timeout: Tool 실행 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            enable_logging: 로깅 활성화 여부
        """
        self.python_path = python_path
        self.connection_timeout = connection_timeout
        self.tool_timeout = tool_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 로깅 설정
        if enable_logging:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        # 상태 관리
        self.session: Optional[ClientSession] = None
        self._stdio_context_manager = None
        self._session_context_manager = None
        self._connected = False
        self._connection_attempts = 0
        self._last_error = None
        
        # Server 파일 경로
        project_root = Path(__file__).parent.parent
        
        # agentsumo.server.main 모듈 사용
        self.server_module = "agentsumo.server.main"
        self.server_file = project_root / "server" / "main.py"
        
        if not self.server_file.exists():
            raise FileNotFoundError(
                f"MCP Server 파일을 찾을 수 없습니다: {self.server_file}"
            )
        
        logger.info(f"SUMOMCPClient 초기화 완료 (Server: {self.server_module})")
    
    async def __aenter__(self):
        """Context manager 진입"""
        await self._connect_with_retry()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        await self._disconnect()
        
        # 예외가 발생했다면 로깅
        if exc_type is not None:
            logger.error(f"Context manager에서 예외 발생: {exc_type.__name__}: {exc_val}")
        
        return False  # 예외를 다시 raise
    
    async def _connect_with_retry(self) -> None:
        """재시도 로직을 포함한 연결"""
        for attempt in range(self.max_retries):
            try:
                self._connection_attempts = attempt + 1
                
                if attempt > 0:
                    logger.info(f"재연결 시도 {attempt + 1}/{self.max_retries}...")
                    await asyncio.sleep(self.retry_delay)
                
                await self._connect()
                logger.info(f"연결 성공 (시도 {self._connection_attempts}회)")
                return
                
            except asyncio.TimeoutError:
                self._last_error = f"연결 타임아웃 ({self.connection_timeout}초)"
                logger.warning(f"시도 {attempt + 1} 실패: {self._last_error}")
                
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"시도 {attempt + 1} 실패: {type(e).__name__}: {e}")
        
        # 모든 재시도 실패
        raise MCPConnectionError(
            f"MCP Server 연결 실패 ({self.max_retries}회 시도). "
            f"마지막 에러: {self._last_error}"
        )
    
    async def _connect(self) -> None:
        """실제 연결 로직 (단일 시도)"""
        if self._connected:
            logger.warning("이미 연결되어 있습니다.")
            return
        
        logger.info("MCP Server 연결 중...")
        
        # Server parameters (python -m 방식으로 모듈 실행)
        # 환경변수 전달 (ANTHROPIC_API_KEY 등)
        import os
        env = os.environ.copy()
        
        server_params = StdioServerParameters(
            command=self.python_path,
            args=["-m", self.server_module],
            env=env  # 환경변수 전달 ✅
        )
        
        # STDIO context manager (타임아웃 적용)
        self._stdio_context_manager = stdio_client(server_params)
        read, write = await asyncio.wait_for(
            self._stdio_context_manager.__aenter__(),
            timeout=self.connection_timeout / 2
        )
        
        # Session context manager
        self._session_context_manager = ClientSession(read, write)
        self.session = await self._session_context_manager.__aenter__()
        
        # 초기화 핸드셰이크 (타임아웃 적용)
        await asyncio.wait_for(
            self.session.initialize(),
            timeout=self.connection_timeout / 2
        )
        
        self._connected = True
        logger.info("MCP Server 연결 완료!")
    
    async def _disconnect(self) -> None:
        """연결 종료"""
        if not self._connected:
            return
        
        logger.info("MCP Server 연결 종료 중...")
        
        try:
            # Session 종료
            if self._session_context_manager:
                await self._session_context_manager.__aexit__(None, None, None)
            
            # STDIO 종료
            if self._stdio_context_manager:
                await self._stdio_context_manager.__aexit__(None, None, None)
            
            self._connected = False
            logger.info("연결 종료 완료")
            
        except Exception as e:
            logger.error(f"연결 종료 중 에러: {e}")
            self._connected = False
    
    async def list_tools(self) -> List[Any]:
        """
        사용 가능한 도구 목록 조회
        
        Returns:
            List[Tool]: 도구 목록
            
        Raises:
            MCPConnectionError: 연결되어 있지 않은 경우
            MCPClientError: 도구 목록 조회 실패
        """
        if not self._connected or not self.session:
            raise MCPConnectionError(
                "MCP Server에 연결되어 있지 않습니다. 'async with' 구문을 사용하세요."
            )
        
        try:
            logger.debug("도구 목록 조회 중...")
            result = await self.session.list_tools()
            logger.info(f"{len(result.tools)}개 도구 발견")
            return result.tools
            
        except Exception as e:
            logger.error(f"도구 목록 조회 실패: {e}")
            raise MCPClientError(f"도구 목록 조회 실패: {e}") from e
    
    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Any:
        """
        도구 실행 (타임아웃 및 에러 처리 포함)
        
        Args:
            name: 도구 이름
            arguments: 도구 인자
            timeout: 실행 타임아웃 (None이면 기본값 사용)
            
        Returns:
            도구 실행 결과
            
        Raises:
            MCPConnectionError: 연결되어 있지 않은 경우
            MCPToolCallError: 도구 실행 실패
            asyncio.TimeoutError: 타임아웃 발생
        """
        if not self._connected or not self.session:
            raise MCPConnectionError(
                "MCP Server에 연결되어 있지 않습니다. 'async with' 구문을 사용하세요."
            )
        
        timeout = timeout or self.tool_timeout
        
        try:
            logger.debug(f"도구 실행: {name}")
            logger.debug(f"  파라미터: {arguments}")
            
            # 타임아웃 적용
            result = await asyncio.wait_for(
                self.session.call_tool(name, arguments),
                timeout=timeout
            )
            
            logger.debug(f"도구 실행 완료: {name}")
            return result
            
        except asyncio.TimeoutError:
            error_msg = f"도구 실행 타임아웃: {name} ({timeout}초 초과)"
            logger.error(error_msg)
            raise asyncio.TimeoutError(error_msg)
            
        except Exception as e:
            error_msg = f"도구 실행 실패: {name} - {type(e).__name__}: {e}"
            logger.error(error_msg)
            raise MCPToolCallError(error_msg) from e
    
    async def health_check(self) -> bool:
        """
        서버 상태 확인
        
        Returns:
            bool: 서버가 정상인 경우 True
        """
        try:
            if not self._connected:
                return False
            
            # 간단한 도구 목록 조회로 health check
            tools = await asyncio.wait_for(
                self.list_tools(),
                timeout=5.0
            )
            
            logger.debug(f"Health check 성공 ({len(tools)}개 도구)")
            return True
            
        except Exception as e:
            logger.warning(f"Health check 실패: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        클라이언트 통계 정보
        
        Returns:
            Dict: 통계 정보
        """
        return {
            "connected": self._connected,
            "connection_attempts": self._connection_attempts,
            "last_error": self._last_error,
            "server_file": str(self.server_file),
            "connection_timeout": self.connection_timeout,
            "tool_timeout": self.tool_timeout,
            "max_retries": self.max_retries
        }
    
    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected


# =============== 유틸리티 함수 ===============

async def create_mcp_client(
    connection_timeout: float = 10.0,
    tool_timeout: float = 300.0,
    max_retries: int = 3
) -> SUMOMCPClient:
    """
    MCP Client를 생성하고 context manager로 반환
    
    사용법:
        async with await create_mcp_client() as client:
            ...
    
    또는 더 간단하게:
        async with SUMOMCPClient() as client:
            ...
    
    Args:
        connection_timeout: 연결 타임아웃 (초)
        tool_timeout: Tool 실행 타임아웃 (초)
        max_retries: 최대 재시도 횟수
    
    Returns:
        SUMOMCPClient: MCP Client 인스턴스
    """
    return SUMOMCPClient(
        connection_timeout=connection_timeout,
        tool_timeout=tool_timeout,
        max_retries=max_retries
    )


async def test_mcp_connection() -> bool:
    """
    MCP 연결 빠른 테스트
    
    Returns:
        bool: 연결 성공 시 True
    """
    try:
        async with SUMOMCPClient(connection_timeout=5.0) as client:
            tools = await client.list_tools()
            print(f"✅ MCP 연결 테스트 성공! ({len(tools)}개 도구)")
            return True
    except Exception as e:
        print(f"❌ MCP 연결 테스트 실패: {e}")
        return False
