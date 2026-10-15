import test from 'node:test';
import assert from 'node:assert/strict';
import {routeLinks} from '../public/transfer-route.js';
test('PLC paths share a reported stage and optical link pulses until verified',()=>{
 assert.deepEqual(routeLinks('waiting'),Array(6).fill('waiting'));
 assert.deepEqual(routeLinks('queued'),['active','waiting','waiting','waiting','waiting','waiting']);
 assert.deepEqual(routeLinks('plc'),['done','active','active','active','waiting','waiting']);
 assert.deepEqual(routeLinks('vlc'),['done','active','active','active','active','waiting']);
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
