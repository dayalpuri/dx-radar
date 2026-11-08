# DX Radar Pro — Context-aware SWL Engine

*English · [Česky](README.cs.md)*

**What can you actually hear on shortwave right now?** DX Radar is a helper for
shortwave listeners (SWL). It takes the current broadcast schedule, your location
and the time, and ranks stations by how realistic their reception is — so you don't
waste time tuning to stations that won't reach you anyway. Results are shown as a
score and as a polar radar around your position.

The score is computed from the things that actually drive reception:

- **distance and direction** of the station (great-circle geometry) and where you have a clear view of the sky,
- **time of day and ionospheric state** — higher bands open in daytime, lower bands at night; space-weather data (SFI/Kp) is pulled from NOAA,
- **the skip zone** — a strong nearby station on a high band can "skip" over your head,
- **transmitter power and beaming** (where its antenna points),
- **adjacent-channel interference** and your **receiver + antenna** setup.

It runs as a web app (PWA) — offline after the first visit. Built in conversation
with AI; data from public schedules (HFCC, AOKI, EiBi). Details on accuracy and
licensing are below and in [`legal.html`](legal.html).

## Files

| File                  | Role                                                        |
|-----------------------|-------------------------------------------------------------|
| `index.html`          | PWA "DX Radar Pro 2.0" — engine + UI + polar radar          |
| `eibi_sync.py`        | Data harvester (HFCC + AOKI + EiBi → builds `eibi.json`)     |
| `eibi.json`           | Generated database of broadcast windows (committed to the repo = synced to mobile) |
| `manifest.webmanifest`| PWA manifest (icon, "Add to Home Screen")                   |
| `sw.js`               | Service worker — works offline after the first visit        |
| `icon-192/512.png`    | App icons                                                   |
| `legal.html`          | Licence, data-source attribution and privacy (EN/CS)        |
| `LICENSE`             | MIT licence for the code (data excluded — own source terms) |

## Data sources (the more lists, the better)

| List | What it provides | Where |
|------|------------------|-------|
| **HFCC** | seasonal (winter/summer) schedule, **exact transmitter GPS** (site.txt), real power in kW, **antenna azimuths** (directivity!), broadcast days, broadcaster names | `hfcc.org/data/{a,b}26/` |
| **AOKI** (Bi Newsletter for DXers, "AOKI list"; personal newsletter of the site maintainer, not official NDXC) | best station names, precise coordinates (DDMMSS), power, azimuths, days; distributed as a Shift-JIS zip | `mediacat.ne.jp/binews/us/xz/xz*.zip` |
| **EiBi** | the largest number of stations (~6,400), often ahead of HFCC; country only approximate (ITU → GPS) | `eibispace.de/dx/sked-*.csv` |

Merged in the order HFCC > AOKI > EiBi; mixing a stale season with a fresh one is
handled (EiBi A26 is skipped if a B26 from HFCC/AOKI exists).

## SWL log & web station verification

- **📝 Log** on each card: record SINPO (5 digits) + notes into the log (localStorage).
- **📖 Log** in the top bar: the full log, deleting entries, **📋 Export MD**
  (Markdown lines for Obsidian).
- **🎧 Stream** on each card: verify the ID of a received station via its web
  streams (radio-browser.info database, https streams only due to mixed-content).
  Exact matches ✅, loose matches ❔ (compare by ear) + Google fallback to the station's site.

## Running locally

```bash
# 1) Download the current schedule and build eibi.json (twice a year is enough, at the A/B season change)
python3 eibi_sync.py --sync

# 2) Serve the PWA locally (enables GPS/compass on localhost)
python3 -m http.server 8080
# → http://localhost:8080/
```

## Running on mobile (GitHub Pages — recommended)

`file://` blocks GPS, compass and clipboard. The PWA is therefore hosted on GitHub
Pages, where it runs over `https://` and everything works:

1. Push this repository to GitHub.
2. On GitHub: **Settings → Pages → Deploy from a branch → `main` / root**.
3. On mobile open `https://<user>.github.io/dx-radar/` and in the Chrome menu choose
   **"Add to Home Screen"** — you get a full-fledged app.
4. After the first visit it also works **offline** (service worker) — in airplane
   mode the GPS entry and bundled data are enough.

## Updating the schedule data (2 ways)

**A) Directly in the PWA (no Python):** the **⬇️ Download schedule** button fetches
the current season in the browser — HFCC first (`B26all00.TXT` + `site.txt` +
`broadcas.txt`: exact coordinates, power, azimuths and days), falling back to the
EiBi CSV if HFCC fails. Neither server sends CORS headers, so a Jina-reader proxy
is used as a fallback. Data is saved to `localStorage` and survives restarts and
airplane mode. On failure the app shows instructions for the manual 📂 import route
(the PWA reads `.csv` and `.json`).

**B) Via a laptop (classic):** `python3 eibi_sync.py --sync` merges HFCC + AOKI + EiBi
and builds `eibi.json`, which you commit to the repo — the PWA uses it as the default
database until the user downloads their own.

Source priority at startup: `localStorage` (last synced) → `eibi.json` in the repo →
built-in sample.

## Sync devel → mobile (workflow)

The repository is the single source of truth. After a season change (end of October /
end of March):

```bash
python3 eibi_sync.py --sync          # new eibi.json
git add eibi.json && git commit -m "B26: schedule update" && git push
# on next online open, mobile picks up fresh data from Pages
```

## Mobile GPS fallback

- No preset locations — enter the QTH via 📍 GPS or manually; it is stored only
  locally (localStorage in this browser / installed PWA), never in the repo.
- 📍 GPS button: over `https://` (Pages) full GPS + compass; on `file://` or if GPS
  is denied it tries an approximate location from IP (±50 km).

## Licence & legal

- **Code** (index.html, eibi_sync.py, sw.js, manifest, icons, docs) is licensed under
  **MIT** — see [`LICENSE`](LICENSE).
- **Schedule data** (eibi.json etc.) is NOT covered by MIT — it comes from HFCC, AOKI
  and EiBi, each under its own terms, redistributed in good faith for non-commercial use.
- Full attribution, usage terms, the disclaimer ("as is", built with AI) and the
  privacy/GDPR notice are in [`legal.html`](legal.html) (bilingual EN/CS; also linked
  from the app footer).

Data source | Licence / terms
------------|----------------
**EiBi** | free use incl. third-party software (by Eike Bierwirth, eibispace.de)
**HFCC/IBD** | public coordination data ("Public Data Files", free access), hfcc.org
**Bi Newsletter ("AOKI list")** | compiler states no licence; redistributed in good faith, non-commercial, with attribution (DX-community convention)

> The app itself stores no personal data (no backend, cookies or analytics); user
> settings live only in `localStorage`. Details in `legal.html`.

## No dependencies

- `eibi_sync.py`: Python 3 standard library only.
- PWA: no frameworks, no build step, a single HTML file + manifest + SW.
