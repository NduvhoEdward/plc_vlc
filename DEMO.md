# Two-laptop PLC–VLC demonstration

The implementation lives in this directory and is based on NduvhoEdward/plc_vlc.
Saved firmware and the original dashboards are unchanged.

## Physical arrangement

Sending laptop: internet Wi-Fi + Ethernet upstream of HomePlug 1.
HomePlug 2: Wi-Fi AP for TX. TX needs independent power; USB is not required.
Receiving laptop: RX USB + internet. The optical receiver keeps its current calibration.
Do not run another serial dashboard or network producer alongside these bridges.

Observed 13 October 2026: TX COM9, RX COM10, TX IP 192.168.0.100.
Both running boards reported 280000 bit/s, and TX PLC/AUTO, 75% gate.
Ports and IP may change on the other laptop. --optical-rate is a pacing estimate,
not a firmware command. Read the boards' rate before changing that estimate.

## Verified physical acceptance

The local acceptance used actual UDP ingress and RX serial output, with no TX
serial commands during transfer. All source and reconstructed payload hashes
matched. Measured durations include AUTO priming, reception and final drain:

- Text: 11.375 seconds.
- 32 × 16: 6.281 seconds.
- 64 × 32: 9.578 seconds.
- 128 × 64: 20.657 seconds.

See hardware-acceptance.json. These finite tests establish network ingress and
optical reception in the connected arrangement. The physical Ethernet route
must remain upstream of the HomePlug pair at the demonstration. The adapter
does not independently instrument the interior of the powerline segment.

Deployed Cloudflare acceptance also passed: text in 8.187 seconds and 64 × 32 in 12.469 seconds, with real RX verification and simulated=false. A production cancellation at 18,200 buffered bytes, before AUTO started, drained and released the rig correctly. The local Cloudflare runtime also passed with 15 visitor sockets. Public Turnstile/browser joining still needs a phone rehearsal.

## Install on each demonstration laptop

Use Python 3.11 or later:

    python -m pip install -r agent/requirements.txt

Role-specific `sender-credentials.json` and `receiver-credentials.json` files can be placed beside the launcher. They are private and ignored by Git. Copy only the receiver file to the receiving laptop. The launcher uses them automatically.

Then run:

    python launch_bridge.py

The launcher asks for sender or receiver, the relay base URL and the respective
private token without echo. Sender asks for TX IP and pacing rate. Receiver asks
for its USB port. Sender and receiver use distinct secrets; do not put either
secret into the public config or GitHub.

The receiving laptop's presentation is http://127.0.0.1:8765.
Only verified results with explicit sharing consent appear there. Received
fragments go only to their submitting phone; shared results also go to currently
connected viewers. The display keeps the last shared result in memory until
the process closes; it is not a fresh indication of link activity.

## Cloudflare deployment

Use the existing Pages project and public/ output directory.
Deploy relay/wrangler.jsonc as the separate Worker; do not deploy the root
wrangler.jsonc as the relay.

Wrangler setup:

    npm install
    npx wrangler login
    npx wrangler deploy --dry-run --config relay/wrangler.jsonc

Create a Turnstile widget for plc-vlc.pages.dev.
The relay needs SESSION_SECRET, AGENT_TOKEN, RECEIVER_TOKEN, JOIN_PASSCODE,
TURNSTILE_SECRET. Generate independent random tokens (at least 32 bytes).

Use configure_relay.py interactively in your own terminal. It asks for the
private values without echo, sets Worker secrets through stdin, deploys, and
updates only the public relay URL and Turnstile site key in public/config.js.
Never paste private values into chat or commit them.

    python configure_relay.py

After configuration, publish the frontend update through the existing GitHub
integration. Share https://plc-vlc.pages.dev/send.html with visitors.
Each visitor selects Connect to rig, enters the invitation passcode, completes
verification, joins the queue and submits during their turn.

## Cancellation and recovery

AUTO waits for 75% occupancy. A cancelled transfer that has not started yet may
need extra duplicates of its own records to reach the gate and drain. The
operator and visitor should expect some already queued data to still transmit.
No remote STOP is issued, and neither rate nor gate is changed.

Stale TX feedback stops production. A lost receiver stops production. Loss of
the sender's relay connection requests cancellation locally. Controls remain
locked until TX reports zero queued bytes and zero frames in flight.

On sender restart, an outstanding transfer is not replayed. If it left a
partially primed buffer, an operator must restore/drain it before reopening
control; the new process does not assume ownership of another producer's data.

## Rehearsal before opening to visitors

1. Start receiver, then sender, and confirm live measurements.
2. Send text and a 64 × 32 drawing from a phone using mobile data.
3. Check a private result does not appear on the presentation.
4. Check an opted-in result appears on phone and presentation.
5. Use a second phone to check automatic turn handoff.
6. Cancel during priming, wait for drain, then verify the next visitor can send.
7. Block light during transmission, restore it, and check partial/timeout state.
8. Disconnect an agent during transfer and check that control remains locked.
9. Confirm TX remains functional on independent power with its USB removed.

## Tests

    node --experimental-loader ./tests/cloudflare-loader.mjs --test tests/relay.test.js
    python -m unittest discover -s tests -p "test_*.py" -v

Unit tests stub Cloudflare and do not establish cloud deployment behaviour.
