"""Desktop dashboard for the current ESP32 2-PPM sketches."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from vlc_metrics import LinkMetrics
from vlc_session import Session, timestamp
from vlc_transport import LinkWorker, list_ports

HERE = Path(__file__).resolve().parent
NAVY, PANEL, INK, CYAN, GOLD = "#081626", "#10283e", "#e7f4ff", "#53e5ff", "#ffe16a"


def show(value, unit=""):
    if value is None:
        return "—"
    return (f"{value:,.1f}" if isinstance(value, float) else f"{value:,}" if isinstance(value, int) else str(value)) + unit


class Dashboard:
    def __init__(self, root, demo=False, base=None):
        self.root, self.demo = root, demo
        self.base = Path(base) if base else HERE / ("demo_results" if demo else "results")
        self.worker, self.roles = None, set()
        self.events = queue.Queue()
        self.metrics = LinkMetrics()
        self.history = deque(maxlen=3600)
        self.started = time.monotonic()
        self.last_sample = -10
        self.replay = False
        self.replay_now = 0
        self.synced = set()
        self.demo_step = 0
        self.session = Session(self.base, demo)
        try:
            config = json.loads((HERE / "vlc_config.json").read_text())
        except (OSError, ValueError):
            config = {}
        root.title("VLC Lab Dashboard")
        root.geometry("1180x900")
        root.minsize(1020, 850)
        style = ttk.Style(root)
        style.theme_use("clam")
        root.configure(background=NAVY)
        style.configure("TFrame", background=NAVY)
        style.configure("TLabel", background=NAVY, foreground=INK, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=7, background=GOLD, foreground=NAVY, bordercolor="#e6bf41")
        style.map("TButton", background=[("active", "#fff1ab"), ("disabled", PANEL)], foreground=[("disabled", "#8196a9")])
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"), foreground=GOLD)
        style.configure("Value.TLabel", font=("Segoe UI", 18, "bold"), foreground=CYAN)
        style.configure("TCheckbutton", background=NAVY, foreground=INK)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TNotebook", background=NAVY, bordercolor="#2b506b")
        style.configure("TNotebook.Tab", background=PANEL, foreground=INK, padding=(12, 7))
        style.map("TNotebook.Tab", background=[("selected", GOLD)], foreground=[("selected", NAVY)])
        style.configure("TEntry", fieldbackground=PANEL, foreground=INK, insertcolor=CYAN)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=INK, arrowcolor=GOLD)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)])
        style.configure("Horizontal.TProgressbar", background=GOLD, troughcolor=PANEL, bordercolor="#2b506b")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=27)
        style.configure("Treeview.Heading", background="#173c56", foreground=GOLD)
        style.map("Treeview", background=[("selected", "#176582")])
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", INK)
        root.option_add("*TCombobox*Listbox.selectBackground", "#176582")
        body = ttk.Frame(root, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="⚡ VLC Lab · Light Link", style="Title.TLabel").pack(anchor="w")
        self.mode = tk.StringVar(value="SYNTHETIC DEMO · no hardware measurements" if demo else "PLC Wi-Fi → buffered 2-PPM → optical RX")
        ttk.Label(body, textvariable=self.mode).pack(anchor="w", pady=(0, 12))
        bar = ttk.Frame(body)
        bar.pack(fill="x")
        self.tx_port = tk.StringVar(value=config.get("tx", "(none)"))
        self.rx_port = tk.StringVar(value=config.get("rx", "(none)"))
        self.port_boxes = []
        for label, var in (("TX USB", self.tx_port), ("RX USB", self.rx_port)):
            ttk.Label(bar, text=label).pack(side="left", padx=(0, 5))
            combo = ttk.Combobox(bar, textvariable=var, width=12, state="readonly")
            combo.pack(side="left", padx=(0, 15))
            self.port_boxes.append(combo)
        ttk.Button(bar, text="Refresh ports", command=self.refresh_ports).pack(side="left")
        self.connect_button = ttk.Button(bar, text="Connect", command=self.connect)
        self.connect_button.pack(side="left", padx=8)
        self.polling = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Live updates (2 s)", variable=self.polling, command=self.set_polling).pack(side="left")
        self.status = tk.StringVar(value="Close Arduino Serial Monitors, choose the TX/RX ports, then Connect. USB: 115200 baud.")
        ttk.Label(body, textvariable=self.status, wraplength=1100).pack(anchor="w", pady=10)
        cards = ttk.Frame(body)
        cards.pack(fill="x")
        self.cards = {}
        for i, (key, label) in enumerate((("wifi", "PLC Wi-Fi connection"), ("rate", "TX / RX bit rate"),
                ("loss", "Live RX packet delivery"), ("throughput", "FIFO drain throughput"),
                ("frames", "CRC-valid RX frames"), ("time", "Last buffer drain time"))):
            box = ttk.Frame(cards, padding=10, relief="solid", borderwidth=1)
            box.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            cards.columnconfigure(i % 3, weight=1)
            ttk.Label(box, text=label).pack(anchor="w")
            var = tk.StringVar(value="—")
            ttk.Label(box, textvariable=var, style="Value.TLabel").pack(anchor="w", pady=3)
            self.cards[key] = var
        tabs = ttk.Notebook(body)
        tabs.pack(fill="both", expand=True, pady=12)
        self.tabs = {}
        for name in ("Overview", "Messages", "Gateway", "Link controls", "Results", "Diagnostics"):
            frame = ttk.Frame(tabs, padding=12)
            tabs.add(frame, text=name)
            self.tabs[name] = frame
        self.build_overview()
        self.build_messages(config)
        self.build_gateway()
        self.build_controls()
        self.build_results()
        self.build_diagnostics()
        self.footer = tk.StringVar(value=f"Automatically recording to: {self.session.path}")
        ttk.Label(body, textvariable=self.footer, wraplength=1100).pack(side="bottom", fill="x", before=tabs)
        self.refresh_ports()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.tick)
        if demo:
            root.after(300, self.demo_tick)

    def build_overview(self):
        frame = self.tabs["Overview"]
        self.buffer_text = tk.StringVar(value="Buffer: waiting for TX measurements")
        ttk.Label(frame, textvariable=self.buffer_text, style="Value.TLabel").pack(anchor="w")
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x", pady=8)
        self.buffer_detail = tk.StringVar()
        ttk.Label(frame, textvariable=self.buffer_detail, wraplength=1060).pack(anchor="w")
        self.chart = tk.Canvas(frame, height=125, background=PANEL, highlightthickness=0)
        self.chart.pack(fill="x", pady=12)
        self.chart.bind("<Configure>", lambda _: self.draw_chart())
        ttk.Label(frame, text="Latest decoded text · CRC-valid RX observation").pack(anchor="w")
        self.latest = tk.StringVar(value=self.metrics.last_message)
        ttk.Label(frame, textvariable=self.latest, font=("Segoe UI", 14), wraplength=1060).pack(anchor="w", pady=7)
        self.link_detail = tk.StringVar()
        ttk.Label(frame, textvariable=self.link_detail, wraplength=1060).pack(anchor="w")

    def build_messages(self, config):
        frame = self.tabs["Messages"]
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.message_path = tk.StringVar(value="TX USB (51 bytes)")
        self.message_path_combo=ttk.Combobox(row, textvariable=self.message_path, values=("TX USB (51 bytes)", "Wi-Fi UDP (1396 bytes)"), state="readonly", width=25)
        self.message_path_combo.pack(side="left")
        self.ip = tk.StringVar(value=config.get("ip", "192.168.0.100"))
        ttk.Label(row, text="  TX IP").pack(side="left")
        ttk.Entry(row, textvariable=self.ip, width=18).pack(side="left", padx=7)
        ttk.Label(row, text="UDP port 5000").pack(side="left")
        ttk.Button(row, text="Send message", command=self.send_message).pack(side="right")
        self.message_input = tk.Text(frame, height=3, font=("Segoe UI", 11), background=PANEL, foreground=INK, insertbackground=CYAN, relief="flat")
        self.message_input.pack(fill="x", pady=8)
        self.message_input.insert("1.0", "Hello from the VLC dashboard")
        self.reply = tk.StringVar(value="Messages enter the existing FIFO; transmission begins at your configured threshold.")
        ttk.Label(frame, textvariable=self.reply, wraplength=1060).pack(anchor="w")
        self.message_table = ttk.Treeview(frame, columns=("time", "text", "delay"), show="headings", height=7)
        for key, title, width in (("time", "Received (SAST)", 210), ("text", "Decoded text / chunk", 580), ("delay", "Text-match delay", 155)):
            self.message_table.heading(key, text=title)
            self.message_table.column(key, width=width)
        self.message_table.pack(fill="both", expand=True, pady=8)
        ttk.Label(frame, text="RX prints at most 10 messages/s. Large PLC messages appear as chunks. Queue acceptance does not confirm delivery. Text-match delay includes queueing/logging and can be ambiguous; it is not exact channel latency.", wraplength=1060).pack(anchor="w")

    def build_gateway(self):
        frame=self.tabs['Gateway']
        ttk.Label(frame,text='PLC + VLC gateway',style='Value.TLabel').pack(anchor='w',pady=(0,12))
        row=ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Label(row,text='Data source').pack(side='left',padx=(0,10))
        self.gateway_source=tk.StringVar(value='PLC (integrated)')
        self.gateway_reported_source=None
        ttk.Combobox(row,textvariable=self.gateway_source,values=('PLC (integrated)','VLC (local USB)'),state='readonly',width=24).pack(side='left')
        apply_button=ttk.Button(row,text='Apply source',command=self.apply_gateway_source)
        apply_button.pack(side='left',padx=10)
        self.gateway_buttons=[apply_button]
        row=ttk.Frame(frame)
        row.pack(fill='x',pady=15)
        for label,command in (('Start · bypass threshold','START'),('Stop TX','STOP'),('Auto · normal threshold','AUTO')):
            button=ttk.Button(row,text=label,command=lambda c=command:self.send_command('TX',c))
            button.pack(side='left',padx=(0,10))
            self.gateway_buttons.append(button)
        self.gateway_status=tk.StringVar(value='Connect the updated TX to read its gateway state.')
        ttk.Label(frame,textvariable=self.gateway_status,wraplength=1050).pack(anchor='w',pady=12)
        ttk.Label(frame,text='PLC / integrated: keeps the existing Wi-Fi FIFO and automatic threshold behavior.\nVLC / local USB: send messages from the Messages tab without the PLC or Wi-Fi; AUTO sends each local message once.\nStart: transmits queued and future data below the threshold until Stop or Auto. Stop: retains queued data; in-flight DMA frames finish. Auto: restores the normal PLC threshold gate.\nSwitching sources retains both queues and waits for DMA to finish. Local mode rejects new PLC datagrams. Rates, modulation, framing, buffer threshold and existing stats remain unchanged.',wraplength=1050).pack(anchor='w',pady=12)

    def apply_gateway_source(self):
        source='LOCAL' if self.gateway_source.get()=='VLC (local USB)' else 'PLC'
        self.send_command('TX','SOURCE '+source)

    def build_controls(self):
        frame = self.tabs["Link controls"]
        self.rate, self.sample, self.threshold = tk.StringVar(value="280000"), tk.StringVar(value="1600000"), tk.StringVar(value="75")
        self.filter, self.order = tk.StringVar(value="1"), tk.StringVar(value="SWAP")
        self.adc_clock=tk.StringVar(value="2")
        rows = (("Matched TX / RX rate (bit/s)", self.rate, (2000, 10000, 50000, 75000, 80000, 100000, 125000, 190000, 200000, 250000, 280000, 300000, 400000, 500000, 600000, 800000, 1000000), "Apply rate to both", self.apply_rate),
                ("RX ADC samples / second", self.sample, (100000, 200000, 500000, 1000000, 1600000, 2000000), "Apply RX sample rate", self.apply_sample),
                ("Buffer start threshold (%)", self.threshold, (0, 5, 25, 50, 75, 90, 99), "Apply TX threshold", lambda: self.numeric("TX", "THRESHOLD", self.threshold, 0, 99)),
                ("RX filter samples", self.filter, (1, 2, 3, 4), "Apply RX filter", lambda: self.numeric("RX", "FILTER", self.filter, 1, 4)),
                ("RX ADC order", self.order, ("RAW", "SWAP"), "Apply RX order", self.apply_order),
                ("RX ADC clock divider", self.adc_clock, (2,4,8,16), "Apply RX clock", self.apply_adc_clock))
        for i, (label, var, values, button, callback) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", padx=6, pady=6)
            ttk.Combobox(frame, textvariable=var, values=values, width=20).grid(row=i, column=1, padx=12)
            ttk.Button(frame, text=button, command=callback).grid(row=i, column=2, sticky="ew")
        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=12)
        for label, role, command in (("Calibrate RX", "RX", "C"), ("RX messages on", "RX", "BENCH 0"), ("RX messages off", "RX", "BENCH 1"), ("Reset RX counters", "RX", "RESET")):
            ttk.Button(buttons, text=label, command=lambda r=role, c=command: self.send_command(r, c)).pack(side="left", padx=3)
        ttk.Button(frame, text="Read current measurements", command=self.refresh_measurements).grid(row=7, column=0, sticky="w")
        ttk.Label(frame, text="High-rate boot profile: 280000 bit/s, RX SAMPLE 1600000, CLOCK 2, ORDER SWAP, FILTER 1. The RX sampling rate leaves processing margin for continuous FIFO data. Connecting reads status only. Settings change only when you press Apply or send a command. RX setting changes can reset counters; calibration interrupts reception. Calibrate while TX is transmitting. PLC threshold remains 75%. Manual settings revert to the sketch defaults after reboot.", wraplength=980).grid(row=8, column=0, columnspan=3, sticky="w", pady=15)

    def apply_adc_clock(self):
        if self.adc_clock.get() in ('2','4','8','16'):
            self.send_command('RX','CLOCK '+self.adc_clock.get())
        else:self.status.set('RX clock divider must be 2, 4, 8 or 16.')

    def build_results(self):
        frame = self.tabs["Results"]
        self.label = tk.StringVar(value="VLC experiment")
        ttk.Label(frame, text="Experiment name").pack(anchor="w")
        ttk.Entry(frame, textvariable=self.label).pack(fill="x", pady=6)
        ttk.Label(frame, text="Notes · hardware, distance, light conditions, rate and observations").pack(anchor="w")
        self.notes = tk.Text(frame, height=6, font=("Segoe UI", 11), background=PANEL, foreground=INK, insertbackground=CYAN, relief="flat")
        self.notes.pack(fill="x", pady=6)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        for label, callback in (("Save results report", self.save_report), ("Open results folder", lambda: os.startfile(str(self.session.path))), ("Load saved capture", self.load_capture), ("New session", self.new_session)):
            ttk.Button(row, text=label, command=callback).pack(side="left", padx=4)
        ttk.Label(frame, text="All received serial lines, decoded messages and measured metrics are saved automatically as CSV and JSON. Save results report creates an offline HTML report with charts, notes and definitions; open it in a browser and print to PDF for presentations. A new session clears dashboard history without resetting either board. Saved captures and demo data are read-only.", wraplength=1030).pack(anchor="w", pady=12)

    def build_diagnostics(self):
        frame = self.tabs["Diagnostics"]
        self.diagnostics = tk.StringVar()
        ttk.Label(frame, textvariable=self.diagnostics, wraplength=1060).pack(anchor="w")
        self.log = ScrolledText(frame, height=10, font=("Consolas", 9), state="disabled", background=PANEL, foreground=CYAN, insertbackground=CYAN, relief="flat")
        self.log.pack(fill="both", expand=True, pady=8)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.command_role, self.command_text = tk.StringVar(value="TX"), tk.StringVar(value="BUFSTAT")
        ttk.Combobox(row, textvariable=self.command_role, values=("TX", "RX"), width=5, state="readonly").pack(side="left")
        ttk.Entry(row, textvariable=self.command_text).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Send terminal command", command=lambda: self.send_command(self.command_role.get(), self.command_text.get())).pack(side="left")

    def refresh_ports(self):
        names = [p.device for p in list_ports.comports()] if list_ports else []
        for box, var in zip(self.port_boxes, (self.tx_port, self.rx_port)):
            box["values"] = ["(none)"] + sorted(set(names + ([var.get()] if var.get() != "(none)" else [])))

    def connect(self):
        if self.demo or self.replay:
            self.status.set("Read-only demo / saved capture. Start a new live session to connect.")
            return
        if self.worker:
            self.worker.stop.set()
            return
        tx, rx = self.tx_port.get(), self.rx_port.get()
        if tx == rx != "(none)" or tx == rx == "(none)":
            self.status.set("Choose at least one port; TX and RX must use different ports.")
            return
        self.worker = LinkWorker(self.events, tx, rx, polling=self.polling.get())
        self.worker.start()
        self.connect_button.configure(text="Disconnect")
        try:
            (HERE / "vlc_config.json").write_text(json.dumps({"tx": tx, "rx": rx, "ip": self.ip.get()}, indent=2))
        except OSError as error:
            self.status.set(f"Port preferences could not be saved: {error}")

    def set_polling(self):
        if self.worker:
            self.worker.polling = self.polling.get()

    def send_command(self, role, command):
        try:
            if self.demo or self.replay or not self.worker or role not in self.roles:
                raise ValueError(f"Connect {role} first. Demo and saved captures are read-only.")
            self.worker.command(role, command)
            self.status.set(f"Sent to {role}: {command}")
            return True
        except (ValueError, OSError) as error:
            self.status.set(str(error))
            return False

    def numeric(self, role, command, variable, lo, hi):
        try:
            value = int(variable.get())
            if not lo <= value <= hi:
                raise ValueError(f"{command} must be between {lo} and {hi}.")
            return self.send_command(role, f"{command} {value}")
        except ValueError as error:
            self.status.set(str(error))

    def apply_rate(self):
        try:
            value = int(self.rate.get())
            sample = self.metrics.rx.get("sample_hz")
            if not {"TX", "RX"}.issubset(self.roles) or not sample:
                raise ValueError("Connect both boards and read RX STAT before applying a matched rate.")
            if not 500 <= value <= 1000000 or sample < 2 * value:
                raise ValueError("Rate must be 500–1000000 and the configured RX sample rate must be at least 2 × rate. Higher experimental rates can lose decoding.")
            if self.send_command("RX", f"RATE {value}"):
                self.send_command("TX", f"RATE {value}")
        except ValueError as error:
            self.status.set(str(error))

    def apply_sample(self):
        try:
            value = int(self.sample.get())
            rate = self.metrics.rx.get("rate")
            if value not in (100000, 200000, 500000, 1000000, 1600000, 2000000) or not rate or value < 2 * rate:
                raise ValueError("Read RX STAT first; choose a supported sample rate at least 2 × the current RX rate. This is an experimental minimum, not a guarantee of decoding.")
            self.send_command("RX", f"SAMPLE {value}")
        except ValueError as error:
            self.status.set(str(error))

    def apply_order(self):
        if self.order.get() in ("RAW", "SWAP"):
            self.send_command("RX", "ORDER " + self.order.get())
        else:
            self.status.set("Order must be RAW or SWAP.")

    def refresh_measurements(self):
        for role, command in (("TX", "STAT"), ("TX", "NETSTAT"), ("TX", "BUFSTAT"), ("RX", "STAT")):
            if role in self.roles:
                self.send_command(role, command)

    def send_message(self):
        text = self.message_input.get("1.0", "end-1c")
        try:
            if self.demo or self.replay or not self.worker or not self.roles:
                raise ValueError("Connect the boards first; demo / saved capture is read-only.")
            if not text or any(ord(c) < 32 or ord(c) > 126 for c in text):
                raise ValueError("Enter a single line of printable ASCII text.")
            if self.metrics.control.get('requested')=='LOCAL' and not self.message_path.get().startswith('TX USB'):
                raise ValueError('Local VLC mode uses TX USB. Select PLC mode for Wi-Fi ingress.')
            if self.message_path.get().startswith("TX USB"):
                if len(text) > 51:
                    raise ValueError("TX USB accepts at most 51 bytes. Choose Wi-Fi UDP for a longer message.")
                if not self.send_command("TX", "MSG " + text):
                    return
            else:
                self.worker.udp_message(self.ip.get(), 5000, text)
            self.metrics.submitted(text, time.monotonic())
        except (ValueError, OSError, UnicodeError) as error:
            self.status.set(str(error))

    def add_log(self, source, line):
        self.log.configure(state="normal")
        self.log.insert("end", f"{source}: {line}\n")
        if int(self.log.index("end-1c").split(".")[0]) > 2500:
            self.log.delete("1.0", "101.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def consume(self, source, line, at, wall=None):
        wall = wall or timestamp()
        event = self.metrics.consume(source, line, at, wall)
        elapsed = at - self.started
        self.session.record(source, event["kind"], line, elapsed, wall)
        self.add_log(source, line)
        if event["kind"] == "message":
            item = event["message"]
            self.session.message(item, elapsed)
            self.message_table.insert("", "end", values=(wall, item["text"], show(item["observed_delay_ms"], " ms")))
            children = self.message_table.get_children()
            if len(children) > 500:
                self.message_table.delete(children[0])
            self.message_table.see(self.message_table.get_children()[-1])
        fields = event["fields"]
        if event['kind']=='control':
            local=fields.get('requested')=='LOCAL'
            if fields.get('requested')!=self.gateway_reported_source:
                self.gateway_source.set('VLC (local USB)' if local else 'PLC (integrated)')
                self.gateway_reported_source=fields.get('requested')
            self.message_path_combo['values']=('TX USB (51 bytes)',) if local else ('TX USB (51 bytes)','Wi-Fi UDP (1396 bytes)')
            if local:self.message_path.set('TX USB (51 bytes)')
        for kind, key, var in (("rx", "rate", self.rate), ("rx", "sample_hz", self.sample), ("rx", "filter_samples", self.filter), ("buffer", "threshold_pct", self.threshold)):
            token = (kind, key)
            if event["kind"] == kind and key in fields and token not in self.synced:
                var.set(str(fields[key]))
                self.synced.add(token)
        if event["kind"] == "rx" and "order_swapped" in fields and "order" not in self.synced:
            self.order.set("SWAP" if fields["order_swapped"] else "RAW")
            self.synced.add("order")
        if event["kind"] == "network" and fields.get("ip") and fields["ip"] != "0.0.0.0":
            self.ip.set(fields["ip"])

    def render(self, snap):
        age = snap["status_age"]
        control=self.metrics.control
        fresh=age.get('control',999)<=8
        enabled=bool(control) and fresh and 'TX' in self.roles and not self.demo and not self.replay
        for button in self.gateway_buttons:
            button.configure(state='normal' if enabled else 'disabled')
        if control:
            pending=f" → {control.get('requested')} (waiting for DMA)" if control.get('pending') else ''
            self.gateway_status.set(f"Active input: {control.get('source')}{pending}   |   TX mode: {control.get('mode')}   |   DMA in-flight: {show(control.get('inflight'))}\nLocal queue: {show(control.get('local_used'))} / {show(control.get('local_capacity'))} bytes   |   PLC queue retained: {show(control.get('plc_used'))} bytes"+('   · state stale' if not fresh else ''))
        else:
            self.gateway_status.set('Gateway status unavailable. Upload the updated TX sketch and connect its USB port.')
        wifi = "Unknown" if "network" not in age else "Stale" if age["network"] > 8 else "Connected" if self.metrics.network.get("connected") else "Disconnected"
        self.cards["wifi"].set(wifi)
        self.cards["rate"].set(f"{show(snap['tx_bps'])} / {show(snap['rx_bps'])}")
        self.cards["loss"].set(f"{snap['rx_delivery_pct']:.2f}%" if snap["rx_delivery_pct"] is not None else snap["rx_delivery_state"])
        self.cards["throughput"].set(show(snap["fifo_drain_bps"], " bit/s"))
        self.cards["frames"].set(show(snap["rx_good"]))
        self.cards["time"].set(show(None if snap["drain_ms"] is None else snap["drain_ms"] / 1000, " s"))
        self.progress["value"] = snap["buffer_pct"] or 0
        state = "Streaming" if self.metrics.buffer.get("streaming", self.metrics.network.get("streaming")) else "Waiting for threshold"
        self.buffer_text.set(f"Buffer {show(snap['used'])} / {show(snap['capacity'])} bytes · {show(snap['buffer_pct'], '%')} · {state}")
        self.buffer_detail.set(f"Start threshold {show(snap['threshold_pct'], '%')}   |   Last fill {show(snap['fill_ms'], ' ms')}   |   Current fill {show(snap['fill_elapsed_ms'], ' ms')}   |   Current drain {show(snap['drain_elapsed_ms'], ' ms')}   |   Cycles {show(snap['cycles'])}")
        self.latest.set(self.metrics.last_message)
        self.buffer_detail.set(self.buffer_detail.get() + "\nFIFO drainage confirms DMA queueing, not optical reception. Blocking the light does not stop this TX.")
        self.reply.set(self.metrics.command_reply + "\nWi-Fi notification: " + self.metrics.last_buffer_event)
        mismatch = " · RATE MISMATCH" if snap["tx_bps"] and snap["rx_bps"] and snap["tx_bps"] != snap["rx_bps"] else ""
        self.link_detail.set(f"RX frames/s: {show(snap['rx_frames_s'])} · Live delivery window: {show(snap['rx_delivery_interval_s'], ' s')} · {snap['rx_delivery_state']}\nLoss since RX reset: {show(snap['loss_pct'], '%')} · TX/RX status age: {show(age.get('tx'), ' s')} / {show(age.get('rx'), ' s')}{mismatch}\nDelivery = unique CRC-valid packets / (unique valid + sequence gaps) between RX reports. Complete outages show no new RX packets until reception resumes; missing trailing packets are not observed. FIFO throughput includes record metadata.")
        self.diagnostics.set("RX  " + "   ".join(f"{k}={show(self.metrics.rx.get(k))}" for k in ("crc", "man", "timing", "overflows", "read_errors", "locked")) + "\nPLC  " + "   ".join(f"{k}={show(self.metrics.network.get(k))}" for k in ("accepted", "rejected", "last_reject_reason")))

    def draw_chart(self):
        self.chart.delete("all")
        width, height = max(300, self.chart.winfo_width()), 145
        self.chart.create_text(12, 12, anchor="w", text="LIGHT LINK / Buffer occupancy · recent history", fill=GOLD)
        for pct in (0, 50, 100):
            y = 110 - pct * .85
            self.chart.create_line(40, y, width - 15, y, fill="#26465f")
            self.chart.create_text(4, y, anchor="w", text=str(pct), fill=INK)
        points = list(self.history)[-150:]
        segment = []
        for i, item in enumerate(points):
            value = item.get("buffer_pct")
            if value is None:
                if len(segment) >= 4:
                    self.chart.create_line(*segment, fill=CYAN, width=3)
                segment = []
                continue
            segment.extend((40 + i * (width - 55) / max(len(points) - 1, 1), 110 - max(0, min(100, value)) * .85))
        if len(segment) >= 4:
            self.chart.create_line(*segment, fill=CYAN, width=3)

    def tick(self):
        for _ in range(300):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, at = event["kind"], event["at"]
            if kind == "line":
                self.consume(event["role"], event["line"], at)
            elif kind == "connected":
                self.roles = set(event["roles"])
                self.status.set("Connected: " + ", ".join(sorted(self.roles)) + " · reading status; settings preserved")
            elif kind == "closed":
                self.roles.clear()
                self.worker = None
                self.connect_button.configure(text="Connect")
            elif kind in ("command", "error", "notice"):
                line = event.get("line", "")
                self.session.record("HOST", "poll" if event.get("automatic") else kind, line, at - self.started)
                if kind != "command" or not event.get("automatic"):
                    self.add_log("HOST", line)
                if kind == "error":
                    self.status.set("Connection error: " + line)
        now = self.replay_now if self.replay else time.monotonic()
        snap = self.metrics.snapshot(now)
        self.render(snap)
        if not self.replay and now - self.last_sample >= 2:
            self.capture_sample(snap, now)
            self.last_sample = now
        self.root.after(100, self.tick)

    def capture_sample(self, snap, now):
        self.session.sample(snap, now - self.started)
        self.history.append(dict(snap, elapsed_s=now - self.started))
        self.draw_chart()

    def save_report(self, notify=True):
        try:
            self.session.metadata.update(label=self.label.get(), notes=self.notes.get("1.0", "end-1c"))
            now = self.replay_now if self.replay else time.monotonic()
            path = self.session.report(self.metrics.snapshot(now), list(self.history), self.metrics.messages)
            self.footer.set(f"Results saved: {path}")
            if notify:
                messagebox.showinfo("Results saved", f"{path}\n\nOpen report.html in a browser to view or print to PDF.")
            return path
        except OSError as error:
            self.status.set("Could not save results: " + str(error))

    def new_session(self):
        if self.worker:
            self.status.set("Disconnect before starting a new session.")
            return False
        self.save_report(False)
        self.session.close()
        self.metrics = LinkMetrics()
        self.gateway_reported_source = None
        self.history.clear()
        self.synced.clear()
        self.started, self.last_sample = time.monotonic(), -10
        self.replay = False
        self.session = Session(self.base, self.demo, self.label.get())
        self.message_table.delete(*self.message_table.get_children())
        self.footer.set(f"Automatically recording to: {self.session.path}")
        self.mode.set("SYNTHETIC DEMO · no hardware measurements" if self.demo else "PLC Wi-Fi → buffered 2-PPM → optical RX")
        return True

    def load_capture(self, path=None):
        if self.worker:
            self.status.set("Disconnect before loading a saved capture.")
            return
        path = path or filedialog.askopenfilename(title="Load events.jsonl", filetypes=(("VLC capture", "*.jsonl"),))
        if not path:
            return
        try:
            records = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
            for record in records:
                if not isinstance(record.get("elapsed_s"), (int, float)) or not isinstance(record.get("line"), str):
                    raise ValueError("Invalid capture record.")
            source_meta = Path(path).parent / "session.json"
            metadata = json.loads(source_meta.read_text()) if source_meta.exists() else {}
            if not self.new_session():
                return
            self.replay, self.started = True, 0
            self.session.demo = bool(metadata.get("synthetic_demo", False))
            self.session.metadata.update(synthetic_demo=self.session.demo, replayed_from=str(path), saved_capture=True)
            self.label.set(metadata.get("label", "Saved VLC capture"))
            self.notes.delete("1.0", "end")
            self.notes.insert("1.0", metadata.get("notes", ""))
            self.mode.set("SAVED CAPTURE · read-only" + (" · SYNTHETIC DEMO" if self.session.demo else ""))
            last = -10
            self.replay_now = 0
            for record in records:
                at = record["elapsed_s"]
                if record.get("source") in ("TX", "RX"):
                    self.consume(record["source"], record["line"], at, record.get("timestamp"))
                    self.replay_now = max(self.replay_now, at)
                    if at - last >= 2:
                        self.capture_sample(self.metrics.snapshot(at), at)
                        last = at
            self.session.save_metadata()
            self.status.set(f"Loaded {len(records):,} capture records. No board commands sent.")
        except (OSError, ValueError, TypeError) as error:
            self.status.set("Could not load capture: " + str(error))

    def demo_tick(self):
        if not self.replay:
            self.demo_step += 1
            n, at = self.demo_step, time.monotonic()
            used = min(n * 3700, 109568)
            for source, line in (("TX", f"TX STAT rate=75000 completed={40*n} inflight=1"),
                    ("TX", "PLC NET connected=1 ip=192.168.0.100 port=5000 buffer=109568 accepted=100 rejected=0 streaming=1"),
                    ("TX", f"PLC BUFFER capacity=109568 used={used} threshold_pct=5 streaming=1 fill_ms=3100 drain_ms=2200 cycles=2 enqueued_bytes={1200*n+used} dequeued_bytes={1200*n}"),
                    ("RX", f"RX STAT rate=75000 good={39*n} missed={n} duplicates=0 crc=0 man=0 timing=0 overflows=0 locked=1 sample_hz=1000000 filter_samples=2 order_swapped=0")):
                self.consume(source, line, at)
            if n % 3 == 0:
                self.consume("RX", f"RX message: Demo message {n//3}", at)
        self.root.after(1000, self.demo_tick)

    def close(self):
        if self.worker:
            self.worker.stop.set()
            self.worker.join(timeout=1)
        self.save_report(False)
        self.session.close()
        self.root.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Clearly labelled synthetic data; does not connect to hardware")
    args = parser.parse_args()
    window = tk.Tk()
    Dashboard(window, args.demo)
    window.mainloop()
