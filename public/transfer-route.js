// Hardware stages cover the PLC path as a whole, not individual HomePlug hops.
// TX streaming proves emission, not reception. Only use current-transfer feedback.
export function routeDisplayStage(stage, feedback, transferId, now = Date.now()) {
  if (stage === 'plc' && transferId && feedback?.id === transferId &&
      feedback.streaming === 1 && feedback.plc === 'online' && !feedback.simulated &&
      now >= feedback.at && now - feedback.at < 3000) return 'vlc-tx';
  return stage;
}
export function routeLinks(stage, status = 'active') {
  if (status === 'confirmed') return Array(6).fill('done');
  const progress = {waiting:0,prepared:0,uploaded:0,queued:0,accepted:1,plc:1,'vlc-tx':1,vlc:1,confirmed:1}[stage] ?? 0;
  const links = Array.from({length:6}, (_, i) => i < progress ? 'done' : 'waiting');
  if (status === 'active') {
    if (stage === 'prepared' || stage === 'queued') links[0]='active';
    if (stage === 'uploaded' || stage === 'accepted') links[progress]='active';
    if (stage === 'plc') links[1]=links[2]=links[3]='active';
    if (stage === 'vlc-tx' || stage === 'vlc' || stage === 'confirmed') links[1]=links[2]=links[3]=links[4]='active';
  } else if (progress < 6) links[progress] = status === 'paused' ? 'paused' : 'stopped';
  return links;
}
