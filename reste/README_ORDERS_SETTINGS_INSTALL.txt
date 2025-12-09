BUS — Orders multi-day + cost engine, and Settings > Countries
=============================================================

1) Copy files into your project preserving paths:
   - app/blueprints/settings/__init__.py
   - app/blueprints/settings/routes.py
   - app/blueprints/settings/templates/settings/countries.html
   - app/blueprints/orders/costs.py
   - app/blueprints/orders/new_order_routes.py
   - app/blueprints/orders/templates/orders/index.html   (backup your current file before replacing)

2) Register the Settings blueprint (once) in your app factory (e.g. app/__init__.py):
   from app.blueprints.settings.routes import bp as settings_bp
   app.register_blueprint(settings_bp)

3) Ensure the new Orders route is imported so its @bp.route('/new') is attached.
   In app/blueprints/orders/__init__.py (or routes.py), add:
   from .new_order_routes import *

4) Hard refresh /orders/ and /settings/countries (Ctrl+F5).

Notes:
- New Orders form posts to url_for('orders.create') => '/orders/new' in new_order_routes.py
- Costs are computed server-side using buses' fuel_consumption and tank_size
- Countries (fee/km + fuel_price) are managed in /settings/countries
- Round trip checkbox doubles both distance-based fees and fuel simulation (return route).
