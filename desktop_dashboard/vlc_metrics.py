"""Metrics for the current 2-PPM firmware. No hardware dependencies."""
import re
from collections import deque


def parse(source, line):
    if source == "RX" and line.startswith("RX message: "):
        return {"kind": "message", "source": source, "line": line, "text": line[12:], "fields": {}}
    fields = dict(re.findall(r"\b([a-z_]+)=([^\s]+)", line))
    for key, value in list(fields.items()):
        if re.fullmatch(r"-?\d+", value):
            fields[key] = int(value)
    kind = "log"
    for prefix, event_kind in (("PLC NET ", "network"), ("PLC BUFFER ", "buffer"), ("VLC BUFFER ", "buffer_event"),
                               ("TX STAT ", "tx"), ("2PPM TX ", "tx"), ("TX CONTROL ", "control"),
                               ("RX STAT ", "rx"), ("CAL ", "calibration")):
        if line.startswith(prefix) and source == ("RX" if event_kind in ("rx", "calibration") else "TX"):
            kind = event_kind
            break
    return {"kind": kind, "source": source, "line": line, "fields": fields}


def counter_rate(reports, key):
    selected = [(t, f[key]) for t, f in reports if isinstance(f.get(key), int)]
    if len(selected) < 2:
        return None
    elapsed = selected[-1][0] - selected[0][0]
    delta = selected[-1][1] - selected[0][1]
    return delta / elapsed if elapsed > 0 and delta >= 0 else None


class LinkMetrics:
    def __init__(self):
        self.tx, self.rx, self.buffer, self.network, self.calibration = {}, {}, {}, {}, {}
        self.control={}
        self.seen = {}
        self.tx_reports, self.rx_reports, self.buffer_reports = deque(), deque(), deque()
        self.messages = deque(maxlen=5000)
        self.pending = deque(maxlen=200)
        self.command_reply = "No message submitted"
        self.resets = 0
        self.last_message = "Waiting for a CRC-valid decoded message"
        self.last_buffer_event = "No Wi-Fi buffer event observed"

    def consume(self, source, line, now, wall=""):
        event = parse(source, line)
        kind, fields = event["kind"], event["fields"]
        if kind == "buffer_event":
            self.last_buffer_event = f"{fields.get('event', '?')} / {fields.get('direction', '?')} · occupancy {fields.get('fill_pct', '?')}% at send time"
        if source == "RX" and (line == "RX RESET" or line.startswith(("RX RATE APPLIED", "RX SAMPLE APPLIED", "RX FILTER APPLIED", "RX ORDER APPLIED", "RX CLOCK APPLIED"))):
            self.rx.clear()
            self.rx_reports.clear()
            self.seen.pop("rx", None)
            self.resets += 1
        if kind in ("tx", "rx", "buffer", "network", "calibration", "control"):
            self.seen[kind] = now
            target = getattr(self, kind)
            primary = {"tx": "completed", "rx": "good", "buffer": "enqueued_bytes"}.get(kind)
            reports = getattr(self, kind + "_reports", None)
            if reports is not None:
                if primary in fields and primary in target and fields[primary] < target[primary]:
                    reports.clear()
                    self.resets += 1
                reports.append((now, dict(fields)))
            target.update(fields)
        if kind == "message":
            text = event["text"]
            observed_delay = None
            # Text matching is a host observation, not a uniquely identified
            # optical acknowledgement. Duplicate PLC text can be ambiguous.
            for index, request in enumerate(self.pending):
                if request["text"] == text and now >= request["at"]:
                    observed_delay = (now - request["at"]) * 1000
                    del self.pending[index]
                    break
            item = {"at": now, "timestamp": wall, "text": text,
                    "observed_delay_ms": observed_delay, "bytes": len(text.encode("utf-8"))}
            self.messages.append(item)
            self.last_message = text
            event["message"] = item
        if source == "TX" and ("queued" in line.lower() or line.startswith("QUEUED ")):
            self.command_reply = "Accepted into TX queue; optical delivery not yet confirmed"
        if source == "TX" and ("REJECT" in line or "REJECTED" in line):
            self.command_reply = line
        return event

    def submitted(self, text, now):
        self.pending.append({"text": text, "at": now})
        self.command_reply = "Submitted; waiting for queue acknowledgement / decoded text"

    def snapshot(self, now):
        for reports in (self.tx_reports, self.rx_reports, self.buffer_reports):
            while reports and reports[0][0] < now - 30:
                reports.popleft()
        recent = [m for m in self.messages if m["at"] >= now - 10]
        tx_rate = counter_rate(self.tx_reports, "completed")
        rx_rate = counter_rate(self.rx_reports, "good")
        queue_rate = counter_rate(self.buffer_reports, "dequeued_bytes")
        ingress_rate = counter_rate(self.buffer_reports, "enqueued_bytes")
        loss = None
        loss_basis = "Unavailable until RX sequence counters are reported"
        good, missed, duplicates = (self.rx.get(k) for k in ("good", "missed", "duplicates"))
        if all(isinstance(v, int) for v in (good, missed, duplicates)) and good > 0:
            expected = max(0, good - duplicates) + missed
            if expected:
                loss = 100 * missed / expected
                loss_basis = "RX sequence gaps since RX counter reset; trailing loss is not observed"
        ratio = None
        if tx_rate is not None and rx_rate is not None and tx_rate > 0:
            ratio = 100 * rx_rate / tx_rate
        capacity = self.buffer.get("capacity", self.network.get("buffer"))
        used = self.buffer.get("used", self.network.get("used"))
        latest_delay = next((m["observed_delay_ms"] for m in reversed(self.messages)
                             if m["observed_delay_ms"] is not None), None)
        status_age = {k: max(0, now - t) for k, t in self.seen.items()}
        if status_age.get("buffer", status_age.get("network", 999)) > 8:
            used = None
        if status_age.get("buffer", 999) > 8:
            queue_rate = ingress_rate = None
        if status_age.get("rx", 999) > 8:
            rx_rate = None
        if status_age.get("tx", 999) > 8:
            tx_rate = None
        # Use board counters, never the throttled text log. Latest two reports
        # make degradation visible at the existing STAT polling cadence.
        delivery = None
        delivery_seconds = None
        delivery_state = "Waiting for two RX reports"
        if status_age.get("rx", 999) > 8:
            delivery_state = "RX status unavailable or stale"
        elif len(self.rx_reports) >= 2:
            (t0, before), (t1, after) = list(self.rx_reports)[-2:]
            keys = ("good", "missed", "duplicates")
            if t1 > t0 and all(isinstance(f.get(k), int) for f in (before, after) for k in keys):
                dg, dm, dd = (after[k] - before[k] for k in keys)
                if min(dg, dm, dd) >= 0 and dg >= dd:
                    delivery_seconds = t1 - t0
                    unique = dg - dd
                    expected = unique + dm
                    if expected:
                        delivery = 100 * unique / expected
                        delivery_state = "Receiving" if unique else "No new valid RX packets"
                    else:
                        delivery_state = "No new RX packets"
        return {
            "tx_bps": self.tx.get("rate"), "rx_bps": self.rx.get("rate"),
            "rx_good": good, "tx_completed": self.tx.get("completed"),
            "loss_pct": loss, "loss_basis": loss_basis,
            "rx_delivery_pct": delivery,
            "rx_delivery_interval_s": delivery_seconds,
            "rx_delivery_state": delivery_state,
            "rx_frames_s": rx_rate, "tx_frames_s": tx_rate,
            "delivery_rate_pct": ratio,
            "fifo_drain_bps": None if queue_rate is None else queue_rate * 8,
            "fifo_ingress_bps": None if ingress_rate is None else ingress_rate * 8,
            "displayed_rx_bps": sum(m["bytes"] for m in recent) * 8 / 10,
            "displayed_rx_basis": "Displayed text only; firmware throttles message logs",
            "capacity": capacity, "used": used,
            "buffer_pct": 100 * used / capacity if capacity and used is not None else None,
            "fill_ms": self.buffer.get("fill_ms"), "drain_ms": self.buffer.get("drain_ms"),
            "fill_elapsed_ms": self.buffer.get("fill_elapsed_ms"),
            "drain_elapsed_ms": self.buffer.get("drain_elapsed_ms"),
            "threshold_pct": self.buffer.get("threshold_pct"),
            "cycles": self.buffer.get("cycles"),
            "observed_delay_ms": latest_delay, "status_age": status_age,
            "counter_resets": self.resets,
            "gateway_source": self.control.get("source"),
            "gateway_requested": self.control.get("requested"),
            "gateway_mode": self.control.get("mode"),
            "local_used": self.control.get("local_used"),
            "local_capacity": self.control.get("local_capacity"),
        }
