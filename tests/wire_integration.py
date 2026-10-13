"""15-viewer integration against local Cloudflare runtime, no hardware."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.python-deps'))
import asyncio, base64, hashlib, hmac, json, time, uuid
from websockets.asyncio.client import connect
def enc(data):return base64.urlsafe_b64encode(data).decode().rstrip('=')
def token(session):
    body=enc(json.dumps(dict(session=session,exp=int(time.time()*1000)+3500000),separators=(',',':')).encode())
    return body+'.'+enc(hmac.new(b'local-session-test',body.encode(),hashlib.sha256).digest())
async def read(ws,kind,predicate=lambda x:True):
    async with asyncio.timeout(15):
        while True:
            data=json.loads(await ws.recv())
            if data.get('type')=='error':raise RuntimeError(data['message'])
            if data.get('type')==kind and predicate(data):return data
async def send(ws,**data):await ws.send(json.dumps(data))
async def run():
    viewers=[]
    async with connect('ws://127.0.0.1:8787/receiver',additional_headers={'Authorization':'Bearer local-rx-test'}) as rx:
        async with connect('ws://127.0.0.1:8787/agent',additional_headers={'Authorization':'Bearer local-agent-test'}) as agent:
            await read(agent,'reconcile')
            await send(rx,type='rx-stats',stats=dict(rate=280000,good=0,crc=0,locked=1,overflows=0))
            await send(agent,type='ready',simulated=True,requiresReceiver=True)
            async def heartbeat():
                while True:
                    await send(rx,type='rx-stats',stats=dict(rate=280000))
                    await send(agent,type='telemetry',plc='simulated',vlc='simulated')
                    await asyncio.sleep(1)
            task=asyncio.create_task(heartbeat())
            try:
                ids=[str(uuid.uuid4()) for _ in range(15)]
                for identifier in ids:
                    ws=await connect('ws://127.0.0.1:8787/ws',origin='https://plc-vlc.pages.dev',subprotocols=['iol',token(identifier)])
                    viewers.append(ws);await send(ws,type='join')
                await read(viewers[0],'room',lambda x:x['controller']==ids[0])
                for owner,share in [(0,False),(1,True)]:
                    payload=dict(kind='text',text='Wire test '+str(owner))
                    digest=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
                    identifier=str(uuid.uuid4())
                    await send(viewers[owner],type='submit',id=identifier,hash=digest,payload=payload,shareDisplay=share)
                    cmd=await read(agent,'transfer',lambda x:x['id']==identifier)
                    await send(agent,type='arm-receiver',id=identifier)
                    await read(rx,'arm',lambda x:x['id']==identifier)
                    await send(rx,type='receiver-armed',id=identifier)
                    await read(agent,'receiver-armed',lambda x:x['id']==identifier)
                    await send(rx,type='rx-record',id=identifier,record='Actual RX observation')
                    got=await read(agent,'rx-record',lambda x:x['id']==identifier)
                    assert got['record']=='Actual RX observation'
                    await send(agent,type='transfer',id=identifier,status='confirmed',received=payload,idle=True)
                    done=await read(viewers[owner],'transfer',lambda x:x.get('status')=='confirmed')
                    assert done['received']==payload
                    if share:
                        shared=await read(viewers[14],'shared-result')
                        assert shared['received']==payload
                        await read(rx,'shared-result')
                    await read(rx,'disarm',lambda x:x['id']==identifier)
                    await read(viewers[owner+1],'room',lambda x:x['controller']==ids[owner+1])
                print('PASS: 15 viewer sockets, separate receiver handshake, private RX observations, verified results and consent sharing.',flush=True)
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                for ws in viewers:await ws.close()
asyncio.run(run())
