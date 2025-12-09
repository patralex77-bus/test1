// build: fix10
console.log('calendar_app_fix9.jsx loaded (fix10)');
// build: fix9
console.log('calendar_app_fix9.jsx loaded (fix9)');
// build: fix8b
console.log('calendar_app_fix8b.jsx loaded (fix8b)');
// build: fix7
console.log('calendar_app_fix7.jsx loaded (fix7)');
// build: fix6 calendar_app.jsx
console.log('calendar_app.jsx loaded (fix6)');
// build: fix5
// build: fix3

const { useState, useMemo, useEffect } = React;
const OS = (window && window.OrdersShared) ? window.OrdersShared : null;

/* Utils */
function startOfDay(d){ const x=new Date(d); x.setHours(0,0,0,0); return x; }
function addDays(d,n){ const x=new Date(d); x.setDate(x.getDate()+n); return x; }
function startOfWeekMonday(d){ const x=startOfDay(d); const day=(x.getDay()+6)%7; x.setDate(x.getDate()-day); return x; }
function daysInMonth(d){ const x=new Date(d); return new Date(x.getFullYear(), x.getMonth()+1, 0).getDate(); }
function isoDate(d){ return d.toISOString().slice(0,10); }
function clampHour(h){ return Math.min(23, Math.max(0, h|0)); }
function copyDateTime(fromDate, toDate){ const o=new Date(toDate); o.setHours(fromDate.getHours(), fromDate.getMinutes(),0,0); return o; }
function fmtTime(d){ return d.toLocaleTimeString('bg-BG',{hour:'2-digit',minute:'2-digit'}); }

/* Orders -> assignments */
function useOrdersAssignments(){
  if(!OS){ return { orders: [], ordersById: new Map(), assignments: [], refresh: ()=>{} }; }
  const [orders, setOrders] = React.useState(OS.listOrders());
  useEffect(()=>{
    const onStorage = (e)=>{ if(e.key==="busops:orders_v1") setOrders(OS.listOrders()); };
    window.addEventListener("storage", onStorage);
    

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

  }, []);
  const assignments = useMemo(()=> orders.map(o=>{
    const [sh,sm]=(o.startTime||"08:00").split(":").map(Number);
    const [eh,em]=(o.endTime||"17:00").split(":").map(Number);
    const day = new Date(o.date+"T00:00:00");
    const from = new Date(day.getFullYear(),day.getMonth(),day.getDate(),sh||8,sm||0);
    const to   = new Date(day.getFullYear(),day.getMonth(),day.getDate(),eh||17,em||0);
    return { id:o.id, title:`${o.origin||""} → ${o.destination||""}`, route:`${o.origin||""} → ${o.destination||""}`, from, to };
  }), [orders]);
  const ordersById = React.useMemo(()=>{ const m=new Map(); orders.forEach(o=>m.set(String(o.id), o)); return m; }, [orders]);
  return { orders, ordersById, assignments, refresh:()=>setOrders(OS.listOrders()) };
}

/* Export/Import */
function exportJSON(data, filename="busops-export.json"){
  const blob = new Blob([JSON.stringify(data,null,2)], {type:"application/json"});
  const url = URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url; a.download=filename; a.click(); URL.revokeObjectURL(url);
}
function importJSONFile(file, onData){
  const reader = new FileReader();
  reader.onload = ()=>{ try{ const data=JSON.parse(reader.result); onData(data); }catch(e){ alert("Invalid JSON"); } };
  reader.readAsText(file);
}

/* Toolbar */
function Toolbar({view,setView,anchor,setAnchor,onExport,onImport}){
  function move(dir){ if(view==="month") setAnchor(addDays(anchor,dir*30)); else if(view==="week") setAnchor(addDays(anchor,dir*7)); else setAnchor(addDays(anchor,dir)); }
  function label(){
    if(view==="month") return anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'});
    if(view==="week"){ const s=startOfWeekMonday(anchor), e=addDays(s,6); return `${s.toLocaleDateString('bg-BG',{day:'2-digit',month:'short'})} – ${e.toLocaleDateString('bg-BG',{day:'2-digit',month:'short',year:'numeric'})}`; }
    return anchor.toLocaleDateString('bg-BG',{day:'2-digit',month:'long',year:'numeric'});
  }
  

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* DnD */
function useDragAndDrop(setOrderTime){
  const [dragId, setDragId] = useState(null);
  function onDragStart(e, id){ e.dataTransfer.setData("text/plain", String(id)); e.dataTransfer.effectAllowed="move"; setDragId(id); }
  function onDragEnd(){ setDragId(null); }
  const allowDrop = (e)=> e.preventDefault();
  function dropOnDate(date){
    

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

    };
  }
  function dropOnDateHour(date, hour){
    

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

    };
  }
  return { dragId, onDragStart, onDragEnd, dropOnDate, dropOnDateHour, allowDrop };
}

/* Views */

function MonthView({anchor, assignments, dnd, ordersById, lanes=[], busFilter='Всички', onSelect, selectedId}){
  // Days of current month
  const total = daysInMonth(anchor);
  const days = Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1));

  // 5 lanes by bus plate
  
  const lanesToShow = (busFilter==='Всички') ? lanes : lanes.filter(l=>l===busFilter);

  // Index assignments by day AND by lane
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
      const o = ordersById?.get(String(a.id));
      const plate = (o?.vehicle_plate && lanes.includes(o.vehicle_plate)) ? o.vehicle_plate
                   : lanes[(Math.abs(String(a.id).split('').reduce((s,ch)=>s+ch.charCodeAt(0),0))) % lanes.length];
      if(map.has(k)){
        map.get(k).get(plate).push(a);
      }
    });
    return map;
  }, [assignments, anchor, ordersById]);

  // cell width ~48px so ~25 days visible on ~1200px screen
  const cellClass = "w-12 border-r p-1.5 shrink-0 min-h-[64px]";

  function dropOnCell(date, lane){
    

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      // Update order time via App's handler + set vehicle_plate
      const asn = assignments.find(x=> String(x.id)===String(id));
      const base = asn ? new Date(asn.from) : new Date(date.getFullYear(), date.getMonth(), date.getDate(), 8, 0);
      const event = new CustomEvent("calendar:setOrderTime", { detail:{ id:String(id), when:base } });
      window.dispatchEvent(event);
      if(OS){ OS.patchOrder(String(id), { vehicle_plate: (lane==='Неразпределени'?'':lane) }); }
    };
  }

  

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
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
        </div>
        <div className="col-span-12 lg:col-span-3">
          <div className="bg-white border rounded-xl p-4 h-full">
            <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
            {selectedId ? (()=>{
              const o = ordersById.get(String(selectedId));
              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
function WeekView({anchor, assignments, dnd}){
  const start = startOfWeekMonday(anchor);
  const days = Array.from({length:7}).map((_,i)=> addDays(start,i));
  const itemsByDay = useMemo(()=>{
    const map = new Map(); days.forEach(d=>map.set(isoDate(d), []));
    assignments.forEach(a=>{ const k=isoDate(startOfDay(a.from)); if(map.has(k)) map.get(k).push(a); });
    return map;
  }, [assignments, anchor]);
  

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
      })}
    </div>
        </div>
        <div className="col-span-12 lg:col-span-3">
          <div className="bg-white border rounded-xl p-4 h-full">
            <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
            {selectedId ? (()=>{
              const o = ordersById.get(String(selectedId));
              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function DayView({anchor, assignments, dnd}){
  const hours = Array.from({length: 16}).map((_,i)=> i+6);
  const list = assignments.filter(a=> isoDate(a.from)===isoDate(anchor));
  const byHour = useMemo(()=>{
    const m = new Map(); hours.forEach(h=>m.set(h, []));
    list.forEach(a=> m.get(a.from.getHours())?.push(a));
    return m;
  }, [list]);
  

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
        })}
      </div>
    </div>
        </div>
        <div className="col-span-12 lg:col-span-3">
          <div className="bg-white border rounded-xl p-4 h-full">
            <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
            {selectedId ? (()=>{
              const o = ordersById.get(String(selectedId));
              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* App */
function App(){
  const [selectedId, setSelectedId] = React.useState(null);
  const [lanes, setLanes] = React.useState(["Неразпределени","W3200MW","W3201MW","W3202MW","W3203MW","W3204MW"]);
  const [busFilter, setBusFilter] = React.useState("Всички");
  const [selectedId, setSelectedId] = React.useState(null);

  const [view, setView] = useState("month");
  const [anchor, setAnchor] = useState(new Date());
  const { orders, ordersById, assignments, refresh } = useOrdersAssignments();
  const selectedOrder = selectedId ? ordersById.get(String(selectedId)) : null;

  // Update order time on drop
  function setOrderTime(id, newStart){
    const asn = assignments.find(a=> String(a.id)===String(id));
    if(!asn) return;
    const dur = (asn.to - asn.from);
    const from = new Date(newStart);
    const to = new Date(from.getTime()+dur);
    const hh = (n)=>String(n).padStart(2,"0");
    OS.updateOrderTime(String(id), from.toISOString().slice(0,10),
      `${hh(from.getHours())}:${hh(from.getMinutes())}`, `${hh(to.getHours())}:${hh(to.getMinutes())}`);
    refresh();
  }
  const dnd = useDragAndDrop(setOrderTime);

  React.useEffect(()=>{
    fetch('/buses/api/list').then(r=>r.json()).then(j=>{
      try{
        const plates = (j.buses||[]).map(b=>b.plate||b.reg||b.id).filter(Boolean);
        const uniq = Array.from(new Set(plates));
        if(uniq.length) setLanes(["Неразпределени", ...uniq]);
      }catch(e){ console.warn('buses/api/list parse', e); }
    }).catch(()=>{});
  }, []);

  const onExport = ()=> exportJSON({ orders });
  const onImport = (file)=> importJSONFile(file, (data)=>{
    if(Array.isArray(data?.orders)){
      // Merge naive
      data.orders.forEach(o=> OS.upsertOrder(o));
      refresh();
    }
  });

  

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

              if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
              const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
              const plannedGross = (o.price||0)-planCosts;
              const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
              

return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

            if(!o) return <div className="text-sm text-slate-500">Няма данни за поръчката.</div>;
            const planCosts = Object.values(o.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const actualCosts = Object.values(o.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0);
            const plannedGross = (o.price||0)-planCosts;
            const actualGross = (o.actual?.revenue??o.price??0)-actualCosts;
            
return (
  <div className="p-4">
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12">
        <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      </div>
      <div className="col-span-12 lg:col-span-9 space-y-4">
        {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} lanes={lanes} busFilter={busFilter} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
        {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} onSelect={setSelectedId} selectedId={selectedId} />}
      </div>
      <div className="col-span-12 lg:col-span-3">
        <div className="bg-white border rounded-xl p-4 h-full">
          <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
          {selectedOrder ? (
            <div className="space-y-2 text-sm">
              <div className="font-medium">{selectedOrder.origin} → {selectedOrder.destination}</div>
              <div className="text-slate-600">{selectedOrder.date} · {selectedOrder.startTime}–{selectedOrder.endTime}</div>
              <div className="text-slate-600">Автобус: {selectedOrder.vehicle_plate || '—'} · Вид: {selectedOrder.bus_type||'—'} · Пътници: {selectedOrder.pax_count||0}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">План</div>
                  <div>Приход: {(selectedOrder.price||0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.price||0)-Object.values(selectedOrder.planned?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-semibold">Реално</div>
                  <div>Приход: {(selectedOrder.actual?.revenue??selectedOrder.price??0).toFixed(2)} лв</div>
                  <div>Разходи: {Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
                  <div>Марж: {(((selectedOrder.actual?.revenue??selectedOrder.price??0)-Object.values(selectedOrder.actual?.costs||{}).reduce((s,v)=>s+Number(v||0),0))).toFixed(2)} лв</div>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <a href="/orders/" className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
                <a href="/orders/#new" className="px-3 py-1.5 text-xs rounded-lg border">Нова поръчка</a>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
          )}
        </div>
      </div>
    </div>
  </div>
);

          })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
        </div>
      </div>
    </div>
  </div>
);

            })() : <div className="text-sm text-slate-500">Избери поръчка от календара.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App/>);
