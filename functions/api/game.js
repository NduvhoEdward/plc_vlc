import { simulate, summary, CHALLENGES, MODEL_VERSION } from '../../public/simulation.js';
const DAY=86400000;
const json=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
async function hash(text){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export function validName(value){return typeof value==='string'&&value.trim().length>=1&&value.trim().length<=24&&!/[\p{C}<>]/u.test(value);}
async function schema(db){await db.batch([
 db.prepare('CREATE TABLE IF NOT EXISTS game_rounds (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, name TEXT NOT NULL, ip_day TEXT NOT NULL, created INTEGER NOT NULL, model TEXT NOT NULL, next INTEGER NOT NULL DEFAULT 0, attempts TEXT NOT NULL DEFAULT \'[]\', score INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0)'),
 db.prepare('CREATE INDEX IF NOT EXISTS game_rank ON game_rounds(model,complete,score DESC,created ASC)'),
 db.prepare('CREATE INDEX IF NOT EXISTS game_daily ON game_rounds(ip_day,created)')]);}
export async function onRequest({request,env}){
 try{
  if(!env.GAME_DB)return json({error:'The shared leaderboard is being connected. Practice still works.'},503);
  if(!['GET','POST'].includes(request.method))return json({error:'Method not allowed.'},405);
  if(request.method==='POST'&&request.headers.get('Origin')!==new URL(request.url).origin)return json({error:'Use the game on this website.'},403);
  await schema(env.GAME_DB);const now=Date.now();
  if(request.method==='GET'){
   const rows=await env.GAME_DB.prepare('SELECT name,score,attempts,created FROM (SELECT name,score,attempts,created,ROW_NUMBER() OVER (PARTITION BY lower(name) ORDER BY score DESC,created ASC) AS position FROM game_rounds WHERE model=? AND complete=1 AND created>?) WHERE position=1 ORDER BY score DESC,created ASC LIMIT 20').bind(MODEL_VERSION,now-30*DAY).all();
   return json({model:MODEL_VERSION,entries:rows.results.map((x,i)=>({rank:i+1,name:x.name,score:x.score,attempts:JSON.parse(x.attempts),created:x.created}))});
  }
  if(Number(request.headers.get('Content-Length')||0)>2048)return json({error:'Request too large.'},413);
  const text=await request.text();if(new TextEncoder().encode(text).length>2048)return json({error:'Request too large.'},413);let body;try{body=JSON.parse(text);}catch{return json({error:'Invalid request.'},400);}
  if(!body||typeof body!=='object'||Array.isArray(body))return json({error:'Invalid request.'},400);
  if(body.action==='start'){
   if(!validName(body.name))return json({error:'Use a nickname of 1–24 characters, without special markup.'},400);
   const ipDay=await hash(`${request.headers.get('CF-Connecting-IP')||'unknown'}:${Math.floor(now/DAY)}`);
   const used=await env.GAME_DB.prepare('SELECT COUNT(*) AS count FROM game_rounds WHERE ip_day=? AND created>?').bind(ipDay,now-DAY).first();
   if(used.count>=100)return json({error:'This network has reached today’s game limit. Try practice or return tomorrow.'},429);
   const id=crypto.randomUUID(),token=crypto.randomUUID()+crypto.randomUUID();
   await env.GAME_DB.prepare('INSERT INTO game_rounds(id,token_hash,name,ip_day,created,model) VALUES(?,?,?,?,?,?)').bind(id,await hash(token),body.name.trim(),ipDay,now,MODEL_VERSION).run();
   await env.GAME_DB.prepare('DELETE FROM game_rounds WHERE id IN (SELECT id FROM game_rounds WHERE created<? LIMIT 100)').bind(now-30*DAY).run();
   return json({id,token,challenges:CHALLENGES,model:MODEL_VERSION});
  }
  if(body.action!=='attempt'||typeof body.id!=='string'||body.id.length>40||typeof body.token!=='string'||body.token.length>80||!Number.isInteger(body.index)||body.index<0||body.index>2)return json({error:'Invalid attempt.'},400);
  const row=await env.GAME_DB.prepare('SELECT * FROM game_rounds WHERE id=?').bind(body.id).first();
  if(!row||row.token_hash!==await hash(body.token)||row.created<now-DAY||row.model!==MODEL_VERSION)return json({error:'This round expired. Start a new round.'},403);
  const attempts=JSON.parse(row.attempts);
  if(body.index<row.next){if(attempts[body.index].cap!==body.cap)return json({error:'This attempt is already recorded.'},409);return json({result:attempts[body.index],next:row.next,complete:!!row.complete,score:row.score});}
  if(body.index!==row.next)return json({error:'Complete the attempts in order.'},409);
  let result;try{result=summary(simulate(body.cap,CHALLENGES[body.index].level,CHALLENGES[body.index].seed));}catch(e){return json({error:e.message},400);}
  attempts.push(result);const next=attempts.length,score=Math.round(attempts.reduce((sum,x)=>sum+x.score,0)/next);
  const update=await env.GAME_DB.prepare('UPDATE game_rounds SET attempts=?,next=?,score=?,complete=? WHERE id=? AND next=?').bind(JSON.stringify(attempts),next,score,next===3?1:0,row.id,row.next).run();
  if(update.meta.changes!==1)return json({error:'An attempt was submitted in another tab. Refresh your round.'},409);
  return json({result,next,complete:next===3,score});
 }catch{return json({error:'The leaderboard is temporarily unavailable. Your practice simulation still works.'},503);}
}
