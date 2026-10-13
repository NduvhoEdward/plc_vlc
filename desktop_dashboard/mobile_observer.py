"""Read actual RX observations from the bridge. Never opens serial or sends board commands."""
import json,threading,time,urllib.request
class ObservationWorker(threading.Thread):
    def __init__(self,events,url='http://127.0.0.1:8765'):
        super().__init__(daemon=True);self.events=events;self.url=url.rstrip('/');self.stop=threading.Event()
        self.cursor=0;self.connected=False;self.last_error=None
    def emit(self,**data):data.setdefault('at',time.monotonic());self.events.put(data)
    def command(self,*args):raise ValueError('Mobile receiver mode is read-only. The bridge owns RX USB; board commands are disabled.')
    def udp_message(self,*args):raise ValueError('TX is controlled by the mobile sender bridge. This dashboard never sends data to TX.')
    picture_batch=udp_message
    subscribe_buffer=udp_message
    def run(self):
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen(self.url+'/events?after='+str(self.cursor),timeout=2) as r:data=json.load(r)
                self.cursor=data['cursor']
                for event in data['events']:self.events.put(event)
                online=bool(data['connected'])
                if online!=self.connected:
                    self.connected=online
                    if online:self.emit(kind='connected',roles=['RX'])
                    else:self.emit(kind='notice',line='Receiver relay disconnected. Local RX measurements remain actual USB observations.')
                self.last_error=None
            except (OSError,ValueError,KeyError) as error:
                self.connected=False
                message='Waiting for the receiver bridge. Run START.cmd; this dashboard does not open RX USB.'
                if message!=self.last_error:self.emit(kind='error',line=message);self.last_error=message
            self.stop.wait(.15)
