"""Interactive launcher for the sender or receiver laptop."""
import getpass, os, runpy, sys
from pathlib import Path
from urllib.parse import urlparse
root=Path(__file__).resolve().parent
if (root/'.python-deps').exists():sys.path.insert(0,str(root/'.python-deps'))
sys.path.insert(0,str(root/'agent'))
role=input('Role [sender/receiver]: ').strip().lower()
import json
credential_path=root/(role+'-credentials.json')
credential=json.loads(credential_path.read_text()) if credential_path.exists() else {}
base=credential.get('relayUrl') or input('Relay base URL (https://...workers.dev): ').strip().rstrip('/')
if urlparse(base).scheme!='https' or not urlparse(base).hostname:
    raise SystemExit('Expected an HTTPS relay URL.')
if role=='sender':
    os.environ['IOL_AGENT_URL']=base.replace('https://','wss://',1)+'/agent'
    os.environ['IOL_AGENT_TOKEN']=credential.get('token') or getpass.getpass('Sender token: ')
    host=input('TX IP [192.168.0.100]: ').strip() or '192.168.0.100'
    rate=input('Current optical rate [280000]: ').strip() or '280000'
    sys.argv=['agent.py','--network-tx','--plc-host',host,'--optical-rate',rate]
    runpy.run_path(str(root/'agent'/'agent.py'),run_name='__main__')
elif role=='receiver':
    os.environ['IOL_RECEIVER_URL']=base.replace('https://','wss://',1)+'/receiver'
    os.environ['IOL_RECEIVER_TOKEN']=credential.get('token') or getpass.getpass('Receiver token: ')
    port=input('RX serial port [COM10]: ').strip() or 'COM10'
    sys.argv=['receiver.py','--rx-port',port]
    runpy.run_path(str(root/'agent'/'receiver.py'),run_name='__main__')
else:raise SystemExit('Choose sender or receiver.')
