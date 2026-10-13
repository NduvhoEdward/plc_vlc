"""GUI integration smoke check using a hidden Tk window; synthetic records, no hardware access."""
import sys,tempfile,time
from pathlib import Path
folder=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(folder))
import tkinter as tk
from mobile_receiver_dashboard import MobileReceiverDashboard
from pixel_protocol import from_pixels
MobileReceiverDashboard.connect=lambda self:None
with tempfile.TemporaryDirectory() as output:
    root=tk.Tk();root.withdraw()
    app=MobileReceiverDashboard(root,base=output)
    assert str(app.send_picture_button.cget('state'))=='disabled'
    pixels=[i%3==0 for i in range(32*16)]
    picture=from_pixels(pixels,0x1234,32,16)
    for record in picture.records():app.consume('RX','RX message: '+record,time.monotonic())
    assert app.received[0x1234]==picture.data
    assert 'actual RX records' in app.image_status.get()
    app.send_command('TX','START')
    assert 'disabled' in app.status.get()
    app.close()
print('PASS: original GUI, Tk/Pillow, actual-record reconstruction path, TX controls blocked.')
