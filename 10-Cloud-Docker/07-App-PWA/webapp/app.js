// API runs on port 5001 (socket server continues using 5000 for legacy clients)
const API_BASE = location.hostname === 'localhost' ? 'http://127.0.0.1:5001' : `${location.protocol}//${location.hostname}:5001`;

const seatMap = document.getElementById('seatMap');
const buyerTypeEl = document.getElementById('buyerType');
const refreshBtn = document.getElementById('refreshBtn');
const openCartBtn = document.getElementById('openCartBtn');
const cartCount = document.getElementById('cartCount');
const cartPanel = document.getElementById('cartPanel');
const cartList = document.getElementById('cartList');
const buyAllBtn = document.getElementById('buyAllBtn');
const clearCartBtn = document.getElementById('clearCartBtn');
const logEl = document.getElementById('log');
const saleOverlay = document.getElementById('saleOverlay');
const saleOverlayTitle = document.getElementById('saleOverlayTitle');
const saleOverlayText = document.getElementById('saleOverlayText');
const saleOverlayTimer = document.getElementById('saleOverlayTimer');

let availability = [];
let saleStatus = { state: 'loading', sales_open: false, sales_closed: false };
let cart = JSON.parse(localStorage.getItem('pwa_cart') || '[]');
let localBuyerId = localStorage.getItem('pwa_buyer_id') || `PWA-${Math.random().toString(36).slice(2,9)}`;
if (!localStorage.getItem('pwa_buyer_id')) localStorage.setItem('pwa_buyer_id', localBuyerId);
let localClientId = localStorage.getItem('pwa_client_id') || `PWA-CLIENT-${Math.random().toString(36).slice(2,9)}`;
if (!localStorage.getItem('pwa_client_id')) localStorage.setItem('pwa_client_id', localClientId);
let pollingHandle = null;

function log(msg){
  const p = document.createElement('div');
  p.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  logEl.prepend(p);
}

function updateCartUI(){
  cartCount.textContent = cart.length;
  cartList.innerHTML = '';
  cart.forEach(r => {
    const li = document.createElement('li');
    li.textContent = `Seat ${r.seat.row}-${r.seat.col} (${r.zone}) — ${r.status || 'reserved'}`;
    cartList.appendChild(li);
  });
}

function formatCountdown(seconds){
  const value = Math.max(0, Math.ceil(Number(seconds) || 0));
  const minutes = Math.floor(value / 60);
  const remainingSeconds = value % 60;
  return minutes > 0 ? `${minutes}:${String(remainingSeconds).padStart(2, '0')}` : `${remainingSeconds}s`;
}

function updateSaleOverlay(){
  const state = saleStatus.state || 'loading';
  if(state === 'open'){
    saleOverlay.classList.add('hidden');
    saleOverlayTitle.textContent = 'Venta abierta';
    saleOverlayText.textContent = 'Ya puedes seleccionar asientos.';
    saleOverlayTimer.textContent = '';
    return;
  }

  saleOverlay.classList.remove('hidden');

  if(state === 'countdown'){
    saleOverlayTitle.textContent = 'La venta está por iniciar';
    saleOverlayText.textContent = 'El coordinador ya autorizó el inicio y el servidor está en cuenta regresiva.';
    saleOverlayTimer.textContent = formatCountdown(saleStatus.countdown_remaining);
    return;
  }

  if(state === 'closed'){
    saleOverlayTitle.textContent = '✓ La venta ha concluido';
    const reason = saleStatus.close_reason || 'unknown';
    if(reason === 'all_sold'){
      saleOverlayText.textContent = 'Todos los asientos se vendieron exitosamente.';
    } else if(reason === 'all_clients_done'){
      saleOverlayText.textContent = 'La venta terminó cuando los clientes completaron su operación.';
    } else {
      saleOverlayText.textContent = 'La simulación ha finalizado.';
    }
    saleOverlayTimer.textContent = '';
    return;
  }

  if(state === 'waiting'){
    saleOverlayTitle.textContent = 'La venta no ha iniciado';
    saleOverlayText.textContent = 'Esperando a que el coordinador envíe la señal de inicio.';
    saleOverlayTimer.textContent = '';
    return;
  }

  saleOverlayTitle.textContent = 'Cargando estado...';
  saleOverlayText.textContent = 'Esperando respuesta del servidor.';
  saleOverlayTimer.textContent = '';
}

async function fetchAvailability(){
  try{
    const res = await fetch(API_BASE + '/api/availability');
    if(!res.ok) throw new Error('No availability');
    const data = await res.json();
    saleStatus = data.sale_status || saleStatus;
    availability = data.seat_status || [];
    renderSeats();
    updateSaleOverlay();
  }catch(err){
    log('No se pudo obtener disponibilidad: '+err.message);
    saleStatus = { state: 'offline', sales_open: false, sales_closed: false };
    updateSaleOverlay();
  }
}

async function registerPWA(){
  try{
    const payload = { client_id: localClientId, client_type: buyerTypeEl.value || 'normal', buyers: 1 };
    const res = await fetch(API_BASE + '/api/register_client', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if(!res.ok) {
      const txt = await res.text();
      log('Registro PWA falló: '+txt);
      return;
    }
    const data = await res.json();
    log('PWA registrada como cliente: ' + data.client_id + ` (${data.connected_clients}/${data.expected_clients})`);

    // signal ready so server can count this client
    const readyRes = await fetch(API_BASE + '/api/ready', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ client_id: localClientId }) });
    if(readyRes.ok){
      const rd = await readyRes.json();
      log('PWA READY: ' + JSON.stringify(rd));
    }
  }catch(err){
    log('Error registrando PWA: '+err.message);
  }
}

function renderSeats(){
  seatMap.innerHTML = '';
  
  // Determine grid columns based on max columns
  const cols = 50; // COLUMNAS from server
  seatMap.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  
  const rowsPerSection = [3, 4, 23]; // PLATINO, PREFERENTE, NORMAL (rows 0-2, 3-6, 7-29)
  const sectionNames = ['SECCIÓN PLATINO', 'SECCIÓN PREFERENTE', 'SECCIÓN NORMAL'];
  const sectionStartRows = [0, 3, 7];
  let currentSectionIdx = 0;
  let nextSectionStartRow = sectionStartRows[1];
  
  for(let r=0;r<availability.length;r++){
    // Add section header when entering a new section
    if(currentSectionIdx < sectionNames.length && r === sectionStartRows[currentSectionIdx]){
      const label = document.createElement('div');
      label.classList.add('section-label');
      label.textContent = sectionNames[currentSectionIdx];
      seatMap.appendChild(label);
      if(currentSectionIdx < sectionNames.length - 1){
        currentSectionIdx++;
        nextSectionStartRow = sectionStartRows[currentSectionIdx];
      }
    }
    
    for(let c=0;c<Math.min(availability[r].length, cols);c++){
      const cell = document.createElement('div');
      cell.classList.add('seat');
      const state = availability[r][c];
      if(state === 'FREE') cell.classList.add('free');
      else if(state === 'RESERVED') cell.classList.add('reserved');
      else cell.classList.add('sold');
      // annotate if seat is in cart
      const inCart = cart.find(x => x.seat.row===r && x.seat.col===c && x.status!=='sold');
      if(inCart) cell.classList.add('mine');

      cell.textContent = `${r}-${c}`;
      cell.dataset.row = r;
      cell.dataset.col = c;
      if(state !== 'SOLD'){
        cell.addEventListener('click', onSeatClick);
      }
      seatMap.appendChild(cell);
    }
  }
}

async function onSeatClick(evt){
  const row = parseInt(evt.currentTarget.dataset.row, 10);
  const col = parseInt(evt.currentTarget.dataset.col, 10);
  const buyerType = buyerTypeEl.value;

  // Send request_ticket to server with specific seat coordinates
  const payload = {
    type: 'REQUEST_TICKET',
    buyer_id: localBuyerId,
    buyer_type: buyerType,
    request_id: cryptoRandomId(),
    row: row,
    col: col,
  };

  try{
    const res = await fetch(API_BASE + '/api/request_ticket', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(data.status === 'ok' && data.reservation_id){
      const entry = { reservation_id: data.reservation_id, seat: data.seat, zone: data.zone, status: 'reserved', ttl_seconds: data.ttl_seconds };
      cart.push(entry);
      localStorage.setItem('pwa_cart', JSON.stringify(cart));
      log(`Reserva OK asiento ${entry.seat.row}-${entry.seat.col} id=${entry.reservation_id}`);
      updateCartUI();
      renderSeats();
    } else {
      log('Reserva rechazada: ' + (data.message || JSON.stringify(data)));
    }
  }catch(err){
    log('Error en reserva: '+err.message);
  }
}

function cryptoRandomId(){
  return Math.random().toString(36).slice(2)+Date.now().toString(36);
}

async function buyAll(){
  if(cart.length === 0) return log('Carrito vacío');
  for(let i=0;i<cart.length;i++){
    const entry = cart[i];
    if(entry.status === 'sold') continue;
    try{
      const payload = { type:'PURCHASE', buyer_id: localBuyerId, reservation_id: entry.reservation_id, request_id: cryptoRandomId() };
      const res = await fetch(API_BASE + '/api/purchase', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const data = await res.json();
      if(data.status === 'ok'){
        entry.status = 'sold';
        entry.ticket_id = data.ticket_id || data.ticket?.ticket_id;
        log(`Compra OK asiento ${entry.seat.row}-${entry.seat.col} ticket=${entry.ticket_id||'n/a'}`);
      } else {
        entry.status = 'failed';
        log(`Compra fallida para ${entry.seat.row}-${entry.seat.col}: ${JSON.stringify(data)}`);
      }
    }catch(err){
      entry.status = 'failed';
      log('Error en compra: '+err.message);
    }
    localStorage.setItem('pwa_cart', JSON.stringify(cart));
    updateCartUI();
  }
  // refresh availability after purchases
  await fetchAvailability();
}

refreshBtn.addEventListener('click', fetchAvailability);
openCartBtn.addEventListener('click', ()=>{ cartPanel.classList.toggle('hidden'); updateCartUI(); });
buyAllBtn.addEventListener('click', buyAll);
clearCartBtn.addEventListener('click', ()=>{ cart=[]; localStorage.setItem('pwa_cart', JSON.stringify(cart)); updateCartUI(); renderSeats(); log('Carrito vaciado'); });

// polling
function startPolling(){
  if(pollingHandle) clearInterval(pollingHandle);
  pollingHandle = setInterval(fetchAvailability, 1000);
}

// service worker registration
if('serviceWorker' in navigator){
  navigator.serviceWorker.register('sw.js').then(()=>console.log('sw registered')).catch(()=>console.log('sw failed'));
}

// init
updateCartUI();
updateSaleOverlay();
registerPWA();  // Register as client BEFORE fetching availability
fetchAvailability();
startPolling();
