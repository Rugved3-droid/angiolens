// Web Worker: angle-space maps off the UI thread. Purely geometric (see metrics.ts guard).
import type { Vec3 } from "./geometry";
import { angleMaps, type Samples } from "./metrics";

export interface MapRequest {
  key: string;
  iso: Vec3;
  target: Samples;
  bif: Vec3[];
  others: Samples[];
  step: number;
}

self.onmessage = (ev: MessageEvent<MapRequest>) => {
  const { key, iso, target, bif, others, step } = ev.data;
  const t0 = performance.now();
  const maps = angleMaps(iso, target, bif, others, step, (done, total) =>
    (self as unknown as Worker).postMessage({ key, progress: done / total }));
  (self as unknown as Worker).postMessage({ key, maps, ms: performance.now() - t0 });
};
