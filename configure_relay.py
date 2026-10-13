"""Run interactively: private values enter via hidden prompts and stdin."""
import getpass, json, shutil, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parent
node=shutil.which('node')
cli=root/'node_modules'/'wrangler'/'bin'/'wrangler.js'
if not node or not cli.exists():raise SystemExit('Install Node.js and run npm install first.')
base=[node,str(cli)]
config=str(root/'relay'/'wrangler.jsonc')
print('Create a Turnstile widget for plc-vlc.pages.dev before continuing.')
secrets={}
for name in ('SESSION_SECRET','AGENT_TOKEN','RECEIVER_TOKEN','JOIN_PASSCODE','TURNSTILE_SECRET'):
    value=getpass.getpass(name+': ')
    if not value:raise SystemExit('Empty value rejected.')
    if name in ('SESSION_SECRET','AGENT_TOKEN','RECEIVER_TOKEN') and len(value)<43:
        raise SystemExit('Use a token generated from at least 32 random bytes.')
    secrets[name]=value
if len(set(secrets[k] for k in ('SESSION_SECRET','AGENT_TOKEN','RECEIVER_TOKEN')))!=3:
    raise SystemExit('Generate independent tokens.')
sitekey=input('Public Turnstile site key: ').strip()
subprocess.run(base+['secret','bulk','--config',config],input=json.dumps(secrets),text=True,check=True)
secrets.clear()
subprocess.run(base+['deploy','--config',config],check=True)
url=input('Deployed relay base URL (https://...workers.dev): ').strip().rstrip('/')
if not url.startswith('https://') or not sitekey:raise SystemExit('Expected HTTPS URL and public site key.')
content="export const CONFIG = Object.freeze("+json.dumps(dict(relayUrl=url,turnstileSiteKey=sitekey,maxTextCharacters=30,maxOriginalBytes=8*1024*1024),indent=2)+");\n"
(root/'public'/'config.js').write_text(content)
print('Public config updated. Publish the frontend through the existing Pages project.')
