"""Portable two-PC launcher. Never requires a system Python or pip install."""
import argparse, json, os, signal, socket, subprocess, sys, threading, time, webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'deps'))
sys.path.insert(0,str(ROOT/'agent'))
STATE={'role':'','status':'Starting','lines':[]}
STATE_LOCK=threading.Lock()
CHILD=None
DASHBOARD=None
SHUTDOWN=threading.Event()
PAGE=r"""<!doctype html><meta charset="utf-8"><title>Internet of Light | Bridge</title>
<style>body{font:18px system-ui;background:#eff4f8;color:#16202e;max-width:1000px;margin:40px auto;padding:20px}h1{font-size:42px}pre{white-space:pre-wrap;background:#16202e;color:#d4ecdf;padding:24px;border-radius:12px}a{color:#186780}</style>
<h1>Internet of Light</h1><h2 id="role"></h2><p id="status">Starting...</p>
<p><a href="https://plc-vlc.pages.dev/send" target="_blank">Open visitor studio</a> · <a href="http://127.0.0.1:8765" target="_blank">Receiver presentation</a></p>
<p>Keep the launcher window open. Press Ctrl+C there to stop.</p><pre id="logs"></pre>
<script>async function update(){try{const s=await(await fetch('/state',{cache:'no-store'})).json();document.getElementById('role').textContent=s.role+' PC';document.getElementById('status').textContent=s.status;document.getElementById('logs').textContent=s.lines.join('\n')}catch{document.getElementById('status').textContent='Launcher stopped'}}update();setInterval(update,1000)</script>"""
def log(message):
    line=time.strftime('%H:%M:%S')+' '+str(message)
    print(line,flush=True)
    with STATE_LOCK: STATE['lines']=(STATE['lines']+[line])[-60:]
    with (ROOT/'logs'/'launcher.log').open('a',encoding='utf-8') as f:f.write(line+'\n')
def status(message):
    with STATE_LOCK: STATE['status']=message
    log(message)
def server(port):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path!='/stop' or self.headers.get('X-IOL-Stop')!='1':
                self.send_error(403);return
            SHUTDOWN.set()
            threading.Thread(target=stop_child,daemon=True).start()
            self.send_response(200);self.end_headers();self.wfile.write(b'Stopping bridge')
        def do_GET(self):
            if self.path=='/state':
                with STATE_LOCK:body=json.dumps(STATE).encode()
                kind='application/json'
            elif self.path=='/':body=PAGE.encode();kind='text/html; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    return http
def serial_ports():
    from serial.tools.list_ports import comports
    return sorted(comports(),key=lambda p:p.device)
def probe_rx(port, seconds=2):
    import serial
    try:
        with serial.Serial(port=None,baudrate=115200,timeout=.15) as s:
            s.dtr=False;s.rts=False;s.port=port;s.open();s.write(b'STAT\n')
            deadline=time.monotonic()+seconds;data=b''
            while time.monotonic()<deadline:
                data=(data+s.read(max(1,min(4096,s.in_waiting))))[-8192:]
                if b'RX STAT ' in data:return True
    except (serial.SerialException,OSError):return False
    return False
def find_rx(preferred='auto'):
    ports=serial_ports()
    if preferred!='auto':
        return preferred if probe_rx(preferred) else None
    # Probe USB devices only. A TX USB responds differently and is never selected.
    for p in ports:
        if p.vid is not None and probe_rx(p.device):return p.device
    return None
def probe_tx(host):
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.settimeout(1);s.connect((host,5000));s.send(b'VLC_STATUS SUBSCRIBE')
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                if b'VLC BUFFER ' in s.recv(2048):return True
    except OSError:pass
    return False
def relay_available(url):
    from urllib.parse import urlparse
    import ssl
    host=urlparse(url).hostname
    try:
        with socket.create_connection((host,443),timeout=8) as tcp:
            with ssl.create_default_context().wrap_socket(tcp,server_hostname=host):return True
    except OSError:return False
def self_check():
    import serial, websockets, sqlite3, ssl
    from pixel_protocol import Picture
    from websockets.asyncio.client import connect
    with sqlite3.connect(':memory:') as db:db.execute('select 1')
    ssl.create_default_context()
    print('PASS: portable Python, serial, WebSockets, TLS, SQLite, optical protocol.')
def stop_child():
    global CHILD
    if CHILD and CHILD.poll() is None:
        try:
            if os.name=='nt':CHILD.send_signal(signal.CTRL_BREAK_EVENT)
            else:CHILD.send_signal(signal.SIGINT)
            CHILD.wait(timeout=8)
        except (OSError,subprocess.TimeoutExpired):
            CHILD.terminate()
            try:CHILD.wait(timeout=3)
            except subprocess.TimeoutExpired:CHILD.kill();CHILD.wait()
    CHILD=None
def open_original_dashboard():
    global DASHBOARD
    if DASHBOARD is not None and DASHBOARD.poll() is None:return
    gui_env=os.environ.copy()
    gui_env['TCL_LIBRARY']=str(ROOT/'gui-runtime'/'tcl'/'tcl8.6')
    gui_env['TK_LIBRARY']=str(ROOT/'gui-runtime'/'tcl'/'tk8.6')
    with (ROOT/'logs'/'dashboard.log').open('a',encoding='utf-8') as gui_log:
        DASHBOARD=subprocess.Popen([str(ROOT/'gui-runtime'/'pythonw.exe'),str(ROOT/'dashboard'/'mobile_receiver_dashboard.py')],cwd=ROOT/'dashboard',env=gui_env,stdout=gui_log,stderr=gui_log)
    log('Original VLC Pixel Studio opened. It observes the bridge without opening RX USB.')

def bridge(role,cfg,cred,port=None):
    global CHILD,DASHBOARD
    env=os.environ.copy()
    url=cred['relayUrl'].replace('https://','wss://',1)
    if role=='sender':
        env.update(IOL_AGENT_URL=url+'/agent',IOL_AGENT_TOKEN=cred['token'])
        args=[str(ROOT/'agent'/'agent.py'),'--network-tx','--plc-host',cfg['plc_host'],'--optical-rate',str(cfg['optical_rate'])]
    else:
        env.update(IOL_RECEIVER_URL=url+'/receiver',IOL_RECEIVER_TOKEN=cred['token'])
        args=[str(ROOT/'agent'/'receiver.py'),'--rx-port',port,'--display-port',str(cfg['display_port'])]
    flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
    CHILD=subprocess.Popen([sys.executable,'-u',*args],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=flags)
    opened=False
    for line in CHILD.stdout:
        safe=line.rstrip().replace(cred['token'],'[redacted]')
        log(safe)
        if 'reconnecting:' in line or 'Connection unavailable:' in line:
            with STATE_LOCK:STATE['status']='Connection interrupted; reconnecting'
        if role=='receiver' and any(name in line for name in ('SerialException','PermissionError','OSError')):
            status('Receiver USB interrupted. Restarting with automatic port detection.')
            stop_child();break
        if 'RX connected.' in line or 'Connected to relay.' in line or 'Relay connected' in line:
            with STATE_LOCK:STATE['status']='Connected to relay'
        if role=='receiver' and 'Presentation:' in line and not opened:
            if cfg.get('receiver_dashboard')=='original':open_original_dashboard()
            else:webbrowser.open('http://127.0.0.1:'+str(cfg['display_port']))
            opened=True
    return CHILD.wait() if CHILD else 1
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-check',action='store_true');parser.add_argument('--check-hardware',action='store_true')
    args=parser.parse_args()
    if args.self_check:self_check();return
    cfg=json.loads((ROOT/'settings.json').read_text());role=cfg['role'];STATE['role']=role.title()
    if args.check_hardware:
        okay=probe_tx(cfg['plc_host']) if role=='sender' else find_rx(cfg['rx_port'])
        print('Hardware detected:',okay);raise SystemExit(0 if okay else 2)
    (ROOT/'logs').mkdir(exist_ok=True)
    # Windows releases the lock even if the launcher is forcibly closed.
    import msvcrt
    lock=(ROOT/'.running.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit('This package is already running. Use its existing launcher window.')
    cred=json.loads((ROOT/(role+'-credentials.json')).read_text())
    self_check()
    network_checked=False
    http=server(cfg['launcher_port'])
    if role=='receiver' and cfg.get('receiver_dashboard')=='original':open_original_dashboard()
    else:webbrowser.open('http://127.0.0.1:'+str(cfg['launcher_port']))
    status('Keep this window open. Ctrl+C stops this bridge.')
    try:
        while not SHUTDOWN.is_set():
            if not relay_available(cred['relayUrl']):
                status('Waiting for internet / Cloudflare. Connect this PC to internet; retrying in 5 seconds.');time.sleep(5);continue
            port=None
            if role=='sender':
                if not probe_tx(cfg['plc_host']):
                    if not network_checked and os.name=='nt':
                        network_checked=True
                        status('Checking Ethernet configuration for the HomePlug subnet...')
                        subprocess.run(['powershell.exe','-NoProfile','-File',str(ROOT/'configure_ethernet.ps1')],check=False)
                        if probe_tx(cfg['plc_host']):continue
                    status('Waiting for TX at '+cfg['plc_host']+'. Connect Ethernet to HomePlug, power TX, and check HomePlug Wi-Fi. Ethernet must reach 192.168.0.x. Retrying in 5 seconds.');time.sleep(5);continue
            else:
                port=find_rx(cfg['rx_port'])
                if not port:
                    choices=', '.join(p.device+' '+p.description for p in serial_ports()) or 'none'
                    status('Waiting for RX USB. Close Serial Monitor / other bridge windows. Detected ports: '+choices+'. Retrying in 5 seconds.');time.sleep(5);continue
                status('RX identified on '+port)
            status('Starting '+role+' bridge. Hardware detected.')
            code=bridge(role,cfg,cred,port)
            stop_child()
            status('Bridge exited ('+str(code)+'). Checking hardware and restarting in 5 seconds.');time.sleep(5)
    except KeyboardInterrupt:status('Stopping this bridge...')
    finally:
        stop_child()
        if DASHBOARD is not None and DASHBOARD.poll() is None:DASHBOARD.terminate()
        http.shutdown();lock.close()
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:stop_child()
    except Exception as e:
        stop_child();print('Launcher error:',type(e).__name__,str(e));sys.exit(1)
