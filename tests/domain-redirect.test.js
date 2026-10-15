import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest } from '../functions/_middleware.js';

test('legacy links redirect to custom domain preserving path and query', async () => {
  for (const method of ['GET', 'HEAD']) {
   for (const host of ['plc-vlc.pages.dev', 'hpv.selah.net.za']) {
    const response = await onRequest({ request: new Request(`https://${host}/send?from=qr`, { method }), next: () => { throw new Error('Unexpected asset request'); } });
    assert.equal(response.status, 302);
    assert.equal(response.headers.get('Location'), 'https://lightlink.selah.net.za/send?from=qr');
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
   }
  }
});
test('custom domain, previews and API submissions are not redirected', async () => {
  for (const [url, method] of [['https://lightlink.selah.net.za/send', 'GET'], ['https://preview.plc-vlc.pages.dev/', 'GET'], ['https://plc-vlc.pages.dev/api/game', 'POST'], ['https://hpv.selah.net.za/api/game', 'POST']]) {
    let nextCalled = false;
    const response = await onRequest({ request: new Request(url, { method }), next: () => { nextCalled = true; return new Response('unchanged'); } });
    assert.equal(nextCalled, true); assert.equal(await response.text(), 'unchanged');
  }
});
