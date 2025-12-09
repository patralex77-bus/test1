// build: fix12m3 — align bars to cell start, auto row height, info panel (+PAX/финанси)
console.log('calendar_app_fix12m3.jsx loaded');

const { useState, useEffect, useMemo, useRef } = React;

/* ========== utils ========== */
const hh = (n)=> String(n).padStart(2,'0');
const num2 = (v)=> {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : '0.00';
};

// ---- ЛОКАЛНИ ДАТИ (без UTC изместване) ----
function makeLocalDate(Y, M0, D, h=12){ return new Date(Y, M0, D, h, 0, 0, 0); }
function parseYMDLocal(s){
  if(!s) return null;
  const [Y,M,D] = String(s).slice(0,10).split('-').map(Number);
  if(!Y || !M || !D) return null;
  return makeLocalDate(Y, M-1, D, 12);
}
function ymdLocal(d){
  const Y = d.getFullYear(), M = hh(d.getMonth()+1), D = hh(d.getDate());
  return `${Y}-${M}-${D}`;
}
const isoDate = (d)=> ymdLocal(d);
const startOfDay = (d)=> makeLocalDate(d.getFullYear(), d.getMonth(), d.getDate(), 12);
const daysInMonth = (anchor)=> new Date(anchor.getFullYear(), anchor.getMonth()+1, 0).getDate();
const addDays = (date, delta)=> makeLocalDate(date.getFullYear(), date.getMonth(), date.getDate()+delta, 12);
const startOfWeekMonday = (d)=> {
  const nd = makeLocalDate(d.getFullYear(), d.getMonth(), d.getDate(), 12);
  const day = (nd.getDay()+6)%7; nd.setDate(nd.getDate()-day);
  return nd;
};

/* ========== status meta ========== */
const STATUS_META = {
  "Планирана":    { bg:"bg-sky-50",    border:"border-sky-400",    pill:"bg-sky-100 text-sky-800" },
  "В изпълнение": { bg:"bg-amber-50",  border:"border-amber-400",  pill:"bg-amber-100 text-amber-800" },
  "Завършена":    { bg:"bg-emerald-50",border:"border-emerald-400",pill:"bg-emerald-100 text-emerald-800" },
  "Отменена":     { bg:"bg-rose-50",   border:"border-rose-400",   pill:"bg-rose-100 text-rose-800" },
  "Фактурирана":  { bg:"bg-indigo-50", border:"border-indigo-400", pill:"bg-indigo-100 text-indigo-800" },
};
const DEFAULT_STATUS = "Планирана";

/* ========== local storage flat ========== */
function lsGetFlat(){
  try{ const a = JSON.parse(localStorage.getItem('busops:orders_v1')||'[]'); return Array.isArray(a)?a:[]; }catch{ return []; }
}
function lsSetFlat(arr){
  try{
    localStorage.setItem('busops:orders_v1', JSON.stringify(arr||[]));
    localStorage.setItem('orders_fallback_store_v1', JSON.stringify(arr||[]));
  }catch{}
}
function emitChanged(){ try{ window.dispatchEvent(new CustomEvent('orders:changed')); }catch{} }

function flatReplaceAllById(id, fresh){
  const src = lsGetFlat();
  const rest = src.filter(x=> String(x.id)!==String(id));
  const merged = rest.concat(fresh);
  lsSetFlat(merged);
  emitChanged();
}
function flatSetStatus(id, status){
  const arr = lsGetFlat().map(r => String(r.id)===String(id) ? {...r, status} : r);
  lsSetFlat(arr); emitChanged();
}

/* ========== server calls (fire-and-forget) ========== */
function persistRangeOnServer(id, start_date, end_date, vehicle_plate, status){
  fetch('/orders/api/update_range', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id, start_date, end_date, vehicle_plate, status })
  }).catch(()=>{});
}
function persistStatus(id, status){
  fetch('/orders/api/set_status', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id:String(id), status:String(status) })
  }).catch(()=>{});
}

/* ========== data hooks ========== */
function useFlatOrders(){
  const [flat, setFlat] = useState([]);
  useEffect(()=>{
    let alive = true;
    (async function(){
      try{
        const r = await fetch('/orders/api/calendar_flat', {cache:'no-store'});
        const j = await r.json();
        const arr = Array.isArray(j.orders) ? j.orders : [];
        if(!alive) return;
        lsSetFlat(arr);
        setFlat(arr);
        emitChanged();
      }catch{
        setFlat(lsGetFlat());
      }
    })();
    const onChange = ()=> setFlat(lsGetFlat());
    window.addEventListener('orders:changed', onChange);
    return ()=> { alive=false; window.removeEventListener('orders:changed', onChange); };
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
        const active = Array.from(new Set(j.active||[]));
        const inactive = Array.from(new Set(j.inactive||[]));
        const list = inactive.length ? ["Неразпределени", ...active, "НЕАКТИВНИ:", ...inactive] : ["Неразпределени", ...active];
        setLanes(list);
        window.__INACTIVE_PLATES__ = new Set(inactive||[]);
      }catch{}
    })();
  }, []);
  return lanes;
}

/* ========== build per-day per-lane ========== */
function buildByDayLane(days, lanes, flat){
  const map = new Map();
  days.forEach(d=>{
    const k = isoDate(d);
    const laneMap = new Map();
    lanes.forEach(l=>laneMap.set(l, []));
    map.set(k, laneMap);
  });
  (flat||[]).forEach(o=>{
    let plate = o.vehicle_plate || 'Неразпределени';
    if(!lanes.includes(plate)) plate = 'Неразпределени';
    const lm = map.get(o.date);
    if(lm) lm.get(plate).push(o);
  });
  return map;
}

/* ========== compute spans (continuous bars) ========== */
function computeSpans(days, lane, byDayLane){
  const spans = [];
  const dayKeys = days.map(isoDate);
  const byId = new Map();
  dayKeys.forEach((k, idx)=>{
    const list = (byDayLane.get(k)?.get(lane)) || [];
    list.forEach(o=>{
      const id = String(o.id);
      (byId.get(id) || byId.set(id, []).get(id)).push({ idx, o });
    });
  });
  byId.forEach(entries=>{
    entries.sort((a,b)=> a.idx - b.idx);
    let i=0;
    while(i<entries.length){
      const startIdx = entries[i].idx;
      const meta = entries[i].o;
      let j=i+1, last=startIdx;
      while(j<entries.length && entries[j].idx===last+1){ last=entries[j].idx; j++; }
      const len = last - startIdx + 1;
      const driver_id   = meta.driver_id ?? meta.driverId ?? null;
      const driver_name = meta.driver_name ?? meta.driverName ?? '';
      spans.push({
        id: String(meta.id),
        startIdx, endIdx:last, len,
        title: meta.title || ('Поръчка #'+meta.id),
        startTime: meta.startTime || '08:00',
        endTime: meta.endTime || '10:00',
        description: meta.description || "",
        status: meta.status || DEFAULT_STATUS,
        driver_id,
        driver_name
      });
      i=j;
    }
  });
  return spans;
}

/* ========== assign stack levels (prevent overlap) ========== */
function assignLevels(spans){
  const sorted = [...spans].sort((a,b)=> a.startIdx - b.startIdx || a.endIdx - b.endIdx);
  const ends=[];
  sorted.forEach(sp=>{
    let lvl=0;
    while(ends[lvl]!=null && ends[lvl] >= sp.startIdx) lvl++;
    ends[lvl] = sp.endIdx;
    sp._level = lvl;
  });
  return { spans: sorted, maxLevel: Math.max(0, ends.length-1) };
}

/* ========== DnD full-range (VERTICAL ONLY) ========== */
function useDragAndDrop(){
  const allowDrop = (e)=> e.preventDefault();
  const onDragStart = (e, id)=> e.dataTransfer.setData('text/plain', String(id));
  const onDragEnd = ()=>{};

  // при drop променяме САМО лентата (vehicle_plate), датите остават същите
  function onDropToCell(_date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData('text/plain');
      if(!id) return;

      // всички плоски записи за тази поръчка, по оригиналните ѝ дати
      const all = lsGetFlat()
        .filter(x=> String(x.id)===String(id))
        .sort((a,b)=> (a.date<b.date?-1: a.date>b.date?1:0));
      if(!all.length) return;

      const first = all[0];
      const originalStart = all[0].date;
      const originalEnd   = all[all.length-1].date;

      // новата лента → нова табела; за "Неразпределени" чистим табелата
      const plate = (lane==='Неразпределени' || lane==='НЕАКТИВНИ:') ? '' : lane;

      // обнови локалния flat: същите дати/часове/статус, само vehicle_plate
      const fresh = all.map(o => ({
        ...o,
        vehicle_plate: plate
      }));

      flatReplaceAllById(id, fresh);

      // бекенд: подай същия диапазон, само новата табела (статус – текущия)
      const status = first.status || DEFAULT_STATUS;
      persistRangeOnServer(String(id), originalStart, originalEnd, plate, status);
    };
  }
  return { allowDrop, onDragStart, onDragEnd, onDropToCell };
}

/* ========== status popup ========== */
const StatusMenu = {
  el: null, onPick: null,
  ensure(){
    if(this.el) return this.el;
    const div = document.createElement('div');
    div.className = "fixed z-50 bg-white border rounded-xl shadow p-1 text-sm";
    div.style.display = 'none';
    const opts = ["Планирана","В изпълнение","Завършена","Отменена","Фактурирана"];
    div.innerHTML = opts.map(s=> `<button data-status="${s}" class="w-full text-left px-3 py-1 rounded hover:bg-slate-100">${s}</button>`).join('');
    div.addEventListener('click', (e)=>{
      const btn = e.target.closest('button[data-status]');
      if(!btn) return;
      const st = btn.getAttribute('data-status');
      const cb = this.onPick; this.hide();
      if(typeof cb==='function') cb(st);
    });
    document.body.appendChild(div);
    this.el = div; return div;
  },
  show(x, y, current, onPick){
    const el = this.ensure();
    this.onPick = onPick;
    el.querySelectorAll('button').forEach(b=>{
      const st = b.getAttribute('data-status');
      b.classList.toggle('bg-slate-100', st===current);
      b.classList.toggle('font-medium', st===current);
    });
    el.style.left = x+'px';
    el.style.top  = y+'px';
    el.style.display = 'block';
    setTimeout(()=> document.addEventListener('mousedown', this._hideOnce = (ev)=>{ if(!el.contains(ev.target)) this.hide(); }, {once:true}), 0);
  },
  hide(){ if(this.el) this.el.style.display='none'; this.onPick = null; }
};

/* ========== LaneRow (align + auto height) ========== */
function LaneRow({lane, days, byDayLane, onDropCell, allowDrop, dnd, onPickStatus, setSelectedId}){
  const rowRef = useRef(null);
  const [cellW, setCellW] = useState(60);

  const spansRaw = useMemo(()=> computeSpans(days, lane, byDayLane), [days, lane, byDayLane]);
  const { spans, maxLevel } = useMemo(()=> assignLevels(spansRaw), [spansRaw]);

  const barH = 37, gap = 6, padTop = 8, padBottom = 8;
  const overlayHeight = padTop + (maxLevel+1)*barH + maxLevel*gap + padBottom;

  useEffect(()=>{
    const measure = ()=>{
      const el = rowRef.current;
      if(!el) return;
      const cell = el.querySelector('[data-cell]');
      if(cell){
        const w = cell.getBoundingClientRect().width;
        if(w>0) setCellW(w);
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return ()=> window.removeEventListener('resize', measure);
  }, [overlayHeight]);

  function barClass(status, isUnassigned){
    if(isUnassigned){
      return "pointer-events-auto absolute top-0 left-0 text-[11px] px-2 py-[5px] rounded border cursor-move truncate bg-rose-50 border-rose-500";
    }
    const meta = STATUS_META[status] || STATUS_META[DEFAULT_STATUS];
    return `pointer-events-auto absolute top-0 left-0 text-[11px] px-2 py-[5px] rounded border cursor-move truncate ${meta.bg} ${meta.border}`;
  }

  function onBarClick(e, sp){
    setSelectedId && setSelectedId(String(sp.id));
    StatusMenu.show(e.clientX, e.clientY, sp.status, (picked)=>{
      flatSetStatus(sp.id, picked);
      persistStatus(sp.id, picked);
      onPickStatus && onPickStatus(sp.id, picked);
    });
  }

  return (
    <div className="relative" style={{minHeight: overlayHeight+'px'}}>
      <div ref={rowRef} className="grid" style={{gridTemplateColumns:`repeat(${days.length}, minmax(0, 1fr))`}}>
        {days.map((d,i)=>(
          <div key={i}
               data-cell
               className="border-r border-b p-1.5"
               style={{minHeight: overlayHeight+'px'}}
               onDragOver={allowDrop}
               onDrop={onDropCell(d, lane)} />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-0">
        {spans.map(sp=>{
          const left = sp.startIdx * cellW;
          const width = sp.len * cellW - 1;
          const top = padTop + sp._level*(barH + gap);
          const meta = STATUS_META[sp.status] || STATUS_META[DEFAULT_STATUS];
          const desc = sp.description ? (' — ' + sp.description) : '';
          const unassignedDriver = !(sp.driver_id || sp.driver_name);
          return (
            <div key={sp.id + ':' + sp.startIdx}
                 className={barClass(sp.status, unassignedDriver)}
                 style={{left:left+'px', width:Math.max(24,width)+'px', top:top+'px', height:(barH-6)+'px'}}
                 draggable
                 onDragStart={(e)=>dnd.onDragStart(e, sp.id)}
                 onClick={(e)=> onBarClick(e, sp)}
                 title={`${sp.title} · ${sp.startTime}-${sp.endTime}${desc}${unassignedDriver?' · без шофьор':''}`}>
              <span className="font-medium">{sp.title}</span>
              {sp.description ? <span className="opacity-80">{desc}</span> : null}
              <span className={`ml-2 inline-block align-middle text-[10px] px-1 py-[1px] rounded ${meta.pill}`}>{sp.status}</span>
              {unassignedDriver ? <span className="ml-2 inline-block align-middle text-[10px] px-1 py-[1px] rounded bg-rose-100 text-rose-800 border border-rose-300">без шофьор</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ========== Views (Month/Week/Day) ========== */
function MonthView({anchor, flat, lanes, dnd, setSelectedId, setInfoSummary}){
  const total = daysInMonth(anchor);
  const days = useMemo(
    ()=> Array.from({length: total}).map((_,i)=> makeLocalDate(anchor.getFullYear(), anchor.getMonth(), i+1, 12)),
    [anchor,total]
  );
  const byDayLane = useMemo(()=> buildByDayLane(days, lanes, flat), [days, lanes, flat]);

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">Клик за статус · Диапазон DnD</div>
      </div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto repeat(${days.length}, minmax(0, 1fr))`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(<div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.getDate()}</div>))}
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium"
                   style={{height:'100%'}}>{lane}</div>
              <div style={{gridColumn:`span ${days.length}`}}>
                <LaneRow
                  lane={lane} days={days} byDayLane={byDayLane}
                  onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                  allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                  dnd={dnd}
                  setSelectedId={setSelectedId}
                />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

function WeekView({anchor, flat, lanes, dnd, setSelectedId}){
  const start = startOfWeekMonday(anchor);
  const days = useMemo(()=> Array.from({length:7}).map((_,i)=> addDays(start,i)), [anchor]);
  const byDayLane = useMemo(()=> buildByDayLane(days, lanes, flat), [days, lanes, flat]);

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Седмица</div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto repeat(7, minmax(0, 1fr))`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(<div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.toLocaleDateString('bg-BG',{weekday:'short', day:'2-digit'})}</div>))}
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium">{lane}</div>
              <div style={{gridColumn:'span 7'}}>
                <LaneRow
                  lane={lane} days={days} byDayLane={byDayLane}
                  onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                  allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                  dnd={dnd}
                  setSelectedId={setSelectedId}
                />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

function DayView({anchor, flat, lanes, dnd, setSelectedId}){
  const day = startOfDay(anchor);
  const byDayLane = useMemo(()=> buildByDayLane([day], lanes, flat), [anchor, lanes, flat]);

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Ден – {day.toLocaleDateString('bg-BG')}</div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto minmax(0, 1fr)`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          <div className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">Поръчки</div>
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium">{lane}</div>
              <div>
                <LaneRow
                  lane={lane} days={[day]} byDayLane={byDayLane}
                  onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                  allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                  dnd={dnd}
                  setSelectedId={setSelectedId}
                />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ========== Info panel helper (локално обобщение) ========== */
function summarizeOrder(flat, id){
  const group = flat.filter(o=> String(o.id)===String(id)).sort((a,b)=> (a.date<b.date?-1: a.date>b.date?1:0));
  if(!group.length) return null;
  const t = group[0];
  const driver_id   = t.driver_id ?? t.driverId ?? null;
  const driver_name = t.driver_name ?? t.driverName ?? '';
  return {
    id: String(id),
    title: t.title || ('Поръчка #'+id),
    plate: t.vehicle_plate || '',
    start_date: group[0].date,
    end_date: group[group.length-1].date,
    startTime: t.startTime || '08:00',
    endTime: t.endTime || '10:00',
    days: group.length,
    description: t.description || '',
    status: t.status || DEFAULT_STATUS,
    driver_id,
    driver_name
  };
}

/* ========== App ========== */
function App(){
  const [view, setView] = useState('month');
  const [anchor, setAnchor] = useState(new Date());
  const [selectedId, setSelectedId] = useState(null);

  const [snap, setSnap] = useState(null);            // <-- snapshot от бекенда (финанси + PAX)
  const [snapLoading, setSnapLoading] = useState(false);
  const [snapError, setSnapError] = useState('');

  const flat = useFlatOrders();
  const lanes = useLanes();
  const dnd = useDragAndDrop();

  const summary = useMemo(()=> selectedId ? summarizeOrder(flat, selectedId) : null, [flat, selectedId]);

  // Зареждане на snapshot когато се избере поръчка
  useEffect(()=>{
    let alive = true;
    setSnap(null); setSnapError('');
    if(!selectedId){ return; }
    (async function(){
      try{
        setSnapLoading(true);
        const res = await fetch(`/orders/api/cabinet/snapshot?id=${encodeURIComponent(selectedId)}`, { headers:{'Accept':'application/json'} });
        if(!res.ok) throw new Error('HTTP '+res.status);
        const j = await res.json();
        if(!alive) return;
        setSnap(j && j.summary ? j.summary : null);
      }catch(err){
        if(!alive) return;
        setSnapError('Неуспешно зареждане на финансова информация.');
      }finally{
        if(alive) setSnapLoading(false);
      }
    })();
    return ()=>{ alive=false; };
  }, [selectedId]);

  // Синхронизираме статус на бара и панела (ако потребителят го смени)
  function handlePickStatus(){ /* нищо специално—панелът ще се рефрешне при следващ избор */ }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 bg-white border rounded-xl px-3 py-2">
        {view==='month' ? (
          <>
            <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setMonth(d.getMonth()-1); setAnchor(d); }}>«</button>
            <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG', {month:'long', year:'numeric'})}</div>
            <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setMonth(d.getMonth()+1); setAnchor(d); }}>»</button>
          </>
        ) : (
          <>
            <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setDate(d.getDate()+(view==='week'?-7:-1)); setAnchor(d); }}>{view==='week'?'« 7':'« 1'}</button>
            <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG')}</div>
            <button className="px-3 py-1.5 rounded-xl border" onClick={()=>{ const d=new Date(anchor); d.setDate(d.getDate()+(view==='week'?7:1)); setAnchor(d); }}>{view==='week'?'7 »':'1 »'}</button>
          </>
        )}
        <div className="ml-2">
          <button className={"px-2 py-1 text-xs rounded "+(view==='day'?'bg-slate-900 text-white':'border')} onClick={()=>setView('day')}>Ден</button>
          <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='week'?'bg-slate-900 text-white':'border')} onClick={()=>setView('week')}>Седмица</button>
          <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='month'?'bg-slate-900 text-white':'border')} onClick={()=>setView('month')}>Месец</button>
        </div>
        <a href="/orders#new" className="ml-2 px-3 py-1.5 text-sm rounded-xl border">+ Нова поръчка</a>
      </div>

      {/* Views */}
      {view==='month' && <MonthView anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} setSelectedId={setSelectedId} />}
      {view==='week'  && <WeekView  anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} setSelectedId={setSelectedId} />}
      {view==='day'   && <DayView   anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} setSelectedId={setSelectedId} />}

       {/* Info panel */}
      <div className="bg-white border rounded-xl p-4">
        <div className="text-sm font-semibold mb-2">Информация за поръчка</div>

        {!summary && (
          <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
        )}

        {summary && (
          <div className="space-y-3 text-sm">
            <div className="font-medium">{summary.title}</div>
            <div className="text-slate-600">
              Диапазон: {summary.start_date} → {summary.end_date} ({summary.days} дни) · Часове: {summary.startTime}–{summary.endTime}
            </div>

            {/* Таблично резюме: основно + финанси */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="border rounded-xl p-3">
                <div className="text-xs text-slate-500 mb-1">Основно</div>
                <table className="w-full">
                  <tbody>
                    <tr>
                      <td className="text-slate-500 w-32">Автобус</td>
                      <td>{summary.plate || '—'}</td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Статус</td>
                      <td>
                        {(() => {
                          const st = (snap?.status) ?? summary.status ?? DEFAULT_STATUS;
                          const pill = (STATUS_META[st] || STATUS_META[DEFAULT_STATUS]).pill;
                          return <span className={`${pill} px-2 py-0.5 rounded`}>{st}</span>;
                        })()}
                      </td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">PAX</td>
                      <td>{(snap?.pax ?? '') !== '' && snap?.pax != null ? snap.pax : '—'}</td>
                    </tr>
                    <tr>
                      <td className="text-slate-500">Шофьор</td>
                      <td>
                        {(summary.driver_id || summary.driver_name)
                          ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300">
                              Да{summary.driver_name ? ` — ${summary.driver_name}` : (summary.driver_id ? ` — #${summary.driver_id}` : '')}
                            </span>
                          : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-300">
                              Не (без шофьор)
                            </span>}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="border rounded-xl p-3">
                <div className="text-xs text-slate-500 mb-1">Финанси</div>
                {snapLoading && <div className="text-slate-500">Зареждане…</div>}
                {!snapLoading && snapError && <div className="text-rose-600">{snapError}</div>}
                {!snapLoading && !snapError && (
                  <table className="w-full">
                    <tbody>
                      <tr>
                        <td className="text-slate-500">Цена (приход)</td>
                        <td className="text-right font-mono">{num2(snap?.price)} €</td>
                      </tr>
                      <tr>
                        <td className="text-slate-500">Брутна печалба</td>
                        <td className="text-right font-mono">{num2(snap?.gross_profit)} €</td>
                      </tr>
                      <tr>
                        <td className="text-slate-500">% Маржа</td>
                        <td className="text-right font-mono">{num2(snap?.margin_pct)} %</td>
                      </tr>
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 pt-1">
              {selectedId && (
                <>
                  <a
                    href={`/orders/entry?edit=${encodeURIComponent(selectedId)}`}
                    className="px-3 py-1.5 text-xs rounded-lg border"
                  >
                    Отвори поръчка
                  </a>
                  <a
                    href={`/orders/${encodeURIComponent(selectedId)}`}
                    className="px-3 py-1.5 text-xs rounded-lg border"
                  >
                    Детайл
                  </a>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* mount */
const root = ReactDOM.createRoot(document.getElementById('app'));
root.render(<App />);

