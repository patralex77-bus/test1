What changed
------------
- Settings > Countries now supports:
  - Цена/км
  - Цена/ден
  - Цена гориво/л
  - ДДС %
  - Отделен бутон „Добави държава“ (показва/скрива формата)
- Cost engine:
  - Взима предвид Цена/ден (пропорционално на дела км за страната и дни; умножава при двупосочно).
  - Изчислява ДДС по държави върху (такси/км + гориво) и дава общо с/без ДДС.
  - Връща разбивки per-country.

Wire-up
-------
1) Copy files preserving paths.
2) Register the blueprint once in app/__init__.py:
   from app.blueprints.settings.routes import bp as settings_countries_bp
   app.register_blueprint(settings_countries_bp)
   (The blueprint name is 'settings_countries' to avoid conflicts.)

3) Your Orders creation already calls compute_costs(order, bus, settings).
   This updated version is drop-in compatible.

Online fuel price sources (optional)
------------------------------------
- EU Weekly Oil Bulletin (free, weekly, EU): official consumer prices by country. Manual parsing or community collations exist. 
- GlobalPetrolPrices API (paid): 135+ countries, simple feed.
- HERE Fuel Prices API (paid): station-level, by location.
- TradingEconomics: aggregates per-country prices.

You can start with manual entries in Settings and later add a background sync job to prefill fuel prices from an API you choose.
