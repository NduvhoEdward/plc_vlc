import importlib.util, unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root.parent/'mobile-control'/'.python-deps'))
spec=importlib.util.spec_from_file_location('portable_launcher',root/'packaging'/'launcher.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
class LauncherTests(unittest.TestCase):
    def test_receiver_identifies_rx_not_tx_or_bluetooth(self):
        ports=[SimpleNamespace(device='COM2',vid=None),SimpleNamespace(device='COM9',vid=1),SimpleNamespace(device='COM10',vid=1)]
        with patch.object(launcher,'serial_ports',return_value=ports),patch.object(launcher,'probe_rx',side_effect=lambda port:port=='COM10') as probe:
            self.assertEqual(launcher.find_rx(),'COM10')
            self.assertEqual([c.args[0] for c in probe.call_args_list],['COM9','COM10'])
    def test_unidentified_usb_does_not_get_selected(self):
        with patch.object(launcher,'serial_ports',return_value=[SimpleNamespace(device='COM9',vid=1)]),patch.object(launcher,'probe_rx',return_value=False):
            self.assertIsNone(launcher.find_rx())
    def test_explicit_port_still_requires_receiver_signature(self):
        with patch.object(launcher,'probe_rx',return_value=False):
            self.assertIsNone(launcher.find_rx('COM9'))
    def test_tx_requires_feedback_not_any_udp_packet(self):
        fake=MagicMock();fake.__enter__.return_value=fake;fake.recv.side_effect=[b'garbage',b'VLC BUFFER used=0 capacity=20000']
        with patch.object(launcher.socket,'socket',return_value=fake):
            self.assertTrue(launcher.probe_tx('192.168.0.100'))
            fake.send.assert_called_once_with(b'VLC_STATUS SUBSCRIBE')
    def test_tls_failure_never_reports_connected(self):
        with patch.object(launcher.socket,'create_connection',side_effect=OSError('offline')):
            self.assertFalse(launcher.relay_available('https://example.com'))
    def test_dashboard_javascript_has_no_literal_newline_in_string(self):
        self.assertIn("join('\\n')",launcher.PAGE)
if __name__=='__main__':unittest.main()
