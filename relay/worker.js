import { DurableObject } from 'cloudflare:workers';
import { RoomModel, FINAL } from './room-model.js';
import { payloadHash, validatePayload } from '../public/payload.js';
import { boundedJSON, equalSecret, signSession, verifySession } from './auth.js';
const json = (data, status = 200) => Response.json(data, { status });
const send = (ws, data) => { try { ws.send(JSON.stringify(data)); } catch { /* Closed sockets are pruned by the runtime. */ } };
export const guestPasscodeRequired = env => env.REQUIRE_PASSCODE !== 'false';
export const allowedOrigins = env => [...new Set([env.ALLOWED_ORIGIN, ...(env.ALLOWED_ORIGINS || '').split(',')].map(value => value?.trim()).filter(Boolean))];
export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin'), path = new URL(request.url).pathname;
    const allowed = allowedOrigins(env).includes(origin);
    if (request.method === 'OPTIONS') return new Response(null, { status: allowed ? 204 : 403, headers: allowed ? { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Vary': 'Origin' } : {} });
    if (!env.SESSION_SECRET || !env.AGENT_TOKEN || (guestPasscodeRequired(env) && !env.JOIN_PASSCODE) || !env.TURNSTILE_SECRET) return json({ error: 'The relay is not configured.' }, 503);
    let identity;
    if (path === '/receiver' && request.headers.get('Upgrade')?.toLowerCase() === 'websocket') {
      if (origin || !env.RECEIVER_TOKEN || !await equalSecret(request.headers.get('Authorization')?.replace(/^Bearer /, ''), env.RECEIVER_TOKEN)) return json({ error: 'Unauthorized.' }, 401);
      identity = { role: 'receiver' };
    } else if (path === '/agent' && request.headers.get('Upgrade')?.toLowerCase() === 'websocket') {
      if (origin || !await equalSecret(request.headers.get('Authorization')?.replace(/^Bearer /, ''), env.AGENT_TOKEN)) return json({ error: 'Unauthorized.' }, 401);
      identity = { role: 'agent' };
    } else {
      if (!allowed) return json({ error: 'Origin not allowed.' }, 403);
      if (path === '/join' && request.method === 'POST') identity = { role: 'join', origin, ip: request.headers.get('CF-Connecting-IP') || 'unknown' };
      else if (path === '/ws' && request.headers.get('Upgrade')?.toLowerCase() === 'websocket') {
        const protocols = (request.headers.get('Sec-WebSocket-Protocol') || '').split(',').map(v => v.trim());
        if (protocols[0] !== 'iol') return json({ error: 'Invalid protocol.' }, 400);
        const session = await verifySession(protocols[1], env.SESSION_SECRET); if (!session) return json({ error: 'Session expired.' }, 401);
        identity = { role: 'viewer', ...session };
      } else return json({ error: 'Not found.' }, 404);
    }
    // Ignore client-provided internal headers. Identity is assigned only after authentication.
    const headers = new Headers(request.headers); headers.set('X-IOL-Identity', JSON.stringify(identity));
    const response = await env.RIG.get(env.RIG.idFromName('capstone-rig')).fetch(new Request(request, { headers }));
    if (response.status === 101) return response;
    const out = new Response(response.body, response); if (allowed) { out.headers.set('Access-Control-Allow-Origin', origin); out.headers.set('Vary', 'Origin'); }
    out.headers.set('Cache-Control', 'no-store'); return out;
  },
};
export class RigRoom extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env); this.ctx = ctx; this.env = env; this.model = new RoomModel(); this.lastSaved = ''; this.rates = new Map();
    ctx.blockConcurrencyWhile(async () => { this.model = new RoomModel(await ctx.storage.get('room') || {}); this.lastSaved = JSON.stringify(this.model.state); });
  }
  viewers() { return this.ctx.getWebSockets('viewer').filter(ws => ws.readyState === 1); }
  agents() { return this.ctx.getWebSockets('agent').filter(ws => ws.readyState === 1); }
  ids() { return new Set(this.viewers().map(ws => ws.deserializeAttachment()?.session)); }
  agent() { return this.agents()[0]; }
  info() { return this.agent()?.deserializeAttachment(); }
  receiver() { return this.ctx.getWebSockets('receiver').find(ws => ws.readyState === 1); }
  receiverOnline() { const info = this.receiver()?.deserializeAttachment(); return !!info && Date.now() - info.seen < 5000; }
  receiverStatus() { if (this.agent()) send(this.agent(), { type: 'receiver-status', online: this.receiverOnline() }); }
  online() { return !!this.info() && Date.now() - this.info().seen < 5000 && (!this.info().requiresReceiver || this.receiverOnline()); }
  async save() {
    const state = JSON.stringify(this.model.state); if (state !== this.lastSaved) { await this.ctx.storage.put('room', this.model.state); this.lastSaved = state; }
    if (this.model.state.active || this.model.state.controller) {
      const at = this.model.state.active ? Date.now() + 10000 : Math.max(Date.now() + 1000, this.model.state.leaseUntil);
      const current = await this.ctx.storage.getAlarm(); if (!current || at < current) await this.ctx.storage.setAlarm(at);
    }
  }
  privateEvent(owner, event) { for (const ws of this.viewers()) if (ws.deserializeAttachment()?.session === owner) send(ws, event); }
  broadcast(event) { for (const ws of this.viewers()) send(ws, event); }
  roomEvent() {
    const s = this.model.state, info = this.info();
    // Public status contains neither payloads nor hashes. Only the owner receives their active ID.
    for (const ws of this.viewers()) {
      const id = ws.deserializeAttachment()?.session;
      send(ws, { type: 'room', online: this.online(), ready: !!info?.ready, simulated: !!info?.simulated, agentSeen: info?.seen || 0,
        controller: s.controller, leaseUntil: s.leaseUntil, queue: s.queue,
        active: s.active ? { id: s.active.owner === id ? s.active.id : null, owner: s.active.owner, stage: s.active.stage } : null });
    }
  }
  async fetch(request) {
    const identity = JSON.parse(request.headers.get('X-IOL-Identity'));
    if (identity.role === 'join') {
      try {
        // Hash addresses; counters expire after ten minutes. No raw IP is stored.
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(identity.ip))), b => b.toString(16).padStart(2, '0')).join('');
        const key = 'rate:' + hash, now = Date.now();
        let rate = await this.ctx.storage.get(key); if (!rate || now - rate.at > 60000) rate = { at: now, count: 0 };
        rate.count++; await this.ctx.storage.put(key, rate);
        if (!await this.ctx.storage.getAlarm()) await this.ctx.storage.setAlarm(now + 600000);
        if (rate.count > 5) return json({ error: 'Too many join attempts. Wait one minute.' }, 429);
        const body = await boundedJSON(request);
        if (guestPasscodeRequired(this.env) && !await equalSecret(body.passcode, this.env.JOIN_PASSCODE)) return json({ error: 'Incorrect invitation passcode.' }, 401);
        if (typeof body.turnstile !== 'string' || body.turnstile.length > 2048) return json({ error: 'Complete verification.' }, 400);
        const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body: new URLSearchParams({ secret: this.env.TURNSTILE_SECRET, response: body.turnstile, remoteip: identity.ip }) });
        const verified = await response.json();
        if (!verified.success || verified.hostname !== new URL(identity.origin || this.env.ALLOWED_ORIGIN).hostname) return json({ error: 'Verification failed. Try again.' }, 403);
        const session = crypto.randomUUID(); return json({ session, token: await signSession(session, this.env.SESSION_SECRET) });
      } catch { return json({ error: 'Invalid join request.' }, 400); }
    }
    if (this.ctx.getWebSockets().length >= 80) return json({ error: 'The demonstration room is full.' }, 429);
    if (identity.role === 'agent' && this.agent()) return json({ error: 'An agent is already connected.' }, 409);
    if (identity.role === 'receiver' && this.receiver()) return json({ error: 'A receiver is already connected.' }, 409);
    if (identity.role === 'viewer') {
      for (const existing of this.viewers()) if (existing.deserializeAttachment()?.session === identity.session) existing.close(1000, 'Session reconnected');
    }
    const pair = new WebSocketPair(), [client, server] = Object.values(pair);
    server.serializeAttachment({ ...identity, seen: Date.now(), ready: false, simulated: false, window: Date.now(), count: 0 });
    this.ctx.acceptWebSocket(server, [identity.role]);
    if (identity.role === 'agent') { send(server, { type: 'receiver-status', online: this.receiverOnline() }); send(server, { type: 'reconcile', active: this.model.state.active }); }
    else if (identity.role === 'receiver') { if (this.model.state.active) send(server, { type: 'arm', id: this.model.state.active.id }); this.receiverStatus(); }
    else {
      if (this.model.state.active?.owner === identity.session) this.privateEvent(identity.session, { type: 'transfer', id: this.model.state.active.id, stage: this.model.state.active.stage, message: 'Transfer status restored; waiting for the agent.' });
      const recent = this.model.state.recent.filter(t => t.owner === identity.session).at(-1);
      if (recent) send(server, { type: 'transfer', id: recent.id, status: recent.status === 'confirmed' ? 'failed' : recent.status, message: recent.status === 'confirmed' ? 'Transfer completed while disconnected. Receiver content expired; no automatic resend.' : 'Previous transfer ended. No automatic resend.' });
    }
    this.model.advance(Date.now(), this.ids()); await this.save(); this.roomEvent();
    return new Response(null, { status: 101, webSocket: client, headers: identity.role === 'viewer' ? { 'Sec-WebSocket-Protocol': 'iol' } : {} });
  }
  async webSocketMessage(ws, message) {
    let identity = ws.deserializeAttachment();
    try {
      if (typeof message !== 'string' || message.length > 4096) throw new Error('Message too large.');
      const now = Date.now();
      if (identity.role === 'viewer' && identity.exp <= now) { ws.close(1008, 'Session expired'); return; }
      if (now - identity.window > 60000) { identity.window = now; identity.count = 0; }
      if (++identity.count > (identity.role === 'receiver' ? 1200 : identity.role === 'agent' ? 500 : 30)) throw new Error('Message rate exceeded.');
      ws.serializeAttachment(identity);
      const data = JSON.parse(message);
      this.model.advance(now, this.ids());
      if (identity.role === 'receiver') {
        identity.seen = now; ws.serializeAttachment(identity); this.receiverStatus();
        const active = this.model.state.active;
        if (data.type === 'rx-stats') {
          const stats = {};
          for (const key of ['rate', 'good', 'crc', 'locked', 'overflows']) if (Number.isSafeInteger(data.stats?.[key]) && data.stats[key] >= 0) stats[key] = data.stats[key];
          if (this.agent()) send(this.agent(), { type: 'rx-stats', stats });
        } else if (data.type === 'receiver-armed') {
          if (!active || active.id !== data.id) throw new Error('Unknown receiver transfer.');
          identity.armed = data.id; ws.serializeAttachment(identity);
          if (this.agent()) send(this.agent(), { type: 'receiver-armed', id: data.id });
        } else if (data.type === 'rx-record') {
          if (!active || active.id !== data.id || identity.armed !== data.id) throw new Error('Receiver is not armed for this transfer.');
          if (typeof data.record !== 'string' || !/^[\x20-\x7e]{1,51}$/.test(data.record)) throw new Error('Invalid RX record.');
          if (this.agent()) send(this.agent(), { type: 'rx-record', id: data.id, record: data.record });
        } else throw new Error('Unsupported receiver command.');
      } else if (identity.role === 'agent') {
        identity.seen = now; ws.serializeAttachment(identity);
        if (data.type === 'ready') {
          if (this.model.state.active) throw new Error('Reconcile the outstanding transfer before becoming ready.');
          identity.ready = true; identity.simulated = !!data.simulated; identity.requiresReceiver = !!data.requiresReceiver; ws.serializeAttachment(identity);
        } else if (data.type === 'telemetry') {
          const telemetry = { type: 'telemetry', simulated: identity.simulated };
          for (const name of ['throughput', 'loss', 'ber', 'snr', 'latency', 'bufferUsed', 'bufferCapacity', 'bufferPercent', 'streaming', 'inflight', 'threshold', 'rxRate', 'rxGood', 'rxCrc', 'rxLocked', 'rxOverflows']) if (typeof data[name] === 'number' && Number.isFinite(data[name])) telemetry[name] = data[name];
          for (const name of ['plc', 'vlc']) if (['online', 'offline', 'simulated', 'unknown'].includes(data[name])) telemetry[name] = data[name];
          this.broadcast(telemetry); this.receiverStatus();
          if (this.model.state.active?.cancelRequested) send(ws, { type: 'cancel', id: this.model.state.active.id });
         } else if (data.type === 'arm-receiver') {
          if (data.id !== this.model.state.active?.id || !this.receiverOnline()) throw new Error('Receiver unavailable.');
          send(this.receiver(), { type: 'arm', id: data.id });
        } else if (data.type === 'progress' || data.type === 'partial') {
          const a = this.model.state.active;
          if (!a || data.id !== a.id) throw new Error('Unknown progress transfer.');
          if (data.type === 'progress') {
            if (!Number.isSafeInteger(data.receivedRecords) || !Number.isSafeInteger(data.totalRecords) || data.totalRecords < 1 || data.totalRecords > 44 || data.receivedRecords < 0 || data.receivedRecords > data.totalRecords) throw new Error('Invalid progress.');
            this.privateEvent(a.owner, { type: 'progress', id: a.id, receivedRecords: data.receivedRecords, totalRecords: data.totalRecords });
          } else {
            if (a.payload?.kind !== 'image' || data.width !== a.payload.width || data.height !== a.payload.height) throw new Error('Invalid partial dimensions.');
            const partial = validatePayload({ kind: 'image', width: data.width, height: data.height, data: data.data });
            const mask = validatePayload({ kind: 'image', width: data.width, height: data.height, data: data.mask });
            this.privateEvent(a.owner, { type: 'partial', id: a.id, ...partial, mask: mask.data });
          }
        } else if (data.type === 'transfer') {
          const a = this.model.state.active; if (!a || data.id !== a.id) throw new Error('Unknown transfer.');
          if (FINAL.includes(data.status)) {
            if (data.idle !== true) throw new Error('Agent must confirm the hardware is idle before releasing the rig.');
            let received;
            if (data.status === 'confirmed') {
              received = validatePayload(data.received);
              if (await payloadHash(received) !== a.hash) throw new Error('Receiver checksum does not match.');
            }
            const event = { type: 'transfer', id: a.id, status: data.status, received, simulated: identity.simulated, integrity: received ? 'SHA-256 payload match; agent RX verification' : undefined,
              durationMs: now - a.started, message: typeof data.message === 'string' ? data.message.slice(0, 200) : undefined };
            const owner = a.owner;
            if (received && a.shareDisplay === true) { const shared = { ...event, type: 'shared-result' }; this.broadcast(shared); if (this.receiver()) send(this.receiver(), shared); }
            if (this.receiver()) send(this.receiver(), { type: 'disarm', id: a.id });
            this.model.finish(data, now); identity.ready = true; ws.serializeAttachment(identity); this.privateEvent(owner, event);
          } else {
            this.model.stage(data); this.privateEvent(a.owner, { type: 'transfer', id: a.id, stage: data.stage, message: typeof data.message === 'string' ? data.message.slice(0, 200) : 'Agent reported progress.' });
          }
        } else if (data.type === 'resume') {
          if (data.id !== this.model.state.active?.id) throw new Error('Unknown resume.');
          identity.ready = false; identity.simulated = !!data.simulated; identity.requiresReceiver = !!data.requiresReceiver; ws.serializeAttachment(identity);
        } else throw new Error('Unsupported agent command.');
      } else {
        const id = identity.session;
        if (data.type === 'join') this.model.join(id, now, this.ids());
        else if (data.type === 'leave') this.model.leave(id, now, this.ids());
        else if (data.type === 'cancel') { this.model.cancel(id, data.id); if (this.agent()) send(this.agent(), { type: 'cancel', id: data.id }); }
        else if (data.type === 'submit') {
          const clean = validatePayload(data.payload); if (await payloadHash(clean) !== data.hash) throw new Error('Payload checksum mismatch.');
          const result = this.model.submit(id, data, now, this.online() && this.info().ready);
          if (result.duplicate) { send(ws, { type: 'transfer', id: data.id, stage: result.duplicate.stage, status: result.duplicate.status === 'confirmed' ? undefined : result.duplicate.status, message: 'Duplicate ignored; no physical resend.' }); }
          else {
            await this.save(); // Persist before any agent dispatch.
            this.privateEvent(id, { type: 'transfer', id: data.id, stage: 'uploaded', message: 'Bounded payload received by relay.' });
            this.model.state.active.stage = 'queued'; await this.save();
            this.privateEvent(id, { type: 'transfer', id: data.id, stage: 'queued', message: 'Queued for the laptop agent.' });
            send(this.agent(), { type: 'transfer', ...this.model.state.active });
          }
        } else throw new Error('Unsupported command.');
      }
      this.model.advance(now, this.ids()); await this.save(); this.roomEvent();
    } catch (error) { send(ws, { type: 'error', message: error.message || 'Invalid command.' }); }
  }
  async webSocketClose(ws) { await this.closed(ws); }
  async webSocketError(ws) { await this.closed(ws); }
  async closed(ws) {
    try { ws.close(1000, 'Connection closed'); } catch { /* already closed */ }
    this.receiverStatus();
    this.model.advance(Date.now(), this.ids()); await this.save(); this.roomEvent();
  }
  async alarm() {
    const now = Date.now();
    for (const ws of this.ctx.getWebSockets()) {
      const attachment = ws.deserializeAttachment();
      if ((attachment.role === 'viewer' && attachment.exp <= now) || (['agent', 'receiver'].includes(attachment.role) && now - attachment.seen > 15000)) ws.close(1008, 'Connection expired');
    }
    this.model.advance(now, this.ids());
    if (this.model.state.active?.cancelRequested && this.agent()) send(this.agent(), { type: 'cancel', id: this.model.state.active.id });
    const rates = await this.ctx.storage.list({ prefix: 'rate:', limit: 1000 });
    for (const [key, rate] of rates) if (now - rate.at > 600000) await this.ctx.storage.delete(key);
    await this.save(); this.roomEvent();
    if (!this.model.state.active && !this.model.state.controller && rates.size) await this.ctx.storage.setAlarm(now + 600000);
  }
}
