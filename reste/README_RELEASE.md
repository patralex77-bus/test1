# BUS Panel — Calendar Release (ready)

## What's included
- `app/static/js/calendar_app_fix12c.jsx` — calendar app (build: fix12j)
- `app/templates/base.html` — full-width calendar layout for page="calendar"

## How to apply
1. Replace the two files in your project with the ones from this ZIP.
2. Restart the server.
3. Hard reload `/calendar` (Ctrl+F5 / Cmd+Shift+R). You should see in the console:
   `calendar_app_fix12c.jsx loaded (fix12j)`

## Notes
- Index template **not** included; your existing `calendar/index.html` should already reference
  `static/js/calendar_app_fix12c.jsx`. If needed, add `?v=fix12j` to bust cache.
- If `/buses/api/list` is unavailable, lanes fallback to ["Неразпределени", W3200MW..W3204MW].
- The "Orders" panel below calendar remains intact.

## Next candidates (optional)
- Persist layout mode in localStorage.
- Real lanes in Week/Day from `/buses/api/list`.
- Resize in Day/Week for duration editing.
- Orders page integration and budgeting (planned vs actual).