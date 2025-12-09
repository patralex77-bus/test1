// build: fix13b
console.log('orders_app_fix13b.jsx loaded');
const { useState, useEffect, useMemo } = React;

/* ===== Store bridge with safe fallback (localStorage) ===== */
(function ensureFallbackStore(){
  if (window.OrdersShared) return;
  const KEY = 'orders_fallback_store_v1';
  function read(){ try{ return JSON.parse(localStorage.getItem(KEY)||'[]'); }catch{ return []; } }
  function write(arr){ try{ localStorage.setItem(KEY, JSON.stringify(arr)); }catch{} }
  function nextId(arr){ return String((arr.reduce((m,o)=>Math.max(m, Number(o.id||0)), 0) || 0) + 1); }
  window.OrdersShared = {
    listOrders(){ return read(); },
    createOrder(data){
      const arr = read();
      const id = nextId(arr);
      const rec = {...data, id};
      arr.push(rec); write(arr); return id;
    },
    patchOrder(id, patch){
      const arr = read();
      const i = arr.findIndex(o=>String(o.id)===String(id));
      if(i>=0){ arr[i] = {...arr[i], ...patch}; write(arr); }
    },
    updateOrder(id, data){
      const arr = read();
      const i = arr.findIndex(o=>String(o.id)===String(id));
      if(i>=0){ arr[i] = {...data, id:String(id)}; write(arr); }
    }
  };
})();

const OS = (window && window.ordersSharedOverride) ? window.ordersSharedOverride : window.OrdersShared;

function sumVals(obj){ try{ return Object.values(obj||{}).reduce((s,v)=> s + Number(v||0), 0); }catch{ return 0; } }
function fmtMoney(n){ return (Number(n||0)).toFixed(2) + " лв"; }

function useOrders(){
  const [orders, setOrders] = useState(OS ? OS.listOrders() : []);
  useEffect(()=>{
    const h = ()=> setOrders(OS ? OS.listOrders() : []);
    window.addEventListener("orders:changed", h);
    return ()=> window.removeEventListener("orders:changed", h);
  }, []);
  return [orders, ()=> window.dispatchEvent(new CustomEvent("orders:changed"))];
}

function useBuses(){
  const [buses, setBuses] = useState([]);
  useEffect(()=>{
    fetch('/buses/api/list').then(r=>r.json()).then(j=>{
      const bs = Array.from(new Set([...(j.active||[]), ...(j.inactive||[])])).filter(x=>x && String(x).trim().length>0);
      setBuses(bs);
    }).catch(()=> setBuses([]));
  }, []);
  return buses;
}

/* ===== Left: Order Form ===== */
function emptyOrder(){
  return {
    id: null,
    date: "",
    startTime: "08:00",
    endTime: "10:00",
    origin: "",
    destination: "",
    vehicle_plate: "",
    pax_count: 0,
    bus_type: "",
    feeder_required: false,
    client_needs: "",
    description: "",
    price: 0,
    planned: { costs: { fuel: 0, tolls: 0, parking: 0, wages: 0, other: 0 } },
    actual: { revenue: null, costs: {} },
  };
}

function DeepClone(x){ return JSON.parse(JSON.stringify(x)); }

function OrderForm({value, onChange, onSaved, buses}){
  const v = value || emptyOrder();
  function set(path, val){
    const next = DeepClone(v);
    const parts = path.split(".");
    let cur = next;
    for(let i=0;i<parts.length-1;i++){ const k=parts[i]; cur[k] = cur[k] ?? {}; cur = cur[k]; }
    cur[parts[parts.length-1]] = val;
    onChange(next);
  }
  function save(){
    if(!OS){ alert("Orders store не е наличен."); return; }
    const data = DeepClone(v);
    if(!data.id){
      const id = OS.createOrder ? OS.createOrder(data) : null;
      if(id!=null) data.id = String(id);
    }else{
      if(OS.patchOrder) OS.patchOrder(String(data.id), data);
      else if(OS.updateOrder) OS.updateOrder(String(data.id), data);
    }
    window.dispatchEvent(new CustomEvent("orders:changed"));
    onSaved && onSaved(data);
  }
  function reset(){ onChange(emptyOrder()); }
  const plannedCosts = sumVals(v.planned?.costs);

  return (
    <div className="bg-white border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold">{v.id ? "Редакция на поръчка #"+v.id : "Нова поръчка"}</div>
        <div className="text-xs text-slate-500">Очаквани разходи: <b>{fmtMoney(plannedCosts)}</b></div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500">Дата</label>
          <input type="date" className="w-full border rounded-lg px-2 py-1.5" value={v.date} onChange={e=>set("date", e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-slate-500">Начало</label>
            <input type="time" className="w-full border rounded-lg px-2 py-1.5" value={v.startTime} onChange={e=>set("startTime", e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-slate-500">Край</label>
            <input type="time" className="w-full border rounded-lg px-2 py-1.5" value={v.endTime} onChange={e=>set("endTime", e.target.value)} />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-500">От</label>
          <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={v.origin} onChange={e=>set("origin", e.target.value)} placeholder="София" />
        </div>
        <div>
          <label className="text-xs text-slate-500">До</label>
          <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={v.destination} onChange={e=>set("destination", e.target.value)} placeholder="Пловдив" />
        </div>

        <div>
          <label className="text-xs text-slate-500">Автобус</label>
          {buses.length ? (
            <select className="w-full border rounded-lg px-2 py-1.5" value={v.vehicle_plate||""} onChange={e=>set("vehicle_plate", e.target.value)}>
              <option value="">—</option>
              {buses.map(b=><option key={b} value={b}>{b}</option>)}
            </select>
          ) : (
            <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={v.vehicle_plate} onChange={e=>set("vehicle_plate", e.target.value)} placeholder="W3201MW" />
          )}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-slate-500">Пътници</label>
            <input type="number" className="w-full border rounded-lg px-2 py-1.5" value={v.pax_count||0} onChange={e=>set("pax_count", Number(e.target.value||0))} />
          </div>
          <div>
            <label className="text-xs text-slate-500">Вид автобус</label>
            <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={v.bus_type||""} onChange={e=>set("bus_type", e.target.value)} placeholder="55+1, двуетажен..." />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-500">Приход (оферта)</label>
          <input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.price||0} onChange={e=>set("price", Number(e.target.value||0))} />
        </div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="feeder" className="border rounded" checked={!!v.feeder_required} onChange={e=>set("feeder_required", e.target.checked)} />
          <label htmlFor="feeder" className="text-xs text-slate-600">Нужен ли е довоз?</label>
        </div>

        <div className="col-span-2">
          <label className="text-xs text-slate-500">Очаквани разходи</label>
          <div className="grid grid-cols-5 gap-2">
            <div><input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.planned?.costs?.fuel||0} onChange={e=>set("planned.costs.fuel", Number(e.target.value||0))} placeholder="Гориво" /><div className="text-[11px] text-slate-500 mt-1">Гориво</div></div>
            <div><input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.planned?.costs?.tolls||0} onChange={e=>set("planned.costs.tolls", Number(e.target.value||0))} placeholder="Такси" /><div className="text-[11px] text-slate-500 mt-1">Такси</div></div>
            <div><input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.planned?.costs?.parking||0} onChange={e=>set("planned.costs.parking", Number(e.target.value||0))} placeholder="Паркинг" /><div className="text-[11px] text-slate-500 mt-1">Паркинг</div></div>
            <div><input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.planned?.costs?.wages||0} onChange={e=>set("planned.costs.wages", Number(e.target.value||0))} placeholder="Заплати" /><div className="text-[11px] text-slate-500 mt-1">Заплати</div></div>
            <div><input type="number" step="0.01" className="w-full border rounded-lg px-2 py-1.5" value={v.planned?.costs?.other||0} onChange={e=>set("planned.costs.other", Number(e.target.value||0))} placeholder="Други" /><div className="text-[11px] text-slate-500 mt-1">Други</div></div>
          </div>
        </div>

        <div className="col-span-2">
          <label className="text-xs text-slate-500">Специфични потребности</label>
          <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={v.client_needs||""} onChange={e=>set("client_needs", e.target.value)} placeholder="Изисквания на клиента" />
        </div>
        <div className="col-span-2">
          <label className="text-xs text-slate-500">Описание</label>
          <textarea className="w-full border rounded-lg px-2 py-1.5 h-24" value={v.description||""} onChange={e=>set("description", e.target.value)} placeholder="Бележки"></textarea>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-4">
        <button className="px-3 py-1.5 rounded-lg border bg-slate-900 text-white" onClick={save}>{v.id ? "Запиши" : "Създай"}</button>
        <button className="px-3 py-1.5 rounded-lg border" onClick={reset}>Нова</button>
      </div>
    </div>
  );
}

/* ===== Right: List + Filters ===== */
function ListFilters({qDate, setQDate, qText, setQText}){
  return (
    <div className="bg-white border rounded-xl p-3 mb-3">
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-slate-500">Дата</label>
          <input type="date" className="w-full border rounded-lg px-2 py-1.5" value={qDate} onChange={e=>setQDate(e.target.value)} />
        </div>
        <div className="col-span-2">
          <label className="text-xs text-slate-500">Търсене</label>
          <input type="text" className="w-full border rounded-lg px-2 py-1.5" value={qText} onChange={e=>setQText(e.target.value)} placeholder="дума от маршрут/описание/автобус" />
        </div>
      </div>
    </div>
  );
}

function OrdersList({orders, onPick, selectedId}){
  return (
    <div className="bg-white border rounded-xl">
      <div className="px-3 py-2 border-b text-sm font-semibold">Поръчки</div>
      <div className="max-h-[70vh] overflow-auto divide-y">
        {orders.length===0 ? (
          <div className="p-3 text-sm text-slate-500">Няма поръчки.</div>
        ) : orders.map(o=>{
          const exp = sumVals(o.planned?.costs);
          return (
            <div key={o.id} className={"p-3 text-sm cursor-pointer hover:bg-slate-50 "+(String(selectedId)===String(o.id)?"bg-amber-50":"")} onClick={()=>onPick(o)}>
              <div className="flex items-center justify-between">
                <div className="font-medium">{o.date || "—"}</div>
                <div className="text-xs text-slate-500">{o.vehicle_plate || "Неразпределени"}</div>
              </div>
              <div className="text-slate-700">{(o.origin||"—")+" → "+(o.destination||"—")}</div>
              <div className="text-xs text-slate-500 mt-1">Очаквани разходи: <b>{fmtMoney(exp)}</b> · Приход: <b>{fmtMoney(o.price)}</b></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ===== Root App ===== */
function App(){
  const buses = useBuses();
  const [orders, notifyChanged] = useOrders();
  const [selected, setSelected] = useState(null);

  const [qDate, setQDate] = useState("");
  const [qText, setQText] = useState("");

  const filtered = useMemo(()=>{
    const txt = (qText||"").trim().toLowerCase();
    const res = [...orders].filter(o=>{
      if(qDate && (o.date||"") !== qDate) return false;
      if(txt){
        const hay = [o.origin, o.destination, o.description, o.vehicle_plate, o.bus_type].join(" ").toLowerCase();
        if(!hay.includes(txt)) return false;
      }
      return true;
    }).sort((a,b)=> String(a.date||"").localeCompare(String(b.date||"")));
    return res;
  }, [orders, qDate, qText]);

  function pick(o){ setSelected(o ? JSON.parse(JSON.stringify(o)) : null); }
  function onSaved(updated){ setSelected(updated); }

  // keep selection fresh if store changes externally
  useEffect(()=>{
    if(!selected || !selected.id) return;
    const fresh = orders.find(o=> String(o.id)===String(selected.id));
    if(fresh) setSelected(JSON.parse(JSON.stringify(fresh)));
  }, [orders]);

  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 lg:col-span-6">
        <OrderForm value={selected || emptyOrder()} onChange={setSelected} onSaved={onSaved} buses={buses} />
      </div>
      <div className="col-span-12 lg:col-span-6">
        <ListFilters qDate={qDate} setQDate={setQDate} qText={qText} setQText={setQText} />
        <OrdersList orders={filtered} selectedId={selected?.id} onPick={pick} />
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("orders_app"));
root.render(<App/>);