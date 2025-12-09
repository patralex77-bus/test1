# app/blueprints/stats/__init__.py
from flask import Blueprint

# казваме, че темплейтите за този blueprint са в подпапка "templates" на пакета
bp = Blueprint("stats", __name__, template_folder="templates")

from . import routes  # noqa
