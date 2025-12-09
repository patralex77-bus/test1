// build: fix12m3 — status click = instant UI + POST, verbose logs
console.log('calendar_app_fix12m3.jsx loaded');

const { useState, useEffect, useMemo, useRef } = React;

const hh = (n)=> String(n).padStart(2,'0');
const isoDate = (d)=> d.toISOString().slice(0,10);
const startOfDay = (d)=> new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0,0,0,0);
const daysInMonth = (anchor)=> new Date(anchor.getFullYear(), anchor.getMonth()+1, 0).getDate();
const addDays = (date, delta)=> { const d=new Date(date); d.setDate(d.getDate()+delta); return d; };
const startOfWeekMonday = (d)=> { const nd=new Date(d); const day=(nd.getDay()+6)%7; nd.setDate(nd.getDate()-day); nd.setHours(0,0,0,0); return nd; };

const STATUS_META = {
  "Планирана":    { bg:"bg-sky-50",    border:"border-sky-400",    pill:"bg-sky-100 text-sky-800" },
  "В изпълнение": { bg:"bg-amber-50",  border:"border-amber-400",  pill:"bg-amber-100 text-amber-800" },
  "Завършена":    { bg:"bg-emerald-50",border:"border-emerald-400",pill:"bg-emerald-100 text-emerald-800" },
  "Отменена":     { bg:"bg-rose-50",   border:"border-rose-400",   pill:"bg-rose-100 text-rose-800" },
  "Фактурирана":  { bg:"bg-indigo-50", border:"border-indigo-400", pill:"bg-indigo-100 text-indigo-800" },
};
const ALL_STATUSES = Object.keys(STATUS_META);
const DEFAULT_STATUS = "Планирана";

/* ===== local storage flat ===== */
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
  console.log('[UI] flatSetStatus', {id, status});
  const arr = lsGetFlat().map(r => String(r.id)===String(id) ? {...r, status} : r);
  lsSetFlat(arr);
  emitChanged();
}

/* ===== server calls (with logs) ===== */
function persistRangeOnServer(id, start_date, end_date, vehicle_plate, status){
  console.log('[POST] /orders/api/update_range', {id, start_date, end_date, vehicle_plate, status});
  fetch('/orders/api/update_range', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id, start_date, end_date, vehicle_plate, status })
  }).then(r=>r.json()).then(j=>{
    console.log('[POST ok] update_range resp', j);
  }).catch(e=> console.error('[POST err] update_range', e));
}
function persistStatus(id, status){
  console.log('[POST] /orders/api/set_status', {id, status});
  fetch('/orders/api/set_status', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id: String(id), status: String(status) })
  }).then(r=>r.json()).then(j=>{
    console.log('[POST ok] set_status resp', j);
  }).catch(e=> console.error('[POST err] set_status', e));
}

/* ===== data hooks ===== */
function useFlatOrders(){
  const [flat, setFlat] = useState([]);
  useEffect(()=>{
    let alive = true;
    (async function(){
      try{
        const r = await fetch('/orders/api/calendar_flat', { cache: 'no-store' });
        const j = await r.json();
        const arr = Array.isArray(j.orders) ? j.orders : [];
        console.log('[GET] calendar_flat items:', arr.length);
        if(!alive) return;
        lsSetFlat(arr);
        setFlat(arr);
        emitChanged();
      }catch(e){
        console.warn('calendar_flat fetch failed, using LS', e);
        setFlat(lsGetFlat());
      }
    })();
    const onChange = ()=> setFlat(lsGetFlat());
    window.addEventListener('orders:changed', onChange);
    return ()=>{ alive=false; window.removeEventListener('orders:changed', onChange); };
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
        console.log('[GET] buses lanes:', list);
      }catch(e){ console.warn('buses/api/list failed', e); }
    })();
  }, []);
  return lanes;
}

/* ===== build spans ===== */
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
      const id = entries[i].o.id;
      const meta = entries[i].o;
      let j=i+1, last=startIdx;
      while(j<entries.length && entries[j].idx===last+1){ last = entries[j].idx; j++; }
      const len = last - startIdx + 1;
      spans.push({
        id: String(id),
        startIdx, len, endIdx: last,
        title: meta.title || ('Поръчка #'+id),
        startTime: meta.startTime || '08:00',
        endTime: meta.endTime || '10:00',
        description: meta.description || "",
        status: meta.status || DEFAULT_STATUS
      });
      i = j;
    }
  });
  return spans;
}
function assignLevels(spans){
  const sorted = [...spans].sort((a,b)=> a.startIdx - b.startIdx || a.endIdx - b.endIdx);
  const levels = [];
  sorted.forEach(sp=>{
    let level=0;
    while(levels[level]!=null && levels[level] >= sp.startIdx) level++;
    levels[level] = sp.endIdx;
    sp._level = level;
  });
  return { spans: sorted, maxLevel: Math.max(0, levels.length-1) };
}

/* ===== DnD ===== */
function useDragAndDrop(){
  const allowDrop = (e)=> e.preventDefault();
  const onDragStart = (e, id)=> e.dataTransfer.setData('text/plain', String(id));
  const onDragEnd = ()=>{};

  function onDropToCell(date, lane){
    return (e)=>{
      e.preventDefault();
      const id = e.dataTransfer.getData('text/plain');
      if(!id) return;
      console.log('[DnD] drop', {id, date: isoDate(date), lane});
      const all = lsGetFlat().filter(x=> String(x.id)===String(id)).sort((a,b)=> (a.date<b.date?-1: a.date>b.date?1:0));
      if(!all.length) return;
      const firstDate = new Date(all[0].date+'T00:00:00');
      const lastDate  = new Date(all[all.length-1].date+'T00:00:00');
      const daysCount = Math.round((lastDate-firstDate)/(24*3600*1000)) + 1;
      const newStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      const newEnd   = addDays(newStart, daysCount-1);

      const first = all[0];
      const [sh,sm] = String(first.startTime||'08:00').split(':').map(x=>parseInt(x||0,10));
      const [eh,em] = String(first.endTime||'10:00').split(':').map(x=>parseInt(x||0,10));
      const title = first.title || ('Поръчка #'+id);
      const status = first.status || DEFAULT_STATUS;
      const desc = first.description || "";

      const plate = (lane==='Неразпределени' || lane==='НЕАКТИВНИ:') ? '' : lane;

      const fresh = [];
      for(let i=0;i<daysCount;i++){
        const d = addDays(newStart, i);
        fresh.push({
          id: String(id),
          date: isoDate(d),
          startTime: hh(sh)+':'+hh(sm),
          endTime: hh(eh)+':'+hh(em),
          title,
          vehicle_plate: plate,
          status,
          description: desc
        });
      }
      flatReplaceAllById(id, fresh);
      persistRangeOnServer(String(id), isoDate(newStart), isoDate(newEnd), plate, status);
    };
  }
  return { allowDrop, onDragStart, onDragEnd, onDropToCell };
}

/* ===== status popup ===== */
const StatusMenu = {
  el: null, onPick: null,
  ensure(){
    if(this.el) return this.el;
    const div = document.createElement('div');
    div.className = "fixed z-50 bg-white border rounded-xl shadow p-1 text-sm";
    div.style.display = 'none';
    div.innerHTML = (["Планирана","В изпълнение","Завършена","Отменена","Фактурирана"]).map(s=>{
      return `<button data-status="${s}" class="w-full text-left px-3 py-1 rounded hover:bg-slate-100">${s}</button>`;
    }).join('');
    div.addEventListener('click', (e)=>{
      const btn = e.target.closest('button[data-status]');
      if(!btn) return;
      const st = btn.getAttribute('data-status');
      const cb = this.onPick;
      this.hide();
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
    el.style.top = y+'px';
    el.style.display = 'block';
    setTimeout(()=> document.addEventListener('mousedown', this._hideOnce = (ev)=>{ if(!el.contains(ev.target)) this.hide(); }, {once:true}), 0);
  },
  hide(){ if(this.el) this.el.style.display='none'; this.onPick=null; }
};

/* ===== UI pieces ===== */
function Toolbar({view, setView, anchor, setAnchor}){
  function goMonths(d){ const x=new Date(anchor); x.setMonth(x.getMonth()+d); setAnchor(x); }
  function goDays(d){ const x=new Date(anchor); x.setDate(x.getDate()+d); setAnchor(x); }
  return (
    <div className="flex flex-wrap items-center gap-2 bg-white border rounded-xl px-3 py-2">
      {view==='month' ? (
        <>
          <button className="px-3 py-1.5 rounded-xl border" onClick={()=>goMonths(-1)}>«</button>
          <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG', {month:'long', year:'numeric'})}</div>
          <button className="px-3 py-1.5 rounded-xl border" onClick={()=>goMonths(1)}>»</button>
        </>
      ) : (
        <>
          <button className="px-3 py-1.5 rounded-xl border" onClick={()=>goDays(view==='week'?-7:-1)}>{view==='week'?'« 7':'« 1'}</button>
          <div className="font-semibold text-sm">{anchor.toLocaleDateString('bg-BG')}</div>
          <button className="px-3 py-1.5 rounded-xl border" onClick={()=>goDays(view==='week'?7:1)}>{view==='week'?'7 »':'1 »'}</button>
        </>
      )}
      <div className="ml-2">
        <button className={"px-2 py-1 text-xs rounded "+(view==='day'?'bg-slate-900 text-white':'border')} onClick={()=>setView('day')}>Ден</button>
        <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='week'?'bg-slate-900 text-white':'border')} onClick={()=>setView('week')}>Седмица</button>
        <button className={"ml-1 px-2 py-1 text-xs rounded "+(view==='month'?'bg-slate-900 text-white':'border')} onClick={()=>setView('month')}>Месец</button>
      </div>
      <a href="/orders#new" className="ml-2 px-3 py-1.5 text-sm rounded-xl border">+ Нова поръчка</a>
    </div>
  );
}

function LaneRow({lane, days, byDayLane, onDropCell, allowDrop, dnd}){
  const rowRef = useRef(null);
  const [cellW, setCellW] = useState(60);
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
    measure(); window.addEventListener('resize', measure);
    return ()=> window.removeEventListener('resize', measure);
  }, []);

  const spansRaw = useMemo(()=>{
    const res = [];
    const keys = days.map(isoDate);
    const byId = new Map();
    keys.forEach((k, idx)=>{
      const list = (byDayLane.get(k)?.get(lane)) || [];
      list.forEach(o=>{
        const id = String(o.id);
        (byId.get(id) || byId.set(id, []).get(id)).push({ idx, o });
      });
    });
    byId.forEach(arr=>{
      arr.sort((a,b)=> a.idx-b.idx);
      let i=0;
      while(i<arr.length){
        const start=arr[i].idx; const meta=arr[i].o; let j=i+1, last=start;
        while(j<arr.length && arr[j].idx===last+1){ last=arr[j].idx; j++; }
        res.push({
          id: String(meta.id), startIdx:start, endIdx:last, len:last-start+1,
          title: meta.title || ('Поръчка #'+meta.id),
          startTime: meta.startTime || '08:00',
          endTime: meta.endTime || '10:00',
          description: meta.description || "",
          status: meta.status || DEFAULT_STATUS
        });
        i=j;
      }
    });
    return res;
  }, [days, lane, byDayLane]);

  const { spans, maxLevel } = useMemo(()=>{
    const sorted = [...spansRaw].sort((a,b)=> a.startIdx - b.startIdx || a.endIdx - b.endIdx);
    const ends=[]; sorted.forEach(sp=>{ let lvl=0; while(ends[lvl]!=null && ends[lvl] >= sp.startIdx) lvl++; ends[lvl]=sp.endIdx; sp._level=lvl; });
    return { spans: sorted, maxLevel: Math.max(0, ends.length-1) };
  }, [spansRaw]);

  const barH = 26, gap = 6, padTop = 8, padBottom = 8;
  const overlayHeight = padTop + (maxLevel+1)*barH + maxLevel*gap + padBottom;

  function openStatus(id, current, evt){
    const {clientX, clientY} = evt;
    StatusMenu.show(clientX, clientY, current, (picked)=>{
      flatSetStatus(id, picked);           // моментално
      persistStatus(id, picked);           // бекенд
    });
  }

  return (
    <div className="relative" style={{minHeight: overlayHeight+'px'}}>
      <div ref={rowRef} className="grid" style={{gridTemplateColumns:`repeat(${days.length}, minmax(0, 1fr))`}}>
        {days.map((d,i)=>(
          <div key={i} data-cell className="border-r border-b min-h-[72px] p-1.5"
               onDragOver={allowDrop} onDrop={onDropCell(d, lane)} />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-0">
        {spans.map(sp=>{
          const left = sp.startIdx*cellW + 4;
          const width = sp.len*cellW - 8;
          const top = padTop + sp._level*(barH+gap);
          const meta = STATUS_META[sp.status] || STATUS_META[DEFAULT_STATUS];
          return (
            <div key={sp.id+':'+sp.startIdx}
                 className={`pointer-events-auto absolute top-1 left-0 text-[11px] px-2 py-[5px] rounded border cursor-move truncate ${meta.bg} ${meta.border}`}
                 style={{left:left+'px', width:Math.max(36,width)+'px', top:top+'px', height:(barH-6)+'px'}}
                 draggable
                 onDragStart={(e)=>dnd.onDragStart(e, sp.id)}
                 onClick={(e)=> openStatus(sp.id, sp.status, e)}
                 title={`${sp.title} · ${sp.startTime}-${sp.endTime}${sp.description?(' — '+sp.description):''}`}>
              <span className="font-medium">{sp.title}</span>
              {sp.description ? <span className="opacity-80"> — {sp.description}</span> : null}
              <span className={`ml-2 inline-block align-middle text-[10px] px-1 py-[1px] rounded ${meta.pill}`}>{sp.status}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ===== Views ===== */
function MonthView({anchor, flat, lanes, dnd}){
  const total = daysInMonth(anchor);
  const days = useMemo(()=> Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1)), [anchor,total]);
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
              <div className={"h-full border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              <div className={ri%2 ? "bg-slate-50/50" : ""} style={{gridColumn:`span ${days.length}`}}>
                <LaneRow lane={lane} days={days} byDayLane={byDayLane}
                         onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                         allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                         dnd={dnd} />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
function WeekView({anchor, flat, lanes, dnd}){
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
              <div className={"h-full border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              <div className={ri%2 ? "bg-slate-50/50" : ""} style={{gridColumn:'span 7'}}>
                <LaneRow lane={lane} days={days} byDayLane={byDayLane}
                         onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                         allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                         dnd={dnd} />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
function DayView({anchor, flat, lanes, dnd}){
  const day = startOfDay(anchor);
  const by = useMemo(()=> buildByDayLane([day], lanes, flat), [anchor, lanes, flat]);
  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Ден – {day.toLocaleDateString('bg-BG')}</div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto minmax(0, 1fr)`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          <div className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">Поръчки</div>
          {lanes.map((lane,ri)=>(
            <React.Fragment key={lane}>
              <div className={"h-full border-r border-b px-2 py-2 text-xs font-medium "+(ri%2 ? "bg-slate-50" : "bg-white")}>{lane}</div>
              <div className={ri%2 ? "bg-slate-50/50" : ""}>
                <LaneRow lane={lane} days={[day]} byDayLane={by}
                         onDropCell={(d,l)=> dnd.onDropToCell(d,l)}
                         allowDrop={lane==='НЕАКТИВНИ:' ? undefined : dnd.allowDrop}
                         dnd={dnd} />
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ===== App ===== */
function App(){
  const [view, setView] = useState('month');
  const [anchor, setAnchor] = useState(new Date());
  const flat = useFlatOrders();
  const lanes = useLanes();
  const dnd = useDragAndDrop();

  return (
    <div className="space-y-4">
      <Toolbar view={view} setView={setView} anchor={anchor} setAnchor={setAnchor} />
      {view==='month' && <MonthView anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} />}
      {view==='week'  && <WeekView  anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} />}
      {view==='day'   && <DayView   anchor={anchor} flat={flat} lanes={lanes} dnd={dnd} />}
    </div>
  );
}

/* mount */
const root = ReactDOM.createRoot(document.getElementById('app'));
root.render(<App/>);
