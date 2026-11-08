#!/usr/bin/env python3
"""Parita skóre PWA (index.html) ↔ CLI (eibi_sync.py) nad stejnými daty a časem.

Spustí node tools/parity_dump.mjs, totéž spočítá Pythonem a porovná záznam po záznamu
(kmitočet, název, aka, skóre). Očekávaný výstup: 0 rozdílů.

    python3 tools/parity.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import eibi_sync as E  # noqa: E402

QTH = {"name": "kalibrace", "lat": 50.1041, "lon": 14.5499, "alt": 305, "az": 50}
SFI, KP = 125, 3


def main():
    js = json.loads(subprocess.run(["node", os.path.join(REPO, "tools", "parity_dump.mjs")],
                                   check=True, capture_output=True, text=True).stdout)
    db = json.load(open(os.path.join(REPO, "schedule.json"), encoding="utf-8"))
    total = diffs = 0
    for iso, rows in js.items():
        now = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        res, _, _ = E.score_stations(db, QTH, rx="pl330", ant="whip", sfi=SFI, kp=KP,
                                     blacklist=(), now_dt=now)
        py = {(r["freq"], r["station"]): (r.get("aka"), r["score"]) for r in res}
        jsr = {(r[0], r[1]): (r[2], r[3]) for r in rows}
        total += len(jsr)
        for k, (aka, sc) in jsr.items():
            if k not in py:
                diffs += 1
                print(f"{iso}: chybí v Pythonu {k} {sc}")
            elif py[k] != (aka, sc):
                diffs += 1
                print(f"{iso}: {k} JS aka={aka} skóre={sc} | Py aka={py[k][0]} skóre={py[k][1]}")
        for k in py:
            if k not in jsr:
                diffs += 1
                print(f"{iso}: chybí v JS {k} {py[k][1]}")
    print(f"parita: {total} záznamů, rozdílů {diffs}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
