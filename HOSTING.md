# Host for free on Cloudflare

The static website and browser demo need only Cloudflare Pages Free and its supplied `pages.dev` address. The live relay additionally uses Workers Free and a SQLite-backed Durable Object. No custom domain, R2, paid plan, or external database is required.

Cloudflare currently makes static Pages asset requests free and unlimited. Workers/Durable Objects have free daily quotas; on Workers Free, operations over the applicable quota fail instead of providing unlimited capacity. Stay on the Free plan. Do not enable a paid upgrade to solve a quota error.

Official references, checked 12 October 2026:

- https://developers.cloudflare.com/pages/functions/pricing/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://developers.cloudflare.com/workers/platform/limits/

Provider terms and quotas may change. This project has no usage charges of its own. Hosting has not been provisioned by this local build.

## 1. Update the existing plc-vlc.pages.dev website

The existing Pages project is already linked to `NduvhoEdward/plc_vlc`. Replace the placeholder with this implementation in that repository. Keep the existing Pages project and its `plc-vlc.pages.dev` address; do not create a second Pages project or change it to direct upload.

Recommended repository structure: put this package at the repository root, keeping `public/`, `relay/`, `agent/` and the supporting documentation separate. In the existing Pages project's build settings, use no framework, no build command, repository root as the root directory, and `public` as the output directory. Push the replacement to the configured production branch; the existing Git integration will deploy it automatically. Confirm the production branch in Pages rather than assuming its name.

The relay is already configured to allow the exact origin `https://plc-vlc.pages.dev`. Set the Turnstile widget hostname to `plc-vlc.pages.dev`. Pages hosting covers the frontend; the separate live relay and laptop agent still need the configuration below.

The following alternative setup instructions are for a new installation only.

## New installations only

### Simplest: direct upload

1. Sign in to https://dash.cloudflare.com with your own account.
2. Open Workers & Pages and create a **Pages** application using direct upload/static assets.
3. Name it `internet-of-light` (or another available name).
4. Upload `internet-of-light-pages.zip` from this project's parent folder, or the contents of `public/`.
5. Deploy and open the returned `https://<project>.pages.dev` URL on your phone.

The archive root contains `index.html`, `send.html`, and their assets. Upload only this static archive, not the source archive or the Arduino project. The entire website and browser demo work before the live relay is configured.

For direct-upload updates, upload a new public archive in the same Pages project. Direct-upload and Git-integrated Pages have different project setup flows; choose Git integration from the start if automatic GitHub deployments are preferred.

### GitHub → Pages

Copy the contents of `internet-of-light/` into a website directory in your GitHub repository (or make it the repository root). Connect that repository through Cloudflare Pages Git integration. Select no framework; leave the build command empty; set the output directory to `public` relative to the selected root directory. If the repository root contains an `internet-of-light` directory, set that as the project's root directory. Only `public/` is published.

There is no frontend installation/build step. Demo visitors do not need to sign in.

## 2. Enable the live relay

This step requires a Cloudflare login and access to the deployed Pages project's settings. Use Node.js 22+ and a normal terminal:

```powershell
npm install
npx wrangler login
```

Create a Turnstile widget in the Cloudflare dashboard, restricted to your Pages hostname. Keep its secret server-side and its site key public.

Set the exact Pages origin in `relay/wrangler.toml`:

```toml
ALLOWED_ORIGIN = "https://your-project.pages.dev"
```

Set secrets using Wrangler's interactive prompts, from the `internet-of-light` directory:

```powershell
npx wrangler secret put SESSION_SECRET --config relay/wrangler.toml
npx wrangler secret put AGENT_TOKEN --config relay/wrangler.toml
npx wrangler secret put JOIN_PASSCODE --config relay/wrangler.toml
npx wrangler secret put TURNSTILE_SECRET --config relay/wrangler.toml
npx wrangler deploy --config relay/wrangler.toml
```

SESSION_SECRET and AGENT_TOKEN must each be long, independently generated random secrets (at least 32 random bytes). JOIN_PASSCODE is the private invitation shared with demonstration visitors. Never commit them or put them in frontend config, screenshots, or URLs. If first-time Wrangler secret creation asks to create the named Worker, create it, then deploy the supplied configuration. Follow current Wrangler dashboard instructions if account setup differs.

In `public/config.js`, enter only public values:

```javascript
relayUrl: "https://internet-of-light-relay.YOUR-SUBDOMAIN.workers.dev",
turnstileSiteKey: "YOUR-PUBLIC-SITE-KEY",
```

Redeploy the public site. The default CSP supports `workers.dev`; if using a different relay domain, add its exact HTTPS/WSS origins to `_headers`. Configure additional site origins only intentionally; the relay currently permits one exact origin.

The Durable Object uses `new_sqlite_classes`, which is available on Workers Free. Its WebSockets use the hibernation API. There are no polling visitors, cron jobs, or permanent 1-second database writes. Only the connected laptop sends roughly one telemetry message per second.

## 3. Connect the simulated laptop agent first

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r agent/requirements.txt
$env:IOL_AGENT_URL = 'wss://internet-of-light-relay.YOUR-SUBDOMAIN.workers.dev/agent'
```

Enter the agent secret without putting its literal value in shell history:

```powershell
$iolAgentSecret = Read-Host 'Agent token' -AsSecureString
$env:IOL_AGENT_TOKEN = [System.Net.NetworkCredential]::new('', $iolAgentSecret).Password
.\.venv\Scripts\python.exe agent/agent.py
```

The default agent is **simulated**, and the browser labels it accordingly. Verify secure joining, two-phone queue ownership, cancellation, reconnect, and receiver display. The agent holds only one outbound connection. Stop it with Ctrl+C when done; remove the token environment variable afterward:

```powershell
Remove-Item Env:IOL_AGENT_TOKEN
```

## 4. Connect the physical PLC → VLC path

Close the original dashboards first. Check the boards' actual serial ports and current TX network IP. Make sure the laptop's outgoing data really traverses the physical PLC pair. Replace the placeholders below:

```powershell
.\.venv\Scripts\python.exe agent/agent.py --hardware --plc-host CURRENT_TX_IP --tx-port ACTUAL_TX_COM_PORT --rx-port ACTUAL_RX_COM_PORT
```

There is no firmware upload step. See README.md for required status commands and START/AUTO behaviour. The adapter requires idle feedback and matching installed firmware. Unsupported devices must be integrated through a verified adapter, not by pretending a transfer succeeded.

Record one real text transfer and one image transfer reconstructed from RX. Then check loss of browser/agent connectivity during an active transfer, cancellation while frames remain queued, and recovery before handing the rig to a new controller.

## Free-tier operation

Use one demonstration room, small packed images, a modest audience, and run the laptop agent only during demonstrations. Watch usage in your Cloudflare dashboard. The UI does not promise unlimited live viewers. The static home page and browser demo remain independent of the relay if its quota is exhausted or the laptop is offline.

For an entirely static alternative, the same `public/` directory can be hosted on GitHub Pages, but update the relay's allowed origin accordingly. The supplied design uses relative links and does not need a custom domain.
