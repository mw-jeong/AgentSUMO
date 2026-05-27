"""
Filesystem MCP Client for AgentSUMO

Connects to the official Filesystem MCP Server for file-based operations.
Supports multiple allowed directories for guide reading and file editing.

Usage:
    # Single directory
    async with FilesystemMCPClient(allowed_directories="/path/to/dir") as client:
        tools = await client.list_tools()
        result = await client.call_tool("read_file", {"path": "/path/to/file.xml"})

    # Multiple directories
    async with FilesystemMCPClient(allowed_directories=["/path/to/guides", "/path/to/output"]) as client:
        tools = await client.list_tools()
"""

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import Any, Optional, List, Union
import asyncio
import logging

logger = logging.getLogger("agentsumo.filesystem_mcp_client")


class FilesystemMCPClient:
    """
    Filesystem MCP Server와 통신하는 클라이언트

    npx -y @modelcontextprotocol/server-filesystem <dir1> [dir2] [dir3] ...

    Tools provided:
    - read_file: Read file contents
    - write_file: Write content to a file
    - read_multiple_files: Read multiple files at once
    - list_directory: List directory contents
    - search_files: Search for files by pattern
    - get_file_info: Get file metadata
    - create_directory: Create a new directory
    """

    def __init__(
        self,
        allowed_directories: Union[str, List[str]],
        connection_timeout: float = 15.0,
        tool_timeout: float = 30.0
    ):
        """
        Initialize Filesystem MCP Client.

        Args:
            allowed_directories: Directory or list of directories to allow access to (absolute paths)
            connection_timeout: Connection timeout in seconds
            tool_timeout: Tool execution timeout in seconds
        """
        if isinstance(allowed_directories, str):
            self.allowed_directories = [allowed_directories]
        else:
            self.allowed_directories = allowed_directories
        self.connection_timeout = connection_timeout
        self.tool_timeout = tool_timeout

        self.session: Optional[ClientSession] = None
        self._stdio_context_manager = None
        self._session_context_manager = None
        self._connected = False

        logger.info(f"FilesystemMCPClient 초기화 (dirs: {self.allowed_directories})")

    async def __aenter__(self):
        """Context manager entry - Connect to server"""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - Disconnect"""
        await self._disconnect()

        if exc_type is not None:
            logger.error(f"FilesystemMCPClient context error: {exc_type.__name__}: {exc_val}")

        return False

    async def _connect(self):
        """Connect to the official Filesystem MCP Server"""
        if self._connected:
            logger.warning("Already connected to Filesystem MCP Server")
            return

        logger.info("Filesystem MCP Server 연결 중...")

        server_params = StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-filesystem",
                *self.allowed_directories
            ],
            env=None
        )

        try:
            # STDIO connection
            self._stdio_context_manager = stdio_client(server_params)
            read, write = await asyncio.wait_for(
                self._stdio_context_manager.__aenter__(),
                timeout=self.connection_timeout / 2
            )

            # Session
            self._session_context_manager = ClientSession(read, write)
            self.session = await self._session_context_manager.__aenter__()

            # Initialize handshake
            await asyncio.wait_for(
                self.session.initialize(),
                timeout=self.connection_timeout / 2
            )

            self._connected = True
            logger.info("✅ Filesystem MCP Server 연결 완료")

        except asyncio.TimeoutError:
            raise RuntimeError(f"Filesystem MCP Server 연결 타임아웃 ({self.connection_timeout}초)")
        except Exception as e:
            raise RuntimeError(f"Filesystem MCP Server 연결 실패: {e}")

    async def _disconnect(self):
        """Disconnect from server"""
        if not self._connected:
            return

        logger.info("Filesystem MCP Server 연결 종료 중...")

        try:
            if self._session_context_manager:
                await self._session_context_manager.__aexit__(None, None, None)

            if self._stdio_context_manager:
                await self._stdio_context_manager.__aexit__(None, None, None)

            self._connected = False
            logger.info("✅ Filesystem MCP 연결 종료")

        except Exception as e:
            logger.warning(f"연결 종료 중 에러 (무시): {e}")
            self._connected = False

    async def list_tools(self) -> List[Any]:
        """
        List available Filesystem tools.

        Returns:
            List of tools (read_file, list_directory, etc.)
        """
        if not self._connected or not self.session:
            raise RuntimeError("Not connected to Filesystem MCP Server")

        try:
            logger.debug("Listing Filesystem tools...")
            result = await self.session.list_tools()
            logger.info(f"✅ {len(result.tools)} Filesystem tools available")
            return result.tools

        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise RuntimeError(f"Failed to list Filesystem tools: {e}")

    async def call_tool(
        self,
        name: str,
        arguments: dict,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Execute a Filesystem tool.

        Args:
            name: Tool name (e.g., "read_file", "list_directory")
            arguments: Tool arguments (e.g., {"path": "/path/to/file"})
            timeout: Execution timeout (None = use default)

        Returns:
            Tool execution result
        """
        if not self._connected or not self.session:
            raise RuntimeError("Not connected to Filesystem MCP Server")

        timeout = timeout or self.tool_timeout

        try:
            logger.debug(f"Filesystem tool 실행: {name}")

            if "path" in arguments:
                logger.debug(f"  Path: {arguments['path']}")

            result = await asyncio.wait_for(
                self.session.call_tool(name, arguments),
                timeout=timeout
            )

            logger.debug(f"✅ Filesystem tool 완료: {name}")
            return result

        except asyncio.TimeoutError:
            error_msg = f"Filesystem tool timeout: {name} ({timeout}초 초과)"
            logger.error(error_msg)
            raise asyncio.TimeoutError(error_msg)

        except Exception as e:
            error_msg = f"Filesystem tool 실행 실패: {name} - {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    @property
    def is_connected(self) -> bool:
        """Check connection status"""
        return self._connected

    def get_stats(self) -> dict:
        """Get client statistics"""
        return {
            "connected": self._connected,
            "allowed_directories": self.allowed_directories,
            "connection_timeout": self.connection_timeout,
            "tool_timeout": self.tool_timeout
        }
