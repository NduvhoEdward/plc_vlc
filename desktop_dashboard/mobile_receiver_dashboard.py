"""Original pixel dashboard connected to the mobile receiver bridge, with one serial owner."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from pixel_dashboard import PixelDashboard
from mobile_observer import ObservationWorker
import tkinter as tk
class MobileReceiverDashboard(PixelDashboard):
    def __init__(self,root,base=None):
        super().__init__(root,base=base or ROOT/'results')
        root.title('VLC Pixel Studio | Mobile receiver | RX USB owned by bridge')
        self.label.set('Mobile PLC / VLC reception - actual RX data')
        self.mode.set('PLC adapter → VLC TX → light → receiver')
        self.image_status.set('Receiver view. Send drawings and pictures from the mobile website.')
        self.send_picture_button.configure(state='disabled')
        self.status.set('Connecting to local receiver bridge. This window never opens RX USB or changes TX.')
        self.tx_port.set('(none)');self.rx_port.set('(none)')
        for box in self.port_boxes:box.configure(state='disabled')
        self.root.after(100,self.connect)
        self.root.after(250,self.relabel)
    def relabel(self):
        def visit(widget):
            try:
                if widget.cget('text')=='PLC Wi-Fi connection':widget.configure(text='PLC adapter link')
            except tk.TclError:pass
            for child in widget.winfo_children():visit(child)
        visit(self.root)
    def connect(self):
        if self.worker:
            self.status.set('Receiver bridge owns RX USB. Close this view or use STOP.cmd to stop the receiver.')
            return
        self.worker=ObservationWorker(self.events);self.worker.start()
        self.connect_button.configure(text='Receiver view connected',state='disabled')
    def send_command(self,*args):
        self.status.set('Board controls are disabled in mobile receiver mode. TX and RX settings are preserved.')
    def begin_picture(self,*args):
        self.image_status.set('Use the mobile website to send. This receiver view never transmits.')
    def send_message(self,*args):
        self.status.set('Use the mobile website to send. This receiver view never transmits.')
    def consume(self,source,line,at,wall=None):
        super().consume(source,line,at,wall)
        if source=='RX' and line.startswith('RX message: TX1:'):
            parts=line[len('RX message: '):].rsplit(':',1)[0].split(':',2)
            if len(parts)==3:self.image_status.set('Received text over light: '+parts[2])
        if line.startswith(('RX message: PX1:','RX message: PH2:','RX message: PD2:')) and self.last_received_at:
            self.image_status.set('Image reconstructed from actual RX records. Final source-match confirmation appears on the mobile website.')
if __name__=='__main__':
    root=tk.Tk();MobileReceiverDashboard(root);root.mainloop()
