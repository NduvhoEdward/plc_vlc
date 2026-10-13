import test from 'node:test';
import assert from 'node:assert/strict';
import { simulate } from '../public/simulation.js';
import { onRequest } from '../functions/api/game.js';
import { localD1 } from './d1-local.js';
const db = localD1();
const call = async (body, origin='https://example.test') => {
  const response = await onRequest({env:{GAME_DB:db}, request:new Request('https://example.test/api/game', body ? {method:'POST',headers:{Origin:origin,'CF-Connecting-IP':'192.0.2.1'},body:JSON.stringify(body)} : {})});
  return {status:response.status, data:await response.json()};
};
test('simulation conserves source data and reports finite storage tradeoff', () => {
  for(const level of ['calm','busy','harsh'])for(const cap of [.5,4,32]){
    const s=simulate(cap,level);
    assert.ok(Math.abs(s.sent/s.total*100+s.lossPct+s.pendingPct-100)<1e-7);
    assert.ok(s.peak<=cap+1e-8);
    assert.ok(s.score>=0&&s.score<=1000);
  }
  assert.ok(simulate(.5,'harsh').missingPct>simulate(32,'harsh').missingPct);
  assert.ok(simulate(32,'harsh').delayMs>simulate(.5,'harsh').delayMs);
});
test('server ranks only completed rounds and recalculates all three scores',async()=>{
  const start=await call({action:'start',name:'Test player'});assert.equal(start.status,200);
  const credentials={id:start.data.id,token:start.data.token};
  assert.equal((await call({action:'attempt',...credentials,index:2,cap:4})).status,409);
  const first=await call({action:'attempt',...credentials,index:0,cap:4,score:999999});
  assert.equal(first.data.result.score,simulate(4,'calm').score);
  assert.equal((await call()).data.entries.length,0);
  const repeated=await call({action:'attempt',...credentials,index:0,cap:4});
  assert.equal(repeated.data.next,1);
  await call({action:'attempt',...credentials,index:1,cap:8});
  const last=await call({action:'attempt',...credentials,index:2,cap:12});assert.equal(last.data.complete,true);
  const entries=(await call()).data.entries;assert.equal(entries.length,1);
  assert.equal(entries[0].score,Math.round((simulate(4,'calm').score+simulate(8,'busy').score+simulate(12,'harsh').score)/3));
});
test('API rejects cross-origin submissions, unsafe names and invalid capacities',async()=>{
  assert.equal((await call({action:'start',name:'Cross'},'https://other.test')).status,403);
  assert.equal((await call({action:'start',name:'<script>'})).status,400);
  const start=(await call({action:'start',name:'Range test'})).data;
  assert.equal((await call({action:'attempt',id:start.id,token:start.token,index:0,cap:1000})).status,400);
  assert.equal((await call({action:'attempt',id:start.id,token:'fake',index:0,cap:4})).status,403);
});
test('a nickname occupies only one place and keeps its best complete round',async()=>{
  const start=(await call({action:'start',name:'TEST PLAYER'})).data;
  for(let index=0;index<3;index++)await call({action:'attempt',id:start.id,token:start.token,index,cap:.5});
  const entries=(await call()).data.entries;
  assert.equal(entries.filter(x=>x.name.toLowerCase()==='test player').length,1);
  assert.equal(entries[0].name,'Test player');
});
