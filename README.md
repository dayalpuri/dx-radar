# DX Radar Pro — Kontextový SWL Engine

Balkónový DX engine pro krátkovlnný SWL DXing: počítá jako zkušený DXer — sférická
trigonometrie (ortodroma, azimut), kardioidní maska balkónu, bonus nadmořské výšky
(nízký take-off angle), detekce rušení ±5 kHz včetně „neviditelné Číny", ionosférické
podmínky dle NOAA, korekce směrovosti vysílače dle azimutu antény (HFCC) a tipy pro
Tecsun PL-330 na míru zvolené anténě.

Postaveno na konverzaci s Gemini (zima B26).

## Soubory

| Soubor                | Role                                                        |
|-----------------------|-------------------------------------------------------------|
| `index.html`          | PWA „DX Radar Pro 2.0" — engine + UI + polární radar |
| `eibi_sync.py`         | Data Harvester + CLI radar (HFCC + EiBi, generování `eibi.json`, terminálový výstup `--now`) |
| `eibi.json`           | Vygenerovaná databáze vysílacích oken (commituje se do repa = sync do mobilu) |
| `manifest.webmanifest`| PWA manifest (ikona, „Přidat na plochu")                    |
| `sw.js`               | Service worker — po první návštěvě jede i offline           |
| `icon-192/512.png`    | Ikony aplikace                                              |

## Zdroje dat (čím víc seznamů, tím líp)

| Seznam | Co dává | Kde |
|--------|---------|-----|
| **HFCC** | zimní/letní rozvrh dle skutečné sezóny, **přesné GPS vysílačů** (site.txt), reálné výkony kW, **azimuty antén** (korekce směrovosti!), dny vysílání, jména vysílatelů | `hfcc.org/data/{a,b}26/` |
| **AOKI** (Bi Newsletter, Nagoya DX Circle) | nejlepší jména stanic, přesné souřadnice (DDMMSS), výkony, azimuty, dny; distribuce zip se Shift-JIS | `mediacat.ne.jp/binews/us/xz/xz*.zip` |
| **EiBi** | největší množství stanic (~6 400), často dřív než HFCC; země jen přibližně (ITU → GPS) | `eibispace.de/dx/sked-*.csv` |

Sloučení v pořadí HFCC > AOKI > EiBi; zástaralá sezóna se míchání s čerstvou
brání (EiBi A26 se přeskočí, existuje-li B26 z HFCC/AOKI). CLI: `--source all|hfcc|aoki|eibi`.

## SWL deník a ověření stanice přes web

- **📝 Log** v každé kartě: zapsání SINPO (5 číslic) + poznámky do deníku (localStorage).
- **📖 Log** v horní liště: celý deník, mazání záznamů, **📋 Export MD**
  (Markdown řádky pro Obsidian — číslované jako v původním návrhu).
- **🎧 Stream** v každé kartě: ověření ID přijaté stanice přes její webové
  streamy (databáze radio-browser.info, jen https streamy kvůli mixed-content).
  Přesné shody ✅, volné shody ❔ (srovnejte sluchem) + Google fallback na web stanice.

## Použití na notebooku (CLI + lokální PWA)

```bash
# 1) Stáhnout aktuální rozvrh EiBi a vygenerovat eibi.json (stačí 2x ročně, změna sezóny A/B)
python3 eibi_sync.py --sync

# 2) CLI radar pro terminál — zadej svoje QTH (šířka, délka, nadm. výška, azimut balkónu)
python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --alt 300 --az 180
python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --rx loop --show-china

# 3) PWA lokálně (povolí GPS/kompas na localhostu)
python3 -m http.server 8080
# → http://localhost:8080/
```

## Použití na mobilu (GitHub Pages — doporučeno)

`file://` blokuje GPS, kompas i schránku. Proto se PWA hostuje přes GitHub Pages,
kde běží na `https://` a vše funguje:

1. Pushni tento repozitář na GitHub (viz níže).
2. Na GitHubu: **Settings → Pages → Deploy from a branch → `main` / root**.
3. Na mobilu otevři `https://<uzivatel>.github.io/dx-radar/`
   a v menu Chrome zvol **„Přidat na plochu"** — vznikne plnohodnotná aplikace.
4. Po první návštěvě funguje i **offline** (service worker) — na balkoně
   v letadlovém režimu stačí GPS presety a vestavěná data.

## Aktualizace dat rozvrhů (2 cesty)

**A) Přímo v PWA (bez Pythonu):** tlačítko **⬇️ Stáhnout rozvrh** stáhne aktuální
sezónu přímo v prohlížeči — nejprve HFCC (`B26all00.TXT` + `site.txt` +
`broadcas.txt`, tedy přesné souřadnice, výkony, azimuty a dny), po pádu HFCC
EiBi CSV. Oba servery neposílají CORS hlavičky, proto se používá fallback přes
Jina reader. Data se uloží do `localStorage` — přežijí restart i letadlový
režim. Případný nezdar zobrazí instrukce k ruční cestě přes 📂 import
(PWA umí `.csv` i `.json`).

**B) Pres notebook (klasicky):** `python3 eibi_sync.py --sync` sloučí HFCC + EiBi
a vygeneruje `eibi.json`, který se commitne do repa — PWA ho použije jako
výchozí databázi, dokud si uživatel nestáhne vlastní.

Priorita zdrojů při startu: `localStorage` (naposledy synchronizovaná) →
`eibi.json` v repu → vestavěný vzorek.

## Sync devel → mobil (workflow)

Repositář je jediný zdroj pravdy. Po změně sezóny (konec října / konec března):

```bash
python3 eibi_sync.py --sync          # nové eibi.json
git add eibi.json && git commit -m "B26: aktualizace rozvrhu EiBi" && git push
# mobil si při příštím online otevření veme čerstvá data z Pages
```

Stejný vzor lze použít i pro další devel projekty (`gramo`, …): každý projekt
jako vlastní repozitář → `gh pages` → na mobilu přidáno na plochu.

## Fallback GPS na mobilu

- Žádné přednastavené polohy — QTH zadáš přes 📍 GPS nebo ručně a uloží se
  jen lokálně (localStorage v tomto prohlížeči / nainstalované PWA), nikdy do repa.
- Tlačítko 📍 GPS: přes `https://` (Pages) plná GPS + kompas; při `file://`
  nebo odmítnutí GPS zkusí přibližnou polohu z IP (±50 km).

## Bez závislostí

- `eibi_sync.py`: pouze standardní knihovna Pythonu 3.
- PWA: bez frameworků, bez buildu, jediný HTML soubor + manifest + SW.
