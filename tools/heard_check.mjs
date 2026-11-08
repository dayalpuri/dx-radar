// Kontrola MUF/propagačního členu proti slyšeným stanicím z logů (tools/logs_heard.csv):
// pro každý úlovek spočítá MUF a prop člen aktuálního kódu a s přepsanými konstantami.
// Jen pozitiva (co šlo) - hlídá, že změna MUF modelu nezabije prokazatelné úlovky v jiném
// ročním období než kalibrační snímky. Rozvrh pro ty dny není, proto jen tento člen.
//
//   node tools/heard_check.mjs --override '{"muf":{"seasonNight":0,"const":1}}' [--sfi 125] [--all]
import fs from 'fs';
import { loadEngine, parseOverrideArg, REPO } from './engine.mjs';

const argv = process.argv.slice(2);
const si = argv.indexOf('--sfi');
const SFI = si >= 0 ? +argv[si + 1] : 125;
const sites = JSON.parse(fs.readFileSync(`${REPO}/tools/sites.json`, 'utf8'));
const rows = fs.readFileSync(`${REPO}/tools/logs_heard.csv`, 'utf8').split('\n')
  .filter(l => l && !l.startsWith('#') && !l.startsWith('utc,')).map(l => l.split(','));

const CUR = loadEngine(), ALT = loadEngine(undefined, parseOverrideArg(argv));
const term = (A, d, la, lo, sl, so, f) => {
  const dl = A.pathDaylight(la, lo, sl, so, d), decl = A.solarDeclination(d);
  const brg = A.calcGeodesic(la, lo, sl, so).bearing;
  return { muf: A.mufEstimate(SFI, dl, decl), prop: A.propagationAdjust(f, brg, SFI, 2, dl, decl) };
};
let worse = 0, better = 0;
console.log('UTC               kHz  vysílač      QTH       el°   MUF cur/alt  prop cur→alt');
for (const [t, rx, f, site, q] of rows) {
  const d = new Date(t), [la, lo] = sites.rx[rx], [sl, so] = sites.tx[site];
  if (!sites.rx[rx] || !sites.tx[site]) { console.log('neznámý klíč', rx, site); continue; }
  const el = CUR.solarElevation((la + sl) / 2, (lo + so) / 2, d);
  const c = term(CUR, d, la, lo, sl, so, +f), a = term(ALT, d, la, lo, sl, so, +f);
  const mark = a.prop < c.prop ? '◄ alt horší' : a.prop > c.prop ? '▲ alt lepší' : '';
  if (a.prop < c.prop) worse++; else if (a.prop > c.prop) better++;
  if (mark || argv.includes('--all'))
    console.log(`${t.slice(0, 16)} ${String(f).padStart(5)}  ${site.padEnd(11)} ${rx.padEnd(8)} ${el.toFixed(0).padStart(4)}   ${String(c.muf).padStart(2)}/${String(a.muf).padStart(2)}       ${String(c.prop).padStart(3)}→${String(a.prop).padStart(3)} ${mark}  S${q}`);
}
console.log(`\nSFI ${SFI}: slyšených ${rows.length}; override horší u ${worse}, lepší u ${better} (prop člen před váhou)`);
