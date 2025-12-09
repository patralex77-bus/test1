// build: fix12m2-min
console.log('calendar_app_fix12m2.jsx (minimal) loaded');

const { useState, useEffect, useMemo, useRef } = React;

// ---- utils ----
function hh(n){ return String(n).padStart(2,'0'); }
function isoDate(d){ return d.toISOString().slice(0,10); }
function startOfDay(d){ return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0,0,0,0); }
function daysInMonth(anchor){ return new Date(anchor.getFullYear(), anchor.getMonth()+1, 0).getDate(); }

// ---- data ----
function useFlatOrders(){
  const [flat, setFlat] = useState([]);
  useEffect(()=>{
    let alive = true;
    (async function(){
      try{
        const r = await fetch('/orders/api/calendar_flat', {cache:'no-store'});
        const j = await r.json();
        if(!alive) return;
        setFlat(Array.isArray(j.orders) ? j.orders : []);
        try{
          // also seed localStorage for other parts of the app
          localStorage.setItem('busops:orders_v1', JSON.stringify(Array.isArray(j.orders) ? j.orders : []));
          localStorage.setItem('orders_fallback_store_v1', JSON.stringify(Array.isArray(j.orders) ? j.orders : []));
          window.dispatchEvent(new CustomEvent('orders:changed'));
        }catch(e){}
      }catch(e){
        console.warn('calendar_flat fetch failed', e);
        setFlat([]);
      }
    })();
    return ()=>{ alive = false; };
  }, []);
  return flat;
}

function useLanes(){
  const [lanes, setLanes] = useState(["Неразпределени"]);
  useEffect(()=>{
    (async function(){
      try{
        const r = await fetch('/buses/api/list');
        const j = await r.json();
        const active = Array.from(new Set((j.active||[])));
        const inactive = Array.from(new Set((j.inactive||[])));
        const base = ["Неразпределени", ...active];
        const list = inactive.length ? [...base, "НЕАКТИВНИ:", ...inactive] : base;
        setLanes(list);
      }catch(e){}
    })();
  }, []);
  return lanes;
}

// ---- MonthView ----
function MonthView({anchor, flat, lanes}){
  const total = daysInMonth(anchor);
  const days = Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1));

  const byDayLane = useMemo(()=>{
    const map = new Map();
    days.forEach(d=>{
      const k = isoDate(d);
      const laneMap = new Map();
      lanes.forEach(l=>laneMap.set(l, []));
      map.set(k, laneMap);
    });
    (flat||[]).forEach(o=>{
      const k = o.date;
      let plate = o.vehicle_plate || 'Неразпределени';
      if(!lanes.includes(plate)) plate = 'Неразпределени';
      if(map.has(k)){ map.get(k).get(plate).push(o); }
    });
    return map;
  }, [flat, lanes, anchor]);

  const gridCols = `auto repeat(${days.length}, minmax(0, 1fr))`;

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">Автобуси по вертикала</div>
      </div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns: gridCols}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(
            <div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.getDate()}</div>
          ))}
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className={"h-16 border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              {days.map((d,i)=>{
                const list = (byDayLane.get(isoDate(d))?.get(lane)) || [];
                const zebra = ri%2 ? "bg-slate-50/50" : "";
                return (
                  <div key={i} className={"border-r border-b p-1.5 min-h-[64px] "+zebra}>
                    <div className="space-y-1">
                      {list.map((o,idx)=>(
                        <div key={o.id + '-' + idx}
                             className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 border border-amber-300 truncate"
                             title={(o.title||'Поръчка') + ' · ' + (o.startTime||'') + '-' + (o.endTime||'')}>
                          {(o.title||'Поръчка')}
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

// ---- App ----
function App(){
  const [anchor, setAnchor] = useState(new Date());
  const flat = useFlatOrders();
  const lanes = useLanes();
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 bg-white border rounded-xl px-3 py-2">
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setMonth(d.getMonth()-1); setAnchor(d); }}>«</button>
        <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG', {month:'long', year:'numeric'})}</div>
        <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setMonth(d.getMonth()+1); setAnchor(d); }}>»</button>
        <a href="/orders#new" className="ml-2 px-3 py-1.5 text-sm rounded-xl border">+ Нова поръчка</a>
      </div>
      <MonthView anchor={anchor} flat={flat} lanes={lanes} />
      <div className="text-xs text-slate-500">Минимален режим (без drag&drop) — показва данни от /orders/api/calendar_flat</div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("app"));
root.render(<App/>);
