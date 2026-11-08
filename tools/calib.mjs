// Kalibrace skóre proti balkonovému ground-truth (stations_calibration.txt).
// Metrika per snímek: per kmitočet max skóre; pozitiv = kvalita >= 1, negativ = ostatní
// aktivní; ROC AUC + TOP10 (kolik z 10 nejvýš skórovaných bylo slyšet).
// Akceptační pravidlo: žádný snímek nezhorší TOP10, AUC neklesne o víc než 0,003.
//
//   node tools/calib.mjs                 metriky aktuálního kódu
//   node tools/calib.mjs --top           + TOP10 seznam (✓kvalita / ✗)
//   node tools/calib.mjs --override '{"muf":{"seasonNight":0}}'   s přepsanými konstantami
//   node tools/calib.mjs --diff '{"skip":{"nearPenaltyMax":30}}'  per kmitočet: aktuální → override
import { loadEngine, loadSnapshots, loadDb, activeAt, parseOverrideArg, QTH_CALIB, WX_CALIB } from './engine.mjs';

const argv = process.argv.slice(2);
const db = loadDb();
const snaps = loadSnapshots();

function run(override = {}) {
  const A = loadEngine(undefined, override);
  A.SPACE_WX.sfi = WX_CALIB.sfi; A.SPACE_WX.kp = WX_CALIB.kp;
  return snaps.map(s => {
    const { env, active } = activeAt(A, db, s.utc, QTH_CALIB);
    const scored = active.map(st => ({ st, r: A.scoreStation(st, env, active) }));
    const best = new Map();
    for (const x of scored) if (!best.has(x.st.freq) || x.r.score > best.get(x.st.freq).r.score) best.set(x.st.freq, x);
    const per = [...best.values()].map(x => ({ f: x.st.freq, s: x.r.score, q: s.gt.get(x.st.freq) ?? 0, st: x.st, r: x.r }));
    const pos = per.filter(r => r.q >= 1), neg = per.filter(r => r.q === 0);
    let c = 0; for (const a of pos) for (const b of neg) c += a.s > b.s ? 1 : a.s === b.s ? 0.5 : 0;
    per.sort((a, b) => b.s - a.s || a.f - b.f);
    const missing = [...s.gt.keys()].filter(f => !best.has(f));
    return { label: s.label, utc: s.utc, active: active.length, n: per.length, pos: pos.length,
      auc: c / (pos.length * neg.length), top10: per.slice(0, 10).filter(r => r.q >= 1).length,
      top10List: per.slice(0, 10).map(r => `${r.f}${r.q ? '✓' + r.q : '✗'}:${r.s}`).join(' '), per, missing };
  });
}

function print(name, res) {
  console.log(name.padEnd(10), res.map(x => `${x.label.slice(5)} AUC ${x.auc.toFixed(3)} TOP10 ${x.top10}/10 (n=${x.n}, slyšeno ${x.pos})`).join(' | '));
  if (argv.includes('--top')) for (const x of res) console.log('   ', x.label, x.top10List,
    x.missing.length ? `  [v rozvrhu neaktivní: ${x.missing.join(', ')}]` : '');
}

const base = run();
print('aktuální', base);
const override = parseOverrideArg(argv);
if (Object.keys(override).length) print('override', run(override));

const di = argv.indexOf('--diff');
if (di >= 0) {
  const other = run(JSON.parse(argv[di + 1]));
  for (let i = 0; i < base.length; i++) {
    const mb = new Map(other[i].per.map(r => [r.f, r]));
    console.log(`\n== ${base[i].label}: aktuální → override (jen změněné)`);
    for (const r of base[i].per) {
      const b = mb.get(r.f);
      if (!b) { console.log(`  ${r.f} q${r.q} ${r.s} → (zmizela)`); continue; }
      if (b.s !== r.s || b.st.station !== r.st.station)
        console.log(`  ${String(r.f).padStart(5)} q${r.q} ${String(r.s).padStart(2)} → ${String(b.s).padStart(2)}  ${r.st.station}` +
          (b.st.station !== r.st.station ? ` ⇒ ${b.st.station}` : '') + `  qrm ${r.r.parts.qrm}→${b.r.parts.qrm}`);
    }
    for (const b of other[i].per) if (!base[i].per.some(r => r.f === b.f)) console.log(`  ${b.f} q${b.q} (nová) ${b.s} ${b.st.station}`);
  }
}
