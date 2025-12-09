// build: fix12k
console.log('calendar_app_fix12c.jsx loaded (fix12k)');

const { useState, useEffect, useMemo, useRef } = React;

// --- Safe OS wrapper (гарантиране на масив от listOrders) ---
(function ensureOrdersSharedSafe(){
  const raw = (window && window.ordersSharedOverride) ? window.ordersSharedOverride
             : ((window && window.OrdersShared) ? window.OrdersShared : null);
  if (!window) return;
  const OS = window.OrdersShared = (raw || {});
  if (typeof OS.listOrders !== 'function') {
    OS.listOrders = () => {
      try {
        const a = JSON.parse(localStorage.getItem('busops:orders_v1') || '[]');
        return Array.isArray(a) ? a : [];
      } catch { return []; }
    };
  } else {
    const orig = OS.listOrders.bind(OS);
    OS.listOrders = () => {
      try {
        const r = orig();
        return Array.isArray(r) ? r : [];
      } catch { return []; }
    };
  }
  if (typeof OS.ingest !== 'function') {
    OS.ingest = (arr) => {
      try {
        const a = Array.isArray(arr) ? arr : [];
        localStorage.setItem('busops:orders_v1', JSON.stringify(a));
        localStorage.setItem('orders_fallback_store_v1', JSON.stringify(a));
        window.dispatchEvent(new CustomEvent('orders:changed'));
      } catch {}
    };
  }
  if (typeof OS.subscribe !== 'function') {
    OS.subscribe = () => () => {};
  }
})();

const OS = (window && window.OrdersShared) ? window.OrdersShared : null;

// ---- utils ----
function hh(n){ return String(n).padStart(2,'0'); }
function isoDate(d){ return d.toISOString().slice(0,10); }
function startOfDay(d){ return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0,0,0,0); }
function daysInMonth(anchor){ return new Date(anchor.getFullYear(), anchor.getMonth()+1, 0).getDate(); }
function startOfWeekMonday(d){ const nd=new Date(d); const day=(nd.getDay()+6)%7; nd.setDate(nd.getDate()-day); nd.setHours(0,0,0,0); return nd; }

// ---- data binding ----
function useOrdersAssignments(){
  if(!OS){
    return { orders: [], ordersById: new Map(), assignments: [], refresh: ()=>{} };
  }
  const [orders, setOrders] = useState(OS.listOrders() || []);

  // Auto-fetch from server flat API once at mount (defensive)
  useEffect(()=>{
    (async function(){
      try{
        const r = await fetch('/orders/api/calendar_flat');
        if(!r.ok) return;
        const j = await r.json();
        const flat = Array.isArray(j.orders) ? j.orders : [];
        if (flat.length > 0) {
          OS.ingest(flat);
        }
      }catch{}
    })();
  }, []);

  useEffect(()=>{
    const h = ()=> setOrders(OS.listOrders() || []);
    window.addEventListener("orders:changed", h);
    return ()=> window.removeEventListener("orders:changed", h);
  }, []);

  const assignments = useMemo(()=>{
    return (orders || []).map(o=>{
      const [sh,sm] = (o.startTime||"08:00").split(":").map(n=>parseInt(n||0,10));
      const [eh,em] = (o.endTime||"10:00").split(":").map(n=>parseInt(n||0,10));
      const from = new Date(o.date ? o.date+"T"+hh(sh)+":"+hh(sm)+":00" : new Date());
      const to   = new Date(o.date ? o.date+"T"+hh(eh)+":"+hh(em)+":00" : new Date());
      return {
        id: String(o.id),
        title: (o.title || (o.origin ? (o.origin + " → " + (o.destination||"")) : "Поръчка #"+o.id)),
        from, to
      };
    });
  }, [orders]);

  const ordersById = useMemo(()=>{
    const m=new Map();
    (orders || []).forEach(o=>m.set(String(o.id), o));
    return m;
  }, [orders]);

  return { orders: (orders||[]), ordersById, assignments, refresh: ()=> setOrders(OS.listOrders() || []) };
}

// ---- DnD helpers ----
function useDragAndDrop(){
  const allowDrop = (e)=> e.preventDefault();
  const onDragStart = (e, id)=>{ e.dataTransfer.setData("text/plain", String(id)); };
  const onDragEnd = ()=>{};
  return { allowDrop, onDragStart, onDragEnd };
}

// ---- Toolbar ----
function Toolbar({view, setView, anchor, setAnchor, onExport, onImport, busFilter, setBusFilter, lanes, layoutMode, setLayoutMode}){
  function go(deltaDays){
    const d = new Date(anchor);
    d.setDate(d.getDate()+deltaDays);
    setAnchor(d);
  }
  return (
    <div className="flex flex-wrap items-center justify-between bg-white border rounded-xl px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>go(-30)}>«</button>
        <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG', {month:'long', year:'numeric'})}</div>
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>go(30)}>»</button>
        <div className="ml-2">
          <button className={"px-2 py-1 text-xs rounded "+(view==='day'?'bg-slate-900 text-white':'border')} onClick={()=>setView('day')}>Ден</button>
          <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='week'?'bg-slate-900 text-white':'border')} onClick={()=>setView('week')}>Седмица</button>
          <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='month'?'bg-slate-900 text-white':'border')} onClick={()=>setView('month')}>Месец</button>
        </div>
        <a href="/orders#new" className="ml-2 px-3 py-1.5 text-sm rounded-xl border">+ Нова поръчка</a>
        <select className="ml-2 px-3 py-1.5 text-sm border rounded-xl" value={busFilter} onChange={(e)=>setBusFilter(e.target.value)}>
          <option>Всички</option>
          {lanes.map(l=> <option key={l}>{l}</option>)}
        </select>
        <div className="ml-2 text-xs text-slate-500">Режим:</div>
        <select className="ml-1 px-3 py-1.5 text-sm border rounded-xl" value={layoutMode} onChange={(e)=>setLayoutMode(e.target.value)}>
          <option value="equal">Равномерни</option>
          <option value="fixed">Фиксирани (скрол)</option>
        </select>
      </div>
      <div className="flex items-center gap-2">
        <button className="px-3 py-1.5 rounded-xl border" onClick={onExport}>Експорт</button>
        <label className="px-3 py-1.5 rounded-xl border cursor-pointer">Импорт
          <input type="file" accept="application/json" className="hidden" onChange={onImport}/>
        </label>
      </div>
    </div>
  );
}

// ---- MonthView ----
function MonthView({anchor, assignments, dnd, ordersById, lanes=[], busFilter='Всички', mode='equal', onSelect, selectedId}){
  const total = daysInMonth(anchor);
  const days = Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1));
  const lanesToShow = (busFilter==='Всички') ? lanes : lanes.filter(l=>l===busFilter);

  const scrollRef = useRef(null);
  useEffect(()=>{
    try{
      const today = new Date();
      if(today.getMonth()!==anchor.getMonth() || today.getFullYear()!==anchor.getFullYear()) return;
      const idx = today.getDate()-1;
      if(mode==='fixed'){ const el = scrollRef.current; if(el){ el.scrollLeft = Math.max(0, idx*48 - 120); } }
    }catch{}
  }, [anchor, mode]);

  const byDayLane = useMemo(()=>{
    const map = new Map();
    days.forEach(d=>{
      const k = isoDate(d);
      const laneMap = new Map();
      lanes.forEach(l=>laneMap.set(l, []));
      map.set(k, laneMap);
    });
    (assignments||[]).forEach(a=>{
      const k = isoDate(startOfDay(a.from));
      const o = ordersById.get(String(a.id));
      let plate = (o && o.vehicle_plate) ? o.vehicle_plate : 'Неразпределени';
      if(!lanes.includes(plate)) plate = 'Неразпределени';
      if(map.has(k)){ map.get(k).get(plate).push(a); }
    });
    return map;
  }, [assignments, anchor, ordersById, lanes]);

  function dropOnCell(date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      const asn = (assignments||[]).find(x=> String(x.id)===String(id));
      const from = new Date(date.getFullYear(), date.getMonth(), date.getDate(), asn?asn.from.getHours():8, asn?asn.from.getMinutes():0);
      const to   = new Date(from.getTime() + (asn ? (asn.to - asn.from) : 2*60*60*1000));
      if(OS && OS.updateOrderTime){
        OS.updateOrderTime(String(id), isoDate(from), hh(from.getHours())+":"+hh(from.getMinutes()), hh(to.getHours())+":"+hh(to.getMinutes()));
      }
      if(OS && OS.patchOrder){
        OS.patchOrder(String(id), { vehicle_plate: (lane==='Неразпределени'?'':lane) });
        if(lane && lane!=='Неразпределени' && lane!=='НЕАКТИВНИ'){
          try{ fetch('/buses/api/mark_used', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({plate: lane})}); }catch(e){}
        }
      }
      window.dispatchEvent(new CustomEvent("orders:changed"));
      if(typeof onSelect==='function') onSelect(id);
    };
  }

  const cellBase = "border-r border-b p-1.5 min-h-[64px]";
  const gridCols = `auto repeat(${days.length}, ${mode==='equal' ? 'minmax(0, 1fr)' : '48px'})`;
  const gridClass = (mode==='equal') ? 'grid w-full' : 'inline-grid';

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">{mode==='equal' ? 'Колони равномерно по ширина' : 'Фиксирани клетки (скрол)'} · Автобуси по Y</div>
      </div>

      <div className="overflow-x-auto" ref={scrollRef}>
        <div className={gridClass} style={{gridTemplateColumns: gridCols}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(
            <div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.getDate()}</div>
          ))}
          {lanesToShow.map((lane,ri) => (
            <React.Fragment key={lane}>
              <div className={"h-16 border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              {days.map((d,i)=>{
                const list = (byDayLane.get(isoDate(d))?.get(lane)) || [];
                const zebra = ri%2 ? "bg-slate-50/50" : "";
                return (
                  <div key={i} className={cellBase + " " + zebra} onDragOver={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop} onDrop={dropOnCell(d, lane)}>
                    <div className="space-y-1">
                      {list.map(a=>(
                        <div key={a.id}
                             draggable
                             onDragStart={(e)=>dnd.onDragStart(e, a.id)}
                             onDragEnd={dnd.onDragEnd}
                             onClick={()=>onSelect && onSelect(a.id)}
                             className={"text-[10px] px-1.5 py-0.5 rounded bg-white/80 border cursor-move truncate " + (selectedId===a.id?"outline outline-2 outline-amber-400":"")}
                             title={a.title}>
                          {a.title}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- WeekView ----
function WeekView({anchor, assignments, dnd, ordersById, lanes=[], mode='equal', onSelect, selectedId}){
  const start = startOfWeekMonday(anchor);
  const days = Array.from({length: 7}).map((_,i)=> new Date(start.getFullYear(), start.getMonth(), start.getDate()+i));

  const byDayLane = useMemo(()=>{
    const map = new Map();
    const dateKeys = days.map(d=> isoDate(d));
    dateKeys.forEach(k=>{
      const laneMap = new Map();
      lanes.forEach(l=>laneMap.set(l, []));
      map.set(k, laneMap);
    });
    (assignments||[]).forEach(a=>{
      const k = isoDate(startOfDay(a.from));
      const o = ordersById.get(String(a.id));
      let plate = (o && o.vehicle_plate) ? o.vehicle_plate : 'Неразпределени';
      if(!lanes.includes(plate)) plate = 'Неразпределени';
      if(map.has(k)) map.get(k).get(plate).push(a);
    });
    return map;
  }, [assignments, lanes, anchor]);

  function dropOnCell(date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      const asn = (assignments||[]).find(x=> String(x.id)===String(id));
      const from = new Date(date.getFullYear(), date.getMonth(), date.getDate(), asn?asn.from.getHours():8, asn?asn.from.getMinutes():0);
      const to   = new Date(from.getTime() + (asn ? (asn.to - asn.from) : 2*60*60*1000));
      if(OS && OS.updateOrderTime){
        OS.updateOrderTime(String(id), isoDate(from), hh(from.getHours())+":"+hh(from.getMinutes()), hh(to.getHours())+":"+hh(to.getMinutes()));
      }
      if(OS && OS.patchOrder){
        OS.patchOrder(String(id), { vehicle_plate: (lane==='Неразпределени'?'':lane) });
        if(lane && lane!=='Неразпределени' && lane!=='НЕАКТИВНИ'){
          try{ fetch('/buses/api/mark_used', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({plate: lane})}); }catch(e){}
        }
      }
      window.dispatchEvent(new CustomEvent("orders:changed"));
      if(typeof onSelect==='function') onSelect(id);
    };
  }

  const gridCols = `auto repeat(${days.length}, ${mode==='equal' ? 'minmax(0, 1fr)' : '72px'})`;
  const gridClass = (mode==='equal') ? 'grid w-full' : 'inline-grid';

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Седмица</div>
      <div className="overflow-x-auto">
        <div className={gridClass} style={{gridTemplateColumns: gridCols}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(<div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.toLocaleDateString('bg-BG',{weekday:'short', day:'2-digit'})}</div>))}
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className={"h-16 border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              {days.map((d,i)=>{
                const list = (byDayLane.get(isoDate(d))?.get(lane)) || [];
                const zebra = ri%2 ? "bg-slate-50/50" : "";
                return (
                  <div key={i} className={"border-r border-b p-1.5 min-h-[64px] "+zebra} onDragOver={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop} onDrop={dropOnCell(d, lane)}>
                    <div className="space-y-1">
                      {list.map(a=>(
                        <div key={a.id} draggable onDragStart={(e)=>dnd.onDragStart(e, a.id)} onDragEnd={dnd.onDragEnd}
                             onClick={()=>onSelect && onSelect(a.id)}
                             className={"text-[10px] px-1.5 py-0.5 rounded bg-white/80 border cursor-move truncate " + (selectedId===a.id?"outline outline-2 outline-amber-400":"")}
                             title={a.title}>{a.title}</div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- DayView ----
function DayView({anchor, assignments, dnd, ordersById, lanes=[], mode='equal', onSelect, selectedId}){
  const day = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
  const hours = Array.from({length:24}).map((_,h)=> h);

  const byHourLane = useMemo(()=>{
    const map = new Map();
    hours.forEach(h=>{
      const laneMap = new Map();
      lanes.forEach(l=>laneMap.set(l, []));
      map.set(h, laneMap);
    });
    (assignments||[]).forEach(a=>{
      const d = new Date(a.from);
      if(d.toDateString() !== day.toDateString()) return;
      const hour = d.getHours();
      const o = ordersById.get(String(a.id));
      let plate = (o && o.vehicle_plate) ? o.vehicle_plate : 'Неразпределени';
      if(!lanes.includes(plate)) plate = 'Неразпределени';
      map.get(hour)?.get(plate)?.push(a);
    });
    return map;
  }, [assignments, lanes, anchor]);

  function dropOnCell(hour, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      const from = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0, 0);
      const to   = new Date(from.getTime() + 2*60*60*1000);
      if(OS && OS.updateOrderTime){
        OS.updateOrderTime(String(id), isoDate(from), hh(from.getHours())+":"+hh(from.getMinutes()), hh(to.getHours())+":"+hh(to.getMinutes()));
      }
      if(OS && OS.patchOrder){
        OS.patchOrder(String(id), { vehicle_plate: (lane==='Неразпределени'?'':lane) });
        if(lane && lane!=='Неразпределени' && lane!=='НЕАКТИВНИ'){
          try{ fetch('/buses/api/mark_used', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({plate: lane})}); }catch(e){}
        }
      }
      window.dispatchEvent(new CustomEvent("orders:changed"));
      if(typeof onSelect==='function') onSelect(id);
    };
  }

  const gridCols = `auto repeat(${hours.length}, ${mode==='equal' ? 'minmax(0, 1fr)' : '56px'})`;
  const gridClass = (mode==='equal') ? 'grid w-full' : 'inline-grid';

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Ден – {day.toLocaleDateString('bg-BG')}</div>
      <div className="overflow-x-auto">
        <div className={gridClass} style={{gridTemplateColumns: gridCols}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {hours.map(h=>(<div key={h} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{h}:00</div>))}
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className={"h-16 border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              {hours.map((h,i)=>{
                const list = (byHourLane.get(h)?.get(lane)) || [];
                const zebra = ri%2 ? "bg-slate-50/50" : "";
                return (
                  <div key={i} className={"border-r border-b p-1.5 min-h-[64px] "+zebra} onDragOver={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop} onDrop={dropOnCell(h, lane)}>
                    <div className="space-y-1">
                      {list.map(a=>(
                        <div key={a.id} draggable onDragStart={(e)=>dnd.onDragStart(e, a.id)} onDragEnd={dnd.onDragEnd}
                             onClick={()=>onSelect && onSelect(a.id)}
                             className={"text-[10px] px-1.5 py-0.5 rounded bg-white/80 border cursor-move truncate " + (selectedId===a.id?"outline outline-2 outline-amber-400":"")}
                             title={a.title}>{a.title}</div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- App ----
function App(){
  const [view, setView] = useState("month");
  const [anchor, setAnchor] = useState(new Date());
  const [selectedId, setSelectedId] = useState(null);
  const [lanes, setLanes] = useState(["Неразпределени"]);
  const [busFilter, setBusFilter] = useState("Всички");
  const [layoutMode, setLayoutMode] = useState("equal");

  const { orders, ordersById, assignments } = useOrdersAssignments();
  const dnd = useDragAndDrop();

  useEffect(()=>{
    fetch('/buses/api/list').then(r=>r.json()).then(j=>{
      try{
        const active = Array.from(new Set((j.active||[])));
        const inactive = Array.from(new Set((j.inactive||[])));
        const base = ["Неразпределени", ...active];
        const lanesList = inactive.length ? [...base, "НЕАКТИВНИ:", ...inactive] : base;
        setLanes(lanesList);
        window.__INACTIVE_PLATES__ = new Set(inactive);
      }catch(e){ console.warn('buses/api/list parse', e); }
    }).catch(()=>{});
  }, []);

  function onExport(){
    if(!OS || !OS.exportJSON) return;
    const blob = new Blob([OS.exportJSON()], {type:"application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "orders_export.json";
    a.click();
  }
  function onImport(e){
    if(!OS || !OS.importJSON) return;
    const f = e.target.files[0]; if(!f) return;
    const rd = new FileReader();
    rd.onload = () => { OS.importJSON(rd.result); window.dispatchEvent(new CustomEvent("orders:changed")); };
    rd.readAsText(f);
  }

  const selectedOrder = selectedId ? ordersById.get(String(selectedId)) : null;

  return (
    <div className="space-y-4">
      <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor}
               onExport={onExport} onImport={onImport}
               busFilter={busFilter} setBusFilter={setBusFilter} lanes={lanes}
               layoutMode={layoutMode} setLayoutMode={setLayoutMode} />

      <div>
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd}
                                      ordersById={ordersById} lanes={lanes} busFilter={busFilter}
                                      mode={layoutMode} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd}
                                      ordersById={ordersById} lanes={lanes}
                                      mode={layoutMode} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd}
                                      ordersById={ordersById} lanes={lanes}
                                      mode={layoutMode} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>

      <div className="bg-white border rounded-xl p-4">
        <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
        {selectedOrder ? (
          <div className="space-y-2 text_sm">
            <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
            <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
            <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-50 rounded-lg p-2">
                <div className="font-semibold">План</div>
                <div>Приход: {(selectedOrder.price||0).toFixed(2)} €</div>
                <div>Разходи: {Object.values((selectedOrder.planned && selectedOrder.planned.costs) || {}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} €</div>
                <div>Марж: {(((selectedOrder.price||0)-Object.values((selectedOrder.planned and selectedOrder.planned.costs) || {}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} €</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-2">
                <div className="font-semibold">Реално</div>
                <div>Приход: {(selectedOrder.actual && selectedOrder.actual.revenue != null ? selectedOrder.actual.revenue : (selectedOrder.price||0)).toFixed(2)} €</div>
                <div>Разходи: {Object.values((selectedOrder.actual && selectedOrder.actual.costs) || {}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} €</div>
                <div>Марж: {(((selectedOrder.actual && selectedOrder.actual.revenue != null ? selectedOrder.actual.revenue : (selectedOrder.price||0)) - Object.values((selectedOrder.actual && selectedOrder.actual.costs) || {}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} €</div>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
        )}
      </div>
    </div>
  );
}

// ---- Mount ----
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App/>);
