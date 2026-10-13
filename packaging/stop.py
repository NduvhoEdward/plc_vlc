import json,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent
settings=json.loads((root/'settings.json').read_text())
request=urllib.request.Request('http://127.0.0.1:'+str(settings['launcher_port'])+'/stop',data=b'',headers={'X-IOL-Stop':'1'})
try:
    with urllib.request.urlopen(request,timeout=5) as response:print(response.read().decode())
except OSError:print('No running launcher was found for this package.')
