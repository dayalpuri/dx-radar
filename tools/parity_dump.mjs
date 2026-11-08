// Výpis skóre z PWA kódu pro kalibrační snímky (JSON na stdout) - vstup pro tools/parity.py
import { loadEngine, loadSnapshots, loadDb, activeAt, QTH_CALIB, WX_CALIB } from './engine.mjs';

const A = loadEngine();
A.SPACE_WX.sfi = WX_CALIB.sfi; A.SPACE_WX.kp = WX_CALIB.kp;
const db = loadDb();
const out = {};
for (const s of loadSnapshots()) {
  const { env, active } = activeAt(A, db, s.utc, QTH_CALIB);
  out[s.utc.toISOString()] = active.map(st => [st.freq, st.station, st.aka || null, A.scoreStation(st, env, active).score]);
}
process.stdout.write(JSON.stringify(out));
