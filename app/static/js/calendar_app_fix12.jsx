// build: fix12
console.log('calendar_app_fix12.jsx loaded (fix12)');
const { useState, useEffect, useMemo, useRef } = React;
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
  const [orders, setOrders] = useState(OS.listOrders());
  useEffect(()=>{
    const h = ()=> setOrders(OS.listOrders());
    window.addEventListener("orders:changed", h);
    return ()=> window.removeEventListener("orders:changed", h);
  }, []);
  const assignments = useMemo(()=>{
    return orders.map(o=>{
      const [sh,sm] = (o.startTime||"08:00").split(":").map(n=>parseInt(n||0,10));
      const [eh,em] = (o.endTime||"10:00").split(":").map(n=>parseInt(n||0,10));
      const from = new Date(o.date ? o.date+"T"+hh(sh)+":"+hh(sm)+":00" : new Date());
      const to   = new Date(o.date ? o.date+"T"+hh(eh)+":"+hh(em)+":00" : new Date());
      return { id: String(o.id), title: (o.title || (o.origin? (o.origin + " → " + (o.destination||"")) : "Поръчка #"+o.id)), from, to };
    });
  }, [orders]);
  const ordersById = useMemo(()=>{ const m=new Map(); orders.forEach(o=>m.set(String(o.id), o)); return m; }, [orders]);
  return { orders, ordersById, assignments, refresh: ()=> setOrders(OS.listOrders()) };
}

// ---- DnD helpers ----
function useDragAndDrop(onSetTime){
  const allowDrop = (e)=> e.preventDefault();
  const onDragStart = (e, id)=>{ e.dataTransfer.setData("text/plain", String(id)); };
  const onDragEnd = ()=>{};
  return { allowDrop, onDragStart, onDragEnd };
}

// ---- Toolbar ----
function Toolbar({view, setView, anchor, setAnchor, onExport, onImport, busFilter, setBusFilter, lanes}){
  function go(deltaDays){
    const d = new Date(anchor);
    d.setDate(d.getDate()+deltaDays);
    setAnchor(d);
  }
  return (
    <div className="flex items-center justify-between bg-white border rounded-xl px-3 py-2">
      <div className="flex items-center gap-2">
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>go(-30)}>«</button>
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>go(-7)}>‹</button>
        <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG', {month:'long', year:'numeric'})}</div>
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>go(7)}>›</button>
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

// ---- Views ----
function MonthView({anchor, assignments, dnd, ordersById, lanes=[], busFilter='Всички', onSelect, selectedId}){
  const total = daysInMonth(anchor);
  const days = Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1));
  const lanesToShow = (busFilter==='Всички') ? lanes : lanes.filter(l=>l===busFilter);

  const headerRef = useRef(null);
  useEffect(()=>{
    try{
      const today = new Date();
      if(today.getMonth()!==anchor.getMonth() || today.getFullYear()!==anchor.getFullYear()) return;
      const idx = today.getDate()-1;
      const cellW = 48;
      const el = headerRef.current;
      if(el){ el.scrollLeft = Math.max(0, idx*cellW - 120); }
    }catch{}
  }, [anchor]);

  const byDayLane = useMemo(()=>{
    const map = new Map();
    days.forEach(d=>{
      const k = isoDate(d);
      const laneMap = new Map();
      lanes.forEach(l=>laneMap.set(l, []));
      map.set(k, laneMap);
    });
    assignments.forEach(a=>{
      const k = isoDate(startOfDay(a.from));
      const o = ordersById.get(String(a.id));
      const plate = (o && o.vehicle_plate && lanes.includes(o.vehicle_plate)) ? o.vehicle_plate : 'Неразпределени';
      if(map.has(k)){ map.get(k).get(plate).push(a); }
    });
    return map;
  }, [assignments, anchor, ordersById, lanes]);

  function dropOnCell(date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      // time (8:00 default or preserve duration)
      const asn = assignments.find(x=> String(x.id)===String(id));
      const from = new Date(date.getFullYear(), date.getMonth(), date.getDate(), asn?asn.from.getHours():8, asn?asn.from.getMinutes():0);
      const to   = new Date(from.getTime() + (asn ? (asn.to - asn.from) : 2*60*60*1000));
      if(OS && OS.updateOrderTime){
        OS.updateOrderTime(String(id), isoDate(from), hh(from.getHours())+":"+hh(from.getMinutes()), hh(to.getHours())+":"+hh(to.getMinutes()));
      }
      if(OS && OS.patchOrder){
        OS.patchOrder(String(id), { vehicle_plate: (lane==='Неразпределени'?'':lane) });
      }
      window.dispatchEvent(new CustomEvent("orders:changed"));
      if(typeof onSelect==='function') onSelect(id);
    };
  }

  const cellClass = "w-12 border-r p-1.5 shrink-0 min-h-[64px]";

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">Дни по X (~25 видими) · Автобуси по Y</div>
      </div>
      <div className="flex">
        <div className="w-32 shrink-0 border-r bg-slate-50">
          <div className="h-8 border-b"></div>
          {lanesToShow.map(l=>(<div key={l} className="h-16 border-b px-2 py-2 text-xs font-medium">{l}</div>))}
        </div>
        <div className="overflow-x-auto" ref={headerRef}>
          <div className="min-w-max flex">
            <div className="h-8 flex">
              {days.map((d,i)=>(
                <div key={i} className="w-12 border-r p-1.5 shrink-0 text-[10px] text-center font-semibold">{d.getDate()}</div>
              ))}
            </div>
          </div>
          <div className="min-w-max">
            {lanesToShow.map(lane=> (
              <div key={lane} className="flex h-16 border-t">
                {days.map((d,i)=>{
                  const list = (byDayLane.get(isoDate(d))?.get(lane)) || [];
                  return (
                    <div key={i} className={cellClass} onDragOver={dnd.allowDrop} onDrop={dropOnCell(d, lane)}>
                      <div className="space-y-1">
                        {list.map(a=>(
                          <div key={a.id}
                               draggable
                               onDragStart={(e)=>dnd.onDragStart(e, a.id)}
                               onDragEnd={dnd.onDragEnd}
                               onClick={()=>onSelect && onSelect(a.id)}
                               className={"text-[10px] px-1.5 py-0.5 rounded bg-slate-100 border cursor-move truncate " + (selectedId===a.id?"outline outline-2 outline-amber-400":"")}
                               title={a.title}>
                            {a.title}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// Simple placeholders for week/day to avoid compile errors
function WeekView({anchor, assignments, dnd, onSelect, selectedId}){
  const start = startOfWeekMonday(anchor);
  const days = Array.from({length: 7}).map((_,i)=> new Date(start.getFullYear(), start.getMonth(), start.getDate()+i));
  return (
    <div className="bg-white border rounded-xl p-3 text-sm text-slate-600">
      Седмичен изглед – в разработка.
    </div>
  );
}
function DayView({anchor, assignments, dnd, onSelect, selectedId}){
  return (
    <div className="bg-white border rounded-xl p-3 text-sm text-slate-600">
      Дневен изглед – в разработка.
    </div>
  );
}

// ---- App ----
function App(){
  const [view, setView] = useState("month");
  const [anchor, setAnchor] = useState(new Date());
  const [selectedId, setSelectedId] = useState(null);
  const [lanes, setLanes] = useState(["Неразпределени","W3200MW","W3201MW","W3202MW","W3203MW","W3204MW"]);
  const [busFilter, setBusFilter] = useState("Всички");

  const { orders, ordersById, assignments, refresh } = useOrdersAssignments();
  const dnd = useDragAndDrop(()=>{});

  // Try fetch buses → dynamic lanes
  useEffect(()=>{
    fetch('/buses/api/list').then(r=>r.json()).then(j=>{
      try{
        const plates = (j.buses||[]).map(b=> b.plate || b.reg || b.id).filter(Boolean);
        const uniq = Array.from(new Set(plates));
        if(uniq.length) setLanes(["Неразпределени", ...uniq]);
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

  return (
    <div className="p-4">
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12">
          <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor}
                   onExport={onExport} onImport={onImport}
                   busFilter={busFilter} setBusFilter={setBusFilter} lanes={lanes} />
        </div>
        <div className="col-span-12 lg:col-span-9 space-y-4">
          {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd}
                                        ordersById={ordersById} lanes={lanes} busFilter={busFilter}
                                        onSelect={setSelectedId} selectedId={selectedId} />}
          {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd}
                                        onSelect={setSelectedId} selectedId={selectedId} />}
          {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd}
                                        onSelect={setSelectedId} selectedId={selectedId} />}
        </div>
        <div className="col-span-12 lg:col-span-3">
          <div className="bg-white border rounded-xl p-4 h-full">
            <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
            {selectedId && ordersById.get(String(selectedId)) ? (
              (()=>{
                const o = ordersById.get(String(selectedId));
                const planCosts = Object.values((o.planned && o.planned.costs) || {}).reduce((s,v)=>s+Number(v||0),0);
                const actualCosts = Object.values((o.actual && o.actual.costs) || {}).reduce((s,v)=>s+Number(v||0),0);
                const plannedGross = (o.price||0)-planCosts;
                const actualGross = ((o.actual && o.actual.revenue != null ? o.actual.revenue : (o.price||0)))-actualCosts;
                return (
                  <div className="space-y-2 text-sm">
                    <div className="font-medium">{o.origin} → {o.destination}</div>
                    <div className="text-slate-600">{o.date} · {o.startTime}–{o.endTime}</div>
                    <div className="text-slate-600">Автобус: {o.vehicle_plate || '—'} · Вид: {o.bus_type||'—'} · Пътници: {o.pax_count||0}</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="bg-slate-50 rounded-lg p-2">
                        <div className="font-semibold">План</div>
                        <div>Приход: {(o.price||0).toFixed(2)} лв</div>
                        <div>Разходи: {planCosts.toFixed(2)} лв</div>
                        <div>Марж: {plannedGross.toFixed(2)} лв</div>
                      </div>
                      <div className="bg-slate-50 rounded-lg p-2">
                        <div className="font-semibold">Реално</div>
                        <div>Приход: {((o.actual && o.actual.revenue != null ? o.actual.revenue : (o.price||0))).toFixed(2)} лв</div>
                        <div>Разходи: {actualCosts.toFixed(2)} лв</div>
                        <div>Марж: {actualGross.toFixed(2)} лв</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                      <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
                    </div>
                  </div>
                );
              })()
            ) : (
              <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Mount ----
const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App/>);