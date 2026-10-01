// Angle-space heatmap: alpha on x (RAO left, LAO right), beta on y (CRAN up). Sequential single-hue ramp
// (blue), low = dark so "near zero" recedes into the dark surface. Hover tooltip, click to set the pose.
import { viewLabel } from "./geometry";

// reference palette blue ramp, 700 -> 100 (dark surface: low values dark)
const RAMP = ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7",
  "#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"];
const rgb = RAMP.map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));

function rampColor(t: number): string {
  const x = Math.min(1, Math.max(0, t)) * (rgb.length - 1);
  const i = Math.min(Math.floor(x), rgb.length - 2);
  const f = x - i;
  const c = rgb[i].map((v, k) => Math.round(v + f * (rgb[i + 1][k] - v)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/** Cell edges halfway between neighbouring samples (handles the uneven +-45 edge rows). */
function edges(v: number[]): number[] {
  const e = [v[0]];
  for (let i = 0; i + 1 < v.length; i++) e.push((v[i] + v[i + 1]) / 2);
  e.push(v[v.length - 1]);
  return e;
}

export interface HeatmapOptions {
  title: string;
  vmax: () => number;
  format: (v: number) => string;
  onPick: (alpha: number, beta: number) => void;
}

export class Heatmap {
  private alpha: number[] = [];
  private beta: number[] = [];
  private values: Float32Array | null = null;
  private pose: [number, number] = [0, 0];
  private optimum: [number, number] | null = null;
  private readonly canvas: HTMLCanvasElement;
  private readonly tip: HTMLDivElement;
  private readonly bar: HTMLCanvasElement;
  private readonly status: HTMLDivElement;
  private readonly M = { l: 36, r: 20, t: 6, b: 26 };

  constructor(host: HTMLElement, private readonly opt: HeatmapOptions) {
    host.classList.add("heatmap");
    host.innerHTML = `<div class="hm-title">${opt.title}</div><div class="hm-plot"><canvas></canvas><div class="hm-tip"></div>
      <div class="hm-status"></div></div><div class="hm-legend"><canvas class="hm-bar"></canvas><span class="hm-lo"></span><span class="hm-hi"></span></div>`;
    this.canvas = host.querySelector(".hm-plot canvas")!;
    this.tip = host.querySelector(".hm-tip")!;
    this.bar = host.querySelector(".hm-bar")!;
    this.status = host.querySelector(".hm-status")!;
    this.canvas.addEventListener("mousemove", (e) => this.hover(e));
    this.canvas.addEventListener("mouseleave", () => (this.tip.style.display = "none"));
    this.canvas.addEventListener("click", (e) => {
      const h = this.hit(e);
      if (h) opt.onPick(this.alpha[h.i], this.beta[h.j]);
    });
  }

  setData(alpha: number[], beta: number[], values: Float32Array | null, status = "") {
    this.alpha = alpha;
    this.beta = beta;
    this.values = values;
    this.status.textContent = status;
    this.status.style.display = status ? "" : "none";
    this.draw();
  }
  setPose(a: number, b: number) { this.pose = [a, b]; this.draw(); }
  setOptimum(o: [number, number] | null) { this.optimum = o; this.draw(); }

  private geom() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio, 2);
    const W = r.width, H = r.height, M = this.M;
    const ax = (a: number) => M.l + ((a + 90) / 180) * (W - M.l - M.r);
    const by = (b: number) => M.t + ((45 - b) / 90) * (H - M.t - M.b);
    return { r, dpr, W, H, ax, by };
  }

  private hit(e: MouseEvent): { i: number; j: number } | null {
    if (!this.alpha.length) return null;
    const { r, ax, by } = this.geom();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const ea = edges(this.alpha), eb = edges(this.beta);
    const i = ea.findIndex((v, k) => k < ea.length - 1 && x >= ax(v) && x <= ax(ea[k + 1]));
    const j = eb.findIndex((v, k) => k < eb.length - 1 && y <= by(v) && y >= by(eb[k + 1]));
    return i >= 0 && j >= 0 ? { i, j } : null;
  }

  private hover(e: MouseEvent) {
    const h = this.hit(e);
    if (!h || !this.values) { this.tip.style.display = "none"; return; }
    const v = this.values[h.j * this.alpha.length + h.i];
    this.tip.style.display = "block";
    this.tip.innerHTML = `<b>${viewLabel(this.alpha[h.i], this.beta[h.j])}</b><br>${this.opt.format(v)}<br><span class="hint">click to move the C-arm</span>`;
    const { r } = this.geom();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    this.tip.style.left = `${Math.min(x + 12, r.width - 130)}px`;
    this.tip.style.top = `${Math.max(y - 46, 0)}px`;
  }

  draw() {
    const { dpr, W, H, ax, by } = this.geom();
    if (!W || !H) return;
    this.canvas.width = Math.round(W * dpr);
    this.canvas.height = Math.round(H * dpr);
    const g = this.canvas.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const vmax = this.scaleMax();
    if (this.values) {
      const ea = edges(this.alpha), eb = edges(this.beta);
      for (let j = 0; j < this.beta.length; j++)
        for (let i = 0; i < this.alpha.length; i++) {
          g.fillStyle = rampColor(this.values[j * this.alpha.length + i] / vmax);
          const x0 = ax(ea[i]), x1 = ax(ea[i + 1]), y0 = by(eb[j + 1]), y1 = by(eb[j]);
          g.fillRect(x0, y0, x1 - x0 + 0.5, y1 - y0 + 0.5);
        }
    }
    // recessive axes
    const ink = getComputedStyle(document.documentElement).getPropertyValue("--muted") || "#8a96a3";
    g.strokeStyle = "rgba(255,255,255,0.18)";
    g.lineWidth = 1;
    g.font = "10px system-ui";
    g.fillStyle = ink;
    g.textAlign = "center";
    for (const a of [-90, -45, 0, 45, 90]) {
      g.beginPath(); g.moveTo(ax(a), by(45)); g.lineTo(ax(a), by(-45)); g.stroke();
      g.fillText(a === 0 ? "AP" : `${a < 0 ? "RAO" : "LAO"}${Math.abs(a)}`, ax(a), H - 14);
    }
    g.textAlign = "right";
    for (const b of [-45, 0, 45]) {
      g.beginPath(); g.moveTo(ax(-90), by(b)); g.lineTo(ax(90), by(b)); g.stroke();
      const y = b === 45 ? by(b) + 8 : b === -45 ? by(b) - 2 : by(b) + 3;
      g.fillText(b === 0 ? "0" : `${b > 0 ? "CRA" : "CAU"}${Math.abs(b)}`, ax(-90) - 3, y);
    }
    g.textAlign = "center";
    g.fillText("primary angle", (ax(-90) + ax(90)) / 2, H - 2);
    // optimum (hollow ring with surface halo) and current pose (crosshair)
    if (this.optimum) {
      const [x, y] = [ax(this.optimum[0]), by(this.optimum[1])];
      g.lineWidth = 4; g.strokeStyle = "#12151a"; g.beginPath(); g.arc(x, y, 6, 0, 2 * Math.PI); g.stroke();
      g.lineWidth = 2; g.strokeStyle = "#ffffff"; g.beginPath(); g.arc(x, y, 6, 0, 2 * Math.PI); g.stroke();
    }
    const [px, py] = [ax(this.pose[0]), by(this.pose[1])];
    g.lineWidth = 3; g.strokeStyle = "#12151a";
    g.beginPath(); g.moveTo(px - 8, py); g.lineTo(px + 8, py); g.moveTo(px, py - 8); g.lineTo(px, py + 8); g.stroke();
    g.lineWidth = 1.5; g.strokeStyle = "#ffd400";
    g.beginPath(); g.moveTo(px - 8, py); g.lineTo(px + 8, py); g.moveTo(px, py - 8); g.lineTo(px, py + 8); g.stroke();
    this.drawLegend(vmax);
  }

  /** Colour scale top: a "nice" value just above the data maximum (never above the option's ceiling). */
  private scaleMax(): number {
    const ceil = Math.max(this.opt.vmax(), 1e-9);
    if (!this.values) return ceil;
    let mx = 0;
    for (const v of this.values) mx = Math.max(mx, v);
    for (const n of [0.05, 0.1, 0.25, 0.5, 1, 1.5, 2, 3, 4]) if (n >= mx - 1e-9 && n <= ceil) return n;
    return ceil;
  }

  private drawLegend(vmax: number) {
    const r = this.bar.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio, 2);
    this.bar.width = Math.round(r.width * dpr);
    this.bar.height = Math.round(r.height * dpr);
    const g = this.bar.getContext("2d")!;
    for (let x = 0; x < this.bar.width; x++) {
      g.fillStyle = rampColor(x / (this.bar.width - 1));
      g.fillRect(x, 0, 1, this.bar.height);
    }
    (this.bar.parentElement!.querySelector(".hm-lo") as HTMLElement).textContent = this.opt.format(0);
    (this.bar.parentElement!.querySelector(".hm-hi") as HTMLElement).textContent = this.opt.format(vmax);
  }
}
