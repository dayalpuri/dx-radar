// Sdílený loader pro kalibrační skripty: spustí SKUTEČNÝ skórovací kód z index.html
// (blacklist → konec scoreStation) + scoring.js v izolovaném kontextu, volitelně
// s přepsanými konstantami. Žádná kopie vzorce - co platí v appce, platí tady.
import fs from 'fs';
import path from 'path';
import vm from 'vm';
import { fileURLToPath } from 'url';

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function deepMerge(a, b) {
  const o = JSON.parse(JSON.stringify(a));
  for (const [k, v] of Object.entries(b || {}))
    o[k] = v && typeof v === 'object' && !Array.isArray(v) ? deepMerge(o[k] || {}, v) : v;
  return o;
}

// override: objekt stejného tvaru jako window.SCORING (jen měněné klíče)
export function loadEngine(repo = REPO, override = {}) {
  const html = fs.readFileSync(`${repo}/index.html`, 'utf8').split('\n');
  const start = html.findIndex(l => l.startsWith('// ── Blacklist'));
  const end = html.findIndex(l => l.startsWith('function evaluateStations'));
  if (start < 0 || end < 0) throw new Error('index.html: výřez skórovacího kódu nenalezen');
  const pre = html.filter(l => /^(const SCORE_HI|function antBand)/.test(l)).join('\n');
  const engine = pre + '\n' + html.slice(start, end).join('\n');
  const ctx = { window: {}, Math, Date, console, LANG: 'cs', tr: k => k };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(`${repo}/scoring.js`, 'utf8'), ctx);
  ctx.SCORING = deepMerge(ctx.window.SCORING, override);
  vm.runInContext(engine + `;globalThis.API = { scoreStation, dedupActive, passesDay, stationKey, isTimeActive,
    calcGeodesic, mufEstimate, pathDaylight, propagationAdjust, solarElevation, solarDeclination,
    SPACE_WX, WEIGHTS, SCORING, setBlacklist: b => { BLACKLIST = b; BLACKLIST_ON = true; },
    isBlacklisted };`, ctx);
  return ctx.API;
}

export function parseOverrideArg(argv) {
  const i = argv.indexOf('--override');
  return i >= 0 ? JSON.parse(argv[i + 1]) : {};
}

// stations_calibration.txt: blok "YYYY-MM-DD,H:MM" + řádky "kHz,kvalita" (0 = neslyšeno).
// Časy: ráno/večer = CET (UTC+1); polední 12:10 = UTC (jen tak sedí s rozvrhem).
export function loadSnapshots(repo = REPO, file = 'stations_calibration.txt') {
  const FIX = { 1535: 15350 }; // překlep (1535 kHz = SV, mimo rozsah)
  const snaps = [];
  for (const block of fs.readFileSync(`${repo}/${file}`, 'utf8').trim().split(/\n\s*\n/)) {
    const lines = block.trim().split('\n');
    const [d, t] = lines[0].split(',');
    const [hh, mm] = t.split(':').map(Number);
    let utc = new Date(Date.UTC(...d.split('-').map((v, i) => i === 1 ? v - 1 : +v), hh - 1, mm));
    if (d === '2026-11-07' && t === '12:10') utc = new Date(Date.UTC(2026, 10, 7, 12, 10));
    const gt = new Map();
    for (const l of lines.slice(1)) { let [f, q] = l.split(',').map(Number); f = FIX[f] || f; gt.set(f, q); }
    snaps.push({ label: `${d} ${t}`, utc, gt });
  }
  return snaps;
}

export const QTH_CALIB = { myLat: 50.1041, myLon: 14.5499, alt: 305, balconyAz: 50, rx: 'pl330', ant: 'whip' };
export const WX_CALIB = { sfi: 125, kp: 3 };

export function loadDb(repo = REPO) {
  return JSON.parse(fs.readFileSync(`${repo}/schedule.json`, 'utf8'));
}

// Aktivní + deduplikované záznamy pro daný okamžik (jako evaluateStations), bez blacklistu
export function activeAt(A, db, utc, qth) {
  const utcMin = utc.getUTCHours() * 60 + utc.getUTCMinutes();
  const day = String(((utc.getUTCDay() + 6) % 7) + 1);
  const env = { ...qth, weights: A.WEIGHTS, now: utc };
  const active = A.dedupActive(db.filter(st => A.isTimeActive(st.start, st.end, utcMin) && A.passesDay(st, day)), env);
  return { env, active, utcMin, day };
}
