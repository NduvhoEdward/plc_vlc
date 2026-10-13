"""RX laptop: serial observations to relay and opt-in local presentation."""
import argparse, asyncio, json, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Internet of Light · Receiver</title>
<style>body{margin:0;background:#0b1720;color:#f5f2dc;font:18px system-ui}main{max-width:1050px;margin:5vh auto;padding:24px}h1{font-size:clamp(36px,6vw,74px);letter-spacing:-.05em}small{color:#eec56c}#stats{display:flex;gap:24px;flex-wrap:wrap}canvas{width:100%;image-rendering:pixelated;background:#fff4ba;max-height:55vh;object-fit:contain}#message{font-size:48px;overflow-wrap:anywhere}#result{border:1px solid #44606d;padding:24px;border-radius:20px;margin-top:32px}</style>
<main><small>PLC → POWERLINE → WI-FI → LIGHT → RECEIVER</small><h1>It arrived through light.</h1><p id="connection">Connecting…</p><div id="stats"></div><section id="result"><p id="caption">Waiting for a visitor to share a verified result.</p><p id="message" hidden></p><canvas id="picture" hidden></canvas></section></main>
<script>
const $=id=>document.getElementById(id);
async function update(){try{const r=await fetch('/state',{cache:'no-store'});const s=await r.json();
$('connection').textContent=s.connected?'Receiver relay connected':'Receiver relay disconnected';
$('stats').replaceChildren();for(const k of ['rate','good','crc','locked','overflows']){if(s.stats[k]!==undefined){const p=document.createElement('p');p.textContent=k+': '+s.stats[k];$('stats').append(p)}}
const p=s.result?.received;$('message').hidden=true;$('picture').hidden=true;
$('caption').textContent=p?'VERIFIED · '+(s.result.durationMs/1000).toFixed(1)+' seconds · opt-in shared result':'Waiting for a visitor to share a verified result.';
if(p?.kind==='text'){$('message').textContent=p.text;$('message').hidden=false}
if(p?.kind==='image'){const c=$('picture');c.width=p.width;c.height=p.height;const x=c.getContext('2d'),d=x.createImageData(c.width,c.height),b=atob(p.data);for(let i=0;i<c.width*c.height;i++){const v=b.charCodeAt(i>>3)&(128>>(i%8))?18:255;d.data.set([v,v,v,255],i*4)}x.putImageData(d,0,0);c.hidden=false}
}catch(e){$('connection').textContent='Receiver display unavailable'} }
update();setInterval(update,1000);
</script></html>"""

class Display:
    def __init__(self):
        self.lock=threading.Lock()
        self.state=dict(connected=False,stats={},result=None)
    def update(self,**changes):
        with self.lock:self.state.update(changes)
    def snapshot(self):
        with self.lock:return json.dumps(self.state).encode()

def serve(display,port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=='/state':body=display.snapshot();kind='application/json'
            elif self.path=='/':body=PAGE.encode();kind='text/html; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

class Receiver:
    def __init__(self,port,display):
        import serial
        self.port=serial.Serial(port=None,baudrate=115200,timeout=.05)
        self.port.dtr=False;self.port.rts=False;self.port.port=port;self.port.open()
        self.display=display;self.active=None;self.partial=b'';self.ws=None
        self.serial_lock=asyncio.Lock();self.stats={}
    async def send(self,data):
        if self.ws:await self.ws.send(json.dumps(data,separators=(',',':')))
    async def read(self):
        last_status=0
        while True:
            async with self.serial_lock:
                chunk=await asyncio.to_thread(self.port.read,min(4096,max(1,self.port.in_waiting)))
            lines=(self.partial+chunk).split(b'\n');self.partial=lines.pop()[-4096:]
            for raw in lines:
                line=raw.decode('ascii','replace').strip()
                if line.startswith('RX STAT '):
                    self.stats={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
                    self.display.update(stats=self.stats)
                elif line.startswith('RX message: ') and self.active:
                    record=line[12:]
                    if 1<=len(record)<=51:
                        await self.send(dict(type='rx-record',id=self.active,record=record))
            if time.monotonic()-last_status>1:
                async with self.serial_lock: await asyncio.to_thread(self.port.write,b'STAT\n')
                await self.send(dict(type='rx-stats',stats=self.stats))
                last_status=time.monotonic()
            await asyncio.sleep(.01)
    async def connect(self,url,secret):
        from websockets.asyncio.client import connect
        while True:
            try:
                async with connect(url,additional_headers={'Authorization':'Bearer '+secret},max_size=4096,ping_interval=20) as ws:
                    self.ws=ws;self.display.update(connected=True)
                    print('RX connected. Waiting for a visitor transfer.',flush=True)
                    task=asyncio.create_task(self.read())
                    try:
                        while True:
                            if task.done():
                                await task
                                raise RuntimeError("RX reader stopped")
                            try: message=await asyncio.wait_for(ws.recv(),timeout=2)
                            except asyncio.TimeoutError: continue
                            data=json.loads(message)
                            if data.get('type')=='arm':
                                async with self.serial_lock:
                                    await asyncio.to_thread(self.port.reset_input_buffer)
                                    self.partial=b'';self.active=data['id']
                                await self.send(dict(type='receiver-armed',id=self.active))
                            elif data.get('type')=='shared-result':
                                self.display.update(result=data)
                                self.active=None
                            elif data.get('type')=='disarm':self.active=None
                            elif data.get('type')=='error':print('Relay:',data.get('message'),flush=True)
                    finally:
                        task.cancel();await asyncio.gather(task,return_exceptions=True)
                        self.ws=None;self.active=None;self.display.update(connected=False)
            except asyncio.CancelledError:raise
            except Exception as error:print('RX reconnecting:',type(error).__name__,flush=True)
            await asyncio.sleep(2)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rx-port',required=True);parser.add_argument('--display-port',type=int,default=8765)
    args=parser.parse_args()
    url=os.environ.get('IOL_RECEIVER_URL','');secret=os.environ.get('IOL_RECEIVER_TOKEN','')
    if not url.startswith('wss://') or urlparse(url).path!='/receiver' or not secret:
        parser.error('Set IOL_RECEIVER_URL=wss://.../receiver and IOL_RECEIVER_TOKEN')
    display=Display();server=serve(display,args.display_port);receiver=Receiver(args.rx_port,display)
    print('Presentation: http://127.0.0.1:'+str(args.display_port),flush=True)
    try:asyncio.run(receiver.connect(url,secret))
    except KeyboardInterrupt:pass
    finally:receiver.port.close();server.shutdown()

if __name__=='__main__':main()
