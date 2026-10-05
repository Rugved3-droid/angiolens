// The atlas's study bar (v1.1; mounted only with atlas.html?study=<code>): the training clock, what to do next, and
// "Finish training", which records the training time, whether the tour was watched to the end and the Predict practice
// (new answers in the atlas Predict history since the training began), then returns to study.html for the post-test.
import { loadSessions, PREDICT_HISTORY_KEY, saveSession } from "./studyStore";

export function mountStudyBar(code: string) {
  const s = loadSessions()[code];
  if (!s) return;
  const bar = document.createElement("div");
  bar.id = "studyBar";
  bar.innerHTML = `
    <span class="sb-tag">Study · training</span>
    <span class="sb-clock" id="sbClock">0:00</span>
    <span class="sb-hint" id="sbHint">Press ▶ Tour (top left) and watch it to the end.</span>
    <button id="sbFinish">Finish training →</button>`;
  const css = document.createElement("style");
  css.textContent = `
    #studyBar { position: fixed; left: 50%; top: 66px; transform: translateX(-50%); z-index: 8; display: flex; align-items: center;
      gap: 12px; padding: 7px 8px 7px 14px; background: #0f141c; border: 1px solid rgba(242,193,78,0.45); border-radius: 12px;
      font: 13.5px "Segoe UI", system-ui, sans-serif; color: #e9edf2; box-shadow: 0 6px 24px rgba(0,0,0,0.4); }
    #studyBar .sb-tag { color: #f2c14e; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; font-size: 11.5px; }
    #studyBar .sb-clock { font-variant-numeric: tabular-nums; color: #c3cbd5; min-width: 38px; }
    #studyBar .sb-hint { color: #c3cbd5; }
    #studyBar button { font: inherit; color: #0d1219; background: #f2c14e; border: 0; border-radius: 8px; padding: 6px 12px; cursor: pointer;
      font-weight: 600; }`;   // top centre, under the toolbar: clear of the tour bar, the caption and the Predict panel
  document.head.appendChild(css);
  document.body.appendChild(bar);
  const t0 = s.training.started ? Date.parse(s.training.started) : Date.now();
  let tourDone = s.training.tourCompleted;
  const hint = () => {
    const min = (Date.now() - t0) / 60000;
    document.getElementById("sbHint")!.textContent = !tourDone
      ? "Press ▶ Tour (top left) and watch it to the end."
      : min < 8 ? "Now practise: X-ray → Predict. About 10 minutes in all." : "Good. Finish when you are ready.";
  };
  const tick = () => {
    const sec = Math.floor((Date.now() - t0) / 1000);
    document.getElementById("sbClock")!.textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    hint();
  };
  tick();
  setInterval(tick, 1000);
  window.addEventListener("cpt:tour-complete", () => {
    tourDone = true;
    const cur = loadSessions()[code];
    if (cur) { cur.training.tourCompleted = true; saveSession(cur); }
    hint();
  });
  document.getElementById("sbFinish")!.onclick = () => {
    const cur = loadSessions()[code];
    if (!cur) return;
    let hist: { chosen: string }[] = [];
    try { hist = JSON.parse(localStorage.getItem(PREDICT_HISTORY_KEY) ?? "[]"); } catch { hist = []; }
    const mine = hist.slice(cur.training.histStart ?? hist.length);
    cur.training = { ...cur.training, ended: new Date().toISOString(), tourCompleted: tourDone, practiceAnswers: mine.length,
      practiceCorrect: mine.filter((h) => h.chosen === "correct").length };
    saveSession(cur);
    location.href = `${import.meta.env.BASE_URL}study.html?code=${encodeURIComponent(code)}`;
  };
}
