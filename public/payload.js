export function packPixels(pixels, width, height) {
  if (![32, 64, 128].includes(width) || height !== width / 2 || pixels.length !== width * height) throw new Error('Unsupported image dimensions.');
  const bytes = new Uint8Array(Math.ceil(pixels.length / 8));
  pixels.forEach((black, i) => { if (black) bytes[i >> 3] |= 128 >> (i & 7); });
  return { kind: 'image', width, height, data: btoa(String.fromCharCode(...bytes)) };
}
export function unpackPixels(payload) {
  const bytes = Uint8Array.from(atob(payload.data), c => c.charCodeAt(0));
  return Array.from({ length: payload.width * payload.height }, (_, i) => !!(bytes[i >> 3] & (128 >> (i & 7))));
}
export function validatePayload(p) {
  if (!p || typeof p !== 'object') throw new Error('Invalid payload.');
  if (p.kind === 'text') {
    if (typeof p.text !== 'string' || !/^[\x20-\x7e]{1,30}$/.test(p.text)) throw new Error('Use 1–30 printable ASCII characters.');
    return { kind: 'text', text: p.text };
  }
  if (p.kind !== 'image' || ![32, 64, 128].includes(p.width) || p.height !== p.width / 2 || typeof p.data !== 'string') throw new Error('Invalid image dimensions.');
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(p.data) || p.data.length > 1368) throw new Error('Invalid packed image.');
  let decoded;
  try { decoded = atob(p.data); } catch { throw new Error('Invalid image encoding.'); }
  if (decoded.length !== p.width * p.height / 8 || btoa(decoded) !== p.data) throw new Error('Image size or encoding mismatch.');
  return { kind: 'image', width: p.width, height: p.height, data: p.data };
}
export function canonical(p) { return JSON.stringify(validatePayload(p)); }
export async function payloadHash(p) {
  const bytes = new TextEncoder().encode(canonical(p));
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
}
