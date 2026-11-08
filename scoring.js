/*
 * scoring.js — JEDINÝ ZDROJ laditelných konstant skóre pro DX Radar.
 *
 * Čtou ho OBA kódy:
 *   - index.html (PWA): načte přes <script src="scoring.js"> jako window.SCORING,
 *   - eibi_sync.py (CLI): vytáhne níže uvedený JSON blok a json.loads ho.
 *
 * Objekt uvnitř MUSÍ zůstat čistý JSON (bez komentářů, bez koncových čárek,
 * bez JS výrazů), aby ho Python spolehlivě rozparsoval. Laď jen tady — změna
 * se propíše do aplikace i do CLI radaru, takže se obě strany nerozejdou.
 *
 * blacklistDefault: skryté stanice (jen ze seznamu/radaru/oken; jako QRM se počítají dál). Výchozí seznam
 * skrývá jen HFCC placeholdery bez skutečného vysílatele - čínské ani jiné stanice
 * ne. Uživatel si dopíše: vzor malými (cnr) = slovo/fráze v názvu, smí za ním být
 * číslo ("cnr" chytí "CNR1", ale "cri" ne "Radio Cristiana"); kód VELKÝMI (CHN)
 * = celá země (přesná shoda).
 *
 * Formulový tvar (pořadí členů, MUF/skip/absorpce) je zrcadlený v obou jazycích;
 * zde žijí pouze čísla, která se reálně ladí.
 */
window.SCORING = {
  "base": 50,
  "clamp": { "min": 5, "max": 99 },
  "boundaries": { "hi": 68, "mid": 50 },
  "spaceWeatherDefault": { "sfi": 142, "kp": 2 },
  "rxBonus": { "pl330": 0, "airspy": 12, "ats4732": -6 },
  "weightsDefault": { "balcony": 1.0, "power": 1.2, "skip": 1.0, "prop": 1.5 },
  "balcony": { "amp": 25 },
  "takeoff": { "altDivM": 1000, "altCap": 1.5, "farDistKm": 3500, "farMul": 15, "nearMul": 5 },
  "beam": { "nearDeg": 45, "midDeg": 90, "nearBonus": 8, "midBonus": 0, "farPenalty": -15 },
  "antenna": {
    "whip": [[5000, -18], [9000, -6], [15000, 10], [999999, 6]],
    "wire": [[5000, 8], [10000, 12], [18000, 4], [999999, 0]],
    "youloop": [[7000, -15], [15000, -6], [999999, -4]],
    "youloopAirspyBonus": 14
  },
  "power": { "centerKw": 100, "mul": 14 },
  "muf": { "const": 6, "sfiMul": 0.09, "dayBoost": 8, "dayStartH": 8, "dayEndH": 16,
    "smoothFromDeg": -6, "smoothToDeg": 20 },
  "prop": {
    "aboveMufPenalty": -35,
    "nearMufPenalty": -10,
    "mufMarginKHz": 3000,
    "auroralKp": 5,
    "auroralFromDeg": 300,
    "auroralToDeg": 60,
    "auroralPenalty": -20
  },
  "dayAbsorption": { "freqCeilKHz": 10000, "maxPenalty": 40 },
  "skip": {
    "pivotMHz": 7,
    "slopeKmPerMHz": 300,
    "floorCapKm": 4000,
    "nearPenaltyMax": 30,
    "farStartKm": 3000,
    "farDivKm": 2000,
    "farPenaltyMul": 8
  },
  "qrm": { "coChannel": -25, "adjacent": -8, "adjacentBoth": -16, "loopHalves": true,
    "minInterfererScore": 45, "louderMargin": 3 },
  "blacklistDefault": ["for new organization", "new organization", "disaster relief", "unknown"]
};
