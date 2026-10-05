// Study sessions in this browser's localStorage (anonymous codes only). Shared by study.html and the atlas's study bar.
import type { Session } from "./studyCore";

const KEY = "cpt.study.sessions.v1";
const CUR = "cpt.study.current";
/** The atlas Predict history (PredictMode, caseId "atlas"): the training practice is counted from it. */
export const PREDICT_HISTORY_KEY = "cpt.predict.history.atlas";

export function loadSessions(): Record<string, Session> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "{}"); } catch { return {}; }
}
export function saveSession(s: Session) {
  const all = loadSessions();
  all[s.code] = s;
  localStorage.setItem(KEY, JSON.stringify(all));
}
export const currentCode = (): string | null => localStorage.getItem(CUR);
export function setCurrent(code: string | null) {
  if (code) localStorage.setItem(CUR, code); else localStorage.removeItem(CUR);
}
