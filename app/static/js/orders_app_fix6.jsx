// build: fix6 orders_app.jsx
console.log('orders_app.jsx loaded (fix6)');
// build: fix4

const { useState, useMemo } = React;
const { defaultOrder, listOrders, upsertOrder, deleteOrder, plannedGross, actualGross, OrderForm } = window.OrdersShared;
function useOrders(){ const [orders, setOrders]=useState(listOrders()); function refresh(){ setOrders(listOrders()); } return { orders, refresh, save:(o)=>{upsertOrder(o);refresh();}, remove:(id)=>{deleteOrder(id);refresh();} }; }
function GrossBadge({value}){ const cls=value>=0?"bg-emerald-100 text-emerald-700 border-emerald-200":"bg-rose-100 text-rose-700 border-rose-200"; return <span className={`px-2 py-0.5 rounded-md text-xs border ${cls}`}>{value.toFixed(2)} лв</span>; }
function OrdersPage(){
  const { orders, save, remove } = useOrders();
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState("");
  React.useEffect(()=>{ if(location.hash==="#new") setEditing(defaultOrder()); }, []);
  const filtered = useMemo(()=> orders.slice().sort((a,b)=>(a.date+a.startTime).localeCompare(b.date+b.startTime))
      .filter(o=>[o.origin,o.destination,o.description,o.bus_type,o.date].join(" ").toLowerCase().includes(filter.toLowerCase())), [orders, filter]);
  return (<div className="space-y-4">
    <div className="flex items-center justify-between">
      <h1 className="text-xl font-semibold">Поръчки</h1>
      <div className="flex items-center gap-2">
        <input className="border rounded-lg px-3 py-2" placeholder="Търсене..." value={filter} onChange={e=>setFilter(e.target.value)} />
        <button className="px-3 py-2 rounded-lg border" onClick={()=>setEditing(defaultOrder())}>Нова поръчка</button>
      </div>
    </div>
    <div className="bg-white border rounded-xl overflow-hidden">
      <div className="grid grid-cols-12 px-3 py-2 text-xs font-semibold bg-slate-50 border-b">
        <div className="col-span-2">Дата</div><div className="col-span-3">Маршрут</div><div className="col-span-2">Автобус / Хора</div><div className="col-span-2">Очаквани разходи</div><div className="col-span-1">Приход</div><div className="col-span-2 text-right">Марж (план)</div>
      </div>
      <div>{filtered.map(o=>{ const variable=Object.values(o.planned.costs).reduce((s,v)=>s+Number(v||0),0); const gross=plannedGross(o); const isPast=new Date(o.date) < new Date(new Date().toDateString());
        return (<div key={o.id} className={`grid grid-cols-12 px-3 py-2 border-t ${isPast?"opacity-60":""}`}>
          <div className="col-span-2">{o.date} · {o.startTime}–{o.endTime}</div><div className="col-span-3 truncate">{o.origin} → {o.destination}</div>
          <div className="col-span-2">{o.bus_type||"—"} · {o.pax_count||0}ч.</div><div className="col-span-2">{variable.toFixed(2)} лв</div><div className="col-span-1">{(o.price||0).toFixed(2)} лв</div>
          <div className="col-span-2 text-right flex items-center justify-end gap-2"><GrossBadge value={gross} /><button className="px-2 py-1 text-xs rounded-lg border" onClick={()=>setEditing(o)}>Отвори</button></div></div>); })}
        {filtered.length===0 && <div className="p-4 text-sm text-slate-500">Няма поръчки.</div>}</div>
    </div>
    {editing && (<div className="bg-white border rounded-xl p-4 space-y-6">
      <div className="flex items-center justify-between"><div className="text-base font-semibold">Поръчка · редакция / детайли</div>
        <div className="flex items-center gap-2"><button className="px-3 py-2 rounded-lg border" onClick={()=>{ remove(editing.id); setEditing(null); }}>Изтрий</button><button className="px-3 py-2 rounded-lg border" onClick={()=>setEditing(null)}>Затвори</button></div></div>
      <OrdersShared.OrderForm value={editing} onChange={setEditing} onSubmit={(o)=>{ save(o); setEditing(o); }} submitText="Запази" />
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white border rounded-xl p-4"><div className="text-sm font-semibold mb-2">План</div>
          <div className="text-sm text-slate-600">Приход: {(editing.price||0).toFixed(2)} лв</div>
          <div className="text-sm text-slate-600">Разходи (планирани): {Object.values(editing.planned.costs).reduce((s,v)=>s+Number(v||0),0).toFixed(2)} лв</div>
          <div className="mt-2">Марж: <span className="px-2 py-0.5 rounded-md text-xs border bg-sky-100 text-sky-700 border-sky-200">{OrdersShared.plannedGross(editing).toFixed(2)} лв</span></div></div>
        <div className="bg-white border rounded-xl p-4"><div className="text-sm font-semibold mb-2">Реално</div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-sm text-slate-600">Реален приход</label><input type="number" step="0.01" className="mt-1 w-full border rounded-lg px-3 py-2" value={editing.actual.revenue??editing.price??0} onChange={e=>setEditing(o=>({...o, actual:{...o.actual, revenue:Number(e.target.value||0)}}))}/></div>
            <div><label className="text-sm text-slate-600">Реално км (одометър)</label><input type="number" className="mt-1 w-full border rounded-lg px-3 py-2" value={editing.actual.km??""} onChange={e=>setEditing(o=>({...o, actual:{...o.actual, km:Number(e.target.value||0)}}))}/></div>
          </div>
          <div className="grid md:grid-cols-5 gap-3 mt-3">{["fuel","tolls","parking","wages","other"].map(k=>(
            <div key={k}><label className="text-sm text-slate-600">Разход {k.toUpperCase()}</label><input type="number" step="0.01" className="mt-1 w-full border rounded-lg px-3 py-2" value={editing.actual.costs[k]||0} onChange={e=>setEditing(o=>({...o, actual:{...o.actual, costs:{...o.actual.costs, [k]:Number(e.target.value||0)}}}))}/></div>
          ))}</div>
          <div className="mt-2">Марж (реално): <span className="px-2 py-0.5 rounded-md text-xs border bg-emerald-100 text-emerald-700 border-emerald-200">{OrdersShared.actualGross(editing).toFixed(2)} лв</span></div>
          <div className="text-xs text-slate-500 mt-1">Разлика: {(OrdersShared.actualGross(editing)-OrdersShared.plannedGross(editing)).toFixed(2)} лв</div>
        </div>
      </div>
    </div>)}
  </div>);}
const root = ReactDOM.createRoot(document.getElementById("orders-app")); root.render(<OrdersPage/>);
