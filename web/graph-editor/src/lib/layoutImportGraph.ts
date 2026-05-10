/**
 * Fruchterman–Reingold–style layout for small graphs (no extra deps).
 * Uses an undirected skeleton derived from directed edges.
 */

export type Point = { x: number; y: number };

function norm(dx: number, dy: number): number {
  return Math.sqrt(dx * dx + dy * dy);
}

function snapToGrid(v: number, grid: number): number {
  return Math.round(v / grid) * grid;
}

/**
 * @param n node count 0..n-1
 * @param directedEdges used to build unique undirected pairs for attraction
 */
export function layoutImportGraph(
  n: number,
  directedEdges: Array<{ from: number; to: number }>,
  opts?: { width?: number; height?: number; grid?: number },
): Point[] {
  const width = opts?.width ?? 960;
  const height = opts?.height ?? 640;
  const grid = opts?.grid ?? 16;

  const pairKey = (a: number, b: number) => (a < b ? `${a},${b}` : `${b},${a}`);
  const undirected = new Map<string, [number, number]>();
  for (const e of directedEdges) {
    if (e.from === e.to) continue;
    const k = pairKey(e.from, e.to);
    if (!undirected.has(k)) undirected.set(k, [e.from, e.to]);
  }
  const edgePairs = [...undirected.values()];

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.32;
  const pos: Point[] = Array.from({ length: n }, (_, i) => {
    const ang = (2 * Math.PI * i) / Math.max(1, n);
    return {
      x: centerX + radius * Math.cos(ang),
      y: centerY + radius * Math.sin(ang),
    };
  });

  if (n === 0) return pos;

  const area = width * height;
  const kFR = Math.sqrt(area / Math.max(1, n));
  let temperature = Math.min(width, height) / 10;
  const cooling = 0.92;
  const iters = 88;

  for (let iter = 0; iter < iters; iter++) {
    const disp: Point[] = Array.from({ length: n }, () => ({ x: 0, y: 0 }));

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = pos[i].x - pos[j].x;
        let dy = pos[i].y - pos[j].y;
        const d = Math.max(0.01, norm(dx, dy));
        const rep = (kFR * kFR) / d;
        dx = (dx / d) * rep;
        dy = (dy / d) * rep;
        disp[i].x += dx;
        disp[i].y += dy;
        disp[j].x -= dx;
        disp[j].y -= dy;
      }
    }

    for (const [i, j] of edgePairs) {
      let dx = pos[j].x - pos[i].x;
      let dy = pos[j].y - pos[i].y;
      const d = Math.max(0.01, norm(dx, dy));
      const att = (d * d) / kFR;
      dx = (dx / d) * att;
      dy = (dy / d) * att;
      disp[i].x += dx;
      disp[i].y += dy;
      disp[j].x -= dx;
      disp[j].y -= dy;
    }

    for (let i = 0; i < n; i++) {
      const dDisp = Math.max(0.01, norm(disp[i].x, disp[i].y));
      const move = Math.min(dDisp, temperature);
      pos[i].x += (disp[i].x / dDisp) * move;
      pos[i].y += (disp[i].y / dDisp) * move;
      pos[i].x = Math.max(40, Math.min(width - 40, pos[i].x));
      pos[i].y = Math.max(40, Math.min(height - 40, pos[i].y));
    }

    temperature *= cooling;
  }

  let minX = Infinity;
  let minY = Infinity;
  for (const p of pos) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
  }
  const pad = 48;
  const dx = pad - minX;
  const dy = pad - minY;
  for (const p of pos) {
    p.x = snapToGrid(p.x + dx, grid);
    p.y = snapToGrid(p.y + dy, grid);
  }

  return pos;
}
