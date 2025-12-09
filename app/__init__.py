# app/__init__.py
from flask import Flask, redirect, url_for

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "change-me"
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # dev: disable static file caching

    # ---- Blueprints (по веднъж всеки) ----
    from .blueprints.calendar import bp as calendar_bp
    from .blueprints.buses import bp as buses_bp
    from .blueprints.drivers import bp as drivers_bp
    from .blueprints.stats import bp as stats_bp
    from .blueprints.orders import bp as orders_bp
    from app.blueprints.driver_portal import bp as driver_portal_bp

    # Един общ blueprint за /settings (вътре: /settings/payroll, /settings/countries, ...).
    # ВНИМАНИЕ: routes.py САМ си задава url_prefix="/settings".
    from .blueprints.settings.routes import bp as settings_bp

    # ---- Регистрация (не слагаме url_prefix втори път) ----
    app.register_blueprint(calendar_bp, url_prefix="/calendar")
    app.register_blueprint(buses_bp, url_prefix="/buses")
    app.register_blueprint(drivers_bp, url_prefix="/drivers")
    app.register_blueprint(stats_bp, url_prefix="/stats")
    app.register_blueprint(orders_bp, url_prefix="/orders")
    app.register_blueprint(settings_bp)  # /settings идва от самия blueprint
    app.register_blueprint(driver_portal_bp)

    @app.route("/")
    def root():
        return redirect(url_for("calendar.index"))

    return app
