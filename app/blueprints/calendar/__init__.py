from flask import Blueprint

# НЕ слагай url_prefix тук; ще го подадем при регистрацията в app/__init__.py
bp = Blueprint(
    "calendar",
    __name__,
    template_folder="templates",
    static_folder="../../static",  # ако така е структурата при теб
)

from . import routes  # noqa
