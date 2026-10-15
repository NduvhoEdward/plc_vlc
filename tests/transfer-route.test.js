import test from 'node:test';
import assert from 'node:assert/strict';
import {routeLinks} from '../public/transfer-route.js';
test('PLC paths share a reported stage and optical link pulses until verified',()=>{
 assert.deepEqual(routeLinks('waiting'),Array(5).fill('waiting'));
 assert.deepEqual(routeLinks('queued'),['done','waiting','waiting','waiting','waiting']);
 assert.deepEqual(routeLinks('plc'),['done','done','active','active','waiting']);
 assert.deepEqual(routeLinks('vlc'),['done','done','active','active','active']);
 assert.equal(routeLinks('confirmed')[4],'active');
 assert.deepEqual(routeLinks('confirmed','confirmed'),Array(5).fill('done'));
});
test('loss, failure and cancellation stop pulsing without confirming optical reception',()=>{
 for(const status of ['paused','failed','cancelled','stopped']){
  const links=routeLinks('vlc',status);
  assert.ok(!links.includes('active'));assert.notEqual(links[4],'done');
 }
});
