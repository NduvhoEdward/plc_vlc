const encoder = new TextEncoder();
const b64url = bytes => btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
const decode = s => Uint8Array.from(atob(s.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - s.length % 4) % 4)), c => c.charCodeAt(0));
async function key(secret) { return crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']); }
export async function signSession(session, secret, now = Date.now()) {
  const body = b64url(encoder.encode(JSON.stringify({ session, exp: now + 3600000 })));
  return `${body}.${b64url(new Uint8Array(await crypto.subtle.sign('HMAC', await key(secret), encoder.encode(body))))}`;
}
export async function verifySession(token, secret, now = Date.now()) {
  try {
    if (!secret || !token || token.length > 512) return null;
    const [body, signature, extra] = token.split('.'); if (extra || !body || !signature) return null;
    if (!await crypto.subtle.verify('HMAC', await key(secret), decode(signature), encoder.encode(body))) return null;
    const data = JSON.parse(new TextDecoder().decode(decode(body)));
    if (!/^[0-9a-f-]{36}$/.test(data.session) || data.exp <= now || data.exp > now + 3600000) return null;
    return data;
  } catch { return null; }
}
export async function equalSecret(a, b) {
  if (typeof a !== 'string' || !b) return false;
  const [aa, bb] = await Promise.all([a, b].map(s => crypto.subtle.digest('SHA-256', encoder.encode(s))));
  const x = new Uint8Array(aa), y = new Uint8Array(bb); let different = 0;
  for (let i = 0; i < x.length; i++) different |= x[i] ^ y[i]; return different === 0;
}
export async function boundedJSON(request, limit = 4096) {
  if (!request.body) throw new Error('Missing request body.');
  const reader = request.body.getReader(); let size = 0, chunks = [];
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    size += value.length; if (size > limit) { await reader.cancel(); throw new Error('Payload is too large.'); } chunks.push(value);
  }
  const all = new Uint8Array(size); let offset = 0; for (const part of chunks) { all.set(part, offset); offset += part.length; }
  return JSON.parse(new TextDecoder().decode(all));
}
