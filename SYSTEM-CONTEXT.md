# PLC/VLC mobile control handover — 13 October 2026

## User requirements
Use the original receiver dashboard from Experiments/scripts/VLC/text_image_vlc_dashboard.
Preserve the TX connection and mobile control experience. Do not replace that dashboard with the newer browser presentation.
Visitor-facing diagrams/copy describe PLC adapter → VLC TX without naming or depicting the intervening radio link.

## Physical and cloud route
Sender PC internet connection is separate from its dedicated HomePlug Ethernet connection.
Sender PC → Ethernet → HomePlug pair / powerline → TX network endpoint 192.168.0.100 UDP 5000 → LED → photodiode RX → receiver PC USB.
TX uses its existing HomePlug AP connection. This implementation detail belongs in technical handover only.
Both PCs make outbound authenticated WebSocket connections to https://internet-of-light-relay.nduvho-ramashia.workers.dev.
Website: https://plc-vlc.pages.dev ; GitHub: NduvhoEdward/plc_vlc.
The sender uses /agent, receiver /receiver, visitors /ws after Turnstile verification (guest passcode is currently disabled).

## Critical ownership rules
1. Exactly ONE sender bridge may own the relay /agent role. A second connection receives HTTP 409.
2. Exactly ONE receiver bridge may own /receiver and open RX USB.
3. Original dashboard in mobile receiver mode NEVER opens serial, subscribes to TX UDP, or changes board settings.
4. The receiver bridge reads RX USB at 115200 with DTR/RTS false, polls STAT and forwards received records to the relay.
5. It exposes a bounded raw RX observation feed at localhost:8765/events?after=N. The dashboard reads this loopback feed through ObservationWorker. The feed contains actual serial lines; no source pixels are substituted.
6. Do not launch legacy pixel_dashboard.py alongside the bridge: its LinkWorker tries to open serial. Use mobile_receiver_dashboard.py, opened automatically by receiver START.cmd.
7. GUI and cloud protocol modules have the same filename but different APIs. GUI runs in a separate process with its own dashboard module directory; do not import its pixel_protocol into the agent process.
8. Do not run an old background run_demo.py service alongside a package. Old service PID metadata lives in mobile-control/.service-pids.json. Verify executable/command line before stopping only those services.

## Firmware / TX invariants
Firmware under Experiments/scripts/VLC/300kbps is unchanged.
Observed live optical rate is 280000 bit/s; package pacing estimate 280000 does not change firmware.
TX retains AUTO and roughly 75% FIFO priming. Do not issue START, SOURCE, buffer-threshold, rate, calibration or RX RESET commands automatically.
Sender alone subscribes to UDP feedback with VLC_STATUS SUBSCRIBE, pauses on stale/full feedback, and paces duplicate 51-byte records until RX acknowledges required records.
Another producer / subscriber can disturb priming or steal status feedback. Do not run independent dashboard transmitters while demonstrating mobile control.
Cancellation may leave queued records which must drain/reconcile. Do not unlock controls or replay an interrupted transfer blindly.

## What completion means
Mobile text uses TX1 with transfer ID and CRC16. Images use existing PH2/PD2 records (legacy PX1 also recognized by original dashboard).
A mobile result is confirmed only after received records reconstruct the submitted payload, hash matches, and hardware reports idle.
PLC transfer alone confirms ingress, not optical reception.
The original dashboard independently reconstructs checksum-valid images from RX. It does not possess the visitor's submitted source/hash, so mobile website is authoritative for source-match confirmation.
GUI mobile mode is read-only for board control; stats, received pictures/text, logs and saved reports stay available.
Native GUI shows actual receiver observations even if the visitor has not chosen public display sharing. Public sharing still requires the original opt-in.

## Packages and launchers
Credential-free source: mobile-control-repository/packaging, agent, desktop_dashboard.
Original GUI base modules are copied unchanged to desktop_dashboard; mobile_observer.py and mobile_receiver_dashboard.py are adapters.
Receiver START.cmd opens the original GUI immediately using bundled Python 3.12/Tk/Pillow, then runs the portable bridge with Python 3.13 and detects RX by RX STAT (not fixed COM10). Do not open the receiver browser monitor automatically; visitors must see the original desktop dashboard. OPEN-DASHBOARD.cmd can reopen the GUI without becoming another serial owner.
Sender START.cmd detects TX feedback; Ethernet setup may require UAC. It adds 192.168.0.10/24 without a default gateway and has a restore helper.
Both launchers have localhost status dashboards: sender 8766, receiver 8767.
STOP.cmd sends a local protected-header stop request to that role's launcher; only its child bridge and GUI stop.
Closing the original GUI does not stop the bridge; STOP.cmd stops the package.
RX serial errors restart detection; they must not leave a dead USB reader repeatedly claiming receiver readiness.
USB drivers, physical connections, internet and optical alignment must already be available. Portable packages cannot fix missing physical connections.

## Files and secrets
Private operational folder: mobile-control. Its *-credentials.json and .demo-secrets.json must stay private.
Passcode record: mobile-control/DEMO-PASSCODE.txt. Do not copy credentials into frontend code, GitHub, screenshots, logs or handover documents.
Private ZIPs contain only the appropriate role credential. Never push or share them with visitors.
Build into a NEW output folder while packages run; Windows locks runtime DLLs in active folders.
Original dashboard sessions/results and source experiments must be preserved; package GUI writes its own dashboard/results.

## Incident history
HTTP InvalidStatus on sender was an older background sender occupying /agent. It was stopped; packaged sender connected.
Rig flicker was an older receiver reconnecting after SerialException. That background receiver was stopped.
At handover, previous run_demo service PID records are zero. A sender package may still be running; inspect localhost:8766/state before starting another.
An unrelated website clock freshness fix and tests were prepared locally but NOT published after approval review rejected a website change for a PC-dashboard problem. Do not stage those unrelated files by accident.
Verify current Git status and deployment before claiming anything is live.

## Verification before future changes
Run bridge/protocol tests and observation feed tests. Check serial owner exclusivity and rejection of GUI board writes.
Check Tk/Pillow using the receiver package's GUI runtime; bridge self-check uses its separate portable runtime.
Test /events with duplicate/missing/out-of-order optical records. Missing raw events must not be treated as complete reception.
Do not use demo/synthetic data as evidence of physical optical success.
After any physical changes, test short text and a 32x16 image and verify RX hash plus idle hardware.

## Guest access and custom domain — 15 October 2026

The user requested guest passcode removal to reduce friction. REQUIRE_PASSCODE=false disables only guest passcode checking; Turnstile, signed visitor sessions, queue limits and private sender/receiver credentials remain required. JOIN_PASSCODE is retained privately for possible restoration; restoring it also requires restoring the frontend input.

The new visitor address is https://hpv.selah.net.za. Hosting stays on Cloudflare Pages (plc-vlc project); Vercel remains authoritative DNS for selah.net.za. The hpv CNAME points to plc-vlc.pages.dev; do not move nameservers or the main Selah site. The relay allows both exact origins during transition and verifies Turnstile against the joining origin hostname. Sender and receiver URLs/tokens are unchanged; packages do not need replacing for guest access/domain changes.

Enable the production pages.dev redirect only after the custom domain HTTPS service works. Preserve paths/query strings and avoid redirect loops. Existing unrelated website freshness edits in mobile-control-repository remain unpublished; this task is isolated in mobile-control-domain.

Deployment verified on 15 October 2026: Cloudflare custom domain is active; hpv.selah.net.za serves HTTPS; production pages.dev GET/HEAD links redirect with 302 preserving paths and query strings. Guest joining without passcode was verified in the browser, with Turnstile and signed session intact. Working source for this change is mobile-control-domain (isolated Git worktree); mobile-control-repository retains unrelated local edits and must be updated carefully before future deployments.


## Visitor studio redesign — 15 October 2026

The public studio opens in live mode with drawing selected at 128 x 64. Turnstile automatically connects the visitor; it does not acquire a control turn. A single explicit Send captures an immutable payload and sharing choice, joins the queue once and dispatches once when that visitor becomes ready controller. Never turn automatic connection into automatic queue joining or transfer replay.

QueuedSend in public/visitor-flow.js owns the pending send intent. Cancellation, pre-dispatch disconnection or hardware becoming unavailable cancels that intent and keeps the draft. Already submitted transfers stay locked for the existing server reconciliation and real receiver hash plus idle confirmation. Async hashing is guarded against cancellation. Queue wait estimates are approximate (30–60 seconds per place), not measured delivery promises.

The canvas and primary Send are first; preview and technical settings are collapsed. Hardware absence is shown as a paused demonstration, distinct from checking the phone connection. Practice remains explicitly simulated under Details. Sharing remains opt-in. No bridge, firmware, credentials or original RX dashboard ownership was changed.

Guest QR target: https://hpv.selah.net.za/send . Printable sign: https://hpv.selah.net.za/visit ; PNG/SVG at /assets/studio-qr.png and /assets/studio-qr.svg. Keep the project homepage available for background information.

Offline visitor alternative: the paused notice offers Try a practice demo. It retains the draft, explicitly labels simulation, and offers Return to the live rig. Mode switching stays disabled during queued or active sends.

Visual transfer route: Send reveals phone -> PC -> PLC TX -> PLC RX -> VLC TX -> VLC RX -> message recipient. The relay is omitted from this visitor diagram, and the explanatory note beneath it is removed. public/transfer-route.js maps existing stages; PLC hops share the reported PLC stage, with no invented per-adapter telemetry. Active lines pulse (reduced-motion disables animation), completed lines turn green. Optical completion requires complete() after receiver payload verification; a raw confirmed stage alone cannot finish the optical line. Disconnections and stopped transfers stop pulsing. Practice route is explicitly labelled simulated. No new hardware commands or connections.

PLC forwarding and optical reception overlap: keep both PLC links active during vlc, completing them conservatively only at verified final confirmation. The existing vlc report means first RX observation, not all PLC bytes admitted.

The final recipient link turns green only on verified completion; receiving optical records alone does not indicate delivery to the recipient.
