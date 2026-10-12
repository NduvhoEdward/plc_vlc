import test from 'node:test';
import assert from 'node:assert/strict';
import { RoomModel } from '../relay/room-model.js';
import { validatePayload, payloadHash } from '../public/payload.js';
import { signSession, verifySession, boundedJSON } from '../relay/auth.js';
import worker, { RigRoom } from '../relay/worker.js';
const id = '12345678-1234-1234-1234-123456789abc';
const payload = { kind: 'text', text: 'Hello' };
const hash = await payloadHash(payload);
test('one controller; busy transfer blocks lease expiry and viewer commands', () => {
  const m = new RoomModel(), ids = new Set(['a', 'b']);
  m.join('a', 100, ids); m.join('b', 100, ids);
  assert.equal(m.state.controller, 'a');
  assert.throws(() => m.submit('b', { id, hash, payload }, 200, true), /turn/);
  m.submit('a', { id, hash, payload }, 200, true); m.advance(70000, ids);
  assert.equal(m.state.controller, 'a'); assert.equal(m.state.active.id, id);
  assert.throws(() => m.leave('a', 70000, ids), /Cancel/);
  m.finish({ id, status: 'confirmed' }, 80000); m.advance(80000, ids);
  assert.equal(m.state.controller, 'b');
});
test('duplicate transfers do not dispatch; conflicting hash rejected', () => {
  const m = new RoomModel({ controller: 'a', leaseUntil: 60000 });
  m.submit('a', { id, hash, payload }, 200, true);
  assert.ok(m.submit('a', { id, hash, payload }, 300, true).duplicate);
  assert.throws(() => m.submit('a', { id, hash: '0'.repeat(64), payload }, 300, true), /Conflicting/);
});
test('disconnected active transfer remains locked and content expires', () => {
  const m = new RoomModel({ controller: 'a', leaseUntil: 60000 });
  m.submit('a', { id, hash, payload }, 200, true); m.advance(1000000, new Set(['b']));
  assert.equal(m.state.active.cancelRequested, true); assert.equal(m.state.active.payload, undefined);
  assert.equal(m.state.controller, 'a');
});
test('payload validation rejects oversized, unsupported, malformed data', () => {
  for (const invalid of [{ kind: 'text', text: 'a'.repeat(31) }, { kind: 'text', text: '<script>\n' }, { kind: 'text', text: '✓' }, { kind: 'image', width: 1000, height: 500, data: 'AA==' }, { kind: 'image', width: 32, height: 16, data: 'AA==' }]) assert.throws(() => validatePayload(invalid));
  const p = { kind: 'image', width: 128, height: 64, data: btoa('\0'.repeat(1024)) };
  assert.deepEqual(validatePayload(p), p);
});
test('session credentials reject tampering, wrong secret, expiry', async () => {
  const token = await signSession(id, 'test-secret', 1000);
  assert.equal((await verifySession(token, 'test-secret', 1001)).session, id);
  assert.equal(await verifySession(token + 'x', 'test-secret', 1001), null);
  assert.equal(await verifySession(token, 'wrong', 1001), null);
  assert.equal(await verifySession(token, 'test-secret', 3601001), null);
});
test('HTTP body limit works without Content-Length', async () => {
  const r = new Request('https://test/join', { method: 'POST', body: 'x'.repeat(5000) });
  await assert.rejects(() => boundedJSON(r), /large/);
});
test('Worker rejects foreign origins, expired sessions and invalid agent secrets', async () => {
  const env = { ALLOWED_ORIGIN: 'https://test.pages.dev', SESSION_SECRET: 's', AGENT_TOKEN: 'a', JOIN_PASSCODE: 'p', TURNSTILE_SECRET: 't' };
  assert.equal((await worker.fetch(new Request('https://relay/ws', { headers: { Origin: 'https://evil.test', Upgrade: 'websocket' } }), env)).status, 403);
  assert.equal((await worker.fetch(new Request('https://relay/ws', { headers: { Origin: env.ALLOWED_ORIGIN, Upgrade: 'websocket', 'Sec-WebSocket-Protocol': 'iol, bad' } }), env)).status, 401);
  assert.equal((await worker.fetch(new Request('https://relay/agent', { headers: { Upgrade: 'websocket', Authorization: 'Bearer wrong' } }), env)).status, 401);
});
class Socket {
  constructor(role, session) { this.readyState = 1; this.meta = { role, session, exp: Date.now() + 3600000, seen: Date.now(), ready: role === 'agent', window: Date.now(), count: 0 }; this.sent = []; }
  deserializeAttachment() { return structuredClone(this.meta); }
  serializeAttachment(a) { this.meta = structuredClone(a); }
  send(value) { this.sent.push(JSON.parse(value)); }
  close() { this.readyState = 3; }
}
async function setup() {
  const sockets = [new Socket('viewer', 'a'), new Socket('viewer', 'b'), new Socket('agent')], values = new Map();
  const ctx = { getWebSockets: tag => sockets.filter(s => !tag || s.meta.role === tag), storage: { get: async key => values.get(key), put: async (key, value) => values.set(key, structuredClone(value)), getAlarm: async () => null, setAlarm: async () => {}, list: async () => new Map() }, blockConcurrencyWhile: fn => ctx.init = fn() };
  const room = new RigRoom(ctx, {}); await ctx.init;
  return { room, sockets, values };
}
test('authenticated viewer cannot submit unless controller; payload never broadcast', async () => {
  const { room, sockets: [a, b, agent] } = await setup();
  await room.webSocketMessage(a, JSON.stringify({ type: 'join' }));
  await room.webSocketMessage(b, JSON.stringify({ type: 'submit', id, hash, payload }));
  assert.equal(room.model.state.active, null);
  await room.webSocketMessage(a, JSON.stringify({ type: 'submit', id, hash, payload }));
  assert.equal(agent.sent.filter(s => s.type === 'transfer').length, 1);
  assert.ok(!JSON.stringify(b.sent).includes('Hello'));
  await room.webSocketMessage(a, JSON.stringify({ type: 'submit', id, hash, payload }));
  assert.equal(agent.sent.filter(s => s.type === 'transfer').length, 1);
});
test('confirmed result requires matching receiver hash AND idle hardware', async () => {
  const { room, sockets: [a, b, agent] } = await setup();
  await room.webSocketMessage(a, JSON.stringify({ type: 'join' })); await room.webSocketMessage(b, JSON.stringify({ type: 'join' }));
  await room.webSocketMessage(a, JSON.stringify({ type: 'submit', id, hash, payload }));
  await room.webSocketMessage(agent, JSON.stringify({ type: 'transfer', id, status: 'confirmed', received: payload, idle: false }));
  assert.ok(room.model.state.active);
  await room.webSocketMessage(agent, JSON.stringify({ type: 'transfer', id, status: 'confirmed', received: { kind: 'text', text: 'Wrong' }, idle: true }));
  assert.ok(room.model.state.active);
  await room.webSocketMessage(agent, JSON.stringify({ type: 'transfer', id, status: 'confirmed', received: payload, idle: true }));
  assert.equal(room.model.state.active, null); assert.equal(room.model.state.controller, 'b');
  assert.ok(a.sent.some(s => s.status === 'confirmed' && s.received?.text === 'Hello'));
  assert.ok(!b.sent.some(s => s.received));
});
test('session command rate limits and expiry are enforced', async () => {
  const { room, sockets: [a] } = await setup();
  a.meta.count = 30; await room.webSocketMessage(a, JSON.stringify({ type: 'join' }));
  assert.match(a.sent.at(-1).message, /rate/);
  a.meta.exp = 0; await room.webSocketMessage(a, JSON.stringify({ type: 'join' })); assert.equal(a.readyState, 3);
});
