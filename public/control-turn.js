export function formatControlTurn(room, session, now = Date.now()) {
  if (!room || !session) return 'Not in queue';
  if (room.controller === session) {
    return room.active ? 'Transfer in progress' : Math.max(0, Math.ceil((room.leaseUntil - now) / 1000)) + ' s remaining';
  }
  const position = (room.queue || []).indexOf(session);
  return position >= 0 ? 'Queue position ' + (position + 1) : 'Not in queue';
}
