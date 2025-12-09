// orders_cabinet.js — MVP панел за „Кабинет“ към поръчка
console.log('orders_cabinet.js loaded');

(function(){
  // --- helpers ---
  const qs  = (s,p=document)=> p.querySelector(s);
  const qsa = (s,p=document)=> Array.from(p.querySelectorAll(s));
  const el  = (tag, cls, html)=> { const d=document.createElement(tag); if(cls) d.className=cls; if(html!=null) d.innerHTML=html; return d; };
  const fmtDate = (s)=> (s||'').slice(0,10);

  const panel   = qs('#cabinet-panel');
  const body    = qs('#cabinet-body');
  const titleEl = qs('#cabinet-title');
  const backdrop= qs('#cabinet-backdrop');
  const closeBtn= qs('#cabinet-close');

  let currentOrderId = null;
  let currentOrder = null; // snapshot

  function openPanel(){
    panel.classList.remove('translate-x-full');
    backdrop.classList.remove('pointer-events-none');
    requestAnimationFrame(()=>{
      backdrop.classList.add('opacity-100');
    });
  }
  function closePanel(){
    panel.classList.add('translate-x-full');
    backdrop.classList.add('pointer-events-none');
    backdrop.classList.remove('opacity-100');
    currentOrderId = null;
    currentOrder   = null;
  }
  closeBtn.addEventListener('click', closePanel);
  backdrop.addEventListener('click', closePanel);

  // --- fetch helpers ---
  async function getOrderSnapshot(id){
    const r = await fetch(`/orders/api/cabinet/snapshot?id=${encodeURIComponent(id)}`, {cache:'no-store'});
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'snapshot failed');
    return j.snapshot;
  }
  async function getDrivers(){
    const r = await fetch('/drivers/api/list', {cache:'no-store'});
    const j = await r.json();
    return (j.drivers||[]).map(d=>({id:d.id, name:`${(d.last_name||'').trim()} ${(d.first_name||'').trim()}`.trim()}));
  }
  async function assignDriver(orderId, driverId){
    const r = await fetch('/orders/api/assign_driver', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ id: orderId, driver_id: driverId })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'assign failed');
    return j;
  }
  async function uploadFile(orderId, file){
    const fd = new FormData();
    fd.append('order_id', String(orderId));
    fd.append('file', file);
    const r = await fetch('/orders/api/files/upload', { method:'POST', body: fd });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'upload failed');
    return j;
  }
  async function deleteFile(orderId, filename){
    const r = await fetch('/orders/api/files/delete', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ order_id: orderId, filename })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'delete failed');
    return j;
  }
  async function addTask(orderId, text){
    const r = await fetch('/orders/api/tasks/add', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ order_id: orderId, text })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'task add failed');
    return j;
  }
  async function toggleTask(orderId, task_id){
    const r = await fetch('/orders/api/tasks/toggle', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ order_id: orderId, task_id })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'task toggle failed');
    return j;
  }
  async function addMessage(orderId, text){
    const r = await fetch('/orders/api/messages/add', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ order_id: orderId, text })
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'message add failed');
    return j;
  }

  // --- UI builders ---
  function renderHeader(snapshot){
    const warnNoDriver = !snapshot.driver || !snapshot.driver.id;
    titleEl.textContent = `Кабинет · ${snapshot.title || ('Поръчка #'+snapshot.id)}`;
    // тон на панела ако няма шофьор
    panel.classList.toggle('ring-2', warnNoDriver);
    panel.classList.toggle('ring-rose-400', warnNoDriver);
  }

  function renderSummary(snapshot){
    const box = el('div','space-y-1');
    const driverName = snapshot.driver?.name || '—';
    const driverId   = snapshot.driver?.id || null;
    const assignedBadge = driverId ? `<span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700">Зачислена</span>`
                                   : `<span class="ml-1 text-xs px-2 py-0.5 rounded-full bg-rose-50 border border-rose-200 text-rose-700">Без шофьор</span>`;

    box.innerHTML = `
      <div class="font-medium">${snapshot.title || ('Поръчка #'+snapshot.id)}</div>
      <div class="text-slate-600">Диапазон: ${fmtDate(snapshot.start_date)} → ${fmtDate(snapshot.end_date)} (${snapshot.days||1} дни)</div>
      <div class="text-slate-600">Часове: ${(snapshot.start_time||'—')} – ${(snapshot.end_time||'—')}</div>
      <div class="text-slate-600">Автобус: ${snapshot.vehicle_plate || '—'}</div>
      <div class="text-slate-600">Статус: <span class="px-2 py-0.5 rounded text-xs bg-slate-100">${snapshot.status||'—'}</span></div>
      <div class="text-slate-600 flex items-center gap-1">
        Зачислена към шофьор: <strong>${driverName}</strong> ${assignedBadge}
      </div>
      <div class="pt-2">
        <a href="/orders/list" class="px-3 py-1.5 text-xs rounded-lg border hover:bg-slate-50">Отвори в „Поръчки“</a>
      </div>
    `;
    return box;
  }

  async function renderAssign(snapshot){
    const wrap = el('div','mt-3 p-3 rounded-xl border bg-slate-50');
    wrap.innerHTML = `
      <div class="font-semibold text-sm mb-2">Зачисляване към шофьор</div>
      <div class="flex gap-2 items-center">
        <select class="border rounded-lg px-2 py-1 text-sm flex-1" id="cabinet-driver-select"><option>Зареждане…</option></select>
        <button class="px-3 py-1.5 rounded-lg border hover:bg-slate-100 text-sm" id="cabinet-assign-btn">Зачисли</button>
      </div>
      <div class="text-xs text-slate-500 mt-1">Листата идва от /drivers/api/list</div>
    `;

    // зареди шофьори
    const sel = qs('#cabinet-driver-select', wrap);
    const btn = qs('#cabinet-assign-btn', wrap);
    try{
      const list = await getDrivers();
      sel.innerHTML = '';
      sel.appendChild(el('option','', '— Избери шофьор —'));
      list.forEach(d=>{
        const opt = el('option','', `${d.name} (#${d.id})`);
        opt.value = d.id;
        if(snapshot.driver?.id && String(snapshot.driver.id)===String(d.id)){
          opt.selected = true;
        }
        sel.appendChild(opt);
      });
    }catch(e){
      sel.innerHTML = '<option>Грешка при зареждане</option>';
    }

    btn.addEventListener('click', async ()=>{
      const val = sel.value;
      if(!val || val==='— Избери шофьор —'){ alert('Изберете шофьор.'); return; }
      try{
        btn.disabled = true; btn.textContent = 'Запис...';
        await assignDriver(snapshot.id, parseInt(val,10));
        // презареди snapshot и панела
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder = fresh;
        paintPanel(fresh);
        // синхронизация с таблицата: отбележи реда „сигнално“ ако няма шофьор
        annotateRowDriverState(snapshot.id, !!fresh.driver?.id);
      }catch(err){
        alert('Неуспешно зачисляване: '+err.message);
      }finally{
        btn.disabled=false; btn.textContent='Зачисли';
      }
    });

    return wrap;
  }

  function renderFiles(snapshot){
    const wrap = el('div','mt-4');
    wrap.innerHTML = `
      <div class="font-semibold text-sm mb-2">Файлове</div>
      <div class="flex items-center gap-2">
        <input type="file" id="cabinet-file-input" class="text-sm">
        <button class="px-3 py-1.5 rounded-lg border hover:bg-slate-100 text-sm" id="cabinet-upload-btn">Качи</button>
      </div>
      <div class="mt-2" id="cabinet-file-list">
        ${(snapshot.files||[]).length ? '' : '<div class="text-slate-500 text-sm">Няма качени файлове.</div>'}
      </div>
    `;

    const listEl = qs('#cabinet-file-list', wrap);
    function renderList(){
      listEl.innerHTML = '';
      (snapshot.files||[]).forEach(f=>{
        const row = el('div','flex items-center justify-between border rounded-lg px-2 py-1 mb-1');
        row.innerHTML = `
          <a class="text-sm underline" href="/orders/api/files/download?order_id=${encodeURIComponent(snapshot.id)}&filename=${encodeURIComponent(f.name)}" target="_blank">${f.name}</a>
          <div class="text-xs text-slate-500">${f.size_human||''}</div>
          <button class="px-2 py-0.5 rounded border text-xs hover:bg-red-50 text-red-700" data-del="${f.name}">Изтрий</button>
        `;
        listEl.appendChild(row);
      });
    }
    renderList();

    const inp = qs('#cabinet-file-input', wrap);
    const btn = qs('#cabinet-upload-btn', wrap);
    btn.addEventListener('click', async ()=>{
      if(!inp.files || !inp.files[0]){ alert('Изберете файл.'); return; }
      try{
        btn.disabled=true; btn.textContent='Качване…';
        await uploadFile(snapshot.id, inp.files[0]);
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder = fresh;
        paintPanel(fresh);
      }catch(e){
        alert('Качването се провали: '+e.message);
      }finally{
        btn.disabled=false; btn.textContent='Качи'; inp.value='';
      }
    });

    listEl.addEventListener('click', async (e)=>{
      const b = e.target.closest('button[data-del]');
      if(!b) return;
      if(!confirm('Да изтрием ли файла?')) return;
      try{
        await deleteFile(snapshot.id, b.getAttribute('data-del'));
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder = fresh;
        paintPanel(fresh);
      }catch(err){
        alert('Грешка при изтриване: '+err.message);
      }
    });

    return wrap;
  }

  function renderTasks(snapshot){
    const wrap = el('div','mt-4');
    wrap.innerHTML = `
      <div class="font-semibold text-sm mb-2">Задачи</div>
      <div class="flex items-center gap-2 mb-2">
        <input type="text" id="cabinet-task-text" class="border rounded-lg px-2 py-1 text-sm flex-1" placeholder="Нова задача…">
        <button class="px-3 py-1.5 rounded-lg border hover:bg-slate-100 text-sm" id="cabinet-task-add">Добави</button>
      </div>
      <ul id="cabinet-task-list" class="space-y-1"></ul>
    `;
    const list = qs('#cabinet-task-list', wrap);

    function paintList(){
      list.innerHTML='';
      (snapshot.tasks||[]).forEach(t=>{
        const li = el('li','flex items-center justify-between border rounded-lg px-2 py-1');
        li.innerHTML = `
          <label class="flex items-center gap-2">
            <input type="checkbox" ${t.done?'checked':''} data-task="${t.id}">
            <span class="${t.done?'line-through text-slate-400':''}">${t.text}</span>
          </label>
          <span class="text-xs text-slate-500">${t.created_at||''}</span>
        `;
        list.appendChild(li);
      });
    }
    paintList();

    list.addEventListener('change', async (e)=>{
      const cb = e.target.closest('input[type="checkbox"][data-task]');
      if(!cb) return;
      try{
        await toggleTask(snapshot.id, cb.getAttribute('data-task'));
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder = fresh; paintPanel(fresh);
      }catch(err){
        alert('Неуспешна промяна на задача: '+err.message);
      }
    });

    const addBtn = qs('#cabinet-task-add', wrap);
    const txt = qs('#cabinet-task-text', wrap);
    addBtn.addEventListener('click', async ()=>{
      const val = (txt.value||'').trim();
      if(!val) return;
      try{
        addBtn.disabled=true; await addTask(snapshot.id, val);
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder=fresh; paintPanel(fresh);
      }catch(err){
        alert('Неуспешно добавяне: '+err.message);
      }finally{
        addBtn.disabled=false; txt.value='';
      }
    });
    return wrap;
  }

  function renderMessages(snapshot){
    const wrap = el('div','mt-4');
    wrap.innerHTML = `
      <div class="font-semibold text-sm mb-2">Съобщения (лог)</div>
      <div class="flex items-center gap-2 mb-2">
        <input type="text" id="cabinet-msg-text" class="border rounded-lg px-2 py-1 text-sm flex-1" placeholder="Съобщение…">
        <button class="px-3 py-1.5 rounded-lg border hover:bg-slate-100 text-sm" id="cabinet-msg-send">Изпрати</button>
      </div>
      <div class="space-y-2" id="cabinet-msg-list"></div>
    `;
    const list = qs('#cabinet-msg-list', wrap);

    function paintList(){
      list.innerHTML='';
      (snapshot.messages||[]).slice().reverse().forEach(m=>{
        const row = el('div','border rounded-lg px-3 py-2');
        row.innerHTML = `
          <div class="text-xs text-slate-500">${m.when||''} · ${m.author||''}</div>
          <div class="mt-1">${m.text||''}</div>
        `;
        list.appendChild(row);
      });
    }
    paintList();

    const sendBtn = qs('#cabinet-msg-send', wrap);
    const txt = qs('#cabinet-msg-text', wrap);
    sendBtn.addEventListener('click', async ()=>{
      const val = (txt.value||'').trim();
      if(!val) return;
      try{
        sendBtn.disabled=true; await addMessage(snapshot.id, val);
        const fresh = await getOrderSnapshot(snapshot.id);
        currentOrder=fresh; paintPanel(fresh);
      }catch(err){
        alert('Неуспешно изпращане: '+err.message);
      }finally{
        sendBtn.disabled=false; txt.value='';
      }
    });

    return wrap;
  }

  function renderTimelineFiles(snapshot){
    const wrap = el('div','mt-4');
    wrap.innerHTML = `<div class="font-semibold text-sm mb-2">Timeline</div>`;
    const list = el('div','space-y-2');
    (snapshot.timeline||[]).slice().reverse().forEach(ev=>{
      const row = el('div','border-l-4 pl-3 py-1 '+(ev.kind==='file'?'border-indigo-400':ev.kind==='task'?'border-emerald-400':'border-slate-400'));
      row.innerHTML = `
        <div class="text-xs text-slate-500">${ev.when||''} · ${ev.who||''}</div>
        <div class="text-sm">${ev.text||''}</div>
      `;
      list.appendChild(row);
    });
    wrap.appendChild(list);
    return wrap;
  }

  function paintPanel(snapshot){
    body.innerHTML='';
    renderHeader(snapshot);
    body.appendChild(renderSummary(snapshot));
    body.appendChild(el('hr','my-3'));
    body.appendChild(el('div','text-xs text-slate-500','* Кабинет: резюме, зачисляване към шофьор, файлове, задачи, съобщения и timeline.'));
    body.appendChild(el('hr','my-3'));
    // секции
    Promise.resolve().then(async ()=>{
      body.appendChild(await renderAssign(snapshot));
      body.appendChild(renderFiles(snapshot));
      body.appendChild(renderTasks(snapshot));
      body.appendChild(renderMessages(snapshot));
      body.appendChild(renderTimelineFiles(snapshot));
    });
  }

  // Подсветка на ред без шофьор (сигнален цвят)
  function annotateRowDriverState(orderId, hasDriver){
    // потърси реда по data-order-id
    const row = document.querySelector(`[data-order-row="${orderId}"]`);
    if(!row) return;
    row.classList.toggle('bg-rose-50', !hasDriver);
    row.classList.toggle('outline', !hasDriver);
    row.classList.toggle('outline-1', !hasDriver);
    row.classList.toggle('outline-rose-300', !hasDriver);
  }

  // Инициализация: закачи бутона „Кабинет“
  document.addEventListener('click', async (e)=>{
    const btn = e.target.closest('[data-open-cabinet]');
    if(!btn) return;
    const orderId = btn.getAttribute('data-order-id');
    const orderTitle = btn.getAttribute('data-order-title') || ('Поръчка #'+orderId);
    // маркирай реда в DOM с атрибут (ако не е)
    const tr = btn.closest('tr');
    if(tr && !tr.hasAttribute('data-order-row')){
      tr.setAttribute('data-order-row', orderId);
    }
    try{
      currentOrderId = orderId;
      titleEl.textContent = 'Кабинет · ' + orderTitle;
      body.innerHTML = '<div class="text-sm text-slate-500">Зареждане…</div>';
      openPanel();
      const snapshot = await getOrderSnapshot(orderId);
      currentOrder = snapshot;
      paintPanel(snapshot);
      annotateRowDriverState(orderId, !!snapshot.driver?.id);
    }catch(err){
      body.innerHTML = `<div class="text-sm text-red-600">Грешка при зареждане: ${err.message}</div>`;
    }
  });

})();
