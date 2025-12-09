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
    return ()=> window.removeEventListener("storage", onStorage);
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
    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
      <div className="flex items-center gap-2">
        <div className="inline-flex rounded-2xl border shadow-sm overflow-hidden">
          <button className={`px-3 py-1.5 text-sm ${view==='day'?'bg-slate-900 text-white':''}`} onClick={()=>setView('day')}>Ден</button>
          <button className={`px-3 py-1.5 text-sm ${view==='week'?'bg-slate-900 text-white':''}`} onClick={()=>setView('week')}>Седмица</button>
          <button className={`px-3 py-1.5 text-sm ${view==='month'?'bg-slate-900 text-white':''}`} onClick={()=>setView('month')}>Месец</button>
        </div>
        <div className="inline-flex rounded-2xl border shadow-sm overflow-hidden ml-2">
          <button className="px-3 py-1.5 text-sm hover:bg-slate-50" onClick={()=>setAnchor(new Date())}>Днес</button>
          <button className="px-3 py-1.5 text-sm hover:bg-slate-50" onClick={()=>move(-1)}>◀</button>
          <button className="px-3 py-1.5 text-sm hover:bg-slate-50" onClick={()=>move(1)}>▶</button>
        </div>
        <input type="date" className="ml-2 px-3 py-1.5 text-sm border rounded-xl" value={isoDate(anchor)} onChange={(e)=>setAnchor(new Date(e.target.value))} />
        <a href="/orders#new" className="ml-2 px-3 py-1.5 text-sm rounded-xl border">+ Нова поръчка</a>
      </div>
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold">{label()}</div>
        <div className="inline-flex rounded-2xl border shadow-sm overflow-hidden ml-2">
          <button className="px-3 py-1.5 text-sm hover:bg-slate-50" onClick={onExport}>Експорт JSON</button>
          <label className="px-3 py-1.5 text-sm hover:bg-slate-50 cursor-pointer">
            Импорт JSON
            <input type="file" accept="application/json" className="hidden" onChange={(e)=>{ const f=e.target.files?.[0]; if(!f) return; onImport(f); }}/>
          </label>
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
    return (e)=>{ e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); if(!id) return;
      return setOrderTime(id, date);
    };
  }
  function dropOnDateHour(date, hour){
    return (e)=>{ e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); if(!id) return;
      return setOrderTime(id, new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour, 0));
    };
  }
  return { dragId, onDragStart, onDragEnd, dropOnDate, dropOnDateHour, allowDrop };
}

/* Views */

function MonthView({anchor, assignments, dnd, ordersById}){
  const total = daysInMonth(anchor);
  const days = Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1));
  const lanes = ["W3200MW","W3201MW","W3202MW","W3203MW","W3204MW"];

  const byDayLane = useMemo(()=>{
    const map = new Map();
    days.forEach(d=>{
      const k = isoDate(d);
      const lm = new Map(); lanes.forEach(l=>lm.set(l, []));
      map.set(k, lm);
    });
    assignments.forEach(a=>{
      const k = isoDate(startOfDay(a.from));
      const o = ordersById?.get(String(a.id));
      const plate = (o?.vehicle_plate && lanes.includes(o.vehicle_plate)) ? o.vehicle_plate : lanes[(Math.abs(String(a.id).split('').reduce((s,ch)=>s+ch.charCodeAt(0),0))) % lanes.length];
      if(map.has(k)) map.get(k).get(plate).push(a);
    });
    return map;
  }, [assignments, anchor, ordersById]);

  const cellClass = "w-12 border-r p-1.5 shrink-0 min-h-[64px]";

  function dropOnCell(date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if(!id) return;
      const asn = assignments.find(x=> String(x.id)===String(id));
      const base = asn ? new Date(asn.from) : new Date(date.getFullYear(), date.getMonth(), date.getDate(), 8, 0);
      const event = new CustomEvent("calendar:setOrderTime", { detail:{ id:String(id), when:base } });
      window.dispatchEvent(event);
      OS.patchOrder(String(id), { vehicle_plate: lane });
    };
  }

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">~25 дни видими по X · 5 автобуса по Y</div>
      </div>
      <div className="flex">
        <div className="w-28 shrink-0 border-r bg-slate-50">
          <div className="h-8 border-b"></div>
          {lanes.map(l=>(<div key={l} className="h-16 border-b px-2 py-2 text-xs font-medium">{l}</div>))}
        </div>
        <div className="overflow-x-auto">
          <div className="min-w-max">
            <div className="h-8 flex">
              {days.map((d,i)=>(
                <div key={i} className="w-12 border-r p-1.5 shrink-0 text-[10px] text-center font-semibold">{d.getDate()}</div>
              ))}
            </div>
            {lanes.map(lane=> (
              <div key={lane} className="flex h-16 border-t">
                {days.map((d,i)=>{
                  const list = byDayLane.get(isoDate(d))?.get(lane) || [];
                  return (
                    <div key={i} className={cellClass} onDragOver={dnd.allowDrop} onDrop={dropOnCell(d, lane)}>
                      <div className="space-y-1">
                        {list.map(a=>(
                          <div key={a.id} draggable onDragStart={(e)=>dnd.onDragStart(e, a.id)} onDragEnd={dnd.onDragEnd}
                               className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 border cursor-move truncate" title={a.title}>
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
    <div className="grid grid-cols-7 gap-2">
      {days.map((d,i)=>{
        const list = itemsByDay.get(isoDate(d))||[];
        return (
          <div key={i} className="bg-white border rounded-xl p-3" onDragOver={dnd.allowDrop} onDrop={dnd.dropOnDate(d)}>
            <div className="text-sm font-semibold mb-2">{d.toLocaleDateString('bg-BG',{weekday:'short', day:'2-digit', month:'short'})}</div>
            <div className="space-y-2">
              {list.map(a=>(
                <div key={a.id} className="border rounded-lg p-2 cursor-move" draggable onDragStart={(e)=>dnd.onDragStart(e, a.id)} onDragEnd={dnd.onDragEnd}>
                  <div className="text-sm font-medium">{a.title}</div>
                  <div className="text-xs text-slate-500">{fmtTime(a.from)} – {fmtTime(a.to)}</div>
                </div>
              ))}
              {list.length===0 && <div className="text-xs text-slate-400">Няма задачи</div>}
            </div>
          </div>
        );
      })}
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
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm text-slate-600">{anchor.toLocaleDateString('bg-BG',{weekday:'long', day:'2-digit', month:'long', year:'numeric'})}</div>
      <div className="grid grid-cols-1">
        {hours.map(h=>{
          const items = byHour.get(h)||[];
          return (
            <div key={h} className="border-t px-3 py-2 min-h-[56px]" onDragOver={dnd.allowDrop} onDrop={dnd.dropOnDateHour(anchor, h)}>
              <div className="text-xs text-slate-500 mb-1">{String(h).padStart(2,'0')}:00</div>
              <div className="flex flex-wrap gap-2">
                {items.map(a=>(
                  <div key={a.id} className="border rounded-lg px-2 py-1 cursor-move" draggable onDragStart={(e)=>dnd.onDragStart(e, a.id)} onDragEnd={dnd.onDragEnd}>
                    <div className="text-xs font-medium">{a.title}</div>
                    <div className="text-[10px] text-slate-500">{fmtTime(a.from)} – {fmtTime(a.to)}</div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* App */
function App(){
  const [view, setView] = useState("month");
  const [anchor, setAnchor] = useState(new Date());
  const { orders, ordersById, assignments, refresh } = useOrdersAssignments();

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

  const onExport = ()=> exportJSON({ orders });
  const onImport = (file)=> importJSONFile(file, (data)=>{
    if(Array.isArray(data?.orders)){
      // Merge naive
      data.orders.forEach(o=> OS.upsertOrder(o));
      refresh();
    }
  });

  return (
    <div className="p-4 space-y-4">
      <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} onExport={onExport} onImport={onImport} />
      {view==="month" && <MonthView anchor={anchor} assignments={assignments} dnd={dnd} ordersById={ordersById} />}
      {view==="week"  && <WeekView  anchor={anchor} assignments={assignments} dnd={dnd} />}
      {view==="day"   && <DayView   anchor={anchor} assignments={assignments} dnd={dnd} />}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App/>);
