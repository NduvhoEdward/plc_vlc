import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { localD1 } from './tests/d1-local.js';
import { onRequest } from './functions/api/game.js';
const gameDB = localD1();
const root = resolve(import.meta.dirname, 'public');
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.csv': 'text/csv; charset=utf-8', '.md': 'text/plain; charset=utf-8' };
const server = http.createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (pathname === '/api/game') {
      const chunks=[];for await (const chunk of request) chunks.push(chunk);
      const body=Buffer.concat(chunks);
      const apiRequest=new Request('http://127.0.0.1:4173/api/game',{method:request.method,headers:request.headers,...(body.length?{body}: {})});
      const result=await onRequest({request:apiRequest,env:{GAME_DB:gameDB}});
      response.writeHead(result.status,Object.fromEntries(result.headers));response.end(await result.text());return;
    }
    let file = resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(root + sep)) throw new Error('Outside root');
    if (!(await stat(file)).isFile()) throw new Error('Not found');
    response.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream', 'X-Content-Type-Options': 'nosniff' });
    response.end(await readFile(file));
  } catch { response.writeHead(404); response.end('Not found'); }
});
server.listen(4173, '127.0.0.1', () => console.log('Local preview: http://127.0.0.1:4173'));
