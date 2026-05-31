"""
AgentSUMO Web Interface

Web interface built on FastAPI and Mapbox GL JS.
"""

from .app import create_app

__all__ = ["create_app"]
