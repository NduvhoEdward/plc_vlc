(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let queued = 0, delivered = 0, lost = 0;
  const buffered = () => document.querySelector('input[name="buffer-mode"]:checked').value === 'buffer';
  for (let i = 0; i < 8; i++) $('queue-cells').append(document.createElement('span'));
  function render(input, sent, story) {
    $('demo-input').textContent = input;
    $('demo-output').textContent = `${delivered} sent`;
    $('queue-title').textContent = buffered() ? 'Gateway buffer' : 'No storage';
    $('queue-count').textContent = buffered() ? `${queued} / 8 packets` : 'Direct handoff';
    $('queue-caption').textContent = buffered() ? 'Eight illustrative storage slots' : 'Only packets sent this step can pass';
    [...$('queue-cells').children].forEach((cell, i) => cell.classList.toggle('occupied', i < queued));
    $('queue-cells').classList.toggle('bypassed', !buffered());
    $('demo-loss').textContent = `${lost} packets lost`;
    $('handoff-story').textContent = story;
  }
  function reset() {
    queued = delivered = lost = 0;
    render('Ready', 0, 'Send a burst to compare how the gateway handles arriving data. Changing mode starts a fresh comparison.');
  }
  function step(incoming) {
    let sent, overflow = 0;
    if (buffered()) {
      // The step's output opportunity frees space before remaining arrivals are stored.
      const available = queued + incoming;
      sent = Math.min(2, available);
      queued = Math.min(8, available - sent);
      overflow = Math.max(0, available - sent - 8);
    } else { sent = Math.min(2, incoming); overflow = incoming - sent; }
    delivered += sent; lost += overflow;
    let story;
    if (incoming) story = buffered()
      ? `${sent} packets sent over light; ${queued} wait in the buffer.${overflow ? ` Storage filled: ${overflow} extra packets were lost.` : ' The burst can finish on later steps.'}`
      : `${sent} packets sent over light; ${overflow} were lost because the direct handoff has no storage.`;
    else story = sent ? `PLC input is paused. Stored data keeps the light link supplied: ${sent} sent, ${queued} still waiting.`
      : 'PLC input is paused and no data is stored. The light link has nothing to send; a buffer cannot bridge a gap once it is empty.';
    render(incoming ? '6 arrived' : 'Paused', sent, story);
  }
  $('burst').addEventListener('click', () => step(6));
  $('pause-input').addEventListener('click', () => step(0));
  $('reset-handoff').addEventListener('click', reset);
  document.querySelectorAll('input[name="buffer-mode"]').forEach(el => el.addEventListener('change', reset));
  reset();
})();
