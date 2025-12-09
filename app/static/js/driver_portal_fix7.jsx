// build: fix7
console.log('driver_portal_fix6_fix7.jsx loaded (fix7)');
// build: fix6 driver_portal.jsx
console.log('driver_portal.jsx loaded (fix6)');

const { useState } = React;
const { findByToken, upsertOrder, actualGross } = window.OrdersShared;
function Portal(){
  const [token,setToken]=useState(""); const [order,setOrder]=useState(null);
  function load(){ const o=findByToken(token.trim()); if(!o){alert("Невалиден токен");return;} setOrder(o); }
  function save(){ upsertOrder(order); alert("Записано"); }
  return (<div className="space-y-4">
    <h1 className="text-xl font-semibold">Портал за шофьори</h1>
    {!order && (<div className="bg-white border rounded-xl p-4 flex items-end gap-2">
      <div className="flex-1"><label className="text-sm text-slate-600">Токен</label><input className="mt-1 w-full border rounded-lg px-3 py-2" value={token} onChange={e=>setToken(e.target.value)} placeholder="drv_xxxxxx" /></div>
      <button className="px-3 py-2 rounded-lg border" onClick={load}>Отвори</button></div>)}
    {order && (<div className="bg-white border rounded-xl p-4 space-y-3">
      <div className="text-sm text-slate-600">Поръчка: {order.origin} → {order.destination} · {order.date} {order.startTime}-{order.endTime}</div>
      <div className="grid md:grid-cols-3 gap-3">
        <div><label className="text-sm text-slate-600">Реален приход</label><input type="number" step="0.01" className="mt-1 w-full border rounded-lg px-3 py-2" value={order.actual.revenue??order.price??0} onChange={e=>setOrder(o=>({...o, actual:{...o.actual, revenue:Number(e.target.value||0)}}))}/></div>
        <div><label className="text-sm text-slate-600">Км реално</label><input type="number" className="mt-1 w-full border rounded-lg px-3 py-2" value={order.actual.km??""} onChange={e=>setOrder(o=>({...o, actual:{...o.actual, km:Number(e.target.value||0)}}))}/></div>
        <div><label className="text-sm text-slate-600">Часове реално</label><input type="number" step="0.1" className="mt-1 w-full border rounded-lg px-3 py-2" value={order.actual.time_hours??""} onChange={e=>setOrder(o=>({...o, actual:{...o.actual, time_hours:Number(e.target.value||0)}}))}/></div>
      </div>
      <div className="grid md:grid-cols-5 gap-3">{["fuel","tolls","parking","wages","other"].map(k=>(
        <div key={k}><label className="text-sm text-slate-600">Разход {k.toUpperCase()}</label><input type="number" step="0.01" className="mt-1 w-full border rounded-lg px-3 py-2" value={order.actual.costs[k]||0} onChange={e=>setOrder(o=>({...o, actual:{...o.actual, costs:{...o.actual.costs, [k]:Number(e.target.value||0)}}}))}/></div>
      ))}</div>
      <div><label className="text-sm text-slate-600">Бележки</label><textarea rows="3" className="mt-1 w-full border rounded-lg px-3 py-2" value={order.actual.driver_notes||""} onChange={e=>setOrder(o=>({...o, actual:{...o.actual, driver_notes:e.target.value}}))}/></div>
      <div className="flex items-center justify-between">
        <div className="text-sm">Марж (реално): <span className="px-2 py-0.5 rounded-md text-xs border bg-emerald-100 text-emerald-700 border-emerald-200">{actualGross(order).toFixed(2)} лв</span></div>
        <div className="flex items-center gap-2"><button className="px-3 py-2 rounded-lg border" onClick={()=>setOrder(null)}>Затвори</button><button className="px-3 py-2 rounded-lg border" onClick={save}>Запази</button></div>
      </div>
    </div>)}
  </div>);}
const root = ReactDOM.createRoot(document.getElementById("driver-portal")); root.render(<Portal/>);
