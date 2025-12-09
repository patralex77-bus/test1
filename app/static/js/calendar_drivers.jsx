/* global React, ReactDOM */
console.log('calendar_drivers.jsx loaded (drivers calendar – 2-row bar; DST-safe; snap; resize-observed; vertical-only DnD)');

const { useState, useEffect, useMemo, useRef } = React;

/* ========== utils (LOCAL date; DST-safe calendar math) ========== */
const MS_DAY = 86400000;
const hh = (n)=> String(n).padStart(2,'0');

function dateFromISOLocal(iso){
  if(!iso || typeof iso !== 'string') return new Date(NaN);
  const [y,m,d] = iso.split('-').map(x=> parseInt(x,10));
  return new Date(y,(m||1)-1,(d||1),0,0,0,0);
}
function isoDate(d){ return `${d.getFullYear()}-${hh(d.getMonth()+1)}-${hh(d.getDate())}`; }
const startOfDay = (d)=> new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0,0,0,0);
const daysInMonth = (anchor)=> new Date(anchor.getFullYear(), anchor.getMonth()+1, 0).getDate();
const addDays = (date, delta)=> { const nd=new Date(date); nd.setDate(nd.getDate()+delta); return nd; };
const startOfWeekMonday = (d)=>{ const nd=new Date(d); const day=(nd.getDay()+6)%7; nd.setDate(nd.getDate()-day); nd.setHours(0,0,0,0); return nd; };

function calendarDiffDaysUTC(a, b){
  const au = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const bu = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.floor((bu - au) / MS_DAY);
}
function inclusiveDaysCount(startISO, endISO){
  const s = dateFromISOLocal(startISO);
  const e = dateFromISOLocal(endISO);
  return Math.max(1, calendarDiffDaysUTC(s, e) + 1);
}

const todayStr = isoDate(new Date());
const isFutureOrToday = (dateStr)=> calendarDiffDaysUTC(dateFromISOLocal(todayStr), dateFromISOLocal(dateStr)) >= 0;

/* ========== status meta ========== */
const STATUS_META = {
  "Планирана":    { bg:"bg-sky-50",    border:"border-sky-400",    pill:"bg-sky-100 text-sky-800" },
  "В изпълнение": { bg:"bg-amber-50",  border:"border-amber-400",  pill:"bg-amber-100 text-amber-800" },
  "Завършена":    { bg:"bg-emerald-50",border:"border-emerald-400",pill:"bg-emerald-100 text-emerald-800" },
  "Отменена":     { bg:"bg-rose-50",   border:"border-rose-400",   pill:"bg-rose-100 text-rose-800" },
  "Фактурирана":  { bg:"bg-indigo-50", border:"border-indigo-400", pill:"bg-indigo-100 text-indigo-800" },
};
const DEFAULT_STATUS = "Планирана";

/* ========== API (бекенд) ========== */
async function fetchSnapshot(from, to){
  const qs = `?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  const r = await fetch(`/calendar/api/snapshot${qs}`, { headers:{Accept:'application/json'}, cache:'no-store' }).catch(()=>null);
  if(r && r.ok){
    const j = await r.json();
    return {
      orders:  Array.isArray(j?.orders)? j.orders : [],
      drivers: Array.isArray(j?.drivers)? j.drivers : [],
    };
  }
  const r2 = await fetch(`/orders/api/list${qs}`, { headers:{Accept:'application/json'} }).catch(()=>null);
  const j2 = r2 ? await r2.json() : {};
  return { orders: Array.isArray(j2?.orders)?j2.orders:[], drivers: [] };
}
function persistStatus(id, status){
  return fetch('/orders/api/set_status', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id:String(id), status:String(status) })
  }).catch(()=>{});
}
function persistAssignDriver(id, driver_id){
  return fetch('/orders/api/assign_driver', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id:String(id), driver_id: driver_id==null? null : Number(driver_id) })
  }).catch(()=>{});
}
async function persistUnassignDriverViaDriverEndpoint(order_id, driver_id){
  try{ const r = await fetch(`/drivers/${encodeURIComponent(driver_id)}/unassign/${encodeURIComponent(order_id)}`, { method:'POST' }); return r.ok; }
  catch(_){ return false; }
}

/* ========== StatusMenu ========== */
const StatusMenu = {
  el:null, onPick:null,
  ensure(){
    if(this.el) return this.el;
    const div = document.createElement('div');
    div.className = "fixed z-50 bg-white border rounded-xl shadow p-1 text-sm";
    div.style.display = 'none';
    const opts = ["Планирана","В изпълнение","Завършена","Отменена","Фактурирана"];
    div.innerHTML = opts.map(s=> `<button data-status="${s}" class="w-full text-left px-3 py-1 rounded hover:bg-slate-100">${s}</button>`).join('');
    div.addEventListener('click', (e)=>{
      const btn = e.target.closest('button[data-status]'); if(!btn) return;
      const st = btn.getAttribute('data-status'); const cb = this.onPick; this.hide();
      if(typeof cb==='function') cb(st);
    });
    document.body.appendChild(div);
    this.el = div; return div;
  },
  show(x,y,current,onPick){
    const el = this.ensure(); this.onPick = onPick;
    el.querySelectorAll('button').forEach(b=>{
      const st = b.getAttribute('data-status');
      b.classList.toggle('bg-slate-100', st===current);
      b.classList.toggle('font-medium', st===current);
    });
    el.style.left = x+'px'; el.style.top = y+'px'; el.style.display = 'block';
    setTimeout(()=> document.addEventListener('mousedown', this._hideOnce=(ev)=>{ if(!el.contains(ev.target)) this.hide(); }, {once:true}), 0);
  },
  hide(){ if(this.el) this.el.style.display='none'; this.onPick=null; }
};

function normalizeDrivers(driversRaw, orders){
  const seen = new Set();
  const out = [];

  // 1) lane „Без шофьор“ винаги първи
  out.push({id: null, name: "— Без шофьор —"});
  seen.add("_none");

  // 2) реални шофьори
  (driversRaw||[]).forEach(d=>{
    const id = d?.id ?? null;
    if(id==null) return;
    const name = d?.name || ("Шофьор #"+id);
    const key = String(id);
    if(!seen.has(key)){ seen.add(key); out.push({id, name}); }
  });

  // 3) липсващи шофьори от поръчките
  (orders||[]).forEach(o=>{
    const id = o?.driver_id ?? null;
    if(id==null) return;
    const name = o?.driver_name || ("Шофьор #"+id);
    const key = String(id);
    if(!seen.has(key)){ seen.add(key); out.push({id, name}); }
  });

  // 4) сортиране само на реалните шофьори
  const head = out.shift();
  out.sort((a,b)=> String(a.name||"").localeCompare(String(b.name||""), "bg"));
  out.unshift(head);

  return out;
}

function normalizeInclusiveRange(o){
  const sISO = o.start_date || o.date;
  const eISO = o.end_date   || o.start_date || o.date;

  const s = dateFromISOLocal(sISO);
  const e = dateFromISOLocal(eISO);

  // ако датите са счупени – връщаме оригиналния обект
  if (isNaN(s) && isNaN(e)) return o;

  // ако край липсва или е преди старта → правим поръчката еднодневна
  if (isNaN(e) || e < s) {
    const only = isoDate(s);
    return { 
      ...o,
      start_date: only,
      end_date:   only,
    };
  }

  // нормален случай: приемаме, че бекендът дава включителен диапазон
  return {
    ...o,
    start_date: isoDate(s),
    end_date:   isoDate(e),
  };
}

function expandOrderDays(o){
  o = normalizeInclusiveRange(o);
  const list = [];
  const sISO = o.start_date || o.date;
  const eISO = o.end_date   || o.start_date || o.date;
  const s = dateFromISOLocal(sISO);
  const e = dateFromISOLocal(eISO);
  const days = Math.max(1, calendarDiffDaysUTC(s, e) + 1);
  for(let i=0;i<days;i++){
    const d = addDays(s, i);
    list.push({
      id: String(o.id),
      date: isoDate(d),
      title: o.title || ('Поръчка #'+o.id),
      description: o.description || "",
      status: o.status || DEFAULT_STATUS,
      startTime: o.startTime || '08:00',
      endTime:   o.endTime   || '10:00',
      driver_id: o.driver_id ?? null,
      driver_name: o.driver_name || "",
      vehicle_plate: o.bus_plate || o.vehicle_plate || ""
    });
  }
  return list;
}
function buildByDayLane(days, lanes, orders){
  const map = new Map(); const dayKeys = days.map(isoDate);
  dayKeys.forEach(k=>{ const laneMap = new Map(); lanes.forEach(l => laneMap.set(l.name, [])); map.set(k, laneMap); });

  (orders||[]).forEach(o=>{
    const expanded = expandOrderDays(o);
    expanded.forEach(rec=>{
      const k = rec.date; const lm = map.get(k); if(!lm) return;
      const laneName = (rec.driver_id==null)
        ? lanes.find(x=> x.id==null)?.name || "— Без шофьор —"
        : (lanes.find(x=> String(x.id)===String(rec.driver_id))?.name || (rec.driver_name || ("Шофьор #"+rec.driver_id)));
      if(!lm.has(laneName)) lm.set(laneName, []);
      lm.get(laneName).push(rec);
    });
  });
  return map;
}
function buildOrderIndex(orders){
  const idx = new Map();
  (orders||[]).forEach(o=>{
    const id = String(o.id);
    const cur = idx.get(id);
    const s = dateFromISOLocal(o.start_date || o.date);
    const e = dateFromISOLocal(o.end_date   || o.start_date || o.date);
    if(!cur){ idx.set(id, { sample:o, s, e }); }
    else { if(s < cur.s) cur.s = s; if(e > cur.e) cur.e = e; }
  });
  return idx;
}
function computeSpans(days, laneName, byDayLane){
  const spans = []; const dayKeys = days.map(isoDate); const byId = new Map();
  dayKeys.forEach((k, idx)=>{
    const list = (byDayLane.get(k)?.get(laneName)) || [];
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
      const plate = meta.vehicle_plate || '—';
      const line2 = (meta.description && meta.description.trim()) ? meta.description : (meta.title || '');
      spans.push({
        id: String(meta.id),
        startIdx, endIdx:last, len,
        title: meta.title, startTime: meta.startTime, endTime: meta.endTime,
        description: meta.description, status: meta.status || DEFAULT_STATUS,
        driver_id: meta.driver_id || null, driver_name: meta.driver_name || '',
        vehicle_plate: plate, line2
      });
      i=j;
    }
  });
  return spans;
}
function assignLevels(spans){
  const sorted = [...spans].sort((a,b)=> a.startIdx - b.startIdx || a.endIdx - b.endIdx);
  const ends=[]; sorted.forEach(sp=>{ let lvl=0; while(ends[lvl]!=null && ends[lvl] >= sp.startIdx) lvl++; ends[lvl] = sp.endIdx; sp._level = lvl; });
  return { spans: sorted, maxLevel: Math.max(0, ends.length-1) };
}

/* ========== Hook: наблюдение на ширината на клетката ========== */
function useObservedCellWidth(rowRef, deps){
  const [cellW, setCellW] = useState(60);

  useEffect(()=>{
    let raf = 0;
    const measure = ()=>{
      const row = rowRef.current;
      if(!row) return;
      const cell = row.querySelector('[data-cell]');
      if(cell){
        const w = cell.getBoundingClientRect().width;
        if(w>0 && Math.abs(w - cellW) > 0.5) setCellW(w);
      }
    };

    const burst = ()=>{
      cancelAnimationFrame(raf);
      let i=0;
      const tick=()=>{ measure(); if(++i<6) raf=requestAnimationFrame(tick); };
      raf=requestAnimationFrame(tick);
    };
    burst();

    let ro;
    if('ResizeObserver' in window){
      ro = new ResizeObserver(()=> burst());
      if(rowRef.current) ro.observe(rowRef.current);
    }

    const onTrans = ()=> burst();
    window.addEventListener('transitionend', onTrans, true);
    window.addEventListener('animationend', onTrans, true);

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(()=> burst()).catch(()=>{});
    }

    const onWinResize = ()=> burst();
    window.addEventListener('resize', onWinResize);

    return ()=>{
      cancelAnimationFrame(raf);
      if(ro){ try{ ro.disconnect(); }catch(_){ } }
      window.removeEventListener('transitionend', onTrans, true);
      window.removeEventListener('animationend', onTrans, true);
      window.removeEventListener('resize', onWinResize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return cellW;
}

/* ========== LaneRow ========== */
function LaneRow({lane, days, byDayLane, onDropCell, allowDrop, onPickStatus, setSelectedId}){
  const rowRef = useRef(null);

  const spansRaw = useMemo(()=> computeSpans(days, lane.name, byDayLane), [days, lane, byDayLane]);
  const { spans, maxLevel } = useMemo(()=> assignLevels(spansRaw), [spansRaw]);

  // по-високи барове за два реда
  const barH = 68, gap = 6, padTop = 8, padBottom = 8;
  const overlayHeight = padTop + (maxLevel+1)*barH + maxLevel*gap + padBottom;

  // наблюдавана ширина на клетката
  const cellW = useObservedCellWidth(rowRef, [overlayHeight, days.length]);

  function barClass(status, forceAlert){
    if(forceAlert) return `pointer-events-auto absolute top-0 left-0 text-[11px] px-2 py-[6px] rounded border cursor-move overflow-hidden bg-rose-50 border-rose-500`;
    const meta = STATUS_META[status] || STATUS_META[DEFAULT_STATUS];
    return `pointer-events-auto absolute top-0 left-0 text-[11px] px-2 py-[6px] rounded border cursor-move overflow-hidden ${meta.bg} ${meta.border}`;
  }
  function onBarClick(e, sp){
    setSelectedId && setSelectedId(String(sp.id));
    StatusMenu.show(e.clientX, e.clientY, sp.status, async (picked)=>{
      try{ await persistStatus(sp.id, picked); }catch(_){}
      onPickStatus && onPickStatus(sp.id, picked);
    });
  }

  return (
    <div className="relative" style={{minHeight: overlayHeight+'px'}}>
      {/* grid cells */}
      <div ref={rowRef} className="grid" style={{gridTemplateColumns:`repeat(${days.length}, minmax(0, 1fr))`}}>
        {days.map((d,i)=>(
          <div key={i}
               data-cell
               className="border-r border-b p-1.5"
               style={{minHeight: overlayHeight+'px'}}
               onDragOver={(e)=>{ e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect='move'; }}
               onDrop={(e)=> onDropCell(d, lane)(e)} />
        ))}
      </div>
      {/* overlay bars */}
      <div className="pointer-events-none absolute inset-0">
        {spans.map(sp=>{
          const left = sp.startIdx * cellW;          // snap към началото на клетката (визуално)
          const width = sp.len * cellW - 1;          // -1 за граници
          const top = padTop + sp._level*(barH + gap);
          const unassigned = !(sp.driver_id || sp.driver_name);

          return (
            <div key={sp.id + ':' + sp.startIdx}
                 className={barClass(sp.status, unassigned)}
                 style={{left:left+'px', width:Math.max(24,width)+'px', top:top+'px', height:(barH-6)+'px'}}
                 draggable
                 onDragStart={(e)=>{ e.dataTransfer.setData('text/plain', String(sp.id)); e.dataTransfer.dropEffect='move'; }}
                 onClick={(e)=> onBarClick(e, sp)}
                 title={`${sp.vehicle_plate || '—'} · ${sp.line2 || ''}`}>
              <div className="leading-tight font-semibold truncate">{sp.vehicle_plate || '—'}</div>
              <div className="text-[10px] leading-tight opacity-90 truncate">{sp.line2 || '—'}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ========== Views (Month/Week/Day) ========== */
function MonthView({anchor, orders, lanes, orderIndex, setSelectedId, onDropTo, onStatusChanged}){
  const total = daysInMonth(anchor);
  const days = useMemo(()=> Array.from({length: total}).map((_,i)=> new Date(anchor.getFullYear(), anchor.getMonth(), i+1)), [anchor,total]);
  const byDayLane = useMemo(()=> buildByDayLane(days, lanes, orders), [days, lanes, orders]);

  function onDropCell(_date, lane){
    return (e)=>{
      e.preventDefault(); e.stopPropagation();
      const id = e.dataTransfer.getData('text/plain');
      if(!id) return;
      // ВАЖНО: подаваме само lane – НЕ променяме дати
      onDropTo({ id, lane });
    };
  }

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold flex items-center justify-between">
        <div>Месец – {anchor.toLocaleDateString('bg-BG',{month:'long',year:'numeric'})}</div>
        <div className="text-xs text-slate-500">Клик за статус · DnD: сменя само шофьор (датите не се променят)</div>
      </div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto repeat(${days.length}, minmax(0, 1fr))`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(<div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.getDate()}</div>))}
          {lanes.map((lane)=>(
            <React.Fragment key={(lane.id==null?"_none":lane.id)+":"+lane.name}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium" style={{height:'100%'}}>{lane.name}</div>
              <div style={{gridColumn:`span ${days.length}`}}>
                <LaneRow
                  lane={lane} days={days} byDayLane={byDayLane}
                  onDropCell={onDropCell}
                  allowDrop={(e)=>{ e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect='move'; }}
                  onPickStatus={onStatusChanged}
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
function WeekView({anchor, orders, lanes, orderIndex, setSelectedId, onDropTo, onStatusChanged}){
  const start = startOfWeekMonday(anchor);
  const days = useMemo(()=> Array.from({length:7}).map((_,i)=> addDays(start,i)), [anchor]);
  const byDayLane = useMemo(()=> buildByDayLane(days, lanes, orders), [days, lanes, orders]);

  function onDropCell(_date, lane){
    return (e)=>{
      e.preventDefault(); e.stopPropagation();
      const id = e.dataTransfer.getData('text/plain');
      if(!id) return;
      onDropTo({ id, lane }); // само смяна на шофьор
    };
  }

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b text-sm font-semibold">Седмица</div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto repeat(7, minmax(0, 1fr))`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          {days.map((d,i)=>(<div key={i} className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">{d.toLocaleDateString('bg-BG',{weekday:'short', day:'2-digit'})}</div>))}
          {lanes.map((lane)=>(
            <React.Fragment key={(lane.id==null?"_none":lane.id)+":"+lane.name}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium">{lane.name}</div>
              <div style={{gridColumn:'span 7'}}>
                <LaneRow
                  lane={lane} days={days} byDayLane={byDayLane}
                  onDropCell={onDropCell}
                  allowDrop={(e)=>{ e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect='move'; }}
                  onPickStatus={onStatusChanged}
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
function DayView({anchor, orders, lanes, orderIndex, setSelectedId, onDropTo, onStatusChanged}){
  const day = startOfDay(anchor);
  const byDayLane = useMemo(()=> buildByDayLane([day], lanes, orders), [anchor, lanes, orders]);

  function onDropCell(_date, lane){
    return (e)=>{
      e.preventDefault(); e.stopPropagation();
      const id = e.dataTransfer.getData('text/plain');
      if(!id) return;
      onDropTo({ id, lane }); // само смяна на шофьор
    };
  }

  return (
    <div className="bg-white border rounded-xl overflow-hidden">
    <div className="px-3 py-2 border-b text-sm font-semibold">Ден – {day.toLocaleDateString('bg-BG')}</div>
      <div className="overflow-x-auto">
        <div className="grid w-full" style={{gridTemplateColumns:`auto minmax(0, 1fr)`}}>
          <div className="h-8 border-r border-b bg-slate-50"></div>
          <div className="h-8 border-b p-1.5 text-[10px] text-center font-semibold">Поръчки</div>
          {lanes.map((lane)=>(
            <React.Fragment key={(lane.id==null?"_none":lane.id)+":"+lane.name}>
              <div className="border-r border-b px-2 py-2 text-xs font-medium">{lane.name}</div>
              <div>
                <LaneRow
                  lane={lane} days={[day]} byDayLane={byDayLane}
                  onDropCell={onDropCell}
                  allowDrop={(e)=>{ e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect='move'; }}
                  onPickStatus={onStatusChanged}
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

/* ========== Info panel helper ========== */
function summarizeOrder(orders, id){
  const group = (orders||[]).filter(o=> String(o.id)===String(id)).sort((a,b)=>{
    const as = a.start_date||a.date||""; const bs = b.start_date||b.date||"";
    return as<bs ? -1 : 1;
  });
  if(!group.length) return null;
  const t = group[0];
  const startStr = group[0].start_date || group[0].date;
  const endStr   = group[group.length-1].end_date || group[group.length-1].date || group[group.length-1].start_date || startStr;

  return {
    id: String(id),
    title: t.title || ('Поръчка #'+id),
    plate: t.bus_plate || t.vehicle_plate || '',
    start_date: startStr,
    end_date: endStr,
    startTime: t.startTime || '08:00',
    endTime: t.endTime || '10:00',
    days: inclusiveDaysCount(startStr, endStr),
    description: t.description || '',
    status: t.status || DEFAULT_STATUS,
    driver_id: t.driver_id || null,
    driver_name: t.driver_name || ''
  };
}

/* ========== App ========== */
function App(){
  const [view, setView] = useState('month');
  const [anchor, setAnchor] = useState(new Date());
  const [orders, setOrders] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(false);

  const [selectedId, setSelectedId] = useState(null);
  const summary = useMemo(()=> selectedId ? summarizeOrder(orders, selectedId) : null, [orders, selectedId]);

  const from = isoDate(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
  const to   = isoDate(new Date(anchor.getFullYear(), anchor.getMonth()+1, 0));

  const reload = React.useCallback(async ()=>{
    setLoading(true);
    const { orders, drivers } = await fetchSnapshot(from, to);
    setOrders(orders||[]);
    setDrivers(normalizeDrivers(drivers, orders));
    setLoading(false);
  }, [from,to]);

  useEffect(()=>{ reload(); }, [reload]);

  // SSE sync (ако има)
  useEffect(()=>{
    let es;
    try{
      es = new EventSource("/calendar/events/orders");
      es.onmessage = ()=> reload();
      es.onerror = ()=>{/* ignore */};
    }catch(_){}
    return ()=>{ if(es) es.close(); };
  }, [reload]);

  const lanes = drivers;
  const orderIndex = useMemo(()=> buildOrderIndex(orders), [orders]);

  // ВАЖНО: вертикално-only преместване → сменяме само шофьор
  async function onDropTo({ id, lane }){
    try{ await persistAssignDriver(String(id), lane?.id==null ? null : Number(lane.id)); }catch(_){}
    setSelectedId(String(id));
    reload();
  }

  function onStatusChanged(){ reload(); }

  async function handleUnassign(){
    const s = summary; if(!s) return;
    if(!(s.driver_id || s.driver_name)) return;
    if(!isFutureOrToday(s.start_date)){ alert("Поръчката е в минал период и не може да бъде свалена от шофьор."); return; }
    let ok = false;
    if(s.driver_id){ ok = await persistUnassignDriverViaDriverEndpoint(s.id, s.driver_id); }
    if(!ok){ try{ await persistAssignDriver(s.id, null); ok = true; }catch(_){ } }
    if(ok){ setSelectedId(null); reload(); } else { alert("Неуспешно сваляне от шофьор."); }
  }

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
      </div>

      {/* Views */}
      {view==='month' && <MonthView anchor={anchor} orders={orders} lanes={lanes} orderIndex={orderIndex} setSelectedId={setSelectedId} onDropTo={onDropTo} onStatusChanged={onStatusChanged} />}
      {view==='week'  && <WeekView  anchor={anchor} orders={orders} lanes={lanes} orderIndex={orderIndex} setSelectedId={setSelectedId} onDropTo={onDropTo} onStatusChanged={onStatusChanged} />}
      {view==='day'   && <DayView   anchor={anchor} orders={orders} lanes={lanes} orderIndex={orderIndex} setSelectedId={setSelectedId} onDropTo={onDropTo} onStatusChanged={onStatusChanged} />}

      {/* Info panel */}
      <div className="bg-white border rounded-xl p-4">
        <div className="text-sm font-semibold mb-2">Информация за поръчка</div>
        {summary ? (
          <div className="space-y-2 text-sm">
            <div className="font-medium">{summary.title}</div>
            <div className="text-slate-600">
              Диапазон: {summary.start_date} → {summary.end_date} ({summary.days} дни) · Часове: {summary.startTime}–{summary.endTime}
            </div>
            <div className="text-slate-600">Автобус: {summary.plate || '—'}</div>
            <div className="text-slate-600">
              Статус:{' '}
              <span className={(STATUS_META[summary.status]||STATUS_META[DEFAULT_STATUS]).pill + " px-2 py-0.5 rounded"}>
                {summary.status}
              </span>
            </div>
            <div className="text-slate-600">
              Зачислена към шофьор:{' '}
              {(summary.driver_id || summary.driver_name)
                ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300">
                    Да — {summary.driver_name || ('#'+summary.driver_id)}
                  </span>
                : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-300">Не (без шофьор)</span>}
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <a href={`/orders/entry?edit=${encodeURIComponent(selectedId)}`} className="px-3 py-1.5 text-xs rounded-lg border">Отвори в „Поръчки“</a>
              {(summary.driver_id || summary.driver_name) && isFutureOrToday(summary.start_date) && (
                <button
                  className="px-3 py-1.5 text-xs rounded-lg border bg-rose-50 hover:bg-rose-100 text-rose-800"
                  onClick={handleUnassign}
                  title="Свали поръчката от текущия шофьор">
                  Свали от шофьор
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-500">Избери поръчка от календара.</div>
        )}
      </div>
    </div>
  );
}

/* mount */
ReactDOM.createRoot(document.getElementById('app')).render(<App/>);
