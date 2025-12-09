# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Пакет за шофьорския кабинет (driver_portal).

Тук само изнасяме bp от routes.py, за да може:
    from app.blueprints.driver_portal import bp as driver_portal_bp
да работи коректно.
"""

from .routes import bp  # noqa: F401
