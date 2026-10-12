import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from agent import Agent, Ledger, SimulatedRig, clean_payload, payload_hash, records_for
from pixel_protocol import ImageAssembler

ID = '12345678-1234-1234-1234-123456789abc'


class ProtocolTests(unittest.TestCase):
    def test_text_with_colons_and_transfer_specific_record(self):
        p = dict(kind='text', text='Hello: receiver')
        records, _ = records_for(p, ID)
        self.assertLessEqual(len(records[0]), 51)
        self.assertNotEqual(records, records_for(p, ID.replace('abc', 'def'))[0])

    def test_monochrome_reassembly_uses_received_records(self):
        for width in (32, 64, 128):
            p = dict(kind='image', width=width, height=width // 2, data=base64.b64encode(bytes([0x81]) * (width * width // 16)).decode())
            records, original = records_for(p, ID)
            assembler = ImageAssembler(); received = None
            for record in reversed(records):
                result = assembler.feed(record)
                if result: received = result
            self.assertEqual(received, original)
            self.assertTrue(all(len(r) == 51 for r in records))
            with self.assertRaises(ValueError): ImageAssembler().feed(records[1][:-1] + ('0' if records[1][-1] != '0' else '1'))

    def test_invalid_payloads(self):
        for p in (dict(kind='text', text='a' * 31), dict(kind='text', text='✓'), dict(kind='image', width=64, height=32, data='AA==')):
            with self.assertRaises(ValueError): clean_payload(p)

    def test_hash_matches_js_known_payload(self):
        self.assertEqual(payload_hash(dict(kind='text', text='Hello')), '06a8c1de7efc5355734b68bf4f0ba063d60fef980c745c7eeb29baaf6470face')


class ReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_transfer_replays_result_without_transmitting(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'test.sqlite'); rig = SimulatedRig(); agent = Agent(rig, ledger)
            p = dict(kind='text', text='Hello'); digest = payload_hash(p)
            ledger.start(ID, digest); ledger.finish(ID, dict(type='transfer', id=ID, status='confirmed', received=p, idle=True))
            events = []
            async def send(event): events.append(event)
            agent.send = send
            await agent.reconcile(dict(active=dict(id=ID, hash=digest)))
            self.assertEqual(events[0]['status'], 'confirmed'); self.assertIsNone(agent.task)
            ledger.db.close()

    async def test_process_restart_marks_interrupted_transfer_failed_no_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / 'test.sqlite'); agent = Agent(SimulatedRig(), ledger)
            ledger.start(ID, 'x'); events = []
            async def send(event): events.append(event)
            agent.send = send
            await agent.reconcile(dict(active=dict(id=ID, hash='x')))
            self.assertEqual(events[0]['status'], 'failed'); self.assertIsNone(agent.task)
            ledger.db.close()


if __name__ == '__main__': unittest.main()
