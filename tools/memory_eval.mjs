// Ověření paměti příjmů proti exportu z NightDX: buď konsolidovaný soubor ze skillu
// nightdx-export (nightdx-radar-*.json), nebo rozbalený zip (složky YYYY-MM-DD/*.json).
// Pro každou noc (mission) se paměť naplní JEN ostatními nocemi a skóre se porovná s tím,
// co ta noc skutečně slyšela - paměť tedy nikdy nevidí vlastní odpověď. Metrika: ROC AUC
// (řadí skóre slyšené nad neslyšené?) a kolik z 30 nejvýš skórovaných nahrávek hrálo.
// Běží nad SKUTEČNÝM kódem z index.html (tools/engine.mjs), žádná kopie vzorce.
//
//   node tools/memory_eval.mjs <soubor.json | složka s rozbaleným zipem> [--sfi 123] [--kp 2]
//        [--az 45] [--override '{"memory":{"amp":30}}']
//
// QTH se bere z nahrávek (rx_lat/rx_lon), přijímač Airspy + YouLoop, váha směrovosti 0
// (smyčka je skoro všesměrová). Rozvrh = aktuální schedule.json, export tedy musí být
// ze stejné vysílací sezóny.
import fs from 'fs';
import path from 'path';
import { loadEngine, loadDb, activeAt, parseOverrideArg } from './engine.mjs';

const argv = process.argv.slice(2);
const src = argv.find(a => !a.startsWith('--') && !a.startsWith('{') && fs.existsSync(a));
if (!src) { console.error('Použití: node tools/memory_eval.mjs <nightdx-radar-*.json | složka s rozbaleným exportem NightDX>'); process.exit(1); }
const num = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? +argv[i + 1] : d; };

const rows = [];
if (fs.statSync(src).isFile()) {
  const j = JSON.parse(fs.readFileSync(src, 'utf8'));
  for (const r of j.rows || []) rows.push({ rx_lat: j.rx?.lat, rx_lon: j.rx?.lon, ...r });
}
const dir = src;
for (const sub of fs.statSync(src).isDirectory() ? fs.readdirSync(dir) : []) {
  const p = path.join(dir, sub);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(sub) || !fs.statSync(p).isDirectory()) continue;
  for (const f of fs.readdirSync(p)) if (f.endsWith('.json')) rows.push(JSON.parse(fs.readFileSync(path.join(p, f), 'utf8')));
}
const A = loadEngine(undefined, parseOverrideArg(argv));
A.SPACE_WX.sfi = num('--sfi', 123); A.SPACE_WX.kp = num('--kp', 2);
const db = loadDb();
const obs = rows.map(r => ({ r, o: A.obsFromNightdx(r) })).filter(x => x.o && x.r.mission);
const nights = [...new Set(obs.map(x => x.r.mission))].sort();
if (nights.length < 2) { console.error('Potřebuji aspoň dvě noci (mission).'); process.exit(1); }
const qth = { myLat: obs[0].r.rx_lat, myLon: obs[0].r.rx_lon, alt: 250, balconyAz: num('--az', 180), rx: 'airspy', ant: 'youloop' };

const out = [];
for (const night of nights) {
  A.setHeardObs(obs.filter(x => x.r.mission !== night).map(x => x.o));
  for (const { r, o } of obs.filter(x => x.r.mission === night)) {
    const utc = new Date(r.utc_start);
    const best = on => {
      A.setHeardOn(on);
      const { env, active } = activeAt(A, db, utc, qth);
      env.weights = { ...A.WEIGHTS, balcony: 0 };
      let b = null;
      for (const st of active) if (st.freq === o[0]) { const s = A.scoreStation(st, env, active); if (!b || s.score > b.score) b = s; }
      return b;
    };
    const base = best(false), mem = best(true);
    if (base) out.push({ night, heard: o[2] > 0 ? 1 : 0, base: base.score, mem: mem.score, adj: mem.parts.mem });
  }
}
const auc = (xs, k) => { const p = xs.filter(x => x.heard), n = xs.filter(x => !x.heard); if (!p.length || !n.length) return NaN;
  let c = 0; for (const a of p) for (const b of n) c += a[k] > b[k] ? 1 : a[k] === b[k] ? 0.5 : 0; return c / p.length / n.length; };
const top = (xs, k, n) => [...xs].sort((a, b) => b[k] - a[k]).slice(0, n).filter(x => x.heard).length;
const line = (name, xs) => console.log(name.padEnd(18), `n=${String(xs.length).padStart(3)} slyšeno ${String(xs.filter(x => x.heard).length).padStart(3)}`,
  `| AUC bez paměti ${auc(xs, 'base').toFixed(3)} → s pamětí ${auc(xs, 'mem').toFixed(3)}`,
  `| TOP30 ${top(xs, 'base', 30)} → ${top(xs, 'mem', 30)}`);
console.log(`Nahrávek ${rows.length}, použitelných KV pozorování ${obs.length}, v rozvrhu ${out.length}. Paměť vždy jen z ostatních nocí.`);
line('všechny noci', out);
for (const n of nights) line(n, out.filter(x => x.night === n));
const up = out.filter(x => x.adj > 0), down = out.filter(x => x.adj < 0);
console.log(`Paměť přidala body u ${up.length} nahrávek (z nich slyšeno ${up.filter(x => x.heard).length}), ubrala u ${down.length} (z nich slyšeno ${down.filter(x => x.heard).length}), beze změny ${out.length - up.length - down.length}.`);
