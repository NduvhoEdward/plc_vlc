import importlib.util,json,queue,sys,time,unittest,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'agent'))
sys.path.insert(0,str(root/'desktop_dashboard'))
from receiver import Display,serve
from mobile_observer import ObservationWorker
class DashboardFeedTests(unittest.TestCase):
    def test_raw_rx_lines_retained_without_source_substitution(self):
        d=Display();d.observe_line('RX STAT good=2');d.observe_line('RX message: actual light data')
        events=json.loads(d.observations())['events']
        self.assertEqual([e['line'] for e in events],['RX STAT good=2','RX message: actual light data'])
        self.assertTrue(all(e['role']=='RX' for e in events))
        self.assertEqual(len(json.loads(d.observations(1))['events']),1)
    def test_buffer_bounded_and_cursor_recovers_after_restart(self):
        d=Display()
        for i in range(2050):d.observe_line(str(i))
        self.assertEqual(len(json.loads(d.observations())['events']),2048)
        self.assertEqual(len(json.loads(d.observations(999999))['events']),2048)
    def test_observer_reads_http_feed_and_refuses_all_board_writes(self):
        d=Display();d.observe_line('RX message: actual');d.update(connected=True)
        server=serve(d,0);q=queue.Queue();worker=ObservationWorker(q,'http://127.0.0.1:'+str(server.server_port))
        try:
            worker.start();deadline=time.monotonic()+3;events=[]
            while time.monotonic()<deadline:
                try:events.append(q.get(timeout=.1))
                except queue.Empty:pass
                if any(e.get('line')=='RX message: actual' for e in events):break
            self.assertTrue(any(e.get('line')=='RX message: actual' for e in events))
            for method in (worker.command,worker.udp_message,worker.picture_batch,worker.subscribe_buffer):
                with self.assertRaises(ValueError):method('TX','START')
        finally:worker.stop.set();worker.join(timeout=3);server.shutdown();server.server_close()
    def test_feed_bad_cursor_is_rejected(self):
        d=Display();server=serve(d,0)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/events?after=bad')
            self.assertEqual(error.exception.code,400)
        finally:server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
