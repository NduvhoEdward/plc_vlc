"""Start one demonstration bridge using its private credential file."""
import argparse, json, os, runpy, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if (ROOT/'.python-deps').exists():sys.path.insert(0,str(ROOT/'.python-deps'))
sys.path.insert(0,str(ROOT/'agent'))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('role',choices=['sender','receiver'])
parser.add_argument('--plc-host',default='192.168.0.100')
parser.add_argument('--optical-rate',type=int,default=280000)
parser.add_argument('--rx-port',default='COM10')
args=parser.parse_args()
credential=json.loads(ROOT.joinpath(args.role+'-credentials.json').read_text())
url=credential['relayUrl'].replace('https://','wss://',1)
print('Starting '+args.role+' bridge. PID='+str(os.getpid()),flush=True)
if args.role=='sender':
    os.environ['IOL_AGENT_URL']=url+'/agent';os.environ['IOL_AGENT_TOKEN']=credential['token']
    sys.argv=['agent.py','--network-tx','--plc-host',args.plc_host,'--optical-rate',str(args.optical_rate)]
    runpy.run_path(str(ROOT/'agent'/'agent.py'),run_name='__main__')
else:
    os.environ['IOL_RECEIVER_URL']=url+'/receiver';os.environ['IOL_RECEIVER_TOKEN']=credential['token']
    sys.argv=['receiver.py','--rx-port',args.rx_port]
    runpy.run_path(str(ROOT/'agent'/'receiver.py'),run_name='__main__')
