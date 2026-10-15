import { routeLinks } from './transfer-route.js';
import { CONFIG } from './config.js';
import { QueuedSend, canQueue, estimatedWait } from './visitor-flow.js';
import { packPixels, unpackPixels, validatePayload, payloadHash } from './payload.js';
const $ = id => document.getElementById(id);
const tabs = [...document.querySelectorAll('[role=tab]')];
let mode = 'live', tab = 'drawing', source = null, payload = null, busy = false, socket = null, token = null;
let session = null, room = null, turnstileToken = '', widget = null, reconnectTimer, reconnectAttempt = 0, connectedOnce = false;
let transferId = null, savedPayload = null, startedAt = 0, demoTimer = null, stageIndex = -1, lastTelemetry = 0;
let workspace = 'compose', previewInView = false;
const queuedSend = new QueuedSend();
let verificationNeeded = false;
let joining = false, autoConnect = true, lastRoomAt = 0, sendAttempt = 0, commandSubmitted = false;
const phoneLayout = matchMedia('(max-width: 650px), (max-width: 950px) and (max-height: 500px)');
const stages = ['prepared', 'uploaded', 'queued', 'accepted', 'plc', 'vlc', 'confirmed'];
let erased = false, drawingPointer = null, history = [], changedDuringStroke = false;
const drawing = $('drawing'), dctx = drawing.getContext('2d');
const safely = (fn, fallback = null) => { try { return fn(); } catch { return fallback; } };
const draft = safely(() => JSON.parse(localStorage.getItem('iol-draft')));
$('message').value = draft?.text || '';
function fillWhite() { dctx.fillStyle = '#fff'; dctx.fillRect(0, 0, drawing.width, drawing.height); }
fillWhite();
if (draft?.drawing?.startsWith('data:image/png;base64,') && draft.drawing.length < 1000000) {
  const image = new Image(); image.onload = () => { dctx.drawImage(image, 0, 0, 640, 320); update(); }; image.src = draft.drawing;
}
function saveDraft() { safely(() => localStorage.setItem('iol-draft', JSON.stringify({ text: $('message').value, drawing: drawing.toDataURL('image/png') }))); }
function renderPixels(canvas, p) {
  canvas.width = p.width; canvas.height = p.height;
  const ctx = canvas.getContext('2d'), pixels = unpackPixels(p), image = ctx.createImageData(p.width, p.height);
  pixels.forEach((v, i) => { image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = v ? 22 : 255; image.data[i * 4 + 3] = 255; });
  ctx.putImageData(image, 0, 0);
}

function renderPartial(m) {
  const clean = validatePayload({ kind: 'image', width: m.width, height: m.height, data: m.data });
  const mask = unpackPixels(validatePayload({ ...clean, data: m.mask }));
  const pixels = unpackPixels(clean), c = $('received-pixels'); c.width = clean.width; c.height = clean.height;
  const x = c.getContext('2d'), image = x.createImageData(c.width, c.height);
  pixels.forEach((p,i) => { const v = mask[i] ? p ? 22 : 255 : 135; image.data.set([v,v,v,255],i*4); });
  x.putImageData(image,0,0); c.hidden = false; $('receiver-empty').hidden = true;
  $('receiver-meta').textContent = 'PARTIAL · gray pixels have not arrived · awaiting verification';
}
function showShared(m) {
  try {
    const p = validatePayload(m.received); $('shared-empty').hidden = true;
    $('shared-text').hidden = p.kind !== 'text'; $('shared-pixels').hidden = p.kind !== 'image';
    if (p.kind === 'text') $('shared-text').textContent = p.text;
    else renderPixels($('shared-pixels'),p);
    $('shared-meta').textContent = (m.simulated ? 'SIMULATED · ' : 'VERIFIED · ') + (m.durationMs / 1000).toFixed(1) + ' seconds · shared with permission';
  } catch { /* Ignore malformed display content. */ }
}

function imagePayload(input) {
  const width = +$('resolution').value, height = width / 2, canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height);
  const iw = input.naturalWidth || input.width, ih = input.naturalHeight || input.height, scale = Math.min(width / iw, height / ih);
  ctx.drawImage(input, (width - iw * scale) / 2, (height - ih * scale) / 2, iw * scale, ih * scale);
  const data = ctx.getImageData(0, 0, width, height).data, pixels = [];
  for (let i = 0; i < data.length; i += 4) pixels.push(.299 * data[i] + .587 * data[i + 1] + .114 * data[i + 2] < +$('threshold').value);
  return packPixels(pixels, width, height);
}
function update() {
  $('characters').textContent = `${$('message').value.length} / ${CONFIG.maxTextCharacters} characters`;
  $('text-bytes').textContent = `${new TextEncoder().encode($('message').value).length} bytes`;
  $('threshold-value').textContent = $('threshold').value;
  $('conversion').hidden = tab === 'text'; $('pixel-preview').hidden = tab === 'text'; $('preview-text').hidden = tab !== 'text';
  $('payload-tag').textContent = tab.toUpperCase();
  payload = null;
  try {
    if (tab === 'text') {
      $('preview-text').textContent = $('message').value || 'Your message appears here.';
      payload = validatePayload({ kind: 'text', text: $('message').value });
      $('payload-details').textContent = `${payload.text.length} message bytes · transfer ID + checksum added by the agent`;
    } else {
      if (tab === 'image' && !source) throw new Error('Choose an image to get started.');
      payload = imagePayload(tab === 'image' ? source : drawing);
      renderPixels($('pixel-preview'), payload);
      $('payload-details').textContent = `${payload.width} × ${payload.height} · ${payload.width * payload.height / 8} packed bytes · monochrome`;
    }
  } catch (e) { $('payload-details').textContent = ! $('message').value && tab === 'text' ? 'Write a message to get started.' : e.message; }
  document.querySelector('.drawing-options').hidden=tab==='text';
  syncButtons();
}
function setTab(next) {
  tab = next;
  tabs.forEach(button => { const active = button.dataset.tab === next; button.setAttribute('aria-selected', active); button.tabIndex = active ? 0 : -1; $(`panel-${button.dataset.tab}`).hidden = !active; });
  update();
}
tabs.forEach((button, index) => {
  button.onclick = () => setTab(button.dataset.tab);
  button.onkeydown = event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
      tabs[next].focus(); setTab(tabs[next].dataset.tab);
    }
  };
});
$('message').oninput = () => { saveDraft(); update(); };
$('clear-text').onclick = () => { $('message').value = ''; saveDraft(); update(); };
let imageRequest = 0;
async function upload(file) {
  if (!file) return;
  const request = ++imageRequest;
  $('send-error').textContent = '';
  try {
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('Choose a PNG, JPEG, or WebP image.');
    if (file.size > CONFIG.maxOriginalBytes) throw new Error('The original must be smaller than 8 MB.');
    const url = URL.createObjectURL(file), image = new Image();
    try { image.src = url; await image.decode(); } finally { URL.revokeObjectURL(url); }
    if (request !== imageRequest) return;
    if (image.naturalWidth * image.naturalHeight > 40000000) throw new Error('Choose an image below 40 megapixels.');
    source = image;
    const thumb = document.createElement('canvas'), ratio = Math.min(1, 600 / Math.max(image.naturalWidth, image.naturalHeight));
    thumb.width = Math.round(image.naturalWidth * ratio); thumb.height = Math.round(image.naturalHeight * ratio);
    thumb.getContext('2d').drawImage(image, 0, 0, thumb.width, thumb.height);
    $('source-preview').src = thumb.toDataURL('image/png'); $('source-preview').hidden = false;
    $('source-details').textContent = `${file.name} · ${image.naturalWidth} × ${image.naturalHeight} · ${(file.size / 1024).toFixed(1)} kB original`;
    setTab('image');
  } catch (e) { $('send-error').textContent = e.message; }
}
$('image-file').onchange = e => upload(e.target.files[0]); $('camera-file').onchange = e => upload(e.target.files[0]);
$('resolution').onchange = update; $('threshold').oninput = update;
function snapshot() { history.push(dctx.getImageData(0, 0, 640, 320)); if (history.length > 15) history.shift(); }
function point(event) { const r = drawing.getBoundingClientRect(); return { x: (event.clientX - r.left) * 640 / r.width, y: (event.clientY - r.top) * 320 / r.height }; }
drawing.onpointerdown = event => {
  if (drawingPointer !== null || busy || queuedSend.pending) return;
  event.preventDefault(); snapshot(); drawingPointer = event.pointerId; changedDuringStroke = true; drawing.setPointerCapture(event.pointerId);
  const p = point(event); dctx.strokeStyle = erased ? '#ffffff' : $('pen-colour').value; dctx.lineWidth = +$('pen-size').value;
  dctx.lineCap = 'round'; dctx.lineJoin = 'round'; dctx.beginPath(); dctx.moveTo(p.x, p.y); dctx.lineTo(p.x + .01, p.y + .01); dctx.stroke();
};
drawing.onpointermove = event => { if (event.pointerId !== drawingPointer) return; event.preventDefault(); const p = point(event); dctx.lineTo(p.x, p.y); dctx.stroke(); };
function endStroke(event) { if (event.pointerId !== drawingPointer) return; drawingPointer = null; if (changedDuringStroke) { changedDuringStroke = false; saveDraft(); update(); } }
drawing.onpointerup = endStroke; drawing.onpointercancel = endStroke; drawing.onlostpointercapture = endStroke;
$('eraser').onclick = () => { erased = !erased; $('eraser').setAttribute('aria-pressed', erased); };
$('undo').onclick = () => { const old = history.pop(); if (old) dctx.putImageData(old, 0, 0); saveDraft(); update(); };
$('clear-drawing').onclick = () => { snapshot(); fillWhite(); saveDraft(); update(); };
let routeStage='waiting';
function showRoute(stage='waiting', status='active') {
  routeStage=stage;
  $('transfer-route').hidden=false;
  const simulated=mode==='demo' || !!room?.simulated;
  $('route-mode').textContent=simulated ? 'SIMULATED ROUTE' : 'LIVE ROUTE';
  const captions={waiting:'Waiting for your turn. Your message has not been sent yet.',prepared:'Preparing your message for the project.',uploaded:'Your message reached the cloud relay.',queued:'Waiting for the sender PC.',accepted:'The sender PC picked up your message.',plc:'Transferring through the PLC adapters to VLC TX.',vlc:'Transmitting light from VLC TX to VLC RX.',confirmed:'Waiting for receiver verification.'};
  $('route-status').textContent=status==='confirmed' ? (simulated ? 'Simulated arrival complete.' : 'Received and verified. The journey is complete!') : status==='paused' ? 'Connection interrupted. Waiting for the real transfer status.' : status!=='active' ? 'Transfer stopped without a confirmed arrival.' : captions[stage] || captions.waiting;
  const links=routeLinks(stage,status);
  document.querySelectorAll('.route-link').forEach((link,i)=>{link.dataset.state=links[i];link.querySelector('small').textContent=({done:'Done',active:'Transferring',waiting:'Waiting',paused:'Paused',stopped:'Stopped'})[links[i]];});
  document.querySelectorAll('.route-node').forEach((node,i)=>{node.dataset.done=String(i===0 || links[i-1]==='done');});
}
function focusRoute() {
  $('transfer-route').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
function markStage(stage, message = '') {
  showRoute(stage);
  stageIndex = stages.indexOf(stage);
  [...$('journey').children].forEach((li, i) => { li.className = i < stageIndex ? 'done' : i === stageIndex ? 'current' : ''; });
  if (stage === 'confirmed') [...$('journey').children].forEach(li => li.className = 'done');
  if (message) {
    const friendly={prepared:'Preparing your message…',uploaded:'Your message reached the project.',queued:'Your message is with the sender.',accepted:'The sender picked up your message.',plc:'Travelling through the powerline link…',vlc:'Travelling across the light link…',confirmed:'It arrived through light. Look at the receiver!'};
    $('transfer-status').textContent=mode==='live' ? (friendly[stage] || message) : message;
  }
  visitorNotice();
  if (busy && mode === 'demo') $('monitor-activity').textContent = `SIMULATED · ${$('journey').children[Math.max(0, stageIndex)].textContent}`;
}
function visitorNotice() {
  const waiting = queuedSend.pending && queuedSend.pending.phase !== 'dispatched';
  const connected = socket?.readyState === 1;
  let title, detail, state = 'checking';
  if (mode === 'demo') { title='Practice mode'; detail='This is a simulation. No hardware is used.'; state='practice'; }
  else if (busy) { title='Your message is on its way'; detail=$('transfer-status').textContent; state='sending'; }
  else if (waiting) {
    const position=room?.queue?.indexOf(session) ?? -1;
    title=position>=0 ? 'Your message is queued' : connected ? 'Saving your place…' : 'Connecting before sending…';
    detail=position>=0 ? estimatedWait(room,session)+'. Keep this page open. Estimates depend on reception.' : 'Your message is saved for this send. You can cancel below.';
    state='queued';
  } else if (!connected || !room) {
    title=verificationNeeded ? 'One quick check' : $('connection-error').textContent ? 'Connection needs attention' : 'Checking the demonstration…';
    detail=verificationNeeded ? 'Complete the verification below to connect. Your drawing stays here.' : $('connection-error').textContent || 'You can start drawing while we connect.';
  } else if (!room.online) {
    title='Demo temporarily paused'; detail='You can keep drawing or try a simulated send while the team brings the rig online.'; state='paused';
  } else if (!canQueue(room)) {
    title='Preparing the light link'; detail='The previous message is clearing. You can keep drawing.'; state='paused';
  } else {
    title=room.active ? 'Someone else is sending' : 'Ready to send';
    detail=room.active ? "Tap Send when you're ready. We'll save your place in line." : 'Tap Send and watch your message arrive at the receiver.';
    state='ready';
  }
  $('visitor-notice').dataset.state=state;
  $('notice-title').textContent=title; $('notice-detail').textContent=detail;
  const alternative=$('notice-mode');
  alternative.hidden=mode!=='demo' && !(connected && room && !room.online);
  alternative.textContent=mode==='demo' ? 'Return to the live rig' : 'Try a practice demo';
  alternative.disabled=busy || !!queuedSend.pending;
  $('rig-status').textContent=mode==='demo' ? 'Practice' : !connected || !room ? 'Checking…' : !room.online ? 'Paused' : !canQueue(room) ? 'Preparing' : 'Online';
  $('turn-status').textContent=busy ? 'Sending…' : waiting ? (room?.queue?.includes(session) ? 'Queue position '+(room.queue.indexOf(session)+1) : 'Saving your place…') : 'Ready when you are';
}
function syncButtons() {
  const waiting=queuedSend.pending && queuedSend.pending.phase!=='dispatched';
  const locked=busy || !!queuedSend.pending;
  const content=payload && (payload.kind==='text' ? payload.text.trim().length>0 : unpackPixels(payload).some(Boolean));
  const paused=mode==='live' && room && !canQueue(room);
  const noun=tab==='drawing' ? 'drawing' : tab==='image' ? 'picture' : 'message';
  $('send').textContent=busy ? 'Sending…' : waiting ? 'Waiting your turn…' : paused ? 'Demo paused' : mode==='demo' ? 'Try a practice send ↗' : 'Send my '+noun+' ↗';
  $('send').disabled=!content || locked || !!paused;
  $('send').hidden=false;
  $('editor-fields').disabled=locked;
  document.querySelector('.editor').setAttribute('aria-busy',String(locked));
  drawing.setAttribute('aria-disabled',String(locked));
  $('share-display').disabled=locked; $('disconnect').disabled=locked;
  for (const id of ['join-queue','leave-queue','preview-payload','return-editor']) $(id).hidden=true;
  $('cancel').hidden=!locked;
  $('cancel').textContent=waiting ? 'Cancel send' : 'Cancel transfer';
  $('demo-mode').disabled=locked; $('live-mode').disabled=locked;
  visitorNotice();
}
function setWorkspace(next) {
  workspace='compose'; document.body.dataset.view='compose';
  if(next==='monitor') {
    $('technical-details').open=true;
    document.querySelector('.monitor-card').scrollIntoView({block:'start',behavior:'auto'});
  } else document.querySelector('.editor').scrollIntoView({block:'start',behavior:'auto'});
  syncButtons();
}
$('view-compose').onclick = () => setWorkspace('compose');
$('view-monitor').onclick = () => setWorkspace('monitor');
$('return-editor').onclick = () => { setWorkspace('compose'); document.querySelector('.editor').scrollIntoView({ block: 'start', behavior: 'auto' }); };
$('preview-payload').onclick = () => {
  if (/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || '')) document.activeElement.blur();
  $('payload-preview-card').scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
};
let previewObserver;
function observePreview() {
  previewObserver?.disconnect();
  const landscape = matchMedia('(min-width: 651px) and (max-height: 500px)').matches;
  previewObserver = new IntersectionObserver(entries => { previewInView = entries[0].isIntersecting && entries[0].intersectionRatio >= .5; syncButtons(); }, { threshold: [0, .5, 1], rootMargin: phoneLayout.matches ? landscape ? '-118px 0px -80px 0px' : '-180px 0px -90px 0px' : '0px' });
  previewObserver.observe(document.querySelector('.preview-box'));
}
observePreview();
phoneLayout.addEventListener('change', () => { observePreview(); syncButtons(); });
function positionPhoneDock() {
  const gap = window.visualViewport && phoneLayout.matches ? Math.max(0, window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop) : 0;
  const keyboard = gap > 120 && /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || '');
  document.body.classList.toggle('keyboard-open', keyboard);
  $('action-dock').style.bottom = keyboard ? `${gap}px` : '';
}
window.visualViewport?.addEventListener('resize', positionPhoneDock);
window.visualViewport?.addEventListener('scroll', positionPhoneDock);
document.addEventListener('focusin', positionPhoneDock); document.addEventListener('focusout', () => setTimeout(positionPhoneDock, 0));
function showConnection(label, detail, online = false) {
  $('join-fields').hidden = !!token;
  $('connection-state').hidden = !token;
  $('connection-label').textContent = label;
  $('connection-label').classList.toggle('connection-online', online);
  $('connection-detail').textContent = detail;
}
$('disconnect').onclick = () => {
  if (busy || queuedSend.pending) return;
  autoConnect=false; $('connect').hidden=false;
  clearTimeout(reconnectTimer); token = null; session = null;
  const previous = socket; socket = null; previous?.close(1000, 'Visitor disconnected');
  room = null; connectedOnce = false; reconnectAttempt = 0;
  showConnection('Disconnected', '');
  $('relay-status').textContent = 'Disconnected'; $('rig-status').textContent = 'Rig offline / unknown';
  $('connection-error').textContent = ''; clearTelemetry(); syncButtons(); setupTurnstile();
};
function switchMode(next) {
  if (busy || queuedSend.pending) return;
  autoConnect=next==='live';
  $('transfer-route').hidden=true;
  mode = next; $('demo-mode').setAttribute('aria-pressed', next === 'demo'); $('live-mode').setAttribute('aria-pressed', next === 'live');
  $('mode-banner').classList.toggle('live-banner', next === 'live'); $('connection-panel').hidden = next !== 'live';
  $('mode-title').textContent = next === 'demo' ? 'Demo mode — no hardware connected' : 'Live mode — waiting for the rig';
  $('mode-description').textContent = next === 'demo' ? 'Everything stays in your browser. Transfer stages and receiver results are simulated.' : 'Only hardware acknowledgements can confirm a real transfer.';
  if (next === 'demo') { clearTimeout(reconnectTimer); socket?.close(); socket = null; room = null; token = null; connectedOnce = false; }
  $('received-text').hidden = true; $('received-pixels').hidden = true; $('receiver-empty').hidden = false;
  $('receiver-meta').textContent = ''; $('transfer-status').textContent = 'No transfer in this mode yet.';
  [...$('journey').children].forEach(li => li.className = ''); stageIndex = -1;
  $('rig-status').textContent = next === 'demo' ? 'Simulated' : 'Rig offline'; $('relay-status').textContent = next === 'demo' ? 'Browser demo' : 'Not connected';
  $('role-status').textContent = next === 'demo' ? 'Demo controller' : 'Viewer'; $('turn-status').textContent = next === 'demo' ? 'No queue in demo' : 'Not in queue';
  showConnection('Disconnected', ''); clearTelemetry(); setupTurnstile(); syncButtons();
  $('monitor-mode').textContent = next === 'demo' ? 'Demo / no hardware' : 'Waiting for rig';
  $('monitor-activity').textContent = next === 'demo' ? 'No hardware connected. Demo transfers are simulated.' : 'Rig offline. Connect to the relay to view measured activity.';
}
$('notice-mode').onclick = () => switchMode(mode==='demo' ? 'live' : 'demo');
$('demo-mode').onclick = () => switchMode('demo'); $('live-mode').onclick = () => switchMode('live');
function clearTelemetry() { lastTelemetry = 0; for (const name of ['bufferPercent','bufferUsed','bufferCapacity','threshold','rxRate','rxGood','rxCrc','rxLocked','rxOverflows']) $('twin-' + name).textContent = 'Unavailable'; $('twin-buffer').value = 0; $('twin-streaming').textContent = 'Unavailable'; for (const name of ['throughput', 'loss', 'ber', 'snr', 'latency', 'links']) $(`metric-${name}`).textContent = 'Unavailable'; $('telemetry-tag').textContent = 'No measurements'; $('last-update').textContent = 'Waiting for measured telemetry.'; $('monitor-plc').textContent = 'Unavailable'; $('monitor-vlc').textContent = 'Unavailable'; }
function showTelemetry(m) {
  lastTelemetry = Date.now();
  for (const name of ['bufferPercent', 'bufferUsed', 'bufferCapacity', 'threshold', 'rxRate', 'rxGood', 'rxCrc', 'rxLocked', 'rxOverflows']) $('twin-' + name).textContent = Number.isFinite(m[name]) ? m[name] : 'Unavailable';
  $('twin-buffer').value = Number.isFinite(m.bufferPercent) ? m.bufferPercent : 0;
  $('twin-streaming').textContent = m.streaming === 1 ? 'Transmitting' : m.streaming === 0 ? 'Idle / priming' : 'Unavailable';
  $('telemetry-tag').textContent = m.simulated ? 'Simulated' : 'Measured';
  for (const [name, unit] of Object.entries({ throughput: ' kbit/s', loss: '%', ber: '', snr: ' dB', latency: ' ms' })) {
    const value = m[name]; $(`metric-${name}`).textContent = typeof value === 'number' && Number.isFinite(value) ? `${value}${unit}` : 'Unavailable';
  }
  $('metric-links').textContent = `${m.plc || 'Unavailable'} / ${m.vlc || 'Unavailable'}`;
  $('monitor-plc').textContent = m.plc || 'Unavailable'; $('monitor-vlc').textContent = m.vlc || 'Unavailable';
  $('last-update').textContent = `Updated ${new Date(lastTelemetry).toLocaleTimeString()}`;
}
function complete(result, simulated = false) {
  busy=false;queuedSend.cancel();
  $('arrival-heading').textContent=result.status==='confirmed' ? (simulated ? 'Practice result' : 'It arrived through light!') : 'At the receiver';
  if (simulated || mode === 'demo') $('monitor-activity').textContent = result.status === 'confirmed' ? 'SIMULATED · Transfer complete. No hardware was used.' : 'SIMULATED · Transfer stopped.';
  if (result.status === 'confirmed' && result.received) {
    markStage('confirmed', simulated ? 'Simulated transfer complete.' : 'Receiver confirmation received.');
    $('receiver-empty').hidden = true;
    $('received-text').hidden = result.received.kind !== 'text'; $('received-pixels').hidden = result.received.kind !== 'image';
    if (result.received.kind === 'text') $('received-text').textContent = result.received.text; else renderPixels($('received-pixels'), result.received);
    $('receiver-meta').textContent = `${simulated ? 'SIMULATED · ' : ''}Integrity: ${result.integrity || 'confirmed'} · ${((result.durationMs || Date.now() - startedAt) / 1000).toFixed(2)} s`;
  } else {
    $('transfer-status').textContent = result.message || 'Transfer stopped without receiver confirmation.';
    const li = $('journey').children[Math.max(0, stageIndex)]; li.className = 'failed';
  }
  showRoute(routeStage,result.status==='confirmed' ? 'confirmed' : 'stopped');
  syncButtons();
}
async function send(intent) {
  if (!intent?.payload || busy) return;
  const attempt=++sendAttempt;commandSubmitted=false;
  busy = true; syncButtons(); $('send-error').textContent = ''; $('receiver-meta').textContent = '';
  $('received-text').hidden = true; $('received-pixels').hidden = true; $('receiver-empty').hidden = false;
  savedPayload = structuredClone(intent.payload); startedAt = Date.now(); transferId = intent.id;
  markStage('prepared', mode === 'demo' ? 'Starting a simulated transfer…' : 'Preparing an authenticated transfer…');
  try {
    const hash = await payloadHash(savedPayload);
    if(attempt!==sendAttempt || !busy) return;
    if (mode === 'demo') {
      let i = 0;
      const advance = () => {
        i++; markStage(stages[i], `SIMULATED · ${$('journey').children[i].textContent}`);
        if (i === stages.length - 1) { complete({ status: 'confirmed', received: savedPayload, integrity: 'simulated exact match', durationMs: Date.now() - startedAt }, true); return; }
        demoTimer = setTimeout(advance, stages[i]==='vlc' ? 2500 : 650);
      };
      demoTimer = setTimeout(advance, 500);
    } else {
      if (!socket || socket.readyState !== 1) throw new Error('Relay disconnected. Your draft is saved.');
      if(room?.controller!==session || !canQueue(room) || room?.active) throw new Error('Your turn changed. Your draft is kept; tap Send again.');
      commandSubmitted=true;
      socket.send(JSON.stringify({ type: 'submit', id: transferId, hash, payload: savedPayload, shareDisplay: intent.shareDisplay }));
    }
  } catch(e) {
    busy=false;queuedSend.cancel();showRoute(routeStage,'stopped');$('send-error').textContent=e.message;
    if(socket?.readyState===1 && room?.controller===session && !room.active) socket.send(JSON.stringify({type:'leave'}));
    syncButtons();
  }
}
function processQueuedSend() {
  if(socket?.readyState!==1) return;
  const action=queuedSend.next(room,session);
  if(action?.type==='join') socket.send(JSON.stringify({type:'join'}));
  else if(action?.type==='submit') void send(action.intent);
  else if(action?.type==='paused') {
    if(room?.controller===session || room?.queue?.includes(session)) socket.send(JSON.stringify({type:'leave'}));
    showRoute(routeStage,'stopped');
    $('transfer-status').textContent='The demonstration paused. Your draft is kept; tap Send when it is ready again.';
  }
  syncButtons();
}
function requestSend() {
  if(!payload || busy || queuedSend.pending || (mode==='live' && room && !canQueue(room))) return;
  if(payload.kind==='image' && !unpackPixels(payload).some(Boolean)) return;
  showRoute('waiting');focusRoute();
  const options={kind:tab,shareDisplay:$('share-display').checked};
  const id=crypto.randomUUID();
  if(mode==='demo') { void send({payload:structuredClone(payload),...options,id}); return; }
  if(!queuedSend.start(payload,options,id)) return;
  $('send-error').textContent='';
  processQueuedSend();syncButtons();
  if(socket?.readyState!==1) { autoConnect=true;if(turnstileToken) void connectGuest(); }
}
$('send').onclick=requestSend;
$('cancel').onclick = () => {
  if(busy && !commandSubmitted && mode==='live') { ++sendAttempt;busy=false;queuedSend.cancel();if(socket?.readyState===1)socket.send(JSON.stringify({type:'leave'}));showRoute(routeStage,'stopped');$('transfer-status').textContent='Send cancelled before upload. Your draft is kept.';syncButtons();return; }
  if(queuedSend.pending && queuedSend.pending.phase!=='dispatched') { queuedSend.cancel(); if(socket?.readyState===1) socket.send(JSON.stringify({type:'leave'})); showRoute(routeStage,'stopped');$('transfer-status').textContent='Send cancelled. Your draft is kept.'; syncButtons(); return; }
  if (mode === 'demo') { clearTimeout(demoTimer); complete({ status: 'cancelled', message: 'Simulated transfer cancelled. Your draft is kept.' }); }
  else if (socket?.readyState === 1) { socket.send(JSON.stringify({ type: 'cancel', id: transferId })); $('transfer-status').textContent = 'Cancellation requested. Waiting for the agent to stop.'; }
  else $('send-error').textContent = 'Reconnect to request cancellation. The rig remains locked until reconciled.';
};
$('join-queue').onclick = () => socket?.send(JSON.stringify({ type: 'join' }));
$('leave-queue').onclick = () => socket?.send(JSON.stringify({ type: 'leave' }));
$('download-payload').onclick = () => {
  if (!payload) { $('send-error').textContent = 'Prepare a valid payload first.'; return; }
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'internet-of-light-payload.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
function relayBase() {
  if (!CONFIG.relayUrl) throw new Error('Live relay has not been configured. The demo is ready to use.');
  const url = new URL(CONFIG.relayUrl); if (url.protocol !== 'https:') throw new Error('The live relay must use HTTPS.');
  return url.origin;
}
async function setupTurnstile() {
  $('configured-relay').textContent = CONFIG.relayUrl ? 'Relay configured by the project team.' : 'The project team must configure a relay URL and Turnstile site key in config.js.';
  if (mode !== 'live' || !CONFIG.turnstileSiteKey) return;
  try {
    if (!window.turnstile) await new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'; script.onload = resolve; script.onerror = () => reject(new Error('Verification could not load.')); document.head.append(script);
    });
    if (widget === null) widget = window.turnstile.render('#turnstile-widget', { sitekey: CONFIG.turnstileSiteKey, 'before-interactive-callback': () => { verificationNeeded=true;syncButtons(); }, 'after-interactive-callback': () => { verificationNeeded=false;syncButtons(); }, callback: value => { verificationNeeded=false;turnstileToken=value; if(autoConnect && !token && mode==='live') void connectGuest(); }, 'expired-callback': () => turnstileToken = '', 'error-callback': () => { autoConnect=false;queuedSend.interrupted();$('connect').hidden=false;$('connection-error').textContent='Verification could not finish. Tap Retry connection or ask the team.';syncButtons(); } });
    else if (autoConnect && !token) { if (turnstileToken) void connectGuest(); else window.turnstile.reset(widget); }
  } catch (e) { $('connection-error').textContent=e.message;$('connect').hidden=false;syncButtons(); }
}
async function connectGuest() {
  if(joining || token || mode!=='live' || !turnstileToken) return;
  joining=true; $('connection-error').textContent=''; $('connect').disabled=true;
  try {
    const response=await fetch(relayBase()+'/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turnstile:turnstileToken})});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error || 'Could not connect. Try again shortly.');
    token=data.token;session=data.session;reconnectAttempt=0;openSocket();
  } catch(e) {
    autoConnect=false;queuedSend.interrupted();$('connection-error').textContent=e.message;
    $('connect').hidden=false;
  } finally {
    joining=false;turnstileToken='';$('connect').disabled=false;syncButtons();
  }
}
$('connect').onclick=()=>{
  autoConnect=true;$('connection-error').textContent='';
  if(turnstileToken) void connectGuest();
  else if(widget!==null) window.turnstile.reset(widget);
  else void setupTurnstile();
};
function openSocket() {
  if (mode !== 'live' || !token) return;
  socket?.close(); const current = new WebSocket(relayBase().replace('https:', 'wss:') + '/ws', ['iol', token]); socket = current;
  $('relay-status').textContent = 'Connecting…'; showConnection('Connecting…', 'Connecting to the live relay.');
  current.onopen = () => { reconnectAttempt = 0; connectedOnce = true; showConnection('Connected to relay', 'Waiting for the hardware status.', true); $('relay-status').textContent = 'Connected'; $('connection-error').textContent = ''; };
  current.onmessage = async event => {
    let data; try { data = JSON.parse(event.data); } catch { return; }
    if (data.type === 'room') {
      room = data; lastRoomAt=performance.now(); showConnection(data.online ? 'Connected · rig online' : 'Connected · rig offline', data.online ? (data.ready ? 'Draw something, then tap Send.' : 'The rig is preparing. You can follow its status below.') : 'Your phone is connected. Waiting for the project hardware.', true); $('disconnect').disabled = busy || !!data.active && data.active.owner === session; $('rig-status').textContent = data.online ? data.simulated ? 'Simulated agent' : data.ready ? 'Rig online' : 'Reconciling rig' : 'Rig offline';
      $('monitor-mode').textContent = data.simulated ? 'Simulated agent' : data.online ? 'Measured rig' : 'Rig offline';
      const activeStage = data.active ? stages.indexOf(data.active.stage) : -1;
      $('monitor-activity').textContent = !data.online ? 'Rig offline. Last activity cannot confirm a live connection.' : data.active ? `${data.simulated ? 'SIMULATED · ' : ''}${activeStage >= 0 ? $('journey').children[activeStage].textContent : 'Transfer in progress'}` : data.ready ? 'Rig idle. Waiting for the controller.' : 'Reconciling an interrupted transfer. Controls remain locked.';
      $('mode-title').textContent = data.simulated ? 'Live relay · simulated laptop agent' : 'Live mode — physical rig';
      $('mode-description').textContent = data.simulated ? 'The relay is real; hardware stages and receiver results are simulated.' : 'Only hardware acknowledgements can confirm a real transfer.';
      $('role-status').textContent = data.controller === session ? 'Controller' : 'Viewer';
      // Visitor queue text is rendered centrally by syncButtons().
      if (data.active?.owner === session) { transferId = data.active.id; busy = true; markStage(data.active.stage, data.active.message || 'Transfer in progress.'); if(!data.online) showRoute(routeStage,'paused'); }
      processQueuedSend();
    } else if (data.type === 'shared-result') showShared(data);
    else if (data.type === 'progress' && data.id === transferId) $('receiver-meta').textContent = 'Your picture is arriving: ' + data.receivedRecords + ' of ' + data.totalRecords + ' pieces.';
    else if (data.type === 'partial' && data.id === transferId) { try { renderPartial(data); } catch {} }
    else if (data.type === 'telemetry') showTelemetry(data);
    else if (data.type === 'transfer' && data.id === transferId) {
      if (data.stage) markStage(data.stage, data.message);
      if (['confirmed', 'failed', 'cancelled'].includes(data.status)) {
        if (data.status === 'confirmed') {
          try {
            if (!savedPayload || await payloadHash(data.received) !== await payloadHash(savedPayload)) throw new Error('Receiver payload did not match this draft.');
          } catch (e) { complete({ status: 'failed', message: e.message }); return; }
        }
        complete(data, !!data.simulated);
      }
    } else if (data.type === 'error') { $('send-error').textContent=data.message; if(queuedSend.pending?.phase !== 'dispatched') queuedSend.cancel(); if(!room?.active) { busy=false;queuedSend.cancel(); } if(!busy && !queuedSend.pending && !$('transfer-route').hidden)showRoute(routeStage,'stopped'); syncButtons(); }
  };
  current.onclose = () => {
    if (socket !== current || mode !== 'live') return;
    if(busy || queuedSend.pending) showRoute(routeStage,'paused');
    if(queuedSend.interrupted()) $('send-error').textContent='Connection interrupted. Your draft is kept; tap Send again once connected.';
    showConnection('Reconnecting…', 'Your draft is saved. Restoring the live connection.'); $('relay-status').textContent = 'Disconnected'; $('rig-status').textContent = 'Rig offline / unknown'; room = null; syncButtons();
    $('monitor-mode').textContent = 'Disconnected'; $('monitor-activity').textContent = 'Relay disconnected. Live rig status is unknown.';
    if (busy) $('transfer-status').textContent = 'Connection lost. Transfer status will be reconciled; your draft is kept.';
    if (reconnectAttempt < 6) reconnectTimer = setTimeout(openSocket, Math.min(30000, 1000 * 2 ** reconnectAttempt++));
    else { token = null; showConnection('Disconnected', ''); $('connection-error').textContent = 'Join the demonstration again. Your draft is kept.'; setupTurnstile(); }
  };
  current.onerror = () => { $('connection-error').textContent = connectedOnce ? 'Relay interrupted. Reconnecting…' : 'Could not reach the relay. Check configuration or sign in again.'; };
}
setInterval(() => {
  visitorNotice();
  if (lastTelemetry && Date.now() - lastTelemetry > 5000) { for (const name of ['bufferPercent','bufferUsed','bufferCapacity','threshold','rxRate','rxGood','rxCrc','rxLocked','rxOverflows']) $('twin-' + name).textContent = 'Stale'; $('twin-streaming').textContent = 'Stale'; $('telemetry-tag').textContent = 'Stale'; $('last-update').textContent = 'Telemetry is stale — last update over 5 seconds ago.'; $('monitor-plc').textContent = 'Stale'; $('monitor-vlc').textContent = 'Stale'; }
  if (mode === 'live' && socket?.readyState === 1 && room?.online && performance.now() - lastRoomAt > 5000) { room.online = false; if(busy)showRoute(routeStage,'paused'); showConnection('Connected · rig offline', 'Your phone is connected. Waiting for hardware telemetry.', true); $('rig-status').textContent = 'Rig offline'; $('monitor-mode').textContent = 'Rig offline'; $('monitor-activity').textContent = 'Agent telemetry stopped. Waiting for reconnection.'; syncButtons(); }
}, 1000);
switchMode('live');
setTab('drawing');
