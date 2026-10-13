import json,shutil,zipfile,hashlib,sys
from pathlib import Path
if len(sys.argv) not in (2,3):raise SystemExit('Usage: python packaging/build_packages.py PRIVATE_OPERATIONAL_FOLDER [OUTPUT_FOLDER_NAME]')
ROOT=Path(sys.argv[1]).resolve()
SOURCE=Path(__file__).resolve().parents[1]
OUT=ROOT/(sys.argv[2] if len(sys.argv)==3 else 'pc-packages')
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
    shutil.copy2(SOURCE/'packaging'/'stop.py',folder/'stop.py')
    (folder/'STOP.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" stop.py\r\npause\r\n')
    if role=='receiver':
        gui=Path(r'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python')
        target=folder/'gui-runtime';target.mkdir(exist_ok=True)
        for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):shutil.copy2(gui/name,target/name)
        for name in ('DLLs','tcl'):shutil.copytree(gui/name,target/name,dirs_exist_ok=True)
        shutil.copytree(gui/'Lib',target/'Lib',dirs_exist_ok=True,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','ensurepip','idlelib'))
        shutil.copytree(gui/'Lib'/'site-packages'/'PIL',target/'Lib'/'site-packages'/'PIL',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        for license_dir in (gui/'Lib'/'site-packages').glob('pillow-*.dist-info'):shutil.copytree(license_dir,target/'Lib'/'site-packages'/license_dir.name,dirs_exist_ok=True)
        (target/'python312._pth').write_text('Lib\nDLLs\nLib/site-packages\n.\n../deps\nimport site\n')
        (folder/'OPEN-DASHBOARD.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"gui-runtime\\python.exe" "dashboard\\mobile_receiver_dashboard.py"\r\nif errorlevel 1 pause\r\n')
        (folder/'dashboard').mkdir(exist_ok=True)
        for module in (SOURCE/'desktop_dashboard').glob('*.py'):shutil.copy2(module,folder/'dashboard'/module.name)
        shutil.copy2(SOURCE/'SYSTEM-CONTEXT.md',folder/'SYSTEM-CONTEXT.md')

    settings=dict(receiver_dashboard='original' if role=='receiver' else None,role=role,plc_host='192.168.0.100',optical_rate=280000,rx_port='auto',display_port=8765,launcher_port=8766 if role=='sender' else 8767)
    (folder/'settings.json').write_text(json.dumps(settings,indent=2))
    (folder/'START.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\ntitle Internet of Light - '+role+' PC\r\n"runtime\\python.exe" -u launcher.py\r\necho.\r\necho Bridge stopped. See logs\\launcher.log if there was an error.\r\npause\r\n')
    (folder/'CHECK.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" launcher.py --self-check\r\npause\r\n')
    note='SENDER: Connect Ethernet to the first HomePlug. Power TX and connect it to the second HomePlug Wi-Fi. TX uses 192.168.0.100; The launcher configures Ethernet 192.168.0.10 / 255.255.255.0 if needed; accept the Windows administrator prompt. No Ethernet gateway is added. If there are multiple wired adapters, it asks you to select one manually. RESTORE ETHERNET.cmd removes its added address afterwards. Keep internet on Wi-Fi.\n' if role=='sender' else 'RECEIVER: Connect RX by USB. Close Serial Monitor and the old standalone dashboard before starting. START.cmd opens the original dashboard in mobile receiver mode; it observes the bridge and does not open USB itself. The launcher identifies RX from its RX STAT response; it never assumes COM10.\n'
    (folder/'READ ME.txt').write_text('INTERNET OF LIGHT - '+role.upper()+' PC\n\nWindows 10/11, 64-bit Intel/AMD.\n1. Extract this ZIP completely onto the PC (do not run inside the ZIP).\n2. Connect the PC to internet.\n3. '+note+'4. Double-click START.cmd. Keep its window open.\n5. Original VLC Pixel Studio opens on receiver; launcher status opens on both PCs.\n6. Stop by double-clicking STOP.cmd (or Ctrl+C in the launcher).\n\nPython and dependencies are bundled. No pip install, GitHub login or Cloudflare login needed.\nThe launcher waits for hardware and retries internet/bridge failures.\nIf Windows does not show any USB port, install the USB serial driver for your ESP32 board.\nSettings are in settings.json; normally no editing is needed.\nVisitors: https://plc-vlc.pages.dev/send ; passcode plcvlc\nThese packages include private bridge credentials. Keep them with the project team.\n')
    (folder/'BUILD.json').write_text(json.dumps(dict(python='3.13.16',python_source='https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip',python_sha256='97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297',websockets='15.0.1',pyserial='3.5'),indent=2))
    archive=OUT/('PLC-VLC-'+role.title()+'-private.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in folder.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.log','.sqlite'):
                z.write(p,str(p.relative_to(OUT)))
    print(archive.name,round(archive.stat().st_size/1024/1024,1),'MB',hashlib.sha256(archive.read_bytes()).hexdigest())
