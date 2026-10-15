import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {QueuedSend,canQueue,estimatedWait} from '../public/visitor-flow.js';
const payload={kind:'text',text:'Hello'};
const ready={online:true,ready:true,controller:null,queue:[],active:null};
test('Send captures one immutable message and joins only once',()=>{
 const q=new QueuedSend();const draft={...payload};
 assert.equal(q.start(draft,{shareDisplay:false},'one'),true);draft.text='Edited';
 assert.equal(q.start(payload,{},'two'),false);
 assert.equal(q.pending.payload.text,'Hello');
 assert.equal(q.next(ready,'me').type,'join');
 assert.equal(q.next(ready,'me'),null);
 assert.equal(q.next({...ready,queue:['me']},'me'),null);
});
test('only the ready controller can dispatch, exactly once',()=>{
 const q=new QueuedSend();q.start(payload,{},'one');
 assert.equal(q.next({...ready,controller:'other',active:{owner:'other'}},'me').type,'join');
 assert.equal(q.next({...ready,controller:'me',ready:false,active:{owner:'other'}},'me'),null);
 assert.equal(q.next({...ready,controller:'me'},'me').type,'submit');
 assert.equal(q.next({...ready,controller:'me'},'me'),null);
});
test('offline or reconciling hardware cancels intent without later automatic sends',()=>{
 for(const room of [{...ready,online:false},{...ready,ready:false}]){
  const q=new QueuedSend();q.start(payload,{},'one');
  assert.equal(q.next(room,'me').type,'paused');
  assert.equal(q.next({...ready,controller:'me'},'me'),null);
  assert.equal(canQueue(room),false);
 }
});
test('cancelled and disconnected queued sends never resume automatically',()=>{
 for(const method of ['cancel','interrupted']){
  const q=new QueuedSend();q.start(payload,{},'one');q.next(ready,'me');
  q[method]();assert.equal(q.next({...ready,controller:'me'},'me'),null);
 }
});
test('dispatched transfer remains recorded on disconnect, preventing duplicate dispatch',()=>{
 const q=new QueuedSend();q.start(payload,{},'one');q.next({...ready,controller:'me'},'me');
 assert.equal(q.interrupted(),false);assert.equal(q.next({...ready,controller:'me'},'me'),null);
});
test('queue estimates distinguish next visitor and longer queues',()=>{
 assert.match(estimatedWait({...ready,queue:['me']},'me'),/next.*30–60 sec/);
 assert.match(estimatedWait({...ready,queue:['a','b','me']},'me'),/3 ahead/);
});
const source=readFileSync(new URL('../public/studio.js',import.meta.url),'utf8');
const sendSource=source.slice(source.indexOf('async function send(intent)'),source.indexOf('function processQueuedSend()'));
function sendContext(){
 let resolveHash;const sent=[],nodes={};
 const context={busy:false,sendAttempt:0,commandSubmitted:false,mode:'live',savedPayload:null,startedAt:0,transferId:null,session:'me',room:{...ready,controller:'me'},canQueue,structuredClone,Date,
  payloadHash:()=>new Promise(resolve=>resolveHash=resolve),socket:{readyState:1,send:value=>sent.push(JSON.parse(value))},queuedSend:new QueuedSend(),syncButtons(){},markStage(){},$:id=>nodes[id]??={hidden:false,textContent:''}};
 vm.createContext(context);vm.runInContext(sendSource,context);
 return {context,sent,resolve:()=>resolveHash('a'.repeat(64))};
}
test('cancellation during async hashing cannot submit afterwards',async()=>{
 const {context,sent,resolve}=sendContext();
 const promise=context.send({payload,id:'one',shareDisplay:false});
 context.busy=false;context.sendAttempt++;resolve();await promise;
 assert.equal(sent.length,0);
});
test('losing a turn during hashing prevents stale submission',async()=>{
 const {context,sent,resolve}=sendContext();
 const promise=context.send({payload,id:'one',shareDisplay:false});
 context.room.controller='other';resolve();await promise;
 assert.equal(sent.filter(m=>m.type==='submit').length,0);
});
test('submission uses the saved payload and sharing choice',async()=>{
 const {context,sent,resolve}=sendContext();
 const input={...payload};const promise=context.send({payload:input,id:'one',shareDisplay:false});
 input.text='Edited later';resolve();await promise;
 assert.equal(sent[0].payload.text,'Hello');assert.equal(sent[0].shareDisplay,false);
});
