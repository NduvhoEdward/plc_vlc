const LEGACY_HOST = 'plc-vlc.pages.dev';
const PRIMARY_ORIGIN = 'https://hpv.selah.net.za';

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname === LEGACY_HOST && ['GET', 'HEAD'].includes(context.request.method)) {
    return new Response(null, {
      status: 302,
      headers: { Location: PRIMARY_ORIGIN + url.pathname + url.search, 'Cache-Control': 'no-store' },
    });
  }
  return context.next();
}
