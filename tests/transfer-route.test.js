import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {routeLinks,routeDisplayStage,routeActiveNode} from '../public/transfer-route.js';

test('fresh TX streaming highlights the optical link before any RX record',()=>{
 const feedback={id:'current',at:1000,streaming:1,plc:'online'};
 const stage=routeDisplayStage('plc',feedback,'current',1500);
 assert.equal(stage,'vlc-tx');
 assert.deepEqual(routeLinks(stage),['done','forwarding','forwarding','forwarding','active','waiting']);
 assert.equal(routeLinks(stage)[5],'waiting');
 for(const status of ['paused','failed','cancelled','stopped']) assert.ok(!routeLinks(stage,status).includes('active'));
});

test('stale, idle, offline, simulated and other-transfer TX feedback cannot advance the route',()=>{
 const feedback={id:'current',at:1000,streaming:1,plc:'online'};
 for(const patch of [{at:-2000},{at:2000},{streaming:0},{streaming:undefined},{plc:'offline'},{simulated:true},{id:'old'}]) {
  assert.equal(routeDisplayStage('plc',{...feedback,...patch},'current',1500),'plc');
 }
 assert.equal(routeDisplayStage('queued',feedback,'current',1500),'queued');
 assert.equal(routeDisplayStage('plc',feedback,null,1500),'plc');
 assert.equal(routeDisplayStage('vlc',feedback,'current',5000),'vlc');
});

test('telemetry updates the displayed route without an RX stage event and never resumes a stopped route',()=>{
 const elements=new Map();
 const element=()=>({dataset:{},classList:{},children:[],textContent:'',setAttribute(){},removeAttribute(){},querySelector:()=>({textContent:''})});
 const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 get('journey').children=Array.from({length:7},element);
 const links=Array.from({length:6},element),nodes=Array.from({length:7},element);
 const context=vm.createContext({$:get,document:{querySelectorAll:selector=>selector==='.route-link'?links:nodes},
  routeLinks,routeDisplayStage,routeActiveNode,mode:'live',busy:true,room:{online:true,active:{id:'one',owner:'me'}},session:'me',
  transferId:'one',socket:{readyState:1},routeStage:'plc',routeStatus:'active',txFeedback:null,
  stageIndex:4,lastTelemetry:0,stages:['prepared','uploaded','queued','accepted','plc','vlc','confirmed']});
 const source=readFileSync(new URL('../public/studio.js',import.meta.url),'utf8');
 vm.runInContext(source.slice(source.indexOf('function showRoute('),source.indexOf('function focusRoute(')),context);
 vm.runInContext(source.slice(source.indexOf('function showTelemetry('),source.indexOf('function complete(')),context);
 vm.runInContext("showTelemetry({streaming:1,plc:'online'})",context);
 assert.equal(links[4].dataset.state,'active');
 assert.equal(links[5].dataset.state,'waiting');
 assert.match(get('route-status').textContent,/TX is transmitting.*Waiting for receiver/);
 assert.equal(get('journey').children[5].className,'current');
 assert.equal(nodes[4].dataset.active,'true');
 assert.equal(nodes[2].dataset.active,'false');
 assert.deepEqual(nodes.map(node=>node.dataset.done),['true','true','true','true','false','false','false']);
 vm.runInContext("showTelemetry({streaming:0,plc:'online'})",context);
 assert.equal(links[4].dataset.state,'waiting');
 vm.runInContext("showRoute('plc','stopped'); showTelemetry({streaming:1,plc:'online'})",context);
 assert.ok(links.every(link=>link.dataset.state!=='active'));
 assert.ok(nodes.every(node=>node.dataset.active==='false'));
});

test('VLC station focus stays on LED transmission, without marking reception complete',()=>{
 assert.equal(routeActiveNode('plc'),2);
 assert.equal(routeActiveNode('vlc-tx'),4);
 assert.equal(routeActiveNode('vlc'),4);
 for(const status of ['paused','stopped','confirmed'])assert.equal(routeActiveNode('vlc-tx',status),-1);
});
test('PLC paths share a reported stage and optical link pulses until verified',()=>{
 assert.deepEqual(routeLinks('waiting'),Array(6).fill('waiting'));
 assert.deepEqual(routeLinks('queued'),['active','waiting','waiting','waiting','waiting','waiting']);
 assert.deepEqual(routeLinks('plc'),['done','active','active','active','waiting','waiting']);
 assert.deepEqual(routeLinks('vlc'),['done','forwarding','forwarding','forwarding','active','waiting']);
 assert.equal(routeLinks('confirmed')[4],'active');
 assert.deepEqual(routeLinks('confirmed','confirmed'),Array(6).fill('done'));
});
test('loss, failure and cancellation stop pulsing without confirming optical reception',()=>{
 for(const status of ['paused','failed','cancelled','stopped']){
  const links=routeLinks('vlc',status);
  assert.ok(!links.includes('active'));assert.notEqual(links[4],'done');
 }
});

test('recipient delivery waits for verified completion',()=>{assert.equal(routeLinks('vlc')[5],'waiting');assert.equal(routeLinks('confirmed')[5],'waiting');assert.equal(routeLinks('confirmed','confirmed')[5],'done');});
