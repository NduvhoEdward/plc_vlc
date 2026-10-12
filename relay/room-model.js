import { validatePayload } from '../public/payload.js';
export const FINAL = ['confirmed', 'failed', 'cancelled'];
export const STAGES = ['uploaded', 'queued', 'accepted', 'plc', 'vlc', 'confirmed'];
export class RoomModel {
  constructor(state = {}) {
    this.state = { queue: [], controller: null, leaseUntil: 0, active: null, recent: [], ...state };
  }
  advance(now, connected) {
    const s = this.state;
    s.queue = s.queue.filter(id => connected.has(id));
    s.recent = s.recent.filter(t => now - t.finished < 3600000).slice(-32);
    if (!s.active && (!connected.has(s.controller) || now >= s.leaseUntil)) { s.controller = null; s.leaseUntil = 0; }
    if (!s.controller && !s.active && s.queue.length) { s.controller = s.queue.shift(); s.leaseUntil = now + 60000; }
    if (s.active && now - s.active.started > 180000) s.active.cancelRequested = true;
    // Expire content even if the disconnected rig cannot yet acknowledge that it stopped.
    if (s.active && now - s.active.started > 900000) delete s.active.payload;
  }
  join(id, now, connected) {
    this.advance(now, connected);
    if (id !== this.state.controller && !this.state.queue.includes(id)) {
      if (this.state.queue.length >= 30) throw new Error('The queue is full. Try again shortly.');
      this.state.queue.push(id);
    }
    this.advance(now, connected);
  }
  leave(id, now, connected) {
    if (this.state.active?.owner === id) throw new Error('Cancel the active transfer and wait for the agent to stop before releasing control.');
    this.state.queue = this.state.queue.filter(s => s !== id);
    if (this.state.controller === id) { this.state.controller = null; this.state.leaseUntil = 0; }
    this.advance(now, connected);
  }
  submit(owner, data, now, online) {
    const s = this.state;
    if (!online) throw new Error('Rig offline or reconciling.');
    if (s.controller !== owner || (!s.active && now >= s.leaseUntil)) throw new Error('Wait for your control turn.');
    if (!/^[0-9a-f-]{36}$/.test(data.id || '') || !/^[0-9a-f]{64}$/.test(data.hash || '')) throw new Error('Invalid transfer identifier.');
    const previous = s.active?.id === data.id ? s.active : s.recent.find(t => t.id === data.id);
    if (previous) {
      if (previous.owner !== owner || previous.hash !== data.hash) throw new Error('Conflicting duplicate transfer.');
      return { duplicate: previous };
    }
    if (s.active) throw new Error('The rig is busy.');
    const payload = validatePayload(data.payload);
    s.active = { id: data.id, owner, hash: data.hash, payload, stage: 'uploaded', started: now, cancelRequested: false };
    return { active: s.active };
  }
  stage(data) {
    const a = this.state.active;
    if (!a || data.id !== a.id) throw new Error('Unknown transfer.');
    const next = STAGES.indexOf(data.stage), current = STAGES.indexOf(a.stage);
    if (next < 0 || next < current) throw new Error('Invalid transfer stage.');
    a.stage = data.stage;
  }
  finish(data, now) {
    const s = this.state, a = s.active;
    if (!a || a.id !== data.id || !FINAL.includes(data.status)) throw new Error('Invalid completion.');
    const record = { id: a.id, owner: a.owner, hash: a.hash, status: data.status, finished: now };
    s.recent.push(record); s.recent = s.recent.slice(-32); s.active = null;
    // A completed/cancelled transfer ends that turn; a queued visitor gets the next turn.
    s.controller = null; s.leaseUntil = 0;
    return record;
  }
  cancel(owner, id) {
    if (!this.state.active || this.state.active.id !== id || this.state.active.owner !== owner) throw new Error('You do not own this transfer.');
    this.state.active.cancelRequested = true;
  }
}
