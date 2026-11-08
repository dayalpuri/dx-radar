# DX Radar Pro — Context-aware SWL Engine

*English · [Česky](README.cs.md)*

**What can you actually hear on shortwave right now — and what did you just tune into?**
DX Radar is a helper for shortwave listeners (SWL). It takes the current broadcast
schedule, your location and the time, and ranks stations by how realistic their
reception is. That helps in both directions:

- **Planning:** don't waste time tuning to stations that won't reach you anyway.
- **Identifying:** you tuned something in but don't know what it is — several
  stations transmit on that frequency somewhere in the world, and the score ranks
  the most likely candidate for your location and time. The 🎧 stream check can then
  confirm it by ear.

Results are shown as a score and as a polar radar around your position.

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
| `scoring.js`          | Single source of tunable score constants (weights, thresholds, default blacklist) — read by both the PWA and the CLI |
| `eibi_sync.py`        | Data harvester (HFCC + AOKI + EiBi → builds `schedule.json`) + CLI radar |
| `schedule.json`       | Generated database (HFCC + AOKI, precise transmitter positions) committed to the repo |
| `schedule_eibi.json`  | Optional EiBi supplement (stations not in HFCC/AOKI, approximate positions) |
| `*.meta.json`         | Season, sources and record count of the generated files      |
| `manifest.webmanifest`| PWA manifest (icon, "Add to Home Screen")                   |
| `sw.js`               | Service worker — works offline after the first visit        |
| `icon-192/512.png`    | App icons                                                   |
| `legal.html`          | Licence, data-source attribution and privacy (EN/CS)        |
| `LICENSE`             | MIT licence for the code (data excluded — own source terms) |

## Data sources (the more lists, the better)

| List | What it provides | Where |
|------|------------------|-------|
| **HFCC** | seasonal (winter/summer) schedule, **exact transmitter GPS** (site.txt), real power in kW, **antenna azimuths** (directivity!), broadcast days, broadcaster names | `hfcc.org/data/{a,b}YY/` |
| **AOKI** (Bi Newsletter for DXers, "AOKI list"; personal newsletter of the site maintainer, not official NDXC) | best station names, precise coordinates (DDMMSS), power, azimuths, days; distributed as a Shift-JIS zip | `mediacat.ne.jp/binews/us/xz/xz*.zip` |
| **EiBi** | the largest number of stations (~8,000), often ahead of HFCC; position only approximate (ITU country code → GPS); days of operation | `eibispace.de/dx/sked-*.csv` |

Merged in the order HFCC > AOKI > EiBi. A lower-priority record is dropped only if it
is the same broadcast (same frequency + same station name or the same transmitter site,
overlapping time and days) and is fully covered by the higher-priority source — different
stations sharing a frequency always stay. The season code (`a26`, `b26`, `a27`…) is
derived from the date; sources from different seasons are never mixed.

## SWL log & web station verification

- **📝 Log** on each card: record SINPO (5 digits) + notes into the log (localStorage).
- **📖 Log** in the top bar: the full log, deleting entries, **📋 Export MD**
  (Markdown lines for Obsidian).
- **🎧 Stream** on each card: verify the ID of a received station via its web
  streams (radio-browser.info database, https streams only due to mixed-content).
  Exact matches ✅, loose matches ❔ (compare by ear) + Google fallback to the station's site.

## Running locally

```bash
# 1) Download the current schedules and build schedule.json (the GitHub cron does this daily)
python3 eibi_sync.py --sync

# 2) Serve the PWA locally (enables GPS/compass on localhost)
python3 -m http.server 8080
# → http://localhost:8080/
```

## CLI radar

The same scoring as the app, in the terminal (constants shared via `scoring.js`):

```bash
python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --alt 300 --az 180
```

| Option | Meaning |
|--------|---------|
| `--rx pl330\|airspy\|ats4732`, `--ant whip\|wire\|youloop` | receiver + antenna |
| `--sort freq\|score`, `--chance top\|mid\|low\|all`, `--limit N` | ordering, score group filter, number of targets |
| `--eibi` | add the EiBi supplement (`schedule_eibi.json`), like the "+ EiBi" switch in the app |
| `--no-blacklist` (alias `--show-china`) | disable the default blacklist from `scoring.js` |
| `--min-score N` | minimum score for time windows (default: the "Audible" boundary) |
| `--sfi`, `--kp` | space weather (default from `scoring.js`) |
| `--json FILE`, `--csv FILE` | use one explicit data file instead |

`--sync --source hfcc|aoki|eibi` refreshes only the chosen source.

## Running on mobile (GitHub Pages — recommended)

`file://` blocks GPS, compass and clipboard. The PWA is therefore hosted on GitHub
Pages, where it runs over `https://` and everything works:

1. Push this repository to GitHub.
2. On GitHub: **Settings → Pages → Deploy from a branch → `main` / root**.
3. On mobile open `https://<user>.github.io/dx-radar/` and in the Chrome menu choose
   **"Add to Home Screen"** — you get a full-fledged app.
4. After the first visit it also works **offline** (service worker) — in airplane
   mode the GPS entry and bundled data are enough.

## Updating the schedule data

The data is refreshed **automatically on GitHub**: a daily Actions cron
(`.github/workflows/sync-schedules.yml`) runs `python3 eibi_sync.py --sync`, which
downloads HFCC + AOKI + EiBi locally in Python (no third-party proxy) and commits
`schedule.json` (+ `schedule_eibi.json`) when anything changed. The repo — and, via
the network-first service worker, the installed PWA — is therefore never more than
~1 day stale. The app just loads `schedule.json` from the repo on startup; there is
no in-browser download step and no dependency on any CORS proxy.

To refresh manually (e.g. locally), run the same command:

```bash
python3 eibi_sync.py --sync
```

## Sync devel → mobile (workflow)

The repository is the single source of truth. After a season change (end of October /
end of March):

```bash
python3 eibi_sync.py --sync          # new schedule.json + schedule_eibi.json (+ .meta)
git add schedule.json schedule.meta.json schedule_eibi.json schedule_eibi.meta.json
git commit -m "B26: schedule update" && git push
# on next online open, mobile picks up fresh data from Pages
```

(Normally you don't do this by hand — the daily GitHub cron commits these for you.)

## Mobile GPS fallback

- No preset locations — enter the QTH via 📍 GPS or manually; it is stored only
  locally (localStorage in this browser / installed PWA), never in the repo.
- 📍 GPS button: over `https://` (Pages) full GPS + compass; on `file://` or if GPS
  is denied it tries an approximate location from IP (±50 km).

## Licence & legal

- **Code** (index.html, scoring.js, eibi_sync.py, sw.js, manifest, icons, legal.html, docs) is licensed under
  **MIT** — see [`LICENSE`](LICENSE).
- **Schedule data** (schedule.json etc.) is NOT covered by MIT — it comes from HFCC, AOKI
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
- PWA: no frameworks, no build step — `index.html` + `scoring.js` + manifest + SW.
