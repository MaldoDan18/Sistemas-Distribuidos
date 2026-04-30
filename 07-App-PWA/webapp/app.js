const API_BASE = location.hostname === 'localhost' ? 'http://127.0.0.1:5000' : `${location.protocol}//${location.hostname}:5000`;

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

let availability = [];
let cart = JSON.parse(localStorage.getItem('pwa_cart') || '[]');
let localBuyerId = localStorage.getItem('pwa_buyer_id') || `PWA-${Math.random().toString(36).slice(2,9)}`;
if (!localStorage.getItem('pwa_buyer_id')) localStorage.setItem('pwa_buyer_id', localBuyerId);
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

async function fetchAvailability(){
  try{
    const res = await fetch(API_BASE + '/api/availability');
    if(!res.ok) throw new Error('No availability');
    const data = await res.json();
    availability = data.seat_status || [];
    renderSeats();
  }catch(err){
    log('No se pudo obtener disponibilidad: '+err.message);
  }
}

function renderSeats(){
  seatMap.innerHTML = '';
  for(let r=0;r<availability.length;r++){
    for(let c=0;c<availability[r].length;c++){
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
  const row = parseInt(evt.currentTarget.dataset.row,10);
  const col = parseInt(evt.currentTarget.dataset.col,10);
  const buyerType = buyerTypeEl.value;

  // Send request_ticket to server
  const payload = {
    type: 'REQUEST_TICKET',
    buyer_id: localBuyerId,
    buyer_type: buyerType,
    request_id: cryptoRandomId(),
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
      log(`Reserva OK ${entry.seat.row}-${entry.seat.col} id=${entry.reservation_id}`);
      updateCartUI();
      renderSeats();
    } else {
      log('Reserva rechazada: ' + JSON.stringify(data));
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
  pollingHandle = setInterval(fetchAvailability, 3000);
}

// service worker registration
if('serviceWorker' in navigator){
  navigator.serviceWorker.register('/webapp/sw.js').then(()=>console.log('sw registered')).catch(()=>console.log('sw failed'));
}

// init
updateCartUI();
fetchAvailability();
startPolling();
