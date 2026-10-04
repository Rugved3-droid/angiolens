// The atlas toolbar (v1.0, D57): ONE row. [Tour] | < scene stepper > | 2-4 essential controls for this scene | [More].
// Controls are declared per scene (data, not DOM); render() rebuilds them, so the toolbar can never drift from the state.
// Everything secondary lives in the "More" drawer. No numbers anywhere (view NAMES only).

export type Opt = { v: string; label: string };
export type Ctl =
  | { kind: "seg"; id: string; options: Opt[]; value: string; onChange: (v: string) => void; title?: string }
  | { kind: "menu"; id: string; options: Opt[]; value: string; onChange: (v: string) => void; title: string }
  | { kind: "button"; id: string; label: string; onClick: () => void; accent?: boolean; disabled?: boolean; title?: string }
  | { kind: "toggle"; id: string; label: string; value: boolean; onChange: (v: boolean) => void; title?: string };
export type Section = { title: string; ctls: Ctl[] };

export const SCENES = ["Heart", "In the chest", "Cath lab", "X-ray", "Catheter", "Cross-section"];

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

export class Toolbar {
  private openMenu: HTMLElement | null = null;
  onScene: (n: number) => void = () => {};
  onPlay: () => void = () => {};

  constructor(private readonly bar: HTMLElement, private readonly drawer: HTMLElement) {
    document.addEventListener("pointerdown", (e) => {
      if (this.openMenu && !this.openMenu.contains(e.target as Node)) this.closeMenu();
      const more = this.bar.querySelector("#bMore");
      if (this.drawer.classList.contains("open") && !this.drawer.contains(e.target as Node) && e.target !== more
        && !(more && more.contains(e.target as Node))) this.toggleDrawer(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { this.closeMenu(); this.toggleDrawer(false); }
    });
  }

  toggleDrawer(open?: boolean) {
    const on = open ?? !this.drawer.classList.contains("open");
    this.drawer.classList.toggle("open", on);
    this.bar.querySelector("#bMore")?.classList.toggle("on", on);
  }

  private closeMenu() { this.openMenu?.remove(); this.openMenu = null; }

  private ctl(c: Ctl, inDrawer: boolean): HTMLElement {
    if (c.kind === "button") {
      const b = el("button", `btn${c.accent ? " accent" : ""}`, c.label);
      b.id = c.id;
      b.disabled = !!c.disabled;
      if (c.title) b.title = c.title;
      b.onclick = () => { c.onClick(); };
      return b;
    }
    if (c.kind === "toggle") {
      const b = el("button", `btn toggle${c.value ? " on" : ""}`, c.label);
      b.id = c.id;
      b.setAttribute("aria-pressed", String(c.value));
      if (c.title) b.title = c.title;
      b.onclick = () => c.onChange(!c.value);
      return b;
    }
    if (c.kind === "seg" || inDrawer) {
      const g = el("div", "seg");
      g.id = c.id;
      g.setAttribute("role", "group");
      if (c.title) g.title = c.title;
      for (const o of c.options) {
        const b = el("button", c.value === o.v ? "on" : "", o.label);
        b.dataset.v = o.v;
        b.onclick = () => c.onChange(o.v);
        g.appendChild(b);
      }
      return g;
    }
    // menu: a compact button showing the current choice, opening a small list under it
    const cur = c.options.find((o) => o.v === c.value)?.label ?? c.title;
    const b = el("button", "btn menu");
    b.id = c.id;
    b.title = c.title;
    b.innerHTML = `<span class="mt">${c.title}</span> <span class="mv"></span> <span class="caret">▾</span>`;
    (b.querySelector(".mv") as HTMLElement).textContent = cur;
    b.onclick = (e) => {
      e.stopPropagation();
      if (this.openMenu?.dataset.for === c.id) { this.closeMenu(); return; }
      this.closeMenu();
      const list = el("div", "menulist panel");
      list.dataset.for = c.id;
      for (const o of c.options) {
        const it = el("button", c.value === o.v ? "on" : "", o.label);
        it.onclick = () => { this.closeMenu(); c.onChange(o.v); };
        list.appendChild(it);
      }
      document.body.appendChild(list);
      const r = b.getBoundingClientRect();
      list.style.left = `${Math.min(r.left, innerWidth - 200)}px`;
      list.style.top = `${r.bottom + 6}px`;
      this.openMenu = list;
    };
    return b;
  }

  render(scene: number, essentials: Ctl[], more: Section[], opts: { tour: boolean; stepDisabled?: boolean }) {
    this.closeMenu();
    const bar = this.bar;
    bar.innerHTML = "";
    const play = el("button", `btn accent${opts.tour ? " on" : ""}`, opts.tour ? "Tour playing" : "▶ Tour");
    play.id = "bPlay";
    play.title = "Play the guided tour";
    play.onclick = () => this.onPlay();
    bar.appendChild(play);
    bar.appendChild(el("span", "sep"));
    const back = el("button", "btn icon", "‹");
    back.id = "bBack"; back.title = "Previous scene"; back.disabled = scene <= 1 || !!opts.stepDisabled;
    back.onclick = () => this.onScene(scene - 1);
    const next = el("button", "btn icon", "›");
    next.id = "bNext"; next.title = "Next scene"; next.disabled = scene >= SCENES.length || !!opts.stepDisabled;
    next.onclick = () => this.onScene(scene + 1);
    const steps = el("div", "steps");
    steps.id = "steps";
    SCENES.forEach((name, i) => {
      const s = el("button", `step${scene === i + 1 ? " on" : ""}${i + 1 < scene ? " done" : ""}`, name);
      s.dataset.s = String(i + 1);
      s.disabled = !!opts.stepDisabled;
      s.onclick = () => this.onScene(i + 1);
      steps.appendChild(s);
    });
    bar.append(back, steps, next);
    if (essentials.length) {
      bar.appendChild(el("span", "sep"));
      const ess = el("div", "ess");
      ess.id = "essentials";
      for (const c of essentials) ess.appendChild(this.ctl(c, false));
      bar.appendChild(ess);
    }
    bar.appendChild(el("span", "sep push"));
    const moreBtn = el("button", `btn${this.drawer.classList.contains("open") ? " on" : ""}`, "More ▾");
    moreBtn.id = "bMore";
    moreBtn.onclick = () => this.toggleDrawer();
    bar.appendChild(moreBtn);
    // drawer
    this.drawer.innerHTML = "";
    for (const sec of more) {
      if (!sec.ctls.length) continue;
      const box = el("div", "dsec");
      box.appendChild(el("div", "dtitle", sec.title));
      for (const c of sec.ctls) box.appendChild(this.ctl(c, true));
      this.drawer.appendChild(box);
    }
  }
}
