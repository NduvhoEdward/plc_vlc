import asyncio, base64, socket, time, unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_agent import ID
from agent import records_for
from split_rig import AutoPacer, NetworkRig

class PacingTests(unittest.TestCase):
    def test_text_batches_preserve_gateway_51_byte_boundaries(self):
        records,_=records_for(dict(kind='text',text='Hello'),ID)
        batch=AutoPacer(records).batch(24,set())
        self.assertEqual(len(batch),24*51)
        self.assertTrue(all(batch[i:i+51].decode().rstrip()==records[0] for i in range(0,len(batch),51)))
    def test_repair_skips_received_records_and_bounds_datagrams(self):
        records,_=records_for(dict(kind='image',width=64,height=32,data=base64.b64encode(bytes(256)).decode()),ID)
        p=AutoPacer(records)
        for _ in range(20):
            batch=p.batch(24,{0,1})
            self.assertLessEqual(len(batch),1224)
            self.assertNotIn(records[0].encode(),batch)
            self.assertNotIn(records[1].encode(),batch)
        self.assertEqual(p.batch(24,set(range(len(records)))),b'')

class DrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_or_inflight_feedback_never_confirms_idle(self):
        with patch('split_rig.socket', SimpleNamespace(socket=lambda *args: SimpleNamespace(connect=lambda *a: None, settimeout=lambda *a: None), AF_INET=2, SOCK_DGRAM=2)) as sock:
            rig=NetworkRig(SimpleNamespace(plc_host='192.0.2.1',optical_rate=300000))
            rig.buffer=dict(used=0,capacity=1040,inflight=1,streaming=1,threshold_pct=75)
            rig.buffer_at=time.monotonic();self.assertFalse(rig.is_idle())
            rig.buffer['inflight']=0;self.assertTrue(rig.is_idle())
            rig.buffer_at=0;self.assertFalse(rig.is_idle())
    async def test_rx_records_require_active_transfer(self):
        with patch('split_rig.socket', SimpleNamespace(socket=lambda *args: SimpleNamespace(connect=lambda *a: None, settimeout=lambda *a: None), AF_INET=2, SOCK_DGRAM=2)):
            rig=NetworkRig(SimpleNamespace(plc_host='192.0.2.1',optical_rate=300000))
            rig.active=ID
            rig.observe(dict(type='rx-record',id='wrong',record='fake'))
            self.assertTrue(rig.observations.empty())
            rig.observe(dict(type='rx-record',id=ID,record='actual'))
            self.assertEqual(rig.observations.get_nowait(),'actual')
    async def test_cancel_during_priming_fills_own_queue_then_drains(self):
        with patch('split_rig.socket', SimpleNamespace(socket=lambda *args: SimpleNamespace(connect=lambda *a: None, settimeout=lambda *a: None), AF_INET=2, SOCK_DGRAM=2)):
            rig=NetworkRig(SimpleNamespace(plc_host='192.0.2.1',optical_rate=300000))
            rig.buffer=dict(used=52,capacity=1040,inflight=0,streaming=0,threshold_pct=75)
            rig.buffer_at=time.monotonic();rig.owned=True;rig.drain_record='x'
            async def start():pass
            async def send(batch):
                self.assertEqual(len(batch),14*51)
                rig.buffer['used']=0
            rig.start=start;rig.send_batch=send
            self.assertTrue(await rig.ensure_idle())
            self.assertFalse(rig.owned)
