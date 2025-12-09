# Calendar inactive lanes — plain plates under "НЕАКТИВНИ:" (v2)

This package contains a drop-in JS with the exact logic you requested:
- Lanes are built as: ["Неразпределени", ...active, "НЕАКТИВНИ:", ...inactive]
- Inactive lanes show **only the plate** (no "НЕАКТИВНИ ·" prefix)
- Dropping onto "НЕАКТИВНИ:" (the separator) is ignored
- Saving an assignment always stores the clean plate (no prefixes)

## Install
1. Backup your original file:
   app/static/js/calendar_app_fix12c.jsx

2. Copy the provided file to:
   app/static/js/calendar_app_fix12c.jsx

3. In your calendar page code (where you initialize lanes/orders), wire the helpers:

   // when mounting:
   CalendarApp.loadBusesForLanes(setLanes);

   // when rendering each order to a lane:
   const lane = CalendarApp.orderToLane(order, lanes);

   // in your drop handler:
   const targetPlate = CalendarApp.dropToPlate(lane);
   if (targetPlate === null) return; // separator
   OS.patchOrder(String(orderId), { vehicle_plate: targetPlate });

4. Hard refresh the browser on /calendar/ (Ctrl+F5).

## Notes
- This file doesn't remove any of your logic; it just provides helpers you can call.
- If your current calendar file already defines these functions, copy just the lane assembly and mapping parts.
