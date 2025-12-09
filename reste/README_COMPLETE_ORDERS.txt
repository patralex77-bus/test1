Complete Orders module (timestamp 1758525251)
======================================

Files included (drop-in):
- app/blueprints/orders/__init__.py
- app/blueprints/orders/ensure_inject.py
- app/blueprints/orders/context_inject.py
- app/blueprints/orders/costs.py
- app/blueprints/orders/routes.py            (GET /orders/, GET /orders/api/list)
- app/blueprints/orders/new_order_routes.py  (POST /orders/new)
- app/blueprints/orders/templates/orders/index.html  (New Order form + Orders list + calendar sync)

How to enable
-------------
1) Copy files preserving paths.
2) In your app factory (create_app), ensure you have:
   from app.blueprints.orders import bp as orders_bp
   app.register_blueprint(orders_bp, url_prefix="/orders")

3) Make sure you have some buses with 'reg_no' in /buses and countries in /settings/countries.

Notes
-----
- This is additive and self-contained. It doesn't remove any of your other code.
- Calendar visualization reads localStorage (busops:orders_v1); visiting /orders/ will sync the latest orders to it.
