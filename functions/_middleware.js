const LEGACY_HOSTS = new Set(['plc-vlc.pages.dev', 'hpv.selah.net.za']);
const PRIMARY_ORIGIN = 'https://lightlink.selah.net.za';

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (LEGACY_HOSTS.has(url.hostname) && ['GET', 'HEAD'].includes(context.request.method)) {
    return new Response(null, {
      status: 302,
      headers: { Location: PRIMARY_ORIGIN + url.pathname + url.search, 'Cache-Control': 'no-store' },
    });
  }
  return context.next();
}
