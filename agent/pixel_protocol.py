"""Complete bit-packed monochrome pictures carried as ordinary printable text."""
import binascii,base64,math,time,zlib
from dataclasses import dataclass

WIDTH, HEIGHT = 16, 8
MAX_PIXELS=128*64
CHUNK_BYTES=24

@dataclass(frozen=True)
class Picture:
    image_id: int
    width: int
    height: int
    data: bytes

    def pixels(self):
        return [bool(self.data[i//8] & (128 >> (i%8))) for i in range(self.width*self.height)]

    def record(self):
        validate(self)
        header=f'{self.image_id:04X}:{self.width}:{self.height}:'
        crc=binascii.crc_hqx(header.encode('ascii')+self.data,0xffff)
        result=f'PX1:{header}{self.data.hex().upper()}:{crc:04X}'
        if len(result)>51:raise ValueError('Picture record exceeds the existing 51-byte text limit.')
        return result

    def records(self):
        validate(self)
        if self.width*self.height<=128:return [self.record()]
        count=math.ceil(len(self.data)/CHUNK_BYTES)
        head=f'PH2:{self.image_id:04X}:{self.width:04X}:{self.height:04X}:{count:04X}:{zlib.crc32(self.data):08X}'
        records=[(head+f':{binascii.crc_hqx(head.encode(),0xffff):04X}').ljust(51,'.')]
        for index in range(count):
            encoded=base64.b64encode(self.data[index*24:(index+1)*24].ljust(24,b'\0')).decode('ascii')
            body=f'PD2:{self.image_id:04X}:{index:04X}:{encoded}'
            records.append(body+f':{binascii.crc_hqx(body.encode(),0xffff):04X}')
        assert all(len(r)==51 for r in records)
        return records

def validate(p):
    if not 0<=p.image_id<=65535 or not 1<=p.width<=128 or not 1<=p.height<=128 or p.width*p.height>MAX_PIXELS:
        raise ValueError('Invalid picture ID or dimensions.')
    if len(p.data)!=(p.width*p.height+7)//8:raise ValueError('Invalid packed pixel length.')
    remainder=p.width*p.height%8
    if remainder and p.data[-1]&((1<<(8-remainder))-1):raise ValueError('Nonzero padding pixels.')

def from_pixels(pixels,image_id,width=WIDTH,height=HEIGHT):
    if len(pixels)!=width*height:raise ValueError('Pixel count does not match dimensions.')
    data=bytearray((len(pixels)+7)//8)
    for i,black in enumerate(pixels):
        if black:data[i//8]|=128>>(i%8)
    result=Picture(image_id,width,height,bytes(data));validate(result);return result

def parse_record(text):
    if not text.startswith('PX1:'):return None
    try:
        if len(text)>51:raise ValueError('Oversized picture record.')
        tag,identifier,w,h,packed,checksum=text.split(':')
        if len(identifier)!=4 or len(checksum)!=4 or any(c not in '0123456789ABCDEF' for c in identifier+packed+checksum):
            raise ValueError('Invalid hexadecimal fields.')
        picture=Picture(int(identifier,16),int(w),int(h),bytes.fromhex(packed));validate(picture)
        # Canonical representation also rejects alternate dimensions/headers.
        if picture.record()!=text:raise ValueError('Picture checksum or representation does not match.')
        return picture
    except (ValueError,TypeError) as error:
        raise ValueError('Invalid text picture: '+str(error)) from error

def convert_picture(path,threshold=128,width=WIDTH,height=HEIGHT):
    """Preserve aspect ratio; black=1, white=0. Pillow is a PC-only dependency."""
    from PIL import Image,ImageOps
    if not 0<=threshold<=255:raise ValueError('Threshold must be 0..255.')
    with Image.open(path) as source:
        rgba=ImageOps.exif_transpose(source).convert('RGBA')
        white=Image.new('RGBA',rgba.size,'white');white.alpha_composite(rgba)
        gray=ImageOps.contain(white.convert('L'),(width,height),Image.Resampling.LANCZOS)
        fitted=Image.new('L',(width,height),255)
        fitted.paste(gray,((width-gray.width)//2,(height-gray.height)//2))
        return [v<threshold for v in fitted.tobytes()]

def save_png(picture,path,scale=None):
    from PIL import Image
    image=Image.new('1',(picture.width,picture.height))
    image.putdata([0 if black else 255 for black in picture.pixels()])
    if scale is None:scale=max(1,min(24,384//picture.width,192//picture.height))
    image.resize((picture.width*scale,picture.height*scale),Image.Resampling.NEAREST).save(path)

def parse_fragment(text):
    if not text.startswith(('PH2:','PD2:')):return None
    if len(text)!=51:raise ValueError('Image fragment must be exactly 51 characters.')
    clean=text.rstrip('.') if text.startswith('PH2:') else text
    try:
        body,checksum=clean.rsplit(':',1)
        if checksum!=f'{binascii.crc_hqx(body.encode("ascii"),0xffff):04X}':raise ValueError('Fragment CRC16 mismatch.')
        fields=body.split(':');identifier=int(fields[1],16)
        if fields[1]!=f'{identifier:04X}' or not 0<=identifier<=65535:raise ValueError('Invalid image ID.')
        if fields[0]=='PH2':
            _,_,w,h,n,c=fields
            width,height,count,crc=int(w,16),int(h,16),int(n,16),int(c,16)
            if not 1<=width<=128 or not 1<=height<=128 or width*height>MAX_PIXELS or not 0<=crc<=0xffffffff:
                raise ValueError('Image dimensions/CRC out of range.')
            validate(Picture(identifier,width,height,b'\0'*((width*height+7)//8)))
            if count!=math.ceil((width*height+7)//8/24):raise ValueError('Invalid fragment count.')
            canonical=f'PH2:{identifier:04X}:{width:04X}:{height:04X}:{count:04X}:{crc:08X}'
            if body!=canonical or clean.ljust(51,'.')!=text:raise ValueError('Noncanonical image header.')
            return dict(kind='header',image_id=identifier,width=width,height=height,count=count,crc32=crc,key=0)
        _,_,index,encoded=fields
        index=int(index,16);data=base64.b64decode(encoded,validate=True)
        if not 0<=index<math.ceil(MAX_PIXELS/8/24) or len(data)!=24:raise ValueError('Invalid fragment index/length.')
        if body!=f'PD2:{identifier:04X}:{index:04X}:{base64.b64encode(data).decode()}':raise ValueError('Noncanonical image fragment.')
        return dict(kind='data',image_id=identifier,index=index,data=data,key=index+1)
    except (ValueError,TypeError,UnicodeError,binascii.Error) as error:
        raise ValueError('Invalid image fragment: '+str(error)) from error

class ImageAssembler:
    """Bounded reassembly from RX alone; duplicates/order do not affect the image."""
    def __init__(self):self.images={}

    def feed(self,text,now=None):
        fragment=parse_fragment(text)
        if fragment is None:return parse_record(text)
        now=time.monotonic() if now is None else now
        self.images={k:v for k,v in self.images.items() if now-v['at']<180}
        identifier=fragment['image_id']
        if identifier not in self.images:
            if len(self.images)>=8:del self.images[min(self.images,key=lambda k:self.images[k]['at'])]
            self.images[identifier]=dict(header=None,chunks={},at=now,picture=None)
        item=self.images[identifier];item['at']=now
        if fragment['kind']=='header':
            if item['header'] and item['header']!=fragment:raise ValueError('Conflicting image metadata.')
            if any(i>=fragment['count'] for i in item['chunks']):raise ValueError('Data index exceeds image header.')
            item['header']=fragment
        else:
            index=fragment['index']
            if item['header'] and index>=item['header']['count']:raise ValueError('Data index exceeds image header.')
            if index in item['chunks'] and item['chunks'][index]!=fragment['data']:raise ValueError('Conflicting image fragment.')
            item['chunks'][index]=fragment['data']
        h=item['header']
        if h and len(item['chunks'])==h['count']:
            size=(h['width']*h['height']+7)//8
            packed=b''.join(item['chunks'][i] for i in range(h['count']))
            if any(packed[size:]):raise ValueError('Invalid last-fragment padding.')
            data=packed[:size]
            if zlib.crc32(data)!=h['crc32']:raise ValueError('Whole-image CRC32 mismatch.')
            picture=Picture(identifier,h['width'],h['height'],data);validate(picture)
            item['picture']=picture;return picture
        return None

    def progress(self,identifier):
        item=self.images.get(identifier)
        if not item:return set(),None,None
        h=item['header'];keys={i+1 for i in item['chunks']}
        if not h:return keys,None,None
        keys.add(0);pixels=[None]*(h['width']*h['height'])
        for index,data in item['chunks'].items():
            for bit in range(24*8):
                offset=index*24*8+bit
                if offset<len(pixels):pixels[offset]=bool(data[bit//8]&(128>>(bit%8)))
        return keys,h,pixels
