// Kontrola propagačního a skip členu proti slyšeným stanicím z logů (tools/logs_heard.csv, lokální, mimo git):
// pro každý úlovek spočítá MUF trasy a oba členy aktuálního kódu a s přepsanými konstantami.
// Jen pozitiva (co šlo) - hlídá, že změna modelu ionosféry nezabije prokazatelné úlovky
// v jiném ročním období než kalibrační data (ta jsou jen z listopadu). Rozvrh pro ty dny
// není, proto jen tyto dva členy. Bez --override vypíše úlovky, které model sám sráží.
//
//   node tools/heard_check.mjs [--override '{"iono":{"seasonSummer":1}}'] [--sfi 125] [--all]
import fs from 'fs';
import { loadEngine, loadLocal, parseOverrideArg, REPO } from './engine.mjs';

const argv = process.argv.slice(2);
const si = argv.indexOf('--sfi');
const SFI = si >= 0 ? +argv[si + 1] : 125;
// vysílače = veřejná data (tx_sites.json); místa příjmu = osobní (local.json, mimo git)
const sites = { tx: JSON.parse(fs.readFileSync(`${REPO}/tools/tx_sites.json`, 'utf8')).tx, rx: loadLocal().rx || {} };
const rows = fs.readFileSync(`${REPO}/tools/logs_heard.csv`, 'utf8').split('\n')
  .filter(l => l && !l.startsWith('#') && !l.startsWith('utc,')).map(l => l.split(','));

const override = parseOverrideArg(argv), hasAlt = Object.keys(override).length > 0;
const CUR = loadEngine(), ALT = loadEngine(undefined, override);
const term = (A, d, la, lo, sl, so, f) => {
  const dist = A.calcGeodesic(la, lo, sl, so).dist;
  const p = A.ionoPath(f, la, lo, sl, so, dist, d, SFI, 2);
  return { ...p, dist, sum: Math.round(p.prop * A.SCORING.weightsDefault.prop + p.skip * A.SCORING.weightsDefault.skip) };
};
let worse = 0, better = 0, hard = 0;
console.log('UTC               kHz  vysílač      QTH          km  MUF cur/alt  prop+skip cur→alt');
for (const [t, rx, f, site, q] of rows) {
  if (!sites.rx[rx] || !sites.tx[site]) { console.log('neznámý klíč', rx, site); continue; }
  const d = new Date(t), [la, lo] = sites.rx[rx], [sl, so] = sites.tx[site];
  const c = term(CUR, d, la, lo, sl, so, +f), a = term(ALT, d, la, lo, sl, so, +f);
  const mark = a.sum < c.sum ? '◄ alt horší' : a.sum > c.sum ? '▲ alt lepší' : '';
  if (a.sum < c.sum) worse++; else if (a.sum > c.sum) better++;
  if (c.sum <= -25) hard++;
  if (argv.includes('--all') || (hasAlt ? mark : c.sum <= -25))
    console.log(`${t.slice(0, 16)} ${String(f).padStart(5)}  ${site.padEnd(11)} ${rx.padEnd(8)} ${String(c.dist).padStart(6)}  ${c.muf.toFixed(0).padStart(3)}/${a.muf.toFixed(0).padStart(3)}      ${String(c.sum).padStart(4)}→${String(a.sum).padStart(4)} ${mark}  S${q}`);
}
console.log(`\nSFI ${SFI}: slyšených ${rows.length}; model sráží o 25 b. a víc ${hard} z nich` +
  (hasAlt ? `; override horší u ${worse}, lepší u ${better}` : ''));
