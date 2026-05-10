/** All-pairs shortest paths (non-negative weights). Unreachable = +Infinity. */

export function dijkstraAllPairs(
  n: number,
  adj: Array<Array<{ to: number; w: number }>>,
): number[][] {
  const dm: number[][] = [];
  const unreachable = Number.POSITIVE_INFINITY;
  for (let s = 0; s < n; s++) {
    const dist = new Array<number>(n).fill(unreachable);
    const used = new Array<boolean>(n).fill(false);
    dist[s] = 0;

    for (let iter = 0; iter < n; iter++) {
      let v = -1;
      let best = unreachable;
      for (let i = 0; i < n; i++) {
        if (!used[i] && dist[i] < best) {
          best = dist[i];
          v = i;
        }
      }
      if (v === -1) break;
      used[v] = true;
      for (const e of adj[v]) {
        const nd = dist[v] + e.w;
        if (nd < dist[e.to]) dist[e.to] = nd;
      }
    }

    dm.push(dist.map((x) => (x === unreachable ? unreachable : Math.max(0, Math.round(x)))));
  }
  return dm;
}
