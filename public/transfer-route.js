// Hardware stages cover the PLC path as a whole, not individual HomePlug hops.
export function routeLinks(stage, status = 'active') {
  if (status === 'confirmed') return Array(5).fill('done');
  const progress = {waiting:0,prepared:0,uploaded:1,queued:1,accepted:2,plc:2,vlc:2,confirmed:2}[stage] ?? 0;
  const links = Array.from({length:5}, (_, i) => i < progress ? 'done' : 'waiting');
  if (status === 'active') {
    if (stage === 'prepared') links[0]='active';
    if (stage === 'uploaded' || stage === 'accepted') links[progress]='active';
    if (stage === 'plc') links[2]=links[3]='active';
    if (stage === 'vlc' || stage === 'confirmed') links[2]=links[3]=links[4]='active';
  } else if (progress < 5) links[progress] = status === 'paused' ? 'paused' : 'stopped';
  return links;
}
