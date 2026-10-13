# Internet of Light

## Live two-laptop demonstration

See [DEMO.md](DEMO.md) for setup and rehearsal. TX now uses its existing UDP buffer feedback without USB; a separate receiving laptop forwards RX USB observations through the relay. Run `python launch_bridge.py` on each laptop with its private role-specific credential file. The mobile studio adds partial-image reception, live buffer/RX statistics, and optional sharing of verified results.


A buildless, mobile-first project website based on the supplied ELEN4012A HTML. The public site has no paid dependencies, subscriptions, API calls, advertisements, or accounts in demo mode.

## Open locally

Double-click `launch-preview.cmd` on this computer, then visit `http://127.0.0.1:4173`. On another computer install Node.js 22.13 or later, then run:

```powershell
node preview.mjs
```

Use an HTTP server rather than double-clicking the HTML: the studio uses JavaScript modules. The preview server binds to this computer's loopback interface only. It does not open your laptop to phones or the internet. Phones use the deployed HTTPS site.

## What is included

- `public/index.html`: project showcase, original signal-chain SVG and buffer simulator, actual receiver circuit drawings, recorded optical results.
- `public/send.html`: text, local photo conversion, touch drawing/undo, preview, payload download, simulated transfers and live connection UI.
- `relay/`: Cloudflare Worker, SQLite-backed Durable Object, authenticated WebSockets, Turnstile, invitation passcode, rate limits, controller queue and lease, private transfer results, checksums, reconnect locking.
- `agent/`: outbound Python agent; simulated agent by default; network-only TX adapter with UDP feedback and a separate RX USB bridge; the older combined-USB adapter remains available.
- `tests/`: relay/authentication/controller tests and Python protocol/reconnect tests.
- `HOSTING.md`: free hosting and live-rig setup.

Demo mode works immediately in a browser and transmits nothing externally. Image originals are decoded and reduced on the device. Drawings and text drafts are saved in that browser's local storage when available. Uploaded originals are held in memory only.

The phone studio has separate **Create & send** and **Monitor link** views. A persistent bottom bar holds preview, send, cancel and queue actions, while connection and controller status stay visible during scrolling. Phone submission first brings the actual payload into view. Monitoring shows public link/activity status while keeping received content private unless its sender explicitly chooses to share a verified result. Layouts handle portrait, landscape, safe areas and keyboard viewport changes.

## Limits and image format

The existing hardware carries printable optical text records of up to 51 bytes. The web agent wraps text in a transfer-specific `TX1:<8 hex ID>:<text>:<CRC16>` record, so messages are limited to 30 printable ASCII characters. The receiver firmware still receives ordinary printable text. The web agent interprets the envelope from `RX message:` output; the older dashboard will show the envelope literally.

Images use the existing PH2/PD2 monochrome framing, copied from `text_image_vlc_demo/dashboard/pixel_protocol.py` without modifying the original. Supported image sizes are 32×16, 64×32, and 128×64, corresponding to 64, 256, and 1,024 packed bytes. Resolution, threshold and aspect-ratio fitting are visible in the editor. JPEG/PNG/WebP originals are limited to 8 MB and 40 megapixels; never uploaded. Packed payload JSON stays below 4 KB, so a bounded authenticated WebSocket frame suffices. There is no R2 bucket or large binary upload endpoint.

For genuine full-colour JPEG transfer, larger pictures, Unicode messages, or arbitrary files, extend and validate the firmware/adapter first. Do not increase frontend limits independently.

## State and privacy

- One rig, at most 80 connected sockets and 30 queued visitors.
- Each control lease lasts 60 seconds. Submission must occur within that turn.
- An active physical transfer owns the rig until an authenticated agent reports completion **and hardware idle**. Lease expiry, browser disconnect, and agent disconnect cannot unlock it.
- Transfers time out into a cancellation request after 3 minutes. Queued content is removed after 15 minutes even if the rig remains locked. The team must restore idle feedback for a disconnected rig; the relay never guesses that it stopped.
- Active payloads are stored in the Durable Object until completion/cancellation/expiry. Completed payloads are removed immediately; small duplicate tombstones expire after one hour.
- Received fragments go only to the submitting session. Verified results are broadcast to connected viewers and the receiver presentation only when the submitting visitor explicitly opts in. Viewer status uses random short-lived session IDs, never names or IP addresses.
- Browser session credentials expire after one hour, stay in memory, and are sent as a WebSocket subprotocol instead of URL query parameters. Rejoin with Turnstile after expiry.
- Hashed IP rate counters expire after ten minutes. Agent deduplication uses a local SQLite ledger; receiver data expires from that ledger after fifteen minutes, with one-hour ID tombstones.
- A completed receiver payload lost during a disconnect is not retained for later download; reconnect shows completion context without silently repeating it.

No UI for remote modulation/duty-cycle changes is exposed because firmware bounds and variants must be verified. The website controls transfer and cancellation only. Mains-connected noise sources remain manual.

## Hardware adapters

The new `--network-tx` adapter uses UDP5000 status snapshots: capacity, occupancy,
threshold, streaming and frames in flight. TX stays in existing PLC/AUTO mode;
repeated identified records prime its 75% gate. No firmware, rate, threshold,
source or calibration changes are made. The separate `agent/receiver.py`
forwards actual RX serial records and read-only STAT feedback. The relay arms
the receiver before each transfer; received records and matching payload hashes
determine confirmation.

Cancellation stops producing new records, but an owned buffer below the AUTO
gate may need additional duplicates to start and drain. Controls remain locked
until fresh feedback confirms no queued bytes or frames in flight. A restarted
sender does not automatically replay a payload or fill an unknown nonempty queue.

The sending laptop must sit upstream of the physical HomePlug pair. Wi-Fi
reachability alone does not prove traversal of the powerline segment. Keep
other producers and serial dashboards closed.

The older `--hardware` adapter requires TX and RX USB and uses existing
CONTROL/SOURCE/START/AUTO commands. See its implementation for that route.

Connected-board acceptance on 13 October 2026 used the existing 280000 bit/s
settings and network-only TX: text, 32×16, 64×32 and 128×64 reconstructed exactly.
Image times including priming and drain were 6.281, 9.578 and 20.657 seconds.
A deployed-cloud acceptance then verified text and a 64×32 image through
separate authenticated bridge connections. Public browser/Turnstile joining and
the final physical arrangement still need phone rehearsal.

## Verification

Run:

```powershell
node --experimental-loader ./tests/cloudflare-loader.mjs --test tests/relay.test.js
python -m unittest discover -s tests -p test_agent.py -v
```

The Cloudflare base class is stubbed in unit tests. These tests verify application logic, not Cloudflare deployment behaviour. A real Worker deployment, Turnstile join, multi-phone queue, disconnect/cancel/reconcile sequence and actual PLC → VLC transmission remain deployment acceptance steps.

See `VALIDATION.md` for checks performed in this workspace.

## Updating images and team details

See [EDITING.md](EDITING.md) for GitHub upload steps, ready-to-copy gallery and team cards, mobile image sizes, and project text locations.

## Shared image-loss challenge

The homepage now offers practice and ranked rounds. The same calm, busy and harsh model traces are used for every player. Scores are calculated again in `functions/api/game.js`, then the average of all three attempts enters the shared top-20 board. The game uses Cloudflare Pages Functions with the free-plan D1 database binding `GAME_DB`, configured in `wrangler.jsonc`. It is separate from the live rig relay; no hardware or agent secret is used.

Nicknames are public, limited to 24 characters, and rendered as text. Unfinished rounds do not appear. Attempts must be sequential, repeat submissions are idempotent, and capacity values are validated. A daily hashed network key limits starts to 100 per network/day; old rows are cleaned up after 30 days. This is an educational scoreboard, not an authenticated competition. The server recomputes scores but does not prove that a human watched the animation.

`node preview.mjs` uses an in-memory SQLite test database; it never modifies the online scoreboard. Node.js 22.13 or later is required for that preview. Run `node --test tests/game.test.js` for the scoring and API checks.

The Wits crest comes from the university's official coat-of-arms page. Missing tiles illustrate unavailable model data; real corrupted image files may fail decoding completely. Recorded performance plots are separate from simulation and include downloadable data and test context. Regenerate them from the original local test folders, or the committed CSV extracts when those folders are absent, with `plot_results.py` and Matplotlib (`pip install --target .plot-deps matplotlib`).
