import test from 'node:test';
import assert from 'node:assert/strict';
import { formatControlTurn } from '../public/control-turn.js';
test('room updates and timer ticks show the same controller countdown', () => {
 const room = { controller: 'me', leaseUntil: 61000, queue: [] };
 for (let now=1000;now<=61000;now+=1000) {
  const heartbeatLabel = formatControlTurn(structuredClone(room), 'me', now);
  const timerLabel = formatControlTurn(room, 'me', now);
  assert.equal(heartbeatLabel,timerLabel);
  assert.equal(timerLabel,((61000-now)/1000)+' s remaining');
 }
});
test('waiting visitors keep queue position until their control turn', () => {
 const room={controller:'someone',leaseUntil:61000,queue:['first','me']};
 assert.equal(formatControlTurn(room,'me',1000),'Queue position 2');
 assert.equal(formatControlTurn(room,'me',10000),'Queue position 2');
 room.controller='me';room.queue=['first'];
 assert.equal(formatControlTurn(room,'me',10000),'51 s remaining');
 room.active={id:'transfer'};
 assert.equal(formatControlTurn(room,'me',11000),'Transfer in progress');
});
test('expired leases and absent visitor state do not show invalid countdowns',()=>{
 assert.equal(formatControlTurn({controller:'me',leaseUntil:1000},'me',2000),'0 s remaining');
 assert.equal(formatControlTurn(null,'me'),'Not in queue');
 assert.equal(formatControlTurn({controller:null},null),'Not in queue');
});
