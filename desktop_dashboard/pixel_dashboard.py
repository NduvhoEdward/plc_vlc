"""Isolated drawing/upload demo using unchanged ESP32 text firmware."""
import base64,html,json,re,secrets,time,math
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from vlc_dashboard import Dashboard,PANEL,GOLD,CYAN
from vlc_session import timestamp
from pixel_protocol import WIDTH,HEIGHT,from_pixels,parse_record,parse_fragment,ImageAssembler,convert_picture,save_png

class PixelDashboard(Dashboard):
    def __init__(self,root,base=None):
        self.width,self.height=64,32
        self.pixels=[False]*(self.width*self.height);self.upload_path=None;self.last_draw=None
        self.assembler=ImageAssembler()
        self.active=None;self.used_ids=set();self.received={};self.transfers=[]
        self.buffer_feedback=None;self.buffer_at=0;self.udp_waiting=False;self.udp_sent_at=0
        self.black_brush=True;self.last_received_at=None;self.last_received_id=None
        super().__init__(root,base=base)
        root.title('VLC Pixel Studio · Draw, upload & send with light')
        root.minsize(960,620)
        root.geometry(f'{min(1180,root.winfo_screenwidth()-60)}x{min(900,root.winfo_screenheight()-80)}')
        notebook=self.tabs['Overview'].master
        tab=ttk.Frame(notebook,padding=12);notebook.insert(0,tab,text='Draw & send picture');notebook.select(tab)
        self.tabs['Draw & send picture']=tab
        self.build_pixel_tab(tab)
        self.set_preset('Light bulb')
        self.label.set('Interactive text-image PLC / VLC demo')
        self.root.after(25,self.picture_tick)

    def build_pixel_tab(self,tab):
        # Keep the main action visible even when the image editor needs to scroll.
        buttons=ttk.Frame(tab);buttons.pack(fill='x',pady=(0,8))
        self.send_picture_button=ttk.Button(buttons,text='⚡ SEND DRAWN / UPLOADED IMAGE',command=self.begin_picture)
        self.send_picture_button.pack(side='left')
        ttk.Button(buttons,text='Cancel new repeats',command=lambda:self.finish_picture('cancelled','Cancelled; already queued frames can still transmit.')).pack(side='left',padx=6)
        ttk.Button(buttons,text='Save demo report',command=self.save_report).pack(side='left',padx=6)
        viewport=ttk.Frame(tab);viewport.pack(fill='both',expand=True)
        self.editor_scroll=tk.Canvas(viewport,bg=PANEL,highlightthickness=0)
        scrollbar=ttk.Scrollbar(viewport,orient='vertical',command=self.editor_scroll.yview)
        scrollbar.pack(side='right',fill='y');self.editor_scroll.pack(side='left',fill='both',expand=True)
        self.editor_scroll.configure(yscrollcommand=scrollbar.set)
        content=ttk.Frame(self.editor_scroll,padding=4)
        content_id=self.editor_scroll.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda e:self.editor_scroll.configure(scrollregion=self.editor_scroll.bbox('all')))
        self.editor_scroll.bind('<Configure>',lambda e:self.editor_scroll.itemconfigure(content_id,width=e.width))
        self.root.bind('<MouseWheel>',self.scroll_editor,add='+')
        tab=content
        ttk.Label(tab,text='Draw a picture or upload a photo',style='Value.TLabel').pack(anchor='w')
        ttk.Label(tab,text='Selectable black-and-white resolution · numbered text packets · progressive RX preview · firmware unchanged',wraplength=1040).pack(anchor='w',pady=(2,8))
        sizebar=ttk.Frame(tab);sizebar.pack(fill='x',pady=4)
        ttk.Label(sizebar,text='Resolution').pack(side='left')
        self.resolution=tk.StringVar(value='64 × 32')
        sizebox=ttk.Combobox(sizebar,textvariable=self.resolution,values=('16 × 8','32 × 16','64 × 32','128 × 64'),state='readonly',width=14)
        sizebox.pack(side='left',padx=8);sizebox.bind('<<ComboboxSelected>>',self.change_resolution)
        ttk.Label(sizebar,text='Higher resolution needs more packets and transfer time.').pack(side='left')
        tools=ttk.Frame(tab);tools.pack(fill='x')
        self.preset=tk.StringVar(value='Light bulb')
        ttk.Combobox(tools,textvariable=self.preset,values=('Light bulb','Heart','Smiley','Arrow'),state='readonly',width=12).pack(side='left')
        ttk.Button(tools,text='Use preset',command=lambda:self.set_preset(self.preset.get())).pack(side='left',padx=4)
        ttk.Button(tools,text='Upload picture…',command=self.upload).pack(side='left',padx=4)
        ttk.Button(tools,text='Clear',command=lambda:self.replace_pixels([False]*(self.width*self.height))).pack(side='left',padx=4)
        ttk.Button(tools,text='Invert',command=lambda:self.replace_pixels([not p for p in self.pixels])).pack(side='left',padx=4)
        self.threshold_image=tk.IntVar(value=128)
        ttk.Label(tools,text='B&W threshold').pack(side='left',padx=(12,4))
        ttk.Scale(tools,from_=0,to=255,variable=self.threshold_image,command=self.reconvert,length=145).pack(side='left')
        pictures=ttk.Frame(tab);pictures.pack(fill='x',pady=10)
        for column in (0,1):pictures.columnconfigure(column,weight=1)
        for column,title in enumerate(('Source · click/drag pixels to draw','Received · built only from RX text')):
            box=ttk.Frame(pictures);box.grid(row=0,column=column,sticky='n',padx=8)
            ttk.Label(box,text=title).pack(anchor='w',pady=(0,5))
            canvas=tk.Canvas(box,width=WIDTH*25,height=HEIGHT*25,bg=PANEL,highlightthickness=1,highlightbackground=CYAN)
            canvas.pack()
            if column==0:self.source_canvas=canvas
            else:self.received_canvas=canvas
        self.source_caption=tk.StringVar(value='Draw with left click. Right click erases.')
        self.received_caption=tk.StringVar(value='No image received. Source pixels are never copied here.')
        ttk.Label(pictures,textvariable=self.source_caption,wraplength=440).grid(row=1,column=0,sticky='w',padx=8,pady=5)
        ttk.Label(pictures,textvariable=self.received_caption,wraplength=440).grid(row=1,column=1,sticky='w',padx=8,pady=5)
        self.source_canvas.bind('<Button-1>',self.draw_start)
        self.source_canvas.bind('<B1-Motion>',self.draw_drag)
        self.source_canvas.bind('<Button-3>',lambda e:self.draw_start(e,erase=True))
        self.source_canvas.bind('<B3-Motion>',lambda e:self.draw_drag(e,erase=True))
        self.render_pixels(self.received_canvas,None)
        routebar=ttk.Frame(tab);routebar.pack(fill='x',pady=5)
        self.image_route=tk.StringVar(value='VLC only · USB → light')
        ttk.Label(routebar,text='Route').pack(side='left')
        ttk.Combobox(routebar,textvariable=self.image_route,values=('VLC only · USB → light','PLC · Wi-Fi → light'),state='readonly',width=25).pack(side='left',padx=6)
        self.image_start=tk.StringVar(value='Start now · existing START')
        ttk.Combobox(routebar,textvariable=self.image_start,values=('Start now · existing START','Automatic · existing 75% gate'),state='readonly',width=29).pack(side='left',padx=6)
        self.calibrate_image=tk.BooleanVar(value=True)
        ttk.Checkbutton(routebar,text='Calibrate RX while sending if needed',variable=self.calibrate_image).pack(side='left',padx=6)
        self.image_status=tk.StringVar(value='Connect TX COM15 / RX COM16 at 115200 baud. No uploads are needed.')
        ttk.Label(tab,textvariable=self.image_status,wraplength=1040,style='Value.TLabel').pack(anchor='w',pady=7)
        self.image_detail=tk.StringVar(value='PLC route requires this PC on the PLC Wi-Fi network. Stop other producers and let the selected queue empty first.')
        ttk.Label(tab,textvariable=self.image_detail,wraplength=1040).pack(anchor='w')
        ttk.Label(tab,text='START uses your existing manual bypass; the threshold value stays 75%. Automatic mode fills the FIFO with repeated copies. RX C briefly pauses capture. Repeats are not new images. A verified picture confirms that picture reached RX; it does not confirm every repeated packet.',wraplength=1040).pack(anchor='w',pady=8)

    def scroll_editor(self,event):
        if self.tabs['Draw & send picture'].winfo_ismapped():
            self.editor_scroll.yview_scroll(-int(event.delta/120),'units')

    def render_pixels(self,canvas,pixels,width=None,height=None):
        from PIL import Image,ImageTk
        width=self.width if width is None else width;height=self.height if height is None else height
        canvas.delete('all')
        cell=min(25,400/width,200/height)
        if pixels is None:
            canvas.create_text(200,100,text='Waiting for RX image',fill=CYAN);return
        if cell>=8:
            for y in range(height):
                for x in range(width):
                    value=pixels[y*width+x]
                    color='#586678' if value is None else ('#07111e' if value else '#fff4ba')
                    canvas.create_rectangle(x*cell,y*cell,(x+1)*cell,(y+1)*cell,fill=color,outline='#526174')
        else:
            image=Image.new('RGB',(width,height));image.putdata([(88,102,120) if v is None else ((7,17,30) if v else (255,244,186)) for v in pixels])
            image=image.resize((round(width*cell),round(height*cell)),Image.Resampling.NEAREST)
            canvas._pixel_photo=ImageTk.PhotoImage(image)
            canvas.create_image(0,0,anchor='nw',image=canvas._pixel_photo)

    def change_resolution(self,_=None):
        if self.active:
            self.resolution.set(f'{self.width} × {self.height}');return
        from PIL import Image
        width,height=map(int,self.resolution.get().split(' × '))
        if (width,height) not in ((16,8),(32,16),(64,32),(128,64)):return
        old=Image.new('L',(self.width,self.height));old.putdata([0 if p else 255 for p in self.pixels])
        self.width,self.height=width,height
        if self.upload_path:self.reconvert()
        else:self.replace_pixels([v<128 for v in old.resize((width,height),Image.Resampling.NEAREST).tobytes()])

    def replace_pixels(self,pixels,uploaded=False):
        if self.active:self.image_status.set('Finish or cancel this transfer before editing the picture.');return
        if len(pixels)!=self.width*self.height:raise ValueError('Grid pixel count does not match resolution.')
        self.pixels=list(pixels)
        if not uploaded:self.upload_path=None
        self.render_pixels(self.source_canvas,self.pixels)
        self.source_caption.set(f'{self.width} × {self.height} pixels · {sum(self.pixels)} black · click/drag to edit')

    def draw_start(self,event,erase=False):
        if self.active:return
        cell=min(25,400/self.width,200/self.height);x,y=int(event.x//cell),int(event.y//cell)
        if 0<=x<self.width and 0<=y<self.height:
            self.black_brush=False if erase else not self.pixels[y*self.width+x]
            self.last_draw=None
            self.draw_drag(event,erase)

    def draw_drag(self,event,erase=False):
        if self.active:return
        cell=min(25,400/self.width,200/self.height);x,y=int(event.x//cell),int(event.y//cell)
        if 0<=x<self.width and 0<=y<self.height:
            previous=self.last_draw or (x,y);steps=max(abs(x-previous[0]),abs(y-previous[1]),1)
            for step in range(steps+1):
                px=round(previous[0]+(x-previous[0])*step/steps);py=round(previous[1]+(y-previous[1])*step/steps)
                self.pixels[py*self.width+px]=False if erase else self.black_brush
            self.last_draw=(x,y)
            self.upload_path=None;self.render_pixels(self.source_canvas,self.pixels)
            self.source_caption.set(f'Hand-drawn {self.width} × {self.height} image · right click erases')

    def set_preset(self,name):
        patterns={
          'Light bulb':['00111100','01000010','10000001','10000001','01000010','00111100','00111100','00011000'],
          'Heart':['01100110','11111111','11111111','01111110','00111100','00011000','00000000','00000000'],
          'Smiley':['00111100','01000010','10100101','10000001','10100101','10011001','01000010','00111100'],
          'Arrow':['00010000','00011000','11111100','11111110','11111100','00011000','00010000','00000000']}
        from PIL import Image
        image=Image.new('L',(16,8));image.putdata([0 if c=='1' else 255 for row in patterns[name] for c in '0000'+row+'0000'])
        self.replace_pixels([v<128 for v in image.resize((self.width,self.height),Image.Resampling.NEAREST).tobytes()])
        self.source_caption.set(name+' · edit pixels or upload a picture')

    def upload(self):
        if self.active:self.image_status.set('Finish or cancel this transfer before uploading another picture.');return
        path=filedialog.askopenfilename(title='Choose picture to convert',filetypes=[('Pictures','*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff'),('All files','*.*')])
        if not path:return
        try:
            pixels=convert_picture(path,int(self.threshold_image.get()),self.width,self.height)
            self.upload_path=path;self.replace_pixels(pixels,uploaded=True)
            self.source_caption.set(Path(path).name+f' → {self.width} × {self.height} B&W; adjust threshold or draw over it')
        except Exception as error:messagebox.showerror('Could not convert picture',str(error))

    def reconvert(self,_=None):
        if self.active:
            self.threshold_image.set(self.active['threshold']);return
        if self.upload_path:
            try:self.replace_pixels(convert_picture(self.upload_path,int(self.threshold_image.get()),self.width,self.height),uploaded=True)
            except Exception as error:self.image_status.set('Conversion error: '+str(error))

    def begin_picture(self):
        if self.active:return
        if self.demo or self.replay or not {'TX','RX'}.issubset(self.roles):
            self.image_status.set('Connect both real boards first. Saved/demo captures cannot transmit.');return
        if self.metrics.tx.get('rate')!=self.metrics.rx.get('rate'):
            self.image_status.set('TX and RX rates must match. Read status or use Link controls first.');return
        route='LOCAL' if self.image_route.get().startswith('VLC') else 'PLC'
        control=self.metrics.control
        if control.get('source')!=route and (control.get('streaming') or control.get('inflight') or control.get('plc_used',0)>0 or control.get('local_used',0)>0):
            self.image_status.set('The other source is active. Pause its producer and let its queue drain before switching routes.');return
        queue_key='local_used' if route=='LOCAL' else 'plc_used'
        if self.metrics.control.get(queue_key,0)>0:
            self.image_status.set('Selected queue still contains data. Stop its producer and let it drain first.');return
        if route=='PLC' and self.metrics.network.get('connected')!=1:
            self.image_status.set('TX is not connected to PLC Wi-Fi. Read NETSTAT first.');return
        identifier=secrets.randbelow(65536)
        while identifier in self.used_ids:identifier=secrets.randbelow(65536)
        self.used_ids.add(identifier)
        picture=from_pixels(self.pixels,identifier,self.width,self.height);records=picture.records()
        directory=self.session.path/'text_images';directory.mkdir(exist_ok=True)
        source=directory/f'source_{identifier:04X}.png';save_png(picture,source)
        self.active=dict(picture=picture,record=records[0],records=records,acked=set(),cursor=0,dwell_sent=0,
                         dwell=max(8,math.ceil(self.metrics.tx['rate']*.25/400)),
                         timeout=max(45,len(records)*.8+30),route=route,started=time.monotonic(),
                         timestamp=timestamp(),directory=directory,source=source,submitted=0,admitted=0,
                         start_now=route=='PLC' and self.image_start.get().startswith('Start now'),
                         ready=False,calibrated=False,stream_since=None,ip=self.ip.get(),last_send=0,
                         threshold=int(self.threshold_image.get()))
        self.buffer_feedback=None;self.udp_waiting=False
        self.send_picture_button.configure(state='disabled')
        self.received_caption.set(f'Waiting for image {identifier:04X}; previous view is not this result.')
        self.image_status.set(f'Preparing image {identifier:04X} · {picture.width} × {picture.height} · {len(records)} text records')
        self.send_command('TX','SOURCE '+route)
        self.send_command('TX','START' if self.active['start_now'] else 'AUTO')
        if route=='PLC':
            try:self.worker.subscribe_buffer(self.active['ip'])
            except (ValueError,OSError) as error:self.finish_picture('failed',str(error))

    def picture_tick(self):
        now=time.monotonic();a=self.active
        if a:
            if not self.worker or not {'TX','RX'}.issubset(self.roles):self.finish_picture('failed','Connection closed during transfer.')
            elif now-a['started']>a['timeout']:self.finish_picture('timeout','Image incomplete. Check alignment, ADC settings and the Wi-Fi route; missing parts were retried.')
            else:
                control=self.metrics.control
                mode='RUN' if a['start_now'] else 'AUTO'
                a['ready']=control.get('source')==a['route'] and control.get('mode')==mode and not control.get('pending')
                if a['ready']:
                    if a['route']=='LOCAL' or control.get('streaming'):
                        if a['stream_since'] is None:a['stream_since']=now
                    if self.calibrate_image.get() and not a['acked'] and not a['calibrated'] and a['stream_since'] is not None and now-a['stream_since']>.4:
                        self.send_command('RX','C');a['calibrated']=True
                    try:
                        if a['route']=='LOCAL' and now-a['last_send']>=.025 and self.worker.commands.qsize()<3:
                            batch=self.next_batch(a,4)
                            if batch:self.worker.picture_batch(batch);a['submitted']+=len(batch);a['last_send']=now
                        elif a['route']=='PLC' and not self.udp_waiting and now-a['last_send']>=.03:
                            if self.buffer_feedback is None or now-self.buffer_at>3:
                                if now-a['last_send']>=1:self.worker.subscribe_buffer(a['ip']);a['last_send']=now
                            else:
                                used,capacity=self.buffer_feedback
                                count=min(24,(capacity-used)//52)
                                if a['start_now']:
                                    estimated=max(0,used-int((now-self.buffer_at)*self.metrics.tx['rate']/640)*52)
                                    count=min(24,max(0,64-estimated//52),(capacity-estimated)//52)
                                if count>0:
                                    batch=self.next_batch(a,count)
                                    if batch:
                                        self.worker.udp_message(a['ip'],5000,''.join(batch))
                                        a['submitted']+=len(batch);self.udp_waiting=True;self.udp_sent_at=now;a['last_send']=now
                        if self.udp_waiting and now-self.udp_sent_at>2:
                            self.udp_waiting=False # Whole-image duplicate retries are safe.
                            self.worker.subscribe_buffer(a['ip'])
                        if a['route']=='PLC' and now-a['started']>6 and self.buffer_feedback is None:
                            self.finish_picture('failed','No PLC buffer reply. Put this PC on the PLC Wi-Fi network and check the TX IP.')
                        elif self.active:
                            self.image_status.set(f'Image {a["picture"].image_id:04X} · RX records {len(a["acked"])}/{len(a["records"])} · awaiting whole-image verification')
                            self.image_detail.set(f'Route: {a["route"]} · {a["picture"].width} × {a["picture"].height} · {len(a["picture"].data)} image bytes · submitted records including repeats: {a["submitted"]} · elapsed: {now-a["started"]:.1f} s. Missing records repeat automatically.')
                    except (ValueError,OSError) as error:self.finish_picture('failed',str(error))
        if self.last_received_at is not None and not self.active:
            age=now-self.last_received_at
            self.received_caption.set(f'Last verified RX image {self.last_received_id:04X} · {age:.1f} s ago; static preview, not live link status')
        self.root.after(25,self.picture_tick)

    @staticmethod
    def next_batch(a,count):
        missing=[i for i in range(len(a['records'])) if i not in a['acked']]
        if not missing:return []
        if a['route']=='LOCAL' or a['start_now']:
            return [a['records'][missing[0]]]*count
        # AUTO must keep feeding the existing FIFO gate. Hold each numbered
        # record long enough for the RX's throttled text output, then repair
        # only the missing records in subsequent rounds. All records are 51B.
        if a['cursor'] not in missing:a['cursor']=next((i for i in missing if i>=a['cursor']),missing[0]);a['dwell_sent']=0
        number=min(count,a['dwell']-a['dwell_sent'])
        batch=[a['records'][a['cursor']]]*number;a['dwell_sent']+=number
        if a['dwell_sent']>=a['dwell']:
            a['cursor']=(a['cursor']+1)%len(a['records']);a['dwell_sent']=0
        return batch

    def consume(self,source,line,at,wall=None):
        super().consume(source,line,at,wall)
        if source=='TX':
            if line.startswith('BUF '):
                try:
                    _,used,capacity=line.split();self.buffer_feedback=(int(used),int(capacity));self.buffer_at=at
                except ValueError:pass
            elif line.startswith('VLC BUFFER '):
                f=dict(re.findall(r'(\w+)=(\d+)',line))
                if 'used' in f and 'capacity' in f:self.buffer_feedback=(int(f['used']),int(f['capacity']));self.buffer_at=at
            elif line.startswith('QUEUED '):
                f=dict(re.findall(r'(\w+)=(\d+)',line))
                if 'used' in f and 'free' in f:self.buffer_feedback=(int(f['used']),int(f['used'])+int(f['free']));self.buffer_at=at
                self.udp_waiting=False
            elif line.startswith('REJECT '):
                self.udp_waiting=False
                if self.active and 'buffer_full' not in line:self.finish_picture('failed','TX rejected picture: '+line)
            if self.active and line=='TX MSG queued in LOCAL buffer':self.active['admitted']+=1
        if source!='RX' or not line.startswith('RX message: '):return
        text=line[len('RX message: '):]
        if not text.startswith(('PX1:','PH2:','PD2:')):return
        try:
            fragment=parse_fragment(text)
            if fragment and self.active and fragment['image_id']==self.active['picture'].image_id:
                key=fragment['key']
                if key>=len(self.active['records']) or self.active['records'][key]!=text:
                    raise ValueError('Received fragment differs from the submitted image.')
            p=self.assembler.feed(text,at)
            if fragment:
                keys,header,pixels=self.assembler.progress(fragment['image_id'])
                if self.active and fragment['image_id']==self.active['picture'].image_id:self.active['acked'].update(keys)
                if p is None and header:
                    self.render_pixels(self.received_canvas,pixels,header['width'],header['height'])
                    self.received_caption.set(f'Image {fragment["image_id"]:04X} · {len(keys)-1}/{header["count"]} data chunks · PARTIAL, not yet verified; gray pixels are missing')
        except ValueError as error:
            self.image_status.set(str(error))
            if self.active and 'Whole-image CRC32' in str(error):self.finish_picture('failed',str(error))
            return
        if p is None:return
        if p.image_id in self.received:
            if self.received[p.image_id]!=p.data:self.image_status.set('Conflicting data for a previously received image ID.');return
        else:
            directory=self.session.path/'text_images';directory.mkdir(exist_ok=True)
            target=directory/f'received_{p.image_id:04X}.png';save_png(p,target)
            (directory/f'received_{p.image_id:04X}.json').write_text(json.dumps(dict(image_id=f'{p.image_id:04X}',received_at=wall or timestamp(),records=p.records(),width=p.width,height=p.height,data_hex=p.data.hex(),origin='RX message only',checksum_verified=True),indent=2),encoding='utf-8')
            self.received[p.image_id]=p.data
            self.render_pixels(self.received_canvas,p.pixels(),p.width,p.height)
        self.last_received_at=at;self.last_received_id=p.image_id
        if self.active and p.image_id==self.active['picture'].image_id:
            if (p.data,p.width,p.height)!=(self.active['picture'].data,self.active['picture'].width,self.active['picture'].height):self.finish_picture('failed','RX image differs from source.');return
            self.finish_picture('verified',f'VERIFIED · image {p.image_id:04X} matches the source pixels received over light')

    def finish_picture(self,state,message):
        if not self.active:return
        a=self.active;self.active=None;self.udp_waiting=False
        self.send_picture_button.configure(state='normal');self.image_status.set(message)
        elapsed=(time.monotonic()-a['started'])*1000
        result=dict(image_id=f'{a["picture"].image_id:04X}',status=state,started=a['timestamp'],finished=timestamp(),
                    route=a['route'],manual_start=a['start_now'],elapsed_to_result_ms=round(elapsed,1),
                    submitted_repeats=a['submitted'],usb_queue_acknowledgements=a['admitted'],
                    width=a['picture'].width,height=a['picture'].height,image_bytes=len(a['picture'].data),
                    text_record_bytes=51,unique_text_records=len(a['records']),records=a['records'],
                    rx_verified=state=='verified',source_file=a['source'].name,
                    received_file=f'received_{a["picture"].image_id:04X}.png' if state=='verified' else None,
                    tx=dict(self.metrics.tx),rx=dict(self.metrics.rx),message=message)
        self.transfers.append(result)
        (a['directory']/f'transfer_{a["picture"].image_id:04X}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        self.image_detail.set(f'Button → verified RX result: {elapsed:.0f} ms. Submitted repeats: {a["submitted"]}; unique images: {1 if state=="verified" else 0}. Queued repeats can still drain. Source remains {a["route"]}.')
        if a['start_now'] and self.worker:self.send_command('TX','AUTO')

    def save_report(self,notify=True):
        path=super().save_report(False)
        if path:
            sections=[]
            for result in getattr(self,'transfers',[]):
                directory=self.session.path/'text_images'
                pictures=[]
                for label,key in [('Source','source_file'),('Received from RX','received_file')]:
                    filename=result.get(key)
                    if filename and (directory/filename).exists():
                        data=base64.b64encode((directory/filename).read_bytes()).decode('ascii')
                        pictures.append(f'<figure><figcaption>{label}</figcaption><img style="image-rendering:pixelated;max-width:384px" src="data:image/png;base64,{data}"></figure>')
                sections.append('<article><h3>Image '+html.escape(result['image_id'])+' · '+html.escape(result['status'])+'</h3><p>'+html.escape(result['route'])+' · button to result '+str(result['elapsed_to_result_ms'])+' ms · submitted repetitions '+str(result['submitted_repeats'])+'</p><div style="display:flex;gap:20px;flex-wrap:wrap">'+''.join(pictures)+'</div></article>')
            text=Path(path).read_text(encoding='utf-8')
            extra='<section><h2>Text-image optical demo</h2><p>Received images originate only from validated RX text records. Repeated packets are not additional unique images. Timing includes software, queueing and calibration. Existing frame delivery statistics remain separate.</p>'+''.join(sections)+'</section>'
            anchor='</body>' if '</body>' in text else '</main>'
            Path(path).write_text(text.replace(anchor,extra+anchor),encoding='utf-8')
            if notify:messagebox.showinfo('Demo results saved',str(path))
        return path

    def new_session(self):
        if self.active:self.image_status.set('Cancel the image transfer before creating a new session.');return False
        if super().new_session():
            self.received={};self.transfers=[];self.assembler=ImageAssembler();self.last_received_at=None;self.render_pixels(self.received_canvas,None)
            self.received_caption.set('No image received in this session.');return True
        return False

    def close(self):
        if self.active:self.finish_picture('cancelled','Dashboard closed; unsent repetitions cancelled.')
        super().close()

if __name__=='__main__':
    window=tk.Tk();PixelDashboard(window);window.mainloop()
