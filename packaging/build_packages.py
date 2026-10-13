import json,shutil,zipfile,hashlib,sys
from pathlib import Path
if len(sys.argv)!=2:raise SystemExit('Usage: python packaging/build_packages.py PRIVATE_OPERATIONAL_FOLDER')
ROOT=Path(sys.argv[1]).resolve()
SOURCE=Path(__file__).resolve().parents[1]
OUT=ROOT/'pc-packages'
RUNTIME=ROOT/'package-build'/'runtime'
def copytree(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyd','bin'))
for role in ('sender','receiver'):
    folder=OUT/('PLC-VLC-'+role.title());folder.mkdir(parents=True,exist_ok=True)
    shutil.copytree(RUNTIME,folder/'runtime',dirs_exist_ok=True)
    (folder/'runtime'/'python313._pth').write_text('python313.zip\n.\n../deps\n..\n../agent\nimport site\n')
    copytree(ROOT/'.python-deps',folder/'deps')
    (folder/'agent').mkdir(exist_ok=True)
    for name in ('agent.py','receiver.py','pixel_protocol.py','split_rig.py'):
        shutil.copy2(SOURCE/'agent'/name,folder/'agent'/name)
    shutil.copy2(SOURCE/'packaging'/'launcher.py',folder/'launcher.py')
    if role=='sender':
        for script in ('configure_ethernet.ps1','restore_ethernet.ps1'):shutil.copy2(SOURCE/'packaging'/script,folder/script)
        (folder/'RESTORE ETHERNET.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npowershell -NoProfile -File "%~dp0restore_ethernet.ps1"\r\npause\r\n')
    shutil.copy2(ROOT/(role+'-credentials.json'),folder/(role+'-credentials.json'))
    settings=dict(role=role,plc_host='192.168.0.100',optical_rate=280000,rx_port='auto',display_port=8765,launcher_port=8766 if role=='sender' else 8767)
    (folder/'settings.json').write_text(json.dumps(settings,indent=2))
    (folder/'START.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\ntitle Internet of Light - '+role+' PC\r\n"runtime\\python.exe" -u launcher.py\r\necho.\r\necho Bridge stopped. See logs\\launcher.log if there was an error.\r\npause\r\n')
    (folder/'CHECK.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" launcher.py --self-check\r\npause\r\n')
    note='SENDER: Connect Ethernet to the first HomePlug. Power TX and connect it to the second HomePlug Wi-Fi. TX uses 192.168.0.100; The launcher configures Ethernet 192.168.0.10 / 255.255.255.0 if needed; accept the Windows administrator prompt. No Ethernet gateway is added. If there are multiple wired adapters, it asks you to select one manually. RESTORE ETHERNET.cmd removes its added address afterwards. Keep internet on Wi-Fi.\n' if role=='sender' else 'RECEIVER: Connect RX by USB. Close Serial Monitor and any old receiver dashboard/bridge. The launcher identifies RX from its RX STAT response; it never assumes COM10.\n'
    (folder/'READ ME.txt').write_text('INTERNET OF LIGHT - '+role.upper()+' PC\n\nWindows 10/11, 64-bit Intel/AMD.\n1. Extract this ZIP completely onto the PC (do not run inside the ZIP).\n2. Connect the PC to internet.\n3. '+note+'4. Double-click START.cmd. Keep its window open.\n5. Receiver presentation and launcher status open automatically.\n6. Stop with Ctrl+C in the launcher window.\n\nPython and dependencies are bundled. No pip install, GitHub login or Cloudflare login needed.\nThe launcher waits for hardware and retries internet/bridge failures.\nIf Windows does not show any USB port, install the USB serial driver for your ESP32 board.\nSettings are in settings.json; normally no editing is needed.\nVisitors: https://plc-vlc.pages.dev/send ; passcode plcvlc\nThese packages include private bridge credentials. Keep them with the project team.\n')
    (folder/'BUILD.json').write_text(json.dumps(dict(python='3.13.16',python_source='https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip',python_sha256='97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297',websockets='15.0.1',pyserial='3.5'),indent=2))
    archive=OUT/('PLC-VLC-'+role.title()+'-private.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.log','.sqlite'):
                z.write(p,str(p.relative_to(OUT)))
    print(archive.name,round(archive.stat().st_size/1024/1024,1),'MB',hashlib.sha256(archive.read_bytes()).hexdigest())
