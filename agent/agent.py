"""Outbound-only relay agent. Default simulation; hardware mode is explicit."""
import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import socket
import sqlite3
import time
from pathlib import Path
from pixel_protocol import Picture, ImageAssembler


def clean_payload(p):
    if not isinstance(p, dict):
        raise ValueError('Invalid payload')
    if p.get('kind') == 'text':
        text = p.get('text')
        if not isinstance(text, str) or not re.fullmatch(r'[\x20-\x7e]{1,30}', text):
            raise ValueError('Text must be 1–30 printable ASCII characters')
        return dict(kind='text', text=text)
    if p.get('kind') != 'image' or p.get('width') not in (32, 64, 128) or p.get('height') != p['width'] // 2:
        raise ValueError('Invalid image dimensions')
    data = base64.b64decode(p.get('data', ''), validate=True)
    if len(data) != p['width'] * p['height'] // 8 or base64.b64encode(data).decode() != p['data']:
        raise ValueError('Invalid packed image')
    return dict(kind='image', width=p['width'], height=p['height'], data=p['data'])


def payload_hash(p):
    encoded = json.dumps(clean_payload(p), ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def records_for(p, transfer_id):
    p = clean_payload(p)
    if p['kind'] == 'text':
        identifier = hashlib.sha256(transfer_id.encode()).hexdigest()[:8].upper()
        body = f'TX1:{identifier}:{p["text"]}'
        return [body + f':{binascii.crc_hqx(body.encode(), 0xffff):04X}'], None
    identifier = int(hashlib.sha256(transfer_id.encode()).hexdigest()[:4], 16)
    picture = Picture(identifier, p['width'], p['height'], base64.b64decode(p['data']))
    return picture.records(), picture


class Ledger:
    """Persist IDs before sending; an interrupted transfer is never automatically resent."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS transfers (id TEXT PRIMARY KEY, hash TEXT, state TEXT, result TEXT, at REAL)')
        self.db.commit()

    def get(self, identifier):
        row = self.db.execute('SELECT hash,state,result FROM transfers WHERE id=?', (identifier,)).fetchone()
        return dict(hash=row[0], state=row[1], result=json.loads(row[2]) if row[2] else None) if row else None

    def start(self, identifier, digest):
        self.db.execute('INSERT INTO transfers VALUES (?,?,?,?,?)', (identifier, digest, 'running', None, time.time()))
        self.db.commit()

    def finish(self, identifier, result):
        self.db.execute('UPDATE transfers SET state=?,result=?,at=? WHERE id=?', (result['status'], json.dumps(result), time.time(), identifier))
        self.db.commit()

    def prune(self):
        # Keep only a one-hour duplicate tombstone after content expires.
        self.db.execute('UPDATE transfers SET result=NULL WHERE at<?', (time.time() - 900,))
        self.db.execute('DELETE FROM transfers WHERE at<? AND state != ?', (time.time() - 3600, 'running'))
        self.db.commit()


class SimulatedRig:
    simulated = True

    async def transfer(self, data, cancel, report):
        for stage in ('plc', 'vlc'):
            if cancel.is_set():
                return dict(status='cancelled', message='Simulated transfer cancelled', idle=True)
            await asyncio.sleep(.8)
            await report(stage)
        if cancel.is_set():
            return dict(status='cancelled', message='Simulated transfer cancelled', idle=True)
        await asyncio.sleep(.5)
        return dict(status='confirmed', received=clean_payload(data['payload']), idle=True)

    async def ensure_idle(self):
        return True

    async def telemetry(self):
        # No invented numerical measurements, even with the simulated agent.
        return dict(plc='simulated', vlc='simulated')


class HardwareRig:
    """Existing UDP5000 PLC ingress, TX control UART, RX UART message feedback.

    This adapter deliberately requires TX queue-drain feedback. No VLC-only route.
    It never changes modulation, rate, threshold, ADC configuration, or firmware.
    """
    simulated = False

    def __init__(self, args):
        import serial
        if not args.plc_host or not args.tx_port or not args.rx_port or args.tx_port == args.rx_port:
            raise ValueError('Hardware mode requires --plc-host, distinct --tx-port and --rx-port')
        self.tx = serial.Serial(args.tx_port, 115200, timeout=.05)
        try:
            self.rx = serial.Serial(args.rx_port, 115200, timeout=.05)
        except Exception:
            self.tx.close()
            raise
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.connect((args.plc_host, 5000))
        self.udp.settimeout(.2)
        self.control, self.control_at = {}, 0
        self.latency = None
        self.last_udp = 0
        self.parts = {'tx': b'', 'rx': b''}

    def command(self, text):
        if text not in ('CONTROL', 'SOURCE PLC', 'START', 'AUTO'):
            raise ValueError('Unsupported serial command')
        self.tx.write((text + '\n').encode('ascii'))

    async def lines(self, which):
        port = self.tx if which == 'tx' else self.rx
        chunk = await asyncio.to_thread(port.read, min(4096, max(1, port.in_waiting)))
        content = self.parts[which] + chunk
        pieces = content.split(b'\n'); self.parts[which] = pieces.pop()[-4096:]
        return [line.decode('ascii', 'replace').strip() for line in pieces]

    async def refresh_control(self):
        self.command('CONTROL')
        for line in await self.lines('tx'):
            if line.startswith('TX CONTROL '):
                self.control = dict(re.findall(r'(\w+)=([^\s]+)', line)); self.control_at = time.monotonic()

    def is_idle(self):
        return time.monotonic() - self.control_at < 2 and all(self.control.get(k) == '0' for k in ('plc_used', 'local_used', 'inflight', 'pending'))

    async def ensure_idle(self):
        for _ in range(40):
            await self.refresh_control()
            if self.is_idle():
                return True
            await asyncio.sleep(.1)
        return False

    async def telemetry(self):
        # Do not read UARTs concurrently with the transfer loop. UART state is
        # sampled by that loop; unsupported BER/SNR/throughput remain unavailable.
        return dict(plc='online' if time.monotonic() - self.last_udp < 5 else 'unknown',
                    vlc='unknown', **({'latency': round(self.latency, 1)} if self.latency is not None else {}))

    async def transfer(self, data, cancel, report):
        if not await self.ensure_idle():
            raise RuntimeError('TX queues are not idle. Stop other producers and drain the rig.')
        records, picture = records_for(data['payload'], data['id'])
        assembler = ImageAssembler(); acked = set(); received = None
        # Clear pre-existing host RX output before starting this unique transfer.
        await asyncio.to_thread(self.rx.reset_input_buffer); self.parts['rx'] = b''
        self.command('SOURCE PLC'); self.command('START')
        started = time.monotonic(); next_send = 0; status = 'failed'; message = 'Receiver timeout; incomplete payload.'
        reported_plc = reported_vlc = False
        try:
            while time.monotonic() - started < 150:
                if cancel.is_set():
                    status = 'cancelled'; message = 'Cancelled. Previously queued frames drained before release.'; break
                await self.refresh_control()
                if self.control.get('source') != 'PLC' or self.control.get('mode') != 'RUN' or self.control.get('pending') != '0':
                    await asyncio.sleep(.05); continue
                if time.monotonic() >= next_send:
                    # A small bounded lead; no production while TX status is stale.
                    if time.monotonic() - self.control_at < 2 and int(self.control.get('plc_used', '999999')) < 1024:
                        missing = [i for i in range(len(records)) if i not in acked]
                        if not missing:
                            break
                        # Repeat each missing record because RX USB output is throttled.
                        record = records[missing[0]]
                        await asyncio.to_thread(self.udp.send, record.encode('ascii'))
                        try:
                            reply = await asyncio.to_thread(self.udp.recv, 2048)
                            if reply.startswith(b'QUEUED '):
                                self.last_udp = time.monotonic()
                                if not reported_plc: await report('plc'); reported_plc = True
                            elif reply.startswith(b'REJECT ') and b'buffer_full' not in reply:
                                raise RuntimeError(reply.decode('ascii', 'replace'))
                        except socket.timeout:
                            pass  # Unique records can safely be repeated; RX decides completion.
                    next_send = time.monotonic() + .03
                for line in await self.lines('rx'):
                    if not line.startswith('RX message: '):
                        continue
                    text = line[12:]
                    if text not in records:
                        continue
                    acked.add(records.index(text))
                    if not reported_vlc: await report('vlc'); reported_vlc = True
                    if picture:
                        candidate = assembler.feed(text)
                        if candidate and (candidate.data, candidate.width, candidate.height) == (picture.data, picture.width, picture.height):
                            received = dict(kind='image', width=candidate.width, height=candidate.height, data=base64.b64encode(candidate.data).decode())
                    else:
                        # Match the transfer-specific record, then verify its CRC16.
                        body, checksum = text.rsplit(':', 1)
                        if checksum == f'{binascii.crc_hqx(body.encode(), 0xffff):04X}':
                            received = dict(kind='text', text=body.split(':', 2)[2])
                if received:
                    status = 'confirmed'; message = 'Payload reconstructed and verified from RX output.'
                    self.latency = (time.monotonic() - started) * 1000; break
                await asyncio.sleep(.01)
        finally:
            # Stop producing and leave START in effect until all admitted frames drain.
            # STOP could leave a nonempty FIFO locked forever. AUTO is restored after drain.
            idle = await self.ensure_idle()
            if idle: self.command('AUTO')
        if not idle:
            raise RuntimeError('Hardware drain not confirmed. Rig stays locked until idle feedback returns.')
        return dict(status=status, received=received, message=message, idle=True)


class Agent:
    def __init__(self, rig, ledger):
        self.rig, self.ledger = rig, ledger
        if getattr(rig, 'split', False): rig.emit = self.send
        self.reconcile_lock = asyncio.Lock()
        self.ws = None; self.active = None; self.task = None; self.cancel = asyncio.Event()

    async def send(self, data):
        if self.ws:
            try: await self.ws.send(json.dumps(data, separators=(',', ':')))
            except Exception: pass  # Persisted result is replayed on reconnect, never re-transmitted.

    async def run_transfer(self, data):
        try:
            async def report(stage):
                await self.send(dict(type='transfer', id=data['id'], stage=stage))
            await report('accepted')
            result = await self.rig.transfer(data, self.cancel, report)
        except Exception as error:
            result = dict(status='failed', message=str(error)[:200], idle=False)
        # Never release a room while physical frames may still be in flight.
        while not result.get('idle'):
            await asyncio.sleep(2)
            result['idle'] = await self.rig.ensure_idle()
        event = dict(type='transfer', id=data['id'], **result)
        self.ledger.finish(data['id'], event); await self.send(event)
        self.active = None

    async def reconcile(self, data):
        active = data.get('active')
        if not active:
            if self.task and not self.task.done():
                # Relay lost its active record. Finish/drain our existing operation first.
                self.cancel.set(); await self.task
            if not await self.rig.ensure_idle():
                raise RuntimeError('Hardware is not idle. Stop other producers and drain the rig.')
            await self.send(dict(type='ready', simulated=self.rig.simulated, requiresReceiver=getattr(self.rig, 'split', False))); return
        identifier = active['id']; saved = self.ledger.get(identifier)
        if self.active == identifier and self.task and not self.task.done():
            if active.get('cancelRequested'): self.cancel.set()
            await self.send(dict(type='resume', id=identifier, simulated=self.rig.simulated, requiresReceiver=getattr(self.rig, 'split', False))); return
        if saved and saved.get('result'):
            await self.send(saved['result']); await self.send(dict(type='ready', simulated=self.rig.simulated, requiresReceiver=getattr(self.rig, 'split', False))); return
        # A restarted process or a lost dispatch is ambiguous. Do not replay payloads.
        if not await self.rig.ensure_idle():
            raise RuntimeError('Interrupted transfer awaiting hardware drain; no replay.')
        result = dict(type='transfer', id=identifier, status='failed', idle=True, message='Interrupted transfer reconciled; payload was not automatically resent.')
        if not saved: self.ledger.start(identifier, active['hash'])
        self.ledger.finish(identifier, result); await self.send(result); await self.send(dict(type='ready', simulated=self.rig.simulated, requiresReceiver=getattr(self.rig, 'split', False)))

    async def reconcile_safe(self, data):
        try:
            async with self.reconcile_lock: await self.reconcile(data)
        except Exception as error: print('Reconciliation:', str(error), flush=True)

    async def heartbeat(self):
        while True:
            await self.send(dict(type='telemetry', **await self.rig.telemetry()))
            await asyncio.sleep(1)

    async def connect(self, url, secret):
        from websockets.asyncio.client import connect
        attempt = 0
        while True:
            try:
                async with connect(url, additional_headers={'Authorization': 'Bearer ' + secret}, max_size=4096, ping_interval=20, open_timeout=15) as ws:
                    self.ws = ws; attempt = 0
                    print('Relay connected. Mode:', 'simulated' if self.rig.simulated else 'hardware', flush=True)
                    heartbeat = asyncio.create_task(self.heartbeat())
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            if data.get('type') in ('receiver-status', 'receiver-armed', 'rx-record', 'rx-stats') and getattr(self.rig, 'split', False): self.rig.observe(data)
                            elif data.get('type') == 'reconcile':
                                if getattr(self.rig, 'split', False):
                                    asyncio.create_task(self.reconcile_safe(data))
                                else: await self.reconcile(data)
                            elif data.get('type') == 'cancel' and data.get('id') == self.active: self.cancel.set()
                            elif data.get('type') == 'transfer':
                                if not re.fullmatch(r'[0-9a-f-]{36}', data.get('id', '')) or payload_hash(data.get('payload')) != data.get('hash'):
                                    raise ValueError('Invalid command or payload hash')
                                old = self.ledger.get(data['id'])
                                if old:
                                    if old['hash'] != data['hash']: raise ValueError('Conflicting transfer ID')
                                    if old['result']: await self.send(old['result'])
                                    continue
                                if self.task and not self.task.done(): raise ValueError('Agent already busy')
                                self.ledger.prune(); self.ledger.start(data['id'], data['hash'])
                                self.active = data['id']; self.cancel = asyncio.Event()
                                self.task = asyncio.create_task(self.run_transfer(data))
                            elif data.get('type') == 'error': print('Relay:', data.get('message'), flush=True)
                    finally:
                        heartbeat.cancel(); await asyncio.gather(heartbeat, return_exceptions=True); self.ws = None
                        if getattr(self.rig, 'split', False): self.cancel.set(); self.rig.receiver_online = False
            except asyncio.CancelledError:
                raise
            except Exception as error:
                response = getattr(error, 'response', None)
                status = getattr(response, 'status_code', None)
                reason = {409: 'Another sender bridge is already connected. Stop the sender on the other PC or close its earlier launcher.', 401: 'Sender credential rejected. Use the current private sender package.', 403: 'Sender connection forbidden. Check relay access configuration.', 429: 'Relay connection limit reached. Wait before retrying.'}.get(status)
                print('Connection unavailable:', reason or ('HTTP ' + str(status) if status else type(error).__name__), '- retrying', flush=True)
            attempt += 1
            await asyncio.sleep(min(30, 2 ** min(attempt, 5)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware', action='store_true')
    parser.add_argument('--network-tx', action='store_true', help='TX UDP feedback; separate receiver laptop')
    parser.add_argument('--optical-rate', type=int, default=300000, help='Pacing estimate only; does not change firmware rate')
    parser.add_argument('--plc-host'); parser.add_argument('--tx-port'); parser.add_argument('--rx-port')
    args = parser.parse_args()
    url, secret = os.environ.get('IOL_AGENT_URL', ''), os.environ.get('IOL_AGENT_TOKEN', '')
    if not url.startswith('wss://') or not secret:
        parser.error('Set IOL_AGENT_URL=wss://.../agent and IOL_AGENT_TOKEN in the environment')
    if args.network_tx:
        from split_rig import NetworkRig
        rig = NetworkRig(args)
    else: rig = HardwareRig(args) if args.hardware else SimulatedRig()
    ledger = Ledger(Path(__file__).with_name('transfers.sqlite'))
    try: asyncio.run(Agent(rig, ledger).connect(url, secret))
    except KeyboardInterrupt: print('Agent stopped. Interrupted transfers must be reconciled before reuse.')
    finally:
        ledger.db.close()
        if getattr(rig, 'split', False): rig.udp.close()
        elif not rig.simulated:
            rig.tx.close(); rig.rx.close(); rig.udp.close()


if __name__ == '__main__': main()
