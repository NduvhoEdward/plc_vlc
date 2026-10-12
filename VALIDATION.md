# Verification — 12 October 2026

## Passed

- 10 Node tests: controller exclusivity; active-transfer lease locking; duplicate/conflicting IDs; payload bounds and encoding; credential tampering/expiry; request body limits without Content-Length; Worker origin and agent-auth rejection; private receiver results; receiver hash and hardware-idle acknowledgement requirements; session message limits.
- 6 Python tests: transfer-specific text framing with colons; all three monochrome sizes and receiver-only CRC reassembly; malformed payload rejection; cross-language SHA-256 agreement; completed-transfer reconciliation without resending; interrupted-process reconciliation without automatic replay.
- Browser preview in Codex: home-page navigation; real assets load; no console warnings/errors observed in the studio; text preview/counters and simulated confirmed receiver result; mobile drawing stroke and undo; image selection and conversion from a 1100×720 PNG; 128×64 prepared payload of 1024 bytes and simulated receiver result; real-mode submit disabled while offline.
- Phone viewport: document width equals viewport width (375 CSS px observed), no horizontal overflow in studio.
- Browser live-mode configuration error is explicit, and changing mode clears the previous simulated receiver result.
- JavaScript syntax checks for studio and Worker.

## Still requires verification

- Cloudflare deployment, free account configuration, Turnstile verification and authentic WebSocket upgrades. Unit tests use a stub Cloudflare base class, not the deployed runtime.
- Real multi-phone queue and reconnect flow with a deployed Durable Object.
- Python UDP/serial hardware adapter against installed boards. No serial ports were opened and no firmware or existing dashboard was modified during this website task.
- Physical PLC traversal, real image/text optical reconstruction, cancellation/drain and recovery on the rig.
- Real phone camera capture and touch events on Android/iOS. The browser drawing check used pointer dragging in a phone-sized viewport.
- Independent scientific metrics such as BER/SNR. Unsupported measurements show Unavailable; the agent does not fabricate them.

## Hosting blockers in this session

Cloudflare dashboard is at its sign-in page, so no account or deployment has been provisioned. Native Sites hosting tools are unavailable. Installing Wrangler from the npm registry failed with UNABLE_TO_VERIFY_LEAF_SIGNATURE; TLS verification was not disabled. The static direct-upload archive is independent of that installation.

The home-page performance values are copied from the existing local optical acceptance records (32×16: 797 ms; 64×32: 2547 ms; 128×64: 8110 ms). They do not represent web-to-PLC-to-VLC measurements.
