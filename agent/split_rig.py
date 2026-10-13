"""Network-only transmitter with AUTO priming and remote RX feedback."""
import asyncio, base64, re, socket, time
from agent import clean_payload, records_for
from pixel_protocol import ImageAssembler

def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)', line))

class AutoPacer:
    def __init__(self, records, rate=300000):
        self.records=records; self.dwell=max(8,(rate+1599)//1600)
        self.cursor=self.sent=0
    def batch(self,count,acked):
        missing=[i for i in range(len(self.records)) if i not in acked]
        if not missing:return b''
        if self.cursor not in missing:
            self.cursor=next((i for i in missing if i>=self.cursor),missing[0]);self.sent=0
        number=min(count,self.dwell-self.sent)
        result=self.records[self.cursor].ljust(51).encode('ascii')*number
        self.sent+=number
        if self.sent>=self.dwell:self.cursor=(self.cursor+1)%len(self.records);self.sent=0
        return result

class NetworkRig:
    simulated=False
    split=True
    def __init__(self,args):
        if not args.plc_host:raise ValueError('--plc-host is required')
        self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.udp.connect((args.plc_host,5000));self.udp.settimeout(.1)
        self.rate=args.optical_rate;self.buffer={};self.buffer_at=0;self.reader=None
        self.observations=asyncio.Queue(maxsize=256)
        self.receiver_online=False;self.receiver_armed=None;self.emit=None;self.active=None
        self.owned=False;self.drain_record=None;self.last_send=0;self.last_admitted=0;self.rejection=None
        self.rx_stats={};self.last_rx=0;self.latency=self.throughput=None
    async def start(self):
        if self.reader is None:self.reader=asyncio.create_task(self.read_udp())
    async def read_udp(self):
        subscribed=0
        while True:
            if time.monotonic()-subscribed>1:
                try:
                    await asyncio.to_thread(self.udp.send,b'VLC_STATUS SUBSCRIBE');subscribed=time.monotonic()
                except OSError:
                    self.buffer_at=0;await asyncio.sleep(.2);continue
            try:packet=await asyncio.to_thread(self.udp.recv,2048)
            except socket.timeout:continue
            except OSError:self.buffer_at=0;await asyncio.sleep(.2);continue
            for line in packet.decode('ascii','replace').splitlines():
                if line.startswith('VLC BUFFER '):
                    data=fields(line);keys=('used','capacity','inflight','streaming','threshold_pct')
                    if all(data.get(k,'').isdigit() for k in keys):
                        values={k:int(data[k]) for k in keys}
                        if 0<=values['used']<=values['capacity'] and values['capacity']>0 and 0<=values['threshold_pct']<=99:
                            self.buffer=values;self.buffer_at=time.monotonic()
                elif line.startswith('QUEUED '):
                    self.last_admitted=time.monotonic()
                    data=fields(line)
                    if data.get('used','').isdigit() and self.buffer:
                        self.buffer['used']=max(self.buffer['used'],int(data['used']))
                elif line.startswith('REJECT ') and 'buffer_full' not in line:self.rejection=line[:160]
    def fresh(self):return time.monotonic()-self.buffer_at<3
    def is_idle(self):
        return self.fresh() and self.buffer['used']==0 and self.buffer['inflight']==0 and time.monotonic()-self.last_send>1
    async def ensure_idle(self):
        await self.start()
        for _ in range(100):
            if self.is_idle():self.owned=False;return True
            # A cancelled transfer below the AUTO gate must be primed with its
            # own duplicates to drain. Never fill another producer's queue.
            if self.owned and self.drain_record and self.fresh() and self.buffer['used']>0 and not self.buffer['streaming']:
                target=(self.buffer['capacity']*self.buffer['threshold_pct']+99)//100
                count=min(24,max(0,(target-self.buffer['used']+51)//52),(self.buffer['capacity']-self.buffer['used'])//52)
                if count:await self.send_batch(self.drain_record.ljust(51).encode('ascii')*count)
            await asyncio.sleep(.1)
        return False
    async def send_batch(self,batch):
        if not batch or not self.fresh():return
        await asyncio.to_thread(self.udp.send,batch);self.last_send=time.monotonic()
        self.buffer['used']=min(self.buffer['capacity'],self.buffer['used']+len(batch)//51*52)
    def observe(self,data):
        if data.get('type')=='receiver-status':self.receiver_online=bool(data.get('online'))
        elif data.get('type')=='receiver-armed':self.receiver_armed=data.get('id')
        elif data.get('type')=='rx-stats':self.rx_stats=data.get('stats',{});self.last_rx=time.monotonic()
        elif data.get('type')=='rx-record' and data.get('id')==self.active:
            try:self.observations.put_nowait(data['record'])
            except asyncio.QueueFull:pass
    async def telemetry(self):
        data=dict(plc='online' if self.fresh() else 'offline',vlc='online' if self.receiver_online and time.monotonic()-self.last_rx<5 else 'unknown')
        if self.fresh():
            data.update(bufferUsed=self.buffer['used'],bufferCapacity=self.buffer['capacity'],
                bufferPercent=round(self.buffer['used']*100/self.buffer['capacity'],1),streaming=self.buffer['streaming'],
                inflight=self.buffer['inflight'],threshold=self.buffer['threshold_pct'])
        for key in ('rate','good','crc','locked','overflows'):
            if isinstance(self.rx_stats.get(key),int):data['rx'+key.capitalize()]=self.rx_stats[key]
        if self.latency is not None:data.update(latency=round(self.latency,1),throughput=round(self.throughput,3))
        return data
    async def transfer(self,data,cancel,report):
        if not await self.ensure_idle():raise RuntimeError('TX not idle or UDP feedback unavailable.')
        if not self.receiver_online:raise RuntimeError('Receiving laptop offline.')
        self.active=data['id'];self.receiver_armed=None
        while not self.observations.empty():self.observations.get_nowait()
        await self.emit(dict(type='arm-receiver',id=self.active))
        for _ in range(100):
            if self.receiver_armed==self.active:break
            await asyncio.sleep(.05)
        else:raise RuntimeError('Receiver did not arm; nothing sent.')
        records,picture=records_for(data['payload'],data['id'])
        pacer=AutoPacer(records,self.rate);assembler=ImageAssembler();acked=set();received=None
        started=time.monotonic();self.owned=True;self.drain_record=records[0];self.rejection=None
        reported_plc=reported_vlc=False;status='failed';message='Receiver timeout; incomplete payload.'
        try:
            while time.monotonic()-started<150:
                if cancel.is_set():status='cancelled';message='Cancelled; queued duplicates drained.';break
                if self.rejection:raise RuntimeError(self.rejection)
                if not self.receiver_online:raise RuntimeError('RX laptop disconnected; production stopped.')
                while not self.observations.empty():
                    record=self.observations.get_nowait().rstrip()
                    if record not in records:continue
                    index=records.index(record)
                    if index in acked:continue
                    acked.add(index)
                    if not reported_vlc:await report('vlc');reported_vlc=True
                    if picture:
                        candidate=assembler.feed(record)
                        keys,header,pixels=assembler.progress(picture.image_id)
                        await self.emit(dict(type='progress',id=self.active,receivedRecords=len(acked),totalRecords=len(records)))
                        if header and pixels:
                            packed=bytearray(len(picture.data));mask=bytearray(len(picture.data))
                            for i,pixel in enumerate(pixels):
                                if pixel is not None:
                                    mask[i//8]|=128>>(i%8)
                                    if pixel:packed[i//8]|=128>>(i%8)
                            await self.emit(dict(type='partial',id=self.active,width=picture.width,height=picture.height,
                                data=base64.b64encode(packed).decode(),mask=base64.b64encode(mask).decode()))
                        if candidate and candidate==picture:
                            received=dict(kind='image',width=candidate.width,height=candidate.height,data=base64.b64encode(candidate.data).decode())
                    else:received=clean_payload(data['payload'])
                if received:
                    status='confirmed';message='Verified from RX records on receiving laptop.'
                    self.latency=(time.monotonic()-started)*1000
                    self.throughput=(len(picture.data) if picture else len(received['text']))*8/self.latency
                    break
                if self.fresh() and time.monotonic()-self.last_send>=.03:
                    count=min(24,(self.buffer['capacity']-self.buffer['used'])//52)
                    if count:
                        batch=pacer.batch(count,acked)
                        await self.send_batch(batch)
                        if self.last_admitted>started and not reported_plc and not reported_vlc:await report('plc');reported_plc=True
                await asyncio.sleep(.01)
        finally:
            idle=await self.ensure_idle();self.active=None
        return dict(status=status,received=received,message=message,idle=idle)
    async def close(self):
        if self.reader:self.reader.cancel();await asyncio.gather(self.reader,return_exceptions=True)
        self.udp.close()
