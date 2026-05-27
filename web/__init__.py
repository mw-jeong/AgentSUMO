"""
AgentSUMO Web Interface

FastAPI + Mapbox GL JS 기반 웹 인터페이스
"""

from .app import create_app

__all__ = ["create_app"]
