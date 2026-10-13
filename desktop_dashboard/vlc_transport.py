"""USB command/telemetry transport for the current ESP32 firmware."""
import pathlib
import queue
import socket
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


class LinkWorker(threading.Thread):
    def __init__(self, events, tx, rx, baud=115200, polling=True, interval=2):
        super().__init__(daemon=True)
        self.events = events
        self.names = {k: v for k, v in (("TX", tx), ("RX", rx)) if v and v != "(none)"}
        self.baud, self.polling, self.interval = baud, polling, interval
        self.commands = queue.Queue()
        self.stop = threading.Event()

    def command(self, role, text):
        if role not in self.names:
            raise ValueError(f"Connect the {role} USB port first.")
        if not text or "\n" in text or "\r" in text or not text.isascii():
            raise ValueError("Commands must be one ASCII line.")
        limit = 55 if role == "TX" else 39
        if len(text) > limit:
            raise ValueError(f"{role} command exceeds the firmware's {limit}-byte command limit.")
        self.commands.put((role, text, False))

    def udp_message(self, ip, port, text):
        payload = ("MSG " + text).encode("ascii")
        if not text or len(payload) > 1400 or any(ord(c) < 32 or ord(c) > 126 for c in text):
            raise ValueError("Wi-Fi messages must be printable ASCII, at most 1396 bytes with MSG prefix.")
        socket.inet_aton(ip)
        self.commands.put(("UDP", (ip, int(port), payload), False))

    def picture_batch(self, records):
        if 'TX' not in self.names or not 1<=len(records)<=4:
            raise ValueError('Connect TX; batches contain 1..4 text records.')
        if any(not r.isascii() or len(r)>51 or '\n' in r or '\r' in r for r in records):
            raise ValueError('Invalid picture text batch.')
        self.commands.put(('TX_BATCH',list(records),False))

    def subscribe_buffer(self,ip,port=5000):
        socket.inet_aton(ip)
        self.commands.put(('UDP',(ip,port,b'VLC_STATUS SUBSCRIBE'),False))

    def emit(self, **event):
        event.setdefault("at", time.monotonic())
        self.events.put(event)

    def run(self):
        ports, buffers = {}, {}
        udp = None
        try:
            if serial is None:
                raise RuntimeError("pyserial is missing; this dashboard uses its bundled dashboard/vendor copy.")
            for role, name in self.names.items():
                port = serial.Serial(port=None, baudrate=self.baud, timeout=0, write_timeout=0.5)
                port.dtr = False
                port.rts = False
                port.port = name
                ports[role] = port
                port.open()
                buffers[role] = bytearray()
            self.emit(kind="connected", roles=list(ports))
            next_poll = 0
            queries = queue.Queue()
            udp_peers = set()
            while not self.stop.wait(0.01):
                now = time.monotonic()
                if self.polling and now >= next_poll:
                    if queries.empty():
                        for role, command in (("TX", "STAT"), ("TX", "NETSTAT"), ("RX", "STAT")):
                            if role in ports:
                                queries.put((role, command, True))
                    next_poll = now + max(2, self.interval)
                try:
                    request = self.commands.get_nowait()
                except queue.Empty:
                    try:
                        request = queries.get_nowait() if self.polling else None
                    except queue.Empty:
                        request = None
                if request is not None:
                    role, command, automatic = request
                    if role == "UDP":
                        ip, port, payload = command
                        if udp is None:
                            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            udp.bind(("0.0.0.0", 0))
                            udp.setblocking(False)
                        udp_peers.add((ip, port))
                        udp.sendto(payload, (ip, port))
                        self.emit(kind="command", role="TX", line=f"UDP {ip}:{port} " + payload.decode("ascii"), automatic=False)
                    elif role == 'TX_BATCH':
                        ports['TX'].write(''.join('MSG '+r+'\n' for r in command).encode('ascii'))
                        self.emit(kind='command',role='TX',line=f'Image batch: {len(command)} repeated records',automatic=False)
                    else:
                        ports[role].write((command + "\n").encode("ascii"))
                        self.emit(kind="command", role=role, line=command, automatic=automatic)
                for role, port in ports.items():
                    data = port.read(min(port.in_waiting, 8192))
                    if not data:
                        continue
                    buffers[role].extend(data)
                    while b"\n" in buffers[role]:
                        line, _, remaining = buffers[role].partition(b"\n")
                        buffers[role] = bytearray(remaining)
                        self.emit(kind="line", role=role, line=line.rstrip(b"\r").decode("utf-8", errors="replace"))
                    if len(buffers[role]) > 16384:
                        buffers[role].clear()
                        self.emit(kind="notice", line=f"{role} oversized partial line discarded")
                if udp:
                    for _ in range(20):
                        try:
                            data, peer = udp.recvfrom(4096)
                        except BlockingIOError:
                            break
                        if peer in udp_peers:
                            for line in data.decode("ascii", errors="replace").splitlines():
                                self.emit(kind="line", role="TX", line=line)
        except Exception as error:
            self.emit(kind="error", line=str(error))
        finally:
            for port in ports.values():
                try:
                    port.close()
                except Exception:
                    pass
            if udp:
                udp.close()
            self.emit(kind="closed")
