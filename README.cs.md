# DX Radar Pro — Kontextový SWL engine

*[English](README.md) · Česky*

**Co právě teď chytíš na krátkých vlnách — a co jsi to vlastně naladil?**
DX Radar je pomocník pro posluchače krátkovlnného rozhlasu (SWL). Vezme aktuální
seznam vysílání, tvoji polohu a čas a seřadí stanice podle toho, jak reálná je jejich
slyšitelnost. Pomůže to v obou směrech:

- **Plánování:** neztrácíš čas laděním stanic, které k tobě stejně nedoletí.
- **Identifikace:** naladil jsi něco a nevíš co — na té frekvenci vysílá víc stanic
  někde ve světě a skóre ti seřadí nejpravděpodobnějšího kandidáta pro tvoji polohu
  a čas. Ověření 🎧 streamem to pak může potvrdit sluchem.

Výsledek ukáže jako skóre i jako polární radar kolem tvé pozice.

Skóre počítá z věcí, které rozhodují o příjmu:

- **vzdálenost a směr** stanice (velkokružnicová geometrie) a kam máš volný výhled na oblohu,
- **denní doba a stav ionosféry** — přes den jdou vyšší pásma, večer nižší; data o kosmickém počasí (SFI/Kp) tahá z NOAA,
- **mrtvá zóna (skip)** — silná blízká stanice na vysokém pásmu může „přeletět" nad hlavou,
- **výkon a směrování vysílače** (kam míří jeho anténa),
- **rušení sousedních kanálů** a tvoje sestava **přijímač + anténa**.

Běží jako webová aplikace (PWA) — po první návštěvě i offline. Postaveno v konverzaci
s AI; data z veřejných rozvrhů (HFCC, AOKI, EiBi). Podrobnosti o přesnosti a licencích
najdeš níže a v [`legal.html`](legal.html).

## Soubory

| Soubor                | Role                                                        |
|-----------------------|-------------------------------------------------------------|
| `index.html`          | PWA „DX Radar Pro 2.0" — engine + UI + polární radar        |
| `eibi_sync.py`        | Stahovač dat (HFCC + AOKI + EiBi → generuje `schedule.json`)    |
| `schedule.json`       | Vygenerovaná databáze (HFCC + AOKI, přesné pozice vysílačů), commituje se do repa |
| `schedule_eibi.json`  | Volitelný EiBi doplněk (stanice mimo HFCC/AOKI, orientační pozice) |
| `manifest.webmanifest`| PWA manifest (ikona, „Přidat na plochu")                    |
| `sw.js`               | Service worker — po první návštěvě jede i offline           |
| `icon-192/512.png`    | Ikony aplikace                                              |
| `legal.html`          | Licence, atribuce zdrojů dat a zásady soukromí (EN/CZ)      |
| `LICENSE`             | MIT licence kódu (data vyňata — vlastní podmínky zdrojů)    |

## Zdroje dat (čím víc seznamů, tím líp)

| Seznam | Co dává | Kde |
|--------|---------|-----|
| **HFCC** | zimní/letní rozvrh dle sezóny, **přesné GPS vysílačů** (site.txt), reálné výkony kW, **azimuty antén** (korekce směrovosti!), dny vysílání, jména vysílatelů | `hfcc.org/data/{a,b}26/` |
| **AOKI** (Bi Newsletter for DXers, „AOKI list"; osobní newsletter správce webu, ne oficiální NDXC) | nejlepší jména stanic, přesné souřadnice (DDMMSS), výkony, azimuty, dny; distribuce zip se Shift-JIS | `mediacat.ne.jp/binews/us/xz/xz*.zip` |
| **EiBi** | největší množství stanic (~6 400), často dřív než HFCC; země jen přibližně (ITU → GPS) | `eibispace.de/dx/sked-*.csv` |

Slučuje se v pořadí HFCC > AOKI > EiBi; míchání zastaralé sezóny s čerstvou je
ošetřeno (EiBi A26 se přeskočí, existuje-li B26 z HFCC/AOKI).

## SWL deník a ověření stanice přes web

- **📝 Log** v každé kartě: zapsání SINPO (5 číslic) + poznámky do deníku (localStorage).
- **📖 Log** v horní liště: celý deník, mazání záznamů, **📋 Export MD** (Markdown pro Obsidian).
- **🎧 Stream** v každé kartě: ověření ID přijaté stanice přes její webové streamy
  (databáze radio-browser.info, jen https streamy kvůli mixed-content). Přesné shody ✅,
  volné shody ❔ (srovnej sluchem) + Google fallback na web stanice.

## Spuštění lokálně

```bash
# 1) Stáhnout aktuální rozvrh a vygenerovat schedule.json (stačí 2x ročně, změna sezóny A/B)
python3 eibi_sync.py --sync

# 2) Lokální server pro PWA (povolí GPS/kompas na localhostu)
python3 -m http.server 8080
# → http://localhost:8080/
```

## Spuštění na mobilu (GitHub Pages — doporučeno)

`file://` blokuje GPS, kompas i schránku. Proto se PWA hostuje přes GitHub Pages,
kde běží na `https://` a vše funguje:

1. Pushni tento repozitář na GitHub.
2. Na GitHubu: **Settings → Pages → Deploy from a branch → `main` / root**.
3. Na mobilu otevři `https://<uzivatel>.github.io/dx-radar/` a v menu Chrome zvol
   **„Přidat na plochu"** — vznikne plnohodnotná aplikace.
4. Po první návštěvě funguje i **offline** (service worker) — v letadlovém režimu
   stačí zadaná poloha a vestavěná data.

## Aktualizace dat rozvrhů

Data se obnovují **automaticky na GitHubu**: denní Actions cron
(`.github/workflows/sync-schedules.yml`) spustí `python3 eibi_sync.py --sync`, který
stáhne HFCC + AOKI + EiBi lokálně v Pythonu (bez 3rd-party proxy) a commitne
`schedule.json` (+ `schedule_eibi.json`), když se něco změnilo. Repo — a přes
network-first service worker i nainstalovaná PWA — je tak max ~den staré. Appka při
startu jen načte `schedule.json` z repa; žádné stahování v prohlížeči ani závislost
na CORS proxy.

Ruční obnova (např. lokálně) stejným příkazem:

```bash
python3 eibi_sync.py --sync
```

## Fallback GPS na mobilu

- Žádné přednastavené polohy — QTH zadáš přes 📍 GPS nebo ručně a uloží se jen lokálně
  (localStorage v tomto prohlížeči / nainstalované PWA), nikdy do repa.
- Tlačítko 📍 GPS: přes `https://` (Pages) plná GPS + kompas; při `file://` nebo
  odmítnutí GPS zkusí přibližnou polohu z IP (±50 km).

## Licence a právní informace

- **Kód** (index.html, eibi_sync.py, sw.js, manifest, ikony, dokumentace) je pod licencí
  **MIT** — viz [`LICENSE`](LICENSE).
- **Data rozvrhů** (schedule.json atd.) MIT nekryje — pocházejí z HFCC, AOKI a EiBi, každý
  pod vlastními podmínkami. Šíří se v dobré víře pro nekomerční použití.
- Kompletní atribuce zdrojů, podmínky užití, vyloučení odpovědnosti („as is", vytvořeno
  s pomocí AI) a zásady soukromí/GDPR jsou v [`legal.html`](legal.html) (dvojjazyčně
  EN/CZ, odkaz je i v patičce aplikace).

Zdroj dat | Licence / podmínky
----------|-------------------
**EiBi** | volné použití vč. software třetích stran (autor Eike Bierwirth, eibispace.de)
**HFCC/IBD** | veřejná koordinační data („Public Data Files", free access), hfcc.org
**Bi Newsletter („AOKI list")** | tvůrce neuvádí licenci; šířeno v dobré víře nekomerčně s atribucí (zvyklost DX komunity)

> Aplikace sama neukládá žádná osobní data (žádný backend, cookies ani analytika);
> uživatelská nastavení žijí jen v `localStorage`. Detaily v `legal.html`.

## Bez závislostí

- `eibi_sync.py`: pouze standardní knihovna Pythonu 3.
- PWA: bez frameworků, bez buildu, jediný HTML soubor + manifest + SW.
