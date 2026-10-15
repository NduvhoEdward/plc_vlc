export const canQueue = room => !!room?.online && (!!room.ready || !!room.active);
export class QueuedSend {
  constructor() { this.pending = null; }
  start(payload, options, id) {
    if (this.pending) return false;
    this.pending = { payload: structuredClone(payload), ...options, id, phase: 'waiting', joinSent: false };
    return true;
  }
  next(room, session) {
    const pending = this.pending;
    if (!pending || pending.phase === 'dispatched' || !room || !session) return null;
    if (!canQueue(room)) { this.pending = null; return { type: 'paused' }; }
    if (room.controller === session && !room.active && room.ready) {
      pending.phase = 'dispatched';
      return { type: 'submit', intent: pending };
    }
    pending.phase = 'queued';
    if ((room.queue || []).includes(session)) return null;
    if (!pending.joinSent) { pending.joinSent = true; return { type: 'join' }; }
    return null;
  }
  cancel() { const previous = this.pending; this.pending = null; return previous; }
  interrupted() {
    if (this.pending && this.pending.phase !== 'dispatched') { this.pending = null; return true; }
    return false;
  }
}
export function estimatedWait(room, session) {
  const position = room?.queue?.indexOf(session) ?? -1;
  if (position < 0) return 'Finding your place…';
  const ahead = position + 1;
  if (ahead === 1) return "You're next · about 30–60 sec";
  return ahead + ' ahead · about ' + Math.max(1, Math.round(ahead / 2)) + '–' + ahead + ' min';
}
