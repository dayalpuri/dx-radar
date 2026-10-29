#!/usr/bin/env python3
"""
eibi_sync.py - Data Harvester + CLI radar pro Balkónový DX Engine.

Dvě funkce v jednom souboru (společný datový základ pro PWA dx-radar.html):

  1. HARVESTER:  stáhne aktuální rozvrh EiBi (sked-*.csv), spáruje země ITU kódem
                 s přibližnými GPS souřadnicemi, označí čínské vysílače
                 (isChina: true) a vygeneruje eibi_b26.json pro import do PWA.

  2. CLI RADAR:  s parametrem --now vypíše stejný "DX Radar" jako PWA přímo
                 do terminálu (sférická trigonometrie, kardioidní maska balkónu,
                 bonus nadmořské výšky, detekce QRM ±5 kHz, tipy pro PL-330).
                 Cíle jsou deduplikované napříč zdroji a defaultně řazené
                 dle kmitočtu (--sort score = dle šance). Časová okna obsahují
                 jen budoucí události (starty ▶, uvolňující se kanály 🔓);
                 brzy končící cíle se značí ⏹ přímo ve výpisu cílů.

Bez externích závislostí - pouze standardní knihovna Pythonu 3.

Použití:
  python3 eibi_sync.py --sync                 # stáhne EiBi a vygeneruje eibi.json
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --alt 300 --az 180   # radar pro zadané QTH
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --sort score  # cíle řazené dle skóre
  python3 eibi_sync.py --now --lat 50.08 --lon 14.42 --csv eibi.csv  # radar z lokálního CSV
"""

import argparse
import csv
import json
import math
import re
import sys
import urllib.request
from datetime import datetime, timezone

EIBI_BASE = "http://eibispace.de/dx/"
# Zimní sezóna (B) platí od poslední říjnové neděle do poslední březnové neděle.
SEASON_FILES = {"b": "sked-b26.csv", "a": "sked-a26.csv"}
DEFAULT_OUT_JSON = "eibi.json"

# ---------------------------------------------------------------------------
# Zjednodušený slovník ITU kódů -> přibližné souřadnice hlavního vysílacího uzlu.
# (Plná verze by parsovala sitelist z HFCC; EiBi samotné souřadnice nedodává.)
# ---------------------------------------------------------------------------
COUNTRY_COORDS = {
    "MLI": (12.65, -8.00),   # Mali
    "TZA": (-6.10, 39.26),   # Tanzanie
    "ETH": (8.88, 38.78),    # Etiopie
    "MDG": (-18.87, 47.50),  # Madagaskar
    "NGA": (9.05, 7.49),     # Nigérie
    "ZAF": (-26.55, 28.01),  # Jižní Afrika (Meyerton)
    "EGY": (31.18, 30.05),   # Egypt (Abis)
    "TUR": (39.93, 32.85),   # Turecko (Emirler)
    "GRC": (38.40, 23.60),   # Řecko (Avlis)
    "IRN": (29.45, 55.68),   # Írán (Sirjan)
    "IND": (13.23, 77.70),   # Indie (Bengaluru)
    "VNM": (21.13, 105.50),  # Vietnam
    "MMR": (16.86, 96.19),   # Myanmar
    "IDN": (-5.14, 119.43),  # Indonésie (Makassar)
    "MYS": (2.99, 101.78),   # Malajsie (Kajang)
    "THA": (14.02, 100.52),  # Thajsko (Udon Thani)
    "BRA": (-15.60, -47.90), # Brazílie (Brasília)
    "CHN": (39.90, 116.40),  # Čína
    "ROU": (44.75, 26.10),   # Rumunsko (Tiganesti)
    "ARS": (24.71, 46.67),   # Saúdská Arábie (Rijád)
    "OMA": (23.58, 58.38),   # Omán
    "CUB": (22.95, -82.40),  # Kuba (Bauta/Artemisa)
    "USA": (38.90, -77.00),  # USA (greenville ~35.9,-77.0; hl. uzel)
    "KOR": (37.55, 126.90),  # Jižní Korea
    "JPN": (35.68, 139.69),  # Japonsko
    "PHL": (14.58, 120.97),  # Filipíny
    "AUS": (-33.87, 151.21), # Austrálie (Sydney/Vyner)
    "CAN": (45.42, -75.70),  # Kanada (Sackville)
    "GBR": (51.48, -0.45),   # Velká Británie (Wootton)
    "FRA": (47.65, 1.30),    # Francie (Allouis)
    "DEU": (50.85, 9.65),    # Německo (Weener/Nauen)
    "ESP": (40.42, -3.70),   # Španělsko (Arganda)
    "ITA": (41.90, 12.50),   # Itálie (RMC Pisa ~43.7,10.4)
    "PRT": (38.75, -9.15),   # Portugalsko
    "NLD": (52.20, 5.40),    # Nizozemsko (Lopik/Mederfoort)
    "BEL": (50.85, 4.35),    # Belgie (Wavre)
    "SWE": (59.33, 18.07),   # Švédsko (Horby)
    "NOR": (59.90, 10.75),   # Norsko (Kvitsøy)
    "FIN": (60.45, 25.00),   # Finsko (Pori ~61.5,21.8)
    "RUS": (55.75, 37.62),   # Rusko (Moskva)
    "UKR": (50.45, 30.52),   # Ukrajina (Kyjev/Brovary)
    "POL": (52.23, 21.00),   # Polsko (Warszawa)
    "CZE": (50.09, 14.30),   # Česko (Liblice)
    "SVK": (48.15, 17.10),   # Slovensko
    "HUN": (47.50, 19.05),   # Maďarsko (Szolnoki/Sopron)
    "AUT": (48.20, 16.37),   # Rakousko (Moosbrunn)
    "SUI": (46.95, 7.45),    # Švýcarsko (Sottens)
    "ISR": (31.90, 34.90),   # Izrael
    "JOR": (32.00, 36.00),   # Jordánsko
    "LBN": (33.90, 35.50),   # Libanon
    "SYR": (33.50, 36.30),   # Sýrie
    "IRQ": (33.30, 44.40),   # Irák (Dohuk)
    "PAK": (33.70, 73.10),   # Pákistán (Islamabad)
    "BGD": (23.80, 90.40),   # Bangladéš (Savar)
    "LKA": (6.90, 79.90),    # Srí Lanka (Ekala)
    "NPL": (27.70, 85.30),   # Nepál
    "KAZ": (43.25, 76.90),   # Kazachstán (Alma-Ata)
    "UZB": (41.30, 69.25),   # Uzbekistán (Taškent)
    "TKM": (38.00, 63.20),   # Turkmenistán
    "KGZ": (42.87, 74.60),   # Kyrgyzstán
    "TWN": (24.71, 121.00),  # Tchaj-wan (Tamsui/Paochung)
    "PRK": (39.00, 125.75),  # Severní Korea (Kujang)
    "MNG": (47.90, 106.90),  # Mongolsko
    "ARG": (-34.60, -58.38), # Argentina (General Pacheco)
    "CHL": (-33.45, -70.67), # Chile (Colina/Rengo)
    "PER": (-12.05, -77.00), # Peru (Mala)
    "COL": (4.60, -74.08),   # Kolumbie
    "VEN": (10.50, -66.90),  # Venezuela (Turmero)
    "ECU": (-0.15, -78.35),  # Ekvádor
    "BOL": (-16.50, -68.15), # Bolívie
    "PRY": (-25.28, -57.60), # Paraguay
    "URY": (-34.90, -56.20), # Uruguay
    "MEX": (19.40, -99.10),  # Mexiko
    "GTM": (14.60, -90.50),  # Guatemala (San Marcos)
    "CRI": (9.90, -84.10),   # Kostarika (Cartago)
    "HND": (14.10, -87.20),  # Honduras
    "DZA": (36.75, 3.05),    # Alžírsko (Bechar/Ourgla)
    "LBY": (32.85, 13.20),   # Libye (Sabratha)
    "TUN": (36.80, 10.18),   # Tunisko (Sidi Tlat)
    "MAR": (33.60, -7.60),   # Maroko (Nador/Casablanca)
    "SDN": (15.60, 32.50),   # Súdán (Omdurman/Umm Haraz)
    "SSD": (4.85, 31.60),    # Jižní Súdán
    "ERI": (15.33, 38.93),   # Eritrea (Asmara)
    "DJI": (11.60, 43.15),   # Džibuti
    "SOM": (2.05, 45.33),    # Somálsko
    "KEN": (-1.28, 36.80),   # Keňa (Nairobi/Thika)
    "UGA": (0.32, 32.60),    # Uganda (Kampala)
    "COD": (-4.30, 15.30),   # DR Kongo (Kananga)
    "COG": (-4.25, 15.25),   # Kongo Brazzaville
    "CMR": (3.87, 11.52),    # Kamerun (Garoua)
    "GAB": (0.42, 9.47),     # Gabon (Ntoum/Moyabi)
    "CIV": (6.70, -5.30),    # Pobřeží slonoviny (Abidjan)
    "SEN": (14.70, -17.40),  # Senegal (Diam Niadio)
    "GHA": (5.60, -0.17),    # Ghana (Tema/Amansuri)
    "BFA": (12.35, -1.50),   # Burkina Faso
    "ZMB": (-15.40, 28.30),  # Zambie (Lusaka)
    "ZWE": (-17.80, 31.05),  # Zimbabwe (Gweru)
    "MOZ": (-25.97, 32.58),  # Mosambik (Maputo/Moatize)
    "MWI": (-13.95, 33.78),  # Malawi (Lilongwe/Mchijii)
    "NAM": (-22.50, 17.05),  # Namibie
    "AGO": (-8.80, 13.25),   # Angola (Benguela)
    "GNQ": (3.75, 8.78),     # Rovníková Guinea (Bata)
    "ARE": (24.43, 54.48),   # UAE (Dubai)
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
    "BGR": (42.70, 23.35),   # Bulharsko (Kostinbrod/Plovdiv)
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
}

# Čínské identifikátory: ITU kód, nebo vzor v názvu stanice (včetně relé mimo Čínu).
CHINA_ITU = {"CHN"}
CHINA_NAME_PATTERNS = ("CRI", "China Radio", "CNR", "China National", "PBS ",
                      "Voice of Strait", "Chinese")

# Generické výchozí QTH (střed ČR) — žádná konkrétní soukromá poloha v repu.
# Vlastní stanoviště zadej přes --lat/--lon/--alt/--az.
DEFAULT_QTH = {"name": "Výchozí (střed ČR)", "lat": 49.80, "lon": 15.47, "alt": 300, "az": 180}

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

BAND_NAMES = [(3200, "120m"), (4750, "90m"), (5006, "60m"),
              (6200, "49m"), (7450, "41m"), (9900, "31m"),
              (12100, "25m"), (13860, "22m"), (15800, "19m"),
              (17480, "16m"), (19020, "15m"), (21850, "13m"),
              (26100, "11m"), (99999, "13m")]


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
    return round(dist), round(bearing)


def compass_dir(az):
    dirs = ['S', 'SSV', 'SV', 'VSV', 'V', 'VJV', 'JV', 'JJV',
            'J', 'JJZ', 'JZ', 'ZJZ', 'Z', 'ZSZ', 'SZ', 'SSZ']  # sever/východ/jih/západ
    return dirs[round(az / 22.5) % 16]


def band_name(freq):
    if freq < 2300:
        return "120m"
    for hi, name in BAND_NAMES:
        if freq <= hi:
            return name
    return "11m"


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
def current_season():
    """B sezóna (zimní) = konec října až konec března."""
    now = datetime.now(timezone.utc)
    if now.month in (11, 12, 1, 2):
        return "b"
    if now.month == 10 and now.day >= 25:
        return "b"
    if now.month == 3 and now.day <= 25:
        return "b"
    return "a"


def download_eibi(csv_path):
    """Stáhne aktuální sked z eibispace.de. Zkusí B sezónu, pak A (fallback)."""
    candidates = [SEASON_FILES["b"], SEASON_FILES["a"]] if current_season() == "b" \
        else [SEASON_FILES["a"], SEASON_FILES["b"]]
    for fname in candidates:
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


def parse_eibi_csv(csv_path):
    """Rozparsuje sked-*.csv do záznamů kompatibilních s PWA (dx-radar.html).

    Formát EiBi (oddělovač ';', první řádek = hlavička):
      0: kHz, 1: HHMM-HHMM, 2: dny, 3: ITU země, 4: stanice, 5: jazyk,
      6: cílová oblast, 7: kód vysílače, 8: persistence, 9-10: platnost.
    """
    records = []
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
            })
    return records


def convert_eibi_csv_to_json(csv_path, out_json=DEFAULT_OUT_JSON):
    records = parse_eibi_csv(csv_path)
    if not records:
        print("[!] Ze souboru EiBi nepřišel žádný použitelný záznam.")
        return None
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
        return r.read().decode("latin-1")


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
        r"(?:([A-Za-z]{3})\s+)?"                         # LANGUAGE (nepovinné)
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
        azimuth = int(azim_s) if azim_s.isdigit() else 0
        tokens = tail.split()
        adm = tokens[0] if tokens else ""
        brc_code = tokens[1] if len(tokens) > 1 else (tokens[0] if tokens else "")
        station = brc.get(brc_code, brc_code) if brc_code else site_name
        lang_code = (lang_code or "").title()
        is_china = adm == "CHN" or any(p in station for p in CHINA_NAME_PATTERNS)
        records.append({
            "freq": freq,
            "start": f"{start_raw[:2]}:{start_raw[2:]}",
            "end": f"{end_raw[:2]}:{end_raw[2:]}",
            "station": station,
            "country": adm,
            "lang": langs.get(lang_code, lang_code),
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
    """Stáhne HFCC rozvrh - zkusí preferovanou sezónu, pak tu druhou."""
    seasons = [preferred_season] + [s for s in ("b26", "a26") if s != preferred_season]
    for season in seasons:
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
                return records
        except Exception as exc:
            print(f"[!] HFCC {season} nedostupné ({exc}).")
    return []


# ---------------------------------------------------------------------------
# 1c) AOKI (Bi Newsletter, Nagoya DX Circle) - třetí velký seznam.
#      Nejlepší jména stanic, přesné souřadnice vysílačů (DDMMSS), výkony,
#      azimuty i dny vysílání; distribuce jako zip se Shift-JIS textem.
# ---------------------------------------------------------------------------
AOKI_ZIP_URLS = {
    "b26": "https://www1.m2.mediacat.ne.jp/binews/us/xz/xzb26.zip",
    "a26": "https://www1.m2.mediacat.ne.jp/binews/us/xz/xza26.zip",
}


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
        azimuth = int(azi_s) if azi_s.isdigit() else 0  # 'ND' -> 0 (nesměrové)
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
    """Stáhne AOKI zip (sezóna b26/a26), rozbalí hlavní txt a zparsuje."""
    import io
    import zipfile
    seasons = [preferred_season] + [s for s in ("b26", "a26") if s != preferred_season]
    for season in seasons:
        try:
            print(f"[*] Stahuji AOKI {season.upper()} ...")
            zf = zipfile.ZipFile(io.BytesIO(download_bytes(AOKI_ZIP_URLS[season])))
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


def merge_schedules(*record_lists):
    """Sloučení seznamů v pořadí priorit: HFCC > AOKI > EiBi (dedup dle freq+start+end)."""
    merged = []
    seen = set()
    for records in record_lists:
        for r in records:
            key = (r["freq"], r["start"], r["end"])
            if key in seen:
                continue
            merged.append(r)
            seen.add(key)
    return merged


def save_json(records, out_json, sources=None):
    with open(out_json, "w", encoding="utf-8") as out:
        json.dump(records, out, ensure_ascii=False)
    # metadata vedle dat: PWA podle ní pozná zdroje a hlavně sezónu
    # (aby si nepřemíchávala starou sezónu z repa s čerstvou online)
    meta = {
        "season": "b26" if current_season() == "b" else "a26",
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
    """DB pro --now: všechny dostupné zdroje sloučené dohromady -
    eibi.json z --sync (HFCC + AOKI) plus sked_eibi.csv (EiBi), dedup
    dle freq+start+end (priorita: co je dřív v seznamu, to vyhrává).
    --json/--csv úplně přebíjí (jeden explicitní zdroj)."""
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            return json.load(f), args.json
    if args.csv:
        return parse_eibi_csv(args.csv), args.csv

    import os
    parts, labels = [], []
    js = None
    for cand in (DEFAULT_OUT_JSON, "eibi_b26.json"):
        try:
            with open(cand, encoding="utf-8") as f:
                js = json.load(f)
            labels.append(cand)
            break
        except OSError:
            pass
    if js:
        parts.append(js)
    # EiBi CSV přidat jen tehdy, když už není součástí JSONu z --sync
    meta_sources = []
    meta_path = DEFAULT_OUT_JSON.rsplit(".", 1)[0] + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta_sources = json.load(f).get("sources", [])
    except (OSError, ValueError):
        pass
    if "eibi" not in meta_sources:
        csv_path = "sked_eibi.csv" if os.path.exists("sked_eibi.csv") else None
        if not csv_path and not args.offline:
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), "sked_eibi.csv")
            got = download_eibi(tmp)
            csv_path = got[0] if got else None
        if csv_path:
            parts.append(parse_eibi_csv(csv_path))
            labels.append("sked_eibi.csv (EiBi)")
    if parts:
        db = merge_schedules(*parts)
        total = sum(len(p) for p in parts)
        if len(parts) > 1 and total != len(db):
            print(f"[+] Sloučeno {len(parts)} zdrojů: {total} -> {len(db)} záznamů "
                  f"(odstraněno {total - len(db)} duplicit).")
        return db, " + ".join(labels)
    print("[!] Data EiBi nedostupná - používám vestavěný vzorek (dnešní večer 2026).")
    return SAMPLE_DB, "vestavěný vzorek"


# ---------------------------------------------------------------------------
# 2) CLI RADAR: stejný pipeline jako PWA, výstup do terminálu
# ---------------------------------------------------------------------------
ANTENNA_LABELS = {"whip": "Prut 60cm", "wire": "Dlouhý drát", "loop": "Smyčka MLA-30+"}


def passes_days(st, now_dt):
    """HFCC pole DAYS ('1234567' = Po-Ne); prázdné = vysílá denně."""
    days = st.get("days", "")
    if not days:
        return True
    return str(now_dt.isoweekday()) in days  # 1=Po ... 7=Ne


def _score_one(st, qth, rx, active_now):
    """Šance jedné stanice proti zadanému stavu éteru (active_now).
    Hlavní výpis jí předává právě vysílající; časová okna budoucí stav:
    ▶ po startu stanice, 🔓 po vypnutí rušitele."""
    lat, lon, alt, az_balcony = qth["lat"], qth["lon"], qth["alt"], qth["az"]
    dist, bearing = calc_geodesic(lat, lon, st["lat"], st["lon"])
    diff = abs(bearing - az_balcony)
    if diff > 180:
        diff = 360 - diff
    balcony_bonus = round(math.cos(math.radians(diff)) * 25)
    alt_factor = min(alt / 1000, 1.5)
    takeoff = round(alt_factor * 15) if dist > 3500 else round(alt_factor * 5)

    # Korekce směrovosti vysílače (HFCC azimut antény):
    # stojíme-li v hlavním paprsku (+/-45°), bonus; mimo (>90°) paprsek, penalizace.
    beam_adj = 0
    az_tx = st.get("azimuth") or 0
    if az_tx > 0:
        brg_tx_to_me = calc_geodesic(st["lat"], st["lon"], lat, lon)[1]
        delta = abs(brg_tx_to_me - az_tx)
        if delta > 180:
            delta = 360 - delta
        beam_adj = 8 if delta <= 45 else (0 if delta <= 90 else -15)

    antenna = 0
    if rx == "whip":
        if st["freq"] < 5000:
            antenna = -18
        elif 9000 <= st["freq"] <= 12000:
            antenna = 12
    elif rx == "loop" and st["freq"] < 7500:
        antenna = 15
    power = round(math.log10(st.get("kw", 100)) * 14)

    # Útlum vzdáleností (multi-hop) - shodné s PWA: bez něj dostávaly extrémně
    # vzdálené stanice nereálně vysoké skóre. ~ -6 b / 1800 km nad 1000 km.
    dist_penalty = -round((dist - 1000) / 1800 * 6) if dist > 1000 else 0

    qrm_plus5 = next((o for o in active_now if o is not st
                      and o["freq"] == st["freq"] + 5 and o.get("kw", 0) >= st.get("kw", 0)), None)
    qrm_minus5 = next((o for o in active_now if o is not st
                       and o["freq"] == st["freq"] - 5 and o.get("kw", 0) >= st.get("kw", 0)), None)
    co_channel = next((o for o in active_now if o is not st
                       and o["freq"] == st["freq"] and o.get("kw", 0) > st.get("kw", 0)), None)

    tip = "AM, BW 3.5 kHz (čistý kanál)"
    qrm_penalty = 0
    if co_channel:
        qrm_penalty = -25
        tip = f"Silné krytí ({co_channel['station']} do {co_channel['end']} UTC). Čekej na vypnutí nosné!"
    elif qrm_plus5 and not qrm_minus5:
        qrm_penalty = -8
        tip = f"QRM z {st['freq'] + 5} kHz ({qrm_plus5['station']}) -> Přepni na LSB, BFO 00, BW 2.5 kHz!"
    elif qrm_minus5 and not qrm_plus5:
        qrm_penalty = -8
        tip = f"QRM z {st['freq'] - 5} kHz ({qrm_minus5['station']}) -> Přepni na USB, BFO 00, BW 2.5 kHz!"

    score = max(5, min(99, 35 + balcony_bonus + takeoff + antenna + power + beam_adj + qrm_penalty + dist_penalty))
    return {"dist": dist, "bearing": bearing, "diff": round(diff), "score": score, "tip": tip}


def score_stations(db, qth, rx="whip", hide_china=True, now_minutes=None, limit=10):
    """Pětistupňové síto: azimutová maska, výška, anténa, výkon, QRM kolize."""
    now_dt = datetime.now(timezone.utc)
    if now_minutes is None:
        now_minutes = now_dt.hour * 60 + now_dt.minute

    active_all = [st for st in db
                  if is_time_active(st.get("start", "00:00"), st.get("end", "23:59"), now_minutes)]
    # Deduplikace napříč zdroji (EiBi/HFCC/AOKI): nech nejsilnější záznam,
    # aby se jedno vysílání nezdvojovalo a nekazilo QRM analýzu (falešná krytí).
    dedup = {}
    for st in active_all:
        k = station_key(st)
        if k not in dedup or st.get("kw", 0) > dedup[k].get("kw", 0):
            dedup[k] = st
    active_all = list(dedup.values())
    results = []
    for st in active_all:
        if not passes_days(st, now_dt):
            continue
        if hide_china and st.get("isChina"):
            continue
        results.append({**st, **_score_one(st, qth, rx, active_all),
                         "mins_left": minutes_until(st.get("end", "23:59"), now_minutes)})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results, active_all, now_minutes


def collect_time_windows(db, active_all, now_minutes, hide_china, qth, rx, max_min=60):
    """⏱ Časová okna: jen budoucí události, které zatím neslyšíš -
    startující stanice (▶) a kanály, kde silný rušitel brzy vypne (🔓).
    ŠANCE se počítá proti budoucímu stavu éteru (po startu / po vypnutí
    rušitele), takže okna jdou řadit i podle pravděpodobnosti úlovku."""
    now_dt = datetime.now(timezone.utc)
    items = []
    seen = set()

    def push(st, t, typ, info, active_now):
        k = station_key(st)
        if k in seen:
            return
        seen.add(k)
        sc = _score_one(st, qth, rx, active_now)
        items.append({"t": t, "typ": typ, "freq": st["freq"], "station": st["station"],
                      "kw": st.get("kw", 0), "score": sc["score"], "info": info})

    # a) Kanál, kde silný rušitel brzy vypne a vyčistí frekvenci slabšímu DXovi
    for st in db:
        if hide_china and st.get("isChina"):
            continue
        if not is_time_active(st.get("start", "00:00"), st.get("end", "23:59"), now_minutes):
            continue
        if not passes_days(st, now_dt):
            continue
        stronger = next((o for o in active_all if o is not st
                         and o["freq"] == st["freq"] and o.get("kw", 0) > st.get("kw", 0)), None)
        if not stronger:
            continue
        if station_key(stronger) == station_key(st):
            continue  # stejná stanice (duplikát z jiného zdroje), ne rušitel
        clear_in = minutes_until(stronger.get("end", "23:59"), now_minutes)
        if clear_in <= max_min:
            # šance až po vyčištění kanálu: silnější rušitelé už nevysílají
            cleaned = [o for o in active_all
                       if not (o is not st and o["freq"] == st["freq"] and o.get("kw", 0) > st.get("kw", 0))]
            push(st, clear_in, "🔓",
                 f"od {stronger['end']} UTC čistý kanál (vypíná {stronger['station']})", cleaned)
    # b) Stanice, které právě nejdou, ale startují v příští hodině
    for st in db:
        if hide_china and st.get("isChina"):
            continue
        if is_time_active(st.get("start", "00:00"), st.get("end", "23:59"), now_minutes):
            continue
        if not passes_days(st, now_dt):
            continue
        starts_in = minutes_until(st.get("start", "00:00"), now_minutes)
        if starts_in <= max_min:
            push(st, starts_in, "▶", f"start v {st.get('start', '?')} UTC", active_all)
    items.sort(key=lambda x: x["t"])
    return items


def print_radar(results, windows, qth, rx, now_minutes, limit=12, sort="freq", chance_label=""):
    now = datetime.now(timezone.utc)
    utc_str = now.strftime("%H:%M")
    width = 94  # šířka tabulky cílů (jedno cíl = jeden řádek)
    sort_label = "dle kmitočtu" if sort == "freq" else "dle šance na úlovek"
    print("=" * width)
    print(f" QTH: {qth['name']} ({qth['alt']}m) | Azimut: {qth['az']}° "
          f"({compass_dir(qth['az'])}) | RX: PL-330 + {ANTENNA_LABELS.get(rx, rx)}")
    print(f" Čas: {utc_str} UTC | Cílů: {len(results)} (řazeno {sort_label}"
          f"{'; filtr: ' + chance_label if chance_label else ''})")
    print("=" * width)

    # 🎯 CÍLE TEĎ nejdřív - to je to, co hráč na balkoně řeší; časová okna až pod tím
    print(f" 🎯 CÍLE TEĎ (řazeno {sort_label}):")
    print(f"{'MK':<4} {'NR':>3} {'FRQ':>7} {'STANICE':<25} {'ZEM':<3} {'VÝKON':>7} "
          f"{'KM':>5} {'AZIMUT':>7} {'±':>5} {'%':>4}  KONEC")
    print("-" * width)
    for i, r in enumerate(results[:limit], 1):
        mark = "[★]" if r["score"] >= 75 else ("[ +]" if r["score"] >= 60 else "[  ]")
        name = r["station"] if len(r["station"]) <= 25 else r["station"][:24] + "…"
        ends = (f"⏹{r['end']} (zb.{r['mins_left']}m)" if r["mins_left"] <= 60
                else r["end"])
        print(f"{mark:<4} {i:>3} {r['freq']:>4}kHz {name:<25} {r.get('country', '?'):<3} "
              f"{r.get('kw', '?'):>4}kW {r['dist']:>5} {r['bearing']:>3}°{compass_dir(r['bearing']):<3} "
              f"{r['diff']:>4}° {r['score']:>3}%  {ends}")
        # jen akční tipy (QRM kolize, krytí kanálu) - zbytek je stejná rada AM/BW
        if not r["tip"].startswith("AM, BW"):
            print(f"{'':>4} └─ {r['tip']}")
    if not results:
        print("Žádné aktivní cíle v tomto časovém okně.")
    print("=" * width)

    # ⏱ ČASOVÁ OKNA: budoucí události (starty, uvolňující se kanály)
    if windows:
        print(" ⏱ ČASOVÁ OKNA (příštích 60 minut) - co zatím neslyšíš:")
        print(f"{'ZA':>5}  T {'FRQ':>4}kHz {'STANICE':<25} {'kW':>5} {'%':>4}  INFO")
        for w in windows[:30]:  # nejbližších 30, ať to nepřeteče obrazovku
            name = w["station"] if len(w["station"]) <= 25 else w["station"][:24] + "…"
            # T: > startuje, ! kanál se uvolní (emoji by rozhodila zarovnání)
            typ = ">" if w["typ"] == "▶" else "!"
            print(f"{str(w['t']) + 'm':>5}  {typ} {w['freq']:>4}kHz {name:<25} "
                  f"{w['kw']:>5} {w['score']:>4}%  {w['info']}")
        if len(windows) > 30:
            print(f"   … a dalších {len(windows) - 30} událostí v příští hodině")
        print("=" * width)
    print("Legenda: [★] šance ≥75 % | [ +] ≥60 % | ⏹ končí do hodiny | └─ akční tip proti QRM")
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
                      help="stáhnout rozvrhy (HFCC + EiBi) a vygenerovat JSON pro PWA (default)")
    mode.add_argument("--now", action="store_true",
                      help="vypsat aktuální DX radar do terminálu")
    ap.add_argument("--source", default="all", choices=["all", "hfcc", "aoki", "eibi"],
                    help="který seznam vysílacích rozvrhů použít (default: all)")
    ap.add_argument("--csv", help="cesta k lokálnímu sked-*.csv (místo stahování)")
    ap.add_argument("--json", help="cesta k existujícímu eibi.json (místo CSV)")
    ap.add_argument("--out", default=DEFAULT_OUT_JSON, help="výstupní JSON pro --sync")
    ap.add_argument("--offline", action="store_true", help="nepřipojovat se k eibispace.de")
    ap.add_argument("--lat", type=float, help="šířka stanoviště (jinak střed ČR)")
    ap.add_argument("--lon", type=float, help="délka stanoviště (jinak střed ČR)")
    ap.add_argument("--alt", type=int, help="nadmorská výška v m (default 300)")
    ap.add_argument("--az", type=int, help="azimut balkónu ve stupních (default 180)")
    ap.add_argument("--rx", default="whip", choices=["whip", "wire", "loop"],
                    help="profil antény (default: whip)")
    ap.add_argument("--show-china", action="store_true",
                    help="nechat v radaru i čínské stanice")
    ap.add_argument("--limit", type=int, default=12, help="počet cílů ve výpisu (default 12)")
    ap.add_argument("--sort", default="freq", choices=["freq", "score"],
                    help="řazení cílů: freq = dle kmitočtu (default), score = dle šance")
    ap.add_argument("--chance", default="top", choices=["all", "top", "mid", "low"],
                    help="filtr skóre jako v PWA: top = nejlepší tercil (default), "
                         "all = vše nad práh 30")
    args = ap.parse_args()

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
        results, active, now_minutes = score_stations(
            db, qth, rx=args.rx, hide_china=not args.show_china, limit=args.limit)
        if args.sort == "freq":
            results.sort(key=lambda r: (r["freq"], -r["score"]))
        else:
            results.sort(key=lambda r: (-r["score"], r["freq"]))
        # Stejná logika jako PWA: pod 30 % šance nezobrazujeme,
        # default = nejlepší tercil (rank-based, remízy nerozbíjejí hranice)
        viable = [r for r in results if r["score"] >= 30]
        by_score = sorted(viable, key=lambda r: -r["score"])
        n3 = math.ceil(len(by_score) / 3) if by_score else 0
        top_keys = {station_key(r) for r in by_score[:n3]}
        mid_keys = {station_key(r) for r in by_score[n3:2 * n3]}
        s_top = by_score[n3 - 1]["score"] if n3 else 0
        if args.chance == "top":
            shown = [r for r in viable if station_key(r) in top_keys]
            chance_label = f"nejlepší tercil ≥ {s_top} %"
        elif args.chance == "mid":
            shown = [r for r in viable if station_key(r) in mid_keys]
            chance_label = f"střední tercil (do {s_top} %)"
        elif args.chance == "low":
            shown = [r for r in viable
                     if station_key(r) not in top_keys and station_key(r) not in mid_keys]
            chance_label = "spodní tercil"
        else:
            shown = viable
            chance_label = "vše (šance ≥ 30 %)"
        windows = collect_time_windows(db, active, now_minutes,
                                       hide_china=not args.show_china, qth=qth, rx=args.rx)
        print(f"[i] Zdroj dat: {source} ({len(db)} záznamů)")
        print_radar(shown, windows, qth, args.rx, now_minutes, args.limit, args.sort, chance_label)
        return 0

    # default: --sync (harvest: HFCC + AOKI + EiBi podle --source)
    season = current_season()
    preferred = "b26" if season == "b" else "a26"

    sources = args.source if args.source != "all" else ["hfcc", "aoki", "eibi"]
    merged = []
    got_season = {}  # zdroj -> sezóna, kterou se skutečně povedlo stáhnout

    if "hfcc" in sources and not args.offline:
        hfcc_records = sync_hfcc(preferred)
        if hfcc_records:
            merged = merge_schedules(merged, hfcc_records)
            got_season["hfcc"] = preferred
    if "aoki" in sources and not args.offline:
        aoki_records, aoki_season = sync_aoki(preferred)
        if aoki_records:
            merged = merge_schedules(merged, aoki_records)
            got_season["aoki"] = aoki_season
    if "eibi" in sources:
        csv_path = args.csv
        eibi_season = None
        if not csv_path:
            if args.offline:
                print("[!] --offline bez --csv nemá EiBi co zpracovat.")
            else:
                csv_path, eibi_season = download_eibi("sked_eibi.csv")
        if csv_path:
            if eibi_season is None:
                eibi_season = "b26" if "b26" in (csv_path or "") else (
                    "a26" if "a26" in (csv_path or "") else None)
            eibi_records = parse_eibi_csv(csv_path)
            # EiBi s letní sezónou nepřidávat, pokud jiný zdroj dodal zimní B26
            fresh = any(s == preferred for s in got_season.values())
            if eibi_records and eibi_season and eibi_season != preferred and fresh:
                print(f"[i] EiBi ({eibi_season}) přeskočeno - data {preferred.upper()} "
                      f"jsou k dispozici z jiných zdrojů (mixování sezón by vytvářelo duchy).")
            elif eibi_records:
                merged = merge_schedules(merged, eibi_records)
                got_season["eibi"] = eibi_season

    if not merged:
        print("[!] Žádná data k uložení.")
        return 1
    for src, ssn in got_season.items():
        print(f"[i] {src}: {ssn.upper()}")
    save_json(merged, args.out, sources=list(got_season.keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
