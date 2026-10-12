
(function(){
const DRAIN=12.5, SRC=10, LINE=40, DT=0.01, DUR=60, N=DUR/DT, YMAX=32;
const LV={calm:{gap:6,out:.3},busy:{gap:3,out:.5},harsh:{gap:1.5,out:.8}};
const $=id=>document.getElementById(id);
const cv=$('cv'), ctx=cv.getContext('2d');
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function rng(s){return function(){s|=0;s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function makeTrace(l){
  const r=rng(11), p=LV[l], up=new Uint8Array(N).fill(1); let t=0, longest=0;
  while(t<DUR){
    t+=-p.gap*Math.log(1-r()); const d=-p.out*Math.log(1-r());
    longest=Math.max(longest,Math.min(d,DUR-t));
    for(let i=Math.floor(t/DT);i<Math.min(N,Math.floor((t+d)/DT));i++) up[i]=0;
    t+=d;
  }
  return {up,longest};
}
let S=null, raf=0;
function fit(){const d=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;cv.width=w*d;cv.height=h*d;ctx.setTransform(d,0,0,d,0,0)}
function draw(){
  const w=cv.clientWidth,h=cv.clientHeight,pad=6; ctx.clearRect(0,0,w,h);
  if(!S) return;
  const E=S.i-1;
  const X=i=>pad+(w-2*pad)*i/N, Y=v=>h-pad-(h-2*pad)*Math.min(v,YMAX)/YMAX;
  ctx.fillStyle=css('--copper-soft');
  let a=-1; for(let i=0;i<=E;i++){const d=!S.tr.up[i]; if(d&&a<0)a=i; if((!d||i===E)&&a>=0){ctx.fillRect(X(a),0,X(i)-X(a),h);a=-1}}
  ctx.strokeStyle=css('--ink');ctx.setLineDash([6,5]);ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(0,Y(S.cap));ctx.lineTo(w,Y(S.cap));ctx.stroke();ctx.setLineDash([]);
  ctx.strokeStyle=css('--beam');ctx.lineWidth=2;ctx.beginPath();
  for(let i=0;i<=E;i++){const x=X(i),y=Y(S.occ[i]);i?ctx.lineTo(x,y):ctx.moveTo(x,y)} ctx.stroke();
  ctx.fillStyle=css('--bad');
  for(let i=0;i<=E;i++) if(S.dropAt[i]) ctx.fillRect(X(i)-1,h-pad-12,2.5,12);
}
function stats(done){
  const lost=S.total?100*S.drop/S.total:0;
  $('sLost').textContent=lost.toFixed(1)+'%';
  $('sPeak').textContent=S.peak.toFixed(1)+' kB';
  $('sDelay').textContent=Math.round(1000*S.peak/DRAIN)+' ms';
  $('sOut').textContent=S.tr.longest.toFixed(2)+' s';
  if(!done) return;
  const v=$('verdict');
  if(lost<1){v.style.color=css('--ok');v.textContent=S.cap>4?'Under 1% lost. Can you do it with less memory?':'Under 1% lost with only '+S.cap.toFixed(1)+' kB. Try Harsh interference.'}
  else{v.style.color=css('--bad');v.textContent=lost.toFixed(1)+'% lost. The buffer overflowed during bursts. Try more memory.'}
}
function step(){
  const i=S.i, tr=S.tr; S.upq+=SRC*DT; let dropped=0;
  if(tr.up[i]){const mv=Math.min(S.upq,LINE*DT); S.upq-=mv; const acc=Math.min(mv,S.cap-S.buf); S.buf+=acc; dropped=mv-acc}
  S.drop+=dropped; S.total+=SRC*DT; S.dropAt[i]=dropped>1e-9?1:0;
  S.buf-=Math.min(S.buf,DRAIN*DT); S.occ[i]=S.buf; S.peak=Math.max(S.peak,S.buf);
}
function frame(){
  const fast=matchMedia('(prefers-reduced-motion:reduce)').matches, k=fast?N:10;
  for(let j=0;j<k&&S.i<N-1;j++){step();S.i++}
  draw(); stats(false);
  if(S.i<N-1) raf=requestAnimationFrame(frame); else {step(); S.i++; draw(); stats(true); $('run').disabled=false}
}
function run(){
  cancelAnimationFrame(raf); fit();
  S={cap:+$('cap').value,tr:makeTrace($('lvl').value),i:0,upq:0,buf:0,drop:0,total:0,peak:0,occ:new Float32Array(N),dropAt:new Uint8Array(N)};
  $('verdict').textContent=''; $('run').disabled=true; frame();
}
$('cap').addEventListener('input',e=>{$('capv').textContent=(+e.target.value).toFixed(1)+' kB'});
$('run').addEventListener('click',run);
addEventListener('resize',()=>{fit();draw()});
fit();
})();
