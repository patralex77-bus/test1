# -*- coding: utf-8 -*-
"""
app.blueprints.orders пакет

Този __init__.py прави blueprint-а bp достъпен като:
    from app.blueprints.orders import bp
или
    from .blueprints.orders import bp
"""

# ВАЖНО: импортът е от routes, където е единствената дефиниция на bp.
from .routes import bp

__all__ = ["bp"]
