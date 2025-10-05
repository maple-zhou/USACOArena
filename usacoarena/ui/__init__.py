"""Web UI integration for USACOArena.

This package exposes helpers to register the management dashboard blueprint
with Flask applications and provides a standalone UI app factory.
"""

from .blueprint import register_ui_blueprint
from .app import create_app

__all__ = ["register_ui_blueprint", "create_app"]
