export const MODEL_VERSION = 'fifo-v1';
export const CHALLENGES = [{level:'calm',seed:11},{level:'busy',seed:11},{level:'harsh',seed:11}];
export const DRAIN = 12.5, SOURCE = 10, LINE = 40, DT = .01, DURATION = 60;
export function random(seed) { return () => { seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296; }; }
export function simulate(cap, level='busy', seed=11) {
  if (!Number.isFinite(cap)||cap<.5||cap>32||Math.abs(cap*2-Math.round(cap*2))>1e-8) throw new Error('Choose a buffer from 0.5 to 32 kB in 0.5 kB steps.');
  const settings={calm:{gap:6,out:.3},busy:{gap:3,out:.5},harsh:{gap:1.5,out:.8}}[level];
  if(!settings) throw new Error('Unknown interference level.');
  const n=Math.round(DURATION/DT), up=new Uint8Array(n).fill(1), r=random(seed);let t=0,longest=0;
  while(t<DURATION){t+=-settings.gap*Math.log(1-r());const d=-settings.out*Math.log(1-r());if(t>=DURATION)break;longest=Math.max(longest,Math.min(d,DURATION-t));for(let i=Math.floor(t/DT);i<Math.min(n,Math.floor((t+d)/DT));i++)up[i]=0;t+=d;}
  let upstream=0,buffer=0,dropped=0,sent=0,peak=0;const occupancy=new Float32Array(n),dropAt=new Uint8Array(n);
  for(let i=0;i<n;i++){upstream+=SOURCE*DT;if(up[i]){const incoming=Math.min(upstream,LINE*DT);upstream-=incoming;const accepted=Math.min(incoming,Math.max(0,cap-buffer));buffer+=accepted;const loss=incoming-accepted;dropped+=loss;dropAt[i]=loss>1e-8?1:0;}peak=Math.max(peak,buffer);const output=Math.min(buffer,DRAIN*DT);buffer-=output;sent+=output;occupancy[i]=buffer;}
  const total=SOURCE*DURATION,lossPct=100*dropped/total,pendingPct=100*(upstream+buffer)/total,missingPct=Math.min(100,lossPct+pendingPct),delayMs=1000*peak/DRAIN;
  const score=Math.max(0,Math.round(1000-20*missingPct-100*delayMs/1000));
  return {cap,level,seed,lossPct,pendingPct,missingPct,delayMs,peak,longest,sent,total,score,occupancy,dropAt,up};
}
export function summary(result){const {cap,level,lossPct,pendingPct,missingPct,delayMs,peak,longest,score}=result;return {cap,level,lossPct,pendingPct,missingPct,delayMs,peak,longest,score};}
