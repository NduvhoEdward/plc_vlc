// Public deployment settings only. Never put the agent token or passcode here.
export const CONFIG = Object.freeze({
  relayUrl: "", // e.g. https://internet-of-light-relay.your-subdomain.workers.dev
  turnstileSiteKey: "", // Public site key, restricted to your Pages domain.
  maxTextCharacters: 30,
  maxOriginalBytes: 8 * 1024 * 1024,
});
