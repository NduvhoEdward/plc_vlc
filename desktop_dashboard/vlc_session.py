"""Append-only capture files and a self-contained, printable results report."""
import csv
import datetime as dt
import html
import json
import pathlib
import uuid

SAST = dt.timezone(dt.timedelta(hours=2), "SAST")


def timestamp():
    return dt.datetime.now(dt.timezone.utc).astimezone(SAST).isoformat(timespec="milliseconds")


class Session:
    def __init__(self, base, demo=False, label="VLC experiment"):
        stamp = dt.datetime.now(dt.timezone.utc).astimezone(SAST).strftime("%Y%m%d_%H%M%S")
        self.path = pathlib.Path(base) / (stamp + "_" + uuid.uuid4().hex[:6])
        self.path.mkdir(parents=True)
        self.demo = demo
        self.metadata = {"label": label, "started": timestamp(), "timezone": "Africa/Johannesburg",
                         "synthetic_demo": demo, "notes": "", "firmware_modified_by_dashboard": False}
        self.raw = (self.path / "events.jsonl").open("w", encoding="utf-8", buffering=1)
        self.lines = (self.path / "logs.csv").open("w", newline="", encoding="utf-8-sig", buffering=1)
        self.log_writer = csv.writer(self.lines)
        self.log_writer.writerow(("timestamp", "elapsed_s", "source", "kind", "line"))
        self.samples_file = (self.path / "metrics.csv").open("w", newline="", encoding="utf-8-sig", buffering=1)
        self.sample_writer = None
        self.messages_file = (self.path / "messages.csv").open("w", newline="", encoding="utf-8-sig", buffering=1)
        self.message_writer = csv.writer(self.messages_file)
        self.message_writer.writerow(("timestamp", "elapsed_s", "decoded_text", "bytes", "observed_text_match_delay_ms"))
        self.save_metadata()

    def save_metadata(self):
        (self.path / "session.json").write_text(json.dumps(self.metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(self, source, kind, line, elapsed, wall=None):
        event = {"timestamp": wall or timestamp(), "elapsed_s": round(elapsed, 6),
                 "source": source, "kind": kind, "line": line}
        self.raw.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.log_writer.writerow((event["timestamp"], event["elapsed_s"], source, kind, line))

    def sample(self, snapshot, elapsed):
        row = {"timestamp": timestamp(), "elapsed_s": round(elapsed, 3)}
        row.update({k: v for k, v in snapshot.items() if not isinstance(v, dict)})
        if self.sample_writer is None:
            self.sample_writer = csv.DictWriter(self.samples_file, fieldnames=list(row))
            self.sample_writer.writeheader()
        self.sample_writer.writerow(row)

    def message(self, item, elapsed):
        self.message_writer.writerow((item["timestamp"], round(elapsed, 6), item["text"], item["bytes"], item["observed_delay_ms"]))

    def close(self):
        for file in (self.raw, self.lines, self.samples_file, self.messages_file):
            if not file.closed:
                file.close()
        self.save_metadata()

    def report(self, snapshot, samples, messages):
        self.save_metadata()
        # Reports cover the entire capture, even after the live chart's history limit.
        self.samples_file.flush()
        with (self.path / "metrics.csv").open(encoding="utf-8-sig", newline="") as file:
            captured = list(csv.DictReader(file))
        if captured:
            samples = []
            for row in captured:
                item = {}
                for key, value in row.items():
                    try:
                        item[key] = float(value) if value else None
                    except (ValueError, TypeError):
                        item[key] = value
                samples.append(item)
        (self.path / "summary.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        escape = lambda value: html.escape(str(value))
        def number(value, suffix=""):
            return "Not available" if value is None else f"{value:,.2f}{suffix}" if isinstance(value, (int, float)) else escape(value)
        def chart(key, title, unit, color):
            finite = [(x["elapsed_s"], x.get(key)) for x in samples if isinstance(x.get(key), (int, float))]
            if len(finite) < 2:
                return f'<section><h2>{escape(title)}</h2><p>Not enough measured samples.</p></section>'
            lo, hi = finite[0][0], finite[-1][0]
            ymax = max(v for _, v in finite) or 1
            segments, segment = [], []
            for item in samples:
                value = item.get(key)
                if not isinstance(value, (int, float)):
                    if segment:
                        segments.append(segment)
                    segment = []
                else:
                    t = item["elapsed_s"]
                    segment.append(f"{50+(t-lo)/max(hi-lo,1)*670:.1f},{200-value/ymax*160:.1f}")
            if segment:
                segments.append(segment)
            polylines = ''.join(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="3"/>' for segment in segments)
            return f'''<section><h2>{escape(title)}</h2><svg viewBox="0 0 760 240" role="img" aria-label="{escape(title)}">
              <path d="M50 30V200H730" fill="none" stroke="#ccd5df"/>
              {polylines}
              <text x="50" y="22">{ymax:.2f} {escape(unit)}</text><text x="50" y="225">{lo:.1f} s</text>
              <text x="660" y="225">{hi:.1f} s</text></svg></section>'''
        fields = (("TX bit rate", "tx_bps", " bit/s"), ("RX bit rate", "rx_bps", " bit/s"),
                  ("RX CRC-valid frames", "rx_good", ""), ("TX completed frames", "tx_completed", ""),
                  ("Live RX packet delivery", "rx_delivery_pct", "%"), ("Live delivery observation window", "rx_delivery_interval_s", " s"),
                  ("RX sequence-gap loss", "loss_pct", "%"), ("FIFO drain throughput", "fifo_drain_bps", " bit/s"),
                  ("Buffer capacity", "capacity", " bytes"), ("Last fill time", "fill_ms", " ms"),
                  ("Last drain time", "drain_ms", " ms"))
        rows = "".join(f"<tr><th>{label}</th><td>{number(snapshot.get(key),unit)}</td></tr>" for label,key,unit in fields)
        message_rows = "".join(f"<tr><td>{escape(m['timestamp'])}</td><td>{escape(m['text'])}</td><td>{number(m['observed_delay_ms'],' ms')}</td></tr>" for m in list(messages)[-200:])
        banner = '<p class="demo">SYNTHETIC DEMO — not hardware measurements</p>' if self.demo else ""
        content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <title>VLC results — {escape(self.metadata['label'])}</title><style>
        body{{font:16px system-ui,sans-serif;color:#203246;background:#eef3f8;margin:0;padding:36px}}
        main{{max-width:1000px;margin:auto;background:white;padding:36px;border-radius:18px}}
        h1{{color:#087b81;margin-bottom:8px}}h2{{font-size:20px}}p{{line-height:1.6}}table{{border-collapse:collapse;width:100%;margin:18px 0}}
        th,td{{text-align:left;border-bottom:1px solid #dce4ec;padding:10px;overflow-wrap:anywhere}}th{{width:40%}}
        .notes{{white-space:pre-wrap}}.demo{{background:#fff0c9;padding:14px}}svg{{width:100%;max-height:280px}}section{{break-inside:avoid}}
        @media print{{body{{background:white;padding:0}}main{{padding:0}}}}</style><main>
        <h1>VLC experiment results</h1><h2>{escape(self.metadata['label'])}</h2>{banner}
        <p>Started {escape(self.metadata['started'])} · Africa/Johannesburg<br>Saved {timestamp()}</p>
        <table>{rows}</table>
        <h2>Experiment notes</h2><p class="notes">{escape(self.metadata['notes']) or 'No notes recorded.'}</p>
        {chart('buffer_pct','Buffer occupancy','%','#087b81')}
        {chart('fifo_drain_bps','Measured FIFO drain throughput','bit/s','#3564b0')}
        {chart('loss_pct','RX sequence-gap loss','%','#c97b16')}
        {chart('rx_delivery_pct','Live RX packet delivery','%','#087b81')}
        <h2>Decoded message observations (latest 200)</h2><table><tr><th>Reception timestamp</th><th>Decoded text</th><th>Text-match delay</th></tr>{message_rows}</table>
        <h2>Measurement definitions</h2><p>FIFO throughput uses TX queue-byte counter deltas and includes record-length metadata; it is not exact optical payload throughput.
        Live RX delivery uses unique CRC-valid packet counter deltas divided by unique valid packets plus newly observed sequence gaps between the latest two RX status reports. It does not use displayed messages. No new packets or stale status is shown as unavailable rather than a misleading 100%. Gaps during a complete outage become countable only when reception resumes. RX sequence-gap loss uses board counters since their last reset and cannot detect missing trailing frames. RX message logs are throttled, so displayed-text throughput is a lower bound.
        Text-match delay measures host submission to an equal decoded text observation, includes queueing and logging delays, and may be ambiguous for repeated messages; it is not synchronized end-to-end latency.
        Buffer fill/drain times are firmware stage measurements. Missing data is shown as unavailable, never zero. Wi-Fi connected status establishes AP association, not proof the PLC is currently sending.</p>
        <p>Raw capture: logs.csv · metrics.csv · messages.csv · events.jsonl · session.json · summary.json</p></main></html>'''
        path = self.path / "report.html"
        path.write_text(content, encoding="utf-8")
        return path
