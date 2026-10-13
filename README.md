# Internet of Light

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
- `agent/`: outbound Python agent; simulated agent by default; explicit UDP PLC ingress adapter with TX and RX serial feedback.
- `tests/`: relay/authentication/controller tests and Python protocol/reconnect tests.
- `HOSTING.md`: free hosting and live-rig setup.

Demo mode works immediately in a browser and transmits nothing externally. Image originals are decoded and reduced on the device. Drawings and text drafts are saved in that browser's local storage when available. Uploaded originals are held in memory only.

The phone studio has separate **Create & send** and **Monitor link** views. A persistent bottom bar holds preview, send, cancel and queue actions, while connection and controller status stay visible during scrolling. Phone submission first brings the actual payload into view. Monitoring shows public link/activity status while keeping received content private to its sender. Layouts handle portrait, landscape, safe areas and keyboard viewport changes.

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
- Received content goes only to the submitting session, not every viewer. Viewer status uses random short-lived session IDs, never names or IP addresses.
- Browser session credentials expire after one hour, stay in memory, and are sent as a WebSocket subprotocol instead of URL query parameters. Rejoin with Turnstile after expiry.
- Hashed IP rate counters expire after ten minutes. Agent deduplication uses a local SQLite ledger; receiver data expires from that ledger after fifteen minutes, with one-hour ID tombstones.
- A completed receiver payload lost during a disconnect is not retained for later download; reconnect shows completion context without silently repeating it.

No UI for remote modulation/duty-cycle changes is exposed because firmware bounds and variants must be verified. The website controls transfer and cancellation only. Mains-connected noise sources remain manual.

## Hardware adapter assumptions

Do not launch hardware mode while another dashboard or Serial Monitor owns either port. The laptop must physically sit upstream of the PLC adapters and reach the TX's **current reported** IP at UDP5000. Wi-Fi reachability alone does not prove that the physical PLC segment was traversed.

The adapter requires the installed gateway to support `CONTROL`, `SOURCE PLC`, `START`, `AUTO`, `TX CONTROL ... plc_used=... local_used=... inflight=... pending=...` and RX `RX message:` lines. It selects `SOURCE PLC`, uses the existing `START` bypass, and returns to `AUTO` after all admitted frames drain. It never changes RATE, THRESHOLD, modulation, ADC settings, firmware, or calibration. Verify TX/RX rate matching manually beforehand. It refuses to proceed when existing queues are nonempty, repeats only missing identified records, and pauses production while TX feedback is stale.

Cancellation stops new production; already admitted records may drain. The rig is released only after queue/inflight feedback confirms idle. If idle cannot be confirmed, the agent keeps retrying and the relay stays locked. Remote STOP is deliberately not used to strand a nonempty FIFO.

The web hardware adapter has not been exercised against live boards. Existing local optical measurements do not verify this website's PLC route. Connect real hardware only after the deployment and simulated-agent flow are checked.

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

The Wits crest comes from the university's official coat-of-arms page. Missing tiles illustrate unavailable model data; real corrupted image files may fail decoding completely. Recorded performance plots are separate from simulation and include downloadable data and test context. Regenerate them from the original local test folders with `plot_results.py` and Matplotlib (`pip install --target .plot-deps matplotlib`).
