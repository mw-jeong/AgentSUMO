"""
AgentSUMO - AI-Powered SUMO Traffic Simulation Platform

Conversational traffic simulation automation platform built on Claude and MCP.
"""

__version__ = "0.1.0"
__author__ = "AgentSUMO Team"

# Export key classes at the top level
from .agent import AgentSUMO
from .client import SUMOMCPClient
from .core import AgentSUMOConfig

__all__ = [
    "AgentSUMO",
    "SUMOMCPClient",
    "AgentSUMOConfig",
]

