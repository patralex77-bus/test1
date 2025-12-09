from flask import Blueprint

bp = Blueprint("buses", __name__, template_folder="templates", static_folder="../../static")

from . import routes  # noqa

# Експортираме функцията, за да може други модули (напр. /stats/) да я импортнат
fetch_buses_list = routes.fetch_buses_list