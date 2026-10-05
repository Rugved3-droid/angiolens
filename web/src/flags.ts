// v1.1 feature flags. New features ship OFF: the v1.0 scenes are unchanged unless a flag is on.
//   atlas.html?ff=shadow          one flag
//   atlas.html?ff=shadow,peel     several
//   atlas.html?ff=all             every v1.1 feature
// A flag given in the URL is remembered for this browser (localStorage "cpt.ff"); ?ff=none clears them.
export type Flag = "shadow" | "peel";
const ALL: Flag[] = ["shadow", "peel"];
const KEY = "cpt.ff";

function read(): Set<Flag> {
  const q = new URLSearchParams(location.search).get("ff");
  let list: string[];
  if (q !== null) {
    list = q === "all" ? ALL : q === "none" ? [] : q.split(",").map((s) => s.trim());
    try { localStorage.setItem(KEY, list.join(",")); } catch { /* private mode: URL only */ }
  } else {
    try { list = (localStorage.getItem(KEY) ?? "").split(",").filter(Boolean); } catch { list = []; }
  }
  return new Set(list.filter((f): f is Flag => (ALL as string[]).includes(f)));
}
const on = read();
export const flag = (f: Flag) => on.has(f);
