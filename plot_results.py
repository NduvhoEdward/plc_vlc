from pathlib import Path
import csv
import json
import sys
sys.path.insert(0, str(Path(__file__).parent / '.plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).parent / 'public'
(root / 'data').mkdir(exist_ok=True)
workspace = Path(__file__).parent.parent
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#586577','xtick.color':'#586577','ytick.color':'#586577','axes.edgecolor':'#d3dce6','savefig.facecolor':'white','svg.fonttype':'none'})
source = workspace / 'text_image_vlc_demo/tests/highres_live_acceptance.json'
if source.exists():
    records = json.loads(source.read_text())['records']
    points = [{'width':r['width'],'height':r['height'],'bytes':r['image_bytes'],'seconds':r['elapsed_to_result_ms']/1000,'verified':r['rx_verified']} for r in records]
else:
    points = [{'width':int(r['width']),'height':int(r['height']),'bytes':int(r['bytes']),'seconds':float(r['seconds']),'verified':r['verified']=='True'} for r in csv.DictReader((root / 'data/image-tests.csv').open())]
fig, ax = plt.subplots(figsize=(7,4), layout='constrained')
bars = ax.bar([f"{r['width']} × {r['height']}" for r in points], [r['seconds'] for r in points], color=['#c0622a','#1d93cf','#16202e'], width=.55)
ax.set_ylabel('Time to verified image (seconds)'); ax.set_xlabel('Monochrome image dimensions'); ax.set_ylim(0,10); ax.set_axisbelow(True); ax.grid(axis='y',alpha=.18)
for bar, point in zip(bars,points):
    ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.2,f"{point['seconds']:.3f} s",ha='center',fontweight='bold',color='#16202e')
fig.savefig(root / 'assets/image-performance.svg'); plt.close(fig)
source = workspace / 'vlc_150khz_test/dashboard/results/20261012_174423_6c2ab0/metrics.csv'
if source.exists():
    rows = list(csv.DictReader(source.open()))
    trace = [{'seconds':float(r['elapsed_s']),'fill_pct':float(r['buffer_pct'])} for r in rows if r.get('buffer_pct') and float(r['elapsed_s'])<=120]
else:
    trace = [{'seconds':float(r['seconds']),'fill_pct':float(r['fill_pct'])} for r in csv.DictReader((root / 'data/fifo-trace.csv').open())]
fig, ax = plt.subplots(figsize=(7,4),layout='constrained')
ax.plot([x['seconds'] for x in trace],[x['fill_pct'] for x in trace],color='#1d93cf',linewidth=2)
ax.axhline(75,color='#c0622a',linestyle='--',label='75% startup / refill threshold')
ax.set_ylim(0,100); ax.set_xlim(0,120); ax.set_ylabel('Dashboard-reported buffer fill (%)'); ax.set_xlabel('Elapsed session time (seconds)'); ax.grid(alpha=.18); ax.legend(loc='lower right',frameon=False,fontsize=9)
fig.savefig(root / 'assets/fifo-performance.svg'); plt.close(fig)
for filename, data in [('image-tests.csv',points),('fifo-trace.csv',trace)]:
    with (root / 'data' / filename).open('w',newline='',encoding='utf-8') as file:
        writer=csv.DictWriter(file,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
(root / 'data/README.md').write_text('''# Published test extracts
Image plot: text_image_vlc_demo/tests/highres_live_acceptance.json, 12 October 2026. LOCAL USB → light route. All three pixel comparisons verified. Times include host pacing and receiver feedback; not optical flight time or bare link bitrate.
FIFO plot: vlc_150khz_test/dashboard/results/20261012_174423_6c2ab0/metrics.csv, first 120 session seconds with reported occupancy (7.063 s onward), 12 October 2026. PLC-labelled gateway session. Repeated values may reflect dashboard snapshots. This is not a controlled worst-case outage experiment or proof of a specific throttling policy.
Only chart fields were exported. No device addresses, raw payloads or credentials are included.
''',encoding='utf-8')
print(f'Plotted {len(points)} verified images and {len(trace)} recorded FIFO samples.')
