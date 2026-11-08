#!/usr/bin/env python3
"""
eibi_sync.py - Data Harvester + CLI radar pro Balkónový DX Engine.

Dvě funkce v jednom souboru (společný datový základ pro PWA index.html):

  1. HARVESTER:  stáhne sezónní rozvrhy HFCC + AOKI (přesné souřadnice vysílačů,
                 výkony, azimuty, dny) -> schedule.json, a EiBi (sked-*.csv, země
                 dle ITU kódu jen s přibližnou polohou) -> doplněk schedule_eibi.json.

  2. CLI RADAR:  s parametrem --now vypíše stejný "DX Radar" jako PWA přímo
                 do terminálu. Skóre počítá 1:1 stejně jako aplikace - obě
                 strany sdílí konstanty ze scoring.js (jediný zdroj), takže se
                 nerozcházejí. Cíle jsou deduplikované napříč zdroji a defaultně
                 řazené dle kmitočtu (--sort score = dle šance). Časová okna
                 obsahují jen budoucí události (starty ▶, uvolňující se kanály 🔓).

Bez externích závislostí - pouze standardní knihovna Pythonu 3.

Použití:
  python3 eibi_sync.py --sync                 # stáhne rozvrhy a vygeneruje schedule.json (+ schedule_eibi.json)
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --alt 300 --az 50   # radar pro zadané QTH
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --rx airspy --ant youloop   # jiná sestava
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --sort score --chance top   # jen silné, dle šance
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --eibi --no-blacklist      # + EiBi doplněk, bez blacklistu
"""

import argparse
import csv
import functools
import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

EIBI_BASE = "http://eibispace.de/dx/"
# Zimní sezóna (B) platí od poslední říjnové neděle do poslední březnové neděle.
# Kódy sezón (a26, b26, a27...) se počítají z data - viz season_code().
DEFAULT_OUT_JSON = "schedule.json"

# ---------------------------------------------------------------------------
# Zjednodušený slovník ITU kódů (jak je používá EiBi: G, D, F, J, KRE, VTN...)
# -> přibližné souřadnice hlavního vysílacího uzlu. Kódy ověřeny proti legendě
# eibispace.de/dx/README.TXT. EiBi samotné souřadnice nedodává; CLA (clandestine)
# a XUU (neidentifikováno) záměrně chybí - poloha neznámá.
# ---------------------------------------------------------------------------
COUNTRY_COORDS = {
    "MLI": (12.65, -8.00),   # Mali
    "TZA": (-6.10, 39.26),   # Tanzanie
    "ETH": (8.88, 38.78),    # Etiopie
    "MDG": (-18.87, 47.50),  # Madagaskar
    "NIG": (9.05, 7.49),     # Nigérie
    "AFS": (-26.55, 28.01),  # Jižní Afrika (Meyerton)
    "EGY": (31.18, 30.05),   # Egypt (Abis)
    "TUR": (39.93, 32.85),   # Turecko (Emirler)
    "GRC": (38.40, 23.60),   # Řecko (Avlis)
    "IRN": (29.45, 55.68),   # Írán (Sirjan)
    "IND": (13.23, 77.70),   # Indie (Bengaluru)
    "VTN": (21.13, 105.50),  # Vietnam
    "MYA": (16.86, 96.19),   # Myanmar
    "INS": (-5.14, 119.43),  # Indonésie (Makassar)
    "MLA": (2.99, 101.78),   # Malajsie (Kajang)
    "THA": (14.02, 100.52),  # Thajsko (Udon Thani)
    "B":   (-15.60, -47.90), # Brazílie (Brasília)
    "CHN": (39.90, 116.40),  # Čína
    "ROU": (44.75, 26.10),   # Rumunsko (Tiganesti)
    "ARS": (24.71, 46.67),   # Saúdská Arábie (Rijád)
    "OMA": (23.58, 58.38),   # Omán
    "CUB": (22.95, -82.40),  # Kuba (Bauta/Artemisa)
    "USA": (38.90, -77.00),  # USA (greenville ~35.9,-77.0; hl. uzel)
    "KOR": (37.55, 126.90),  # Jižní Korea
    "J":   (35.68, 139.69),  # Japonsko
    "PHL": (14.58, 120.97),  # Filipíny
    "AUS": (-33.87, 151.21), # Austrálie (Sydney/Vyner)
    "CAN": (45.42, -75.70),  # Kanada (Sackville)
    "G":   (51.48, -0.45),   # Velká Británie (Wootton)
    "F":   (47.65, 1.30),    # Francie (Allouis)
    "D":   (50.85, 9.65),    # Německo (Weener/Nauen)
    "E":   (40.42, -3.70),   # Španělsko (Arganda)
    "I":   (41.90, 12.50),   # Itálie (RMC Pisa ~43.7,10.4)
    "POR": (38.75, -9.15),   # Portugalsko
    "HOL": (52.20, 5.40),    # Nizozemsko (Lopik/Mederfoort)
    "BEL": (50.85, 4.35),    # Belgie (Wavre)
    "S":   (59.33, 18.07),   # Švédsko (Horby)
    "NOR": (59.90, 10.75),   # Norsko (Kvitsøy)
    "FIN": (60.45, 25.00),   # Finsko (Pori ~61.5,21.8)
    "RUS": (55.75, 37.62),   # Rusko (Moskva)
    "UKR": (50.45, 30.52),   # Ukrajina (Kyjev/Brovary)
    "POL": (52.23, 21.00),   # Polsko (Warszawa)
    "CZE": (50.09, 14.30),   # Česko (Liblice)
    "SVK": (48.15, 17.10),   # Slovensko
    "HNG": (47.50, 19.05),   # Maďarsko (Szolnoki/Sopron)
    "AUT": (48.20, 16.37),   # Rakousko (Moosbrunn)
    "SUI": (46.95, 7.45),    # Švýcarsko (Sottens)
    "ISR": (31.90, 34.90),   # Izrael
    "JOR": (32.00, 36.00),   # Jordánsko
    "LBN": (33.90, 35.50),   # Libanon
    "SYR": (33.50, 36.30),   # Sýrie
    "IRQ": (33.30, 44.40),   # Irák (Dohuk)
    "PAK": (33.70, 73.10),   # Pákistán (Islamabad)
    "BGD": (23.80, 90.40),   # Bangladéš (Savar)
    "CLN": (6.90, 79.90),    # Srí Lanka (Ekala)
    "NPL": (27.70, 85.30),   # Nepál
    "KAZ": (43.25, 76.90),   # Kazachstán (Alma-Ata)
    "UZB": (41.30, 69.25),   # Uzbekistán (Taškent)
    "TKM": (38.00, 63.20),   # Turkmenistán
    "KGZ": (42.87, 74.60),   # Kyrgyzstán
    "TWN": (24.71, 121.00),  # Tchaj-wan (Tamsui/Paochung)
    "KRE": (39.00, 125.75),  # Severní Korea (Kujang)
    "MNG": (47.90, 106.90),  # Mongolsko
    "ARG": (-34.60, -58.38), # Argentina (General Pacheco)
    "CHL": (-33.45, -70.67), # Chile (Colina/Rengo)
    "PRU": (-12.05, -77.00), # Peru (Mala)
    "CLM": (4.60, -74.08),   # Kolumbie
    "VEN": (10.50, -66.90),  # Venezuela (Turmero)
    "EQA": (-0.15, -78.35),  # Ekvádor
    "BOL": (-16.50, -68.15), # Bolívie
    "PRG": (-25.28, -57.60), # Paraguay
    "URG": (-34.90, -56.20), # Uruguay
    "MEX": (19.40, -99.10),  # Mexiko
    "GTM": (14.60, -90.50),  # Guatemala (San Marcos)
    "CTR": (9.90, -84.10),   # Kostarika (Cartago)
    "HND": (14.10, -87.20),  # Honduras
    "ALG": (36.75, 3.05),    # Alžírsko (Bechar/Ourgla)
    "LBY": (32.85, 13.20),   # Libye (Sabratha)
    "TUN": (36.80, 10.18),   # Tunisko (Sidi Tlat)
    "MRC": (33.60, -7.60),   # Maroko (Nador/Casablanca)
    "SDN": (15.60, 32.50),   # Súdán (Omdurman/Umm Haraz)
    "SSD": (4.85, 31.60),    # Jižní Súdán
    "ERI": (15.33, 38.93),   # Eritrea (Asmara)
    "DJI": (11.60, 43.15),   # Džibuti
    "SOM": (2.05, 45.33),    # Somálsko
    "KEN": (-1.28, 36.80),   # Keňa (Nairobi/Thika)
    "UGA": (0.32, 32.60),    # Uganda (Kampala)
    "COD": (-4.30, 15.30),   # DR Kongo (Kananga)
    "COG": (-4.25, 15.25),   # Kongo Brazzaville
    "CME": (3.87, 11.52),    # Kamerun (Garoua)
    "GAB": (0.42, 9.47),     # Gabon (Ntoum/Moyabi)
    "CTI": (6.70, -5.30),    # Pobřeží slonoviny (Abidjan)
    "SEN": (14.70, -17.40),  # Senegal (Diam Niadio)
    "GHA": (5.60, -0.17),    # Ghana (Tema/Amansuri)
    "BFA": (12.35, -1.50),   # Burkina Faso
    "ZMB": (-15.40, 28.30),  # Zambie (Lusaka)
    "ZWE": (-17.80, 31.05),  # Zimbabwe (Gweru)
    "MOZ": (-25.97, 32.58),  # Mosambik (Maputo/Moatize)
    "MWI": (-13.95, 33.78),  # Malawi (Lilongwe/Mchijii)
    "NMB": (-22.50, 17.05),  # Namibie
    "AGL": (-8.80, 13.25),   # Angola (Benguela)
    "GNE": (3.75, 8.78),     # Rovníková Guinea (Bata)
    "UAE": (24.43, 54.48),   # UAE (Dubai)
    "QAT": (25.28, 51.52),   # Katar
    "KWT": (29.35, 47.95),   # Kuvajt (Kabed)
    "BHR": (26.20, 50.58),   # Bahrajn
    "AFG": (34.50, 69.20),   # Afghánistán
    "BLR": (53.90, 27.55),   # Bělorusko (Minsk)
    "MDA": (47.00, 28.85),   # Moldavsko (Mayak/Grimace)
    "SRB": (44.80, 20.48),   # Srbsko (Viline Vode/Kvish)
    "HRV": (45.80, 16.00),   # Chorvatsko (Zagreb/Deanovec)
    "BIH": (43.85, 18.40),   # Bosna (Vogosca)
    "SVN": (46.05, 14.50),   # Slovinsko
    "MKD": (41.98, 21.43),   # Severní Makedonie (Oteševo)
    "BUL": (42.70, 23.35),   # Bulharsko (Kostinbrod/Plovdiv)
    "ALB": (41.33, 19.45),   # Albánie (Shijak)
    "GEO": (41.70, 44.80),   # Gruzie (Tbilisi)
    "ARM": (40.18, 44.50),   # Arménie (Gavar)
    "AZE": (40.40, 49.85),   # Ázerbájdžán
    "IRL": (53.30, -6.30),   # Irsko (Clarkestown)
    "DNK": (56.30, 9.50),    # Dánsko (Kalundborg/Daud)
    "ISL": (64.13, -21.90),  # Island (Grindavik)
    "LUX": (49.60, 6.10),    # Lucembursko (Junglinster/Marnach)
    "CYP": (35.15, 33.38),   # Kypr (Zygi/Maherido)
    "MLT": (35.85, 14.50),   # Malta (Delimara/Madliena)
    "PNG": (-9.45, 147.20),  # Papua Nová Guinea (Port Moresby)
    "NCL": (-22.28, 166.40), # Nová Kaledonie
    "VUT": (-17.75, 168.30), # Vanuatu
    "CVA": (42.05, 12.32),   # Vatikán (Santa Maria di Galeria)
    "SWZ": (-26.57, 31.42),  # Eswatini (TWR Manzini)
    "NZL": (-38.84, 176.42), # Nový Zéland (Rangitaiki)
    "ALS": (59.75, -151.73), # Aljaška (Anchor Point)
    "HWA": (19.03, -155.67), # Havaj (Naalehu)
    "GUM": (13.28, 144.67),  # Guam (Merizo)
    "HKG": (22.30, 114.17),  # Hongkong
    "CNR": (28.10, -15.42),  # Kanárské ostrovy
    "AZR": (37.74, -25.67),  # Azory
    "PTR": (18.22, -66.59),  # Portoriko
    "BER": (32.30, -64.78),  # Bermudy
    "PNR": (8.98, -79.52),   # Panama
    "TRD": (10.65, -61.50),  # Trinidad a Tobago
    "TCD": (12.11, 15.04),   # Čad
    "FJI": (-18.14, 178.44), # Fidži
    "OCE": (-17.53, -149.57),# Francouzská Polynésie (Tahiti)
    "SLM": (-9.43, 159.95),  # Šalamounovy ostrovy
    "MRT": (14.61, -61.07),  # Martinik
    "LBR": (6.24, -10.70),   # Libérie (ELWA Monrovia)
    "SNG": (1.42, 103.73),   # Singapur (Kranji)
    "CYM": (19.29, -81.37),  # Kajmanské ostrovy
    "NCG": (12.13, -86.25),  # Nikaragua
    "SEY": (-4.62, 55.45),   # Seychely
}

# Čínské identifikátory: ITU kód, nebo vzor v názvu stanice (včetně relé mimo Čínu).
CHINA_ITU = {"CHN"}
CHINA_NAME_PATTERNS = ("CRI", "China Radio", "CNR", "China National", "PBS ",
                      "Voice of Strait", "Chinese")

# Generické výchozí QTH (střed ČR) — žádná konkrétní soukromá poloha v repu.
# Vlastní stanoviště zadej přes --lat/--lon/--alt/--az.
DEFAULT_QTH = {"name": "Výchozí (střed ČR)", "lat": 49.80, "lon": 15.47, "alt": 300, "az": 180}


# --- Laditelné konstanty skóre: JEDINÝ ZDROJ je scoring.js (čte ho i PWA) ---
# Díky tomu se CLI radar a aplikace v prohlížeči nemůžou rozejít - laď jen scoring.js.
def _load_scoring():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoring.js")
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    m = re.search(r"window\.SCORING\s*=\s*(\{.*?\});", txt, re.DOTALL)
    if not m:
        raise RuntimeError("scoring.js: blok 'window.SCORING = {...}' nenalezen")
    return json.loads(m.group(1))


SCORING = _load_scoring()


def jround(x):
    """Zaokrouhlení jako JS Math.round() (half-up k +∞), ne bankéřské jako Python
    round(). Nutné, aby CLI skóre sedělo 1:1 s PWA i na hodnotách X.5."""
    return math.floor(x + 0.5)

# Vzorek databáze (fallback pro --now bez dat; identický s PWA, aby výstupy seděly)
SAMPLE_DB = [
    {"freq": 5995, "start": "19:00", "end": "23:00", "station": "ORTM Radio Mali", "country": "MLI", "lang": "Fr/Bambara", "site": "Bamako", "lat": 12.65, "lon": -8.00, "kw": 50, "isChina": False},
    {"freq": 6015, "start": "18:00", "end": "20:00", "station": "ZBC Radio Zanzibar", "country": "TZA", "lang": "Swahili", "site": "Dole", "lat": -6.10, "lon": 39.26, "kw": 50, "isChina": False},
    {"freq": 6020, "start": "19:00", "end": "22:00", "station": "China Radio Int.", "country": "CHN", "lang": "Albanian/Russian", "site": "Szczecinek/Kashgar", "lat": 39.47, "lon": 75.98, "kw": 500, "isChina": True},
    {"freq": 6110, "start": "18:00", "end": "20:00", "station": "Radio Romania Int.", "country": "ROU", "lang": "German", "site": "Tiganesti", "lat": 44.75, "lon": 26.10, "kw": 300, "isChina": False},
    {"freq": 6110, "start": "18:00", "end": "21:00", "station": "Radio Fana", "country": "ETH", "lang": "Amharic/Oromo", "site": "Addis Abeba", "lat": 8.88, "lon": 38.78, "kw": 100, "isChina": False},
    {"freq": 6185, "start": "19:20", "end": "20:20", "station": "IRIB Voice of Iran", "country": "IRN", "lang": "English", "site": "Sirjan", "lat": 29.45, "lon": 55.68, "kw": 500, "isChina": False},
    {"freq": 9420, "start": "18:00", "end": "23:00", "station": "ERT Voice of Greece", "country": "GRC", "lang": "Greek", "site": "Avlis", "lat": 38.40, "lon": 23.60, "kw": 100, "isChina": False},
    {"freq": 9620, "start": "19:00", "end": "20:30", "station": "All India Radio", "country": "IND", "lang": "Hindi/English", "site": "Bengaluru", "lat": 13.23, "lon": 77.70, "kw": 500, "isChina": False},
    {"freq": 7220, "start": "20:30", "end": "21:00", "station": "Voice of Vietnam", "country": "VNM", "lang": "English", "site": "Son Tay", "lat": 21.13, "lon": 105.50, "kw": 100, "isChina": False},
    {"freq": 7220, "start": "20:00", "end": "20:30", "station": "Voice of Vietnam", "country": "VNM", "lang": "German", "site": "Son Tay", "lat": 21.13, "lon": 105.50, "kw": 100, "isChina": False},
    {"freq": 5985, "start": "19:00", "end": "21:30", "station": "Myanma Radio", "country": "MMR", "lang": "Burmese/Eng", "site": "Yangon", "lat": 16.86, "lon": 96.19, "kw": 50, "isChina": False},
    {"freq": 5990, "start": "19:00", "end": "22:00", "station": "China Radio Int.", "country": "CHN", "lang": "Turkish/Eng", "site": "Urumqi", "lat": 43.82, "lon": 87.61, "kw": 500, "isChina": True},
    {"freq": 9575, "start": "20:00", "end": "23:00", "station": "Radio Cairo", "country": "EGY", "lang": "Arabic/English", "site": "Abis", "lat": 31.18, "lon": 30.05, "kw": 250, "isChina": False},
    {"freq": 11780, "start": "20:00", "end": "23:59", "station": "Rádio Nacional Amazônia", "country": "BRA", "lang": "Portuguese", "site": "Brasília", "lat": -15.60, "lon": -47.90, "kw": 100, "isChina": False},
    {"freq": 9665, "start": "21:00", "end": "23:59", "station": "Voz Missionária", "country": "BRA", "lang": "Portuguese", "site": "Camboriú", "lat": -27.02, "lon": -48.65, "kw": 10, "isChina": False},
    {"freq": 4755, "start": "21:00", "end": "23:00", "station": "Voice of Indonesia", "country": "IDN", "lang": "English", "site": "Makassar", "lat": -5.14, "lon": 119.43, "kw": 50, "isChina": False},
    {"freq": 3320, "start": "20:00", "end": "23:00", "station": "Radio Sondergrense", "country": "ZAF", "lang": "Afrikaans", "site": "Meyerton", "lat": -26.55, "lon": 28.01, "kw": 100, "isChina": False},
    {"freq": 6676, "start": "00:00", "end": "23:59", "station": "Bangkok / Mumbai VOLMET", "country": "THA/IND", "lang": "English (USB)", "site": "Bangkok/Mumbai", "lat": 13.75, "lon": 100.50, "kw": 10, "isChina": False},
]

# ---------------------------------------------------------------------------
# SFÉRICKÁ MATEMATIKA (Haversine + počáteční azimut ortodromy)
# ---------------------------------------------------------------------------
def calc_geodesic(lat1, lon1, lat2, lon2):
    """Vrátí (vzdálenost_km, azimut_stupně) po ortodromě."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    dp = p2 - p1
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    bearing = math.degrees(math.atan2(y, x)) % 360
    return jround(dist), jround(bearing)


def compass_dir(az):
    dirs = ['S', 'SSV', 'SV', 'VSV', 'V', 'VJV', 'JV', 'JJV',
            'J', 'JJZ', 'JZ', 'ZJZ', 'Z', 'ZSZ', 'SZ', 'SSZ']  # sever/východ/jih/západ
    return dirs[jround(az / 22.5) % 16]


def is_time_active(start, end, now_minutes):
    sh, sm = map(int, start.split(':'))
    eh, em = map(int, end.split(':'))
    s, e = sh * 60 + sm, eh * 60 + em
    if s == e:  # 00:00-23:59 i degenerovaná okna bereme jako celodenní
        return True
    return s <= now_minutes < e if s < e else (now_minutes >= s or now_minutes < e)


def minutes_until(end, now_minutes):
    eh, em = map(int, end.split(':'))
    e = eh * 60 + em
    return (e - now_minutes) % (24 * 60)


def _hhmm(s):
    h, m = map(int, s.split(':'))
    return h * 60 + m


def is_all_day(st):
    """Celodenní vysílání (00:00-24:00, 00:00-23:59, start == konec) nikdy „nekončí"."""
    s, e = _hhmm(st.get("start", "00:00")), _hhmm(st.get("end", "23:59"))
    return s % 1440 == e % 1440 or (s == 0 and e >= 1439)


def minutes_left(st, now_minutes):
    """Minuty do konce vysílání; celodenní = inf (žádné ⏹ ani 🔓 okno). Jako PWA minutesLeft()."""
    if is_all_day(st):
        return math.inf
    return minutes_until(st.get("end", "23:59"), now_minutes) or 1440


def _bl_matches(p, st):
    """Vzor VELKÝMI = kód země (přesně); jinak slovo/fráze v názvu, za kterou smí
    být číslo ("cnr" ~ "CNR1", "cri" !~ "Cristiana"). Stejně jako PWA blMatches()."""
    if p == p.upper() and re.search(r"[A-Z]", p) and st.get("country", "") == p:
        return True
    return re.search(rf"(^|[^a-z0-9]){re.escape(p.lower())}($|[^a-z])",
                     (st.get("station") or "").lower()) is not None


def is_blacklisted(st, patterns):
    """Jako PWA isBlacklisted(): i druhý název téhož vysílání (aka)."""
    aka = {"station": st["aka"]} if st.get("aka") else None
    return any(_bl_matches(p, st) or (aka and _bl_matches(p, aka)) for p in patterns or ())


def make_ctx(qth, rx, ant, sfi, kp, now=None):
    """Kontext jednoho přepočtu (jako env v PWA) + cache skóre dopadu na QTH.
    now = jednotný čas celého přepočtu (poloha Slunce), ne systémový čas per stanice."""
    return {"qth": qth, "rx": rx, "ant": ant, "sfi": sfi, "kp": kp, "arrival": {},
            "now": now or datetime.now(timezone.utc)}


def arrival_score(st, ctx):
    """Skóre dopadu na QTH = skóre bez QRM (PWA arrivalScore). Cache drží i objekt,
    aby se id() nemohlo recyklovat."""
    hit = ctx["arrival"].get(id(st))
    if hit is None or hit[0] is not st:
        hit = (st, _score_one(st, ctx["qth"], ctx["rx"], ctx["ant"], None,
                              ctx["sfi"], ctx["kp"], ctx)["score"])
        ctx["arrival"][id(st)] = hit
    return hit[1]


def louder(o, st, ctx):
    """Rušitel jen když sám na QTH dopadá a silněji než stanice (PWA louder)."""
    q = SCORING["qrm"]
    ao = arrival_score(o, ctx)
    return ao >= q["minInterfererScore"] and ao > arrival_score(st, ctx) + q["louderMargin"]


def prefer_record(a, b, ctx):
    """Totéž vysílání ze dvou zdrojů: přesná poloha (ne approxLoc) má přednost, pak
    lepší dopad na QTH (vysílač/anténa k nám), pak vyšší výkon. Jako PWA preferRecord."""
    if bool(a.get("approxLoc")) != bool(b.get("approxLoc")):
        return b if a.get("approxLoc") else a
    sa, sb = arrival_score(a, ctx), arrival_score(b, ctx)
    if sa != sb:
        return b if sb > sa else a
    return b if b.get("kw", 0) > a.get("kw", 0) else a


def _is_placeholder(st):
    """HFCC rezervační slot bez vysílatele („For new organization") - reálně vysílá, ale jméno není."""
    return any(_bl_matches(p, st) for p in SCORING["placeholderNames"])


def _merge_twin(a, b, ctx):
    """Jako PWA mergeTwin(): placeholder vs skutečný program téhož vysílače -> technická
    data z preferovaného záznamu, identita (název, země, jazyk) ze skutečného; placeholder
    se nedrží ani jako aka (jinak by ho výchozí blacklist skryl i se skutečnou stanicí)."""
    kept = prefer_record(a, b, ctx)
    other = b if kept is a else a
    if _is_placeholder(kept) and not _is_placeholder(other):
        return {**kept, "station": other.get("station"), "country": other.get("country"),
                "lang": other.get("lang"), "aka": other.get("aka")}
    if _is_placeholder(other):
        return kept
    if not kept.get("aka") and other.get("station") != kept.get("station"):
        kept = {**kept, "aka": other.get("station")}
    return kept


def dedup_active(records, ctx):
    """Jako PWA dedupActive(): stejná stanice (station_key), pak stejný kmitočet ze
    stejného vysílače ve stejnou chvíli = totéž vysílání pod jiným názvem."""
    dedup = {}
    for st in records:
        k = station_key(st)
        dedup[k] = prefer_record(dedup[k], st, ctx) if k in dedup else st
    out = []
    for st in dedup.values():
        i = next((i for i, o in enumerate(out) if o["freq"] == st["freq"] and _same_site(o, st)), None)
        if i is None:
            out.append(st)
        else:
            out[i] = _merge_twin(out[i], st, ctx)
    return out


# Běžné zkratky v názvech stanic: EiBi píše "R.ROMANIA INT.",
# HFCC/AOKI "Radio Romania International" - po rozbalení je to tatáž stanice.
_STATION_ALIAS = {
    "R": "RADIO", "RD": "RADIO", "INT": "INTERNATIONAL", "INTL": "INTERNATIONAL",
    "NATL": "NATIONAL", "BC": "BROADCASTING", "BR": "BROADCASTING",
    "COMM": "COMMUNICATIONS", "ORG": "ORGANIZATION",
}


def _norm_station(name):
    words = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper()).split()
    return "".join(_STATION_ALIAS.get(w, w) for w in words)


def station_key(st):
    """Deduplikační klíč: stejná stanice na stejné frekvenci (jako v PWA),
    aby se jedno vysílání z EiBi/HFCC/AOKI nezdvojovalo. Zkratky v názvu
    se rozbalují, takže chytá i různě zapsané názvy téže stanice."""
    return f"{st.get('freq')}|{_norm_station(st.get('station'))}"


# ---------------------------------------------------------------------------
# 1) HARVESTER: EiBi CSV -> JSON pro PWA
# ---------------------------------------------------------------------------
def current_season(now=None):
    """B sezóna (zimní) = konec října až konec března."""
    now = now or datetime.now(timezone.utc)
    if now.month in (11, 12, 1, 2):
        return "b"
    if now.month == 10 and now.day >= 25:
        return "b"
    if now.month == 3 and now.day <= 25:
        return "b"
    return "a"


def season_code(now=None):
    """Kód aktuální sezóny ITU/HFCC: 'a26' = léto 2026, 'b26' = zima 2026/27
    (v lednu-březnu 2027 tedy pořád 'b26')."""
    now = now or datetime.now(timezone.utc)
    yy = now.year % 100
    if current_season(now) == "b" and now.month <= 3:
        yy -= 1
    return f"{current_season(now)}{yy:02d}"


def previous_season(code):
    """b26 -> a26, a27 -> b26 (záloha, když nová sezóna ještě není publikovaná)."""
    yy = int(code[1:])
    return f"a{yy:02d}" if code[0] == "b" else f"b{(yy - 1) % 100:02d}"


def season_candidates(preferred=None):
    preferred = preferred or season_code()
    return [preferred, previous_season(preferred)]


def download_eibi(csv_path):
    """Stáhne aktuální sked z eibispace.de. Zkusí aktuální sezónu, pak předchozí."""
    for fname in (f"sked-{s}.csv" for s in season_candidates()):
        url = EIBI_BASE + fname
        try:
            print(f"[*] Stahuji {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "dx-radar/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(csv_path, "wb") as f:
                f.write(r.read())
            print(f"[+] Uloženo: {csv_path} ({fname})")
            return csv_path, fname
        except Exception as exc:
            print(f"[!] {fname} nedostupné ({exc}).")
    print("[!] EiBi online nedostupné - použijte lokální CSV přes --csv.")
    return None, None


_EIBI_DAYS = {"Mo": 1, "Tu": 2, "We": 3, "Th": 4, "Fr": 5, "Sa": 6, "Su": 7}


def parse_eibi_days(raw):
    """EiBi sloupec dnů -> řetězec číslic jako HFCC ('135' = Po, St, Pá; '' = denně).

    Umí 'Mo-Fr', 'We-Mo' (přes konec týdne), 'Tu,Fr', 'SaSu' a číslice '1245'
    (1 = pondělí). Nepravidelné/speciální údaje ('irr', 'alt', '1.Sa', '3Nov',
    'LSB'...) nefiltrujeme -> ''.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        days = {int(c) for c in raw if "1" <= c <= "7"}
    else:
        days = set()
        for part in raw.split(","):
            m = re.fullmatch(r"([A-Z][a-z])-([A-Z][a-z])", part)
            if m and m.group(1) in _EIBI_DAYS and m.group(2) in _EIBI_DAYS:
                a, b = _EIBI_DAYS[m.group(1)], _EIBI_DAYS[m.group(2)]
                d = a
                while True:
                    days.add(d)
                    if d == b:
                        break
                    d = d % 7 + 1
                continue
            chunks = re.findall(r"..", part) if len(part) % 2 == 0 else []
            if not chunks or any(c not in _EIBI_DAYS for c in chunks):
                return ""
            days.update(_EIBI_DAYS[c] for c in chunks)
    if not days or len(days) == 7:
        return ""
    return "".join(str(d) for d in sorted(days))


def parse_eibi_csv(csv_path):
    """Rozparsuje sked-*.csv do záznamů kompatibilních s PWA (index.html).

    Formát EiBi (oddělovač ';', první řádek = hlavička):
      0: kHz, 1: HHMM-HHMM, 2: dny, 3: ITU země, 4: stanice, 5: jazyk,
      6: cílová oblast, 7: kód vysílače, 8: persistence, 9-10: platnost.
    """
    records = []
    skipped = {}
    with open(csv_path, mode="r", encoding="latin-1") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader, None)  # přeskočit hlavičku
        for row in reader:
            if len(row) < 5:
                continue
            try:
                freq = int(float(row[0].strip()))
            except ValueError:
                continue
            if not (2300 <= freq <= 26100):
                continue
            time_raw = row[1].strip()
            if len(time_raw) != 9 or "-" not in time_raw:
                continue
            start_s, end_s = time_raw.split("-")
            if not (start_s.isdigit() and end_s.isdigit()):
                continue
            country = row[3].strip()
            station = row[4].strip()
            lang = row[5].strip() if len(row) > 5 else ""
            site = row[7].strip() if len(row) > 7 else ""
            if country not in COUNTRY_COORDS:
                skipped[country] = skipped.get(country, 0) + 1
                continue  # bez souřadnic nemá záznam pro radar hodnotu
            lat, lon = COUNTRY_COORDS[country]
            is_china = (country in CHINA_ITU
                        or any(pat in station for pat in CHINA_NAME_PATTERNS))
            records.append({
                "freq": freq,
                "start": f"{start_s[:2]}:{start_s[2:]}",
                "end": f"{end_s[:2]}:{end_s[2:]}",
                "station": station,
                "country": country,
                "lang": lang,
                "site": site or station,
                "lat": lat, "lon": lon,
                "kw": 500 if is_china else 100,
                "isChina": is_china,
                "days": parse_eibi_days(row[2]),
                "approxLoc": True,  # poloha = centroid země, ne přesný vysílač
            })
    if skipped:
        top = ", ".join(f"{k or '?'}:{v}" for k, v in sorted(skipped.items(), key=lambda kv: -kv[1]))
        print(f"[!] EiBi: {sum(skipped.values())} záznamů bez souřadnic země přeskočeno ({top}).")
    return records


# ---------------------------------------------------------------------------
# 1b) HFCC (hfcc.org) - druhý velký sezónní seznam.
#     Oproti EiBi nabízí: přesné GPS souřadnice vysílačů (site.txt), reálné
#     výkony, azimuty vysílacích antén a dny vysílání (korekce směrovosti!).
# ---------------------------------------------------------------------------
HFCC_BASE = "http://www.hfcc.org/data/"


def download_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dx-radar/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
    # HFCC soubory se liší: language.txt je UTF-8 (s BOM), broadcas.txt Latin-1.
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def hfcc_files(season):
    s = season.upper()
    return {
        "schedule": f"{HFCC_BASE}{season}/{s}all00.TXT",
        "site": f"{HFCC_BASE}{season}/site.txt",
        "broadcas": f"{HFCC_BASE}{season}/broadcas.txt",
        "language": f"{HFCC_BASE}{season}/language.txt",
    }


def parse_hfcc_site(text):
    """site.txt -> {KOD: (nazev, lat, lon)}; souřadnice ve tvaru 46N57 / 001E59."""
    rx = re.compile(
        r"^(\S+)\s+(.+?)\s+([A-Z]{1,3})\s+(\d{2})([NS])(\d{2})\s+(\d{3})([EW])(\d{2})")
    sites = {}
    for line in text.splitlines():
        m = rx.match(line)
        if not m:
            continue
        code, name, _adm, latd, lath, latm, lond, lone, lonm = m.groups()
        lat = int(latd) + int(latm) / 60
        lon = int(lond) + int(lonm) / 60
        if lath == "S":
            lat = -lat
        if lone == "W":
            lon = -lon
        sites[code] = (name.strip(), round(lat, 3), round(lon, 3))
    return sites


def parse_hfcc_table(text):
    """admin/broadcas/language tabulky: KOD -> název (fixní šířka sloupce)."""
    out = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        code = line[:3].strip()
        name = line[3:53].strip() or line[3:].strip()
        if code and name and code[0].isalpha():
            out[code] = name
    return out


def parse_hfcc_schedule(text, sites, brc, langs):
    """HFCC 'Sxxall00.TXT' -> záznamy kompatibilní s PWA (+azimuth, +days).

    Řádky nemají stoprocentně fixní sloupce (CIRAF/ZONES i AFRQ mívají
    proměnnou šířku), proto parsujeme regulárním výrazem ukotveným na
    jednoznačnou strukturu: FREQ STRT STOP ... LOC POWR AZIM SLW ANT DAYS
    FDATE TDATE MOD [AFRQ] LANGUAGE ADM BRC FMO REQ...
    """
    row_rx = re.compile(
        r"^\s*(\d{4,5})\s+(\d{4})\s+(\d{4})\s+"          # FREQ STRT STOP
        r".*?\s+([A-Z0-9-]{1,5})\s+"                     # CIRAF/ZONES .. LOC (kód místa)
        r"(\d{1,4})\s+(\d{1,3})\s+(\d)\s+(\d{1,4})\s+(\d{1,7})\s+"  # POWR AZIMUTH SLW ANT DAYS
        r"(\d{6})\s+(\d{6})\s+([A-Z])\s+"                # FDATE TDATE MOD
        r"(?:(\d{4,5})\s+)?"                             # AFRQ (nepovinné)
        r"(?:((?:[A-Z][a-z]{2})+)\s+)?"                  # LANGUAGE: Eng / EngSpa / EngSlkCmn (nepovinné)
        r"(.*)$"                                         # ADM BRC FMO REQ ...
    )
    today = datetime.now(timezone.utc).date()

    def expired(tdate):
        """TDATE je DDMMYY (270327 = 27. 3. 2027)."""
        if len(tdate) != 6:
            return False
        try:
            end = datetime(2000 + int(tdate[4:6]), int(tdate[2:4]), int(tdate[:2])).date()
        except ValueError:
            return False
        return end < today

    records = []
    skipped_noloc = 0
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(";"):
            continue
        m = row_rx.match(line)
        if not m:
            continue
        (freq_s, start_raw, end_raw, loc, powr_s, azim_s, _slw, _ant,
         days, fdate, tdate, _mod, _afrq, lang_code, tail) = m.groups()
        freq = int(freq_s)
        if not 2300 <= freq <= 26100:
            continue
        if expired(tdate):  # expirovaná platnost záznamu
            continue
        if loc not in sites:
            skipped_noloc += 1
            continue
        site_name, lat, lon = sites[loc]
        kw = int(powr_s) if powr_s.isdigit() and int(powr_s) > 0 else 100
        # HFCC 360 nepoužívá; 0 má v datech skoro jen nesměrové typy antén (7xx/9xx)
        # -> 0 bereme jako všesměrovou (None), ne jako anténu mířící na sever.
        azimuth = int(azim_s) if azim_s.isdigit() and int(azim_s) > 0 else None
        tokens = tail.split()
        adm = tokens[0] if tokens else ""
        brc_code = tokens[1] if len(tokens) > 1 else (tokens[0] if tokens else "")
        station = brc.get(brc_code, brc_code) if brc_code else site_name
        # Složený kód (EngSpa) = víc jazyků v jednom vysílání -> "English / Spanish"
        lang = " / ".join(langs.get(c, c) for c in re.findall(r"[A-Z][a-z]{2}", lang_code or ""))
        is_china = adm == "CHN" or any(p in station for p in CHINA_NAME_PATTERNS)
        records.append({
            "freq": freq,
            "start": f"{start_raw[:2]}:{start_raw[2:]}",
            "end": f"{end_raw[:2]}:{end_raw[2:]}",
            "station": station,
            "country": adm,
            "lang": lang,
            "site": site_name,
            "lat": lat, "lon": lon,
            "kw": kw,
            "isChina": is_china,
            "azimuth": azimuth,
            "days": "" if days in ("", "1234567") else days,
        })
    if skipped_noloc:
        print(f"[!] {skipped_noloc} HFCC záznamů bez známého kódu vysílače přeskočeno.")
    return records


def sync_hfcc(preferred_season):
    """Stáhne HFCC rozvrh - zkusí preferovanou sezónu, pak předchozí.
    Vrací (záznamy, skutečně stažená sezóna)."""
    for season in season_candidates(preferred_season):
        try:
            files = hfcc_files(season)
            print(f"[*] Stahuji HFCC {season.upper()} ...")
            schedule = download_text(files["schedule"])
            sites = parse_hfcc_site(download_text(files["site"]))
            brc = parse_hfcc_table(download_text(files["broadcas"]))
            langs = parse_hfcc_table(download_text(files["language"]))
            records = parse_hfcc_schedule(schedule, sites, brc, langs)
            if records:
                print(f"[+] HFCC {season.upper()}: {len(records)} oken, "
                      f"{len(sites)} vysílacích míst")
                return records, season
        except Exception as exc:
            print(f"[!] HFCC {season} nedostupné ({exc}).")
    return [], None


# ---------------------------------------------------------------------------
# 1c) AOKI ("Bi Newsletter for DXers", běžně "AOKI list") - třetí velký seznam.
#      Pozn.: osobní newsletter správce webu, ne oficiální materiál klubu NDXC.
#      Tvůrce neuvádí licenci; používáno nekomerčně s atribucí (viz legal.html).
#      Nejlepší jména stanic, přesné souřadnice vysílačů (DDMMSS), výkony,
#      azimuty i dny vysílání; distribuce jako zip se Shift-JIS textem.
# ---------------------------------------------------------------------------
AOKI_ZIP_URL = "https://www1.m2.mediacat.ne.jp/binews/us/xz/xz{season}.zip"


def download_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dx-radar/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _ddmmss_to_dec(val, hemi_neg):
    """'372221N' / '1405056E' -> desetinné stupně."""
    neg = val[-1] in hemi_neg
    body = val[:-1]
    deg = len(val) == 7 and 2 or 3  # lat: DDMMSS, lon: DDDMMSS
    d = int(body[:deg])
    m = int(body[deg:deg + 2])
    s = int(body[deg + 2:deg + 4])
    out = d + m / 60 + s / 3600
    return -out if neg else out


def parse_aoki_txt(text):
    """xzb26.txt (Shift-JIS, fixní sloupce) -> záznamy kompatibilní s PWA."""
    lines = text.splitlines()
    header = next((l for l in lines if "FRE" in l and "STATION" in l and "L/L" in l), None)
    if header is None:
        return []
    labels = ["FRE", "STATION", "UTC", "Su-W-Sa", "Language", "Pow",
              "Azi", "Location", "ADM", "L/L", "Remarks"]
    pos_list = sorted((header.find(l), l) for l in labels if header.find(l) != -1)
    bounds = {}
    for i, (p, lab) in enumerate(pos_list):
        end = pos_list[i + 1][0] if i + 1 < len(pos_list) else len(header)
        bounds[lab] = (p, end)
    seg = lambda line, lab: line[bounds[lab][0]:bounds[lab][1]].strip()

    def convert_days(days):
        """AOKI: pozice 1-7, den 1 = neděle -> interní 1=Po ... 7=Ne."""
        out = ""
        for i, ch in enumerate(days.ljust(7), start=1):
            if ch.isdigit():
                aoki_day = int(ch)  # 1=Ne, 2=Po, ..., 7=So
                internal = {1: 7, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}[aoki_day]
                out += str(internal)
        return "".join(sorted(out))

    records = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith(("b2", "a2", "FRE")):
            continue
        try:
            freq = int(seg(line, "FRE"))
        except ValueError:
            continue
        if not 2300 <= freq <= 26100:
            continue
        time_raw = seg(line, "UTC")
        if len(time_raw) != 9 or "-" not in time_raw:
            continue
        start_s, end_s = time_raw.split("-")
        if not (start_s.isdigit() and end_s.isdigit()):
            continue
        station = seg(line, "STATION") or "?"
        lang = seg(line, "Language")
        powr_s = seg(line, "Pow")
        azi_s = seg(line, "Azi")
        site = seg(line, "Location") or station
        adm = seg(line, "ADM")
        ll = seg(line, "L/L")
        if len(ll) >= 14:  # 372221N1405056E
            try:
                lat = round(_ddmmss_to_dec(ll[:7], "S"), 3)
                lon = round(_ddmmss_to_dec(ll[7:], "W"), 3)
            except ValueError:
                continue
        else:
            continue
        kw = int(powr_s) if powr_s.isdigit() and int(powr_s) > 0 else 100
        azimuth = int(azi_s) if azi_s.isdigit() else None  # 'ND' = nesměrová; 0 = sever
        days = convert_days(seg(line, "Su-W-Sa"))
        is_china = adm in ("CHN", "CN") or any(p in station for p in CHINA_NAME_PATTERNS)
        records.append({
            "freq": freq,
            "start": f"{start_s[:2]}:{start_s[2:]}",
            "end": f"{end_s[:2]}:{end_s[2:]}",
            "station": station,
            "country": adm,
            "lang": lang,
            "site": site,
            "lat": lat, "lon": lon,
            "kw": kw,
            "isChina": is_china,
            "azimuth": azimuth,
            "days": "" if days == "1234567" else days,
        })
    return records


def sync_aoki(preferred_season):
    """Stáhne AOKI zip (aktuální sezóna, pak předchozí), rozbalí hlavní txt a zparsuje."""
    import io
    import zipfile
    for season in season_candidates(preferred_season):
        try:
            print(f"[*] Stahuji AOKI {season.upper()} ...")
            zf = zipfile.ZipFile(io.BytesIO(download_bytes(AOKI_ZIP_URL.format(season=season))))
            # hlavní seznam: člen 'xz*.txt' (ne userlist1.txt s utility stanicemi)
            member = next((n for n in zf.namelist()
                            if n.lower().startswith("xz") and n.lower().endswith(".txt")), None)
            if not member:
                continue
            records = parse_aoki_txt(zf.read(member).decode("shift_jis", errors="replace"))
            if records:
                print(f"[+] AOKI {season.upper()}: {len(records)} oken "
                      f"(včetně přesných souřadnic vysílačů)")
                return records, season
        except Exception as exc:
            print(f"[!] AOKI {season} nedostupné ({exc}).")
    return [], None


@functools.lru_cache(maxsize=None)
def _minute_set(start, end):
    """Minuty dne (po 5 min), kdy okno start-end běží; přes půlnoc se zalomí."""
    return {m for m in range(0, 1440, 5) if is_time_active(start, end, m)}


def _days_overlap(a, b):
    """Prázdné 'days' = denně; jinak musí mít obě okna aspoň jeden společný den."""
    return not a or not b or bool(set(a) & set(b))


_GENERIC_WORDS = {"RADIO", "VOICE", "OF", "THE", "INTERNATIONAL", "NATIONAL",
                  "BROADCASTING", "STATION", "SERVICE", "WORLD", "AND"}


def _station_words(name):
    words = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper()).split()
    return [_STATION_ALIAS.get(w, w) for w in words]


def same_station(a, b):
    """Stejná stanice i při různém zápisu napříč zdroji: shoda normalizovaného
    názvu, nebo je kratší název celými slovy začátkem delšího
    ('WWV' ~ 'WWV Colorado (m.ann.)', ne však 'WWV' ~ 'WWVH Hawaii').
    Samotná obecná slova ('Radio', 'Voice of') na shodu nestačí."""
    wa, wb = _station_words(a), _station_words(b)
    if not wa or not wb:
        return False
    if "".join(wa) == "".join(wb):
        return True
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return long_[:len(short)] == short and not set(short) <= _GENERIC_WORDS


def _same_site(a, b):
    """Stejný vysílací komplex (do dedup.sameSiteKm ze scoring.js; HFCC „Sofia" vs AOKI
    „Kostinbrod" 20 km) - jen u přesných poloh, ne EiBi centroidů."""
    if a.get("approxLoc") or b.get("approxLoc"):
        return False
    return calc_geodesic(a["lat"], a["lon"], b["lat"], b["lon"])[0] <= SCORING["dedup"]["sameSiteKm"]


def _days_cover(o, r):
    """Pokrývají dny vysílání o všechny dny r? (prázdné = denně)"""
    od, rd = o.get("days", ""), r.get("days", "")
    return not od or (bool(rd) and set(rd) <= set(od))


def find_cross_source_dup(r, index):
    """Záznam z prioritnějšího zdroje, který je totéž vysílání jako r, jinak None.
    Totéž vysílání = stejný kmitočet + (stejná stanice NEBO stejný vysílač: dva různé
    programy nemůžou jít v tutéž chvíli na stejném kmitočtu z jednoho místa - HFCC
    uvádí provozovatele, AOKI program). r se vyřadí, jen když ho takové záznamy
    pokrývají CELÝ (čas i dny) - jinak by zmizel vysílací čas, který prioritnější
    zdroj nemá. Různé stanice z různých vysílačů se NIKDY neslučují."""
    need = _minute_set(r["start"], r["end"])
    matches = [o for o in index.get(r["freq"], ())
               if _days_cover(o, r) and need & _minute_set(o["start"], o["end"])
               and (same_station(r.get("station"), o.get("station")) or _same_site(r, o))]
    covered = set().union(*(_minute_set(o["start"], o["end"]) for o in matches))
    return matches[0] if matches and need <= covered else None


def merge_schedules(*record_lists, stats=None):
    """Sloučení seznamů v pořadí priorit: HFCC > AOKI > EiBi.

    - uvnitř jednoho zdroje se zahodí jen úplně shodné záznamy,
    - mezi zdroji jen totéž vysílání (find_cross_source_dup),
    takže všechny různé stanice na jednom kmitočtu v datech zůstanou."""
    merged = []
    index = {}  # freq -> záznamy z dřívějších (prioritnějších) zdrojů
    stats = stats if stats is not None else {}
    stats.setdefault("exact", 0)
    stats.setdefault("cross", 0)
    for records in record_lists:
        seen_exact = set()
        added = []
        for r in records:
            exact = json.dumps(r, sort_keys=True, ensure_ascii=False)
            if exact in seen_exact:
                stats["exact"] += 1
                continue
            seen_exact.add(exact)
            dup = find_cross_source_dup(r, index)
            if dup is not None:
                stats["cross"] += 1
                # jiný název téhož vysílání (typicky AOKI program k HFCC provozovateli)
                if "aka" not in dup and not same_station(r.get("station"), dup.get("station")):
                    dup["aka"] = r["station"]
                continue
            merged.append(r)
            added.append(r)
        for r in added:
            index.setdefault(r["freq"], []).append(r)
    return merged


def save_json(records, out_json, sources=None, season=None):
    with open(out_json, "w", encoding="utf-8") as out:
        json.dump(records, out, ensure_ascii=False)
    # metadata vedle dat: PWA podle ní pozná zdroje a hlavně sezónu
    # (aby si nepřemíchávala starou sezónu z repa s čerstvou online)
    meta = {
        "season": season or season_code(),
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "sources": sorted(sources or []),
    }
    meta_path = out_json.rsplit(".", 1)[0] + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as out:
        json.dump(meta, out, ensure_ascii=False)
    print(f"[+] Uloženo {len(records)} vysílacích oken do {out_json}")
    print(f"[+] Metadata (sezóna {meta['season']}, zdroje {meta['sources']}) do {meta_path}")
    return out_json


def load_schedule(args):
    """DB pro --now - stejná data jako PWA: schedule.json (HFCC + AOKI),
    s --eibi navíc schedule_eibi.json (doplněk s hrubou polohou, jako přepínač
    „+ EiBi" v aplikaci). --json/--csv úplně přebíjí (jeden explicitní zdroj)."""
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            return json.load(f), args.json
    if args.csv:
        return parse_eibi_csv(args.csv), args.csv

    db, labels = [], []
    files = [DEFAULT_OUT_JSON] + (["schedule_eibi.json"] if args.eibi else [])
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                db += json.load(f)
            labels.append(path)
        except (OSError, ValueError):
            print(f"[!] {path} nenačten - spusť nejdřív --sync.")
    if db:
        return db, " + ".join(labels)
    print("[!] Rozvrh nedostupný - používám vestavěný vzorek (dnešní večer 2026).")
    return SAMPLE_DB, "vestavěný vzorek"


# ---------------------------------------------------------------------------
# 2) CLI RADAR: stejný pipeline jako PWA, výstup do terminálu
# ---------------------------------------------------------------------------
ANTENNA_LABELS = {"whip": "Prut 60cm", "wire": "7m drát na cívce", "youloop": "YouLoop"}
RX_LABELS = {"pl330": "Tecsun PL-330", "airspy": "Airspy HF+ Discovery", "ats4732": "Mini ATS-4732"}


def passes_days(st, now_dt, day=None):
    """Pole DAYS ('1234567' = Po-Ne); prázdné = vysílá denně. day přebije den z now_dt."""
    days = st.get("days", "")
    if not days:
        return True
    return str(day or now_dt.isoweekday()) in days  # 1=Po ... 7=Ne


def solar_declination(dt):
    """Deklinace Slunce (°, +23,44 v létě, −23,44 v zimě) - roční období pro MUF i elevaci."""
    # fractional day-of-year (vč. hodin), ať sedí s JS: doy = (d - UTC(rok,0,0))/den
    doy = dt.timetuple().tm_yday + (dt.hour + dt.minute / 60) / 24
    return -23.44 * math.cos(math.radians((360 / 365) * (doy + 10)))


def solar_elevation(lat, lon, dt):
    """Elevace Slunce (°) nad bodem v daném UTC čase (pro denní absorpci)."""
    rad = math.pi / 180
    hour_utc = dt.hour + dt.minute / 60
    decl = solar_declination(dt)
    solar_time = hour_utc + lon / 15
    ha = (solar_time - 12) * 15
    return math.degrees(math.asin(
        math.sin(lat * rad) * math.sin(decl * rad) +
        math.cos(lat * rad) * math.cos(decl * rad) * math.cos(ha * rad)))


def day_absorption(freq, my_lat, my_lon, st_lat, st_lon, dt):
    """Denní absorpce D-vrstvy: osvětlená trasa pod freqCeil je silně tlumená.
    Shodné s PWA - hlavní oprava fantomových dálkových stanic v poledne."""
    da = SCORING["dayAbsorption"]
    if freq >= da["freqCeilKHz"]:
        return 0
    mid_lat, mid_lon = (my_lat + st_lat) / 2, (my_lon + st_lon) / 2
    sun_el = solar_elevation(mid_lat, mid_lon, dt)
    if sun_el <= 0:
        return 0
    freq_factor = (da["freqCeilKHz"] - freq) / da["freqCeilKHz"]
    return -jround(math.sin(math.radians(sun_el)) * freq_factor * da["maxPenalty"])


def muf_estimate(sfi, daylight=0.0, decl=0.0):
    """MUF odhad; denní posun plynule dle osvětlení prostředku trasy (daylight 0..1,
    gray-line). decl = deklinace Slunce: letní noční F2 vrstva nestihne zrekombinovat
    -> noční MUF ±seasonNight MHz (ve dne člen mizí). Shodné s PWA mufEstimate()."""
    m = SCORING["muf"]
    return jround(m["const"] + m["sfiMul"] * sfi + m["dayBoost"] * daylight
                  + m["seasonNight"] * (decl / 23.44) * (1 - daylight))


def path_daylight(lat1, lon1, lat2, lon2, dt):
    """0 = noc (Slunce nad středem trasy <= smoothFromDeg), 1 = den (>= smoothToDeg)."""
    m = SCORING["muf"]
    el = solar_elevation((lat1 + lat2) / 2, (lon1 + lon2) / 2, dt)
    return min(1.0, max(0.0, (el - m["smoothFromDeg"]) / (m["smoothToDeg"] - m["smoothFromDeg"])))


def propagation_adjust(freq, bearing, sfi, kp, daylight=0.0, decl=0.0):
    """Okno LUF-MUF + aurorální absorpce; shodné s PWA propagationAdjust()."""
    p = SCORING["prop"]
    muf = muf_estimate(sfi, daylight, decl)
    adj = 0
    if freq > muf * 1000 + p["mufMarginKHz"]:
        adj += p["aboveMufPenalty"]
    elif freq > muf * 1000 - p["mufMarginKHz"]:
        adj += p["nearMufPenalty"]
    if kp >= p["auroralKp"] and (bearing >= p["auroralFromDeg"] or bearing <= p["auroralToDeg"]):
        adj += p["auroralPenalty"]
    return adj


def skip_term(freq, dist):
    """Mrtvá zóna (skip) + multi-hop útlum; shodné s PWA skipTerm()."""
    sk = SCORING["skip"]
    f_mhz = freq / 1000
    floor = min(max((f_mhz - sk["pivotMHz"]) * sk["slopeKmPerMHz"], 0), sk["floorCapKm"])
    s = 0
    if dist < floor:
        s -= jround((floor - dist) / floor * sk["nearPenaltyMax"])
    if dist > sk["farStartKm"]:
        s -= jround((dist - sk["farStartKm"]) / sk["farDivKm"] * sk["farPenaltyMul"])
    return s


def _ant_band(buckets, f):
    """Anténní zisk dle pásma: první práh, pod který freq spadá."""
    for lim, val in buckets:
        if f < lim:
            return val
    return 0


def _score_one(st, qth, rx, ant, active_now, sfi, kp, ctx=None):
    """Šance jedné stanice proti zadanému stavu éteru (active_now).
    1:1 zrcadlo scoreStation() z PWA; konstanty ze SCORING (scoring.js).
    Hlavní výpis dostává právě vysílající; časová okna budoucí stav:
    ▶ po startu stanice, 🔓 po vypnutí rušitele."""
    lat, lon, alt, az_balcony = qth["lat"], qth["lon"], qth["alt"], qth["az"]
    ctx = ctx or make_ctx(qth, rx, ant, sfi, kp)
    now = ctx["now"]  # jednotný čas přepočtu (jako env.now v PWA), ne per stanice
    w = SCORING["weightsDefault"]
    dist, bearing = calc_geodesic(lat, lon, st["lat"], st["lon"])

    diff = abs(bearing - az_balcony)
    if diff > 180:
        diff = 360 - diff
    balcony_bonus = jround(math.cos(math.radians(diff)) * SCORING["balcony"]["amp"])

    tk = SCORING["takeoff"]
    alt_factor = min(alt / tk["altDivM"], tk["altCap"])
    takeoff = jround(alt_factor * tk["farMul"]) if dist > tk["farDistKm"] else jround(alt_factor * tk["nearMul"])

    beam_adj = 0
    az_tx = st.get("azimuth")
    if az_tx is not None:  # None = všesměrová anténa; 0 = míří na sever
        brg_tx_to_me = calc_geodesic(st["lat"], st["lon"], lat, lon)[1]
        delta = abs(brg_tx_to_me - az_tx)
        if delta > 180:
            delta = 360 - delta
        bm = SCORING["beam"]
        beam_adj = bm["nearBonus"] if delta <= bm["nearDeg"] else (
            bm["midBonus"] if delta <= bm["midDeg"] else bm["farPenalty"])

    a = SCORING["antenna"]
    antenna = 0
    if ant == "whip":
        antenna = _ant_band(a["whip"], st["freq"])
    elif ant == "wire":
        antenna = _ant_band(a["wire"], st["freq"])
    elif ant == "youloop":
        antenna = _ant_band(a["youloop"], st["freq"])
        if rx == "airspy":
            antenna += a["youloopAirspyBonus"]

    rx_bonus = SCORING["rxBonus"].get(rx, 0)
    power = jround(math.log10(max(st.get("kw") or 0, 1) / SCORING["power"]["centerKw"]) * SCORING["power"]["mul"])

    daylight = path_daylight(lat, lon, st["lat"], st["lon"], now)
    prop_adj = propagation_adjust(st["freq"], bearing, sfi, kp, daylight, solar_declination(now))
    day_absorb = day_absorption(st["freq"], lat, lon, st["lat"], st["lon"], now)
    skip = skip_term(st["freq"], dist)

    # QRM jen od rušitelů, kteří na QTH reálně dopadají silněji; active_now=None = bez QRM
    qrm_now = active_now or []
    qrm_plus5 = next((o for o in qrm_now if o is not st
                      and o["freq"] == st["freq"] + 5 and louder(o, st, ctx)), None)
    qrm_minus5 = next((o for o in qrm_now if o is not st
                       and o["freq"] == st["freq"] - 5 and louder(o, st, ctx)), None)
    co_channel = next((o for o in qrm_now if o is not st
                       and o["freq"] == st["freq"] and louder(o, st, ctx)), None)

    q = SCORING["qrm"]
    tip = "AM, BW 3.5 kHz (čistý kanál)"
    qrm_penalty = 0
    if co_channel:
        qrm_penalty = q["coChannel"]
        tip = f"Silné krytí ({co_channel['station']} do {co_channel['end']} UTC). Čekej na vypnutí nosné!"
    elif qrm_plus5 and qrm_minus5:
        # rušitel z obou stran: postranním pásmem (USB/LSB) se dá uhnout jen jednomu
        qrm_penalty = q["adjacentBoth"]
        tip = (f"QRM z obou stran ({st['freq'] - 5} i {st['freq'] + 5} kHz) -> "
               f"zúži filtr na BW 2 kHz, případně sync AM!")
    elif qrm_plus5:
        qrm_penalty = q["adjacent"]
        tip = f"QRM z {st['freq'] + 5} kHz ({qrm_plus5['station']}) -> Přepni na LSB, BFO 00, BW 2.5 kHz!"
    elif qrm_minus5:
        qrm_penalty = q["adjacent"]
        tip = f"QRM z {st['freq'] - 5} kHz ({qrm_minus5['station']}) -> Přepni na USB, BFO 00, BW 2.5 kHz!"
    if ant == "youloop" and q.get("loopHalves"):
        qrm_penalty = jround(qrm_penalty / 2)

    raw = (SCORING["base"] + rx_bonus
           + balcony_bonus * w["balcony"]
           + takeoff + beam_adj + antenna
           + power * w["power"]
           + (prop_adj + day_absorb) * w["prop"]
           + skip * w["skip"]
           + qrm_penalty)
    cl = SCORING["clamp"]
    score = max(cl["min"], min(cl["max"], jround(raw)))
    return {"dist": dist, "bearing": bearing, "diff": jround(diff), "score": score, "tip": tip}


def score_stations(db, qth, rx="pl330", ant="whip", sfi=None, kp=None,
                   blacklist=(), now_minutes=None, now_dt=None):
    """Stejný pipeline jako PWA evaluateStations(): aktivní teď + dnes + mimo blacklist,
    deduplikace, pak skóre proti tomuto stavu éteru. now_dt/now_minutes = jednotný čas
    celého přepočtu (i pro polohu Slunce); now_minutes přebije čas dne z now_dt."""
    if sfi is None:
        sfi = SCORING["spaceWeatherDefault"]["sfi"]
    if kp is None:
        kp = SCORING["spaceWeatherDefault"]["kp"]
    now_dt = now_dt or datetime.now(timezone.utc)
    if now_minutes is None:
        now_minutes = now_dt.hour * 60 + now_dt.minute
    else:
        now_dt = now_dt.replace(hour=now_minutes // 60, minute=now_minutes % 60)

    # Dny PŘED deduplikací: stanice, která dnes nevysílá, nesmí strhávat QRM ostatním
    # ani vytlačit dnešní záznam téže stanice. Blacklist jen SKRÝVÁ z výpisu - v éteru
    # skrytá stanice dál vysílá, takže v active_all zůstává jako zdroj rušení.
    ctx = make_ctx(qth, rx, ant, sfi, kp, now_dt)
    active_all = dedup_active([
        st for st in db
        if is_time_active(st.get("start", "00:00"), st.get("end", "23:59"), now_minutes)
        and passes_days(st, now_dt)], ctx)
    results = [{**st, **_score_one(st, qth, rx, ant, active_all, sfi, kp, ctx),
                "mins_left": minutes_left(st, now_minutes)}
               for st in active_all if not is_blacklisted(st, blacklist)]
    results.sort(key=lambda r: r["score"], reverse=True)
    return results, active_all, now_minutes


def collect_time_windows(db, active_all, now_minutes, blacklist, qth, rx, ant,
                         sfi, kp, max_min=60, min_score=0, now_dt=None):
    """⏱ Časová okna: jen budoucí události, které zatím neslyšíš -
    startující stanice (▶) a kanály, kde silný rušitel brzy vypne (🔓).
    ŠANCE se počítá proti budoucímu stavu éteru (po startu / po vypnutí
    rušitele), takže okna jdou řadit i podle pravděpodobnosti úlovku."""
    now_dt = now_dt or datetime.now(timezone.utc)
    today = now_dt.isoweekday()
    tomorrow = today % 7 + 1
    ctx = make_ctx(qth, rx, ant, sfi, kp, now_dt)
    items = []
    seen = set()

    def push(st, t, typ, info, active_now):
        k = station_key(st)
        if k in seen:
            return
        sc = _score_one(st, qth, rx, ant, active_now, sfi, kp, ctx)
        if sc["score"] < min_score:  # jako PWA: min. skóre platí i pro okna
            return
        seen.add(k)
        items.append({"t": t, "typ": typ, "freq": st["freq"], "station": st["station"],
                      "kw": st.get("kw", 0), "score": sc["score"], "info": info})

    # a) Kanál, kde silný rušitel brzy vypne a vyčistí frekvenci slabšímu DXovi.
    # Jen deduplikované active_all: surová db by u duplikátu téže stanice (HFCC+AOKI)
    # hlásila, že ji „překrývá" její vlastní dvojče.
    for st in active_all:
        if is_blacklisted(st, blacklist):
            continue
        stronger = next((o for o in active_all if o is not st
                         and o["freq"] == st["freq"] and louder(o, st, ctx)), None)
        if not stronger:
            continue
        clear_in = minutes_left(stronger, now_minutes)  # celodenní rušitel = inf, nevypne
        if clear_in <= max_min:
            # šance až po vyčištění kanálu: silnější rušitelé už nevysílají
            cleaned = [o for o in active_all
                       if not (o is not st and o["freq"] == st["freq"] and louder(o, st, ctx))]
            push(st, clear_in, "🔓",
                 f"od {stronger['end']} UTC čistý kanál (vypíná {stronger['station']})", cleaned)
    # b) Stanice, které právě nejdou, ale startují v příští hodině.
    # Co už teď na stejném kmitočtu vysílá (navazující blok, i pod druhým názvem aka),
    # není „nový start".
    for st in active_all:
        seen.add(station_key(st))
        if st.get("aka"):
            seen.add(station_key({"freq": st["freq"], "station": st["aka"]}))
    for st in db:
        if is_blacklisted(st, blacklist):
            continue
        if is_time_active(st.get("start", "00:00"), st.get("end", "23:59"), now_minutes):
            continue
        starts_in = minutes_until(st.get("start", "00:00"), now_minutes)
        if starts_in > max_min:
            continue
        # start po půlnoci UTC = zítřejší den vysílání
        if not passes_days(st, now_dt, tomorrow if now_minutes + starts_in >= 1440 else today):
            continue
        # Stejný vysílač už na kmitočtu běží a poběží i po tomto startu = totéž vysílání
        # pod jiným názvem (HFCC provozovatel vs AOKI program), ne nový start.
        if any(o["freq"] == st["freq"] and _same_site(o, st)
               and minutes_left(o, now_minutes) > starts_in for o in active_all):
            continue
        push(st, starts_in, "▶", f"start v {st.get('start', '?')} UTC", active_all)
    items.sort(key=lambda x: x["t"])
    return items


def print_radar(results, windows, qth, rx, ant, now_minutes, limit=12, sort="freq", chance_label=""):
    utc_str = f"{now_minutes // 60:02d}:{now_minutes % 60:02d}"
    width = 94  # šířka tabulky cílů (jedno cíl = jeden řádek)
    hi, mid = SCORING["boundaries"]["hi"], SCORING["boundaries"]["mid"]
    sort_label = "dle kmitočtu" if sort == "freq" else "dle šance na úlovek"
    print("=" * width)
    print(f" QTH: {qth['name']} ({qth['alt']}m) | Azimut: {qth['az']}° "
          f"({compass_dir(qth['az'])}) | RX: {RX_LABELS.get(rx, rx)} + {ANTENNA_LABELS.get(ant, ant)}")
    print(f" Čas: {utc_str} UTC | Cílů: {len(results)} (řazeno {sort_label}"
          f"{'; filtr: ' + chance_label if chance_label else ''})")
    print("=" * width)

    # 🎯 CÍLE TEĎ nejdřív - to je to, co hráč na balkoně řeší; časová okna až pod tím
    print(f" 🎯 CÍLE TEĎ (řazeno {sort_label}):")
    print(f"{'MK':<4} {'NR':>3} {'FRQ':>7} {'STANICE':<25} {'ZEM':<3} {'VÝKON':>7} "
          f"{'KM':>5} {'AZIMUT':>7} {'±':>5} {'SK':>4}  KONEC")
    print("-" * width)
    for i, r in enumerate(results[:limit], 1):
        mark = "[★]" if r["score"] >= hi else ("[ +]" if r["score"] >= mid else "[  ]")
        name = r["station"] if len(r["station"]) <= 25 else r["station"][:24] + "…"
        ends = (f"⏹{r['end']} (zb.{r['mins_left']}m)" if r["mins_left"] <= 60
                else r["end"])
        print(f"{mark:<4} {i:>3} {r['freq']:>4}kHz {name:<25} {r.get('country', '?'):<3} "
              f"{r.get('kw', '?'):>4}kW {r['dist']:>5} {r['bearing']:>3}°{compass_dir(r['bearing']):<3} "
              f"{r['diff']:>4}° {r['score']:>4}  {ends}")
        # jen akční tipy (QRM kolize, krytí kanálu) - zbytek je stejná rada AM/BW
        if not r["tip"].startswith("AM, BW"):
            print(f"{'':>4} └─ {r['tip']}")
    if not results:
        print("Žádné aktivní cíle v tomto časovém okně.")
    print("=" * width)

    # ⏱ ČASOVÁ OKNA: budoucí události (starty, uvolňující se kanály)
    if windows:
        print(" ⏱ ČASOVÁ OKNA (příštích 60 minut) - co zatím neslyšíš:")
        print(f"{'ZA':>5}  T {'FRQ':>4}kHz {'STANICE':<25} {'kW':>5} {'SK':>4}  INFO")
        for w in windows[:30]:  # nejbližších 30, ať to nepřeteče obrazovku
            name = w["station"] if len(w["station"]) <= 25 else w["station"][:24] + "…"
            # T: > startuje, ! kanál se uvolní (emoji by rozhodila zarovnání)
            typ = ">" if w["typ"] == "▶" else "!"
            print(f"{str(w['t']) + 'm':>5}  {typ} {w['freq']:>4}kHz {name:<25} "
                  f"{w['kw']:>5} {w['score']:>4}  {w['info']}")
        if len(windows) > 30:
            print(f"   … a dalších {len(windows) - 30} událostí v příští hodině")
        print("=" * width)
    print(f"Legenda: SK = skóre (heuristika 5–99, ne %) | [★] Silné ≥{hi} | [ +] Slyšitelné ≥{mid} | "
          "⏹ končí do hodiny | └─ akční tip proti QRM")
    print("Okna: T > = stanice startuje | T ! = kanál se uvolní (rušitel vypíná); ŠANCE = po události")
    print("Více cílů: zvyš --limit | Řazení: --sort freq|score | "
          "Filtr šance: --chance top|mid|low|all | Místo: --lat --lon --alt --az")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="eibi_sync.py - Data Harvester + CLI radar pro Balkónový DX Engine")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--sync", action="store_true",
                      help="stáhnout rozvrhy (HFCC + AOKI + EiBi) a vygenerovat JSON pro PWA (default)")
    mode.add_argument("--now", action="store_true",
                      help="vypsat aktuální DX radar do terminálu")
    ap.add_argument("--source", default="all", choices=["all", "hfcc", "aoki", "eibi"],
                    help="který seznam vysílacích rozvrhů použít (default: all)")
    ap.add_argument("--csv", help="cesta k lokálnímu sked-*.csv (místo stahování)")
    ap.add_argument("--json", help="cesta k existujícímu schedule.json (místo CSV)")
    ap.add_argument("--out", default=DEFAULT_OUT_JSON, help="výstupní JSON pro --sync")
    ap.add_argument("--offline", action="store_true", help="nepřipojovat se k eibispace.de")
    ap.add_argument("--lat", type=float, help="šířka stanoviště (jinak střed ČR)")
    ap.add_argument("--lon", type=float, help="délka stanoviště (jinak střed ČR)")
    ap.add_argument("--alt", type=int, help="nadmorská výška v m (default 300)")
    ap.add_argument("--az", type=int, help="azimut balkónu ve stupních (default 180)")
    ap.add_argument("--rx", default="pl330", choices=["pl330", "airspy", "ats4732"],
                    help="přijímač (default: pl330)")
    ap.add_argument("--ant", default="whip", choices=["whip", "wire", "youloop"],
                    help="anténa (default: whip)")
    ap.add_argument("--sfi", type=int, default=None,
                    help="sluneční tok (default dle scoring.js)")
    ap.add_argument("--kp", type=int, default=None,
                    help="geomagnetický index Kp (default dle scoring.js)")
    ap.add_argument("--no-blacklist", "--show-china", dest="no_blacklist", action="store_true",
                    help="vypnout blacklist (výchozí seznam ze scoring.js: jen HFCC placeholdery)")
    ap.add_argument("--eibi", action="store_true",
                    help="přidat EiBi doplněk (schedule_eibi.json, hrubá poloha) jako přepínač „+ EiBi“ v PWA")
    ap.add_argument("--limit", type=int, default=12, help="počet cílů ve výpisu (default 12)")
    ap.add_argument("--min-score", type=int, default=None,
                    help="min. skóre pro časová okna (default jako PWA: hranice Slyšitelné ze scoring.js)")
    ap.add_argument("--sort", default="freq", choices=["freq", "score"],
                    help="řazení cílů: freq = dle kmitočtu (default), score = dle šance")
    ap.add_argument("--chance", default="top", choices=["all", "top", "mid", "low"],
                    help="filtr skóre dle pevných hranic jako v PWA: top = Silné, "
                         "mid = Slyšitelné, low = Slabé, all = vše")
    args = ap.parse_args()
    if args.sfi is None:
        args.sfi = SCORING["spaceWeatherDefault"]["sfi"]
    if args.kp is None:
        args.kp = SCORING["spaceWeatherDefault"]["kp"]

    qth = dict(DEFAULT_QTH)
    if args.lat is not None or args.lon is not None:
        qth["lat"] = args.lat if args.lat is not None else qth["lat"]
        qth["lon"] = args.lon if args.lon is not None else qth["lon"]
        qth["name"] = f"Vlastní ({qth['lat']:.4f}, {qth['lon']:.4f})"
    if args.alt is not None:
        qth["alt"] = args.alt
    if args.az is not None:
        qth["az"] = args.az

    if args.now:
        if args.lat is None and args.lon is None:
            print("⚠  Bez --lat/--lon počítám pro střed ČR (orientačně). "
                  "Zadej svoje QTH: --lat 50.08 --lon 14.42 --alt 300 --az 180")
        db, source = load_schedule(args)
        blacklist = () if args.no_blacklist else SCORING["blacklistDefault"]
        now_dt = datetime.now(timezone.utc)  # jeden čas pro cíle i okna (poloha Slunce)
        results, active, now_minutes = score_stations(
            db, qth, rx=args.rx, ant=args.ant, sfi=args.sfi, kp=args.kp, blacklist=blacklist,
            now_dt=now_dt)
        if args.sort == "freq":
            results.sort(key=lambda r: (r["freq"], -r["score"]))
        else:
            results.sort(key=lambda r: (-r["score"], r["freq"]))
        # Stejné pevné hranice jako PWA: Silné >= hi, Slyšitelné mid..hi, Slabé < mid.
        hi = SCORING["boundaries"]["hi"]
        mid = SCORING["boundaries"]["mid"]
        if args.chance == "top":
            shown = [r for r in results if r["score"] >= hi]
            chance_label = f"Silné (skóre ≥ {hi})"
        elif args.chance == "mid":
            shown = [r for r in results if mid <= r["score"] < hi]
            chance_label = f"Slyšitelné ({mid}–{hi - 1})"
        elif args.chance == "low":
            shown = [r for r in results if r["score"] < mid]
            chance_label = f"Slabé (skóre < {mid})"
        else:
            shown = results
            chance_label = "vše"
        windows = collect_time_windows(db, active, now_minutes,
                                       blacklist=blacklist, qth=qth,
                                       rx=args.rx, ant=args.ant, sfi=args.sfi, kp=args.kp,
                                       min_score=mid if args.min_score is None else args.min_score,
                                       now_dt=now_dt)
        print(f"[i] Zdroj dat: {source} ({len(db)} záznamů)")
        print_radar(shown, windows, qth, args.rx, args.ant, now_minutes,
                    args.limit, args.sort, chance_label)
        return 0

    # default: --sync (harvest: HFCC + AOKI + EiBi podle --source)
    preferred = season_code()

    sources = args.source if args.source != "all" else ["hfcc", "aoki", "eibi"]
    merged = []
    got_season = {}  # zdroj -> sezóna, kterou se skutečně povedlo stáhnout
    merge_stats = {}

    if "hfcc" in sources and not args.offline:
        hfcc_records, hfcc_season = sync_hfcc(preferred)
        if hfcc_records:
            got_season["hfcc"] = hfcc_season
    if "aoki" in sources and not args.offline:
        aoki_records, aoki_season = sync_aoki(preferred)
        if aoki_records:
            got_season["aoki"] = aoki_season
    # Nemíchat sezóny: když jeden zdroj už má aktuální a druhý jen předchozí,
    # předchozí vynech (rozvrhy se mezi sezónami výrazně liší).
    if len(set(got_season.values())) > 1:
        for src in [s for s, ssn in got_season.items() if ssn != preferred]:
            print(f"[!] {src.upper()} má jen sezónu {got_season.pop(src).upper()} "
                  f"(ostatní {preferred.upper()}) - vynechávám, ať se sezóny nemíchají.")
    if "hfcc" in got_season:
        merged = merge_schedules(merged, hfcc_records, stats=merge_stats)
    if "aoki" in got_season:
        merged = merge_schedules(merged, aoki_records, stats=merge_stats)
    main_season = next(iter(got_season.values()), None)
    # EiBi se do schedule.json NEMERGUJE (jen country-centroid souřadnice by kazily skóre).
    # Místo toho jde do samostatného schedule_eibi.json jako volitelný doplněk pro PWA:
    # stanice mimo HFCC/AOKI, označené approxLoc (hrubá poloha). Appka ho přimerguje
    # jen když uživatel zapne přepínač „+ EiBi".
    eibi_extra = []
    if "eibi" in sources:
        csv_path = args.csv
        eibi_season = None
        if not csv_path:
            if args.offline:
                print("[!] --offline bez --csv nemá EiBi co zpracovat.")
            else:
                csv_path, eibi_season = download_eibi("sked_eibi.csv")
        if csv_path:
            # download_eibi vrací název souboru (např. "sked-b26.csv") -> normalizuj na sezónu
            m = re.search(r"([ab]\d\d)", str(eibi_season or csv_path or ""))
            eibi_season = m.group(1) if m else None
            eibi_records = parse_eibi_csv(csv_path)
            if eibi_records and eibi_season and main_season and eibi_season != main_season:
                print(f"[i] EiBi ({eibi_season}) doplněk přeskočen - jiná sezóna než "
                      f"HFCC/AOKI ({main_season.upper()}).")
            elif eibi_records:
                # Doplněk = jen vysílání, která HFCC/AOKI nemá (stejná stanice v jiném
                # čase/dnech zůstává); různé stanice na stejném kmitočtu se nezahazují.
                eibi_extra = merge_schedules(merged, eibi_records)[len(merged):]
                print(f"[i] EiBi doplněk: {len(eibi_extra)} stanic navíc mimo HFCC/AOKI (hrubá poloha).")

    if not merged and not eibi_extra:
        print("[!] Žádná data k uložení.")
        return 1
    for src, ssn in got_season.items():
        print(f"[i] {src}: {ssn.upper()}")
    if merge_stats:
        print(f"[i] Sloučení HFCC+AOKI: {merge_stats['exact']} úplně shodných, "
              f"{merge_stats['cross']} totožných vysílání napříč zdroji vynecháno.")
    if merged:
        save_json(merged, args.out, sources=list(got_season.keys()), season=main_season)
    if eibi_extra:
        save_json(eibi_extra, "schedule_eibi.json", sources=["eibi"],
                  season=eibi_season or main_season)
    return 0


if __name__ == "__main__":
    sys.exit(main())
